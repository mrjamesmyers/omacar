# OmaCar

Live OBD-II diagnostics for your car

    ./install.sh          CLI, launcher, icon, and Omarchy menu entries
    ./install.sh --bind   also bind SUPER + SHIFT + C
    ./uninstall.sh        remove every hook it placed
    ./test/smoke.sh       install into a scratch HOME and verify, safely

The app is one self-contained page (`share/app.html`) served over
http://127.0.0.1 by `lib/serve.py` on ports 7560 7561 7562 7563 7564 — never `file://`,
because a null origin breaks embedded YouTube and partitions localStorage.

Config edits live in marker-delimited blocks (`>>> omacar` … `<<< omacar`)
so they survive other people — and other Claude sessions — editing the same
files. `install.sh` is idempotent; run it again after a git pull.

Scaffolded from [omarchy-app-template](../omarchy-app-template).
