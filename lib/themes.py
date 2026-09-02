"""Themes you build yourself, kept beside the drive layout.

WHY THE SERVER AND NOT THE BROWSER.

For the same reason the drive layout lives here: a theme you make at the
kitchen table should be the theme the tablet on the dashboard is wearing.
localStorage would have made it per-browser, which on a tool that is
deliberately usable from a phone, a laptop and a bolted-down cockpit display
is the wrong answer three times over.

WHY NINE COLOURS AND NOT TWENTY-NINE.

A theme here is a handful of source colours. Everything the app actually
paints with -- the four surface steps, the four ink weights, the semantic
colours and their backgrounds, the badge inks, the in-car brights -- is
derived from those by theme.palette_of(), which is the same function an
Omarchy theme goes through.

That is deliberate and it is the whole design. palette_of() is where the
contrast floors live: where `faint` gets nudged until it clears 5:1 on the
surface it will actually sit on, where a theme's terminal-yellow gets pulled
until a warning is readable through a windscreen, where --bright earns its
glare margin. An editor that wrote the output tokens directly would let
somebody build a palette that is beautiful on a desk and illegible in a car,
and would need every one of those rules reimplemented in JavaScript to stop
them.

Nine decisions, and the result is legible by construction.
"""

import json
import os
import re
import time

STORE = os.path.expanduser("~/.config/omarchy/omacar-themes.json")

# What the app is currently wearing. "omarchy" means follow the desktop.
DESKTOP = "omarchy"

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}$")

# The colours a theme is made of. Mirrors theme.SOURCE_KEYS; `mode` is handled
# separately because it is not a colour.
COLOURS = ("background", "foreground", "accent",
           "red", "green", "yellow", "blue", "magenta")

# A starting point that is already a coherent theme rather than a blank form.
# Editing something is a far better first move than inventing something.
SEED = {
    "mode": "dark",
    "background": "#12131A",
    "foreground": "#E8EAF2",
    "accent": "#7AA2F7",
    "red": "#F7768E",
    "green": "#9ECE6A",
    "yellow": "#E0AF68",
    "blue": "#7AA2F7",
    "magenta": "#BB9AF7",
}

# Enough to keep a garage of them, few enough that the file stays a file.
MAX_THEMES = 40
MAX_NAME = 48


def _blank():
    return {"active": DESKTOP, "themes": {}}


def load():
    try:
        with open(STORE, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return _blank()
    if not isinstance(raw, dict):
        return _blank()
    out = _blank()
    themes = raw.get("themes")
    if isinstance(themes, dict):
        for tid, body in list(themes.items())[:MAX_THEMES]:
            clean = _clean(tid, body)
            if clean:
                out["themes"][tid] = clean
    active = raw.get("active")
    # An active id pointing at a theme that has been deleted is how an app
    # ends up unstyled with nothing on screen explaining why.
    out["active"] = active if active in out["themes"] else DESKTOP
    return out


def _clean(tid, body):
    """One theme, or None if it is not one. Never raises on a hand-edited file."""
    if not isinstance(tid, str) or not SLUG.match(tid):
        return None
    if not isinstance(body, dict):
        return None
    out = {"name": str(body.get("name") or tid)[:MAX_NAME]}
    out["mode"] = "light" if str(body.get("mode", "")).lower() == "light" else "dark"
    for key in COLOURS:
        v = body.get(key)
        if isinstance(v, str) and HEX.match(v.strip()):
            out[key] = v.strip().lower()
        else:
            out[key] = SEED[key]
    return out


def save(store):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    body = dict(store)
    body["_comment"] = (
        "OmaCar themes. Nine source colours each; everything else is derived "
        "by lib/theme.py so the contrast floors always apply. Edit here or in "
        "the app: OmaCar → Themes.")
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2)
    os.replace(tmp, STORE)
    return load()


def put(tid, body):
    store = load()
    clean = _clean(tid, body)
    if not clean:
        return store, "that is not a theme"
    if tid not in store["themes"] and len(store["themes"]) >= MAX_THEMES:
        return store, "that is as many themes as this keeps"
    store["themes"][tid] = clean
    return save(store), None


def remove(tid):
    store = load()
    if tid in store["themes"]:
        del store["themes"][tid]
        if store["active"] == tid:
            store["active"] = DESKTOP
        return save(store), None
    return store, "no such theme"


def select(tid):
    store = load()
    if tid != DESKTOP and tid not in store["themes"]:
        return store, "no such theme"
    store["active"] = tid
    return save(store), None


def active():
    """(source colours, stamp) for whatever the app should be wearing.

    Returns (None, stamp) to mean "follow the desktop", so the caller keeps
    reading Omarchy's own theme file rather than this having to know how.
    """
    store = load()
    tid = store["active"]
    if tid == DESKTOP or tid not in store["themes"]:
        return None, 0
    # The stamp is what tells a running app the palette moved. It has to change
    # when the theme is edited AND when a different one is picked, so it comes
    # from the file both of those write.
    try:
        stamp = int(os.path.getmtime(STORE))
    except OSError:
        stamp = int(time.time())
    return store["themes"][tid], stamp
