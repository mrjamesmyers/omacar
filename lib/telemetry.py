"""Shared telemetry: what to poll, how often, and how to score efficiency.

The efficiency term is what drives the ambient ring's colour, so it had
better mean something. Where the ECU gives us MAF and speed we compute real
instantaneous fuel economy; only when it does not do we fall back to a
heuristic, and we say which one we used.
"""

# Tiered polling. Everything at gauge rate just floods the bus and makes
# every reading late — the slow group genuinely only drifts.
FAST = ["RPM", "SPEED", "ENGINE_LOAD", "THROTTLE_POS"]
MID = ["SHORT_FUEL_TRIM_1", "LONG_FUEL_TRIM_1", "TIMING_ADVANCE", "MAF"]
# THESE THREE ARE NOW THE FALLBACK, NOT THE ANSWER.
#
# They are what a car with no profile gets, and they are shaped by one car --
# a Honda hybrid. HYBRID_BATTERY_REMAINING in the slow tier is useless on a
# diesel Golf and it costs a request every cycle to find that out.
#
# tiers() below asks the vehicle's profile first and falls back to exactly
# these, so nothing changes for a car nobody has written a profile for. That
# is deliberate: a framework that requires a profile before it works at all
# is a framework nobody adopts.
SLOW = ["COOLANT_TEMP", "INTAKE_TEMP", "RUN_TIME", "FUEL_LEVEL",
        "CONTROL_MODULE_VOLTAGE", "AMBIANT_AIR_TEMP",
        # Mode 01 PID 0x5B. The CR-Z lists this in its own support bitmap and
        # nothing has ever asked for it, so a hybrid's single most interesting
        # number has been one line away this whole time.
        #
        # It goes in SLOW deliberately. Pack charge moves on the timescale of a
        # hill, not a gear change, and the fast tier is the one competing with
        # RPM and speed for a serial link that is the real bottleneck here.
        #
        # A PID appearing in the support bitmap is a claim by the ECU, not a
        # promise: plenty of modules advertise a PID and then return a constant.
        # Until a reading actually varies on this car it stays a candidate --
        # nothing downstream may draw a gauge from it. See lib/ima.py.
        "HYBRID_BATTERY_REMAINING"]

_TIER_FALLBACK = {"fast": FAST, "mid": MID, "slow": SLOW}


def tiers(vin=None, slug=None):
    """What to poll on THIS car: {"fast": [...], "mid": [...], "slow": [...]}.

    Resolution order is profile-by-slug, profile-by-VIN, then the constants
    above. Every step is allowed to fail quietly, because the failure mode
    that matters is not "no profile" -- it is a daemon that will not start
    because a profile is malformed. Polling the generic set is always a
    correct thing to do; refusing to poll never is.
    """
    doc = None
    try:
        import profile as profilelib
        if not slug and vin:
            slug = profilelib.for_vin(vin)
        if slug:
            doc, _p = profilelib.load(slug)
    except Exception:
        doc = None
    out = {}
    for tier in ("fast", "mid", "slow"):
        names = None
        if doc:
            try:
                names = profilelib.poll(doc, tier, default=None)
            except Exception:
                names = None
        out[tier] = list(names) if names else list(_TIER_FALLBACK[tier])
    return out

# Gasoline: stoichiometric air/fuel by mass, and fuel density.
AFR_GASOLINE = 14.7
FUEL_DENSITY_G_PER_L = 745.0

# 2015 CR-Z, manual, real-world. The band the ring reads against: at or below
# GOOD is full green, at or above POOR is full blue.
LPHK_GOOD = 4.5
LPHK_POOR = 9.5


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def fuel_rate_lph(maf_gps):
    """Instantaneous fuel burn, litres per hour, from mass air flow."""
    if maf_gps is None or maf_gps <= 0:
        return None
    grams_fuel_per_s = maf_gps / AFR_GASOLINE
    return grams_fuel_per_s * 3600.0 / FUEL_DENSITY_G_PER_L


def economy(maf_gps, speed_kph):
    """(L/100km, L/h). L/100km is None when stopped — it is undefined there."""
    lph = fuel_rate_lph(maf_gps)
    if lph is None:
        return None, None
    if not speed_kph or speed_kph < 3:
        return None, lph
    return lph / speed_kph * 100.0, lph


def efficiency(sample):
    """0 (thirsty) .. 1 (frugal), plus how we got there.

    Returns (value, basis) where basis is 'economy', 'load' or 'idle'.
    """
    lphk, lph = economy(sample.get("MAF"), sample.get("SPEED"))

    if lphk is not None:
        span = LPHK_POOR - LPHK_GOOD
        return clamp(1.0 - (lphk - LPHK_GOOD) / span), "economy"

    # Stopped but running: idling is neither efficient nor a crime. Anchor
    # low-ish so the ring settles blue at a standstill rather than lying green.
    speed = sample.get("SPEED") or 0
    if speed < 3:
        return 0.25, "idle"

    # No MAF on this ECU: fall back to load and throttle. Coarser, and the
    # UI says so rather than pretending it measured something.
    load = sample.get("ENGINE_LOAD")
    throttle = sample.get("THROTTLE_POS")
    if load is None and throttle is None:
        return 0.5, "load"
    parts = [1.0 - clamp((v or 0) / 100.0) for v in (load, throttle) if v is not None]
    return clamp(sum(parts) / len(parts)), "load"
