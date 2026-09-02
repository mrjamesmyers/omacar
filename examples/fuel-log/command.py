#!/usr/bin/env python3
"""An example OmaCar plugin: a fuel log.

Shows the three things a plugin gets for free:

  * OMACAR_DB points at THIS vehicle's database, so a plugin does not have to
    know where OmaCar keeps things or which car is current.
  * OMACAR_LIB is on PYTHONPATH, so `import records` and the rest work.
  * Its own tables live in the same per-VIN database, so they follow the car.
"""
import os, sqlite3, sys, time

DB = os.environ["OMACAR_DB"]

def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS fuel_log (
        id INTEGER PRIMARY KEY, at REAL, litres REAL, cost REAL, odo REAL)""")
    return c

def add(litres, cost, odo):
    c = db()
    c.execute("INSERT INTO fuel_log (at,litres,cost,odo) VALUES (?,?,?,?)",
              (time.time(), float(litres), float(cost), float(odo)))
    c.commit()
    print(f"  logged {litres} L for {cost} at {odo}")

def show():
    c = db()
    rows = list(c.execute("SELECT at,litres,cost,odo FROM fuel_log ORDER BY odo"))
    if not rows:
        print("  no fill-ups yet:  omacar fuel add <litres> <cost> <odometer>")
        return
    print(f"\n  {len(rows)} fill-up(s)")
    for i in range(1, len(rows)):
        d = rows[i][3] - rows[i-1][3]
        if d > 0:
            print(f"    {d:7.1f} mi on {rows[i][1]:5.1f} L "
                  f"= {d / (rows[i][1] * 0.264172):5.1f} mpg")

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "add" and len(a) == 4: add(a[1], a[2], a[3])
    else: show()
