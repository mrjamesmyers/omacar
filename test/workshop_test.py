#!/usr/bin/env python3
"""The workshop's load-bearing logic, tested without a car or an adapter.

Four things here are worth a test because getting them wrong would be quiet
rather than loud: the unit conversions (a reciprocal that looks like a scale),
the service countdown (two intervals racing), the Mode 06 verdict (a value
between a floor and a ceiling), and the advisor's evidence check (the only
thing standing between a language model and a confident invention).
"""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import ai            # noqa: E402
import records       # noqa: E402
import api           # noqa: E402

PASS, FAIL = [], []


def ok(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"   {'ok ' if cond else 'FAIL'}  {name}")


def head(name):
    print(f"\n  {name}\n")


def _raises(fn):
    try:
        fn()
    except Exception:
        return True
    return False


# ---- units ------------------------------------------------------------------
head("Units")

imp = records.UNITS["imperial"]
met = records.UNITS["metric"]

ok("a kilometre is 0.621 miles", abs(records.to_dist(100, imp) - 62.1371) < 0.01)
ok("metric leaves distance alone", records.to_dist(100, met) == 100)
ok("a litre is 0.264 gallons", abs(records.to_vol(10, imp) - 2.6417) < 0.001)

# The trap: economy is a reciprocal. 235.2 / L/100km = mpg, so a LOWER
# consumption is a HIGHER mpg, and anything treating it as a scale factor
# silently reports a thrifty car as a thirsty one.
ok("6.5 L/100km is 36.2 mpg", abs(records.to_econ(6.5, imp) - 36.187) < 0.01)
ok("a thriftier car scores higher in mpg",
   records.to_econ(5.0, imp) > records.to_econ(8.0, imp))
ok("a thriftier car scores lower in L/100km",
   records.to_econ(5.0, met) < records.to_econ(8.0, met))
ok("no consumption is not infinite economy", records.to_econ(0, imp) is None)
ok("missing consumption stays missing", records.to_econ(None, imp) is None)
ok("32 F is 0 C", abs(records.to_temp(0, imp) - 32.0) < 0.001)


# ---- the service countdown --------------------------------------------------
head("Service countdown")

import sqlite3      # noqa: E402
import tempfile     # noqa: E402
import time         # noqa: E402

tmp = tempfile.mkdtemp()
dbpath = os.path.join(tmp, "t.db")
db = sqlite3.connect(dbpath)
db.execute("""CREATE TABLE service (item TEXT PRIMARY KEY, code TEXT,
    last_km REAL, last_at REAL, interval_km REAL, interval_days REAL, note TEXT)""")
now = time.time()
db.executemany("INSERT INTO service VALUES (?,?,?,?,?,?,?)", [
    # Half its mileage gone, a tenth of its time: mileage decides.
    ("Oil", "A", 1000.0, now - 36.5 * 86400, 1000.0, 365, ""),
    # No mileage interval at all — time is the only thing that can decide.
    ("Brake fluid", "7", 1000.0, now - 1095 * 86400, 0.0, 1095, ""),
    # Past due on distance.
    ("Plugs", "4", 1000.0, now - 10 * 86400, 100.0, 3650, ""),
])
db.commit()
db.close()

records_db = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True)
records_db.row_factory = sqlite3.Row
svc = records.service(records_db, odometer=1500.0)
by = {s["item"]: s for s in svc["items"]}
records_db.close()

ok("whichever interval is further along decides", by["Oil"]["by"] == "distance")
ok("half the mileage gone is half the life left", by["Oil"]["life"] == 50)
ok("a time-only item is scored on time", by["Brake fluid"]["by"] == "time")
ok("a time-only item at its interval is due", by["Brake fluid"]["life"] <= 0)
ok("past due reads as overdue", by["Plugs"]["state"] == "overdue")
ok("overdue distance is reported negative", by["Plugs"]["km_left"] < 0)
ok("the nearest item is the next one", svc["next"]["item"] in ("Plugs", "Brake fluid"))
ok("oil gets a short name for the pill", records.short_name("Engine oil & filter") == "OIL")
# The one the naive "first word" version got wrong: two items starting "Engine".
ok("coolant is not called ENGINE", records.short_name("Engine coolant") == "COOLANT")


# ---- Mode 06 ----------------------------------------------------------------
head("Mode 06 verdicts")


def m6(value, lo=None, hi=None):
    dbp = os.path.join(tmp, "m6.db")
    d = sqlite3.connect(dbp)
    d.execute("""CREATE TABLE mode06 (mid TEXT PRIMARY KEY, name TEXT,
        component TEXT, value REAL, lo REAL, hi REAL, unit TEXT, note TEXT, pos INTEGER)""")
    d.execute("INSERT INTO mode06 VALUES ('0x01','t','c',?,?,?,'u','',0)", (value, lo, hi))
    d.commit()
    d.close()
    ro = sqlite3.connect(f"file:{dbp}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    out = records.mode06(ro)[0]
    ro.close()
    os.remove(dbp)
    return out


ok("under the ceiling passes", m6(0.5, hi=1.0)["pass"] is True)
ok("over the ceiling fails", m6(1.5, hi=1.0)["pass"] is False)
ok("under the floor fails", m6(0.5, lo=1.0)["pass"] is False)
# The number that makes Mode 06 a prediction rather than a pass/fail list.
ok("a test at 95% of its limit reports it",
   abs(m6(0.95, hi=1.0)["headroom"] - 0.95) < 1e-9)


# ---- the DTC decoder --------------------------------------------------------
head("Trouble code decoding")

# The decoder is what makes the tool useful on a car it has never met, so it
# has to be right about the structure even when the library has no entry.
kb = json.load(open(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "share", "data", "dtc.json")))
ok("the library carries the codes the simulator sets",
   all(c in kb for c in ("P0135", "P1449", "P0420", "P0301", "B1225", "C1B00")))
ok("every entry ranks its causes",
   all("causes" in v for k, v in kb.items() if not k.startswith("_")))
ok("cause shares are plausible percentages",
   all(0 < c["share"] <= 100
       for k, v in kb.items() if not k.startswith("_")
       for c in v.get("causes", [])))
ok("smart data points at real channels or Mode 06 tests",
   all(s["pid"].startswith("MODE06:") or s["pid"].isupper()
       for k, v in kb.items() if not k.startswith("_")
       for s in v.get("smart", [])))


# ---- the advisor's guard rails ---------------------------------------------
head("Advisor grounding")

ok("plain JSON parses", ai.extract_json('{"a":1}') == {"a": 1})
ok("a fenced reply parses", ai.extract_json('```json\n{"a":2}\n```') == {"a": 2})
ok("JSON with prose around it parses",
   ai.extract_json('Here you go:\n{"a":3}\nhope that helps') == {"a": 3})
ok("a brace inside a string does not end the object",
   ai.extract_json('{"a":"} not the end","b":4}')["b"] == 4)
ok("nonsense returns nothing", ai.extract_json("no json here") is None)

bundle = {"faults": {"P0135": {}}, "mode06": {"0x39": {}}, "vehicle": {}}
keys = ai.evidence_keys(bundle)
ok("bundle keys are citable at one level in", "faults.P0135" in keys and "mode06.0x39" in keys)

reply = {"findings": [
    {"title": "real", "evidence": ["faults.P0135"]},
    {"title": "invented", "evidence": ["faults.P9999"]},
    {"title": "half right", "evidence": ["faults.P0135", "mode06.0xZZ"]},
]}
out, dropped = ai.validate("triage", reply, bundle)
titles = [f["title"] for f in out["findings"]]
ok("a finding citing real evidence survives", "real" in titles)
# The load-bearing one: a finding about a car we do not have never reaches the
# screen, and Python decides that rather than a polite request to the model.
ok("a finding citing evidence that does not exist is dropped", "invented" not in titles)
ok("the drop is reported rather than silent", len(dropped) == 1)
ok("a partly-valid citation is kept and trimmed",
   "half right" in titles
   and out["findings"][-1]["evidence"] == ["faults.P0135"])


# ---- bidirectional ----------------------------------------------------------
head("Functional tests")

import sim   # noqa: E402
import random as _random  # noqa: E402

r = _random.Random(1)


def kill(cyl, rpm=780.0):
    v = {"RPM": rpm, "ENGINE_LOAD": 18.0, "SHORT_FUEL_TRIM_1": 0.0}
    out, _ = sim.apply_actuator({"test": f"injector_kill_{cyl}"}, v, 88.0, r)
    return rpm - out["RPM"]


drops = {c: kill(c) for c in (1, 2, 3, 4)}
ok("silencing a cylinder drops the idle", all(d > 60 for d in drops.values()))
# The whole point of a balance test: the weak cylinder drops the idle less,
# because it was already contributing less.
ok("the weak cylinder drops it least", min(drops, key=drops.get) == 1)
ok("the weak cylinder is clearly below the others",
   drops[1] / max(drops.values()) < 0.8)

fan = sim.apply_actuator({"test": "fan_high"}, {"RPM": 780.0, "ENGINE_LOAD": 18.0,
                                                "SHORT_FUEL_TRIM_1": 0.0}, 88.0, r)[1]
ok("the cooling fan pulls the coolant target down", fan < 0)
ok("a commanded fan actually cools", sim.warm(95.0, 20.0, 10.0, 1.0, bias=fan) < 95.0)
ok("coolant never falls below ambient", sim.warm(21.0, 20.0, 0.0, 600.0, bias=-40.0) >= 20.0)

purge = sim.apply_actuator({"test": "evap_purge"}, {"RPM": 780.0, "ENGINE_LOAD": 18.0,
                                                    "SHORT_FUEL_TRIM_1": 0.0}, 88.0, r)[0]
ok("opening the purge valve pushes trim negative", purge["SHORT_FUEL_TRIM_1"] < -5)

ok("an unknown test is refused",
   _raises(lambda: api.actuate("launch_control")))
cmd = api.actuate("fan_high", 9999)
ok("durations are capped in the server, not trusted to the caller",
   cmd["duration"] == api.LIMITS["fan_high"]["max"])
ok("a command carries its own expiry", cmd["at"] + cmd["duration"] > time.time())
ok("a test needing a running engine says so", api.LIMITS["injector_kill_1"]["idle"] is True)
api.actuate(None, stop=True)


# ---- the watchdog -----------------------------------------------------------
head("Watchdog rules")

import watch  # noqa: E402


def sample(**kw):
    v = {"COOLANT_TEMP": 90, "RPM": 2000, "SPEED": 60,
         "CONTROL_MODULE_VOLTAGE": 14.2, "FUEL_LEVEL": 60,
         "LONG_FUEL_TRIM_1": 2.0}
    v.update(kw)
    return {"connected": True, "values": v}


def run_watch(samples, seconds=2.0):
    got = []
    w = watch.Watch(quiet=True, persist=False, watch_faults=False, sink=got)
    t = 1000.0
    for s_ in samples:
        w.tick(s_, t)
        t += seconds
    return got, w


hot = [sample(COOLANT_TEMP=107)] * 2
ok("a brief excursion is not an alert", not run_watch(hot)[0])

got, _ = run_watch([sample(COOLANT_TEMP=107)] * 6)
ok("a sustained one is", [a["title"] for a in got] == ["Engine running hot"])

# The whole reason for hysteresis: a value parked on a limit must not produce
# a notification every two seconds for the rest of the drive.
got, _ = run_watch([sample(COOLANT_TEMP=107)] * 60)
ok("it fires once, not once per sample",
   sum(1 for a in got if a["title"] == "Engine running hot") == 1)

# Two rules watch coolant at two levels; the quieter one must stand down.
ok("the louder rule suppresses the quieter one about the same value",
   not any(a["title"] == "Coolant above normal" for a in got))

got, _ = run_watch([sample(COOLANT_TEMP=101)] * 20)
ok("the quieter rule fires on its own",
   any(a["title"] == "Coolant above normal" for a in got))

got, _ = run_watch([sample(COOLANT_TEMP=107)] * 6
                   + [sample(COOLANT_TEMP=94)] * 3
                   + [sample(COOLANT_TEMP=107)] * 6)
ok("it re-arms only after the value comes properly back down",
   sum(1 for a in got if a["title"] == "Engine running hot") == 2)

got, _ = run_watch([sample(RPM=0, SPEED=0, CONTROL_MODULE_VOLTAGE=12.3)] * 60)
ok("a parked car is silent", not got)

got, _ = run_watch([sample(CONTROL_MODULE_VOLTAGE=12.1)] * 30)
ok("a running car that stopped charging is not",
   any(a["title"] == "Not charging" for a in got))

got, _ = run_watch([sample(FUEL_LEVEL=8)] * 30)
ok("low fuel is worth one quiet word", any(a["title"] == "Fuel low" for a in got))

# A trip: moving, then stopped for longer than the gap.
drive = [sample(SPEED=90)] * 60
after = [sample(SPEED=0, RPM=0)] * 120
got, _ = run_watch(drive + after)
trip = [a for a in got if a["title"] == "Trip finished"]
ok("a finished trip is summarised", len(trip) == 1)
ok("the summary carries the distance",
   trip and trip[0]["extra"]["km"] > 2)

# A car that never got out of the car park must not produce a trip.
got, _ = run_watch([sample(SPEED=4)] * 3 + [sample(SPEED=0, RPM=0)] * 120)
ok("a shuffle in the car park is not a trip",
   not any(a["title"] == "Trip finished" for a in got))

# Swapping cars — or switching between the simulator and a real adapter —
# replaces the fault list wholesale. Announcing that as a repair is a lie.
wv = watch.Watch(quiet=True, persist=False, watch_faults=False, sink=[])
wv.known_vin, wv.known_codes = "VIN-A", {"P0135", "P1449"}
seen = []
wv.sink = seen


class FakeDb:
    def close(self):
        pass


def with_car(vin, codes):
    real_connect, real_faults, real_vehicle = (
        records.connect, records.faults, records.vehicle)
    records.connect = lambda: FakeDb()
    records.faults = lambda db: [{"code": c, "active": True, "severity": "warning",
                                  "descr": c, "module": None} for c in codes]
    records.vehicle = lambda db: {"vin": vin}
    try:
        wv.faults(1000.0)
    finally:
        records.connect, records.faults, records.vehicle = (
            real_connect, real_faults, real_vehicle)


with_car("VIN-B", ["P0420"])
ok("a different car's codes are adopted silently", not seen)
ok("and become the new baseline", wv.known_codes == {"P0420"})
with_car("VIN-B", ["P0420", "P0301"])
ok("a genuinely new code on the same car IS announced",
   any("P0301" in a["title"] for a in seen))

ok("every rule has both an arming and a re-arming level",
   all(r.get("on") and r.get("off") for r in watch.RULES))
ok("no rule fires on a single sample except the one that should",
   all(r.get("hold", 0) >= 1 for r in watch.RULES))


# ---- compaction -------------------------------------------------------------
head("Compaction")

import prune  # noqa: E402

ptmp = tempfile.mkdtemp()
real_db = records.DB
records.DB = prune.records.DB = os.path.join(ptmp, "p.db")
pdb = sqlite3.connect(records.DB)
pdb.execute("""CREATE TABLE samples (t REAL PRIMARY KEY, rpm REAL, speed REAL,
    load REAL, throttle REAL, coolant REAL, intake REAL, maf REAL, stft REAL,
    ltft REAL, timing REAL, lphk REAL, eff REAL)""")
# An hour at a steady 100 km/h burning a steady 8 g/s, ninety days ago, plus a
# recent hour that must survive.
old_t = time.time() - 90 * 86400
new_t = time.time() - 3600
pdb.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(old_t + i, 2200, 100.0, 40, 25, 90, 30, 8.0, 0, 5, 14, None, .6)
                 for i in range(3600)])
pdb.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(new_t + i, 2200, 100.0, 40, 25, 90, 30, 8.0, 0, 5, 14, None, .6)
                 for i in range(1800)])
pdb.commit()
pdb.close()

dry = prune.compact(keep_days=45, dry=True, verbose=False)
kept_before = sqlite3.connect(records.DB).execute(
    "SELECT count(*) FROM samples").fetchone()[0]
ok("a dry run changes nothing", kept_before == 5400 and dry["deleted"] == 0)

out = prune.compact(keep_days=45, verbose=False)
pdb = sqlite3.connect(records.DB)
kept = pdb.execute("SELECT count(*) FROM samples").fetchone()[0]
tot = pdb.execute("SELECT sum(km), sum(litres), sum(trips) FROM days").fetchone()
pdb.close()

ok("old raw samples are dropped", out["deleted"] == 3600)
ok("recent raw samples survive", kept == 1800)
# 100 km/h for an hour is 100 km; 8 g/s over 3600 s at 14.7:1 and 745 g/L is
# 2.63 L. The rollup must reproduce both, and it must do it across the midnight
# boundary the span happens to straddle.
ok("the distance survives compaction", abs(tot[0] - 100.0) < 0.2)
ok("the fuel survives compaction", abs(tot[1] - 2.63) < 0.02)
ok("economy is recoverable from the rollup",
   abs((tot[1] / tot[0] * 100) - 2.63) < 0.05)
ok("a drive is counted once even split across two days", tot[2] in (1, 2))

again = prune.compact(keep_days=45, verbose=False)
ok("compacting twice is safe", again["deleted"] == 0)

records.DB = prune.records.DB = real_db
shutil.rmtree(ptmp, ignore_errors=True)


# ---- theme ------------------------------------------------------------------
head("Theme")

import theme as theme_mod  # noqa: E402

THEMES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "..", "..", ".config", "omarchy", "themes")
dark = theme_mod.palette(os.path.expanduser(
    "~/.config/omarchy/themes/liquid-glass/colors.toml"))
lightp = theme_mod.palette(os.path.expanduser(
    "~/.config/omarchy/themes/liquid-glass-light/colors.toml"))

ok("a dark theme comes out dark", dark["mode"] == "dark")
ok("a light theme comes out light", lightp["mode"] == "light")
ok("ink is legible on the panel, both ways",
   theme_mod.contrast(dark["ink"], dark["panel"]) > 7
   and theme_mod.contrast(lightp["ink"], lightp["panel"]) > 7)
# The one that breaks silently: a theme's yellow is chosen for a terminal, not
# for a panel, and an unreadable warning colour is worse than no colour.
for name, p in (("dark", dark), ("light", lightp)):
    for role in ("ok", "warn", "bad", "info", "ai"):
        ok(f"{role} is readable on the {name} panel",
           theme_mod.contrast(p[role], p["panel"]) >= 3.3)
ok("badge text contrasts with its own badge",
   all(theme_mod.contrast(p[r], p["on-" + r]) >= 3.5
       for p in (dark, lightp) for r in ("ok", "warn", "bad", "info", "ai")))
ok("a missing theme falls back rather than failing",
   theme_mod.palette("/nonexistent/colors.toml")["mode"] == "dark")


# ---- the vehicle book -------------------------------------------------------
head("Odometer and service book")

import book  # noqa: E402

btmp = tempfile.mkdtemp()
book_real = records.DB
records.DB = book.records.DB = os.path.join(btmp, "b.db")
bdb = sqlite3.connect(records.DB)
bdb.execute("""CREATE TABLE samples (t REAL PRIMARY KEY, rpm REAL, speed REAL,
    load REAL, throttle REAL, coolant REAL, intake REAL, maf REAL, stft REAL,
    ltft REAL, timing REAL, lphk REAL, eff REAL)""")
# Fifteen minutes at exactly 96.6 km/h — sixty miles an hour.
drive_t0 = time.time() - 900
bdb.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(drive_t0 + i, 2100, 96.6, 35, 22, 88, 28, 7.5, 0, 4, 14, None, .6)
                 for i in range(900)])
bdb.commit()
bdb.close()

ok("with nothing set there is no odometer", book.odometer()[0] is None)

# The reading is taken before the drive, so the drive counts.
book.set_odometer(100000.0, when=time.time() - 1800)
km, at, driven = book.odometer()
# OBD-II has no odometer PID; this is speed integrated, so it has to be right.
ok("the odometer advances by what was driven", abs(driven - 24.15) < 0.4)
ok("...on top of the reading you gave it", abs(km - 100024.15) < 0.4)

# And a reading taken after the drive must not count it twice.
book.set_odometer(100050.0, when=time.time())
ok("a fresh reading resets what counts as since",
   abs(book.odometer()[0] - 100050.0) < 0.2)

bdb = sqlite3.connect(records.DB)
bdb.row_factory = sqlite3.Row
n = book.ensure_schedule(bdb)
bdb.commit()
ok("a car with no book gets a starter schedule", n == len(book.STARTER))
svc = records.service(bdb, book.odometer()[0])
# Everything starts overdue on purpose: eleven green ticks on a car nobody has
# told us anything about would be a lie.
ok("and everything in it starts due", all(i["state"] == "overdue" for i in svc["items"]))
bdb.close()

ok("logging by a partial name finds the item",
   book.log_service("oil") == "Engine oil & filter")
ok("an unknown item is refused rather than invented",
   book.log_service("flux capacitor") is None)

bdb = sqlite3.connect(records.DB)
bdb.row_factory = sqlite3.Row
svc = records.service(bdb, book.odometer()[0])
oil = next(i for i in svc["items"] if i["item"].startswith("Engine oil"))
ok("a logged item is no longer due", oil["state"] == "ok" and oil["life"] > 95)
ok("the rest still are", sum(1 for i in svc["items"] if i["state"] == "overdue")
   == len(book.STARTER) - 1)
bdb.close()

book.add_item("Timing belt", interval_km=160000, interval_days=3650)
bdb = sqlite3.connect(records.DB)
bdb.row_factory = sqlite3.Row
items = [i["item"] for i in records.service(bdb, 100050.0)["items"]]
bdb.close()
ok("an item can be added", "Timing belt" in items)
ok("and removed", book.forget_item("Timing belt") == 1)

records.DB = book.records.DB = book_real
shutil.rmtree(btmp, ignore_errors=True)


# ---- cockpit and the drive layout -------------------------------------------
head("Cockpit and drive layout")

import serve  # noqa: E402


class FakeHandler(serve.Handler):
    """Just enough of a request to exercise the two gates."""

    def __init__(self, path="/api/live", headers=None):
        self.path = path
        self.headers = headers or {}


def gate(token, path="/api/live", header=None):
    serve.TOKEN = token
    h_ = FakeHandler(path, {"Authorization": header} if header else {})
    return FakeHandler._authorised(h_)


ok("with no token configured everything is allowed", gate("", "/api/live"))
serve.TOKEN = "s3cret"
ok("a request with no token is refused", not gate("s3cret", "/api/live"))
ok("a request with the wrong token is refused", not gate("s3cret", "/api/live?k=nope"))
ok("a request with the right token is allowed", gate("s3cret", "/api/live?k=s3cret"))
ok("the bearer header works too",
   gate("s3cret", "/api/live", header="Bearer s3cret"))
ok("a near-miss token is refused",
   not gate("s3cret", "/api/live", header="Bearer s3cre"))
serve.TOKEN = ""

serve.ALLOW_CONTROL = False
h = FakeHandler()
# The point of a cockpit: it can show you the car, and it cannot touch it.
ok("a read-only display cannot clear codes", not FakeHandler._may_write(h, "/api/clear"))
ok("a read-only display cannot command an actuator",
   not FakeHandler._may_write(h, "/api/actuate"))
ok("a read-only display cannot spend the AI budget",
   not FakeHandler._may_write(h, "/api/ai"))
ok("a read-only display may still switch units",
   FakeHandler._may_write(h, "/api/units"))
serve.ALLOW_CONTROL = True
ok("with control it may do all of it", FakeHandler._may_write(h, "/api/clear"))

args = serve.parse_args(["7570", "share", "--host", "0.0.0.0", "--token", "t"])
ok("binding to the network defaults to read-only", args[4] is False)
args = serve.parse_args(["7599", "share"])
ok("loopback keeps every power it had", args[4] is True)
args = serve.parse_args(["7570", "share", "--host", "0.0.0.0", "--token", "t", "--control"])
ok("control is opt-in and explicit", args[4] is True)

# The layout is bounded here rather than trusted to whatever wrote the file:
# forty tiles is not a layout and none is a blank screen in a moving car.
saved = api.save_drive_layout({"tiles": ["a"] * 40, "columns": 99, "hero": "rpm"})
ok("the tile count is capped", len(saved["tiles"]) == 8)
ok("the column count is capped", saved["columns"] == 4)
ok("the hero is kept", saved["hero"] == "rpm")
ok("auto drive defaults to switching on connect",
   api.DEFAULT_DRIVE["auto"] == "connect")
saved = api.save_drive_layout({"auto": "moving"})
ok("auto drive can wait for the car to move", saved["auto"] == "moving")
saved = api.save_drive_layout({"auto": "nonsense"})
ok("an unknown auto mode is ignored rather than stored", saved["auto"] == "moving")
saved = api.save_drive_layout({"auto": "off", "auto_return": False})
ok("auto drive can be switched off", saved["auto"] == "off")
ok("returning to the workshop is separately controllable",
   saved["auto_return"] is False)
saved = api.save_drive_layout({"tiles": []})
ok("an empty layout falls back to the default",
   saved["tiles"] == api.DEFAULT_DRIVE["tiles"])
api.save_drive_layout(dict(api.DEFAULT_DRIVE))


# ---- the API surface --------------------------------------------------------
head("API")

ok("unknown endpoints are not ours", api.handle_get("/api/nope", "") is None)
ok("history accepts a span", api.handle_get("/api/history", "mins=5&n=10")[0] == 200)
ok("a query integer is clamped", api.qint("n=99999", "n", 10, 1, 100) == 100)
ok("a missing query integer falls back", api.qint("", "n", 7) == 7)
ok("a query string is decoded", api.qstr("q=hello+world", "q") == "hello world")
ok("units can only be one of two things",
   api.handle_post("/api/units", '{"system":"furlongs"}')[0] == 400)
ok("the advisor knows the new question kinds",
   {"symptom", "recording"} <= set(ai.SCHEMAS) == set(ai.PROMPTS))

shutil.rmtree(tmp, ignore_errors=True)

print(f"\n  {len(PASS)} passed, {len(FAIL)} failed\n")
sys.exit(1 if FAIL else 0)
