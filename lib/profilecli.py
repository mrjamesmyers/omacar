"""`omacar profile` — inspect, check, merge and promote vehicle profiles.

The promote command is the important one. A prospector can only ever produce
`candidate` or `observed`; moving an entry to `validated` is a claim that a
person checked it against something real, and this is where that claim gets
made and recorded together with its evidence. Requiring `--against` is not
bureaucracy: an entry that says "validated" with no statement of what it was
validated against is indistinguishable from a guess once it reaches somebody
else's car.
"""

import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile as P  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, YELLOW, RED, BLUE = "\033[32m", "\033[33m", "\033[31m", "\033[34m"

TONE = {"validated": GREEN, "observed": BLUE, "candidate": DIM, "refuted": RED}


def _load_path(arg):
    """A slug or a path, so a downloaded file works without being installed."""
    if os.path.exists(arg):
        with open(arg, "rb") as f:
            return tomllib.load(f), arg
    return P.load(arg)


def cmd_list():
    names = P.available()
    extra = []
    d = os.path.expanduser("~/.local/state/omacar/profiles")
    if os.path.isdir(d):
        extra = [f for f in sorted(os.listdir(d)) if f.endswith(".draft.toml")]
    if not names and not extra:
        print("  no profiles yet — run: omacar prospect")
        return 0
    for n in names:
        doc, path = P.load(n)
        pids = (doc or {}).get("pid", [])
        counts = {}
        for p in pids:
            c = p.get("confidence", "candidate")
            counts[c] = counts.get(c, 0) + 1
        bits = "  ".join(f"{TONE.get(k, '')}{v} {k}{RESET}"
                         for k, v in sorted(counts.items()))
        ok, _ = P.verify(doc or {})
        seal = (f"{GREEN}✓{RESET}" if ok else
                f"{YELLOW}?{RESET}" if ok is None else f"{RED}✗{RESET}")
        print(f"  {BOLD}{n}{RESET}  {seal}  {len(pids)} pid(s)   {bits}")
    for f in extra:
        print(f"  {DIM}{f}  (draft){RESET}")
    return 0


def cmd_show(arg):
    doc, path = _load_path(arg)
    if not doc:
        print(f"  no profile {arg!r}")
        return 1
    car = doc.get("car") or {}
    meta = doc.get("meta") or {}
    print(f"\n  {BOLD}{car.get('make','?')} {car.get('model','?')}{RESET}"
          f"  {DIM}{car.get('slug','')}{RESET}")
    if car.get("years"):
        print(f"  years {car['years'][0]}–{car['years'][1]}"
              f"   vin prefix {car.get('vin_prefix') or '—'}")
    if meta.get("contributors"):
        print(f"  contributors: {', '.join(meta['contributors'])}")
    ok, why = P.verify(doc)
    print("  integrity: " + (f"{GREEN}checksum matches{RESET}" if ok
                             else f"{YELLOW}{why}{RESET}" if ok is None
                             else f"{RED}{why}{RESET}"))
    print(f"  {DIM}{path}{RESET}\n")
    for p in doc.get("pid") or []:
        c = p.get("confidence", "candidate")
        print(f"  {TONE.get(c,'')}{c:<10}{RESET} {p.get('id','')}")
        print(f"    {p.get('header','')}  {p.get('request','')}"
              f"   {p.get('name') or DIM + 'unnamed' + RESET}"
              f"   {p.get('formula') or ''} {p.get('unit') or ''}")
        prov = p.get("provenance") or {}
        found = f"{prov.get('found_by','?')} on {prov.get('found_on','?')}"
        print(f"    {DIM}found by {found}{RESET}")
        if prov.get("validated_against"):
            print(f"    {DIM}validated against {prov['validated_against']}"
                  f" by {prov.get('validated_by','?')}{RESET}")
        if c == "refuted":
            print(f"    {DIM}refuted: {prov.get('note') or 'no reason given'}{RESET}")
    return 0


def cmd_check(arg):
    doc, path = _load_path(arg)
    if not doc:
        print(f"  no profile {arg!r}")
        return 1
    ok, why = P.verify(doc)
    probs = P.problems(doc)
    print(f"\n  {BOLD}{path}{RESET}")
    print("  integrity: " + (f"{GREEN}ok{RESET}" if ok
                             else f"{YELLOW}{why}{RESET}" if ok is None
                             else f"{RED}{why}{RESET}"))
    if not probs:
        print(f"  {GREEN}no problems{RESET} — safe to share\n")
        return 0
    print(f"  {YELLOW}{len(probs)} problem(s):{RESET}")
    for p in probs:
        print(f"    - {p}")
    print()
    return 1


def cmd_merge(base_arg, incoming_arg, out=None):
    base, bpath = _load_path(base_arg)
    inc, ipath = _load_path(incoming_arg)
    if not base or not inc:
        print("  need two profiles")
        return 1
    ok, why = P.verify(inc)
    if ok is False:
        print(f"  {RED}refusing to merge: {why}{RESET}")
        print("  The incoming file does not match its own checksum, so it was "
              "altered after it was written.")
        return 1
    doc, notes = P.merge(base, inc)
    dest = out or bpath
    P.write(dest, doc)
    print(f"\n  merged {ipath}\n     into {dest}\n")
    for n in notes:
        print(f"    {n}")
    print()
    return 0


def cmd_promote(arg, pid_id, against, who=None):
    """Move one entry to `validated`, recording what it was checked against."""
    doc, path = _load_path(arg)
    if not doc:
        print(f"  no profile {arg!r}")
        return 1
    import time
    hit = None
    for p in doc.get("pid") or []:
        if p.get("id") == pid_id:
            hit = p
            break
    if not hit:
        print(f"  no entry with id {pid_id!r}")
        return 1
    if not hit.get("formula"):
        # A validated entry drives a display. Without a formula there is
        # nothing to drive it with, and "validated" would mean only that some
        # bytes moved -- which is what `observed` already says.
        print(f"  {YELLOW}{pid_id} has no formula.{RESET}")
        print("  Write one first: an entry cannot be validated as a reading if")
        print("  there is no reading to check. Edit the file and set e.g.")
        print('      formula = "(A*256+B)/10"')
        return 1
    prov = hit.setdefault("provenance", {})
    hit["confidence"] = "validated"
    prov["validated_by"] = who or os.environ.get("USER") or "unknown"
    prov["validated_on"] = time.strftime("%Y-%m-%d")
    prov["validated_against"] = against
    P.write(path, doc)
    print(f"\n  {GREEN}{pid_id} is now validated{RESET}")
    print(f"  against: {against}")
    print(f"  {DIM}{path}{RESET}\n")
    return 0


def cmd_refute(arg, pid_id, why, who=None):
    doc, path = _load_path(arg)
    if not doc:
        print(f"  no profile {arg!r}")
        return 1
    import time
    for p in doc.get("pid") or []:
        if p.get("id") == pid_id:
            p["confidence"] = "refuted"
            prov = p.setdefault("provenance", {})
            prov["refuted_by"] = who or os.environ.get("USER") or "unknown"
            prov["refuted_on"] = time.strftime("%Y-%m-%d")
            prov["note"] = why
            P.write(path, doc)
            print(f"\n  {RED}{pid_id} marked refuted{RESET}\n  {why}\n")
            print(f"  {DIM}Kept rather than deleted, so nobody rediscovers it.{RESET}\n")
            return 0
    print(f"  no entry with id {pid_id!r}")
    return 1


def cmd_migrate(arg, make=None, model=None, who=None):
    """Bring a pre-schema draft up to schema 1.

    Old drafts carry the findings but none of the provenance, and there is no
    way to invent it after the fact -- we do not know who ran that sweep or
    what they checked it against. So migration fills in what it can (the
    entries, their varying bytes, an id derived from header+request) and
    marks the rest unknown rather than guessing. An entry that arrives without
    provenance is honestly provenance-less.
    """
    doc, path = _load_path(arg)
    if not doc:
        print(f"  no profile {arg!r}")
        return 1
    if doc.get("schema") == P.SCHEMA:
        print(f"  {path} is already schema {P.SCHEMA}")
        return 0
    car = dict(doc.get("car") or {})
    car.setdefault("make", make or "")
    car.setdefault("model", model or "")
    old_desc = car.get("description") or ""
    pids = []
    for p_ in doc.get("pid") or []:
        varying = p_.get("varying_bytes") or []
        pids.append({
            "id": f"{p_.get('header','')}_{p_.get('request','')}".lower(),
            "name": "" if str(p_.get("name","")).startswith("unnamed_") else p_.get("name",""),
            "header": p_.get("header",""), "request": p_.get("request",""),
            "service": p_.get("service"), "payload_len": p_.get("payload_len"),
            "varying_bytes": varying,
            "formula": p_.get("formula") or "", "unit": p_.get("unit") or "",
            "confidence": "observed" if varying else "candidate",
            "provenance": {
                "found_by": who or "unknown",
                "found_on": old_desc or car.get("slug") or "unknown vehicle",
                "method": "migrated from a pre-schema draft",
                "first_seen": (doc.get("car") or {}).get("discovered", "")[:8] or "",
                "note": "provenance was not recorded before schema 1",
            },
        })
    out = {"schema": P.SCHEMA, "car": car,
           "meta": {"contributors": [who or "unknown"]}, "pid": pids}
    dest = path.replace(".draft.toml", ".toml")
    P.write(dest, out)
    print(f"\n  migrated {len(pids)} entries")
    print(f"     from {path}\n       to {dest}\n")
    probs = P.problems(out)
    if probs:
        print(f"  {YELLOW}still needs attention:{RESET}")
        for q in probs:
            print(f"    - {q}")
        print()
    return 0


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="omacar profile", add_help=True)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    s = sub.add_parser("show");  s.add_argument("profile")
    s = sub.add_parser("check"); s.add_argument("profile")
    s = sub.add_parser("merge")
    s.add_argument("base"); s.add_argument("incoming"); s.add_argument("--out")
    s = sub.add_parser("promote")
    s.add_argument("profile"); s.add_argument("id")
    s.add_argument("--against", required=True,
                   help="what you checked it against — a dash gauge, a second "
                        "tool, a physical change you made")
    s.add_argument("--by")
    s = sub.add_parser("migrate")
    s.add_argument("profile"); s.add_argument("--make"); s.add_argument("--model")
    s.add_argument("--by")
    s = sub.add_parser("refute")
    s.add_argument("profile"); s.add_argument("id")
    s.add_argument("--why", required=True)
    s.add_argument("--by")
    args = ap.parse_args(argv)

    if args.cmd == "show":
        return cmd_show(args.profile)
    if args.cmd == "check":
        return cmd_check(args.profile)
    if args.cmd == "merge":
        return cmd_merge(args.base, args.incoming, args.out)
    if args.cmd == "promote":
        return cmd_promote(args.profile, args.id, args.against, args.by)
    if args.cmd == "migrate":
        return cmd_migrate(args.profile, args.make, args.model, args.by)
    if args.cmd == "refute":
        return cmd_refute(args.profile, args.id, args.why, args.by)
    return cmd_list()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
