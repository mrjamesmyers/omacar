#!/usr/bin/env python3
"""Prospector logic tests against a scripted fake ECU.

The emulator answers generic OBD-II but not Honda's manufacturer services, so
the *positive* path — finding a responder and spotting which bytes move —
cannot be exercised on the bench. A fake ECU can, and it is where the logic
that matters actually lives.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))

import elm as elmlib      # noqa: E402
import prospect           # noqa: E402

fails = 0


def check(label, expected, actual):
    global fails
    if expected == actual:
        print(f"   ok  {label}")
    else:
        print(f" FAIL  {label}\n         expected {expected!r}\n         got      {actual!r}")
        fails += 1


class FakeEcu:
    """Answers 2101 on 07E2 with one moving byte and one constant byte."""

    def __init__(self):
        self.header = None
        self.tick = 0
        self.writes_attempted = []

    def set_header(self, h):
        self.header = h

    def request(self, payload):
        service = int(payload[:2], 16)
        if service not in elmlib.READ_ONLY_SERVICES:
            self.writes_attempted.append(payload)
            raise elmlib.WriteAttempted(payload)
        if payload == "010D":
            return ["7E8410D00"]                      # stopped
        if self.header == "07E2" and payload == "2101":
            self.tick += 1
            soc = 0x40 + self.tick                    # moves
            return [f"7EA046101{soc:02X}5A"]          # 61 01 <soc> 5A
        if self.header == "07E2" and payload == "2102":
            return ["7EA0461027F7F"]                  # answers, never changes
        if self.header == "07E0" and payload == "2101":
            return ["7E8037F2131"]                    # requestOutOfRange
        return []                                     # silence


print("\n  OmaCar prospector logic\n")

# --- classification ---------------------------------------------------------
check("positive response recognised", "positive",
      elmlib.classify(["7EA0461014A5A"], 0x21)[0])
check("negative response names the NRC", "requestOutOfRange",
      elmlib.classify(["7E8037F2131"], 0x21)[1])
check("silence is distinct from a negative", "silent",
      elmlib.classify([], 0x21)[0])

# --- read-only enforcement --------------------------------------------------
for svc in (0x2E, 0x2F, 0x31, 0x11, 0x14, 0x85):
    if svc in elmlib.READ_ONLY_SERVICES:
        print(f" FAIL  service 0x{svc:02X} must not be allowed")
        fails += 1
print("   ok  every state-changing service is refused")

ecu = FakeEcu()
try:
    ecu.request("2E0100")
    print(" FAIL  a write request should raise")
    fails += 1
except elmlib.WriteAttempted:
    print("   ok  a write request raises before it reaches the bus")

# --- the moving gate --------------------------------------------------------
check("stationary car reads as not moving", False, prospect.moving(ecu))


class MovingEcu(FakeEcu):
    def request(self, payload):
        if payload == "010D":
            return ["7E8410D2A"]                      # 42 km/h
        return super().request(payload)


check("moving car is detected", True, prospect.moving(MovingEcu()))

# --- sweep ------------------------------------------------------------------
noop = lambda *a: None
ecu = FakeEcu()
found = prospect.sweep(ecu, ["07E0", "07E2"], 0x21, [0x01, 0x02, 0x03], 0, noop)
check("sweep finds only the responders", 2, len(found))
check("responders carry their header", {"07E2"}, {f["header"] for f in found})

# --- variance detection -----------------------------------------------------
prospect.resample(ecu, found, 5, 0, noop)
by_req = {f["request"]: f for f in found}
check("a byte that moves is flagged", [0], by_req["2101"]["varying"])
check("a byte that never moves is not flagged", [], by_req["2102"]["varying"])

# --- header pruning ---------------------------------------------------------
silent = FakeEcu()
silent.request = lambda p: [] if p != "010D" else ["7E8410D00"]
found2 = prospect.sweep(silent, ["07E5"], 0x21, list(range(0, 200)), 0, noop)
check("a header that never answers is abandoned early", 0, len(found2))

print()
if fails:
    print(f"  {fails} failed\n")
    sys.exit(1)
print("  all good\n")
