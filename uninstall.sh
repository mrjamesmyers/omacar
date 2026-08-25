#!/bin/bash
#
# OmaCar uninstaller: removes every hook the installer placed.

set -uo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib/omarchy-app.sh"
set +e
oa_init omacar "OmaCar"

"$OA_CMD" server stop >/dev/null 2>&1

oa_remove
rm -rf "$OA_STATE_DIR"

echo "OmaCar removed."
