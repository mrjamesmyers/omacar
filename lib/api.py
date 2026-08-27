"""The loopback API behind the OmaCar workshop.

Everything the app knows comes through here, and everything here comes out of
`records.py`, so the browser, the CLI and the advisor can never disagree about
what the car said.

    GET  /api/snapshot          the whole car in one read
    GET  /api/live              the current sample
    GET  /api/history           samples over a span, decimated to fit a graph
    GET  /api/records           saved scans, recordings and advisor answers
    GET  /api/ai                poll an advisor job
    GET  /api/ai/history
    GET  /api/theme             the active Omarchy palette, mapped to our roles
    GET  /api/concerns          what is trending somewhere it should not
    GET  /api/snapshots         states captured by hand or by the watchdog
    GET  /api/vehicles          the garage
    GET  /api/photos            photographs, filed against codes and concerns
    POST /api/photo             add, annotate or remove one
    POST /api/snapshot          freeze the state now
    POST /api/vehicle           switch to another car, or name one
    GET  /api/drive             the drive-mode layout
    POST /api/drive             change it
    POST /api/actuate           command an actuator, or stop one
    POST /api/units             switch between imperial and metric
    POST /api/odometer          set the reading (there is no odometer PID)
    POST /api/service           log, add or forget a maintenance item
    POST /api/scan              run a full-system scan and file the report
    POST /api/clear             clear codes in one module or all of them
    POST /api/record            save a stretch of samples as a recording
    POST /api/ai                start an advisor job

Advisor calls take a minute or so, which is far too long to hold a request
open while a spinner lies about progress. They are jobs: POST starts one and
returns an id, GET polls it. The worker is a plain thread — there is exactly
one user and they are on the same machine.
"""

import json
import os
import sqlite3
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book     # noqa: E402
import concerns  # noqa: E402
import photos   # noqa: E402
import garage   # noqa: E402
import records  # noqa: E402
import share    # noqa: E402
import theme    # noqa: E402

try:
    import ai
except Exception:                                   # pragma: no cover
    ai = None


# ---- advisor jobs -----------------------------------------------------------

_JOBS = {}
_JOBS_LOCK = threading.Lock()
# A job is finished work nobody has collected yet, so they are cheap to keep
# and pointless to keep forever.
JOB_TTL = 3600


def _sweep():
    now = time.time()
    with _JOBS_LOCK:
        for k in [k for k, v in _JOBS.items()
                  if v.get("done_at") and now - v["done_at"] > JOB_TTL]:
            _JOBS.pop(k, None)


def start_job(kind, question=None, code=None, refresh=False, span=None):
    if ai is None or not ai.available():
        raise RuntimeError(
            "the advisor needs the `claude` CLI, which is not installed. "
            "Everything else in OmaCar works without it.")
    _sweep()
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "kind": kind, "question": question, "code": code,
           "span": span, "state": "running", "started": time.time(),
           "result": None, "error": None, "done_at": None}
    with _JOBS_LOCK:
        _JOBS[jid] = job

    def work():
        try:
            out = ai.ask(kind, question=question, code=code, refresh=refresh,
                         span=span)
            job["result"] = out
            job["state"] = "done"
        except Exception as e:                       # noqa: BLE001
            job["error"] = str(e)[:600]
            job["state"] = "error"
        finally:
            job["done_at"] = time.time()

    threading.Thread(target=work, daemon=True).start()
    return job


def job_state(jid):
    with _JOBS_LOCK:
        job = _JOBS.get(jid)
    if not job:
        return {"state": "unknown"}
    out = dict(job)
    out["elapsed"] = round(time.time() - job["started"], 1)
    return out


# ---- the scan ---------------------------------------------------------------

def scan():
    """A full-system code scan, filed in the record book.

    On a real car this walks every module the adapter can address. Here it
    reads what the modules are holding — and the report marks which of them a
    plain OBD-II adapter could genuinely have reached, because a scan report
    that quietly implies it read the airbag module over a generic protocol is
    the sort of thing that gets people hurt.
    """
    s = records.snapshot()
    by_module = {}
    for f in s["faults"]:
        mid = (f.get("module") or {}).get("id") or "PGM-FI"
        by_module.setdefault(mid, []).append(f)

    report_modules = []
    for m in s["modules"]:
        codes = by_module.get(m["id"], [])
        active = [c for c in codes if c["active"]]
        report_modules.append({
            "id": m["id"], "name": m["name"], "system": m["system"],
            "addr": m["addr"], "generic": m["generic"],
            "part": m.get("part"), "sw": m.get("sw"),
            "codes": codes,
            "active": len(active),
            "worst": ("critical" if any(c["severity"] == "critical" for c in active)
                      else "warning" if any(c["severity"] == "warning" for c in active)
                      else "normal" if active else "clean"),
        })

    report = {
        "at": int(time.time()),
        "vehicle": s["name"],
        "vin": s["vehicle"].get("vin"),
        "odometer": s["odometer"],
        "units": s["units"],
        "simulated": s["simulated"],
        "modules": report_modules,
        "totals": {
            "modules": len(report_modules),
            "with_codes": sum(1 for m in report_modules if m["active"]),
            "codes": sum(m["active"] for m in report_modules),
            "cleared": sum(1 for f in s["faults"] if not f["active"]),
        },
        "readiness": s["readiness"],
        "mode06": s["mode06"],
        "mode06_failed": [m["mid"] for m in s["mode06"] if m["pass"] is False],
        "service_due": (s["service"] or {}).get("due", 0),
        "service_next": (s["service"] or {}).get("next"),
    }
    rid = records.write_record(
        "scan",
        f"{report['totals']['codes']} code(s) across "
        f"{report['totals']['with_codes']} module(s)",
        {"totals": report["totals"],
         "modules": [{"id": m["id"], "active": m["active"], "worst": m["worst"]}
                     for m in report_modules],
         "ready": s["readiness"]["ready"]},
        odo=s["odometer"])
    report["record_id"] = rid
    return report


def clear_codes(module=None):
    """Mode 04. Clears codes, and is honest about what that costs.

    Clearing does not fix anything and it resets every readiness monitor, so
    the returned payload says exactly what was lost — the app puts that in
    front of the user before the button does anything.
    """
    db = sqlite3.connect(records.DB, timeout=5.0)
    try:
        db.row_factory = sqlite3.Row
        if not records.has(db, "faults"):
            return {"cleared": 0, "monitors_reset": 0}
        mods = {m["id"]: m for m in records.modules(db)}
        codes = []
        for r in db.execute("SELECT code, status FROM faults"):
            if r["status"] not in ("stored", "pending", "permanent"):
                continue
            if module:
                owner = next((m["id"] for m in mods.values()
                              if r["code"] in m["codes"]), None)
                if owner != module:
                    continue
            # Permanent codes are permanent on purpose: they exist so a car
            # cannot be presented for an emissions test with the codes wiped
            # on the way there. Mode 04 does not touch them and neither do we.
            if r["status"] == "permanent":
                continue
            codes.append(r["code"])
        now = time.time()
        for c in codes:
            db.execute("UPDATE faults SET status='cleared', last_seen=? "
                       "WHERE code=?", (now, c))
        reset = 0
        if records.has(db, "readiness"):
            cur = db.execute(
                "UPDATE readiness SET complete=0 WHERE kind='trip' AND supported=1")
            reset = cur.rowcount
        db.commit()
    finally:
        db.close()
    records.write_record("clear", f"cleared {len(codes)} code(s)",
                         {"codes": codes, "module": module,
                          "monitors_reset": reset})
    return {"cleared": len(codes), "codes": codes, "monitors_reset": reset}


# ---- the drive layout ------------------------------------------------------
#
# Kept on the server rather than in the browser's storage, so the layout you
# arranged on the workstation is the layout the tablet in the car shows. A
# cockpit display is read-only, which means it inherits the arrangement rather
# than being able to change it — which is the right way round: you set this up
# in the kitchen, not at seventy miles an hour.

DRIVE_CFG = os.path.expanduser("~/.config/omarchy/omacar-drive.json")

DEFAULT_DRIVE = {
    "hero": "speed",
    "tiles": ["econ_now", "coolant", "volts"],
    "columns": 3,
    "footer": "trip",
    # When the app should take itself to drive mode on its own. On a tablet
    # bolted to a dashboard this is the difference between a diagnostic tool
    # and an instrument cluster: you get in, the adapter wakes up, and the
    # screen is already the one you want without touching it.
    #   off      never
    #   connect  the moment the adapter answers
    #   moving   the moment the car is actually rolling
    "auto": "connect",
    # ...and back to the workshop when the link drops, so a car you have just
    # parked and unplugged leaves you looking at the codes rather than at a
    # dead gauge.
    "auto_return": True,
}
AUTO_MODES = ("off", "connect", "moving")


def drive_layout():
    try:
        with open(DRIVE_CFG) as f:
            saved = json.load(f) or {}
    except (OSError, ValueError):
        saved = {}
    out = dict(DEFAULT_DRIVE)
    out.update({k: v for k, v in saved.items() if not k.startswith("_")})
    # Bound it here rather than trusting whatever wrote the file. A layout with
    # forty tiles is not a layout, and one with none is a blank screen in a
    # moving car.
    tiles = [t for t in (out.get("tiles") or []) if isinstance(t, str)][:8]
    out["tiles"] = tiles or list(DEFAULT_DRIVE["tiles"])
    try:
        out["columns"] = max(1, min(4, int(out.get("columns", 3))))
    except (TypeError, ValueError):
        out["columns"] = 3
    if out.get("auto") not in AUTO_MODES:
        out["auto"] = DEFAULT_DRIVE["auto"]
    out["auto_return"] = bool(out.get("auto_return", True))
    return out


def save_drive_layout(data):
    cur = drive_layout()
    for key in ("hero", "footer"):
        if isinstance(data.get(key), str):
            cur[key] = data[key]
    if data.get("auto") in AUTO_MODES:
        cur["auto"] = data["auto"]
    if isinstance(data.get("auto_return"), bool):
        cur["auto_return"] = data["auto_return"]
    if isinstance(data.get("tiles"), list):
        cur["tiles"] = [t for t in data["tiles"] if isinstance(t, str)][:8]
    if data.get("columns") is not None:
        try:
            cur["columns"] = max(1, min(4, int(data["columns"])))
        except (TypeError, ValueError):
            pass
    cur["_comment"] = ("Drive-mode layout. Edit here or in the app: OmaCar → "
                       "Drive → Customise. Tile ids are listed in "
                       "share/js/views/drive.js.")
    os.makedirs(os.path.dirname(DRIVE_CFG), exist_ok=True)
    tmp = DRIVE_CFG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cur, f, indent=2)
    os.replace(tmp, DRIVE_CFG)
    return drive_layout()


# ---- bidirectional --------------------------------------------------------

COMMAND = os.path.join(records.STATE, "command.json")

# What each test is allowed to do, and what it must not. The duration cap is
# the important column: a cooling fan commanded on and then forgotten is a flat
# battery, and an injector held off is a catalytic converter full of fuel.
LIMITS = {
    # Not an actuator: it holds the engine at idle so a test has a baseline
    # taken under the same conditions as the measurement. On a real car this
    # is a technician leaving it running; here the simulator has to be told.
    "hold_idle":     {"max": 180, "idle": True},
    "fan_low":       {"max": 60, "idle": False},
    "fan_high":      {"max": 60, "idle": False},
    "ac_clutch":     {"max": 30, "idle": True},
    "evap_purge":    {"max": 20, "idle": True},
    "egr_open":      {"max": 15, "idle": True},
    "fuel_pump":     {"max": 10, "idle": False},
    "injector_kill_1": {"max": 8, "idle": True},
    "injector_kill_2": {"max": 8, "idle": True},
    "injector_kill_3": {"max": 8, "idle": True},
    "injector_kill_4": {"max": 8, "idle": True},
}


def actuate(test, duration=None, stop=False):
    """Command an actuator, or stop whatever is running.

    Every test is capped in this process rather than trusted to the caller, and
    the command carries its own expiry so a crashed app cannot leave a fan on.
    """
    os.makedirs(records.STATE, exist_ok=True)
    if stop or not test:
        try:
            os.remove(COMMAND)
        except OSError:
            pass
        return {"stopped": True}
    lim = LIMITS.get(test)
    if not lim:
        raise ValueError(f"unknown test {test!r}")
    secs = min(lim["max"], max(1, int(duration or lim["max"])))
    cmd = {
        "id": uuid.uuid4().hex[:8],
        "test": test,
        "at": time.time(),
        "duration": secs,
        "idle": lim["idle"],
    }
    tmp = COMMAND + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
    os.replace(tmp, COMMAND)
    records.write_record("test", f"actuator: {test}", {"test": test, "seconds": secs})
    return cmd


def save_recording(label, t0, t1):
    db = records.connect()
    series = records.samples(db, since=t0, until=t1, limit=100000) if db else []
    st = records.stats(series) if series else {}
    if db:
        db.close()
    rid = records.write_record("movie", label or "Recording",
                               {"rows": len(series), "channels": st},
                               t0=t0, t1=t1)
    return {"id": rid, "rows": len(series), "channels": st}


# ---- routing ----------------------------------------------------------------

def qint(query, name, default, lo=None, hi=None):
    for part in query.split("&"):
        if part.startswith(name + "="):
            try:
                v = int(float(part[len(name) + 1:]))
            except ValueError:
                return default
            if lo is not None:
                v = max(lo, v)
            if hi is not None:
                v = min(hi, v)
            return v
    return default


def qstr(query, name, default=None):
    from urllib.parse import unquote_plus
    for part in query.split("&"):
        if part.startswith(name + "="):
            return unquote_plus(part[len(name) + 1:])
    return default


def handle_get(path, query):
    """(status, payload) or None when it is not ours."""
    if path == "/api/snapshot":
        return 200, records.snapshot()
    if path == "/api/live":
        return 200, records.live()
    if path == "/api/history":
        db = records.connect()
        t0 = qstr(query, "from")
        t1 = qstr(query, "to")
        n = qint(query, "n", 900, 1, 20000)
        if t0:
            series = records.samples(db, since=float(t0),
                                     until=float(t1) if t1 else None, limit=n)
        else:
            mins = qint(query, "mins", 20, 1, 60 * 24 * 14)
            series = records.samples(db, since=time.time() - mins * 60, limit=n)
        if db:
            db.close()
        return 200, {"rows": series, "cols": records.SAMPLE_COLS}
    if path == "/api/records":
        db = records.connect()
        out = records.records(db, kind=qstr(query, "kind"),
                              n=qint(query, "n", 50, 1, 500)) if db else []
        if db:
            db.close()
        return 200, {"records": out}
    if path == "/api/ai":
        jid = qstr(query, "job")
        if not jid:
            return 400, {"error": "job id required"}
        return 200, job_state(jid)
    if path == "/api/ai/history":
        return 200, {"records": ai.history() if ai else []}
    if path == "/api/ai/available":
        return 200, {"available": bool(ai and ai.available())}
    if path == "/api/drive":
        return 200, drive_layout()
    if path == "/api/concerns":
        return 200, {"concerns": concerns.assess()}
    if path == "/api/snapshots":
        return 200, {"snapshots": concerns.snapshots(
            qint(query, "n", 40, 1, 200))}
    if path == "/api/photos":
        return 200, {"photos": photos.listing(
            subject=qstr(query, "subject"), subject_id=qstr(query, "id"))}
    if path == "/api/vehicles":
        return 200, {"vehicles": garage.vehicles(), "current": garage.current()}
    if path == "/api/theme":
        # The mtime rides along so the app can re-apply on a theme change
        # without re-parsing anything it already has.
        try:
            stamp = int(os.path.getmtime(theme.THEME))
        except OSError:
            stamp = 0
        return 200, {"stamp": stamp, "vars": theme.palette()}
    return None


def handle_post(path, body):
    try:
        data = json.loads(body or "{}")
    except ValueError:
        data = {}
    if path == "/api/scan":
        return 200, scan()
    if path == "/api/clear":
        return 200, clear_codes(module=data.get("module"))
    if path == "/api/record":
        try:
            return 200, save_recording(data.get("label"),
                                       float(data["from"]), float(data["to"]))
        except (KeyError, TypeError, ValueError):
            return 400, {"error": "from and to (epoch seconds) required"}
    if path == "/api/drive":
        return 200, save_drive_layout(data)
    if path == "/api/snapshot":
        return 200, concerns.capture(
            reason=data.get("reason") or "manual",
            label=data.get("label"), note=data.get("note"))
    if path == "/api/photo":
        act = data.get("action") or "add"
        if act == "remove":
            return 200, {"removed": photos.remove(data.get("id") or "")}
        if act == "annotate":
            return 200, {"ok": photos.annotate(
                data.get("id") or "", note=data.get("note"),
                subject=data.get("subject"), subject_id=data.get("subject_id"),
                tags=data.get("tags"))}
        try:
            return 200, photos.add(
                data.get("image") or "", subject=data.get("subject") or "general",
                subject_id=data.get("subject_id") or "",
                note=data.get("note") or "", tags=data.get("tags"))
        except ValueError as e:
            return 400, {"error": str(e)}
    if path == "/api/vehicle":
        key = data.get("key")
        if data.get("name") and key:
            garage.name_vehicle(key, data["name"])
        elif key:
            garage.set_current(key)
            records.refresh_db()
        return 200, {"current": garage.current(),
                     "vehicles": garage.vehicles()}
    if path == "/api/odometer":
        try:
            km = float(data["km"])
        except (KeyError, TypeError, ValueError):
            return 400, {"error": "km required"}
        book.set_odometer(km)
        return 200, {"odometer": book.odometer()[0]}
    if path == "/api/service":
        act = data.get("action")
        if act == "log":
            done = book.log_service(data.get("item") or "")
            if not done:
                return 404, {"error": "no such item"}
            return 200, {"logged": done}
        if act == "add":
            return 200, {"added": book.add_item(
                data.get("item") or "Item",
                interval_km=float(data.get("interval_km") or 0),
                interval_days=int(data.get("interval_days") or 0),
                note=data.get("note") or "")}
        if act == "forget":
            return 200, {"removed": book.forget_item(data.get("item") or "")}
        if act == "start":
            db = book.open_db()
            try:
                n = book.ensure_schedule(db)
            finally:
                db.close()
            return 200, {"started": n}
        return 400, {"error": "action must be log, add, forget or start"}
    if path == "/api/units":
        want = str(data.get("system") or "").lower()
        if want not in records.UNITS:
            return 400, {"error": "units must be imperial or metric"}
        # One setting, in one file, read by the app, the CLI and the dock card,
        # so those three can never disagree about what a mile is.
        path_cfg = records.CONFIG
        try:
            with open(path_cfg) as f:
                cfg = json.load(f) or {}
        except (OSError, ValueError):
            cfg = {}
        cfg["units"] = want
        cfg.setdefault("_comment",
                       "OmaCar's record stays metric because OBD-II is metric "
                       "on the wire. This only decides how it is shown.")
        os.makedirs(os.path.dirname(path_cfg), exist_ok=True)
        tmp = path_cfg + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, path_cfg)
        return 200, {"units": records.units_for()}
    if path == "/api/actuate":
        try:
            return 200, actuate(data.get("test"), data.get("duration"),
                                bool(data.get("stop")))
        except ValueError as e:
            return 400, {"error": str(e)}
    if path == "/api/ai":
        try:
            span = data.get("span")
            if span and len(span) == 2:
                span = (float(span[0]), float(span[1]))
            else:
                span = None
            job = start_job(data.get("kind", "triage"),
                            question=data.get("question"),
                            code=data.get("code"),
                            refresh=bool(data.get("refresh")),
                            span=span)
        except Exception as e:                       # noqa: BLE001
            return 503, {"error": str(e)}
        return 200, {"id": job["id"], "state": job["state"]}
    return None
