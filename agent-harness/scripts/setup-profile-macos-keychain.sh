#!/usr/bin/env bash
set -euo pipefail

PROFILE="default"
BASE_URL=""
USERNAME=""
SERVICE="ugreen-nas"
INSECURE=0
RUN_DOCTOR=1
ALLOWED_ROOTS=()

usage() {
  cat <<'EOF'
Usage:
  setup-profile-macos-keychain.sh \
    --base-url https://NAS_OR_TAILSCALE:5006 \
    --username alice \
    --allowed-root "/Shared" \
    [--profile default] [--service ugreen-nas] [--insecure] [--no-doctor]

Stores the NAS password in macOS Keychain, then writes:
  ~/.config/ugreen-nas-cli/config.toml

No plaintext password is written to the repository or config file.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --username)
      USERNAME="$2"
      shift 2
      ;;
    --allowed-root)
      ALLOWED_ROOTS+=("$2")
      shift 2
      ;;
    --service)
      SERVICE="$2"
      shift 2
      ;;
    --insecure)
      INSECURE=1
      shift
      ;;
    --no-doctor)
      RUN_DOCTOR=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script uses macOS Keychain and only runs on macOS." >&2
  exit 1
fi

if ! command -v security >/dev/null 2>&1; then
  echo "macOS security command not found." >&2
  exit 1
fi

UGNAS_BIN="${UGNAS_BIN:-}"
if [[ -z "$UGNAS_BIN" ]]; then
  if command -v ugnas >/dev/null 2>&1; then
    UGNAS_BIN="$(command -v ugnas)"
  elif [[ -x "$HOME/.local/bin/ugnas" ]]; then
    UGNAS_BIN="$HOME/.local/bin/ugnas"
  else
    echo "ugnas not found. Run scripts/install.sh first." >&2
    exit 1
  fi
fi

if [[ -z "$BASE_URL" ]]; then
  read -r -p "WebDAV base URL, e.g. https://NAS_OR_TAILSCALE:5006: " BASE_URL
fi
if [[ -z "$USERNAME" ]]; then
  read -r -p "NAS username: " USERNAME
fi
if [[ ${#ALLOWED_ROOTS[@]} -eq 0 ]]; then
  read -r -p "Allowed NAS root, e.g. /Shared: " root
  ALLOWED_ROOTS+=("$root")
fi

read -r -s -p "NAS password for $USERNAME: " PASSWORD
echo
if [[ -z "$PASSWORD" ]]; then
  echo "Password cannot be empty." >&2
  exit 1
fi

security add-generic-password -U -s "$SERVICE" -a "$USERNAME" -w "$PASSWORD" >/dev/null
unset PASSWORD

PROFILE_ARGS=(
  --profile "$PROFILE"
  profile-init
  --base-url "$BASE_URL"
  --username "$USERNAME"
  --macos-keychain-service "$SERVICE"
)

for root in "${ALLOWED_ROOTS[@]}"; do
  PROFILE_ARGS+=(--allowed-root "$root")
done

if [[ "$INSECURE" -eq 1 ]]; then
  PROFILE_ARGS+=(--insecure)
fi

"$UGNAS_BIN" "${PROFILE_ARGS[@]}"

if [[ "$RUN_DOCTOR" -eq 1 ]]; then
  "$UGNAS_BIN" --profile "$PROFILE" --json doctor
fi
