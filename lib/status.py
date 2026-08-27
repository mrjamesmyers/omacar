"""`omacar status` — is the whole thing working, in one screen.

`omacar doctor` answers "what is the adapter talking to", which needs the venv
and a serial connection. This answers the different question you actually ask
at a terminal: is anything watching my car, when did it last hear from it, and
is there something I should know. Pure standard library, so it works before
`omacar setup` has ever been run.
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import records  # noqa: E402
import watch    # noqa: E402

try:
    import ai
except Exception:                                        # noqa: BLE001
    ai = None

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, AMBER, RED = "\033[32m", "\033[33m", "\033[31m"


def mark(ok):
    return f"{GREEN}  ok  {RESET}" if ok is True else (
        f"{AMBER} warn {RESET}" if ok is None else f"{RED} FAIL {RESET}")


def unit_active(name):
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", "--quiet", name],
                           timeout=4)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pid_alive(path):
    try:
        with open(path) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def line(state, label, detail=""):
    print(f" {mark(state)} {label:<26}{DIM}{detail}{RESET}")


def main():
    snap = records.live()
    db = records.connect()
    u = records.units_for()
    now = time.time()

    print(f"\n{BOLD}  The car{RESET}\n")
    v = records.vehicle(db)
    if v:
        odo = v.get("odometer_km")
        line(True, v.get("name", "unknown"),
             (f"{records.to_dist(odo, u):,.0f} {u['dist']}   " if odo else "")
             + (v.get("vin") or ""))
        if v.get("simulated"):
            line(None, "simulated", "not a real adapter — omacar sim stop to use the car")
    else:
        line(False, "no vehicle record", "run: omacar sim seed, or plug in an adapter")

    connected = bool(snap.get("connected"))
    age = now - (snap.get("t") or 0) if snap.get("t") else None
    line(connected, "link",
         (f"{snap.get('kind', 'adapter')} on {snap.get('port', '?')}"
          if connected else snap.get("status", "nothing answering")))
    line(age is not None and age < 30, "last sample",
         f"{age:.0f}s ago" if age is not None else "never")
    line(True, "state", records.status(snap))

    print(f"\n{BOLD}  What is running{RESET}\n")
    sim = unit_active("omacar-sim.service") or pid_alive(
        os.path.join(records.STATE, "sim.pid"))
    watching = unit_active("omacar-watch.service") or pid_alive(watch.PIDFILE)
    daemon = pid_alive(os.path.join(records.STATE, "daemon.pid"))
    line(bool(daemon or sim), "sample source",
         "real daemon" if daemon else "simulator" if sim else
         "nothing — omacar daemon start, or omacar sim start")
    # The one that matters for leaving an adapter in the car.
    line(bool(watching), "watchdog",
         "watching" if watching else "not running — omacar watch start")
    line(True, "advisor", "ready" if (ai and ai.available())
         else "the `claude` CLI is not installed (everything else works)")

    print(f"\n{BOLD}  What it knows{RESET}\n")
    faults = [f for f in records.faults(db) if f["active"]] if db else []
    # A stored code is a finding, not a broken tool. FAIL is reserved for
    # things that stop OmaCar doing its job — an alerter that cries failure
    # over the car's own news is one nobody reads twice.
    line(True if not faults else None, "trouble codes",
         "none stored" if not faults
         else ", ".join(f["code"] for f in faults[:6]))
    r = records.readiness(db) if db else {"ready": None, "incomplete": 0}
    line(True if r.get("ready") else None, "emissions readiness",
         "ready" if r.get("ready") else f"{r.get('incomplete', 0)} monitor(s) incomplete")
    svc = records.service(db, v.get("odometer_km")) if db else None
    if svc:
        nxt = svc["next"]
        line(True if nxt["life"] > 15 else None, "next service",
             f"{nxt['item']}  {max(0, nxt['life'])}%"
             + (f"  ·  {records.to_dist(nxt['km_left'], u):,.0f} {u['dist']}"
                if nxt.get("km_left") is not None else ""))

    alerts = watch.alerts(40)
    day = [a for a in alerts if now - a["at"] < 86400]
    crit = [a for a in day if (a.get("payload") or {}).get("urgency") == "critical"]
    line(False if crit else (True if not day else None), "alerts today",
         "none" if not day else f"{len(day)} ({len(crit)} critical)")
    for a in day[:3]:
        p = a.get("payload") or {}
        print(f"        {DIM}{time.strftime('%H:%M', time.localtime(a['at']))}  "
              f"{p.get('title', '')} — {p.get('body', '')}{RESET}")

    perf = records.performance(records.days(db)) if db else None
    if perf and perf.get("year"):
        y = perf["year"]
        econ = records.to_econ(y.get("lphk"), u)
        line(True, "this year",
             f"{records.to_dist(y['km'], u):,.0f} {u['dist']}"
             + (f"   ·   {econ:.1f} {u['econ']}" if econ else ""))

    if db:
        db.close()
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
