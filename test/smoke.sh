#!/bin/bash
#
# OmaCar smoke test.
#
# Installs into a scratch HOME, asserts every hook landed, uninstalls, then
# asserts the scratch HOME is back to how it started. Touches nothing real —
# safe to run on a live desktop with other sessions working.

fails=0
ok()   { printf '   ok  %s\n' "$1"; }
bad()  { printf ' FAIL  %s\n' "$1"; fails=$((fails + 1)); }
check(){ if [[ "$2" == "$3" ]]; then ok "$1"; else printf ' FAIL  %s (expected %q, got %q)\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

echo
echo "  OmaCar smoke test (scratch HOME: $SCRATCH)"
echo

mkdir -p "$SCRATCH/.config/omarchy/extensions" "$SCRATCH/.config/hypr"
printf '{\n}\n' >"$SCRATCH/.config/omarchy/extensions/omarchy-menu.jsonc"
printf '{"plugins":[],"bar":{"layout":{}}}\n' >"$SCRATCH/.config/omarchy/shell.json"
printf -- '-- existing user config\n' >"$SCRATCH/.config/hypr/bindings.lua"
before_bindings=$(cat "$SCRATCH/.config/hypr/bindings.lua")

HOME="$SCRATCH" "$ROOT/install.sh" --bind >/dev/null 2>&1 || bad "install.sh exited non-zero"

[[ -L "$SCRATCH/.local/bin/omacar" ]] && ok "CLI symlinked onto PATH" || bad "CLI symlinked onto PATH"
[[ -f "$SCRATCH/.local/share/applications/omacar.desktop" ]] && ok "desktop entry written" || bad "desktop entry written"
grep -q '>>> omacar' "$SCRATCH/.config/omarchy/extensions/omarchy-menu.jsonc" && ok "menu block spliced" || bad "menu block spliced"
grep -q '>>> omacar' "$SCRATCH/.config/hypr/bindings.lua" && ok "keybinding block added" || bad "keybinding block added"
# The Omarchy menu is JSONC: line comments, and trailing commas before a
# closing brace are the existing convention there, not corruption.
python3 -c "
import json, re
raw = open('$SCRATCH/.config/omarchy/extensions/omarchy-menu.jsonc').read()
raw = re.sub(r'^\s*//.*$', '', raw, flags=re.M)
raw = re.sub(r',(\s*[}\]])', r'\1', raw)
d = json.loads(raw)
assert 'omacar.open' in d, 'our entry is missing'
" 2>/dev/null && ok "menu file is still valid JSONC and has our entry" || bad "menu file is still valid JSONC and has our entry"

# Idempotence: a second install must not duplicate anything.
HOME="$SCRATCH" "$ROOT/install.sh" --bind >/dev/null 2>&1
check "install is idempotent (one menu block)" "1" \
  "$(grep -c '>>> omacar' "$SCRATCH/.config/omarchy/extensions/omarchy-menu.jsonc")"
check "install is idempotent (one binding block)" "1" \
  "$(grep -c '>>> omacar' "$SCRATCH/.config/hypr/bindings.lua")"

HOME="$SCRATCH" "$ROOT/uninstall.sh" >/dev/null 2>&1 || bad "uninstall.sh exited non-zero"

[[ -e "$SCRATCH/.local/bin/omacar" ]] && bad "CLI removed" || ok "CLI removed"
grep -q '>>> omacar' "$SCRATCH/.config/omarchy/extensions/omarchy-menu.jsonc" && bad "menu block removed" || ok "menu block removed"
check "user's own config untouched" "$before_bindings" "$(cat "$SCRATCH/.config/hypr/bindings.lua")"

echo
if ((fails)); then echo "  $fails failed"; exit 1; else echo "  all good"; fi
echo
