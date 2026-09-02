# Contributing a service reset

Oil life. Electronic parking brake retract. Steering angle sensor. TPMS relearn.
Battery registration. DPF regeneration. Throttle body relearn.

These are the jobs that most often force somebody to pay a shop for ninety
seconds of work, and they are the highest-value thing you can contribute to
OmaCar. **One person's verified definition covers that model for everybody who
ever runs it.**

---

## Why we cannot just find these ourselves

OmaCar discovers readable data by sweeping: ask service `0x22` for every
identifier and see which ones answer. That is safe, because an identifier that
does not exist replies `requestOutOfRange` and nothing happens.

**Service `0x31` cannot be explored that way, and never will be.** A routine is
not a value you read — it is a procedure the module *runs*. The routine
identifier you just guessed might spin a radiator fan, cycle an ABS pump,
retract a parking brake with a wheel off the ground, or run the engine to a
target speed. There is no harmless miss.

So every definition has to come from a documented procedure or a verified
capture. There is no shortcut, and OmaCar will not pretend otherwise: when it
has nothing verified for your vehicle, it says so rather than showing you a list
of plausible guesses.

## Where definitions can come from

In rough order of how much we trust them:

1. **A factory service manual procedure.** The best source. Manuals often
   describe the sequence in terms a tool implements directly.
2. **A verified capture.** If you own a tool that performs the reset, a CAN
   trace of it doing so is definitive. `candump` on a Linux box with a CAN
   interface, or a logging OBD adapter.
3. **A published community definition** for the same make and era, confirmed to
   work on your own car.
4. **Somebody on a forum said so.** This is `"confidence": "reported"` at best,
   and it must say so.

**What is never acceptable:** inferring an identifier because a different make
uses it, or because it looks like a plausible next number. That is how a routine
meant for a fuel pump test gets sent to a module that uses that ID for something
else.

## The format

Definitions live in `share/data/resets.json` (bundled) or
`~/.local/state/omacar/resets.json` (yours, and it overrides).

```json
{
  "id": "honda-oil-life-reset",
  "name": "Oil life reset",
  "category": "service",
  "makes": ["Honda"],
  "models": ["Fit", "CR-Z"],
  "years": [2009, 2015],
  "header": "18DA10F1",
  "requests": ["1003", "3101FF00"],
  "delay_between": 0.4,
  "confidence": "verified",
  "source": "2012 Honda Fit service manual, section 4-12",
  "confirmed_on": ["2012 Honda Fit Sport"],
  "warning": "Resets the oil life indicator to 100%. Only do this after an actual oil change — the indicator is what tells the next person when the oil was last changed.",
  "preconditions": [
    "Engine off, ignition on",
    "The oil has actually been changed"
  ]
}
```

**Every field earns its place:**

| Field | Why it matters |
|---|---|
| `makes` / `models` / `years` | Narrows who is offered it. A Honda routine ID on a BMW reaches a module that means something else by it. |
| `header` | The module address. Wrong address, wrong computer. |
| `requests` | Sent in order, stopping at the first refusal. |
| `delay_between` | Routines often need a moment between steps. Say so rather than making the tool guess. |
| `confidence` | `verified` / `reported` / `unverified`. Shown next to the button, in that colour. |
| `source` | **Required.** A definition nobody can trace is a definition nobody should run. |
| `confirmed_on` | Actual vehicles somebody ran it on. Empty is honest; fabricated is not. |
| `warning` | Shown before the button. Say what physically happens. |
| `preconditions` | What must be true first. Be specific about safety — "nobody near the wheels" is a real precondition. |

## Testing yours

1. Put it in `~/.local/state/omacar/resets.json` and it appears immediately.
2. `omacar write arm`
3. Run it with the car parked, engine off, ignition on, and a charger connected
   if you can — the tool refuses below 12.2 V for good reason.
4. Confirm the effect physically. A positive response only means the module
   accepted the request; the oil life indicator on the dash is the real test.
5. Set `confidence` honestly and add your vehicle to `confirmed_on`.

## Safety, stated plainly

- **Never run an actuator test with the car in gear, on a lift, or with anyone
  near moving parts.** OmaCar refuses while the car reports road speed, but it
  cannot see a person leaning into the engine bay.
- **An interrupted calibration can be worse than not starting one.** If a
  routine involves a calibration, get the voltage right first.
- **Know how to undo it, before you do it.** Some resets have no inverse.

If a definition you write turns out to be wrong, say so and get it removed. The
value of this file is entirely in its trustworthiness — a shared database with
one dangerous entry is worse than no shared database at all.
