"""Colours a chart can actually tell apart.

WHY THIS IS NOT IN theme.py, AND WHY IT EXISTS AT ALL.

theme.py guarantees CONTRAST: every colour it derives is legible against the
surface it will sit on. That is the right invariant for text and pills, and it
is why a theme somebody invents at the kitchen table is still readable through
a windscreen at noon.

It says nothing about whether two colours can be told apart from EACH OTHER,
and that is the only property a chart with more than one series depends on. The
two invariants are independent, and the app shipped six trace colours that pass
the first and fail the second. Measured on the live theme:

    #f7768e (bad) vs #eb927b (warn)   ΔE 3.9 deutan,  7.7 normal vision
    #8ab6b8 (a mix of info and ok)    chroma 0.047 — reads grey
    all six lightnesses                0.709 - 0.816 — one narrow band

Below about 15 even full-colour vision struggles; below 8 a red-green
colourblind reader has no chance. So the replay chart was drawing six lines
that a third of the people who might use it could not follow, and two lines
nobody could.

Since users BUILD themes here, this cannot be fixed by choosing better
constants. It has to be derived, per theme, the way contrast already is.

THE MATHS IS BORROWED ON PURPOSE.

OKLab, the Machado-Oliveira-Fernandes (2009) CVD transforms at severity 1.0,
and ΔE as Euclidean distance in OKLab ×100 — these are transcribed from the
validator this project checks its palettes with. If the fix used a different
metric from the check, the two would disagree at exactly the borderline cases
that matter, and a palette could be "fixed" into something that still fails.
They must stay in lockstep; that is the whole reason for copying rather than
inventing.
"""

import math

# Machado, Oliveira & Fernandes (2009), severity 1.0, applied in LINEAR rgb.
MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779),
               (-0.078411, 0.930809, 0.147602),
               (0.004733, 0.691367, 0.303900)),
}

# ΔE×100 in OKLab. TARGET is what a palette should reach; FLOOR is the lowest
# that is defensible and only with a second cue (a direct label, a gap, a
# texture). NORMAL_FLOOR is not negotiable by secondary encoding: below it,
# people with ordinary colour vision cannot separate the pair either.
CVD_TARGET = 8.0
CVD_FLOOR = 6.0
NORMAL_FLOOR = 15.0
CHROMA_FLOOR = 0.10

# OKLCh lightness a categorical mark must sit inside. Narrow on purpose: marks
# far outside it either vanish into the surface or glare off it, and a set
# spread across a wide L range reads as a ramp -- an ORDER -- when categorical
# colours are supposed to carry identity and no order at all.
#
# It is also narrow enough to be a real constraint: 0.19 wide in dark mode
# means separation has to come from hue and chroma, not from lightness. An
# earlier ladder here ran 0.58-0.80 and produced a palette that passed every
# other check and failed this one, including the theme's own accent at 0.719.
BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}


def _s2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin2s(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _hex_to_lin(h):
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return [_s2lin(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)]
    except ValueError:
        return None


def _lin_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(
        max(0, min(255, int(round(_lin2s(c) * 255)))) for c in rgb)


def oklab_from_lin(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3) \
        if (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) > 0 else 0.0
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3) \
        if (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) > 0 else 0.0
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3) \
        if (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) > 0 else 0.0
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def lin_from_oklab(lab):
    L, a, b = lab
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s]


def oklab(h):
    lin = _hex_to_lin(h)
    return oklab_from_lin(lin) if lin else (0.0, 0.0, 0.0)


def oklch(h):
    L, a, b = oklab(h)
    return L, math.hypot(a, b), (math.degrees(math.atan2(b, a)) % 360.0)


def from_oklch(L, C, hue):
    rad = math.radians(hue)
    return _lin_to_hex(lin_from_oklab((L, C * math.cos(rad), C * math.sin(rad))))


# Which band in_gamut() should check against. Set by series() rather than
# threaded through every call, because in_gamut is called thousands of times
# per derivation and the mode does not change inside one.
_band_dark = [True]


def in_gamut(L, C, hue, tol=0.0):
    """Does this OKLCh triple actually survive the trip through sRGB?

    OKLCh is bigger than sRGB, and asking for a chroma that does not exist at
    a given lightness does not fail -- _lin_to_hex clamps each channel and
    hands back a duller colour than was requested. That is how a request for
    C=0.13 came back as #FFCAB0 at C=0.07, under the chroma floor and reading
    grey. So a candidate is only usable if the colour that comes BACK still
    has the chroma that was asked for.
    """
    got = from_oklch(L, C, hue)
    gl, gc, _gh = oklch(got)
    # The DELIVERED lightness, not the requested one. Quantising to 8-bit
    # moves L slightly, and asking for exactly the ceiling produced colours
    # that came back at 0.672 against a limit of 0.67 -- in band on the way
    # in, out of band on the way out.
    blo, bhi = BAND["dark"] if _band_dark[0] else BAND["light"]
    if not (blo <= gl <= bhi):
        return False
    # No slack on the floor itself. A tolerance of 0.012 let a colour through
    # at chroma 0.089 against a floor of 0.10, which audit() then flagged as
    # grey -- a floor that can be missed by "nearly" is not a floor.
    return gc >= CHROMA_FLOOR - tol


CONTRAST_MIN = 3.0


def rel_lum(h):
    lin = _hex_to_lin(h)
    if not lin:
        return 0.0
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def simulate(h, kind):
    lin = _hex_to_lin(h)
    if not lin:
        return [0.0, 0.0, 0.0]
    M = MACHADO[kind]
    return [max(0.0, min(1.0, sum(M[i][j] * lin[j] for j in range(3))))
            for i in range(3)]


def delta_e(a, b, kind=None):
    """Euclidean distance in OKLab ×100. kind=None is ordinary vision."""
    la = oklab_from_lin(simulate(a, kind) if kind else (_hex_to_lin(a) or [0, 0, 0]))
    lb = oklab_from_lin(simulate(b, kind) if kind else (_hex_to_lin(b) or [0, 0, 0]))
    return 100.0 * math.dist(la, lb)


def worst_gap(a, b):
    """How far apart two colours are for the reader who can separate them least.

    protan and deutan are the binding constraints (red-green, ~8% of men);
    tritan is rarer and reported rather than enforced by the validator, so it
    is not part of the minimum here either.
    """
    return min(delta_e(a, b, "protan"), delta_e(a, b, "deutan"))


def separates(colour, placed, cvd=CVD_TARGET, normal=NORMAL_FLOOR):
    """Is this colour far enough from everything already chosen?"""
    for other in placed:
        if worst_gap(colour, other) < cvd:
            return False
        if delta_e(colour, other) < normal:
            return False
    return True


def series(seeds, n, surface, light=False):
    """`n` colours a chart can use, derived from this theme's own colours.

    Seeds are tried IN ORDER and kept when they are already far enough from
    what has been placed, so a theme's identity survives wherever it can: the
    first series stays the theme's accent, the second its green, and a palette
    that was fine to begin with comes out unchanged.

    When a seed collides it is not discarded but WALKED -- rotated around the
    OKLCh hue circle at a lightness taken from a deliberately staggered ladder.
    The ladder matters as much as the rotation: the measured failure was six
    colours inside a 0.11 lightness band, and two hues at identical lightness
    stay confusable under simulation no matter how far apart the hues are.

    Nothing here can fail closed. If no rotation clears the floor -- possible
    when a theme is nearly monochrome and n is large -- the best candidate
    found is taken anyway and reported by audit() rather than silently
    pretending. A chart with imperfect colours beats a chart that refuses to
    draw.
    """
    seeds = [s for s in seeds if _hex_to_lin(s)]
    if not seeds:
        seeds = ["#7AA2F7"]
    dark = not light

    # A lightness ladder spanning a usable band. Dark surfaces need brighter
    # marks, light surfaces darker ones, and both need the spread.
    _band_dark[0] = dark
    lo, hi = BAND["dark"] if dark else BAND["light"]
    # CONTRAST IS A FILTER, NOT A BIAS.
    #
    # It was a bias first: shrink the band 45% away from the surface so marks
    # land where contrast is easy. That bought contrast by spending the
    # lightness range separation needs, and the bill came due on rose-pine --
    # every hard check passed except the normal-vision floor, at ΔE 14.9
    # against a floor of 15, because there was no room left to move.
    #
    # The two constraints are not actually in competition. Contrast is a
    # per-colour property with a hard threshold, so it belongs in the candidate
    # filter beside the gamut check, where it rejects individual colours and
    # leaves the whole band available to everything else. Separation is a
    # property BETWEEN colours and needs all the room it can get.
    ladder = [lo + (hi - lo) * (i / max(1, n - 1)) for i in range(n)]
    # Interleave so neighbouring series differ most in lightness, rather than
    # ramping smoothly and putting the two closest together side by side.
    order = sorted(range(n), key=lambda i: (i % 2, i))
    ladder = [ladder[order.index(i)] for i in range(n)]

    placed = []
    for i in range(n):
        seed = seeds[i % len(seeds)]
        L0, C0, H0 = oklch(seed)
        target_L = ladder[i]
        chroma = max(CHROMA_FLOOR + 0.02, C0)

        # A seed is only kept AS IS when it already sits in the band. The
        # theme's identity is worth preserving, but not at the cost of a
        # palette that fails the band check -- so a seed outside it is pulled
        # to the nearest rung and treated like any other candidate.
        if (separates(seed, placed) and C0 >= CHROMA_FLOOR
                and lo <= L0 <= hi
                and contrast_ratio(seed, surface) >= CONTRAST_MIN):
            placed.append(seed)
            continue

        # Chroma is the third axis, and leaving it out is why constrained
        # themes fell back to a failing colour: catppuccin-latte kept its raw
        # red and the next slot could only reach #A71900, ΔE 10.0 apart. Two
        # colours of the same hue and lightness are still separable if one is
        # vivid and the other muted, and sweeping chroma is what finds that.
        best, best_score = None, -1.0
        for spin in range(0, 360, 6):
          for cmul in (1.0, 0.72, 1.35, 0.55):
            chroma = max(CHROMA_FLOOR + 0.01, C0 * cmul)
            for dl in (0.0, -0.05, 0.05, -0.10, 0.10):
                Lc = max(lo, min(hi, target_L + dl))
                hue = (H0 + spin) % 360
                # Reject anything sRGB cannot actually render at this chroma,
                # rather than accepting the washed-out colour it clamps to.
                if not in_gamut(Lc, chroma, hue):
                    continue
                cand = from_oklch(Lc, chroma, hue)
                # Rejected here rather than nudged later: a mark under 3:1 on
                # its own panel is not a mark, whatever its hue does.
                if contrast_ratio(cand, surface) < CONTRAST_MIN:
                    continue
                if not placed:
                    best = cand
                    break
                score = min(min(worst_gap(cand, o) for o in placed),
                            min(delta_e(cand, o) for o in placed) / 2.0)
                if score > best_score:
                    best, best_score = cand, score
                if separates(cand, placed):
                    best, best_score = cand, 999
                    break
            if best_score >= 999:
                break
        placed.append(best or seed)

    # REPAIR PASS.
    #
    # Placement is greedy, so a colour chosen early constrains every colour
    # after it and the last slot inherits whatever room is left. On most
    # themes that is fine; on a couple it left a pair too close and the
    # fallback took a failing colour rather than none.
    #
    # Re-walking the worst offender against ALL the others -- not just the
    # ones that happened to precede it -- costs one more sweep and rescues
    # exactly those cases. Bounded, and it only ever replaces a colour with a
    # strictly better one, so it cannot make a palette worse.
    for _round in range(3):
        bad = audit(placed, surface)
        if not bad:
            break
        worst_i, worst_score = None, 1e9
        for i, c in enumerate(placed):
            others = [o for j, o in enumerate(placed) if j != i]
            score = min([min(worst_gap(c, o), delta_e(c, o) / 2.0)
                         for o in others] or [1e9])
            if score < worst_score:
                worst_i, worst_score = i, score
        if worst_i is None:
            break
        others = [o for j, o in enumerate(placed) if j != worst_i]
        L0, C0, H0 = oklch(placed[worst_i])
        found, found_score = None, worst_score
        for spin in range(0, 360, 4):
            for cmul in (1.0, 0.7, 1.3, 0.5, 1.6):
                ch = max(CHROMA_FLOOR + 0.01, C0 * cmul)
                for Lc in [lo + (hi - lo) * k / 8.0 for k in range(9)]:
                    if not in_gamut(Lc, ch, (H0 + spin) % 360):
                        continue
                    cand = from_oklch(Lc, ch, (H0 + spin) % 360)
                    if contrast_ratio(cand, surface) < CONTRAST_MIN:
                        continue
                    sc = min(min(worst_gap(cand, o) for o in others),
                             min(delta_e(cand, o) for o in others) / 2.0)
                    if sc > found_score:
                        found, found_score = cand, sc
        if not found:
            break
        placed[worst_i] = found
    return placed


def audit(palette, surface):
    """What is still wrong, in the validator's own terms. Empty means clean."""
    out = []
    for i in range(len(palette) - 1):
        a, b = palette[i], palette[i + 1]
        g, nrm = worst_gap(a, b), delta_e(a, b)
        if g < CVD_FLOOR:
            out.append(f"{a}/{b} CVD ΔE {g:.1f} < {CVD_FLOOR}")
        if nrm < NORMAL_FLOOR:
            out.append(f"{a}/{b} normal ΔE {nrm:.1f} < {NORMAL_FLOOR}")
    for c in palette:
        if oklch(c)[1] < CHROMA_FLOOR:
            out.append(f"{c} chroma {oklch(c)[1]:.3f} reads grey")
    return out
