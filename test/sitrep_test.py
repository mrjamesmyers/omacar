#!/usr/bin/env python3
"""The sitrep, and the promise that it does not say who you are.

Run directly. Touches no real state: XDG_STATE_HOME and XDG_CONFIG_HOME are
pointed at a temporary directory BEFORE the modules are imported, because both
of them resolve their paths at import time and a test that writes over
somebody's real alert feed is not a test.
"""
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="omacar-sitrep-test-")
os.environ["XDG_STATE_HOME"] = os.path.join(_TMP, "state")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "config")
os.environ["OMACAR_STATE"] = os.path.join(_TMP, "state", "omacar")
os.makedirs(os.environ["OMACAR_STATE"], exist_ok=True)
os.makedirs(os.path.join(_TMP, "config", "omarchy"), exist_ok=True)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "lib"))

import deliver  # noqa: E402
import sitrep  # noqa: E402

PASS = FAIL = 0


def head(title):
    print(f"\n  {title}\n")


def ok(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"   ok   {label}")
    else:
        FAIL += 1
        print(f"   FAIL  {label}")


# The car this project actually runs on, so a leak in a test looks like a leak.
CAR = {
    "year": 2015, "make": "Honda", "model": "CR-Z",
    "vin": "JHMZF1D44FS001835",
    "plate": "JRMYERS",
    "driver": "James",
    "owner": "James",
    "title": "James' 2015 Honda CR-Z",
    "name": "2015 Honda CR-Z",
    "odometer": 305834.2,
}

REP = {
    "at": 1788400000, "since": 1788313600, "car": dict(CAR),
    "driving": {"km": 100.0, "minutes": 88, "top": 145.0, "sessions": 2},
    "alerts": [{"kind": "trip", "title": "Trip finished",
                "body": "JRMYERS drove 62.1 mi", "urgency": "low",
                "at": 1788399000}],
    "concerns": [{"id": "ltft_drift", "title": "Fuel trim climbing",
                  "detail": "JHMZF1D44FS001835 long-term trim +1.2%/month",
                  "headroom": 0.55}],
}

head("What a redacted sitrep is allowed to say")

r = sitrep.redact(REP)
blob = json.dumps(r)

for field, value in (("VIN", CAR["vin"]), ("plate", CAR["plate"]),
                     ("owner", CAR["title"]), ("odometer", "305834")):
    ok(f"the {field} is gone", value not in blob)

ok("but the car is still recognisable to its owner",
   r["car"].get("make") == "Honda" and r["car"].get("model") == "CR-Z"
   and r["car"].get("year") == 2015)

# The allowlist is the whole design. A denylist would pass this silently.
head("Redaction is an allowlist, not a denylist")

sneaky = dict(REP)
sneaky["car"] = dict(CAR)
sneaky["car"]["home_address"] = "12 Somewhere Lane"
sneaky["car"]["insurance_policy"] = "POL-88213"
out = json.dumps(sitrep.redact(sneaky))
ok("a field nobody thought about does not leak",
   "Somewhere Lane" not in out and "POL-88213" not in out)
ok("even though it was on the vehicle record",
   "home_address" in json.dumps(sneaky))

head("Identifiers quoted inside generated text")

# watch.py and concerns.py write prose, and prose can quote anything.
ok("a plate inside an alert body is scrubbed",
   "JRMYERS" not in json.dumps(r["alerts"]))
ok("a VIN inside a concern detail is scrubbed",
   "JHMZF1D44FS001835" not in json.dumps(r["concerns"]))
ok("and the sentence still reads",
   "your car" in json.dumps(r["alerts"]) + json.dumps(r["concerns"]))
ok("the original is not mutated",
   REP["car"]["vin"] == CAR["vin"] and "JRMYERS" in REP["alerts"][0]["body"])

head("The defaults are the private ones")

cfg = sitrep.load()
ok("it is off until somebody turns it on", cfg["enabled"] is False)
ok("and summary, not full", cfg["detail"] == "summary")
ok("with no channels configured", cfg["channels"] == [])

with open(sitrep.CONFIG, "w", encoding="utf-8") as f:
    f.write("{ this is not json")
ok("a hand-mangled config does not raise", sitrep.load()["detail"] == "summary")
with open(sitrep.CONFIG, "w", encoding="utf-8") as f:
    json.dump({"enabled": True, "detail": "wildly-invalid"}, f)
ok("and an unknown detail level falls back to summary",
   sitrep.load()["detail"] == "summary")
os.remove(sitrep.CONFIG)

head("Rendering never reaches the wire with an identifier")

subj = sitrep.subject(r)
body = sitrep.render(r, detail="summary")
ok("the body carries no VIN or plate",
   CAR["vin"] not in body and CAR["plate"] not in body)
ok("nor the owner's name", "James" not in body and "James" not in subj)
ok("it says which car it is about", "Honda" in body and "CR-Z" in body)
ok("and says plainly what it withheld",
   "no VIN, plate or name" in body)

full = sitrep.render(REP, detail="full")
ok("opt-in full detail does include them, on purpose",
   CAR["vin"] in full and CAR["plate"] in full)

head("Not crying wolf")

st = {}
fresh, held = sitrep.news(REP, st=st, now=1788400000)
ok("a concern nobody has been told about is news", len(fresh) == 1)

st = sitrep.remember(fresh, st=st, now=1788400000)
fresh2, held2 = sitrep.news(REP, st=st, now=1788400000 + 86400)
ok("the same concern tomorrow is not news again", fresh2 == [] and len(held2) == 1)

fresh3, _ = sitrep.news(REP, st=st, now=1788400000 + sitrep.REPEAT_AFTER + 10)
ok("but it is raised again after a month", len(fresh3) == 1)

worse = json.loads(json.dumps(REP))
worse["concerns"][0]["headroom"] = 0.55 + sitrep.WORSE_BY + 0.01
fresh4, _ = sitrep.news(worse, st=st, now=1788400000 + 3600)
ok("and immediately if it gets materially worse", len(fresh4) == 1)

nudge = json.loads(json.dumps(REP))
nudge["concerns"][0]["headroom"] = 0.56
fresh5, _ = sitrep.news(nudge, st=st, now=1788400000 + 3600)
ok("a small move stays quiet", fresh5 == [])

head("Credentials")

ok("the config file is never a source of the password",
   "smtp_password" not in open(
       os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "lib", "sitrep.py"), encoding="utf-8").read())

os.makedirs(os.path.dirname(deliver.SECRETS), exist_ok=True)
with open(deliver.SECRETS, "w", encoding="utf-8") as f:
    json.dump({"smtp_password": "hunter2"}, f)

os.chmod(deliver.SECRETS, 0o644)
refused = None
try:
    deliver.secret("smtp_password", "NOPE_NOT_SET")
except deliver.Refused as e:
    refused = str(e)
ok("a world-readable secret file refuses rather than warns", refused is not None)
ok("and the message says how to fix it", refused and "chmod 600" in refused)

os.chmod(deliver.SECRETS, 0o600)
ok("at 0600 it is read", deliver.secret("smtp_password", "NOPE") == "hunter2")

os.environ["OMACAR_SMTP_PASSWORD"] = "from-env"
ok("the environment wins over the file",
   deliver.secret("smtp_password", "OMACAR_SMTP_PASSWORD") == "from-env")
del os.environ["OMACAR_SMTP_PASSWORD"]

ok("an error carrying the password has it removed",
   "hunter2" not in deliver._scrub("535 auth failed for hunter2", "hunter2"))
ok("and short strings are not scrubbed into nonsense",
   deliver._scrub("bad login", "ab") == "bad login")

head("Sending refuses rather than sending badly")

res = deliver.send("s", "b", [{"kind": "smtp", "host": "", "to": "a@b.c"}])
ok("an incomplete smtp channel is refused, not attempted",
   res and res[0]["ok"] is False and "host" in res[0]["error"])

res = deliver.send("s", "b", [{"kind": "carrier-pigeon"}])
ok("an unknown channel kind is reported, not ignored",
   res and res[0]["ok"] is False and "no such channel" in res[0]["error"])

res = deliver.send("s", "b", [{"kind": "ntfy", "enabled": False}])
ok("a disabled channel is skipped silently", res == [])

res = deliver.send("s", "b", [{"kind": "ntfy"}])
ok("ntfy with no destination is refused", res and res[0]["ok"] is False)

shutil.rmtree(_TMP, ignore_errors=True)
print(f"\n  {PASS} passed, {FAIL} failed\n")
sys.exit(1 if FAIL else 0)
