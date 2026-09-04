"""omacar daemon — connect once, poll at tiered rates, publish a snapshot.

One long-lived connection. Opening a serial connection costs 5-8 seconds, so
nothing else in OmaCar is allowed to open one: the UI reads the snapshot this
writes, and the bar widget reads the cache.

    live.json       the current sample, rewritten atomically each fast tick
    telemetry.db    one row per second, for trips and history
"""
import json
import os
import signal
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import connect  # noqa: E402
import survey  # noqa: E402
import telemetry  # noqa: E402

import records  # noqa: E402

LIVE = os.path.join(connect.STATE, "live.json")
# Resolved at open time rather than at import: the vehicle can change between
# the two, and it does — that is exactly what survey.prepare() is for.
DB = None
PIDFILE = os.path.join(connect.STATE, "daemon.pid")

# THE "SURVEY NOW" REQUEST FILE.
#
# The daemon owns the serial port -- one process, one /dev/ttyUSB0 -- so the
# API server cannot read the car itself. Before this existed the app's
# "Scan all systems" button called records.snapshot(), which reads the
# DATABASE, and dressed the already-stored result in a 190ms-per-module
# progress animation. The data was real (the daemon had collected it) but the
# button did not do what it said, and it finished fast enough that the person
# pressing it correctly suspected it of faking.
#
# A file is the right mechanism here rather than a socket or a signal: every
# other cross-process handoff in OmaCar is a file in the state directory
# (live.json, bench-pty, daemon.pid), it survives either side restarting, and
# a daemon that is not running simply never consumes it -- which the API can
# see and report honestly instead of pretending.
SURVEY_REQUEST = os.path.join(connect.STATE, "survey-now")

FAST_HZ = 5.0
MID_EVERY = 5          # fast ticks
SLOW_EVERY = 25


def open_db():
    db = sqlite3.connect(records.DB)
    db.execute("""CREATE TABLE IF NOT EXISTS samples (
        t REAL PRIMARY KEY, rpm REAL, speed REAL, load REAL, throttle REAL,
        coolant REAL, intake REAL, maf REAL, stft REAL, ltft REAL,
        timing REAL, lphk REAL, eff REAL, soc REAL)""")
    db.execute("CREATE INDEX IF NOT EXISTS samples_t ON samples(t)")
    # Databases written before the hybrid column existed -- which on this car
    # is 34,000 rows of real driving -- must not be thrown away to gain it.
    # ADD COLUMN is the one schema change SQLite makes in place and in constant
    # time, and old rows then read NULL, which is the honest value for a period
    # when nobody was asking the car the question.
    if "soc" not in {r[1] for r in db.execute("PRAGMA table_info(samples)")}:
        db.execute("ALTER TABLE samples ADD COLUMN soc REAL")
    db.commit()
    return db


def publish(payload):
    tmp = LIVE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, LIVE)


def value_of(result):
    if result is None or result.is_null():
        return None
    v = result.value
    return float(v.magnitude) if hasattr(v, "magnitude") else v


# Startup contention budget. Twelve tries at 2.5s is thirty seconds, which
# comfortably outlasts a dtclog sweep of four modules -- the thing that was
# actually holding the port when this failed. Bounded rather than infinite so
# `omacar daemon start` still reports failure on a car that is genuinely off,
# rather than hanging until somebody notices.
STARTUP_TRIES = 12
STARTUP_BACKOFF = 2.5
STARTUP_LOCK_WAIT = 20.0


def _unwind(_signum, _frame):
    """Turn a stop signal into the exception the loop already knows about.

    `omacar daemon stop` is `kill "$pid"` -- a plain SIGTERM. Python's default
    disposition for SIGTERM terminates the interpreter WITHOUT unwinding the
    stack, so the `finally` at the bottom of main() never ran: live.json was
    left saying connected=true with the daemon already gone, its pid file was
    left behind, and the serial port was released without anybody being told.

    Everything downstream then read a dead file as a live car. The bar panel
    offered "Stop" for fifteen seconds after there was nothing to stop, and
    then "Reconnect" -- which reads as "the link dropped" -- for a daemon the
    owner had deliberately shut down.

    Raising KeyboardInterrupt is the whole fix, because the loop already
    catches it and the finally already does the right thing. Nothing else
    needed to change.
    """
    raise KeyboardInterrupt


def main():
    # Installed before the port is opened, so a stop arriving during a slow
    # connect still unwinds rather than leaving a half-built daemon behind.
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, _unwind)
        except (ValueError, OSError):
            # Not the main thread, or a platform without SIGHUP. Losing the
            # handler is worth less than losing the daemon on startup.
            pass

    # lease=False: this process is the one the lease exists to move aside.
    #
    # BUT IT STILL HAS TO WAIT ITS TURN.
    #
    # lease=False skips request_port(), which skips take_port_lock() as well --
    # so the daemon used to open the serial device regardless of who was
    # already talking to it. On 2026-09-03 dtclog was mid-sweep when the daemon
    # started; two readers hit one ELM327, the adapter answered neither
    # properly, and the daemon exited "not connected". The owner was sitting in
    # the car with a perfectly healthy adapter reading 13.7 V.
    #
    # hand_over() has retried twenty times since it was written, because a
    # daemon that gives up its port mid-run and cannot get it back is obviously
    # broken. Startup had exactly the same problem and one attempt. So: wait
    # for whoever holds the exclusive lock to finish, then retry on the same
    # terms the running daemon already uses.
    import obd

    conn = port = kind = None
    for attempt in range(STARTUP_TRIES):
        # Taking the flock and immediately dropping it is how this waits for an
        # in-flight one-off command WITHOUT holding a lock for the daemon's
        # whole life -- which would deadlock every command that needs the port.
        if connect.take_port_lock(timeout=STARTUP_LOCK_WAIT):
            connect.release_port_lock()
        try:
            conn, port, kind = connect.connect(timeout=1.0, fast=True,
                                               lease=False)
        except SystemExit:
            raise
        except Exception:                                     # noqa: BLE001
            conn = None
        if conn is not None and conn.status() == obd.OBDStatus.CAR_CONNECTED:
            break
        if conn is not None:
            try:
                conn.close()
            except Exception:                                 # noqa: BLE001
                pass
            conn = None
        if attempt < STARTUP_TRIES - 1:
            # The adapter needs a moment after another reader has closed it --
            # the same 0.6s courtesy hand_over() already pays, rounded up
            # because a sweep can take longer than a lease to unwind.
            time.sleep(STARTUP_BACKOFF)

    if conn is None or conn.status() != obd.OBDStatus.CAR_CONNECTED:
        status = str(conn.status()) if conn is not None else "no connection"
        publish({"connected": False, "status": status, "port": port})
        sys.exit(f"omacar daemon: not connected ({status}) "
                 f"after {STARTUP_TRIES} attempts")

    with open(PIDFILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    supported = {c.name for c in conn.supported_commands}
    cmds = {tier: [n for n in names if n in supported]
            for tier, names in (("fast", telemetry.FAST),
                                ("mid", telemetry.MID),
                                ("slow", telemetry.SLOW))}

    # Which car is this? The VIN decides which record we open, so it has to be
    # read before anything opens one. Switching the file under a live SQLite
    # handle does not fail loudly — it refuses the next write with "attempt to
    # write a readonly database", which is a memorable way to spend an evening.
    survey.prepare(conn, obd)

    db = open_db()
    sample, tick, last_row = {}, 0, 0.0
    # The last complete published sample, echoed back during a hand-off.
    sample_snapshot = {}
    started = time.time()

    # The slow half of the car: codes, readiness, on-board tests, the VIN.
    # None of it changes at gauge rate and all of it costs bus time the gauge
    # would rather have, so it runs once on connect and then rarely. Without
    # it a real adapter feeds the sample stream and nothing else, and the
    # whole diagnostic side of the app has nothing to show.
    last_survey = 0.0

    def slow_pass():
        nonlocal last_survey
        last_survey = time.time()
        try:
            survey.survey(conn, obd)
        except Exception as e:                            # noqa: BLE001
            # A survey that fails must never take the gauge down with it.
            print(f"survey failed: {e}", file=sys.stderr, flush=True)

    slow_pass()

    def yielded_until():
        """Deadline on an active lease, or None when there is no live one.

        A lease past its deadline is treated as absent AND removed: a one-off
        command that crashed must not be able to pause the gauge permanently.
        """
        try:
            with open(connect.PORT_YIELD, encoding="utf-8") as f:
                until = float(f.read().strip())
        except (OSError, ValueError):
            return None
        if time.time() >= until:
            try:
                os.remove(connect.PORT_YIELD)
            except OSError:
                pass
            return None
        return until

    def yield_snapshot():
        """What to publish while the adapter is lent out.

        A HAND-OFF USED TO LOOK EXACTLY LIKE A DEAD DAEMON.

        This published {"connected": false, "status": "yielded"} and nothing
        else -- no `t`, no values. Every reader treats a sample with no
        timestamp as stale and a sample with no values as an offline car, so
        for the ten to twenty seconds of a DTC sweep the whole app decided the
        link was gone: the bar icon went grey, Stop became Connect, a driving
        car became "parked", and the watchdog filed an adapter-lost alert.
        Then it all came back. Every five minutes, for the length of a drive.

        The daemon is alive and the car is still on the other end of the cable,
        so it keeps saying so -- with a current `t`, the last readings it took,
        and a status that admits where the port went.
        """
        out = dict(sample_snapshot)
        out.update({
            "connected": False,
            "status": "yielded",
            "handover": True,
            "port": port,
            "t": time.time(),
            "note": "a command is using the adapter",
        })
        return out

    def hand_over():
        """Close the port, wait for the lease to end, then take it back."""
        nonlocal conn, supported, cmds, db
        publish(yield_snapshot())
        try:
            conn.close()
        except Exception:                                     # noqa: BLE001
            pass
        # Keep publishing through the wait. A lease can outlast the staleness
        # window, and a hand-off that goes stale is indistinguishable from a
        # daemon that died holding the port.
        while yielded_until():
            time.sleep(0.3)
            publish(yield_snapshot())
        # Same courtesy in the other direction: the command has just closed the
        # port and the adapter is mid-teardown.
        time.sleep(0.6)
        # Reconnect. survey.prepare() runs again because the VIN decides which
        # record is open, and a different car could have been plugged in while
        # we were not looking.
        for attempt in range(20):
            try:
                conn, _p, _k = connect.connect(timeout=1.0, fast=True, lease=False)
                if conn.status() == obd.OBDStatus.CAR_CONNECTED:
                    supported = {c.name for c in conn.supported_commands}
                    cmds.update({tier: [n for n in names if n in supported]
                                 for tier, names in (("fast", telemetry.FAST),
                                                     ("mid", telemetry.MID),
                                                     ("slow", telemetry.SLOW))})
                    survey.prepare(conn, obd)
                    db = open_db()
                    return True
            except SystemExit:
                pass
            except Exception:                                 # noqa: BLE001
                pass
            time.sleep(0.5)
        return False

    try:
        while True:
            # Someone wants the adapter. Step aside rather than make them
            # believe the cable has failed.
            if yielded_until():
                if not hand_over():
                    publish({"connected": False, "status": "lost", "port": port})
                    sys.exit("omacar daemon: could not reopen the adapter")

            # An on-demand survey, asked for by the app. Claimed by removing
            # the file BEFORE the work, so a survey that throws cannot leave a
            # request behind to be retried every tick forever.
            if os.path.exists(SURVEY_REQUEST):
                try:
                    os.remove(SURVEY_REQUEST)
                except OSError:
                    pass
                slow_pass()

            names = list(cmds["fast"])
            if tick % MID_EVERY == 0:
                names += cmds["mid"]
            if tick % SLOW_EVERY == 0:
                names += cmds["slow"]

            for n in names:
                sample[n] = value_of(conn.query(getattr(obd.commands, n)))

            lphk, lph = telemetry.economy(sample.get("MAF"), sample.get("SPEED"))
            eff, basis = telemetry.efficiency(sample)
            now = time.time()

            live_payload = {
                "connected": True, "port": port, "kind": kind,
                "t": now, "uptime": now - started,
                "protocol": conn.protocol_name(),
                "supported": sorted(supported),
                "values": dict(sample),
                "economy_lphk": lphk, "fuel_lph": lph,
                "efficiency": eff, "efficiency_basis": basis,
            }
            sample_snapshot.clear()
            sample_snapshot.update(live_payload)
            publish(live_payload)

            if now - last_row >= 1.0:
                # Columns named rather than positional. The bare VALUES form
                # this replaces was correct only for as long as nobody added a
                # column, and it would have failed silently by writing the new
                # value into the wrong field the first time somebody did.
                db.execute(
                    "INSERT OR REPLACE INTO samples "
                    "(t, rpm, speed, load, throttle, coolant, intake, maf, "
                    "stft, ltft, timing, lphk, eff, soc) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (now, sample.get("RPM"), sample.get("SPEED"),
                     sample.get("ENGINE_LOAD"), sample.get("THROTTLE_POS"),
                     sample.get("COOLANT_TEMP"), sample.get("INTAKE_TEMP"),
                     sample.get("MAF"), sample.get("SHORT_FUEL_TRIM_1"),
                     sample.get("LONG_FUEL_TRIM_1"), sample.get("TIMING_ADVANCE"),
                     lphk, eff, sample.get("HYBRID_BATTERY_REMAINING")))
                db.commit()
                last_row = now

            if now - last_survey >= survey.EVERY:
                slow_pass()

            tick += 1
            time.sleep(1.0 / FAST_HZ)
    except KeyboardInterrupt:
        pass
    finally:
        # This block is why _unwind() below exists. Reaching it is the ONLY
        # thing that tells the rest of the app the car is gone.
        publish({"connected": False, "status": "stopped", "port": port})
        db.close()
        conn.close()
        try:
            os.remove(PIDFILE)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
