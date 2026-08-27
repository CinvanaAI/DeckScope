#!/usr/bin/env bash
# ===================================================================
#  DeckScope installer for macOS and Linux
#  Run:  bash install.sh      (or double-click install.command on a Mac)
# ===================================================================
set -u
cd "$(dirname "$0")"

bold=$(tput bold 2>/dev/null || echo ""); dim=$(tput dim 2>/dev/null || echo "")
green=$(tput setaf 2 2>/dev/null || echo ""); red=$(tput setaf 1 2>/dev/null || echo "")
reset=$(tput sgr0 2>/dev/null || echo "")

echo
echo "  =============================================================="
echo "  ${bold}  DeckScope — Installer${reset}"
echo "  =============================================================="
echo
echo "   This will:"
echo "     1. Check that Python is installed"
echo "     2. Install DeckScope into its own private folder"
echo "     3. Add a launcher you can double-click"
echo "     4. Walk you through setup, step by step"
echo
echo "   Outside this folder it adds: a Desktop launcher, a settings folder at"
echo "   ~/.config/deckscope for your config, keys and cache, and — if one of"
echo "   them already exists and is writable — a 'deckscope' command in"
echo "   ~/.local/bin or /usr/local/bin. Nothing else is touched."
# NOTE: install.command carried a stronger and untrue version of this
# line ("nothing outside this folder and your Desktop"), while doing
# the same symlink. Two near-duplicate installers drift; when they
# drift about what they change to the system, one of them is lying.
echo
read -r -p "   Press Enter to continue (or Ctrl+C to stop) "

# ---------- 1. Python ------------------------------------------------
echo
echo "  [1/4] Looking for Python..."
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "        ${red}Python 3.9 or newer was not found.${reset}"
  echo
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "        On a Mac, the simplest fix is to run:"
    echo "          ${bold}brew install python${reset}"
    echo "        or download it from https://www.python.org/downloads/"
  else
    echo "        Install it with your package manager, for example:"
    echo "          ${bold}sudo apt install python3 python3-venv${reset}"
  fi
  echo
  exit 1
fi
echo "        Found: $($PY --version)"

# ---------- 2. venv --------------------------------------------------
echo
echo "  [2/4] Setting up a private Python environment..."
echo "        ${dim}(this keeps DeckScope from interfering with anything else)${reset}"
if [ ! -d ".venv" ]; then
  if ! "$PY" -m venv .venv 2>/dev/null; then
    echo "        ${red}Could not create the environment.${reset}"
    echo "        On Debian/Ubuntu you may need:  sudo apt install python3-venv"
    exit 1
  fi
fi
VENVPY="$PWD/.venv/bin/python"

echo
echo "  [3/4] Installing DeckScope and its components..."
echo "        ${dim}(this takes a minute or two the first time)${reset}"
"$VENVPY" -m pip install --upgrade pip --quiet
if ! "$VENVPY" -m pip install -e ".[all]" --quiet; then
  echo "        ${red}Installation failed.${reset} Check your internet connection"
  echo "        and any corporate proxy, then run this installer again."
  exit 1
fi
echo "        Done."

# ---------- 3. launcher ----------------------------------------------
echo
echo "  [4/4] Creating a launcher..."
LAUNCHER="$PWD/DeckScope.command"
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
cd "\$(dirname "\$0")"
exec "$VENVPY" -m deckscope app
LAUNCH
chmod +x "$LAUNCHER"

DESKTOP="$HOME/Desktop"
if [ -d "$DESKTOP" ]; then
  ln -sf "$LAUNCHER" "$DESKTOP/DeckScope.command" 2>/dev/null && \
    echo "        Added 'DeckScope' to your Desktop."
fi

# A `deckscope` command on the PATH, if there's a sane place for one.
for bindir in "$HOME/.local/bin" "/usr/local/bin"; do
  if [ -d "$bindir" ] && [ -w "$bindir" ]; then
    ln -sf "$PWD/.venv/bin/deckscope" "$bindir/deckscope" 2>/dev/null && \
      echo "        Added the 'deckscope' command to $bindir."
    break
  fi
done

# ---------- 4. wizard ------------------------------------------------
echo
echo "  =============================================================="
echo "  ${bold}  Installed. Now let's set it up.${reset}"
echo "  =============================================================="
echo
"$VENVPY" -m deckscope setup

echo
echo "  =============================================================="
echo "  ${green}${bold}  All done.${reset}"
echo
echo "    Double-click ${bold}DeckScope${reset} on your Desktop any time to open it."
echo "  =============================================================="
echo
