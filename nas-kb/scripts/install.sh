#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_HOME="${NAS_KB_INSTALL_HOME:-$HOME/.local/share/nas-kb}"
BIN_DIR="${NAS_KB_BIN_DIR:-$HOME/.local/bin}"
VENV_DIR="$INSTALL_HOME/venv"

mkdir -p "$INSTALL_HOME" "$BIN_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install -e "$ROOT_DIR" >/dev/null
ln -sfn "$VENV_DIR/bin/nas-kb" "$BIN_DIR/nas-kb"
"$BIN_DIR/nas-kb" --help >/dev/null
echo "Installed nas-kb to $BIN_DIR/nas-kb"
