# UGREEN NAS CLI

UGREEN NAS CLI is a small, agent-friendly command-line interface for working with UGREEN NAS files over WebDAV. It is designed for teams that want coworkers, scripts, or AI agents to list, read, upload, edit, move, copy, delete, and search NAS files without opening the NAS web UI or installing a desktop client.

The CLI uses each user's own NAS account. Passwords are not stored in this repository; on macOS, the setup script stores them in Keychain and writes only a local profile.

## Why This Exists

NAS web apps are built for humans. AI agents and automation tools need a stable command surface with structured output. This project provides:

- JSON output for AI agents and scripts
- WebDAV-based file operations
- local profiles with allowed root directories
- macOS Keychain setup for per-user credentials
- explicit safety gates for deletion and overwrites
- a short `AI_AGENT_USAGE.md` file that can be handed to another agent

## What It Can Do

```bash
ugnas --profile default --json doctor
ugnas --profile default --json ls "/Shared"
ugnas --profile default --json cat "/Shared/brief.md"
ugnas --profile default --json get "/Shared/report.docx" -o ./report.docx
ugnas --profile default --json put ./draft.md "/Shared/draft.md"
ugnas --profile default --json edit "/Shared/notes.md"
ugnas --profile default --json mkdir "/Shared/NewFolder"
ugnas --profile default --json cp "/Shared/a.md" "/Shared/a-copy.md"
ugnas --profile default --json mv "/Shared/a-copy.md" "/Shared/archive/a-copy.md"
ugnas --profile default --json rm "/Shared/archive/a-copy.md" --yes
ugnas --profile default --json search "contract" --under "/Shared" --max-depth 4
ugnas --profile default --json recent --under "/Shared" --days 7 --max-depth 4
ugnas --profile default --json --dry-run mv "/Shared/draft.md" "/Shared/archive/draft.md"
```

## Requirements

- macOS for the included Keychain setup script
- Python 3.11+
- `git`
- a reachable UGREEN NAS WebDAV endpoint, usually:

```text
https://NAS_IP_OR_DOMAIN:5006
```

For remote use, prefer Tailscale or a company VPN so the WebDAV service is not exposed directly to the public internet.

## Quick Start

Clone and install:

```bash
git clone https://github.com/Simonlau4/ugreen-nas-cli.git
cd ugreen-nas-cli/agent-harness
scripts/install.sh
```

Configure your own NAS account:

```bash
scripts/setup-profile-macos-keychain.sh \
  --base-url https://NAS_IP_OR_DOMAIN:5006 \
  --username YOUR_NAS_USERNAME \
  --allowed-root "/Shared"
```

If your NAS still uses a self-signed HTTPS certificate, add `--insecure`:

```bash
scripts/setup-profile-macos-keychain.sh \
  --base-url https://NAS_IP_OR_DOMAIN:5006 \
  --username YOUR_NAS_USERNAME \
  --allowed-root "/Shared" \
  --insecure
```

Verify:

```bash
ugnas --profile default --json doctor --path "/Shared"
ugnas --profile default --json capabilities
ugnas --profile default --json ls "/Shared"
```

For administrator and teammate rollout, follow [`docs/team-onboarding.md`](docs/team-onboarding.md).

## Giving It To An AI Agent

After setup, give the agent this file:

```text
agent-harness/AI_AGENT_USAGE.md
```

Tell the agent to:

- always use `--json`
- stay inside the configured allowed root
- inspect with `ls`, `stat`, or `cat` before writing
- avoid `rm` unless explicitly asked by the user

## Remote Access Notes

The CLI needs a raw WebDAV endpoint. UGREENlink is useful for browser or UGREEN client access, but it may not expose WebDAV methods directly. Use `ugnas --json doctor` to test an endpoint before giving it to coworkers or agents.

Recommended order:

1. Tailscale or company VPN to reach the NAS WebDAV endpoint
2. trusted HTTPS certificate and domain name
3. DDNS with strict firewall rules, only if your team understands the exposure

Avoid plain HTTP and avoid directly publishing NAS services to the public internet unless you have a clear network security plan.

## Security Model

- Each coworker uses their own NAS account.
- Credentials stay in the user's local environment or macOS Keychain.
- `allowed_roots` constrains all remote paths before network requests are made.
- `rm` requires `--yes`.
- `put` does not overwrite existing files unless `--overwrite` is provided.
- `--dry-run` previews `put`, `edit`, `mkdir`, `mv`, `cp`, and `rm` without changing the NAS.
- Mutating operations append a local audit log by default.

## Project Layout

```text
agent-harness/
  scripts/install.sh
  scripts/setup-profile-macos-keychain.sh
  AI_AGENT_USAGE.md
  cli_anything/ugreen_nas/
skills/
  cli-anything-ugreen-nas/SKILL.md
```

## Development

```bash
cd agent-harness
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e . pytest
python -m pytest cli_anything/ugreen_nas/tests -q
```

## Notes

This project currently targets WebDAV. SMB, SFTP, and NFS are intentionally not wrapped because WebDAV gives the simplest HTTP-native command surface for local AI agents and scripts.
