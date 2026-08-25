"""omacar live — stream readings to the terminal.

A tiered poll: the fast group is what a gauge needs to feel alive, the slow
group is what only drifts. Polling everything at gauge rate just starves the
bus and makes every reading late.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import connect  # noqa: E402

FAST = ["RPM", "SPEED", "ENGINE_LOAD", "THROTTLE_POS"]
SLOW = ["COOLANT_TEMP", "INTAKE_TEMP", "TIMING_ADVANCE", "SHORT_FUEL_TRIM_1"]
DIM, RESET, BOLD = "\033[2m", "\033[0m", "\033[1m"


def main():
    names = sys.argv[1:] or None
    conn, port, kind = connect.connect()
    import obd

    if conn.status() != obd.OBDStatus.CAR_CONNECTED:
        sys.exit(f"omacar: not connected ({conn.status()})")

    supported = {c.name for c in conn.supported_commands}
    fast = [n for n in (names or FAST) if n in supported]
    slow = [] if names else [n for n in SLOW if n in supported]
    if not fast and not slow:
        sys.exit("omacar: none of those PIDs are supported by this ECU")

    print(f"\n  {BOLD}OmaCar live{RESET}  {DIM}{port} ({kind}) — ctrl-c to stop{RESET}\n")
    values, tick = {}, 0
    try:
        while True:
            group = fast + (slow if tick % 5 == 0 else [])
            for n in group:
                r = conn.query(getattr(obd.commands, n))
                if not r.is_null():
                    values[n] = r.value
            line = "  ".join(f"{DIM}{n}{RESET} {values[n]:~P}" if hasattr(values[n], "units")
                             else f"{DIM}{n}{RESET} {values[n]}"
                             for n in group if n in values)
            print(f"\r  {line}\033[K", end="", flush=True)
            tick += 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
