"""Photographs of the thing you are looking at, filed against it.

The one part of a Snap-on tablet that is not software: you are under a bonnet,
you can see the problem, and the useful record of it is a picture. A perished
hose, a wet manifold, a corroded connector, a wear pattern on a tyre — none of
that is on the bus and all of it is the diagnosis.

So: photographs, each attached to something the tool already knows about — a
trouble code, a concern, a snapshot, a service item — with a note and the
odometer at the time. Filed in the vehicle's own record, so they travel with
the car rather than with the tablet.

Stored as files rather than blobs in the database. A hundred photographs is
half a gigabyte and SQLite is the wrong shape for that; it also means the
pictures survive anything that happens to the database and can be handed to
somebody with a file manager.

    ~/.local/state/omacar/photos/<vehicle>/<id>.jpg

Where the camera works, and where it does not
---------------------------------------------
`getUserMedia` needs a secure context. `http://127.0.0.1` counts as one, so
the camera works in the kiosk and on the machine running OmaCar. A cockpit
display reached over the LAN at `http://192.168.x.x` does NOT, and no browser
will let it near a camera. That is a browser rule, not ours, and the app says
so rather than presenting a button that cannot work — a tablet on the network
can still upload a picture it already took.
"""

import base64
import binascii
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garage   # noqa: E402
import records  # noqa: E402

ROOT = os.path.join(records.STATE, "photos")

# Generous for a photograph, mean enough that a runaway upload cannot fill a
# tablet's eMMC in one request.
MAX_BYTES = 8 * 1024 * 1024

# What a browser's canvas.toBlob will actually hand us.
KINDS = {
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"RIFF": ("webp", "image/webp"),
}

SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def folder(key=None):
    d = os.path.join(ROOT, SAFE.sub("", key or garage.current()) or "unknown")
    os.makedirs(d, exist_ok=True)
    return d


def sniff(blob):
    """The format, from the bytes. Never from a filename somebody sent us."""
    for magic, (ext, mime) in KINDS.items():
        if blob.startswith(magic):
            if magic == b"RIFF" and blob[8:12] != b"WEBP":
                continue
            return ext, mime
    return None, None


def open_db():
    db = records.connect_rw()
    db.execute("""CREATE TABLE IF NOT EXISTS photos (
        id TEXT PRIMARY KEY, at REAL, file TEXT, mime TEXT, bytes INTEGER,
        subject TEXT, subject_id TEXT, note TEXT, odo REAL, tags TEXT)""")
    return db


def add(data_url_or_bytes, subject="general", subject_id="", note="", tags=None):
    """File one photograph against something.

    `subject` is what it is a picture of — "code", "concern", "snapshot",
    "service" or "general" — and `subject_id` names which one. That pairing is
    the whole filing system, and it is why a photograph of a weeping hose ends
    up on the same screen as the code it explains.
    """
    blob = data_url_or_bytes
    if isinstance(blob, str):
        # A canvas hands JavaScript a data: URL; take the payload only.
        if "," in blob and blob.startswith("data:"):
            blob = blob.split(",", 1)[1]
        try:
            blob = base64.b64decode(blob, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("that is not an image")
    if not isinstance(blob, (bytes, bytearray)):
        raise ValueError("that is not an image")
    if len(blob) > MAX_BYTES:
        raise ValueError(f"too large — {len(blob) // 1024} kB, limit "
                         f"{MAX_BYTES // 1024} kB")
    ext, mime = sniff(blob)
    if not ext:
        # Refusing anything we cannot identify keeps arbitrary files out of a
        # directory the app serves back to a browser.
        raise ValueError("only JPEG, PNG and WebP")

    pid = f"{int(time.time())}-{os.urandom(3).hex()}"
    name = f"{pid}.{ext}"
    path = os.path.join(folder(), name)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)

    odo = None
    try:
        snap = records.snapshot()
        odo = snap.get("odometer")
    except Exception:                                     # noqa: BLE001
        pass

    db = open_db()
    try:
        db.execute("INSERT INTO photos VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (pid, time.time(), name, mime, len(blob), subject,
                    str(subject_id or ""), note or "", odo,
                    json.dumps(tags or [])))
        db.commit()
    finally:
        db.close()
    return {"id": pid, "file": name, "mime": mime, "bytes": len(blob),
            "subject": subject, "subject_id": str(subject_id or ""),
            "note": note or "", "odo": odo, "at": int(time.time())}


def listing(subject=None, subject_id=None, n=200):
    db = records.connect()
    if db is None:
        return []
    try:
        sql = "SELECT * FROM photos"
        args, where = [], []
        if subject:
            where.append("subject = ?")
            args.append(subject)
        if subject_id:
            where.append("subject_id = ?")
            args.append(str(subject_id))
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY at DESC LIMIT ?"
        args.append(n)
        out = records.rows(db, sql, tuple(args), table="photos")
    finally:
        db.close()
    for p in out:
        try:
            p["tags"] = json.loads(p.get("tags") or "[]")
        except (ValueError, TypeError):
            p["tags"] = []
        p["url"] = "/photo/" + p["file"]
    return out


def path_of(name):
    """Resolve a served filename, refusing anything that climbs out."""
    safe = SAFE.sub("", os.path.basename(name or ""))
    if not safe:
        return None
    path = os.path.join(folder(), safe)
    if not os.path.isfile(path):
        return None
    # Belt and braces: the resolved path has to still be inside the folder.
    if os.path.commonpath([os.path.realpath(path),
                           os.path.realpath(folder())]) != os.path.realpath(folder()):
        return None
    return path


def remove(pid):
    db = open_db()
    try:
        row = db.execute("SELECT file FROM photos WHERE id = ?", (pid,)).fetchone()
        if row is None:
            return False
        db.execute("DELETE FROM photos WHERE id = ?", (pid,))
        db.commit()
    finally:
        db.close()
    try:
        os.remove(os.path.join(folder(), row["file"]))
    except OSError:
        pass
    return True


def annotate(pid, note=None, subject=None, subject_id=None, tags=None):
    db = open_db()
    try:
        sets, args = [], []
        for col, val in (("note", note), ("subject", subject),
                         ("subject_id", subject_id)):
            if val is not None:
                sets.append(f"{col} = ?")
                args.append(str(val))
        if tags is not None:
            sets.append("tags = ?")
            args.append(json.dumps(tags))
        if not sets:
            return False
        args.append(pid)
        db.execute(f"UPDATE photos SET {', '.join(sets)} WHERE id = ?", args)
        db.commit()
        return True
    finally:
        db.close()


def main(argv):
    what = argv[0] if argv else "list"
    if what in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if what == "add" and len(argv) > 1:
        with open(argv[1], "rb") as f:
            blob = f.read()
        try:
            p = add(blob, subject=argv[2] if len(argv) > 2 else "general",
                    subject_id=argv[3] if len(argv) > 3 else "",
                    note=" ".join(argv[4:]))
        except ValueError as e:
            print(f"omacar photo: {e}", file=sys.stderr)
            return 1
        print(f"  filed {p['id']} ({p['bytes'] // 1024} kB)")
        return 0
    if what == "remove" and len(argv) > 1:
        print("  removed" if remove(argv[1]) else "  no such photograph")
        return 0
    shots = listing()
    print()
    if not shots:
        print("  No photographs yet.")
        print("  Take them in the app — Codes, Concerns or Snapshots — or:")
        print("      omacar photo add <file> code P0135 'weeping at the flange'")
        print()
        return 0
    for p in shots:
        stamp = time.strftime("%d %b %H:%M", time.localtime(p["at"]))
        subj = f"{p['subject']}:{p['subject_id']}" if p["subject_id"] else p["subject"]
        print(f"  {p['id']:<20} {stamp}  {subj:<18} {p['note'][:44]}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
