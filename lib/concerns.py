"""Snapshots, trends, and the things worth worrying about.

Three ideas, one file, because they are the same idea at three timescales.

**A snapshot** is now, frozen. When something looks wrong you want the whole
state — every live value, every code, every Mode 06 margin, the trims, the
odometer — as it was at that moment, not as it is by the time you get round to
looking. The watchdog takes one automatically whenever a rule fires, so the
evidence for an alert is captured before the condition clears itself.

**A trend** is one measurement over months. A scan tool tells you a test is
passing. It is passing *today*; the useful question is for how much longer, and
that needs the same measurement taken repeatedly and a line drawn through it.

**A concern** is a trend that is going somewhere bad, with an estimate of when
it arrives. That is the whole point: a catalyst monitor at 95% of its limit and
climbing a point a month is a failure with a date on it, and knowing the date is
the difference between planning a repair and being stranded by one.

The arithmetic is deliberately plain — least squares on the raw points, no
smoothing, no seasonality model. A trend that needs a clever fit to be visible
is a trend that is not there, and a projection dressed up in statistics it
cannot support is worse than no projection.
"""

import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import records  # noqa: E402

# A fit needs enough points to be worth drawing, and enough span to mean
# anything. Three readings a week apart is not a trend.
MIN_POINTS = 6
MIN_SPAN_DAYS = 21

# How far ahead a projection is allowed to claim. Past this the line is
# arithmetic rather than a forecast, and it says "beyond a year" instead.
MAX_PROJECT_DAYS = 730


# ---- snapshots --------------------------------------------------------------

def capture(reason="manual", label=None, note=None, extra=None):
    """Freeze the whole state, and file it.

    Kept as one JSON payload rather than rows in a dozen tables: a snapshot is
    read as a unit, compared as a unit, and must not change shape when the
    tables around it do.
    """
    s = records.snapshot()
    v = (s["live"].get("values") or {})
    shot = {
        "reason": reason,
        "at": int(time.time()),
        "vehicle": s.get("name"),
        "vin": (s.get("vehicle") or {}).get("vin"),
        "odometer": s.get("odometer"),
        "status": s.get("status"),
        "connected": s.get("connected"),
        "live": {k: v.get(k) for k in (
            "RPM", "SPEED", "ENGINE_LOAD", "THROTTLE_POS", "COOLANT_TEMP",
            "INTAKE_TEMP", "AMBIANT_AIR_TEMP", "MAF", "FUEL_LEVEL",
            "CONTROL_MODULE_VOLTAGE", "SHORT_FUEL_TRIM_1", "LONG_FUEL_TRIM_1",
            "TIMING_ADVANCE", "RUN_TIME") if v.get(k) is not None},
        "economy_lphk": s["live"].get("economy_lphk"),
        "codes": [{"code": f["code"], "status": f["status"],
                   "descr": f.get("descr"), "severity": f.get("severity")}
                  for f in s.get("active_faults", [])],
        "readiness": {
            "ready": (s.get("readiness") or {}).get("ready"),
            "incomplete": [m["name"] for m in (s.get("readiness") or {}).get("monitors", [])
                           if m["supported"] and not m["complete"]],
        },
        "mode06": [{"mid": m["mid"], "name": m["name"], "value": m["value"],
                    "lo": m["lo"], "hi": m["hi"], "pass": m["pass"],
                    "headroom": m.get("headroom")}
                   for m in s.get("mode06", [])],
        "service_next": (s.get("service") or {}).get("next"),
        "note": note,
    }
    if extra:
        shot.update(extra)
    rid = records.write_record(
        "snapshot",
        label or _auto_label(shot),
        shot, odo=s.get("odometer"))
    shot["id"] = rid
    return shot


def _auto_label(shot):
    bits = []
    if shot.get("codes"):
        bits.append(f"{len(shot['codes'])} code(s)")
    live = shot.get("live") or {}
    if live.get("COOLANT_TEMP") is not None:
        bits.append(f"{live['COOLANT_TEMP']:.0f}C")
    if live.get("SPEED") is not None:
        bits.append(f"{live['SPEED']:.0f} km/h")
    return f"{shot['reason']}: " + ("  ".join(bits) if bits else "state captured")


def snapshots(n=40):
    db = records.connect()
    out = records.records(db, kind="snapshot", n=n) if db else []
    if db:
        db.close()
    return out


def compare(a, b):
    """What changed between two snapshots. The pre/post-repair question."""
    pa, pb = (a or {}).get("payload") or {}, (b or {}).get("payload") or {}
    out = {"live": {}, "codes": {"gone": [], "new": []}, "mode06": {}}
    la, lb = pa.get("live") or {}, pb.get("live") or {}
    for k in sorted(set(la) | set(lb)):
        if la.get(k) != lb.get(k):
            out["live"][k] = {"before": la.get(k), "after": lb.get(k)}
    ca = {c["code"] for c in pa.get("codes") or []}
    cb = {c["code"] for c in pb.get("codes") or []}
    out["codes"]["gone"] = sorted(ca - cb)
    out["codes"]["new"] = sorted(cb - ca)
    ma = {m["mid"]: m for m in pa.get("mode06") or []}
    mb = {m["mid"]: m for m in pb.get("mode06") or []}
    for mid in sorted(set(ma) & set(mb)):
        if ma[mid]["value"] != mb[mid]["value"]:
            out["mode06"][mid] = {"name": mb[mid]["name"],
                                  "before": ma[mid]["value"],
                                  "after": mb[mid]["value"],
                                  "hi": mb[mid].get("hi"),
                                  "lo": mb[mid].get("lo")}
    return out


# ---- fitting ----------------------------------------------------------------

def fit(points):
    """Least squares through (x, y). Returns (slope, intercept, r2) or None.

    Plain on purpose. A drift that needs smoothing to be visible is not a
    drift, and r² is carried so the caller can decline to draw a conclusion
    through a cloud.
    """
    pts = [(x, y) for x, y in points if y is not None]
    n = len(pts)
    if n < MIN_POINTS:
        return None
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for _, y in pts)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, intercept, r2


def project(slope, intercept, limit, now_x):
    """Days until the line reaches a limit, or None if it never will."""
    if slope == 0:
        return None
    x = (limit - intercept) / slope
    days = x - now_x
    if days <= 0 or days > MAX_PROJECT_DAYS:
        return None
    return days


def when(days):
    """A band rather than a date. The fit does not support a date."""
    if days is None:
        return "beyond a year"
    if days < 21:
        return "within weeks"
    if days < 75:
        return "a month or two"
    if days < 200:
        return "three to six months"
    if days < 400:
        return "within the year"
    return "a year or more out"


# ---- the concerns -----------------------------------------------------------

def _day_series(days_rows, key):
    base = None
    out = []
    for d in days_rows:
        if d.get(key) is None:
            continue
        t = datetime.strptime(d["day"], "%Y-%m-%d").timestamp() / 86400.0
        base = t if base is None else base
        out.append((t, float(d[key])))
    return out


def assess(db=None):
    """Everything trending somewhere it should not, worst first."""
    own = db is None
    db = db or records.connect()
    if db is None:
        return []
    try:
        rows = records.days(db)
        out = []
        out += _mode06_trends(db)
        out += _trim_trend(rows)
        out += _economy_trend(rows)
        out += _coolant_trend(rows)
        out += _code_recurrence(db)
        rank = {"critical": 0, "warning": 1, "info": 2}
        out.sort(key=lambda c: (rank.get(c["severity"], 3),
                                c.get("days_to_limit") or 9999))
        return out
    finally:
        if own:
            db.close()


def _mode06_trends(db):
    """A self-test margin closing. The measurement no consumer tool watches."""
    if not records.has(db, "mode06_history"):
        return []
    try:
        rows = records.rows(
            db, "SELECT mid, at, value, lo, hi FROM mode06_history ORDER BY at")
    except Exception:                                     # noqa: BLE001
        return []
    by_mid = {}
    for r in rows:
        by_mid.setdefault(r["mid"], []).append(r)
    names = {m["mid"]: m for m in records.mode06(db)}
    out = []
    for mid, series in by_mid.items():
        if len(series) < MIN_POINTS:
            continue
        span = (series[-1]["at"] - series[0]["at"]) / 86400.0
        if span < MIN_SPAN_DAYS:
            continue
        f = fit([(r["at"] / 86400.0, r["value"]) for r in series])
        if not f or f[2] < 0.35:
            continue
        slope, intercept, r2 = f
        last = series[-1]
        hi, lo = last.get("hi"), last.get("lo")
        limit = hi if hi is not None and slope > 0 else (lo if lo is not None and slope < 0 else None)
        if limit is None:
            continue
        now_x = time.time() / 86400.0
        days = project(slope, intercept, limit, now_x)
        meta = names.get(mid) or {}
        headroom = meta.get("headroom")
        if days is None and (headroom is None or headroom < 0.8):
            continue
        out.append({
            "id": "mode06:" + mid,
            "title": (meta.get("name") or mid) + " is drifting toward its limit",
            "kind": "on-board test",
            "severity": "warning" if (days or 999) < 200 else "info",
            "value": last["value"], "limit": limit,
            "unit": meta.get("unit", ""),
            "per_month": round(slope * 30, 4),
            "days_to_limit": round(days) if days else None,
            "when": when(days),
            "confidence": round(r2 * 100),
            "detail": (f"Measured {last['value']:g} against a limit of {limit:g}"
                       + (f", moving {abs(slope * 30):.3g} a month" if slope else "")
                       + "."),
            "evidence": [f"mode06.{mid}"],
            "series": [(r["at"], r["value"]) for r in series[-40:]],
        })
    return out


def _trim_trend(rows):
    """Long-term fuel trim creeping. The earliest sign of most air leaks."""
    series = _day_series(rows, "ltft_mean")
    f = fit(series)
    if not f or len(series) < MIN_POINTS:
        return []
    slope, intercept, r2 = f
    if r2 < 0.3 or abs(slope * 30) < 0.15:
        return []
    now_x = time.time() / 86400.0
    limit = 15.0 if slope > 0 else -15.0
    days = project(slope, intercept, limit, now_x)
    latest = series[-1][1]
    if abs(latest) < 4 and days is None:
        return []
    return [{
        "id": "trim",
        "title": "Long-term fuel trim is drifting "
                 + ("positive" if slope > 0 else "negative"),
        "kind": "fuelling",
        "severity": "warning" if abs(latest) > 8 or (days or 999) < 200 else "info",
        "value": round(latest, 2), "limit": limit, "unit": "%",
        "per_month": round(slope * 30, 3),
        "days_to_limit": round(days) if days else None,
        "when": when(days),
        "confidence": round(r2 * 100),
        "detail": (f"Averaged {series[0][1]:+.1f}% at the start of the record and "
                   f"{latest:+.1f}% now, moving {slope * 30:+.2f}% a month. "
                   + ("Adding fuel — a vacuum leak, a tiring front oxygen sensor "
                      "or a metering fault." if slope > 0
                      else "Taking fuel out — leaking injectors or high fuel pressure.")),
        "evidence": ["perf.by_month", "now.long_fuel_trim_pct"],
        "series": [(x * 86400, y) for x, y in series[-90:]],
    }]


def _economy_trend(rows):
    """Fuel consumption rising. Slow, unglamorous, and it costs real money."""
    series = _day_series([r for r in rows if (r.get("km") or 0) > 8], "lphk")
    f = fit(series)
    if not f or len(series) < MIN_POINTS:
        return []
    slope, intercept, r2 = f
    monthly = slope * 30
    if r2 < 0.2 or monthly <= 0.02:
        return []
    first, last = series[0][1], series[-1][1]
    change = (last - first) / first * 100 if first else 0
    if change < 6:
        return []
    return [{
        "id": "economy",
        "title": "Fuel consumption is rising",
        "kind": "economy",
        "severity": "info",
        "value": round(last, 2), "limit": None, "unit": "L/100km",
        "per_month": round(monthly, 3),
        "days_to_limit": None, "when": "",
        "confidence": round(r2 * 100),
        "detail": (f"Up {change:.0f}% across the record. Some of that is the "
                   "seasons; a step that does not come back is a fault "
                   "arriving slowly."),
        "evidence": ["perf.by_month"],
        "series": [(x * 86400, y) for x, y in series[-120:]],
    }]


def _coolant_trend(rows):
    """Peak coolant creeping up — a rad, a fan or a thermostat going slowly."""
    series = _day_series(rows, "coolant_max")
    f = fit(series)
    if not f or len(series) < MIN_POINTS:
        return []
    slope, intercept, r2 = f
    if r2 < 0.3 or slope * 30 < 0.25:
        return []
    now_x = time.time() / 86400.0
    days = project(slope, intercept, 105.0, now_x)
    return [{
        "id": "coolant",
        "title": "Peak coolant temperature is climbing",
        "kind": "cooling",
        "severity": "warning" if (days or 999) < 200 else "info",
        "value": round(series[-1][1], 1), "limit": 105.0, "unit": "°C",
        "per_month": round(slope * 30, 3),
        "days_to_limit": round(days) if days else None,
        "when": when(days),
        "confidence": round(r2 * 100),
        "detail": "The highest temperature seen each day, trending up. A "
                  "radiator silting, a fan that starts late, or a thermostat "
                  "opening slowly.",
        "evidence": ["sample_statistics.channels"],
        "series": [(x * 86400, y) for x, y in series[-120:]],
    }]


def _code_recurrence(db):
    """A code that keeps coming back is a different problem from one that set
    once — and the count is already in the record."""
    out = []
    for f in records.faults(db):
        if not f.get("active") or (f.get("count") or 0) < 4:
            continue
        span_days = ((f.get("last_seen") or 0) - (f.get("first_seen") or 0)) / 86400.0
        if span_days < 7:
            continue
        rate = f["count"] / max(1.0, span_days) * 30
        if rate < 1.0:
            continue
        out.append({
            "id": "code:" + f["code"],
            "title": f"{f['code']} keeps coming back",
            "kind": "recurring fault",
            "severity": "warning" if f.get("severity") == "critical" else "info",
            "value": round(rate, 1), "limit": None, "unit": "per month",
            "per_month": round(rate, 1),
            "days_to_limit": None, "when": "",
            "confidence": 80,
            "detail": (f"{f['descr']} — {f['count']} times over "
                       f"{span_days:.0f} days, about {rate:.1f} a month. A code "
                       "that recurs is an intermittent fault, not a one-off."),
            "evidence": [f"faults.{f['code']}"],
            "code": f["code"],
            "series": [],
        })
    return out


# ---- terminal ---------------------------------------------------------------

def main(argv):
    what = argv[0] if argv else "list"
    if what in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if what == "capture":
        shot = capture("manual", " ".join(argv[1:]) or None)
        print(f"\n  captured #{shot['id']}: {_auto_label(shot)}\n")
        return 0
    if what == "snapshots":
        for s in snapshots(20):
            print(f"  #{s['id']:<5} {time.strftime('%d %b %H:%M', time.localtime(s['at']))}"
                  f"  {s.get('label', '')}")
        return 0

    found = assess()
    print()
    if not found:
        print("  Nothing trending anywhere it should not.")
        print("  Trends need a few weeks of record before they mean anything.")
        print()
        return 0
    for c in found:
        head = {"critical": "!!", "warning": "! ", "info": "  "}[c["severity"]]
        print(f"  {head} {c['title']}")
        print(f"     {c['detail']}")
        line = []
        if c.get("limit") is not None:
            line.append(f"now {c['value']:g}{c['unit']} of {c['limit']:g}{c['unit']}")
        if c.get("days_to_limit"):
            line.append(f"reaches it in about {c['days_to_limit']} days ({c['when']})")
        elif c.get("when"):
            line.append(c["when"])
        line.append(f"{c['confidence']}% fit")
        print(f"     {'  ·  '.join(line)}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
