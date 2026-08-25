"""Car profiles: manufacturer-specific PIDs OmaCar has learned.

Read with tomllib (stdlib since 3.11), written by hand-rolled formatting.
No YAML dependency — the schema is small and the file is meant to be edited
by a person after the prospector drafts it.
"""
import os
import tomllib

PROFILE_DIRS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles"),
    os.path.expanduser(
        os.environ.get("XDG_STATE_HOME", "~/.local/state") + "/omacar/profiles"),
]


def load(slug):
    for d in PROFILE_DIRS:
        p = os.path.join(d, slug + ".toml")
        if os.path.exists(p):
            with open(p, "rb") as f:
                return tomllib.load(f), p
    return None, None


def available():
    out = []
    for d in PROFILE_DIRS:
        if os.path.isdir(d):
            out += [f[:-5] for f in sorted(os.listdir(d)) if f.endswith(".toml")]
    return sorted(set(out))


def _q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def write_draft(path, car, findings):
    """Draft a profile from prospector findings. Every entry is a candidate
    until a human validates it against something real — the schema says so."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [
        "# OmaCar profile — DRAFT, written by `omacar prospect`.",
        "#",
        "# Every entry below is a *candidate*: the ECU answered, and the bytes",
        "# marked `varies` changed between samples. That is evidence, not",
        "# meaning. Name it, write its formula, check it against something you",
        "# can see (the dash, a second tool), then set confidence = \"validated\".",
        "# An unvalidated candidate must not drive a gauge.",
        "",
        "[car]",
        f"slug = {_q(car.get('slug', 'unknown'))}",
        f"description = {_q(car.get('description', ''))}",
        f"protocol = {_q(car.get('protocol', ''))}",
        f"discovered = {_q(car.get('discovered', ''))}",
        "",
    ]
    for f in findings:
        lines += [
            "[[pid]]",
            f"name = {_q(f.get('name') or 'unnamed_' + f['header'] + '_' + f['pid'])}",
            f"header = {_q(f['header'])}",
            f"service = 0x{f['service']:02X}",
            f"request = {_q(f['request'])}",
            f"response = {_q(f.get('sample', ''))}",
            f"payload_len = {f.get('payload_len', 0)}",
            "varying_bytes = [" + ", ".join(str(b) for b in f.get("varying", [])) + "]",
            'formula = ""            # e.g. "A", "A*100/255", "(A*256+B)/10"',
            'unit = ""',
            'confidence = "candidate"',
            'validated_against = ""',
            "",
        ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path
