"""Plugins: extending OmaCar without forking it.

WHAT THIS IS FOR.

Three things already extend OmaCar without code: vehicle profiles, reset
definitions and owner procedures are all data files, and that covers most of
what a contributor wants. What it does not cover is somebody who wants a screen
of their own, a command of their own, or to be told when something happens --
a marque forum with a decoder for their own manufacturer's packets, a fleet
owner wanting every fault mailed to them, somebody who wants OmaCar's drive log
in their own database.

Today the answer to all of those is "fork it", which means their work never
comes back and they inherit a maintenance burden for one feature.

WHAT A PLUGIN IS.

A directory with a manifest, in the user's own config. It may contribute any of:

    plugin.json          what it is and what it provides   (required)
    command.py           adds `omacar <name>`
    view.js              adds a screen to the app
    data/resets.json     more reset definitions
    data/procedures.json more owner procedures
    hooks/on-fault       run when a new fault appears
    hooks/on-drive-end   run when a drive finishes
    hooks/on-scan        run after a full scan

Nothing is compiled, bundled or registered anywhere. Dropping the directory in
is the installation, and deleting it is the uninstallation.

A PLUGIN IS CODE YOU ARE RUNNING, AND THIS FILE SAYS SO.

There is no sandbox here and it would be dishonest to imply one: a plugin's
command runs as you, with your access to the car. That is the same trust you
extend to anything you install, and the mitigation is not a fake boundary but
plain speech -- `omacar plugins` shows what each one contributes, including
that it executes code, before you rely on it.

The protections that DO exist are about robustness rather than trust:

  - A hook runs detached with a timeout and its output discarded. A plugin that
    hangs or crashes cannot stall the gauge, which is polling a serial port in
    a moving car.
  - A malformed manifest disables that plugin and nothing else.
  - Hooks never run while the app is merely reading; they fire on events that
    have already happened.
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import records  # noqa: E402

ROOT = os.path.join(os.path.expanduser(
    os.environ.get("XDG_CONFIG_HOME", "~/.config")),
    "omacar", "plugins")

# A hook gets this long, then it is killed. Generous for anything sensible and
# far too short to matter to a car.
HOOK_TIMEOUT = 20

HOOKS = {
    "on-fault": "a new fault code appeared",
    "on-drive-end": "a drive finished",
    "on-scan": "a full system scan completed",
}

REQUIRED = ("name", "description")


def discover():
    """Every plugin directory, valid or not.

    Invalid ones are returned WITH their problem rather than skipped, because a
    plugin that silently does not load is the worst possible outcome for
    somebody who just wrote one.
    """
    out = []
    if not os.path.isdir(ROOT):
        return out
    for entry in sorted(os.listdir(ROOT)):
        d = os.path.join(ROOT, entry)
        if not os.path.isdir(d):
            continue
        man = os.path.join(d, "plugin.json")
        if not os.path.exists(man):
            out.append({"dir": d, "id": entry, "ok": False,
                        "problem": "no plugin.json"})
            continue
        try:
            with open(man, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError) as e:
            out.append({"dir": d, "id": entry, "ok": False,
                        "problem": f"plugin.json is not valid JSON: {e}"})
            continue
        missing = [k for k in REQUIRED if not meta.get(k)]
        if missing:
            out.append({"dir": d, "id": entry, "ok": False,
                        "problem": f"plugin.json is missing {', '.join(missing)}"})
            continue
        out.append({
            "dir": d, "id": entry, "ok": True, "problem": "",
            "name": meta.get("name"), "description": meta.get("description"),
            "version": meta.get("version", ""), "author": meta.get("author", ""),
            "provides": provides(d),
            "meta": meta,
        })
    return out


def provides(d):
    """What this directory actually contributes, from what is on disk.

    Read from the filesystem rather than from the manifest's own claims: a
    manifest saying it provides a view when there is no view.js is a bug
    somebody will spend an evening on.
    """
    got = []
    if os.path.exists(os.path.join(d, "command.py")):
        got.append("command")
    if os.path.exists(os.path.join(d, "view.js")):
        got.append("view")
    for f in ("resets.json", "procedures.json"):
        if os.path.exists(os.path.join(d, "data", f)):
            got.append(f[:-5])
    hooks = os.path.join(d, "hooks")
    if os.path.isdir(hooks):
        for hk in HOOKS:
            if os.path.exists(os.path.join(hooks, hk)):
                got.append("hook:" + hk)
    return got


def by_id(pid):
    for p in discover():
        if p["id"] == pid or p.get("name") == pid:
            return p
    return None


# ---- commands ---------------------------------------------------------------

def commands():
    """{name: (plugin, path)} for everything adding an `omacar <name>`."""
    out = {}
    for p in discover():
        if not p["ok"] or "command" not in p["provides"]:
            continue
        name = (p["meta"].get("command") or p["id"]).strip()
        if name and name not in out:
            out[name] = (p, os.path.join(p["dir"], "command.py"))
    return out


def run_command(name, argv):
    """Hand control to a plugin's command. Returns its exit status."""
    cmds = commands()
    if name not in cmds:
        return None
    plugin, path = cmds[name]
    env = dict(os.environ)
    # Everything a plugin needs to find the car's data without guessing at
    # paths, so a plugin does not have to reimplement our layout.
    env["OMACAR_STATE"] = records.STATE
    env["OMACAR_DB"] = records.DB
    env["OMACAR_LIB"] = os.path.dirname(os.path.abspath(__file__))
    env["OMACAR_PLUGIN_DIR"] = plugin["dir"]
    env["PYTHONPATH"] = (env["OMACAR_LIB"] + os.pathsep
                         + env.get("PYTHONPATH", ""))
    return subprocess.call([sys.executable, path] + list(argv), env=env)


# ---- hooks ------------------------------------------------------------------

def fire(event, payload=None):
    """Tell every plugin that something happened. Never blocks meaningfully.

    The payload goes in on stdin as JSON rather than as arguments, so a fault
    description containing a quote or a newline cannot become a shell problem.

    Failures are swallowed on purpose. This is called from the polling loop of
    a tool running in a moving car; a plugin that crashes, hangs or writes
    nonsense must be incapable of taking the gauge down with it.
    """
    if event not in HOOKS:
        return []
    fired = []
    body = json.dumps(payload or {})
    for p in discover():
        if not p["ok"]:
            continue
        script = os.path.join(p["dir"], "hooks", event)
        if not os.path.exists(script):
            continue
        env = dict(os.environ)
        env["OMACAR_STATE"] = records.STATE
        env["OMACAR_DB"] = records.DB
        env["OMACAR_EVENT"] = event
        env["OMACAR_PLUGIN_DIR"] = p["dir"]
        try:
            subprocess.run([script], input=body, text=True, env=env,
                           timeout=HOOK_TIMEOUT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           start_new_session=True)
            fired.append(p["id"])
        except Exception:                                      # noqa: BLE001
            # Including TimeoutExpired. A slow plugin is a plugin problem.
            continue
    return fired


# ---- contributed data --------------------------------------------------------

def data_files(kind):
    """Plugin-contributed `resets.json` / `procedures.json`, in load order.

    Returned as paths for the caller to merge, rather than merged here: resets
    and procedures already know how to overlay their own bundled and user
    files, and a third loader would be a third place for the rules to drift.
    """
    out = []
    for p in discover():
        if not p["ok"]:
            continue
        f = os.path.join(p["dir"], "data", kind + ".json")
        if os.path.exists(f):
            out.append(f)
    return out


def views():
    """Plugin screens, for the app to load."""
    out = []
    for p in discover():
        if not p["ok"] or "view" not in p["provides"]:
            continue
        out.append({
            "id": "plugin-" + p["id"],
            "label": p["meta"].get("label") or p["name"],
            "title": p["description"],
            "src": f"/plugin/{p['id']}/view.js",
        })
    return out


def view_path(pid, name="view.js"):
    """Resolve a plugin's asset, refusing anything that climbs out."""
    p = by_id(pid)
    if not p or not p["ok"]:
        return None
    safe = os.path.basename(name or "")
    if not safe.endswith(".js"):
        return None
    full = os.path.realpath(os.path.join(p["dir"], safe))
    if not full.startswith(os.path.realpath(p["dir"]) + os.sep):
        return None
    return full if os.path.exists(full) else None


# ---- cli --------------------------------------------------------------------

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, YELLOW, RED = "\033[32m", "\033[33m", "\033[31m"


def cmd_list():
    found = discover()
    print(f"\n  {BOLD}Plugins{RESET}  {DIM}{ROOT}{RESET}")
    if not found:
        print(f"  {DIM}none installed. See doc/PLUGINS.md.{RESET}\n")
        return 0
    for p in found:
        if not p["ok"]:
            print(f"    {RED}✗{RESET} {p['id']:20} {p['problem']}")
            continue
        prov = ", ".join(p["provides"]) or "nothing"
        print(f"    {GREEN}●{RESET} {p['id']:20} {p['name']}")
        print(f"      {DIM}{p['description']}{RESET}")
        print(f"      provides: {prov}")
        if "command" in p["provides"] or any(x.startswith("hook:")
                                             for x in p["provides"]):
            print(f"      {YELLOW}runs code as you{RESET}")
    print()
    return 0


def main(argv):
    # --dispatch is how bin/omacar hands an unknown command to a plugin.
    # Exit 127 means "no plugin claims this name", which the caller turns into
    # the normal unknown-command message.
    if argv and argv[0] == "--dispatch":
        rest = argv[1:]
        if not rest:
            return 127
        code = run_command(rest[0], rest[1:])
        return 127 if code is None else code
    return cmd_list()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
