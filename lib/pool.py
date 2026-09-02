"""Pooled discovery, over a git repository rather than a server.

THE ARGUMENT THIS IMPLEMENTS.

Sweeping a car's manufacturer identifier range takes about seventy minutes --
but only once per MODEL, if the result is shared. That is the whole coverage
case: a vendor pays engineers to do it once per make behind closed doors and
rents it back; a community does it in parallel and every owner of that model
inherits it.

The roadmap files this under a cloud service, and it does not need one. A
profile is a small text file, the merge rules are already defined, and there is
already a repository everybody who installs this has a copy of. Fetching is an
HTTP GET of a file; contributing is a pull request. No accounts, no server, no
uptime, and the review that keeps bad data out is the review a maintainer was
going to do anyway.

WHAT A DOWNLOADED PROFILE IS AND IS NOT.

It is community data. The checksum proves the file has not been corrupted in
transit; it proves NOTHING about whether the person who wrote it was right, and
it is not a signature. A contributor could publish an entry marked `validated`
that is simply wrong, and the merge rules -- which let better evidence win --
would take it.

So fetching never applies anything by itself. It shows what would change and
stops. Applying is a separate, deliberate act, and every entry that arrives
this way is stamped with where it came from, so a reading that later looks
wrong can be traced out of the profile rather than merely doubted.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile as P  # noqa: E402

# Where the pool lives. Overridable, because a club, a marque forum or a shop
# should be able to run its own without asking anybody's permission.
DEFAULT_POOL = os.environ.get(
    "OMACAR_POOL",
    "https://raw.githubusercontent.com/mrjamesmyers/omacar/main/profiles")

TIMEOUT = 20
MAX_BYTES = 2 * 1024 * 1024


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "omacar"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read(MAX_BYTES + 1)


def _github_listing(pool):
    """List a GitHub-hosted pool from the API when there is no index.

    A hand-maintained index is one more thing to forget: a contributor adds a
    profile, does not update index.json, and the pool silently does not offer
    it. Falling back to listing the directory makes the pool self-maintaining
    -- the files ARE the index -- while index.json still works for a pool
    hosted on anything else.
    """
    import re
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)",
                 (pool or "").rstrip("/"))
    if not m:
        return None
    owner, repo, ref, path = m.groups()
    api = (f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
           f"?ref={ref}")
    try:
        raw = _get(api)
        items = json.loads(raw.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return None
    if not isinstance(items, list):
        return None
    return [{"slug": i["name"][:-5], "entries": None, "validated": None}
            for i in items
            if isinstance(i, dict) and i.get("name", "").endswith(".toml")]


def index(pool=None):
    """What the pool offers. (entries, error)."""
    url = (pool or DEFAULT_POOL).rstrip("/") + "/index.json"
    try:
        raw = _get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            listed = _github_listing(pool or DEFAULT_POOL)
            if listed:
                return listed, ""
            return [], ("the pool has no index yet — nobody has contributed a "
                        "profile. Yours would be the first.")
        return [], f"HTTP {e.code} from the pool"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return [], f"could not reach the pool: {e}"
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return [], "the pool index is not valid JSON"
    return doc.get("profiles") or [], ""


def fetch(slug, pool=None):
    """One profile from the pool, checked. (doc, note, error)."""
    import tomllib
    url = (pool or DEFAULT_POOL).rstrip("/") + f"/{slug}.toml"
    try:
        raw = _get(url)
    except urllib.error.HTTPError as e:
        return None, "", (f"no profile {slug!r} in the pool" if e.code == 404
                          else f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, "", f"could not reach the pool: {e}"
    if len(raw) > MAX_BYTES:
        return None, "", "that profile is implausibly large; refusing it"
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return None, "", f"the downloaded profile is not valid TOML: {e}"

    ok, why = P.verify(doc)
    if ok is False:
        # Integrity only. A file that does not match its own checksum was
        # altered after it was written, which is a reason to stop regardless of
        # whether the alteration was malicious or a text editor.
        return None, "", f"refusing it: {why}"
    note = "checksum matches" if ok else "no checksum recorded"

    problems = P.problems(doc)
    if problems:
        return None, "", ("that profile does not satisfy the schema:\n    - "
                          + "\n    - ".join(problems[:6]))
    return doc, note, ""


def stamp_origin(doc, slug, pool=None):
    """Mark every entry with where it came from.

    Without this, a merged profile cannot tell you which readings are your own
    work and which arrived from somebody else -- and the first time an entry
    looks wrong, that is the only question worth asking.
    """
    src = (pool or DEFAULT_POOL).rstrip("/") + f"/{slug}.toml"
    when = time.strftime("%Y-%m-%d")
    for p in doc.get("pid") or []:
        prov = p.setdefault("provenance", {})
        prov.setdefault("note", "")
        marker = f"from the pool {src} on {when}"
        if marker not in prov["note"]:
            prov["note"] = (prov["note"] + "; " if prov["note"] else "") + marker
    return doc


def diff(local, incoming):
    """What merging would actually change, before anything is written."""
    have = {p.get("id"): p for p in (local.get("pid") or [])}
    added, upgraded, kept = [], [], []
    for p in incoming.get("pid") or []:
        pid = p.get("id")
        if not pid:
            continue
        cur = have.get(pid)
        if not cur:
            added.append((pid, p.get("confidence")))
        elif P.RANK.get(p.get("confidence"), -1) > P.RANK.get(cur.get("confidence"), -1):
            upgraded.append((pid, cur.get("confidence"), p.get("confidence")))
        else:
            kept.append(pid)
    return {"added": added, "upgraded": upgraded, "kept": len(kept)}


def contribution(slug):
    """Prepare a local profile for sharing, and say what to check first.

    Returns (path, warnings). The warnings are the point: a contributor should
    see what they are about to publish about their own car BEFORE it is in a
    pull request, not after.
    """
    doc, path = P.load(slug)
    if not doc:
        return None, [f"no profile {slug!r}"]
    warn = list(P.problems(doc))

    # A full VIN must never leave the machine. The format truncates at write
    # time, so this is a last check rather than the only one.
    for p in doc.get("pid") or []:
        for k, v in (p.get("provenance") or {}).items():
            if isinstance(v, str) and len(v.strip()) == 17 and v.strip().isalnum():
                warn.append(f"{p.get('id')}: provenance.{k} looks like a full VIN")

    counts = {}
    for p in doc.get("pid") or []:
        c = p.get("confidence", "candidate")
        counts[c] = counts.get(c, 0) + 1
    if not counts.get("validated"):
        warn.append("nothing in this profile is validated yet — it is still "
                    "worth sharing, but say so when you open the pull request")

    out = os.path.join(os.path.expanduser("~"), f"{slug}.toml")
    P.write(out, doc)
    return out, warn
