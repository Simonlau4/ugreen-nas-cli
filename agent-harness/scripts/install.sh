#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$HARNESS_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
INSTALL_HOME="${UGNAS_INSTALL_HOME:-$HOME/.local/share/ugreen-nas-cli}"
BIN_DIR="${UGNAS_BIN_DIR:-$HOME/.local/bin}"
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
"$VENV_DIR/bin/python" -m pip install --upgrade "$HARNESS_DIR" >/dev/null

cat > "$BIN_DIR/ugnas" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/ugnas" "\$@"
EOF

cat > "$BIN_DIR/cli-anything-ugreen-nas" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/cli-anything-ugreen-nas" "\$@"
EOF

cat > "$BIN_DIR/nas-cli" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/ugnas" "\$@"
EOF

chmod 755 "$BIN_DIR/ugnas" "$BIN_DIR/cli-anything-ugreen-nas" "$BIN_DIR/nas-cli"

"$BIN_DIR/ugnas" --help >/dev/null
"$PYTHON_BIN" "$REPO_ROOT/scripts/install-codex-skill.py" cli-anything-ugreen-nas

echo "Installed ugnas to $BIN_DIR/ugnas"
echo "Installed cli-anything-ugreen-nas to $BIN_DIR/cli-anything-ugreen-nas"
echo "Installed nas-cli compatibility entry to $BIN_DIR/nas-cli"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Add $BIN_DIR to PATH if your shell cannot find ugnas." ;;
esac
