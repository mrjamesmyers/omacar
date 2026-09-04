"""What the car is actually speaking, and what that changes.

Everything in OmaCar was written against CAN, because every car since 2008 in
the US uses it and the development vehicle is a 2015. But the cars nobody will
spend twelve thousand dollars to diagnose are exactly the older ones, and they
are not on CAN. Supporting them is not a matter of a slower baud rate: four
things change, and getting any of them wrong looks like a car with nothing to
say.

WHAT ACTUALLY DIFFERS.

**Header shape.** `ATSH` takes three hex digits on 11-bit CAN, eight on 29-bit,
and six on J1850 and ISO 9141 -- three bytes of priority, target and source.
Sending a CAN-shaped header on ISO 9141 is not rejected loudly; the adapter
takes it and the car simply never answers.

**Framing.** ISO-TP -- the first-frame/consecutive-frame protocol that
`elm.reassemble` implements -- is a CAN construct. On J1850 and ISO 9141 a long
reply arrives as repeated lines each carrying the full header, and reassembling
them with PCI logic produces confident nonsense.

**Timing.** ISO 9141-2 runs at 10.4 kbaud against CAN's 500, and its
initialisation is a 5-baud address sequence taking two to three seconds. Our
sweep timings were tuned on CAN; applied unchanged they time out before a
healthy slow car has finished speaking.

**What is worth asking.** Service 0x22 barely exists before CAN. Manufacturer
data on these cars lives in older enhanced modes, and sweeping 0x22 across a
1998 vehicle is sixty thousand requests guaranteed to find nothing. Discovery
has to ask what the protocol can answer.

WHAT THIS FILE DOES NOT DO.

It does not claim to have been tested on a pre-CAN car. The development fleet
is a 2015 CR-Z and a 2012 Fit, both CAN. Everything here follows from the
ELM327 datasheet and the relevant ISO documents, and every entry says which
family it belongs to so somebody with a 1999 vehicle can check it rather than
trust it. `verified` is a field here for the same reason it is one in a
profile.
"""

# ELM327 protocol numbers, as reported by ATDPN.
FAMILY_CAN = "can"
FAMILY_J1850 = "j1850"
FAMILY_ISO = "iso9141"
FAMILY_KWP = "kwp2000"
FAMILY_J1939 = "j1939"

PROTOCOLS = {
    "1": {"name": "SAE J1850 PWM", "family": FAMILY_J1850, "baud": 41600,
          "header_digits": 6, "iso_tp": False, "typical": "Ford, 1996-2004",
          "default_header": "61 6A F1", "verified": False},
    "2": {"name": "SAE J1850 VPW", "family": FAMILY_J1850, "baud": 10400,
          "header_digits": 6, "iso_tp": False, "typical": "GM, 1996-2005",
          "default_header": "68 6A F1", "verified": False},
    "3": {"name": "ISO 9141-2", "family": FAMILY_ISO, "baud": 10400,
          "header_digits": 6, "iso_tp": False,
          "typical": "Chrysler, and most European and Asian, 1996-2004",
          "default_header": "68 6A F1", "verified": False},
    "4": {"name": "ISO 14230-4 KWP (5-baud init)", "family": FAMILY_KWP,
          "baud": 10400, "header_digits": 6, "iso_tp": False,
          "typical": "1996-2006", "default_header": "68 6A F1",
          "verified": False},
    "5": {"name": "ISO 14230-4 KWP (fast init)", "family": FAMILY_KWP,
          "baud": 10400, "header_digits": 6, "iso_tp": False,
          "typical": "1996-2006", "default_header": "68 6A F1",
          "verified": False},
    "6": {"name": "ISO 15765-4 CAN 11/500", "family": FAMILY_CAN, "baud": 500000,
          "header_digits": 3, "iso_tp": True, "typical": "most cars since 2008",
          "default_header": "7DF", "verified": True},
    "7": {"name": "ISO 15765-4 CAN 29/500", "family": FAMILY_CAN, "baud": 500000,
          "header_digits": 8, "iso_tp": True, "typical": "Honda, and others",
          "default_header": "18DB33F1", "verified": True},
    "8": {"name": "ISO 15765-4 CAN 11/250", "family": FAMILY_CAN, "baud": 250000,
          "header_digits": 3, "iso_tp": True, "typical": "uncommon on cars",
          "default_header": "7DF", "verified": False},
    "9": {"name": "ISO 15765-4 CAN 29/250", "family": FAMILY_CAN, "baud": 250000,
          "header_digits": 8, "iso_tp": True, "typical": "uncommon on cars",
          "default_header": "18DB33F1", "verified": False},
    "A": {"name": "SAE J1939 CAN 29/250", "family": FAMILY_J1939, "baud": 250000,
          "header_digits": 8, "iso_tp": True,
          "typical": "heavy trucks and buses", "default_header": "18EAFFF9",
          "verified": False},
}


def describe(dpn):
    """Whatever ATDPN said, as something we can reason about.

    ATDPN answers with the protocol number, sometimes prefixed with 'A' when
    it was reached by auto-search ('A6' rather than '6'). Stripping that is not
    cosmetic: 'A6' is not a key in the table, and a lookup miss would silently
    fall back to CAN assumptions on a car that is not on CAN.
    """
    if not dpn:
        return None
    s = str(dpn).strip().upper()
    if s.startswith("A") and len(s) > 1:
        s = s[1:]
    return PROTOCOLS.get(s)


def is_can(dpn):
    p = describe(dpn)
    return bool(p and p["family"] in (FAMILY_CAN, FAMILY_J1939))


def uses_iso_tp(dpn):
    p = describe(dpn)
    return bool(p and p["iso_tp"])


def broadcast(dpn, fallback="7DF"):
    """The functional 'ask every module' header for this protocol.

    Every protocol entry already carries one; nothing was reading it. Callers
    hardcoded "07DF", which is the 11-bit CAN broadcast and the wrong SHAPE on
    a 29-bit car -- so header_ok() correctly refused it and `omacar dtc` died
    with a traceback on the one car this project was built for. The right
    answer was in the table the whole time.
    """
    p = describe(dpn)
    h = (p or {}).get("default_header") or fallback
    return h.replace(" ", "")


def header_ok(dpn, header):
    """Is this header the right shape for this protocol?

    Returns (ok, detail). A wrong-shaped header is the failure that looks most
    like a dead car: the adapter accepts it and nothing ever answers.
    """
    p = describe(dpn)
    if not p:
        return True, ""          # unknown protocol: not our place to refuse
    clean = (header or "").replace(" ", "")
    want = p["header_digits"]
    if len(clean) != want:
        return False, (f"{p['name']} wants a {want}-digit header; "
                       f"{header!r} has {len(clean)}")
    return True, ""


# Sweep pacing. CAN can be hammered; a 10.4 kbaud line cannot, and the ELM's
# own timeout has to be long enough for a slow car to finish a reply.
def pacing(dpn):
    p = describe(dpn)
    if not p:
        return {"delay": 0.06, "timeout": 5.0, "atst": None}
    if p["family"] == FAMILY_CAN:
        return {"delay": 0.02, "timeout": 5.0, "atst": "20"}
    if p["baud"] >= 41000:            # J1850 PWM
        return {"delay": 0.08, "timeout": 8.0, "atst": "40"}
    # The slow lines: ISO 9141-2, KWP, J1850 VPW.
    return {"delay": 0.15, "timeout": 12.0, "atst": "80"}


def discovery_services(dpn):
    """Which services are worth sweeping on this protocol, and why.

    Sweeping UDS 0x22 across a 1998 car is sixty thousand requests that cannot
    succeed, and a tool that does it looks broken rather than thorough.
    """
    p = describe(dpn)
    if not p:
        return [(0x22, "UDS read-by-identifier")]
    if p["family"] in (FAMILY_CAN, FAMILY_J1939):
        return [(0x22, "UDS read-by-identifier"),
                (0x21, "older manufacturer read")]
    if p["family"] == FAMILY_KWP:
        # KWP2000 has readDataByLocalIdentifier, a single-byte id.
        return [(0x21, "KWP read-by-local-identifier"),
                (0x22, "KWP read-by-common-identifier")]
    # J1850 and ISO 9141: enhanced data is mode 0x22 on a few makes and
    # manufacturer-defined elsewhere. 0x21 is the common one.
    return [(0x21, "manufacturer enhanced read")]


def id_width(dpn, service):
    """How many hex digits the identifier takes for this service.

    0x21 on the older protocols is a ONE-byte local identifier, not the
    two-byte DID that 0x22 uses. Sweeping it with four digits asks 65536
    questions where 256 exist, and every one of them is malformed.
    """
    if service == 0x22:
        return 4
    if service == 0x21:
        return 2
    return 4


def summary(dpn):
    p = describe(dpn)
    if not p:
        return f"unknown protocol {dpn!r}"
    seal = "" if p["verified"] else "  (untested by this project)"
    return (f"{p['name']} — {p['typical']}, {p['baud']} baud, "
            f"{p['header_digits']}-digit headers, "
            f"{'ISO-TP' if p['iso_tp'] else 'no ISO-TP'}{seal}")
