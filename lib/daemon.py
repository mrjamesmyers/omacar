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

LIVE = os.path.join(connect.STATE, "live.json")
DB = os.path.join(connect.STATE, "telemetry.db")
PIDFILE = os.path.join(connect.STATE, "daemon.pid")

FAST_HZ = 5.0
MID_EVERY = 5          # fast ticks
SLOW_EVERY = 25


def open_db():
    db = sqlite3.connect(DB)
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
    conn, port, kind = connect.connect(timeout=1.0, fast=True)
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

    # Before anything opens the database: if the record in it belongs to the
    # simulator, move it aside. Doing this later — with the sample connection
    # already open — renames the file under a live handle, and the next write
    # fails with "attempt to write a readonly database", which is a memorable
    # way to spend an evening.
    survey.prepare()

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

    try:
        while True:
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
