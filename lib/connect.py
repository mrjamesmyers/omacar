"""Where OmaCar looks for a car, in order.

  1. $OMACAR_PORT              explicit override
  2. the running bench emulator
  3. a wired adapter on /dev/ttyUSB* or /dev/ttyACM*

The OBDLink SX is a wired FTDI device, so it lands on /dev/ttyUSB0. On Arch
the group that owns those nodes is `uucp`, not `dialout` — being in the wrong
group is what "permission denied" on a perfectly good adapter looks like.
"""
import atexit
import glob
import json
import grp
import os
import sys
import time

STATE = os.path.expanduser(
    os.environ.get("XDG_STATE_HOME", "~/.local/state") + "/omacar")
BENCH_PTY = os.path.join(STATE, "bench-pty")
LIVE_JSON = os.path.join(STATE, "live.json")
DAEMON_PID = os.path.join(STATE, "daemon.pid")

# THE PORT LEASE.
#
# /dev/ttyUSB0 admits exactly one process. The daemon holds it continuously to
# feed the gauge, which means `omacar doctor`, `live`, `survey` and `prospect`
# -- every one-off command -- were locked out whenever the daemon was up, and
# reported "not connected" as though the cable had failed. That is a miserable
# thing to read standing next to a running car.
#
# So: a lease. A one-off command writes this file with a deadline, the daemon
# sees it, closes its connection and waits, the command does its work, and the
# file is removed on the way out. The daemon reconnects on its own.
#
# The DEADLINE is the important half. If the command crashes or is killed, the
# file is left behind -- and without an expiry that would pause the daemon
# forever, turning a transient failure into a silent permanent one. The daemon
# ignores and clears a lease past its deadline.
PORT_YIELD = os.path.join(STATE, "port-yield")
YIELD_GRACE = 90.0          # seconds a lease may hold before the daemon takes over


def daemon_running():
    try:
        with open(DAEMON_PID, encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def daemon_yielded(since_ts=0.0):
    """Has the daemon published that it has let go?

    WATCH THE DAEMON'S OWN SIGNAL, DO NOT PROBE THE PORT.

    The first version opened the serial port to test whether it was free. That
    works, but it means every one-off command performs THREE open/close cycles
    on the ELM327 -- the probe, then python-obd's real connect, with the
    daemon's own teardown in between. An ELM327 resets on open (ATZ) and does
    not enjoy being cycled like that; the result was a doctor run that hung
    intermittently, roughly one in three.
    #
    The daemon already publishes status="yielded" into live.json when it steps
    aside, so the information is there for free and costs the adapter nothing.
    """
    # MUST BE NEWER THAN OUR REQUEST.
    #
    # Without the timestamp check this reads a "yielded" left over from the
    # PREVIOUS command, concludes the port is free before the daemon has even
    # seen the new lease, and opens on top of it. That produced a clean
    # alternating pass/fail across repeated runs -- every other one inherited a
    # stale all-clear.
    try:
        if os.path.getmtime(LIVE_JSON) < since_ts:
            return False
        with open(LIVE_JSON, encoding="utf-8") as f:
            return json.load(f).get("status") == "yielded"
    except (OSError, ValueError):
        # No live.json means nothing is holding the port anyway.
        return True


def request_port(port, timeout=12.0):
    """Ask a running daemon to let go, and wait until it has.

    Returns True when the port is ours to open. Safe to call when no daemon is
    running: it notices, writes nothing, and returns immediately.
    """
    if not daemon_running():
        return True
    try:
        with open(PORT_YIELD, "w", encoding="utf-8") as f:
            f.write(str(time.time() + YIELD_GRACE))
    except OSError:
        return False
    asked_at = time.time()
    deadline = asked_at + timeout
    while time.time() < deadline:
        if daemon_yielded(asked_at):
            # LET THE ADAPTER BREATHE.
            #
            # python-obd opens with ATZ, a chip reset that takes a second or
            # two to answer. Handing the port straight over means that reset
            # lands while the ELM327 is still tearing down the previous
            # session, and it can simply not reply -- which the caller then
            # reports as a car that will not talk. Observed with three
            # connect/disconnect cycles inside twenty seconds.
            time.sleep(0.6)
            _start_heartbeat()
            return True
        time.sleep(0.3)
    release_port()
    return False


_HEARTBEAT = {"stop": None}


def _start_heartbeat(interval=25.0):
    """Keep the lease alive for as long as this process is using the port.

    YIELD_GRACE exists so a crashed command cannot pause the gauge forever, but
    a fixed deadline also kills long jobs: `omacar prospect` sweeps 1536
    requests over several minutes, and at 90 seconds the daemon reasonably
    concluded the lease was abandoned and took the port back mid-sweep --
    surfacing as "device reports readiness to read but returned no data
    (multiple access on port?)".
    A heartbeat gives both: the deadline stays short, so a dead process is
    noticed quickly, while a live one keeps pushing it forward.
    """
    import threading
    stop = threading.Event()

    def beat():
        while not stop.wait(interval):
            try:
                with open(PORT_YIELD, "w", encoding="utf-8") as f:
                    f.write(str(time.time() + YIELD_GRACE))
            except OSError:
                return

    threading.Thread(target=beat, daemon=True).start()
    _HEARTBEAT["stop"] = stop


def release_port():
    if _HEARTBEAT["stop"] is not None:
        _HEARTBEAT["stop"].set()
        _HEARTBEAT["stop"] = None
    try:
        os.remove(PORT_YIELD)
    except OSError:
        pass


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


# Baud rates an ELM327 might be speaking, in the order worth trying.
#
# 38400 first because that is the OBDLink SX default and what this project was
# built against -- trying it first keeps the common case as fast as it was.
# 115200 second because it is the OBDLink EX default, and an EX asked at 38400
# answers with line noise rather than silence, which python-obd reports as
# NOT_CONNECTED with 0 supported commands. That failure looks exactly like a
# dead adapter or a car with the ignition off, which is a miserable thing to
# debug in a car park.
BAUD_CANDIDATES = (38400, 115200, 500000, 230400, 9600)


BAUD_CACHE = os.path.join(STATE, "baud")


def _cached_baud(port):
    """The rate this port answered on last time, if it is still the same port.

    Detection costs up to five serial opens with a timeout each -- around eight
    seconds. That is fine once, and far too slow on every command: it pushed
    daemon startup past the ten-second window `omacar daemon start` waits for a
    pidfile, so the daemon was reported as failing when it was merely slow.
    An adapter does not change its baud between runs, so remember it.
    """
    try:
        with open(BAUD_CACHE, encoding="utf-8") as f:
            cached_port, baud = f.read().split(None, 1)
        return int(baud) if cached_port == port else None
    except (OSError, ValueError):
        return None


def _remember_baud(port, baud):
    try:
        with open(BAUD_CACHE, "w", encoding="utf-8") as f:
            f.write("%s %d" % (port, baud))
    except OSError:
        pass


def detect_baud(port, candidates=BAUD_CANDIDATES, use_cache=True):
    """The rate this adapter actually answers on, or None.

    Asks ATI and looks for "ELM" in the reply. Cheap -- a wrong rate either
    returns nothing or returns bytes that cannot contain the string.
    """
    import time
    try:
        import serial
    except ImportError:
        return None

    if use_cache:
        hit = _cached_baud(port)
        if hit:
            # Trust it, but verify cheaply -- a different adapter on the same
            # path would otherwise be talked to at the wrong rate forever.
            try:
                with serial.Serial(port, hit, timeout=0.8) as s:
                    s.reset_input_buffer(); s.write(b"ATI\r"); time.sleep(0.4)
                    if b"ELM" in s.read(200).upper():
                        return hit
            except Exception:                                 # noqa: BLE001
                pass

    for baud in candidates:
        try:
            with serial.Serial(port, baud, timeout=1.0) as s:
                s.reset_input_buffer()
                s.write(b"\r")
                time.sleep(0.2)
                s.reset_input_buffer()
                s.write(b"ATI\r")
                time.sleep(0.5)
                if b"ELM" in s.read(200).upper():
                    _remember_baud(port, baud)
                    return baud
        except Exception:
            continue
    return None


def connect(timeout=3, fast=False, lease=True):
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

    # Take the lease before opening anything. Every one-off command reaches the
    # car through here, so doing it once covers doctor, live, survey and
    # prospect alike -- and the bench emulator, which has no daemon, skips it
    # because daemon_running() is false.
    # lease=False for the daemon itself: it IS the holder, and asking itself to
    # let go would write a lease it then waits on forever.
    if lease and kind == "wired" and not request_port(port):
        sys.exit("omacar: the daemon is holding " + port + " and did not let go.\n"
                 "  stop it with: omacar daemon stop")
    # Give it back on the way out, however this process ends. Without this a
    # command that raises leaves the daemon paused until the lease expires.
    if lease:
        atexit.register(release_port)
    # OMACAR_BAUD wins if set; otherwise ask the adapter. Falling back to
    # 38400 keeps the original behaviour when detection cannot run (no
    # pyserial, or a port that will not open twice).
    override = os.environ.get("OMACAR_BAUD")
    if override:
        baud = int(override)
    else:
        baud = detect_baud(port) or 38400

    conn = obd.OBD(port, baudrate=baud, fast=fast, timeout=timeout)
    return conn, port, kind
