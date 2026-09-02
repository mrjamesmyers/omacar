# OmaCar — Roadmap

## The goal

**Make the best vehicle diagnostic tool in the world free, and make it run on a
laptop somebody already owns.**

Professional diagnostics is one of the last consumer-adjacent fields still gated
by five-figure hardware. Flagship scan tools from Snap-on, Autel and Launch run
from the low thousands to well over ten thousand dollars, plus an annual
subscription to keep vehicle coverage current. Every one of them is a mid-range
Android tablet in a rubber case, running software, talking to an interface that
costs tens of dollars over a standard connector.

*(Figures throughout are indicative rather than quoted. Prices vary by
territory, bundle and dealer, and none of them are cited here from a price
list. The argument does not depend on the exact number — it depends on the
ratio, which is not close.)*

You are not paying for the tablet. You are paying for **coverage**: thousands of
engineer-years spent working out what identifier means what on which model. That
is the moat, and it is the only real one.

This document is about how a free tool takes it.

---

## Why this is winnable

Four asymmetries, and the third is the whole strategy.

**1. The hardware advantage is gone.** The compute in these tablets is weaker
than the second-hand laptop this was developed on. The interface is an ELM327
or STN chipset costing tens of dollars. There is nothing in the box worth four
figures.

**2. Their software is worse than it should be.** These are single-vendor
codebases under decade-old assumptions, with no plugin story, no scripting, and
no way to open them up. Data lands in a proprietary format on a device that
stops getting updates when the vendor decides. That is the same trap this
project was started to escape.

**3. Coverage is expensive per-vendor and nearly free per-community.** Sweeping
the full manufacturer identifier range takes about **70 minutes per car** — but
only **once per model**, if the result is shared. Snap-on pays engineers to do
this behind closed doors, once, per make, and rents it back. A community does it
in parallel, for free, and every owner of that model inherits it. **A hundred
CR-Z owners running one sweep each is a coverage database no vendor can price
against, because their cost floor is salaries and ours is zero.**

**4. We can be honest in ways a product with a price tag cannot.** A tool that
must justify a subscription has an incentive to look confident. This one can
label a guess a guess, say "this came from cache", and refuse to run.

### What we do not pretend

Being credible means naming what is genuinely hard, gated, or off the table.

- **Repair information** (ALLDATA, Mitchell1, wiring diagrams, OEM procedures) is
  licensed content. We will never clone it. We can link out, and we can let
  people attach their own notes to a vehicle.
- **Immobilizer and key programming** requires OEM security algorithms, is
  region-regulated, and is the single most abused capability in this market.
  Out of scope, deliberately, and not a coverage gap we intend to close.
- **ECU reflashing** needs manufacturer-signed images and, in most markets now, an
  OEM subscription plus a J2534 device. Not implemented; see Principles.
- **Security gateways** (FCA SGW, and equivalents spreading across other makes)
  require authenticated access to write to a modern vehicle at all. Read access
  is often unaffected. Where a gateway blocks us, we say so plainly rather than
  looking broken.
- **ADAS calibration** needs physical targets and a level floor. Software alone
  cannot do it.
- **Oscilloscope and multimeter** work needs hardware we do not ship. We can
  integrate with things people already own.

Everything else these tools do is reachable.

---

## Where we are

~13,600 lines. One vehicle validated end to end (2015 Honda CR-Z), on real
hardware, over a real adapter.

**Working**
- Live gauge cluster and drive mode, ~10 Hz
- Full system scan: 108 generic PIDs, readiness monitors, freeze frame, Mode 06
- Fault codes with severity, system grouping and plain-language explanation
- Drive logging to SQLite, trip history validated against the odometer
- Multi-vehicle garage — one database per VIN, automatic switching, driver names
- `prospect` — read-only manufacturer PID discovery, motion-gated, voltage-gated
- `dtc` — UDS 0x19 fault-catalogue reader (**where the Honda data actually was**)
- `dtclog` — DTC status sampling across a whole drive
- `learn` — module discovery that accumulates across passes
- **Write mode** — clear codes, functional tests, settings writes; disarmed by
  default, consequences stated before sending
- Learn mode, onboarding, in-car hub layout, Omarchy Radio
- Quickshell plugin: bar icon, panel, start/stop, live status
- **Replay** — scrub a recorded drive, read every channel at any instant, CSV export
- **Shareable profile format** with per-entry provenance and merge rules (2.1)
- **Automatic discovery** that resumes across drives and gates itself on the
  alternator (2.2)
- **Validation by correlation** against trusted channels, which refuses when the
  data cannot distinguish two explanations (2.3)
- **Protocol awareness** for pre-CAN vehicles — header shapes, framing, pacing
  and which services are worth asking (2.5, untested on a pre-CAN car)

**Honest limits**
- One validated vehicle profile
- Manufacturer identifier space is ~4.5% explored on that one car
- No coverage for any other make
- Pre-CAN support is written from the ELM327 datasheet and the ISO documents,
  and **has never been run against a pre-CAN car**. Every protocol entry says so.
- Nothing in `resets.json` or `procedures.json` is `verified` yet: verified means
  somebody ran it on a real car, and nobody has.

---

## Phase 1 — A complete tool for one car

*Everything a home mechanic needs, done properly, before breadth.*

**1.1 Service resets.** The single most requested workshop function and the
thing that most often forces a DIY owner to pay a shop: oil life, electronic
parking brake retract, steering angle sensor, TPMS relearn, battery
registration, DPF regeneration, throttle body relearn. Each is a routine control
(0x31) call with per-make parameters. **This is the highest-value item on the
entire roadmap per hour of work.**

**1.1b Owner procedures. — DONE.** A large share of what people buy a scan tool for is
not a diagnostic operation at all — Honda's oil life reset is buttons on the
instrument cluster, TPMS calibration is a settings menu, key fob resync is an
ignition sequence. An expensive tablet does these no better than a person with
the right instructions, and often does not do them at all. Because nothing is sent
to the vehicle, these carry a *different risk profile* from routine control and
therefore a lower evidence bar: a wrong entry wastes an afternoon rather than
commanding an actuator. Shipped in `share/data/procedures.json`.

**1.2 Bi-directional test UI.** The write path exists; it needs a screen.
Actuator tests with a physical-safety confirmation, live feedback, and an
always-visible release control.

**1.3 Live data that earns its name. — MOSTLY DONE.** Multi-PID graphing,
recording, and replay with a scrubber: done. CSV export: done. Snapshot-on-
trigger, so an intermittent fault is captured without anybody watching: not yet.

**1.4 Guided diagnosis.** For a stored code: what it means, the usual causes
ranked, which live values discriminate between them, and what to test next.
This is the "SureTrack" feature, and it is where an LLM is genuinely better than
a static database — it can reason over *this* car's actual live data.

**1.5 Reports.** A PDF a mechanic or a buyer will take seriously.

## Phase 2 — Coverage, the actual moat

*The hard problem. Everything here is in service of it.*

**2.1 A profile format worth sharing. — DONE.** Versioned, checksummed (for
integrity — explicitly *not* a signature, which would need a key story this
project does not have), with provenance per entry: who found it, on which model year, validated against a physical gauge or
merely observed to vary. **Confidence is a field, not a footnote.**

**2.2 Automated discovery. — DONE.** Today a sweep is a person deciding to run one.
It should be: plug in, and OmaCar quietly maps what it has not seen — resuming
across drives, never while moving, never below the voltage floor.

**2.3 Validation without a lab. — DONE.** A candidate becomes validated when it tracks
something we already trust: correlate an unknown byte against a known PID, a
GPS speed, an ambient temperature. Anything that moves with coolant temperature
across three drives is coolant temperature.

**2.4 Cross-model inference.** Manufacturers reuse identifier maps across models
and years far more than they admit. A validated Honda map is a strong prior for
every other Honda of that era. This is where a shared database compounds:
**coverage grows faster than the number of contributors.**

**2.5 Protocol breadth. — WRITTEN, UNTESTED.** J1850 PWM/VPW, ISO 9141-2 and KWP2000 for pre-CAN
vehicles; J1939 for trucks. Old vehicles are exactly the ones nobody will spend
thousands of dollars to diagnose.

## Phase 3 — OmaCar Cloud (Rails)

*The local app has no server and never will need one. This is additive.*

The daemon writes JSON; the app reads JSON. That seam is where a cloud companion
attaches without touching a line of protocol code — and Rails is genuinely the
right tool for it, in a way it is emphatically not for serial framing.

- **Pooled discovery** — the point of the whole phase. Contribute a sweep, receive
  everyone else's.
- Garages that outlive a reinstall; history across vehicles and people
- Longitudinal health: hybrid battery capacity trend over years, compared against
  other cars of the same model and age. **No scan tool on the market does this**,
  because none of them have a fleet.
- Shareable reports — a link for a mechanic or a buyer

**Never a dependency.** OmaCar must remain fully functional with no network, no
account, and no upstream, forever.

## Phase 4 — Professional parity

- **J2534 pass-thru** support, opening OEM-grade access on supported interfaces
- **Security gateway** handling — authenticate where legitimately possible, and
  state clearly where it is not
- **Scope integration** with hardware people already own
- **Multi-tech workflows**: a shop with several people and one vehicle history
- **Fleet mode**: the same tool for a small business with twenty vans

## Phase 5 — Past parity

*Where being software on a real computer stops being a cost saving and starts
being a different category of thing.*

- **Predictive alerts** from your own history, not a generic service interval:
  "your battery's cranking voltage has fallen 8% in four months"
- **Hands-free in the bay** — the `omawebcam` head-gesture engine already exists;
  a technician under a car with a torque wrench in each hand should be able to
  change the live data page
- **Automation** — OmaCar is a CLI first. Anything here scripts, and pipes
- **A real plugin API** so third parties extend it without forking
- **Local-first LLM** so guided diagnosis works in a rural garage with no signal

---

## How we will know it is working

Not downloads. These:

1. **Vehicles with a validated community profile.** The only number that matters.
2. **Makes with any coverage at all.** Breadth of the long tail.
3. **A repair somebody completed** that would otherwise have been a shop visit.
4. **A professional technician using it in a paid job.** The real threshold.
5. **Time from plugging into an unknown car to useful manufacturer data.** Today:
   roughly 70 minutes of sweeping. The target is *seconds*, because someone else
   already did it.

---

## Principles

Load-bearing. Several were learned by breaking something.

1. **Reads are free; writes are armed.** Writing is a first-class capability, not
   a hidden one — a tool that cannot clear a code after you fixed the fault is a
   viewer. But writes disarm themselves, refuse while the car is moving, refuse
   below 12.2 V, and state their consequences before sending.
2. **Reprogramming stays out.** Not squeamishness: 0x34/0x36/0x37 need a
   manufacturer-signed image we cannot produce, and a partial transfer leaves a
   module unable to boot. That is a tow truck, not a fault code.
3. **No build step.** ES modules from disk, Python stdlib where possible. A tool
   you cannot open and repair is the trap it was built to replace.
4. **Never invent data.** A candidate is labelled a candidate. A cached scan says
   so. A progress bar over cached results is a scan tool inventing work.
5. **Refuse when it matters, and say why.** Every guard names the incident that
   caused it. The voltage floor exists because a 25-minute key-on session tripped
   an ABS warning.
6. **The car is not urgent work.** Everything background runs `Nice=10`. An
   unthrottled poll loop crashed the compositor on a 2-core machine once already.
7. **Your data is yours, in a format you can read.** SQLite and JSON on your own
   disk. No account required, ever.

---

## The one-sentence version

*A second-hand laptop, a cheap cable, and a community that shares what it finds
should be able to out-diagnose a tool costing a hundred times as much — and
every model somebody maps makes it true for one more car.*
