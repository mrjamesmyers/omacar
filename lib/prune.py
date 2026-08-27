"""Keeping the record without keeping every second of it forever.

At one sample a second, a car driven a thousand miles a week writes about
eighty thousand rows a week — roughly 0.6 GB a year. On a tablet bolted to a
dashboard that is both a disk problem and a speed problem: every query the app
makes has to walk past it.

The fix is the one every time-series system lands on. Raw samples are a rolling
window, kept for as long as they are useful for actually looking at a drive.
Everything older is rolled into the daily figures that the year view uses
anyway, and then dropped. The rollup is computed from exactly the same maths as
the live path — same integration, same fuel model, same "never integrate across
a gap" rule — so the year does not develop a seam at the compaction boundary.

Nothing is lost that anybody looks at. What goes is the second-by-second detail
of a drive from four months ago, which no one has ever wanted.
"""

import os
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import records  # noqa: E402

# How much raw detail to keep. Long enough to open last month's odd drive in
# the data lab, short enough that the file stays small on a cheap tablet.
KEEP_DAYS = 45

# Rows are nominally a second apart. Anything longer is the daemon having been
# away, and integrating across it would invent distance.
MAX_STEP = 10
MOVING_KPH = records.MOVING_KPH
AFR = records.AFR_GASOLINE
DENSITY = records.FUEL_DENSITY_G_PER_L

# What the tank costs, for the daily cost column. Overridden from the same
# config the units come from.
FUEL_PRICE = 1.62


def price():
    try:
        import json
        with open(records.CONFIG) as f:
            return float((json.load(f) or {}).get("fuel_price") or FUEL_PRICE)
    except (OSError, ValueError, TypeError):
        return FUEL_PRICE


def rollup(rows):
    """One day of samples reduced to the row the `days` table holds."""
    km = litres = moving_s = engine_s = idle_s = 0.0
    top_kph = 0.0
    prev_t = None
    trips = 0
    gap_open = True
    for (t, speed, maf) in rows:
        dt = 1.0 if prev_t is None else t - prev_t
        if dt > MAX_STEP:
            # A gap is the daemon having been away. It also ends a trip.
            dt = 1.0
            gap_open = True
        if gap_open and (speed or 0) > MOVING_KPH:
            trips += 1
            gap_open = False
        prev_t = t
        engine_s += dt
        if speed and speed > MOVING_KPH:
            km += speed * dt / 3600.0
            moving_s += dt
            top_kph = max(top_kph, speed)
        else:
            idle_s += dt
        if maf and maf > 0:
            litres += (maf / AFR) * dt / DENSITY
    return {
        "km": round(km, 2), "litres": round(litres, 3),
        # Fuel over distance for the whole day, never the mean of the
        # per-second figures — the same rule the live path uses.
        "lphk": round(litres / km * 100.0, 2) if km > 0.5 else None,
        "moving_s": int(moving_s), "engine_s": int(engine_s),
        "idle_s": int(idle_s), "top_kph": round(top_kph, 1),
        "trips": trips,
    }


def compact(keep_days=KEEP_DAYS, dry=False, verbose=True):
    """Roll samples older than the window into `days`, then drop them."""
    if not os.path.exists(records.DB):
        return {"rolled": 0, "deleted": 0, "days": 0}
    cutoff = time.time() - keep_days * 86400
    db = sqlite3.connect(records.DB, timeout=10.0)
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS days (
            day TEXT PRIMARY KEY, km REAL, litres REAL, lphk REAL,
            moving_s INTEGER, engine_s INTEGER, idle_s INTEGER,
            top_kph REAL, trips INTEGER, cost REAL, odo REAL)""")

        old = db.execute(
            "SELECT t, speed, maf FROM samples WHERE t < ? ORDER BY t ASC",
            (cutoff,)).fetchall()
        if not old:
            return {"rolled": 0, "deleted": 0, "days": 0}

        by_day = {}
        for row in old:
            key = datetime.fromtimestamp(row[0]).strftime("%Y-%m-%d")
            by_day.setdefault(key, []).append(row)

        p = price()
        rolled = 0
        for day, rows in sorted(by_day.items()):
            r = rollup(rows)
            existing = db.execute(
                "SELECT km, litres FROM days WHERE day = ?", (day,)).fetchone()
            # A day may already have a rollup — the seeder writes them, and a
            # partial day can be compacted twice. Take whichever figure is
            # larger rather than adding, so re-running is safe.
            if existing and (existing[0] or 0) >= r["km"]:
                continue
            if dry:
                rolled += 1
                continue
            db.execute(
                "INSERT INTO days (day, km, litres, lphk, moving_s, engine_s, "
                "idle_s, top_kph, trips, cost) VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(day) DO UPDATE SET km=excluded.km, "
                "litres=excluded.litres, lphk=excluded.lphk, "
                "moving_s=excluded.moving_s, engine_s=excluded.engine_s, "
                "idle_s=excluded.idle_s, top_kph=excluded.top_kph, "
                "trips=excluded.trips, cost=excluded.cost",
                (day, r["km"], r["litres"], r["lphk"], r["moving_s"],
                 r["engine_s"], r["idle_s"], r["top_kph"], r["trips"],
                 round(r["litres"] * p, 2)))
            rolled += 1

        deleted = 0
        if not dry:
            cur = db.execute("DELETE FROM samples WHERE t < ?", (cutoff,))
            deleted = cur.rowcount
            db.commit()
            # SQLite does not hand the space back on its own, and the whole
            # point of this is the size of the file.
            db.execute("VACUUM")
        out = {"rolled": rolled, "deleted": deleted, "days": len(by_day),
               "cutoff": cutoff}
    finally:
        db.close()
    if verbose:
        print(f"  rolled {out['rolled']} day(s), dropped {out['deleted']:,} "
              f"raw sample(s) older than {keep_days} days")
    return out


def size():
    try:
        return os.path.getsize(records.DB)
    except OSError:
        return 0


def main(argv):
    dry = "--dry-run" in argv
    keep = KEEP_DAYS
    for a in argv:
        if a.startswith("--keep="):
            try:
                keep = max(2, int(a.split("=", 1)[1]))
            except ValueError:
                pass
    before = size()
    out = compact(keep_days=keep, dry=dry)
    after = size()
    if not dry and before:
        print(f"  {before / 1e6:.1f} MB → {after / 1e6:.1f} MB")
    if dry:
        print("  (dry run — nothing was written)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
