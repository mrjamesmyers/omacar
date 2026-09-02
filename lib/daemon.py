"""omacar daemon — connect once, poll at tiered rates, publish a snapshot.

One long-lived connection. Opening a serial connection costs 5-8 seconds, so
nothing else in OmaCar is allowed to open one: the UI reads the snapshot this
writes, and the bar widget reads the cache.

    live.json       the current sample, rewritten atomically each fast tick
    telemetry.db    one row per second, for trips and history
"""
import json
import os
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
        timing REAL, lphk REAL, eff REAL)""")
    db.execute("CREATE INDEX IF NOT EXISTS samples_t ON samples(t)")
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


def main():
    # lease=False: this process is the one the lease exists to move aside.
    conn, port, kind = connect.connect(timeout=1.0, fast=True, lease=False)
    import obd

    if conn.status() != obd.OBDStatus.CAR_CONNECTED:
        publish({"connected": False, "status": str(conn.status()), "port": port})
        sys.exit(f"omacar daemon: not connected ({conn.status()})")

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

    def hand_over():
        """Close the port, wait for the lease to end, then take it back."""
        nonlocal conn, supported, cmds, db
        publish({"connected": False, "status": "yielded", "port": port,
                 "note": "a command is using the adapter"})
        try:
            conn.close()
        except Exception:                                     # noqa: BLE001
            pass
        while yielded_until():
            time.sleep(0.3)
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

            publish({
                "connected": True, "port": port, "kind": kind,
                "t": now, "uptime": now - started,
                "protocol": conn.protocol_name(),
                "supported": sorted(supported),
                "values": sample,
                "economy_lphk": lphk, "fuel_lph": lph,
                "efficiency": eff, "efficiency_basis": basis,
            })

            if now - last_row >= 1.0:
                db.execute(
                    "INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (now, sample.get("RPM"), sample.get("SPEED"),
                     sample.get("ENGINE_LOAD"), sample.get("THROTTLE_POS"),
                     sample.get("COOLANT_TEMP"), sample.get("INTAKE_TEMP"),
                     sample.get("MAF"), sample.get("SHORT_FUEL_TRIM_1"),
                     sample.get("LONG_FUEL_TRIM_1"), sample.get("TIMING_ADVANCE"),
                     lphk, eff))
                db.commit()
                last_row = now

            if now - last_survey >= survey.EVERY:
                slow_pass()

            tick += 1
            time.sleep(1.0 / FAST_HZ)
    except KeyboardInterrupt:
        pass
    finally:
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
