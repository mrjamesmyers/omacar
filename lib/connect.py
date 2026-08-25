"""Where OmaCar looks for a car, in order.

  1. $OMACAR_PORT              explicit override
  2. the running bench emulator
  3. a wired adapter on /dev/ttyUSB* or /dev/ttyACM*

The OBDLink SX is a wired FTDI device, so it lands on /dev/ttyUSB0. On Arch
the group that owns those nodes is `uucp`, not `dialout` — being in the wrong
group is what "permission denied" on a perfectly good adapter looks like.
"""
import glob
import grp
import os
import sys

STATE = os.path.expanduser(
    os.environ.get("XDG_STATE_HOME", "~/.local/state") + "/omacar")
BENCH_PTY = os.path.join(STATE, "bench-pty")


def bench_port():
    try:
        with open(BENCH_PTY, encoding="utf-8") as f:
            port = f.read().strip()
        return port if port and os.path.exists(port) else None
    except OSError:
        return None


def wired_ports():
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


def resolve():
    """Return (port, kind) or (None, None)."""
    override = os.environ.get("OMACAR_PORT")
    if override:
        return override, "override"
    p = bench_port()
    if p:
        return p, "bench"
    w = wired_ports()
    if w:
        return w[0], "wired"
    return None, None


def serial_group_warning(port):
    """Return a hint if we plainly cannot read the device we found."""
    if not port or not os.path.exists(port) or os.access(port, os.R_OK | os.W_OK):
        return None
    try:
        owner = grp.getgrgid(os.stat(port).st_gid).gr_name
    except (KeyError, OSError):
        owner = "uucp"
    return (f"{port} is not readable by you. On Arch the serial group is "
            f"'{owner}': sudo usermod -aG {owner} $USER, then log out and back in.")


def connect(timeout=3, fast=False):
    """Connect python-obd, quietly. Exits with a useful message if it can't."""
    import logging
    logging.disable(logging.CRITICAL)
    import obd
    obd.logger.setLevel(logging.CRITICAL)

    port, kind = resolve()
    if not port:
        sys.exit("omacar: no adapter and no bench emulator.\n"
                 "  plug in an adapter, or run: omacar bench start")
    warn = serial_group_warning(port)
    if warn:
        sys.exit("omacar: " + warn)
    conn = obd.OBD(port, baudrate=38400, fast=fast, timeout=timeout)
    return conn, port, kind
