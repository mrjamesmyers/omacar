# Finding the data your car does not advertise

Generic OBD-II is a legal minimum. It exists so an emissions inspector can plug
in any tool and get a defined set of answers, and it is deliberately narrow:
about 200 standard PIDs, aimed almost entirely at whether the engine is
polluting.

Your car measures far more than that on the same two wires. Individual hybrid
battery cell voltages. Transmission clutch pressures. Steering angle. Every
sensor the manufacturer's own dealer tool shows you for $8,000 a seat is on that
bus already — behind identifiers nobody published.

This document is how to go and find them, and what OmaCar refuses to do while
you look.

> **Read this section even if you skip the rest.** Everything here reads. None
> of it writes. That distinction is what makes this safe to try on a car you
> depend on, and the moment you start experimenting outside these tools it stops
> being true.

---

## 1. The shape of the problem

A diagnostic request has three parts:

**Who you are talking to.** Modules have addresses. On a modern CAN car the
tester sends to `18DAxxF1` and the module replies from `18DAF1xx`, where `xx`
identifies the module — `10` engine, `03` and `04` were the hybrid controllers
on our test car. On older 11-bit CAN it is `7E0`/`7E8`.

**What kind of question.** A *service*. `0x01` is generic live data. `0x22` is
"read data by identifier" — the manufacturer's own live values. `0x19` is "read
DTC information". `0x21` is an older Honda/Toyota-era read service.

**Which value.** For `0x22`, a two-byte **DID** (Data IDentifier). There are
65,536 of them and the manufacturer publishes none.

So the search is: for each module, for each service, for each identifier — does
anything come back?

## 2. Establish the module answers *at all* before sweeping it

The single most important step, and the easiest to skip.

ISO 14229 reserves `F100`–`F19F` for identification data — part numbers,
software versions, the VIN. Almost every module that speaks `0x22` answers
something in there. Sweep that range **first**, on every candidate address:

```
omacar prospect --service 0x22 --headers 18DA03F1,18DA04F1 --range F100-F1FF --parked
```

If a module answers here, it is present, powered, and speaking the service. Any
later empty result from that module is now a **fact about its DID map** rather
than an unanswered question about whether the module was ever listening.

If it answers nothing here, stop. You have the wrong address, the wrong
protocol, or a module that is asleep — and no amount of sweeping will fix any of
those.

## 3. Sweep, and know what "no" sounds like

```
omacar prospect --service 0x22 --headers 18DA03F1,18DA04F1 --range 0000-0FFF --parked
```

Three different negatives, which mean three different things:

| Reply | Meaning |
|---|---|
| `7F 22 31` requestOutOfRange | **The module is answering.** It parsed your request and says that identifier does not exist. |
| `7F 22 7E/7F` notSupportedInActiveSession | It exists, but not in the session you are in. Worth noting. |
| Silence / `NO DATA` | Nobody is listening at that address. |

An active refusal is a *good* result: it confirms the whole chain — wiring,
protocol, addressing, service — and isolates the unknown to the identifier
alone. A sweep returning thousands of `requestOutOfRange` has proven the map is
empty there. A sweep returning silence has proven nothing.

## 4. Confirm a hit actually carries a value

A module answering an identifier does not mean it is telling you something
useful. Half of them are constants — a part number, a calibration ID.

OmaCar re-reads every responder several times and reports which byte positions
changed. Bytes that never move across samples are almost certainly static;
bytes that move are candidate live values. Then:

1. **Change the world and re-read.** Press the brake. Turn the wheel. Switch on
   the headlights. A byte that tracks something you did is nearly identified.
2. **Check against a gauge you trust.** If you think you have found coolant
   temperature, compare it to the dash. Scale and offset are usually
   `value = (raw * a) + b` with small integer-ish `a` and `b`.
3. **Only then name it**, and mark it `confidence = "validated"`.

Until step 3, it is a guess. OmaCar labels it as one. **A tool that presents a
guess with the same confidence as a measurement is worse than a tool that shows
nothing**, because you will act on it.

## 5. When `0x22` comes up empty — the lesson from our own car

We swept 8,192 identifiers across both hybrid modules on a 2015 Honda CR-Z and
found **nothing**. Both modules answered `F1xx` normally, so they were awake and
speaking; they simply had no DIDs mapped in the range we searched.

The mistake was assuming `0x22` was the only door.

**Service `0x19` is a different question entirely.** It takes a *subfunction*,
not a DID, so no amount of DID sweeping will ever discover it. Subfunction `0x0A`
asks a module to enumerate every fault code it is capable of setting:

```
omacar dtc --parked
```

On the same car that returned nothing from 8,192 DIDs, this returned **49
Honda-specific codes** from one module — hybrid battery cell faults, cooling
fan, current sensors, inverter temperatures.

That catalogue is a map of what the module *measures*. It does not give you live
values, but it tells you exactly what to expect and stops the next sweep being
blind.

**Try `0x19` before committing hours to `0x22`.** It costs about twenty requests.

## 6. Budget your time and your battery

Measured on real hardware, roughly `0.05 s` per request:

| Scope | Requests | Time |
|---|---|---|
| `F100-F1FF`, 2 modules | 512 | ~30 s |
| `0000-0FFF`, 2 modules | 8,192 | ~7–15 min |
| Full manufacturer range `0100-A5FF`, 2 modules | ~84,000 | **~70 min** |
| Service `0x19`, all subfunctions, 3 modules | ~24 | ~15 s |

**The battery is the real limit, not the time.** Ignition on with the engine off
runs everything off a 12 V battery with no alternator. We learned this the
literal hard way: a 25-minute key-on sweep ended with an **ABS warning light** on
the dash — a classic undervoltage symptom, not damage, and it cleared on the
next drive. For anything beyond about ten minutes, run the engine or connect a
charger.

## 7. The protections, and why each exists

None of these are theoretical. Each one is here because of something that went
wrong.

**Read-only services, enforced as a whitelist.** `lib/elm.py` defines
`READ_ONLY_SERVICES`. A service not in that set cannot be sent, whatever asks
for it. Absent by construction: `0x14` (clear DTCs), `0x2E` (write), `0x2F`
(I/O control), `0x31` (routine control), `0x11` (ECU reset), `0x85` (control DTC
setting) — and most importantly **`0x34`/`0x36`/`0x37`, the firmware-flashing
trio**. Those write program memory; an interrupted or mismatched transfer leaves
a module with no valid firmware, which is a tow to the dealer. There is nothing
readable there, so they are not implemented at all.

**Clearing codes is not implemented.** Not disabled — absent. A diagnostic that
quietly erases the evidence of an intermittent fault is worse than no diagnostic.

**A stationary gate on sweeps.** `prospect` reads road speed and refuses to run
if the car is moving. If it cannot read speed at all, it refuses unless you pass
`--parked` and take responsibility. Flooding a live bus with thousands of
unknown requests at motorway speed is not a risk worth taking for data.
`dtclog` is deliberately exempt: it sends about eight known-good requests every
few minutes, four orders of magnitude less traffic. **The gate is calibrated to
bus load, not to the service number.**

**A battery floor.** Every probe reads voltage first and refuses below **11.8 V**.
This exists entirely because of the ABS incident above.

**Nice=10 on every background process.** Unrelated to the car and still
load-bearing: an unthrottled poll loop starved the compositor on a 2-core test
machine badly enough to crash the desktop.

**Honest caching.** A scan that reused cached data says so. An early version
showed a progress bar over cached results, which is a scan tool inventing work.

## 8. Contribute what you find

A validated profile is worth far more shared than kept. Sweeping the full
manufacturer range takes about seventy minutes **per car** — but only once per
*model*, if the results are pooled. The second owner of your car should get the
map, not the sweep.

Profiles live in `~/.local/state/omacar/profiles/`. Include the model year and
say plainly which entries you validated against a physical gauge and which are
still candidates.

---

### A note on why this is safe to try

Everything above is a question. A car's diagnostic bus is designed to be
interrogated by tools it has never met — that is the entire point of a
standardised connector. Asking for an identifier that does not exist gets you
`requestOutOfRange`, which is the module doing exactly what it was designed to
do.

The danger is never in reading. It is in writing, and in tools that blur the
line. OmaCar keeps that line at the transport layer, where no amount of
enthusiasm further up can cross it.
