#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
INSTALL_HOME="${NAS_KB_INSTALL_HOME:-$HOME/.local/share/nas-kb}"
BIN_DIR="${NAS_KB_BIN_DIR:-$HOME/.local/bin}"
VENV_DIR="$INSTALL_HOME/venv"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "Python 3.11+ is required." >&2
  exit 1
fi

mkdir -p "$INSTALL_HOME" "$BIN_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install --upgrade "$ROOT_DIR" >/dev/null
ln -sfn "$VENV_DIR/bin/nas-kb" "$BIN_DIR/nas-kb"
"$BIN_DIR/nas-kb" --help >/dev/null
"$PYTHON_BIN" "$REPO_ROOT/scripts/install-codex-skill.py" nas-knowledge-base
echo "Installed nas-kb to $BIN_DIR/nas-kb"
