#!/bin/sh
# SmartPloy local-only Playwright launcher for desktop Linux.
# Explicit user-operated process: never run from the public website.
set -eu
umask 077

fail() {
  printf '%s\n' "SmartPloy local helper: $*" >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || fail "Python 3.11 or later is required."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' ||
  fail "Install Python 3.11+ on this computer first."

BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) ||
  fail "Cannot locate the extracted helper directory."
test -f "$BASE/bridge.py" && test -f "$BASE/assistant.py" ||
  fail "The reviewed bridge.py and assistant.py must be in this extracted folder."

VENV="$BASE/.smartploy-local-venv"
test ! -L "$VENV" || fail "Local virtual environment must not be a symlink."
if test ! -x "$VENV/bin/python"; then
  test ! -e "$VENV" || fail "An incomplete local venv exists; inspect it before restarting."
  printf '%s\n' "Creating an isolated Python environment inside the extracted directory."
  python3 -m venv "$VENV" ||
    fail "Python venv creation failed. Install your distribution's python3-venv package and try again."
fi

PY="$VENV/bin/python"
if ! "$PY" -c 'from importlib.metadata import version; assert version("playwright") == "1.55.0"' >/dev/null 2>&1; then
  printf '%s\n' "First-time setup: install the official pinned Playwright 1.55.0 package into this local venv?"
  printf '%s\n' "No admin rights or global Python changes are needed. This accesses your configured package index."
  printf 'Type INSTALL to proceed, anything else to cancel: '
  IFS= read -r choice || fail "Install cancelled."
  test "$choice" = INSTALL || fail "Install cancelled. No Playwright package was installed."
  "$PY" -m pip install --disable-pip-version-check --no-input --no-cache-dir 'playwright==1.55.0' ||
    fail "The local Playwright package installation failed."
fi

# Ask before browser download, and never install operating-system packages.
if ! "$PY" -c 'import os; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); ok=os.path.isfile(p.chromium.executable_path); p.stop(); assert ok' >/dev/null 2>&1; then
  printf '%s\n' "First-time setup: download the Chromium browser required by Playwright?"
  printf '%s\n' "It is stored in your normal Playwright cache; no system-browser profile is used."
  printf 'Type CHROMIUM to proceed, anything else to cancel: '
  IFS= read -r choice || fail "Chromium download cancelled."
  test "$choice" = CHROMIUM || fail "Chromium download cancelled."
  "$PY" -m playwright install chromium ||
    fail "Chromium installation failed; check browser runtime dependencies and try again."
fi

printf '%s\n' "Starting your private local SmartPloy helper at 127.0.0.1:48741."
printf '%s\n' "Keep this terminal open. Copy the one-time pairing code into your signed-in SmartPloy application."
printf '%s\n' "The employer's final Submit button is always your separate decision."
cd "$BASE"
exec "$PY" "$BASE/bridge.py"
