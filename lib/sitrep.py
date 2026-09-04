"""The daily sitrep: what your car did, and what is drifting.

WHY THIS FILE EXISTS AT ALL, GIVEN EVERYTHING ELSE ALREADY DOES THE WORK.

The analysis was already here. watch.py has fired debounced, hysteretic rules
at a running car since the beginning; concerns.py already draws a line through
months of Mode 06 margins and tells you the DATE a limit gets reached; ai.py
already reads the whole evidence bundle with the local `claude` CLI and drops
any finding that cites something not in it.

All of that shouts into a laptop that is sitting in a car in a car park.

So this file does exactly one new thing: it decides what is worth telling
somebody who is not looking at the screen, and it does that carefully, because
the failure mode of every alerting system ever built is that it cries wolf
until people stop reading it. Everything below about dedupe, escalation and
quiet days is aimed at that one failure and nothing else.

THE PRIVACY RULE, WHICH IS NOT NEGOTIABLE.

This is the first thing in OmaCar that leaves the machine. Everything else --
the database, the themes, the drive logs, even the AI, which shells out to a
CLI running locally -- stays on the laptop by construction. A sitrep does not.
It goes to a mail server, and from there to an inbox, and it is retained by
both.

So the default sitrep carries NO identifiers. Not the VIN, not the plate, not
the driver's name, not the odometer, and not the vehicle title (which is built
from the owner's name and so leaks it). What is left -- "your 2015 Honda CR-Z
drove 62 miles and its long-term fuel trim is climbing" -- is useful to the
person who owns it and is not much use to anybody else who reads the mail.

`redact()` below is the whole guarantee, so it works by ALLOWING a known set of
fields through rather than by removing a known set. A denylist silently leaks
every field somebody adds later; an allowlist silently drops them, which is the
failure you want. It has its own tests for exactly this reason.

Full detail is available, because sometimes the whole point is to forward the
thing to a mechanic. It is opt-in, per send, and never the default.
"""

import json
import os
import time

import concerns
import records

CONFIG = os.path.join(os.path.expanduser(
    os.environ.get("XDG_CONFIG_HOME", "~/.config")),
    "omarchy", "omacar-sitrep.json")

STATE = os.path.join(records.STATE, "sitrep.json")

# What a sitrep is allowed to say about the car when it is redacted. An
# ALLOWLIST, deliberately -- see the module docstring. Adding a field to the
# vehicle record must not silently start mailing it out.
CAR_ALLOWED = ("year", "make", "model")

# How long a standing concern stays quiet after it has been reported once.
# A fuel trim that will cross its limit in seven months does not become news
# again tomorrow, and mailing it every morning is how somebody learns to
# archive these unread.
REPEAT_AFTER = 30 * 86400

# ...unless it got materially worse. Expressed as a fraction of the way to the
# limit, so "it moved a bit" stays quiet and "it moved a lot" speaks up.
WORSE_BY = 0.15

DEFAULTS = {
    "enabled": False,
    # summary | full. The default is the one that cannot leak who you are.
    "detail": "summary",
    "daily_at": "20:00",
    # Anything at or above this urgency goes out the moment it is filed rather
    # than waiting for the digest.
    "urgent_now": True,
    "channels": [],
}


def load():
    """Config, or the defaults. Never raises on a hand-edited file."""
    out = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return out
    if not isinstance(raw, dict):
        return out
    for k in DEFAULTS:
        if k in raw:
            out[k] = raw[k]
    out["enabled"] = bool(out["enabled"])
    out["detail"] = "full" if str(out.get("detail")) == "full" else "summary"
    if not isinstance(out.get("channels"), list):
        out["channels"] = []
    return out


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATE)


# ---------------------------------------------------------------- redaction

def redact(rep):
    """A sitrep with nothing in it that says whose car this is.

    Allowlist, not denylist. If you are reading this because a field leaked,
    the bug is that something was added to the ALLOWED tuple, not that
    something was forgotten from a removal list -- which is the point.
    """
    out = dict(rep)
    car = rep.get("car") or {}
    out["car"] = {k: car[k] for k in CAR_ALLOWED if car.get(k)}
    # Alerts and concerns are generated text and can quote anything, so the
    # car's own identifying strings are scrubbed out of them by value. A body
    # that happens to contain the plate is exactly the leak this catches.
    secrets = [str(car.get(k) or "") for k in
               ("vin", "plate", "driver", "owner", "title", "name")]
    secrets = [s for s in secrets if len(s) >= 4]

    def clean(text):
        s = str(text or "")
        for bad in secrets:
            if bad and bad in s:
                s = s.replace(bad, "your car")
        return s

    for key in ("alerts", "concerns"):
        items = []
        for it in (rep.get(key) or []):
            c = dict(it)
            for f in ("title", "body", "detail", "note"):
                if f in c:
                    c[f] = clean(c[f])
            items.append(c)
        out[key] = items
    out["redacted"] = True
    return out


# ---------------------------------------------------------------- gathering

def _alerts_since(since):
    try:
        with open(os.path.join(records.STATE, "alerts.json"),
                  encoding="utf-8") as f:
            feed = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for a in (feed.get("alerts") or []):
        if not isinstance(a, dict):
            continue
        if float(a.get("at") or 0) >= since:
            out.append(a)
    return out


def _driving_since(since, db=None):
    """Distance and time from the sample stream, not from a trips table.

    The trips table is written by watch.py and is the tidier source, but it is
    also the one that was empty on a real car for months while the simulator
    filled it. Integrating the samples is slower and cannot be wrong about
    whether the car actually moved.
    """
    own = db is None
    if own:
        import sqlite3
        db = sqlite3.connect(records.DB)
    try:
        rows = db.execute(
            "SELECT t, speed FROM samples WHERE t >= ? AND speed IS NOT NULL "
            "ORDER BY t", (since,)).fetchall()
    except Exception:
        return {"km": 0.0, "minutes": 0, "top": 0.0, "sessions": 0}
    finally:
        if own:
            db.close()

    km = 0.0
    moving = 0.0
    top = 0.0
    sessions = 0
    prev_t = None
    for t, sp in rows:
        sp = float(sp or 0.0)
        top = max(top, sp)
        if prev_t is not None:
            dt = t - prev_t
            # A gap longer than a minute is the car being switched off, not a
            # slow sample. Counting it as driving would invent hours.
            if dt > 60:
                sessions += 1
            elif dt > 0:
                km += sp * dt / 3600.0
                if sp > 1:
                    moving += dt
        prev_t = t
    if rows:
        sessions += 1
    return {"km": round(km, 2), "minutes": int(moving / 60),
            "top": round(top, 1), "sessions": sessions}


def gather(since=None, db=None):
    """Everything a sitrep might say, unredacted. Render decides what leaves."""
    now = time.time()
    if since is None:
        since = now - 86400
    car = {}
    try:
        car = records.vehicle() or {}
    except Exception:
        car = {}
    try:
        assessed = concerns.assess(db=db) or {}
    except Exception:
        assessed = {}
    items = assessed.get("concerns") if isinstance(assessed, dict) else assessed
    return {
        "at": int(now),
        "since": int(since),
        "car": car,
        "driving": _driving_since(since, db=db),
        "alerts": _alerts_since(since),
        "concerns": list(items or []),
        "redacted": False,
    }


# ------------------------------------------------------------ what is news

def _key(item):
    return str(item.get("id") or item.get("kind") or item.get("title") or "")[:80]


def _severity_of(item):
    try:
        return float(item.get("headroom") if item.get("headroom") is not None
                     else item.get("progress") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def news(rep, st=None, now=None):
    """The concerns worth mentioning, given what has already been said.

    Returns (fresh, held). A concern is fresh when it has never been sent, when
    REPEAT_AFTER has elapsed, or when it has moved WORSE_BY closer to its limit
    since the last time it was mentioned. Everything else is held, and held is
    the normal case on a healthy car -- a sitrep that has nothing to report
    should say so in one line rather than repeat last month's news.
    """
    now = time.time() if now is None else now
    st = _state() if st is None else st
    seen = st.get("seen") or {}
    fresh, held = [], []
    for c in (rep.get("concerns") or []):
        k = _key(c)
        prior = seen.get(k)
        if not prior:
            fresh.append(c)
            continue
        aged = (now - float(prior.get("at") or 0)) >= REPEAT_AFTER
        worse = _severity_of(c) - float(prior.get("sev") or 0.0) >= WORSE_BY
        (fresh if (aged or worse) else held).append(c)
    return fresh, held


def remember(items, st=None, now=None):
    """Record what was actually sent, so it is not sent again tomorrow."""
    now = time.time() if now is None else now
    st = _state() if st is None else st
    seen = dict(st.get("seen") or {})
    for c in items:
        seen[_key(c)] = {"at": int(now), "sev": _severity_of(c)}
    st["seen"] = seen
    st["last_sent"] = int(now)
    _save_state(st)
    return st


# ---------------------------------------------------------------- rendering

def _line(label, value):
    return f"  {label:<22}{value}"


def render(rep, detail="summary", fresh=None, units=None):
    """The message body. Plain text, because a sitrep is read on a phone.

    `rep` is redacted by the caller when it should be -- this function does not
    redact, so that there is exactly one place where that decision is made and
    it is impossible to reach the mail server through a path that skipped it.
    """
    u = units or records.units_for()
    car = rep.get("car") or {}
    name = " ".join(str(car.get(k)) for k in ("year", "make", "model")
                    if car.get(k)) or "Your car"
    d = rep.get("driving") or {}
    out = [f"{name} — {time.strftime('%-d %b', time.localtime(rep.get('at', 0)))}", ""]

    if d.get("sessions"):
        dist = records.to_dist(d.get("km") or 0.0, u)
        out.append(_line("driven", f"{dist:.1f} {u['dist']} over "
                                   f"{d.get('sessions')} session"
                                   f"{'' if d.get('sessions') == 1 else 's'}"))
        out.append(_line("moving", f"{d.get('minutes', 0)} min"))
        if d.get("top"):
            out.append(_line("top speed",
                             f"{records.to_dist(d['top'], u):.0f} {u['speed']}"))
    else:
        out.append("  The car was not driven.")

    alerts = [a for a in (rep.get("alerts") or [])
              if str(a.get("urgency")) in ("critical", "normal")]
    if alerts:
        out += ["", "WHILE DRIVING"]
        for a in alerts[:6]:
            out.append(f"  • {a.get('title')} — {a.get('body')}")

    items = fresh if fresh is not None else (rep.get("concerns") or [])
    if items:
        out += ["", "WHAT IS DRIFTING"]
        for c in items[:6]:
            out.append(f"  • {c.get('title') or _key(c)}")
            for f in ("detail", "body", "note"):
                if c.get(f):
                    out.append(f"      {c[f]}")
                    break
            if c.get("when"):
                out.append(f"      reaches its limit around {c['when']}")
    else:
        out += ["", "Nothing new is drifting."]

    if detail == "full":
        out += ["", "FULL DETAIL"]
        for k in ("vin", "plate", "odometer", "title"):
            if car.get(k):
                out.append(_line(k, car[k]))
    else:
        out += ["", "This message carries no VIN, plate or name.",
                "Open OmaCar for the full evidence."]
    return "\n".join(out)


def subject(rep, fresh=None):
    car = rep.get("car") or {}
    what = str(car.get("model") or "car")
    items = fresh if fresh is not None else (rep.get("concerns") or [])
    urgent = [a for a in (rep.get("alerts") or [])
              if str(a.get("urgency")) == "critical"]
    if urgent:
        return f"OmaCar — {urgent[0].get('title')} on your {what}"
    if items:
        return f"OmaCar — {len(items)} thing{'' if len(items) == 1 else 's'} " \
               f"to look at on your {what}"
    return f"OmaCar — your {what} is fine"


def build(since=None, detail=None, db=None, now=None):
    """A ready-to-send sitrep: (subject, body, fresh_items, raw).

    The single place the privacy decision is made. Everything downstream gets
    text that has already been through it.
    """
    cfg = load()
    detail = detail or cfg.get("detail") or "summary"
    raw = gather(since=since, db=db)
    fresh, _held = news(raw, now=now)
    body_src = raw if detail == "full" else redact(raw)
    fresh_src = fresh if detail == "full" else (redact({"concerns": fresh,
                                                        "car": raw.get("car")})
                                               .get("concerns") or [])
    return (subject(body_src, fresh_src),
            render(body_src, detail=detail, fresh=fresh_src),
            fresh, raw)
