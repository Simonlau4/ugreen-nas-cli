# UGREEN NAS CLI Harness

This directory contains the installable Python CLI package for `ugnas`.

For the project overview, start with the repository root `README.md`. For promptable AI-agent instructions, use `AI_AGENT_USAGE.md`.

## Install Locally

```bash
scripts/install.sh
ugnas --help
```

The install script creates a venv under `~/.local/share/ugreen-nas-cli` and writes small launcher scripts to `~/.local/bin`.
It also registers the `cli-anything-ugreen-nas` Skill under
`$CODEX_HOME/skills` (default: `~/.codex/skills`). Open a new Codex task after
installation so Codex can discover the Skill.

The package installs two commands:

- `ugnas`
- `cli-anything-ugreen-nas`

## Configure A Profile On macOS

```bash
scripts/setup-profile-macos-keychain.sh \
  --base-url https://NAS_IP_OR_DOMAIN:5006 \
  --username YOUR_NAS_USERNAME \
  --allowed-root "/Shared"
```

If the NAS uses a self-signed HTTPS certificate, add `--insecure` for now. Prefer a trusted certificate for normal use.

The generated config lives at:

```text
~/.config/ugreen-nas-cli/config.toml
```

The password stays in macOS Keychain.

## Environment Variable Mode

For short-lived tests, environment variables also work:

```bash
export UGREEN_NAS_BASE_URL="https://NAS_IP_OR_DOMAIN:5006"
export UGREEN_NAS_USERNAME="alice"
export UGREEN_NAS_PASSWORD="..."
export UGREEN_NAS_ALLOWED_ROOTS="/Shared:/Team"
ugnas --json doctor
```

Do not commit shell scripts or docs containing real passwords.

## Common Commands

```bash
ugnas --profile default --json doctor
ugnas --profile default --json ls "/Shared"
ugnas --profile default --json cat "/Shared/brief.md"
# Download to a new local path:
ugnas --profile default --json get "/Shared/report.docx" -o ./report.docx
# Replace an existing local download:
ugnas --profile default --json get "/Shared/report.docx" -o ./report.docx --overwrite
ugnas --profile default --json put ./report.docx "/Shared/report.docx" --overwrite
ugnas --profile default --json mkdir "/Shared/NewFolder"
ugnas --profile default --json mv "/Shared/a.md" "/Shared/archive/a.md" --overwrite
ugnas --profile default --json cp "/Shared/a.md" "/Shared/a-copy.md" --overwrite
ugnas --profile default --json rm "/Shared/a-copy.md" --yes
ugnas --profile default --json search "contract" --under "/Shared" --max-depth 4
ugnas --profile default --json recent --under "/Shared" --days 7 --max-depth 4
ugnas --profile default --json --dry-run rm "/Shared/a-copy.md"
```

Place global flags such as `--json` and `--dry-run` before the command. A dry run never writes an audit event because it does not change the NAS.

`get` preserves an existing local file unless `--overwrite` is supplied.

## Remote Access Choice

The CLI needs a raw WebDAV endpoint. If an endpoint passes `ugnas --json doctor`, it can be used.

Recommended:

- Tailscale or company VPN for remote access
- WebDAV over HTTPS
- a trusted certificate and domain name when possible

Use UGREENlink only if `doctor` confirms it exposes WebDAV methods.

## Tests

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e . pytest
python -m pytest cli_anything/ugreen_nas/tests -q
```
