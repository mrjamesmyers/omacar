# OmaCar

Live OBD-II diagnostics for your car, on your Omarchy desktop.

Built for a **2015 Honda CR-Z** with a wired **OBDLink SX** on `/dev/ttyUSB0`,
but everything below P2 is generic OBD-II and works on any car built since 1996.

    ./install.sh          CLI, launcher, icon, and Omarchy menu entries
    ./install.sh --bind   also bind Super+Shift+C
    ./test/smoke.sh       install into a scratch HOME and verify, safely

## Status: P0 — bench rig

You do not need the adapter, or the car, to develop this.

    omacar setup          build the Python environment
    omacar bench start    start the ELM327 emulator (a simulated car on a pty)
    omacar doctor         adapter, protocol, supported PIDs, stored faults
    omacar live RPM SPEED stream readings to the terminal
    omacar bench stop

`doctor` against the emulator negotiates **ISO 15765-4 (CAN 11/500)** — the
same protocol Honda has used since 2008, so the bench is a fair rehearsal for
the real car.

## Environment notes

`python-obd` is not in the Arch repos, so it lives in a venv under
`~/.local/share/omacar/venv`. `ELM327-emulator` additionally needs
`setuptools<81` and `--no-build-isolation`, because its build script still
imports `pkg_resources`, which setuptools 81 removed. `omacar setup` handles
both; that combination is the only one that installs on Python 3.14.

**On Arch the serial group is `uucp`, not `dialout`.** When the SX arrives:

    sudo usermod -aG uucp $USER    # then log out and back in

`omacar doctor` checks this and says so rather than failing with a bare
permission error.

## Where it goes next

- **P1 — the cluster.** A polling daemon at tiered rates into SQLite, and the
  CR-Z's own *ambient meter* in `share/app.html`: the ring that glows blue in
  NORMAL, greens as you drive efficiently, and turns red in SPORT. WebGL at
  `highp` — at `mediump` the hash collapses on this iGPU and renders black,
  and headless testing hides it.
- **P2 — the CR-Z profile.** IMA state of charge, assist vs. regen, and battery
  temperature live behind Honda-specific PIDs that no off-the-shelf tool ships.
  A PID prospector sweeps Mode 22 across the hybrid ECU headers, logs what
  answers, and validates candidates against the dash's own SoC bars. The output
  is `profiles/honda-crz-2015.yaml` — the part worth handing back to the CR-Z
  community.
- **P3 — faults and readiness.** DTCs in plain English, freeze frames, and
  readiness monitors.

## Two safety rules, baked in from the start

**Clearing a code also clears the readiness monitors**, and a car with unset
monitors fails emissions until it completes a drive cycle. Any clear action
says that before it fires.

**IMA faults touch a high-voltage system.** Read and log them; do not offer
one-click clearing of hybrid codes the way you would for a loose gas cap.

Scaffolded from [omarchy-app-template](../omarchy-app-template).
