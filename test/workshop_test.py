#!/usr/bin/env python3
"""The workshop's load-bearing logic, tested without a car or an adapter.

Four things here are worth a test because getting them wrong would be quiet
rather than loud: the unit conversions (a reciprocal that looks like a scale),
the service countdown (two intervals racing), the Mode 06 verdict (a value
between a floor and a ceiling), and the advisor's evidence check (the only
thing standing between a language model and a confident invention).
"""

import json
import re
import pathlib
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

# Themes live in the user's config when they have been customised and in
# Omarchy's share directory otherwise. This used to name two liquid-glass paths
# under ~/.config only; neither is installed here, so BOTH reads fell through to
# FALLBACK -- which is dark. "a dark theme comes out dark" passed by accident
# and "a light theme comes out light" could never pass at all. A test that
# cannot pass teaches nothing, so find a real theme of each kind or say why not.
THEME_DIRS = [os.path.expanduser("~/.config/omarchy/themes"),
              "/usr/share/omarchy/themes"]


def find_theme(want_mode):
    """A real installed theme of the given mode, or None."""
    for d in THEME_DIRS:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            path = os.path.join(d, n, "colors.toml")
            if not os.path.exists(path):
                continue
            raw = theme_mod.read(path)
            if not raw:
                continue
            if (raw.get("mode") or "dark").lower() == want_mode:
                return path
    return None


dark_path = find_theme("dark")
light_path = find_theme("light")

if not (dark_path and light_path):
    print("   --    need one dark and one light theme installed; skipped")
else:
    dark = theme_mod.palette(dark_path)
    lightp = theme_mod.palette(light_path)

    ok("a dark theme comes out dark", dark["mode"] == "dark")
    ok("a light theme comes out light", lightp["mode"] == "light")

    # The in-car ink. The hub, its tiles and the radio transport are painted
    # entirely in these two, and they were the only tokens app.css defined that
    # palette() did not emit -- so the whole driving screen stayed hardcoded
    # white whatever the desktop was wearing.
    ok("the theme supplies the in-car ink the hub is painted in",
       "bright" in dark and "bright-2" in dark)
    ok("in-car ink inverts on a light theme",
       theme_mod.luminance(lightp["bright"]) < theme_mod.luminance(lightp["panel"]))
    # And they have to stay two weights, not two names for the same white.
    for name, p in (("dark", dark), ("light", lightp)):
        ok(f"bright and bright-2 are a real step apart on the {name} theme",
           theme_mod.contrast(p["bright"], p["panel"])
           > theme_mod.contrast(p["bright-2"], p["panel"]) * 1.3)
        ok(f"in-car ink clears the glare floor on the {name} theme",
           theme_mod.contrast(p["bright"], p["panel"]) >= 12
           and theme_mod.contrast(p["bright-2"], p["panel"]) >= 7)

    ok("ink is legible on the panel, both ways",
       theme_mod.contrast(dark["ink"], dark["panel"]) > 7
       and theme_mod.contrast(lightp["ink"], lightp["panel"]) > 7)
    # The one that breaks silently: a theme's yellow is chosen for a terminal,
    # not for a panel, and an unreadable warning colour is worse than none.
    for name, p in (("dark", dark), ("light", lightp)):
        for role in ("ok", "warn", "bad", "info", "ai"):
            ok(f"{role} is readable on the {name} panel",
               theme_mod.contrast(p[role], p["panel"]) >= 3.3)
    ok("badge text contrasts with its own badge",
       all(theme_mod.contrast(p[r], p["on-" + r]) >= 3.5
           for p in (dark, lightp) for r in ("ok", "warn", "bad", "info", "ai")))
ok("a missing theme falls back rather than failing",
   theme_mod.palette("/nonexistent/colors.toml")["mode"] == "dark")


# ---- the garage -------------------------------------------------------------
head("The garage")

import garage  # noqa: E402

gtmp = tempfile.mkdtemp()
g_state, g_garage, g_pointer, g_legacy = (
    garage.STATE, garage.GARAGE, garage.POINTER, garage.LEGACY)
garage.STATE = gtmp
garage.GARAGE = os.path.join(gtmp, "vehicles")
garage.POINTER = os.path.join(gtmp, "current-vehicle")
garage.LEGACY = os.path.join(gtmp, "telemetry.db")

ok("a VIN becomes a filename", garage.key_for("JHMZF1D64FS004917") == "JHMZF1D64FS004917")
# A VIN is alphanumeric by definition, so anything else is punctuation
# somebody typed — and keeping it would make two spellings into two cars.
ok("punctuation is stripped out of it", garage.key_for("JH-MZ/F1 D6") == "JHMZF1D6")
ok("something too short to be a VIN is not one", garage.key_for("AB") == "unknown")

k1, new1 = garage.switch_to("JHMZF1D64FS004917")
ok("switching to an unseen car says it is new", new1 is True)
ok("...and it becomes current", garage.current() == k1)
k2, new2 = garage.switch_to("WP0ZZZ99ZTS392124")
ok("a second car gets its own key", k2 != k1)
_, again = garage.switch_to("JHMZF1D64FS004917")
ok("coming back to the first is not new", again is False)

# The bug this whole module exists to prevent: one car's codes landing on
# another car's record.
ok("each car has its own database path", garage.path_for(k1) != garage.path_for(k2))

garage.STATE, garage.GARAGE, garage.POINTER, garage.LEGACY = (
    g_state, g_garage, g_pointer, g_legacy)
shutil.rmtree(gtmp, ignore_errors=True)


# ---- trends and concerns ----------------------------------------------------
head("Trends")

import concerns  # noqa: E402

ok("a fit needs enough points", concerns.fit([(1, 1), (2, 2)]) is None)
line = concerns.fit([(i, 2.0 * i + 5.0) for i in range(10)])
ok("a straight line is found exactly",
   abs(line[0] - 2.0) < 1e-9 and abs(line[1] - 5.0) < 1e-9)
ok("...and reported as a perfect fit", abs(line[2] - 1.0) < 1e-9)
noise = concerns.fit([(i, 5.0) for i in range(10)])
ok("a flat line has no slope", abs(noise[0]) < 1e-9)

ok("a projection reaches the limit where it should",
   abs(concerns.project(1.0, 0.0, 110.0, 100.0) - 10.0) < 1e-9)
ok("a line going the wrong way never arrives",
   concerns.project(-1.0, 0.0, 110.0, 100.0) is None)
ok("nor does one that arrives too far out to mean anything",
   concerns.project(0.0001, 0.0, 110.0, 100.0) is None)
ok("a projection past a year says so", concerns.when(500) == "a year or more out")
ok("and one within weeks says that", concerns.when(10) == "within weeks")
ok("no projection is not a date", concerns.when(None) == "beyond a year")


# ---- photographs ------------------------------------------------------------
head("Photographs")

import photos  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
ok("a JPEG is recognised by its bytes", photos.sniff(JPEG)[0] == "jpg")
ok("so is a PNG", photos.sniff(PNG)[0] == "png")
# Never from a filename: an executable called photo.jpg is still an executable.
ok("anything else is refused", photos.sniff(b"MZ\x90\x00rubbish")[0] is None)
ok("a truncated WebP is not a WebP", photos.sniff(b"RIFFxxxxNOPE")[0] is None)

ptmp = tempfile.mkdtemp()
photos_root = photos.ROOT
photos.ROOT = ptmp
ok("a filename that climbs out resolves to nothing",
   photos.path_of("../../../etc/passwd") is None)
ok("...as does an absolute one", photos.path_of("/etc/passwd") is None)
ok("and a name for a file that is not there", photos.path_of("nope.jpg") is None)
photos.ROOT = photos_root
shutil.rmtree(ptmp, ignore_errors=True)


# ---- the survey's ordering contract -----------------------------------------
head("Survey")

import survey  # noqa: E402


class FakeResponse:
    def __init__(self, value):
        self._v = value

    def is_null(self):
        return self._v is None

    @property
    def value(self):
        return self._v


class FakeConn:
    """Just enough of a connection to answer a Mode 09 VIN query."""

    def __init__(self, vin):
        self.vin = vin

    def query(self, cmd, force=False):
        return FakeResponse(bytearray(self.vin.encode()) if self.vin else None)

    def protocol_name(self):
        return "ISO 15765-4 (CAN 11/500)"


class FakeCommands:
    VIN = object()


class FakeObd:
    commands = FakeCommands


stmp = tempfile.mkdtemp()
s_state, s_garage, s_pointer, s_legacy = (
    garage.STATE, garage.GARAGE, garage.POINTER, garage.LEGACY)
garage.STATE = stmp
garage.GARAGE = os.path.join(stmp, "vehicles")
garage.POINTER = os.path.join(stmp, "current-vehicle")
garage.LEGACY = os.path.join(stmp, "telemetry.db")
survey_real_db = records.DB

ok("no connection means no switching", survey.prepare(None) is None)

out = survey.prepare(FakeConn("JHMZF1D64FS004917"), FakeObd)
ok("a VIN picks the car", out and out[0] == "JHMZF1D64FS004917")
ok("an unseen car is reported as new", out[1] is True)
ok("...and the reader is pointed at it", garage.key_for("JHMZF1D64FS004917") in records.DB)

out = survey.prepare(FakeConn("JHMZF1D64FS004917"), FakeObd)
ok("the same car again is not new", out[1] is False)

out = survey.prepare(FakeConn("WP0ZZZ99ZTS392124"), FakeObd)
ok("a different car switches records", out[0] == "WP0ZZZ99ZTS392124")

# An adapter that will not give up a VIN keeps whatever record was current.
# That is the best guess available and is at least stable.
before = records.DB
ok("no VIN leaves the record alone",
   survey.prepare(FakeConn(None), FakeObd) is None and records.DB == before)

garage.STATE, garage.GARAGE, garage.POINTER, garage.LEGACY = (
    s_state, s_garage, s_pointer, s_legacy)
records.DB = survey_real_db
shutil.rmtree(stmp, ignore_errors=True)

# VIN decoding, which is the only way this tool knows what car it is in.
ok("the manufacturer comes from the first three characters",
   survey.decode_vin("JHMZF1D64FS004917").get("make") == "Honda")
ok("the year comes from the tenth",
   survey.decode_vin("JHMZF1D64FS004917").get("year") == 2015)
ok("a valid North American check digit is confirmed",
   survey.decode_vin("1HGCM82633A004352").get("vin_valid") is True)
ok("a broken one is reported rather than trusted",
   survey.decode_vin("1HGCM82634A004352").get("vin_valid") is False)
ok("a VIN too short to read gives nothing", survey.decode_vin("ABC") == {})
ok("the model is never guessed",
   "model" not in survey.decode_vin("JHMZF1D64FS004917"))


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


# ---- the shareable report ---------------------------------------------------
head("Sharing")

import share  # noqa: E402

doc = share.build(note="for the garage")
ok("the report is a whole document", doc.startswith("<!doctype html>"))
ok("the note reaches it", "for the garage" in doc)
# The whole point: it opens on somebody else's machine, ten years from now,
# with no server and no network.
ok("nothing is fetched from anywhere",
   "http://" not in doc and "https://" not in doc)
ok("no stylesheet or script is linked",
   "<link" not in doc.lower() and "<script" not in doc.lower())
ok("it says how it was produced", "read from the vehicle" in doc.lower()
   or "control units" in doc.lower())
# A simulated car must say so in anything that leaves the machine.
ok("a simulated car is labelled as one in the report",
   ("SIMULATED" in doc) == bool(records.snapshot().get("simulated")))
ok("the vehicle is named in the title", "OmaCar report" in doc)


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

# ---- the panel must not re-implement staleness differently ------------------
head("Panel freshness")

_panel = pathlib.Path(__file__).resolve().parent.parent / "plugin" / "Panel.qml"
_qml = _panel.read_text(encoding="utf-8")

# The QML panel reads live.json directly rather than going through
# records.live(), so it carries its own copy of the staleness rule. That is a
# real duplication and it went wrong once: the panel had NO check at all, and
# happily showed an 8.6-hour-old {"connected": true} as a live link -- green bar
# icon, a Stop button, over an adapter that was not plugged in. This test is
# here so the two numbers cannot drift apart again.
_m = re.search(r"readonly property int liveStale:\s*(\d+)", _qml)
ok("the panel declares a staleness window", _m is not None)
ok("the panel's staleness window matches records.LIVE_STALE",
   _m is not None and int(_m.group(1)) == records.LIVE_STALE)
ok("the panel gates connected on freshness, not on the flag alone",
   "root.liveFresh" in _qml
   and re.search(r"property bool connected:.{0,200}?liveFresh", _qml, re.S) is not None)
# A frozen clock is the other half of the same bug: freshness is measured
# against nowSec, so the timer that advances it must not stop with the panel.
ok("the clock keeps running while the panel is shut",
   re.search(r"interval:\s*root\.opened \? 1000 : \d+", _qml) is not None)


# The car in the bar and in the panel. The wheels are each a Shape rotated
# about its own hub, and the rotation origin has to be given in the path space
# the rotation is applied in -- BEFORE the Translate that lifts the artwork into
# view. Adding the translate offsets to the origin looked right and rotated each
# wheel about a point roughly a third of a car above itself, so the spokes swung
# up over the roof and off the top of the icon once per revolution.
head("The car")

_car = (pathlib.Path(__file__).resolve().parent.parent / "plugin" / "Car.qml"
        ).read_text(encoding="utf-8")
_origin = re.search(r"Rotation\s*\{(.*?)\}", _car, re.S)
ok("each wheel rotates about its own hub", _origin is not None)
ok("the wheel's rotation origin carries no translate offset",
   _origin is not None
   and "offX" not in _origin.group(1) and "offY" not in _origin.group(1))
ok("the artwork offsets are still applied, as a Translate",
   "Translate { x: root.offX; y: root.offY }" in _car)


head("The link")

# A hand-off is not a disconnection. The daemon lends the serial port to the DTC
# sweep every few minutes and publishes connected=false while it does; read
# literally that turned a whole drive into a flapping link -- twenty "the
# adapter is no longer answering" alerts in an afternoon, none of them real.
import watch as watch_mod  # noqa: E402

_alerts = []
_w = watch_mod.Watch(quiet=True, persist=False, watch_faults=False,
                     sink=_alerts)
_w.last_connected = True

_w.link(False, {"status": "yielded", "handover": True}, 1000.0)
ok("a hand-off raises nothing", not _alerts)
ok("a hand-off does not even count as a state change", _w.last_connected is True)

# A blip: down at t, back up before the settle window closes.
_w.link(False, {"status": "lost"}, 1001.0)
_w.link(True, {"connected": True}, 1005.0)
ok("a link that returns inside the settle window raises nothing", not _alerts)

# A real drop: down, and still down past the window.
_w.link(False, {"status": "lost"}, 2000.0)
ok("a fresh drop is not announced immediately", not _alerts)
_w.link(False, {"status": "lost"}, 2000.0 + watch_mod.Watch.LINK_SETTLE + 1)
ok("a drop that holds is announced", len(_alerts) == 1)
ok("and it is the adapter alert", bool(_alerts) and _alerts[0]["key"] == "link")
ok("and it says the adapter stopped answering",
   bool(_alerts) and "no longer answering" in _alerts[0]["body"])

ok("records.live marks a hand-off as one", "handover" in records.live())


head("Whose car")

# `name` is the human's label for the car and the only field that carries the
# model, because OBD-II does not report one. records.vehicle() used to
# overwrite it with f"{year} {make} {model}" -- against a `model` key that has
# never existed on any car -- so the model was destroyed to build "2015 Honda".
_vdb = sqlite3.connect(":memory:")
_vdb.row_factory = sqlite3.Row
_vdb.execute("CREATE TABLE vehicle (k TEXT PRIMARY KEY, v TEXT)")
for _k, _v in (("name", '"CR-Z"'), ("make", '"Honda"'), ("year", "2015"),
               ("driver", '"James"')):
    _vdb.execute("INSERT INTO vehicle (k, v) VALUES (?, ?)", (_k, _v))
_veh = records.vehicle(_vdb)

ok("the model survives", _veh["model"] == "CR-Z")
ok("the name says what the car is", _veh["name"] == "2015 Honda CR-Z")
ok("the title says whose it is", _veh["title"] == "James' 2015 Honda CR-Z")
ok("the human's own label is still available to the garage editor",
   _veh["label"] == "CR-Z")
ok("a name ending in s takes a bare apostrophe",
   records.possessive("James") == "James'")
ok("any other name takes 's", records.possessive("Alex") == "Alex's")
ok("no driver means no possessive", records.possessive("") == "")

# A car with nothing but a label must not come out blank.
_vdb2 = sqlite3.connect(":memory:")
_vdb2.row_factory = sqlite3.Row
_vdb2.execute("CREATE TABLE vehicle (k TEXT PRIMARY KEY, v TEXT)")
_vdb2.execute("INSERT INTO vehicle (k, v) VALUES ('name', '\"the van\"')")
ok("a car with only a label keeps it", records.vehicle(_vdb2)["name"] == "the van")

# The panel's engine-load row. Both children were unanchored, so the throttle
# reading printed on top of the words ENGINE LOAD.
ok("the panel's engine-load row anchors its label and its reading apart",
   re.search(r"SectionLabel \{\s*id: loadLabel.*?anchors\.left", _qml, re.S) is not None
   and re.search(r"Muted \{\s*id: loadValue.*?anchors\.right", _qml, re.S) is not None)

# THE PANEL'S ROLLUP HAD NO WRITER.
#
# Panel.qml reads ~/.local/state/omarchy/liquid-glass-car.json and refreshed it
# by running `liquid-glass-car --quiet` -- a command that exists nowhere in this
# repo and on nobody's PATH. So the file was never written, root.car was always
# {}, and every vehicle field in the panel -- name, VIN, faults, service, trips,
# odometer -- was permanently blank while the live gauges worked fine. The
# panel said "No car" next to a car that was plainly driving.
_refresh = re.search(r"function refreshNow\(\) \{(.*?)\n  \}", _qml, re.S)
ok("the panel has a refresh", _refresh is not None)
_cmd = _refresh.group(1) if _refresh else ""
ok("the panel's refresh does not call a command that does not exist",
   "liquid-glass-car" not in _cmd)
_cli = (pathlib.Path(__file__).resolve().parent.parent / "bin" / "omacar"
        ).read_text(encoding="utf-8")
_sub = re.search(r"omacar (panel-cache)", _cmd)
ok("the panel's refresh names an omacar subcommand", _sub is not None)
ok("and the CLI actually has that subcommand",
   _sub is not None and re.search(r"^\s*%s\)" % re.escape(_sub.group(1)),
                                  _cli, re.M) is not None)
ok("opening the panel rebuilds the rollup rather than only re-reading it",
   re.search(r"onOpenedChanged:.{0,600}?root\.refreshNow\(\)", _qml, re.S) is not None)

# The panel must not treat a hand-off as a lost car either.
ok("the panel knows a hand-off from a disconnection",
   "readonly property bool handover:" in _qml
   and re.search(r"property bool connected:.{0,200}?handover", _qml, re.S) is not None)


head("Serving")

# Static assets carried no Cache-Control at all, so browsers fell back to
# heuristic caching and an updated OmaCar kept running the old js modules in
# any tab that already had them -- silently, with no error to notice.
_serve = (pathlib.Path(__file__).resolve().parent.parent / "lib" / "serve.py"
          ).read_text(encoding="utf-8")
ok("static responses declare a cache policy",
   re.search(r'send_header\("Cache-Control", "no-cache"\)', _serve) is not None)
# Match the CALL, not the prose: the comment beside it explains the choice by
# naming no-store, and the first version of this test read that and failed.
_end = re.search(r"def end_headers.*?super\(\).end_headers\(\)", _serve, re.S).group(0)
ok("it is no-cache, so unchanged assets still 304 rather than re-download",
   re.findall(r'send_header\("Cache-Control", "([a-z-]+)"\)', _end) == ["no-cache"])
ok("the API keeps its stricter no-store", '"Cache-Control", "no-store"' in _serve)
# One header, not two: the API sets its own before end_headers runs.
ok("a response that set its own policy is not given a second one",
   "self.cache_policy_sent" in _serve
   and re.search(r"def send_header.*?cache-control", _serve, re.S) is not None)

head("Looks")

_share = pathlib.Path(__file__).resolve().parent.parent / "share"
_fx = (_share / "js" / "effects.js").read_text(encoding="utf-8")
_looks = (_share / "js" / "looks.js").read_text(encoding="utf-8")

ok("the lasers effect is gone from the effects module", "lasers" not in _fx)
ok("and no look still asks for it", "laser" not in _looks)
ok("nothing anywhere in the app still references it",
   not any("laser" in (_share / "js" / f.name).read_text(encoding="utf-8")
           for f in (_share / "js").glob("*.js")))

# A look names an effect by string. Point one at an effect that does not exist
# and nothing errors -- mountEffect just silently draws the other one, which is
# how a look ends up wearing somebody else's animation.
_effects = set(re.findall(r'"([a-z]+)"',
               re.search(r"export const EFFECTS = \[(.*?)\]", _fx).group(1)))
_want = set(re.findall(r"effect:\s*\"([a-z]+)\"", _looks))
ok("the aurora is a real effect", "aurora" in _effects)
ok("every look names an effect that exists", _want.issubset(_effects))
ok("and every effect is reachable from some look", _effects.issubset(_want | {"off"}))

# The aurora is drawn small and scaled up; if that buffer ever loses its cap
# the effect quietly becomes a full-resolution fill on a 2-core laptop.
ok("the aurora renders into a small buffer, not the full canvas",
   re.search(r"const LOW = \d{2,3};", _fx) is not None
   and "drawImage(buf" in _fx)


head("Gauges")

_gauges = (_share / "js" / "gauges.js").read_text(encoding="utf-8")
_drive = (_share / "js" / "views" / "drive.js").read_text(encoding="utf-8")
api_src = (pathlib.Path(__file__).resolve().parent.parent / "lib" / "api.py"
           ).read_text(encoding="utf-8")

# The kinds the browser can draw and the kinds the server will store have to be
# the same list. They live in two languages and drift silently: an unknown kind
# reaching the browser renders NOTHING, in a moving car.
_js_kinds = set(re.findall(r"^  ([a-z]+): \{$", 
                re.search(r"export const KINDS = \{(.*?)\n\};", _gauges, re.S).group(1),
                re.M))
_py_kinds = set(re.findall(r'"([a-z]+)"',
                re.search(r"GAUGE_KINDS = \((.*?)\)", api_src, re.S).group(1)))
ok("the browser and the server agree on the gauge kinds", _js_kinds == _py_kinds)
ok("digital is one of them", "digital" in _js_kinds)

# Only readouts with a scale may wear a gauge; the rest can only be numbers.
ok("a readout with no scale is offered nothing but a number",
   "return def && def.scale ? KIND_IDS : [\"digital\"];" in _gauges)
ok("an unrecognised kind falls back rather than rendering nothing",
   "export function normaliseKind" in _gauges
   and "allowed.includes(kind) ? kind : \"digital\"" in _gauges)

# Every readout that declares a scale must also be able to produce a NUMBER for
# it. A scale with no read() is a face with a needle that never moves.
_scaled = set(re.findall(r"^  ([a-z_0-9]+): \{(?=(?:(?!^  [a-z_0-9]+: \{).)*?\n    scale:)",
                         _drive, re.S | re.M))
_readable = set(re.findall(r"^  ([a-z_0-9]+): \{(?=(?:(?!^  [a-z_0-9]+: \{).)*?\n    read:)",
                           _drive, re.S | re.M))
ok("several readouts carry a scale", len(_scaled) >= 10)
ok("every scaled readout can also produce a raw number", _scaled.issubset(_readable))

# The bands are spans, because trouble is not always at the top of the scale.
ok("bands are spans rather than a single upper threshold",
   "function bands(scale)" in _gauges and "b.from === undefined" in _gauges)
ok("fuel trim marks trouble at both ends of its scale",
   re.search(r"LONG_FUEL_TRIM_1.{0,400}?to: -15.{0,200}?from: 15", _drive, re.S) is not None)
# A signed scale grows from zero. Filled from the left edge, a healthy +7.8%
# trim drew a bar straight through the whole negative half and its warnings.
ok("a signed bar anchors at zero", "const zeroT = scale.min < 0 && scale.max > 0" in _gauges)

# The layout round-trips: a kind the server drops is a kind that silently
# reverts the moment the editor saves.
_drive_default = api.DEFAULT_DRIVE
ok("the stored layout has somewhere to keep the kinds",
   "kinds" in _drive_default and "heroKind" in _drive_default)
_saved = api._clean_kinds({"speed": "dial", "rpm": "arc",
                           "coolant": "nonsense", 7: "bar", "load": "digital"})
ok("a kind that does not exist is dropped", "coolant" not in _saved)
ok("a non-string tile id is dropped", 7 not in _saved)
ok("the good ones survive", _saved == {"speed": "dial", "rpm": "arc"})


head("The hub")

# The hub used to rebuild its entire DOM -- title, vitals, the radio transport,
# six tiles and every SVG icon in them -- inside a listener on `live`, which
# fires every 250ms. Four times a second the whole screen was destroyed and
# made again: that is what the blinking was, and it also meant the volume
# slider could not be dragged, because the element under your finger stopped
# existing.
_hub = (_share / "js" / "views" / "hub.js").read_text(encoding="utf-8")
ok("the live listener updates rather than rebuilds",
   re.search(r'store\.on\("live",\s*update\)', _hub) is not None)
ok("nothing removes the hub's children on a sample",
   "n.remove()" not in _hub and "clear(root)" not in _hub)
ok("a value is only written when it changed", "!== text" in _hub)
ok("the radio is remounted on radio events, not on samples",
   re.search(r"radio\.on\(remountRadio\)", _hub) is not None)

head("Themes you build")

import themes as themes_mod  # noqa: E402

_thstore = os.path.join(tmp, "themes.json")
_th_real = themes_mod.STORE
themes_mod.STORE = _thstore

VIOLET = {"name": "Violet", "mode": "dark", "background": "#141021",
          "foreground": "#ede7ff", "accent": "#b48eff", "red": "#ff6b8a",
          "green": "#6be39a", "yellow": "#ffc46b", "blue": "#7fb4ff",
          "magenta": "#c98cff"}

ok("nothing to start with", themes_mod.load()["themes"] == {})
ok("and the desktop is what is worn", themes_mod.load()["active"] == themes_mod.DESKTOP)

_store, _err = themes_mod.put("violet", VIOLET)
ok("a theme can be saved", _err is None and "violet" in _store["themes"])
ok("saving does not change what is worn", _store["active"] == themes_mod.DESKTOP)

_store, _err = themes_mod.select("violet")
ok("and then worn", _err is None and _store["active"] == "violet")
_src, _stamp = themes_mod.active()
ok("the active theme is handed back as source colours", _src["accent"] == "#b48eff")
ok("with a stamp, so a running app notices", _stamp > 0)

# THE POINT OF THE WHOLE DESIGN: nine colours in, a legible palette out.
_p = theme_mod.palette_of(VIOLET)
ok("a theme built from nine colours derives the whole palette",
   all(k in _p for k in ("ground", "panel", "raise", "edge", "ink", "dim",
                         "faint", "ghost", "bright", "bright-2", "ok", "bad")))
# ground used to fall back to `background`, which makes the page behind the app
# exactly the colour of the cards on it and erases every panel edge.
ok("the ground is a real step below the panel", _p["ground"] != _p["panel"])
ok("and it took the theme's own hue with it",
   theme_mod.hex_to_rgb(_p["ground"])[2] > theme_mod.hex_to_rgb(_p["ground"])[1])
# The floors apply to a home-made theme exactly as they do to an installed one.
ok("body ink clears its floor", theme_mod.contrast(_p["faint"], _p["panel"]) >= 5.0)
ok("in-car ink clears its floor", theme_mod.contrast(_p["bright"], _p["panel"]) >= 12)
for _role in ("ok", "warn", "bad", "info", "ai"):
    ok(f"{_role} is readable on a home-made panel",
       theme_mod.contrast(_p[_role], _p["panel"]) >= 3.3)

# A theme naming nothing must still be the app's own designed palette.
ok("an empty theme falls back rather than deriving from nothing",
   theme_mod.palette_of({})["ground"] == "#070B0D")
ok("an installed theme is unaffected by any of this",
   theme_mod.palette_of({"background": "#1a1b26", "darker_background": "#0e0e14",
                         "foreground": "#c0caf5"})["ground"] == "#0e0e14")

# Hand-edited nonsense must not reach the browser.
_store, _err = themes_mod.put("BAD ID", VIOLET)
ok("an id that is not a slug is refused", _err is not None)
_bad = themes_mod._clean("x", {**VIOLET, "background": "not a colour", "mode": "sideways"})
ok("a colour that is not a colour falls back to the seed",
   _bad["background"] == themes_mod.SEED["background"])
ok("a mode that is not a mode becomes dark", _bad["mode"] == "dark")

# Deleting what you are wearing must leave you wearing something.
themes_mod.select("violet")
_store, _err = themes_mod.remove("violet")
ok("deleting the active theme falls back to the desktop",
   _store["active"] == themes_mod.DESKTOP)
_src, _ = themes_mod.active()
ok("and the app is told to follow the desktop again", _src is None)

themes_mod.STORE = _th_real


shutil.rmtree(tmp, ignore_errors=True)

print(f"\n  {len(PASS)} passed, {len(FAIL)} failed\n")
sys.exit(1 if FAIL else 0)
