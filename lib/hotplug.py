"""Starting the daemon when the adapter appears, with and without root.

Two paths, because the good one needs a password and the useful one should not.

  The udev rule (`omacar hotplug install`) is the proper answer: the kernel
  knows the moment the device shows up, gives it a stable `/dev/obd` name, and
  asks the user's systemd to start the daemon. It needs one sudo, once.

  The watchdog does the same job without root by noticing that a serial port
  has appeared where there was not one before. It is a second or two slower and
  it cannot give the device a stable name, but it needs nothing from anybody.

Both are safe to have at once — starting a daemon that is already running is a
no-op, and that is checked before anything is spawned.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import connect   # noqa: E402
import records   # noqa: E402

RULES_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "share", "udev", "99-omacar.rules")
RULES_DST = "/etc/udev/rules.d/99-omacar.rules"


def daemon_running():
    try:
        with open(os.path.join(records.STATE, "daemon.pid")) as f:
            os.kill(int(f.read().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def sim_running():
    try:
        with open(os.path.join(records.STATE, "sim.pid")) as f:
            os.kill(int(f.read().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def adapter_present():
    """A real adapter — not the bench emulator, which is a pty we made."""
    port, kind = connect.resolve()
    return port if kind in ("wired", "override") else None


def start_daemon():
    """Best effort. The daemon owns the serial port; this only asks for it."""
    if daemon_running():
        return False
    if sim_running():
        # The simulator holds live.json. Two writers would fight, and the
        # simulator is the one somebody switched on deliberately.
        return False
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    try:
        subprocess.run([os.path.join(root, "bin", "omacar"), "daemon", "start"],
                       timeout=60, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return daemon_running()


# ---- the udev rule ---------------------------------------------------------

def installed():
    return os.path.exists(RULES_DST)


def install():
    src = os.path.abspath(RULES_SRC)
    print(f"  installing {src}\n            → {RULES_DST}")
    print("  this needs one sudo, and only once.\n")
    cmds = [
        ["sudo", "install", "-m", "644", src, RULES_DST],
        ["sudo", "udevadm", "control", "--reload-rules"],
        ["sudo", "udevadm", "trigger", "--subsystem-match=tty"],
    ]
    for c in cmds:
        r = subprocess.run(c)
        if r.returncode != 0:
            print(f"  failed: {' '.join(c)}", file=sys.stderr)
            return 1
    print("\n  done. Unplug and replug the adapter to test it.")
    return 0


def remove():
    if not installed():
        print("  not installed")
        return 0
    for c in (["sudo", "rm", "-f", RULES_DST],
              ["sudo", "udevadm", "control", "--reload-rules"]):
        subprocess.run(c)
    print("  removed")
    return 0


def status():
    port = adapter_present()
    print()
    print(f"  udev rule      {'installed' if installed() else 'not installed'
                             } ({RULES_DST})")
    print(f"  stable name    {'/dev/obd → ' + os.path.realpath('/dev/obd')
                              if os.path.exists('/dev/obd') else 'not present'}")
    print(f"  adapter        {port or 'none found'}")
    print(f"  daemon         {'running' if daemon_running() else 'not running'}")
    print(f"  simulator      {'running' if sim_running() else 'not running'}")
    if port:
        warn = connect.serial_group_warning(port)
        if warn:
            print(f"\n  {warn}")
    print()
    return 0


def main(argv):
    what = argv[0] if argv else "status"
    if what == "install":
        return install()
    if what == "remove":
        return remove()
    if what in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    return status()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
