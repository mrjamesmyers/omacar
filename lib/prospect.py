"""omacar prospect — find the manufacturer PIDs nobody documents.

Generic OBD-II will not tell you a CR-Z's IMA state of charge, assist/regen
current, or battery temperature. Those live behind Honda-specific services,
and no off-the-shelf tool ships a Honda custom-PID set. So: ask the ECU
directly, and record what answers.

Method
------
1. Sweep candidate headers x PIDs with a read-only service (0x21 or 0x22).
2. Anything that answers positively is a responder.
3. Re-sample every responder several times with the engine running, and diff
   the payloads. **Bytes that never change are almost certainly not the
   reading you want.** Variance is the signal.
4. Draft a profile of candidates for a human to name and validate.

Nothing here is authoritative. A responder is evidence that an address
exists, not knowledge of what it means — the draft profile says so, and the
cluster refuses to display an unvalidated candidate.
"""
import atexit
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import connect  # noqa: E402
import elm as elmlib  # noqa: E402
import profile as profilelib  # noqa: E402

# Honda 11-bit diagnostic addresses. 7E0/7E8 is the engine pair; hybrids put
# the motor and battery controllers on the neighbouring addresses.
DEFAULT_HEADERS = ["07E0", "07E1", "07E2", "07E3", "07E4", "07E5"]

DIM, BOLD, GREEN, YELLOW, RESET = "\033[2m", "\033[1m", "\033[32m", "\033[33m", "\033[0m"


def parse_range(spec, width):
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return range(int(lo, 16), int(hi, 16) + 1)
    return range(0, 1 << (4 * width))


def moving(el):
    """True if the car reports any road speed. Refuse to sweep if so.

    The broadcast header comes from the protocol rather than being assumed.
    "07DF" is the 11-bit CAN functional address and it is the wrong shape on a
    29-bit car -- which is every Honda this project has touched. set_header()
    rightly refuses it, so the safety check that exists to stop a sweep while
    the car is moving was instead crashing `omacar dtc` before it could read
    anything at all.
    """
    try:
        import protocols
        el.set_header(protocols.broadcast(getattr(el, "protocol", None)))
    except Exception:
        el.set_header("07DF")
    kind, _, data = elmlib.classify(el.request("010D"), 0x01, "010D")
    if kind != "positive" or len(data) < 6:
        return None                      # cannot tell — caller decides
    try:
        return int(data[4:6], 16) > 0
    except ValueError:
        return None


def sweep(el, headers, service, pids, delay, on_progress):
    found, tried = [], 0
    total = len(headers) * len(pids)
    for header in headers:
        el.set_header(header)
        dead = 0
        for pid in pids:
            req = f"{service:02X}{pid:0{4 if service == 0x22 else 2}X}"
            kind, detail, data = elmlib.classify(el.request(req), service, req)
            tried += 1
            on_progress(tried, total, header, req, kind)
            if kind == "positive":
                found.append({"header": header, "service": service,
                              "pid": f"{pid:X}", "request": req, "sample": data,
                              "payload_len": max(0, (len(data) - 4) // 2)})
                dead = 0
            elif kind == "silent":
                dead += 1
                # A header that has answered nothing at all is not there.
                if dead >= 24 and not any(f["header"] == header for f in found):
                    on_progress(tried, total, header, req, "skip")
                    break
            time.sleep(delay)
    return found


def resample(el, found, rounds, delay, on_progress):
    """Re-read every responder and mark which byte offsets actually move."""
    series = {id(f): [f["sample"]] for f in found}
    for r in range(rounds):
        for f in found:
            el.set_header(f["header"])
            kind, _, data = elmlib.classify(el.request(f["request"]), f["service"], f["request"])
            series[id(f)].append(data if kind == "positive" else "")
            time.sleep(delay)
        on_progress(r + 1, rounds, "", "", "resample")
    for f in found:
        samples = [s for s in series[id(f)] if s]
        varying = []
        if len(samples) > 1:
            n = min(len(s) for s in samples)
            for i in range(4, n, 2):          # skip the service+pid echo
                if len({s[i:i + 2] for s in samples}) > 1:
                    varying.append((i - 4) // 2)
        f["varying"] = varying
        f["samples"] = samples[:8]
    return found


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="omacar prospect", add_help=True)
    ap.add_argument("--service", default="0x21",
                    help="read-only service to sweep: 0x21 (Honda) or 0x22 (UDS)")
    ap.add_argument("--headers", default=",".join(DEFAULT_HEADERS))
    ap.add_argument("--range", dest="rng", default="",
                    help="PID range in hex, e.g. 00-FF or 0000-01FF")
    ap.add_argument("--delay", type=float, default=0.06)
    ap.add_argument("--rounds", type=int, default=6, help="resamples per responder")
    ap.add_argument("--car", default="honda-crz-2015")
    ap.add_argument("--parked", action="store_true",
                    help="confirm the car is parked when road speed cannot be read")
    args = ap.parse_args(argv)

    service = int(args.service, 16)
    if service not in elmlib.READ_ONLY_SERVICES:
        sys.exit(f"omacar: service {args.service} is not read-only; refusing.")

    port, kind = connect.resolve()
    if not port:
        sys.exit("omacar: no adapter and no bench emulator.")
    warn = connect.serial_group_warning(port)
    if warn:
        sys.exit("omacar: " + warn)
    # Take the port lease rather than refusing outright.
    #
    # prospect drives elm.py directly instead of going through
    # connect.connect(), so it did not inherit the handoff that doctor, live
    # and survey get -- it just told you to stop the daemon. Same lease, same
    # deadline, released on the way out however this exits: a sweep that dies
    # halfway must not leave the gauge paused.
    if not connect.request_port(port):
        sys.exit("omacar: the daemon is holding " + port + " and did not let go.\n"
                 "  stop it with: omacar daemon stop")
    atexit.register(connect.release_port)

    headers = [h.strip().upper() for h in args.headers.split(",") if h.strip()]
    width = 2 if service == 0x22 else 1
    pids = parse_range(args.rng, width) if args.rng else parse_range("00-FF", 1) \
        if service != 0x22 else parse_range("0000-00FF", 2)

    # The OBDLink EX runs at 115200; elm.py defaults to 38400, which is the SX.
    # Asked at the wrong rate an EX returns line noise rather than silence, so
    # a sweep would record "no responder" for every PID on the car.
    el = elmlib.Elm(port, baudrate=(connect.detect_baud(port) or 38400))
    print(f"\n  {BOLD}OmaCar prospector{RESET}  {DIM}{port} ({kind}){RESET}")
    el.init()

    # Pace the sweep for the wire it is actually on.
    #
    # These timings were tuned on 500 kbaud CAN. ISO 9141-2 runs at 10.4 kbaud
    # and needs an order of magnitude longer before silence means anything --
    # applied unchanged, a healthy slow car times out on every request and
    # reports as having nothing to say.
    import protocols
    prof = protocols.describe(el.protocol)
    pace = protocols.pacing(el.protocol)
    if prof:
        print(f"  {DIM}{protocols.summary(el.protocol)}{RESET}")
        if not prof["verified"]:
            print(f"  {YELLOW}This protocol has not been tested by this "
                  f"project.{RESET} Results are worth reporting either way.")
    if args.delay == 0.06:            # untouched default: follow the protocol
        args.delay = pace["delay"]
    if pace.get("atst"):
        try:
            el.set_timeout(int(pace["atst"], 16) * 4)
        except (ValueError, AttributeError, TypeError):
            pass

    # The safety gate. A sweep floods the bus with unknown requests; doing
    # that while the car is moving is not a risk worth taking for data.
    if kind == "bench":
        print(f"  {DIM}bench emulator — vehicle-motion gate does not apply{RESET}")
    else:
        mv = moving(el)
        if mv:
            el.close()
            sys.exit("\n  refusing to sweep: the car reports road speed.\n"
                     "  Park it, leave the engine running, and try again.\n")
        if mv is None and not args.parked:
            el.close()
            sys.exit("\n  refusing to sweep: road speed could not be read, so I\n"
                     "  cannot tell whether the car is moving.\n\n"
                     "  If it is parked with the engine running, say so:\n"
                     "      omacar prospect --parked\n")

    # The sweep is the long one, so it is the one that can flatten the battery.
    # See lib/dtc.py for why this exists.
    import dtc as dtclib
    v = dtclib.battery_volts(el)
    if v is not None:
        print(f"  battery {v:.1f} V")
        if v < dtclib.LOW_VOLTS:
            el.close()
            sys.exit(f"\n  refusing to sweep: {v:.1f} V is too low for a key-on\n"
                     f"  session. Start the engine, or charge the battery.\n")

    print(f"  service 0x{service:02X} · {len(headers)} headers · "
          f"{len(pids)} pids · {len(headers) * len(pids)} requests")
    print(f"  {DIM}read-only services only; writes are refused at the transport{RESET}\n")

    last = [0.0]
    started = [time.time()]
    hits = [0]

    def _dur(secs):
        secs = int(max(0, secs))
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m{secs % 60:02d}s"
        return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"

    def progress(i, total, header, req, kind_):
        now = time.time()
        if kind_ == "positive":
            hits[0] += 1
        if kind_ in ("positive", "skip") or now - last[0] > 0.5:
            last[0] = now
            pct = 100.0 * i / max(1, total)
            mark = {"positive": GREEN + "hit " + RESET, "skip": DIM + "skip" + RESET,
                    "resample": DIM + "diff" + RESET}.get(kind_, "    ")

            # AN ETA, BECAUSE THESE RUNS ARE LONG.
            #
            # A bare percentage is fine for something that takes ten seconds.
            # A full 16-bit range on one ECU is over two hours, and without a
            # remaining-time figure there is no way to tell a slow sweep from a
            # stuck one -- or to decide whether it is worth starting before
            # you need the car back. Measured from actual elapsed time rather
            # than a per-request constant, so a bus that slows down is
            # reflected rather than hidden.
            elapsed = now - started[0]
            rate = i / elapsed if elapsed > 0.5 else 0
            eta = f" · {_dur((total - i) / rate)} left" if rate > 0 else ""
            found_s = f" · {hits[0]} hit{'' if hits[0] == 1 else 's'}" if hits[0] else ""

            sys.stdout.write(
                f"\r  {pct:5.1f}%  {header:<9} {req:<7} {mark}"
                f"{DIM}{_dur(elapsed)} elapsed{eta}{found_s}{RESET}\033[K")
            sys.stdout.flush()

    found = sweep(el, headers, service, list(pids), args.delay, progress)
    print(f"\r\033[K  {len(found)} responder(s)\n")

    if found:
        print(f"  resampling {len(found)} responder(s) x{args.rounds} to find "
              f"which bytes move…")
        resample(el, found, args.rounds, args.delay, progress)
        print("\r\033[K", end="")
    el.close()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw = os.path.join(connect.STATE, f"prospect-{stamp}.json")
    os.makedirs(connect.STATE, exist_ok=True)
    with open(raw, "w", encoding="utf-8") as f:
        json.dump({"port": port, "service": service, "headers": headers,
                   "found": found}, f, indent=2)

    live = [f for f in found if f.get("varying")]
    print(f"  {BOLD}Results{RESET}\n")
    for f in found:
        v = f.get("varying") or []
        tag = f"{GREEN}{len(v)} byte(s) move{RESET}" if v else f"{DIM}static{RESET}"
        print(f"    {f['header']}  {f['request']:<6} len={f['payload_len']:<3} {tag}")
    print()

    draft = profilelib.write_draft(
        os.path.join(connect.STATE, "profiles", args.car + ".draft.toml"),
        {"slug": args.car, "description": "drafted by omacar prospect",
         "protocol": "ISO 15765-4 (CAN 11/500)", "discovered": stamp},
        live or found)

    print(f"  raw log   {raw}")
    print(f"  draft     {draft}")
    print(f"\n  {YELLOW}Every entry is a candidate.{RESET} Name it, write its formula,")
    print("  check it against the dash, then set confidence = \"validated\".\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
