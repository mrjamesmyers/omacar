"""OmaCar wearing whatever theme Omarchy is wearing.

An app on this desktop that ships its own colours is a guest that turned up in
its own clothes. Omarchy keeps the active palette at
`~/.local/state/omarchy/current/theme/colors.toml`, every other application
reads it, and so does this.

The mapping is not a straight copy. A theme's palette is written for terminals
and window chrome — sixteen ANSI colours and a handful of backgrounds — and a
diagnostic tool needs a different vocabulary: a ground, three surface steps,
three ink weights, and five semantic colours that must stay distinguishable
from each other on any of them. So the theme supplies the hues and this decides
the roles, which is why a light theme comes out legible rather than inverted.

Parsed by hand rather than with a TOML library: the file is `key = "value"`
lines and a dependency for that would be a dependency to keep working forever.
"""

import os
import re

# The active theme, or whatever OMACAR_THEME points at — which is how the
# light themes get looked at during development without changing the desktop
# out from under whoever is using it.
THEME = os.environ.get(
    "OMACAR_THEME",
    os.path.expanduser("~/.local/state/omarchy/current/theme/colors.toml"))

# What the app falls back to when there is no Omarchy theme to read — the
# palette it was designed against, so a standalone install still looks right.
FALLBACK = {
    "mode": "dark",
    "background": "#0D1417", "dark_background": "#0A1013",
    "darker_background": "#070B0D", "lighter_background": "#162228",
    "foreground": "#E7F0EE", "dark_foreground": "#93A6A2", "muted": "#5F726E",
    "accent": "#4FA8E8", "red": "#E85D4E", "green": "#4ACE8A",
    "yellow": "#E5B457", "orange": "#E5B457", "blue": "#4FA8E8",
    "cyan": "#64D2FF", "magenta": "#8B7CF0",
}

LINE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"')


def read(path=THEME):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = LINE.match(line)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        return {}
    return out


def hex_to_rgb(v):
    v = (v or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        return None
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def luminance(v):
    """Relative luminance, for deciding what is dark and what is not."""
    rgb = hex_to_rgb(v)
    if not rgb:
        return 0.0

    def chan(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a, b, k):
    """`a` moved `k` of the way toward `b`."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    if not ra or not rb:
        return a
    return rgb_to_hex([ra[i] + (rb[i] - ra[i]) * k for i in range(3)])


def readable(colour, on, floor=3.4):
    """Nudge a colour until it is legible on a background.

    A theme's red is chosen to be legible in a terminal, which is not the same
    background this app puts it on. Rather than give up on the theme's hue, walk
    it toward the ink until it clears a contrast floor — the colour still reads
    as that theme's red, and the text can still be read.
    """
    if not hex_to_rgb(colour) or not hex_to_rgb(on):
        return colour
    target = "#FFFFFF" if luminance(on) < 0.5 else "#000000"
    out = colour
    for step in range(12):
        if contrast(out, on) >= floor:
            return out
        out = mix(out, target, 0.09)
    return out


def palette(path=THEME):
    """The app's CSS custom properties, derived from the active theme."""
    t = read(path)
    src = dict(FALLBACK)
    src.update({k: v for k, v in t.items() if v})
    light = (src.get("mode") or "dark").lower() == "light"

    fg = src.get("foreground") or FALLBACK["foreground"]

    # Four surface steps. A dark theme goes down from its background and a
    # light one goes up, so the same four roles exist either way and every
    # layout rule in the app keeps working without knowing which it got.
    if light:
        ground = src.get("dark_background") or src.get("background")
        panel = src.get("background")
        panel2 = src.get("lighter_background") or mix(panel, fg, 0.04)
        raise_ = mix(panel, fg, 0.09)
    else:
        ground = src.get("darker_background") or src.get("background")
        panel = src.get("background")
        panel2 = src.get("lighter_background") or mix(panel, fg, 0.05)
        raise_ = mix(panel2, fg, 0.07)

    # Ink weights and rules are the foreground bled into the ground rather than
    # fixed greys, so they sit correctly on a warm theme and a cold one alike.
    ink = fg
    dim = src.get("dark_foreground") or mix(fg, ground, 0.35)
    faint = src.get("muted") or mix(fg, ground, 0.58)
    ghost = mix(fg, ground, 0.74)

    # THE INK WEIGHTS GET THE SAME CONTRAST FLOOR THE SEMANTIC COLOURS GET.
    #
    # Below this, `dim` and `faint` were whatever the bleed happened to
    # produce, and nobody measured the result. On the stock dark palette faint
    # landed near 3:1 on --panel: fine at a desk, and gone in a car with the
    # sun on the screen. Every tile label, every unit, every caption in this
    # app is --faint, so "hard to read in sunlight" was not a drive-mode
    # problem -- it was the whole app.
    #
    # Measured against --panel because that is the surface these actually sit
    # on (cards, tiles, rows), not against --ground.
    #
    # The floors are deliberately above WCAG's 4.5:1 for body text: this is a
    # tool used outdoors, in a moving vehicle, at a glance. ghost is decorative
    # (rules, disabled chrome) so it keeps a lower floor -- lifting it to match
    # would flatten the hierarchy that makes the other two readable.
    # WHITE INK ON DARK, NOT A TINTED GREY.
    #
    # The contrast floors above were the first attempt and they were not
    # enough: on the Tokyo Night palette they lifted faint from 1.91:1 to
    # 5.15:1, which passes WCAG and is still washed out through a windscreen
    # with the sun on the panel. Contrast ratio is not the whole story
    # outdoors -- a blue-grey at 5:1 reads worse in glare than white at the
    # same ratio, because the eye is fighting the ambient colour temperature
    # as well as the luminance.
    #
    # So on a dark theme the ink weights are pulled toward white rather than
    # merely away from the ground, and the separation between them is kept
    # small: hierarchy still reads, but nothing falls into the range where it
    # cannot be read at a glance in a moving car.
    #
    # Light themes are left alone -- they have the opposite problem and none
    # of this applies.
    if not light:
        WHITE = "#FFFFFF"
        ink = mix(ink, WHITE, 0.72)
        dim = mix(dim, WHITE, 0.82)
        faint = mix(faint, WHITE, 0.68)
        ghost = mix(ghost, WHITE, 0.42)

    dim = readable(dim, panel, floor=7.0)
    faint = readable(faint, panel, floor=5.0)
    ghost = readable(ghost, panel, floor=2.6)
    edge = mix(ground, fg, 0.10 if light else 0.09)
    edge2 = mix(ground, fg, 0.20 if light else 0.17)

    # Semantics. Amber is the one that needs care: plenty of themes use a
    # yellow that is perfectly readable in a terminal and invisible on a panel,
    # so warning prefers `orange` where the theme has one and falls back to
    # yellow. Every semantic colour is then checked against the surface it will
    # actually sit on, and nudged if it does not clear the floor.
    on = panel
    sem = {
        "ok": src.get("green"),
        "warn": src.get("orange") or src.get("yellow"),
        "bad": src.get("red"),
        "info": src.get("blue") or src.get("accent"),
        "ai": src.get("magenta") or src.get("accent"),
    }
    sem = {k: readable(v or FALLBACK.get(k, fg), on) for k, v in sem.items()}

    def tint(hexv, alpha):
        rgb = hex_to_rgb(hexv) or (0, 0, 0)
        return "rgba(%d, %d, %d, %.3f)" % (rgb[0], rgb[1], rgb[2], alpha)

    out = {
        "mode": "light" if light else "dark",
        "ground": ground, "panel": panel, "panel-2": panel2, "raise": raise_,
        "edge": edge, "edge-2": edge2,
        "ink": ink, "dim": dim, "faint": faint, "ghost": ghost,
        "accent": src.get("accent") or sem["info"],
    }
    for k, v in sem.items():
        out[k] = v
        # The wash behind a tinted card. Heavier on light themes, where a 12%
        # tint on white is invisible.
        out[k + "-bg"] = tint(v, 0.16 if light else 0.12)
        # What to print ON that colour when it is used as a solid fill — a
        # count badge, a filled pill. Whichever of black and white actually
        # contrasts better, measured, not guessed: a luminance threshold puts
        # white on a saturated red at 3.4:1 when black would have given 6.2.
        # Blending the colour with itself is worse again — a dark red digit on
        # a red badge is a dot with a rumour of a number in it.
        dark_ink, light_ink = "#0A0A0C", "#FFFFFF"
        out["on-" + k] = (dark_ink if contrast(v, dark_ink) >= contrast(v, light_ink)
                          else light_ink)
    return out


def css(path=THEME):
    """The palette as a stylesheet the app can drop on :root."""
    p = palette(path)
    body = "\n".join(f"  --{k}: {v};" for k, v in p.items() if k != "mode")
    scheme = p["mode"]
    return (f"/* Generated from Omarchy's active theme. */\n"
            f":root {{\n  color-scheme: {scheme};\n{body}\n}}\n")


def main():
    import json
    import sys
    if "--css" in sys.argv:
        print(css(), end="")
        return 0
    print(json.dumps(palette(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
