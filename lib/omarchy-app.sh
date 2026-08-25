# omarchy-app.sh — the shared install/uninstall primitives behind Omarchy apps.
#
# This file is VENDORED into each generated app (lib/omarchy-app.sh), not
# depended on at runtime. An app repo must stay self-contained: clone, run
# ./install.sh, done. Re-vendor with `omarchy-app-new --update .`.
#
# Everything derives from $HOME, which is what makes the whole installer
# testable: run it with HOME=/tmp/whatever and it touches nothing real.
#
#   source lib/omarchy-app.sh
#   oa_init omacar "Car Diagnostics"

set -euo pipefail

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

oa_init() { # slug "Display Name"
  OA_APP="$1"
  OA_NAME="${2:-$1}"
  OA_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[1]}")")" && pwd)"

  OA_BIN="$HOME/.local/bin"
  OA_CMD="$OA_BIN/$OA_APP"
  OA_PLUGIN_DIR="$HOME/.config/omarchy/plugins/$OA_APP"
  OA_MENU_FILE="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
  OA_SHELL_JSON="$HOME/.config/omarchy/shell.json"
  OA_BINDINGS_FILE="$HOME/.config/hypr/bindings.lua"
  OA_AUTOSTART_FILE="$HOME/.config/hypr/autostart.lua"
  OA_ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
  OA_APPS_DIR="$HOME/.local/share/applications"
  OA_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/$OA_APP"
  OA_TOGGLE_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/toggles/hypr/$OA_APP.lua"

  # Live desktop calls are no-ops when we're installing into a scratch HOME.
  OA_LIVE=1
  [[ "$HOME" == "$(getent passwd "$(id -u)" | cut -d: -f6)" ]] || OA_LIVE=0
}

oa_say()  { printf '  \033[1m%s\033[0m %s\n' "${1:-}" "${2:-}"; }
oa_warn() { printf '  \033[1;33m!\033[0m %s\n' "$1" >&2; }
oa_die()  { printf '  \033[1;31merror\033[0m %s\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Commands on PATH
# ---------------------------------------------------------------------------

oa_bin_link() {
  mkdir -p "$OA_BIN"
  local tool
  for tool in "$OA_ROOT"/bin/*; do
    [[ -f "$tool" ]] || continue
    ln -sfn "$tool" "$OA_BIN/$(basename "$tool")"
  done
  oa_say "" "$OA_APP on your PATH"
}

# ---------------------------------------------------------------------------
# Icon + desktop launcher
# ---------------------------------------------------------------------------

oa_icon_install() {
  [[ -f "$OA_ROOT/share/icon.svg" ]] || return 0
  mkdir -p "$OA_ICON_DIR"
  if command -v rsvg-convert >/dev/null; then
    rsvg-convert -w 256 -h 256 "$OA_ROOT/share/icon.svg" -o "$OA_ICON_DIR/$OA_APP.png"
  elif command -v magick >/dev/null; then
    magick -background none "$OA_ROOT/share/icon.svg" -resize 256x256 "$OA_ICON_DIR/$OA_APP.png"
  fi
}

# StartupWMClass is what ties a Chromium web-app window back to this entry.
# Without it the window's own class (chrome-127.0.0.1__app.html-Default)
# matches nothing and the dock falls back to a generic icon.
oa_desktop_entry() { # "Comment" "Exec" "Categories" "Keywords" ["StartupWMClass"]
  mkdir -p "$OA_APPS_DIR"
  {
    echo "[Desktop Entry]"
    echo "Type=Application"
    echo "Name=$OA_NAME"
    echo "Comment=$1"
    echo "Exec=$2"
    echo "Icon=$OA_APP"
    echo "Terminal=false"
    [[ -n "${5:-}" ]] && echo "StartupWMClass=$5"
    echo "Categories=$3"
    echo "Keywords=$4"
  } >"$OA_APPS_DIR/$OA_APP.desktop"
  gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
  oa_say "" "app launcher entry installed (search: $OA_NAME)"
}

# ---------------------------------------------------------------------------
# Managed config blocks
# ---------------------------------------------------------------------------

# Replace (or append) a marker-delimited block in a Lua config file. Other
# sessions edit these files too, so we only ever touch our own block.
oa_lua_block() { # file content
  local file="$1" content="$2" tmp
  tmp=$(mktemp)
  mkdir -p "$(dirname "$file")"
  touch "$file"
  sed "/^-- >>> $OA_APP/,/^-- <<< $OA_APP/d" "$file" >"$tmp"
  # Trim trailing blank lines so repeated installs don't grow the file.
  sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$tmp" 2>/dev/null || true
  printf '\n-- >>> %s (managed by %s/install.sh — edits inside are overwritten)\n%s\n-- <<< %s\n' \
    "$OA_APP" "$OA_APP" "$content" "$OA_APP" >>"$tmp"
  mv "$tmp" "$file"
}

# Splice menu/menu-entries.jsonc in just above the menu file's closing brace.
# __CMD__ in the entries file is replaced with the installed command path.
oa_menu_splice() {
  [[ -f "$OA_ROOT/menu/menu-entries.jsonc" ]] || return 0
  mkdir -p "$(dirname "$OA_MENU_FILE")"
  [[ -f "$OA_MENU_FILE" ]] || printf '{\n}\n' >"$OA_MENU_FILE"

  local tmp close_line
  tmp=$(mktemp)
  sed "/\/\/ >>> $OA_APP/,/\/\/ <<< $OA_APP/d" "$OA_MENU_FILE" >"$tmp"

  close_line=$(grep -n '^[[:space:]]*}[[:space:]]*$' "$tmp" | tail -1 | cut -d: -f1)
  if [[ -z "$close_line" ]]; then
    rm -f "$tmp"
    oa_die "$OA_MENU_FILE has no closing brace; fix it and rerun."
  fi
  {
    head -n "$((close_line - 1))" "$tmp"
    echo "  // >>> $OA_APP (managed by $OA_APP/install.sh)"
    sed "s|__CMD__|$OA_CMD|g; s/^/  /" "$OA_ROOT/menu/menu-entries.jsonc"
    echo "  // <<< $OA_APP"
    tail -n "+$close_line" "$tmp"
  } >"$OA_MENU_FILE"
  rm -f "$tmp"
  oa_say "" "menu entries added (Omarchy menu → $OA_NAME)"
}

# ---------------------------------------------------------------------------
# Bar plugin
# ---------------------------------------------------------------------------

# Copy, never symlink: the shell's hot-reload watches the real plugin
# directory and does not see writes through a symlink.
oa_plugin_install() {
  [[ -f "$OA_ROOT/plugin/manifest.json" ]] || return 0
  if [[ -e "$OA_PLUGIN_DIR" && ! -L "$OA_PLUGIN_DIR" && ! -f "$OA_PLUGIN_DIR/manifest.json" ]]; then
    oa_die "$OA_PLUGIN_DIR exists and isn't ours — move it aside first."
  fi
  [[ -L "$OA_PLUGIN_DIR" ]] && rm "$OA_PLUGIN_DIR"
  mkdir -p "$OA_PLUGIN_DIR"
  cp -f "$OA_ROOT"/plugin/* "$OA_PLUGIN_DIR/"

  # The overlay service mounts only for plugins listed in shell.json's
  # plugins[]; the bar layout alone does not load it.
  if [[ -f "$OA_SHELL_JSON" ]] && command -v jq >/dev/null &&
     ! jq -e --arg id "$OA_APP" '.plugins[]? | select(.id == $id)' "$OA_SHELL_JSON" >/dev/null 2>&1; then
    local tmp; tmp=$(mktemp)
    jq --arg id "$OA_APP" '.plugins = ((.plugins // []) + [{"id":$id}])' "$OA_SHELL_JSON" >"$tmp" &&
      mv "$tmp" "$OA_SHELL_JSON"
  fi

  ((OA_LIVE)) && omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  oa_say "" "bar plugin registered"
}

oa_bar_place() { # [--before other.widget]
  [[ -f "$OA_ROOT/plugin/manifest.json" ]] || return 0
  ((OA_LIVE)) || return 0
  if jq -e --arg id "$OA_APP" '.bar.layout | .. | objects | select(.id? == $id)' \
       "$OA_SHELL_JSON" >/dev/null 2>&1; then
    oa_say "" "widget already in the bar"
    return 0
  fi
  if omarchy-bar put "$OA_APP" "$@" >/dev/null 2>&1 ||
     omarchy-bar put "$OA_APP" --section right >/dev/null 2>&1; then
    oa_say "" "widget placed in the bar"
  else
    oa_warn "couldn't place the bar widget — run: omarchy bar put $OA_APP"
  fi
}

# ---------------------------------------------------------------------------
# Hyprland
# ---------------------------------------------------------------------------

oa_hypr_reload() { # "success message"
  ((OA_LIVE)) || return 0
  hyprctl reload >/dev/null 2>&1 || true
  local errors
  errors=$(hyprctl configerrors 2>/dev/null || true)
  if [[ -n "$errors" && "$errors" != *"no errors"* ]]; then
    oa_warn "hyprctl configerrors reported:"
    echo "$errors" >&2
  else
    [[ -n "${1:-}" ]] && oa_say "" "$1"
  fi
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

# Reverses every hook the install placed. Deliberately not `set -e` sensitive:
# a partial install must still uninstall cleanly.
oa_remove() {
  local tool
  if [[ -f "$OA_SHELL_JSON" ]] && command -v jq >/dev/null; then
    local tmp; tmp=$(mktemp)
    jq --arg id "$OA_APP" '
      (.bar.layout // {}) |= with_entries(.value |= (if type == "array" then map(select(.id != $id)) else . end))
      | .plugins = ((.plugins // []) | map(select(.id != $id)))' \
      "$OA_SHELL_JSON" >"$tmp" 2>/dev/null && mv "$tmp" "$OA_SHELL_JSON" || rm -f "$tmp"
  fi

  sed -i "/^-- >>> $OA_APP/,/^-- <<< $OA_APP/d" "$OA_BINDINGS_FILE" 2>/dev/null || true
  sed -i "/^-- >>> $OA_APP/,/^-- <<< $OA_APP/d" "$OA_AUTOSTART_FILE" 2>/dev/null || true
  sed -i "/\/\/ >>> $OA_APP/,/\/\/ <<< $OA_APP/d" "$OA_MENU_FILE" 2>/dev/null || true

  for tool in "$OA_ROOT"/bin/*; do
    [[ -f "$tool" ]] && rm -f "$OA_BIN/$(basename "$tool")"
  done
  rm -f "$OA_TOGGLE_FILE" "$OA_APPS_DIR/$OA_APP.desktop" "$OA_ICON_DIR/$OA_APP.png"
  [[ -L "$OA_PLUGIN_DIR" ]] && rm "$OA_PLUGIN_DIR" || rm -rf "$OA_PLUGIN_DIR"

  if ((OA_LIVE)); then
    hyprctl reload >/dev/null 2>&1 || true
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  fi
}
