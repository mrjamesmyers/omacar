# OmaCar

Live OBD-II diagnostics for your car, on your Omarchy desktop.

Built for a **2015 Honda CR-Z** with a wired **OBDLink SX** on `/dev/ttyUSB0`,
but everything below P2 is generic OBD-II and works on any car built since 1996.

    ./install.sh          CLI, launcher, icon, and Omarchy menu entries
    ./install.sh --bind   also bind Super+Shift+C
    ./test/all.sh         every test — needs neither a car nor an adapter

## Status: P2 — the PID prospector

You do not need the adapter, or the car, to develop this.

    omacar setup          build the Python environment
    omacar bench start    start the ELM327 emulator (a simulated car on a pty)
    omacar doctor         adapter, protocol, supported PIDs, stored faults
    omacar live RPM SPEED stream readings to the terminal
    omacar bench stop

`doctor` against the emulator negotiates **ISO 15765-4 (CAN 11/500)** — the
same protocol Honda has used since 2008, so the bench is a fair rehearsal for
the real car.

Then the cluster itself:

    omacar daemon start   one long-lived connection, tiered polling
    omacar                open the cluster

### The ambient meter

The ring borrows the CR-Z's own language: it glows blue in NORMAL and ECON,
greens as you drive efficiently, and commits to red in SPORT. **Colour is
efficiency; the bright arc is road speed**; a slim inner arc is engine speed.

Efficiency is not a vibe. Where the ECU reports MAF and speed, OmaCar computes
real instantaneous economy — mass air flow over the stoichiometric ratio gives
fuel mass flow, and that over road speed gives L/100km — then reads it against
a band (4.5 good, 9.5 poor) tuned for this car. Only when MAF is unavailable
does it fall back to a load-and-throttle estimate, and **the status bar says
which one it used**. A gauge that looks authoritative while guessing is worse
than one that admits it estimated.

Preview it without a car: `?demo=1`, `?mode=sport`, `?units=metric`.

### One process owns the serial port

Opening an OBD connection costs 5-8 seconds. So exactly one process holds it —
the daemon — and everything else reads what it publishes: the UI polls
`/api/live`, the bar widget reads a cache. Nothing else opens a connection.

    ~/.local/state/omacar/live.json      current sample, rewritten atomically
    ~/.local/state/omacar/telemetry.db   one row per second, for trips

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

- **P3 — faults and readiness.** DTCs in plain English, freeze frames, and
  readiness monitors.

## Finding what Honda does not document

Generic OBD-II will not give you IMA state of charge, assist/regen current, or
battery temperature — those live behind manufacturer services, and no
off-the-shelf tool ships a Honda custom-PID set.

    omacar prospect                              sweep service 0x21 (Honda)
    omacar prospect --service 0x22 --range 0000-01FF
    omacar profile                               what has been learned so far

The method: sweep candidate headers against a read-only service, keep whatever
answers, then **re-sample every responder several times and diff the payloads**.
Bytes that never change are almost certainly not the reading you want; variance
is the signal. The output is a draft profile of candidates.

A responder is evidence that an address exists, not knowledge of what it means.
Every drafted entry is `confidence = "candidate"`, and **an unvalidated
candidate must never drive a gauge**. Name it, write its formula, check it
against something you can see — the dash's own SoC bars, or a second tool —
then mark it validated.

### Safety, enforced rather than documented

- **Read-only at the transport.** `lib/elm.py` holds a whitelist of services it
  will emit (0x01, 0x02, 0x03, 0x06, 0x07, 0x09, 0x21, 0x22) and raises before
  anything reaches the bus otherwise. Write (0x2E), input/output control
  (0x2F), routine control (0x31), ECU reset (0x11) and clear-DTC (0x14) cannot
  be sent by this tool at all.
- **It refuses to sweep a moving car.** Road speed is checked first; if the car
  is moving it stops, and if speed cannot be read it stops and asks you to
  confirm with `--parked` rather than assuming.
- **It refuses to fight the daemon** for the serial port.
- Rate-limited, and headers that answer nothing are abandoned early.

## Verify shader changes on the real display

The ring's fragment shader declares `precision highp float`. At `mediump` the
hash collapses on this machine's integrated GPU and the ring renders black —
and **software/headless GL renders it correctly, which hides the bug**. The
headless screenshots used during development therefore cannot prove the shader
is right; open it on the actual monitor after touching the GLSL.

## Two safety rules, baked in from the start

**Clearing a code also clears the readiness monitors**, and a car with unset
monitors fails emissions until it completes a drive cycle. Any clear action
says that before it fires.

**IMA faults touch a high-voltage system.** Read and log them; do not offer
one-click clearing of hybrid codes the way you would for a loose gas cap.

Scaffolded from [omarchy-app-template](../omarchy-app-template).
