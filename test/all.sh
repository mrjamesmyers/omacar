#!/bin/bash
#
# Every OmaCar test. The install round-trip runs against a scratch HOME; the
# prospector's logic runs against a scripted fake ECU. Neither needs a car.

set -uo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/omacar/venv"
fails=0

"$ROOT/test/smoke.sh" || fails=$((fails + 1))

if [[ -x "$VENV/bin/python" ]]; then
  "$VENV/bin/python" "$ROOT/test/prospect_test.py" || fails=$((fails + 1))
else
  echo "  (skipping prospector tests — run: omacar setup)"
fi

# The workshop's own logic — units, the service countdown, Mode 06 verdicts,
# the advisor's evidence check, the theme derivation and the drive-mode gauges.
#
# Stdlib only, so system python runs nearly all of it. The venv is PREFERRED
# rather than required: a handful of checks import modules that reach pyserial
# (dtclog is one), and under system python those skip themselves with a note.
# They were silently skipping in every run until this line preferred the venv,
# which is a guard that exists and never fires -- the worst kind.
if [[ -x "$VENV/bin/python" ]]; then
  "$VENV/bin/python" "$ROOT/test/workshop_test.py" || fails=$((fails + 1))
else
  python3 "$ROOT/test/workshop_test.py" || fails=$((fails + 1))
fi

exit $((fails > 0))
