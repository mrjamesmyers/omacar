"""What has already been asked, so a sweep can resume instead of restarting.

THE PROBLEM THIS SOLVES.

A full sweep of the manufacturer identifier range is about seventy minutes of
continuous bus time. Nobody has seventy uninterrupted minutes of parked,
engine-running car, and the battery will not survive it with the engine off. So
discovery has to happen the way driving happens: a few minutes at a time, over
weeks, resuming exactly where it stopped.

That needs a record of what has been asked. Not what ANSWERED -- the whole
point is that almost nothing answers, and "we asked 0000-0FFF and found
nothing" is the expensive, valuable result that must never be paid for twice.

WHY INTERVALS AND NOT A BITMAP.

64K identifiers per (module, service) would be an 8KB bitmap each, which is
fine, but sweeps are overwhelmingly contiguous: the record is a handful of
ranges, and merged intervals stay small, stay readable in the JSON, and make
"what is the next thing to ask" a subtraction rather than a scan.
"""

import json
import os
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import connect  # noqa: E402

STATE_DIR = os.path.join(connect.STATE, "frontier")


def path_for(vehicle_key):
    os.makedirs(STATE_DIR, exist_ok=True)
    return os.path.join(STATE_DIR, f"{vehicle_key}.json")


def load(vehicle_key):
    try:
        with open(path_for(vehicle_key), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"vehicle": vehicle_key, "services": {}}


def save(doc, vehicle_key):
    p = path_for(vehicle_key)
    tmp = p + ".tmp"
    doc["updated"] = time.time()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, p)
    return p


# ---- interval arithmetic ----------------------------------------------------

def merge(spans):
    """Sorted, non-overlapping, adjacent ones joined."""
    out = []
    for lo, hi in sorted(tuple(s) for s in spans):
        if out and lo <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def add(spans, lo, hi):
    return merge(list(spans) + [[lo, hi]])


def covered(spans):
    return sum(hi - lo + 1 for lo, hi in spans)


def next_gap(spans, lo, hi, want):
    """The next unswept chunk inside [lo, hi], at most `want` wide.

    Returns (start, end) or None when the range is complete. Walking forward
    from `lo` rather than picking the largest gap keeps a sweep's output
    readable -- somebody watching sees identifiers climb, and a resumed sweep
    carries on from where the last one visibly stopped.
    """
    cur = lo
    for s_lo, s_hi in merge(spans):
        if s_hi < cur:
            continue
        if s_lo > cur:
            end = min(hi, s_lo - 1, cur + want - 1)
            if end >= cur:
                return cur, end
            return None
        cur = max(cur, s_hi + 1)
        if cur > hi:
            return None
    if cur <= hi:
        return cur, min(hi, cur + want - 1)
    return None


# ---- the record ------------------------------------------------------------

def key(service, header):
    return f"0x{service:02X}/{header}"


def record(doc, service, header, lo, hi, hits=None):
    """Note that [lo, hi] has been asked of this module on this service."""
    svc = doc.setdefault("services", {}).setdefault(key(service, header),
                                                    {"swept": [], "found": []})
    svc["swept"] = add(svc.get("swept") or [], lo, hi)
    if hits:
        svc["found"] = sorted(set((svc.get("found") or []) + list(hits)))
    svc["last"] = time.time()
    return doc


def progress(doc, service, header, lo, hi):
    svc = (doc.get("services") or {}).get(key(service, header)) or {}
    spans = [s for s in merge(svc.get("swept") or [])]
    inside = 0
    for s_lo, s_hi in spans:
        a, b = max(s_lo, lo), min(s_hi, hi)
        if b >= a:
            inside += b - a + 1
    total = hi - lo + 1
    return inside, total, (100.0 * inside / total if total else 100.0)


def summary(doc):
    out = []
    for k, svc in sorted((doc.get("services") or {}).items()):
        spans = merge(svc.get("swept") or [])
        out.append({
            "key": k,
            "swept": covered(spans),
            "spans": len(spans),
            "found": len(svc.get("found") or []),
            "last": svc.get("last"),
        })
    return out
