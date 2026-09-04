#!/usr/bin/env python3
"""The IMA reader's load-bearing logic, tested without a car or an adapter.

Four things here would fail QUIETLY rather than loudly, which is the only
reason any of them is worth a test.

The first is the 0x40 rule. Every DTC status byte this car has ever produced
says "the monitor has not run this cycle", and the whole IMA screen is built
around saying so as a headline. The failure mode is not a crash: it is the day
a real pass or fail finally appears in a drive log and the flag STAYS on,
telling the owner his eighteen genuine hybrid faults are nothing to worry
about. So the test that matters is not that the flag is true today, it is that
it goes false the instant one real status byte lands.

The second is the anti-fakery guard. A quantity nobody has discovered must
never carry a number. The tempting failure is a zero, and a zero on a state of
charge is a flat pack.

The third is that nothing raises. Every input is a file a person can edit or
delete and a drive log is appended to while it is being read, so the last line
of a live one is routinely half written.

The fourth is that the commands this screen tells somebody to type are real.
A screen that confidently prints a subcommand bin/omacar does not have is worse
than a screen that prints nothing.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

import connect       # noqa: E402
import frontier      # noqa: E402
import garage        # noqa: E402
import ima           # noqa: E402

PASS, FAIL = [], []


def ok(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"   {'ok ' if cond else 'FAIL'}  {name}")


def head(name):
    print(f"\n  {name}\n")


# A scratch state directory. Every reader in ima.py resolves connect.STATE at
# call time, so pointing it here redirects the whole module -- which is what
# lets these tests describe a car that does not exist.
tmp = tempfile.mkdtemp(prefix="omacar-ima-test-")
_real_state = connect.STATE
_real_frontier = frontier.STATE_DIR
_real_garage = (garage.STATE, garage.GARAGE, garage.POINTER)

connect.STATE = tmp
frontier.STATE_DIR = os.path.join(tmp, "frontier")
garage.STATE = tmp
garage.GARAGE = os.path.join(tmp, "vehicles")
garage.POINTER = os.path.join(tmp, "current-vehicle")
os.makedirs(os.path.join(tmp, "dtclog"), exist_ok=True)


def write_log(name, records):
    p = os.path.join(tmp, "dtclog", name)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def sample(t, volts, header, codes, status_flag="not run this cycle",
           status_byte=0x40, catalogue=None, count=None):
    """One dtclog record, shaped exactly as lib/dtclog.sample_once writes it."""
    mod = {
        "count": {"kind": "positive",
                  "count": len(codes) if count is None else count},
        "status": {"kind": "positive", "raw": "59",
                   "dtcs": [{"code": c, "status": status_byte,
                             "flags": status_flag} for c in codes]},
    }
    if catalogue is not None:
        mod["catalogue"] = {"raw": "59", "dtcs": list(catalogue)}
    return {"t": t, "volts": volts, "modules": {header: mod}}


NOW = time.time()

# ---- the fault picture ------------------------------------------------------
head("The fault picture")

write_log("drive-a.jsonl", [
    sample(NOW - 600, 13.9, "18DA03F1", ["P0A7F-03", "P1446-03"],
           catalogue=["P0A7F-03", "P1446-03", "P0DA8-03"]),
    sample(NOW - 300, 14.0, "18DA03F1", ["P0A7F-03", "P0DA8-03", "P1447-03"],
           catalogue=["P0A7F-03", "P1446-03", "P0DA8-03", "P1447-03"]),
])
write_log("drive-b.jsonl", [
    sample(NOW - 120, 12.4, "18DA04F1", ["P1437-03"], catalogue=["P1437-03"]),
])

mods = ima.modules()
batt = mods["18DA03F1"]
motor = mods["18DA04F1"]

# The catalogue is a UNION across captures, not the last one seen. A module
# that answers with a short reply on one pass must not shrink what we know.
ok("the catalogue is the union across every capture",
   batt["catalogue"] == ["P0A7F-03", "P0DA8-03", "P1446-03", "P1447-03"])
ok("distinct flagged codes are counted across the whole record",
   len(batt["flagged"]) == 4)
ok("every individual observation is counted, not just the distinct codes",
   batt["observations"] == 5)
ok("a code seen in two samples records both",
   next(f for f in batt["flagged"] if f["code"] == "P0A7F-03")["seen"] == 2)
ok("first and last sightings are kept",
   batt["first_seen"] < batt["last_seen"])
ok("two modules stay two modules", motor["observations"] == 1)

# THE ONE THAT MATTERS.
ok("all-not-run is true while every status byte says the monitor has not run",
   batt["all_not_run"] is True)

write_log("drive-c.jsonl", [
    sample(NOW - 60, 14.1, "18DA03F1", ["P0A7F-03"],
           status_flag="confirmed, failed since clear", status_byte=0x28),
])
after = ima.modules()["18DA03F1"]
ok("one real status byte anywhere flips it false -- the guard is not a constant",
   after["all_not_run"] is False)
ok("and the new flag string is recorded beside the old one",
   len(after["flag_states"]) == 2)
os.remove(os.path.join(tmp, "dtclog", "drive-c.jsonl"))

# ---- surviving the files ----------------------------------------------------
head("Surviving the files")

# dtclog appends while a drive is in progress, so the last line of a live log
# is routinely half written.
with open(os.path.join(tmp, "dtclog", "drive-a.jsonl"), "a") as f:
    f.write('{"t": 123, "modules": {"18DA03F1": {"stat')
ok("a half-written last line costs that line and nothing else",
   len(ima.modules()["18DA03F1"]["flagged"]) == 4)

with open(os.path.join(tmp, "dtclog", "drive-junk.jsonl"), "w") as f:
    f.write("this is not json at all\n[]\n{}\n")
ok("a log that is not a log at all is skipped rather than fatal",
   len(ima.modules()["18DA03F1"]["flagged"]) == 4)

with open(os.path.join(tmp, "live.json"), "w") as f:
    f.write("{ definitely not json")
ok("a corrupt live.json does not raise", isinstance(ima.quantities(), list))

ok("summary() survives every one of them",
   not ima.summary().get("error"))

empty = tempfile.mkdtemp(prefix="omacar-ima-empty-")
connect.STATE = empty
ok("a state directory with nothing in it produces a summary, not an exception",
   isinstance(ima.summary().get("quantities"), list))
ok("and every quantity in it is undiscovered",
   all(q["state"] == "undiscovered" for q in ima.quantities()))
shutil.rmtree(empty, ignore_errors=True)
connect.STATE = tmp

# ---- the four states --------------------------------------------------------
head("The four states")


def live(values, age=0.0, supported=("HYBRID_BATTERY_REMAINING",)):
    with open(os.path.join(tmp, "live.json"), "w", encoding="utf-8") as f:
        json.dump({"connected": True, "t": time.time() - age,
                   "supported": list(supported), "values": values}, f)


def q(qid):
    return next(x for x in ima.quantities() if x["id"] == qid)


live({}, supported=[])
ok("a PID the car has never claimed is undiscovered",
   q("pack_remaining")["state"] == "undiscovered")

live({})
row = q("pack_remaining")
ok("a PID the car SAYS it supports but nobody has polled is still undiscovered",
   row["state"] == "undiscovered")
# The distinction the owner has to be able to read off the screen: a support
# bitmap is a claim about a bitmap, not a reading.
ok("and it says so rather than implying a measurement",
   "bitmap" in (row["note"] or "").lower() and row["value"] is None)

live({"HYBRID_BATTERY_REMAINING": 74.5}, age=2.0)
row = q("pack_remaining")
ok("a fresh reading is measured", row["state"] == "measured")
ok("and it carries the number", abs(row["value"] - 74.5) < 0.001)

live({"HYBRID_BATTERY_REMAINING": 74.5}, age=3600.0)
row = q("pack_remaining")
ok("the same reading an hour later is stale, not measured",
   row["state"] == "stale")
ok("stale still shows the number, because history is not nothing",
   row["value"] == 74.5)

# THE ANTI-FAKERY GUARD. An undiscovered quantity carrying a number -- most
# temptingly a zero -- is the exact failure this whole screen exists to avoid.
ok("nothing undiscovered ever carries a value",
   all(x["value"] is None for x in ima.quantities()
       if x["state"] == "undiscovered"))
ok("every undiscovered quantity carries a command that would find it",
   all(x["command"] for x in ima.quantities()
       if x["state"] == "undiscovered"))
ok("and a safety line, because these are engine-running sweeps",
   all("ATRV" in x["safety"] or "voltage" in x["safety"]
       for x in ima.quantities() if x["state"] == "undiscovered"))

# ---- candidates -------------------------------------------------------------
head("Unvalidated candidates")

prof_dir = os.path.join(tmp, "profiles")
os.makedirs(prof_dir, exist_ok=True)
import profile as profilelib  # noqa: E402
_real_dirs = list(profilelib.PROFILE_DIRS)
profilelib.PROFILE_DIRS = [prof_dir]


def write_profile(confidence, varying="[]"):
    with open(os.path.join(prof_dir, "honda-crz-2015.toml"), "w") as f:
        f.write('schema = 1\n[car]\nslug = "honda-crz-2015"\n\n'
                '[[pid]]\nid = "x"\nheader = "18DA03F1"\nrequest = "22F181"\n'
                'service = 0x22\nvarying_bytes = %s\n'
                'confidence = "%s"\n' % (varying, confidence))


write_profile("candidate")
c = ima._candidates()[0]
ok("a candidate on a hybrid module is surfaced", c["header"] == "18DA03F1")
# lib/profile.py writes this rule into the header of every file it generates:
# an entry below `validated` must not drive a gauge.
ok("and it is marked as not displayable", c["displayable"] is False)
ok("a static payload is described as a constant, not as a reading",
   "constant" in c["why"])

write_profile("validated")
ok("only a validated entry may drive a display",
   ima._candidates()[0]["displayable"] is True)

write_profile("candidate", varying="[2, 3]")
ok("a candidate whose bytes MOVED lifts the register out of undiscovered",
   q("soc")["state"] == "candidate")
ok("and it still refuses to put a number on it", q("soc")["value"] is None)
# An UNNAMED moving byte cannot be attributed to one quantity. Pinning it to
# state of charge because that is the one everybody wants would be the same
# invention this whole screen exists to refuse.
ok("an unnamed moving candidate lifts every quantity, not just the wanted one",
   q("pack_temp")["state"] == "candidate"
   and "which quantity it carries" in q("soc")["note"])

with open(os.path.join(prof_dir, "honda-crz-2015.toml"), "a") as f:
    f.write('name = "pack_temp"\n')
ok("a NAMED candidate belongs to the quantity it names",
   q("pack_temp")["state"] == "candidate")
ok("and to no other", q("soc")["state"] == "undiscovered")

write_profile("candidate")
ok("a candidate whose bytes never moved leaves the register undiscovered",
   q("soc")["state"] == "undiscovered")

os.remove(os.path.join(prof_dir, "honda-crz-2015.toml"))
with open(os.path.join(prof_dir, "honda-crz-2015.toml"), "w") as f:
    f.write("this is not toml [[[\n")
ok("a hand-mangled profile costs the candidate list and nothing else",
   ima._candidates() == [] and not ima.summary().get("error"))
profilelib.PROFILE_DIRS = _real_dirs

# ---- discovery uses frontier, it does not reimplement it --------------------
head("Discovery")

with open(garage.POINTER, "w") as f:
    f.write("TESTCAR")

d = ima.discovery()
ok("an untouched car reports an empty frontier", d["frontier_empty"] is True)
first = next(r for r in d["ranges"]
             if r["header"] == "18DA03F1" and r["service"] == "0x22")
ok("the next unasked block starts at the bottom of the range",
   first["next"] == "0000-0FFF")
ok("nothing is reported as swept", first["swept"] == 0)

doc = frontier.load("TESTCAR")
frontier.record(doc, 0x22, "18DA03F1", 0x0000, 0x0FFF)
frontier.save(doc, "TESTCAR")

d = ima.discovery()
after = next(r for r in d["ranges"]
             if r["header"] == "18DA03F1" and r["service"] == "0x22")
ok("recording a span moves the next question past it",
   after["next"] == "1000-1FFF")
ok("and the swept count is frontier's arithmetic, not a second copy of it",
   after["swept"] == 0x1000)
ok("the answered list reports the 0x19 catalogues the logs actually hold",
   any(a["sub"] == "0A" and a["header"] == "18DA03F1" for a in d["answered"]))

# THE TWO SERVICES DO NOT HAVE THE SAME SIZE OF SPACE. 0x21 takes a one-byte
# local identifier -- 256 of them -- and 0x22 takes a two-byte DID running to
# 0xA5FF. Reporting "0% of 42,496 identifiers" against 0x21 would be a made-up
# number on the one panel whose entire job is counting honestly.
r21 = next(r for r in d["ranges"]
           if r["header"] == "18DA03F1" and r["service"] == "0x21")
r22 = next(r for r in d["ranges"]
           if r["header"] == "18DA03F1" and r["service"] == "0x22")
ok("service 0x21 is 256 identifiers wide, not 42,496", r21["total"] == 256)
ok("service 0x22 runs to 0xA5FF", r22["total"] == 0xA5FF + 1)
ok("and the next block is printed at the identifier's own width",
   r21["next"] == "00-FF" and r22["next"] == "1000-1FFF")

# ---- the commands are real --------------------------------------------------
head("The commands are real")

with open(os.path.join(ROOT, "bin", "omacar"), encoding="utf-8") as f:
    launcher = f.read()

steps = ima.next_steps()
ok("there is always something to suggest next", len(steps) > 0)

bad = []
for st in steps:
    parts = st["command"].split()
    if len(parts) < 2 or parts[0] != "omacar":
        bad.append(st["command"])
        continue
    # The subcommand has to appear as a case label in the launcher. A screen
    # that prints a command bin/omacar does not have is worse than one that
    # prints nothing at all.
    if f"\n  {parts[1]})" not in launcher and f"| {parts[1]})" not in launcher \
            and f"\n  {parts[1]} " not in launcher:
        bad.append(st["command"])
ok("every suggested command names a subcommand bin/omacar actually has",
   not bad)
if bad:
    for b in bad:
        print("        " + b)

ok("every step says what it costs", all(st.get("cost") for st in steps))
ok("every step carries its own safety line", all(st.get("safety") for st in steps))
ok("the untried service is the first thing suggested",
   steps[0]["id"] == "service21")

# ---- the simulator is owned up to ------------------------------------------
head("Simulator honesty")

import sqlite3  # noqa: E402
os.makedirs(garage.GARAGE, exist_ok=True)
db = sqlite3.connect(os.path.join(garage.GARAGE, "TESTCAR.db"))
db.execute("CREATE TABLE vehicle (k TEXT PRIMARY KEY, v TEXT)")
db.execute("CREATE TABLE faults (code TEXT, status TEXT)")
db.execute("INSERT INTO vehicle VALUES ('simulated', 'true')")
db.execute("INSERT INTO vehicle VALUES ('name', '\"Bench\"')")
db.commit()
db.close()
ok("a simulated vehicle record is reported as simulated",
   ima.summary()["vehicle"]["simulated"] is True)

db = sqlite3.connect(os.path.join(garage.GARAGE, "TESTCAR.db"))
db.execute("UPDATE vehicle SET v='false' WHERE k='simulated'")
db.commit()
db.close()
ok("and a real one is not", ima.summary()["vehicle"]["simulated"] is False)

# ---- it must import without the serial library ------------------------------
head("The web server can import it")

connect.STATE = _real_state
frontier.STATE_DIR = _real_frontier
garage.STATE, garage.GARAGE, garage.POINTER = _real_garage

# The server runs under the SYSTEM interpreter, where pyserial is not
# installed. discover.py learned this the expensive way -- a module-level
# import of elm killed GET /api/learned outright. ima.py must never acquire
# one, and the only way to prove that is to import it somewhere pyserial is
# not.
py = shutil.which("python3")
if py:
    r = subprocess.run(
        [py, "-c",
         "import sys; sys.path.insert(0, %r); import ima; "
         "assert 'serial' not in sys.modules; "
         "s = ima.summary(); assert isinstance(s['quantities'], list); "
         "print('ok')" % os.path.join(ROOT, "lib")],
        capture_output=True, text=True)
    ok("system python imports ima and builds a summary without pyserial",
       r.returncode == 0 and "ok" in r.stdout)
    if r.returncode != 0:
        print("        " + (r.stderr.strip().splitlines() or ["?"])[-1])
else:
    print("   ..    no system python3 on PATH; skipping the import check")

head("Plugging the car in has to light this screen up")

# The point of adding HYBRID_BATTERY_REMAINING to telemetry.SLOW is that the
# next drive fills this row on its own. That only works if the register reads
# the daemon's live.json and PROMOTES the quantity -- and the failure would be
# silent, because an undiscovered row and a row nobody wired up look identical.
_soc_state = os.path.join(tmp, "soc-state")
os.makedirs(_soc_state, exist_ok=True)
_prev_state = connect.STATE
connect.STATE = _soc_state


def _pack(live):
    p = os.path.join(_soc_state, "live.json")
    if live is None:
        if os.path.exists(p):
            os.remove(p)
    else:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(live, f)
    for q in ima.quantities():
        if q["id"] == "pack_remaining":
            return q
    return {}


_now = time.time()
_SUPP = ["HYBRID_BATTERY_REMAINING"]

_q = _pack({"connected": True, "t": _now, "supported": _SUPP,
            "values": {"RPM": 1500, "HYBRID_BATTERY_REMAINING": 62.4}})
ok("a car that is plugged in and answering reads measured",
   _q.get("state") == ima.MEASURED)
ok("and carries the real number, not a placeholder", _q.get("value") == 62.4)
ok("and says where it came from", _q.get("source") == "live.json")

_q = _pack({"connected": False, "t": _now - 3600, "supported": _SUPP,
            "values": {"HYBRID_BATTERY_REMAINING": 62.4}})
ok("an hour-old reading is demoted to stale, not shown as now",
   _q.get("state") == ima.STALE)

_q = _pack({"connected": True, "t": _now, "supported": _SUPP,
            "values": {"RPM": 1500}})
ok("supported but never answered stays undiscovered",
   _q.get("state") == ima.UNDISCOVERED and _q.get("value") is None)
# The advice used to say "it is in no poll tier and there is no samples column
# to store it in". Both were true when written and both are now false.
ok("and the advice does not send somebody to build what already exists",
   "no poll tier" not in (_q.get("next") or ""))
ok("it points at the drive that will answer it instead",
   "SLOW" in (_q.get("next") or "") and "soc" in (_q.get("next") or ""))

_q = _pack(None)
ok("with no live.json at all it is undiscovered and empty",
   _q.get("state") == ima.UNDISCOVERED and _q.get("value") is None)

connect.STATE = _prev_state

shutil.rmtree(tmp, ignore_errors=True)

print(f"\n  {len(PASS)} passed, {len(FAIL)} failed\n")
sys.exit(1 if FAIL else 0)
