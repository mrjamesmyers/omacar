# Writing an OmaCar plugin

Three things already extend OmaCar without any code at all — **vehicle
profiles**, **reset definitions** and **owner procedures** are data files, and
between them they cover most of what anybody wants to add. Start there if you
can.

A plugin is for the rest: a screen of your own, a command of your own, or being
told when something happens. A marque forum with a decoder for their own
manufacturer's packets. A fleet owner who wants every fault mailed to them.
Somebody who wants the drive log in their own database.

Without this the answer to all of those is *fork it* — which means the work
never comes back, and whoever did it inherits a maintenance burden for one
feature.

---

## A plugin is a directory

```
~/.config/omacar/plugins/fuel-log/
  plugin.json            what it is                        (required)
  command.py             adds `omacar fuel`
  view.js                adds a screen to the app
  data/resets.json       more reset definitions
  data/procedures.json   more owner procedures
  hooks/on-fault         run when a new fault appears
  hooks/on-drive-end     run when a drive finishes
  hooks/on-scan          run after a full system scan
```

Everything except `plugin.json` is optional. Nothing is compiled, bundled or
registered: **dropping the directory in is the installation, and deleting it is
the uninstallation.**

`omacar plugins` lists what is installed and what each one contributes — read
from the filesystem, not from the manifest's claims, so a manifest that says it
provides a view when there is no `view.js` cannot cost you an evening.

## The manifest

```json
{
  "name": "Fuel log",
  "description": "Records every fill-up and works out real-world economy",
  "version": "0.1.0",
  "author": "you",
  "command": "fuel",
  "label": "Fuel"
}
```

`name` and `description` are required. `command` is the word after `omacar`
(defaults to the directory name); `label` is what the rail shows.

## Read this before you install someone else's

**A plugin is code you are running.** Its command runs as you, with your access
to the car. There is no sandbox, and it would be dishonest to imply one — the
mitigation is that `omacar plugins` tells you plainly which plugins execute
code, before you rely on them.

The protections that *do* exist are about robustness, not trust:

- A hook runs with a timeout and its output discarded. A plugin that hangs or
  crashes **cannot stall the gauge**, which is polling a serial port in a moving
  car.
- A malformed manifest disables that plugin and nothing else.
- A plugin view that throws on import loses its own screen and nothing else.
- **A plugin can never shadow a built-in command.** Names are resolved after
  every built-in, so nobody's directory can redefine what `omacar scan` does.

## Commands

`command.py` is run with the interpreter OmaCar uses, and gets:

| variable | what it is |
|---|---|
| `OMACAR_DB` | the **current vehicle's** database — you never have to work out which car |
| `OMACAR_STATE` | the state directory |
| `OMACAR_LIB` | OmaCar's own modules, already on `PYTHONPATH` |
| `OMACAR_PLUGIN_DIR` | your own directory |

Because `OMACAR_LIB` is importable you can use the real thing rather than
reimplementing it:

```python
import records, book, garage
snapshot = records.snapshot()
```

Your own tables can live in `OMACAR_DB` alongside OmaCar's. They are then
per-vehicle for free, and they follow the car — including when it is sold.

## Hooks

A hook is any executable. The event arrives as **JSON on stdin** — not as
arguments, so a fault description containing a quote or a newline cannot become
a shell problem.

```bash
#!/usr/bin/env bash
payload=$(cat)
echo "$(date -Is) $payload" >> "$OMACAR_STATE/faults.log"
```

| hook | fires when |
|---|---|
| `on-fault` | a code appears that was not there before |
| `on-drive-end` | a drive finishes |
| `on-scan` | a full system scan completes |

`on-fault` fires **after** the fault is written, never before — a hook that
announced something and then failed to record it would be worse than no hook.

## Views

`view.js` is an ES module whose default export takes a root element, exactly
like OmaCar's own views:

```js
import { h, store, api } from "../../js/core.js";

export default function myView(root) {
  root.appendChild(h("section.card",
    h("div.title", "Mine"),
    h("p.lede", `${(store.car.active_faults || []).length} active faults`)));
}
```

It is imported dynamically at boot. There is no bundler and there never will
be — that is the same reason OmaCar itself has no build step.

## Data

`data/resets.json` and `data/procedures.json` use the formats documented in
[RESETS.md](RESETS.md). They are merged between the bundled definitions and the
user's own, so a plugin can add procedures for a make without touching the
repository.

The confidence rules apply exactly as they do everywhere else: a routine
identifier nobody has confirmed on a real car is `unverified`, and saying
otherwise in a plugin is no more acceptable than saying it upstream.

## A worked example

`examples/fuel-log/` in this repository is a complete plugin — a command, a
view, and a hook — in about sixty lines. Copy it:

```
cp -r examples/fuel-log ~/.config/omacar/plugins/
omacar plugins
omacar fuel add 32.1 48.75 186402
```
