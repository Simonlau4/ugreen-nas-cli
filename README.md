# UGREEN NAS CLI

UGREEN NAS CLI is a small, agent-friendly command-line interface for working with UGREEN NAS files over WebDAV. It is designed for teams that want coworkers, scripts, or AI agents to list, read, upload, edit, move, copy, delete, and search NAS files without opening the NAS web UI or installing a desktop client.

The CLI uses each user's own NAS account. Passwords are not stored in this repository; on macOS, the setup script stores them in Keychain and writes only a local profile.

## Shared knowledge layer

V0.1.0 uses `ugnas` / `nas-cli` as the default team path: each teammate connects with an individual NAS account and reads only explicitly allowed roots.

The optional [`nas-kb/`](nas-kb/) package adds semantic retrieval when ordinary NAS file search is insufficient. It builds an incremental knowledge index from approved NAS Markdown, PDF, and DOCX files, keeps NAS files as the source of truth, uses EverOS as a rebuildable retrieval layer, and provides an authenticated read-only gateway for team Agents.

When semantic retrieval is needed, the two layers have separate roles:

- `ugnas` / `nas-cli`: each teammate lists, reads, uploads, and updates files with an individual NAS account.
- `nas-kb`: one central indexer updates approved `Published/` directories and serves shared search context.

The central EverOS service and provider credentials stay private; team Agents receive only a gateway URL and read token.

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

- Python 3.11+
- `git`
- a reachable UGREEN NAS WebDAV endpoint, usually:

```text
https://NAS_IP_OR_DOMAIN:5006
```

For remote use, prefer Tailscale or a company VPN so the WebDAV service is not exposed directly to the public internet.

macOS is required only for the included Keychain helper. The CLI itself also runs on Linux when credentials are supplied through environment variables or another local password command.

## Quick Start

Clone and install:

```bash
git clone https://github.com/Simonlau4/ugreen-nas-cli.git
cd ugreen-nas-cli/agent-harness
scripts/install.sh
```

The installer also registers the `cli-anything-ugreen-nas` Skill under
`$CODEX_HOME/skills` (or `~/.codex/skills` when `CODEX_HOME` is unset). Open a
new Codex task after installation so Codex can discover it.

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

For the startup test, configure the shared Agent knowledge root:

```bash
scripts/setup-profile-macos-keychain.sh \
  --base-url https://NAS_IP_OR_DOMAIN:5006 \
  --username YOUR_NAS_USERNAME \
  --allowed-root "/Agent_Knowledge_Base"

ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

Repeat `--allowed-root` for an approved project root only when the teammate needs project data. The Agent knowledge base does not grant project access. The current startup pilot is complete when a teammate's local Agent reads `STARTUP_TEST_KNOWLEDGE.md` and answers a listed question with that NAS source path; project access and semantic search are not required.

For administrator and teammate rollout, follow [`docs/team-onboarding.md`](docs/team-onboarding.md).

## Deploy the shared knowledge layer

`nas-kb` requires a separately deployed EverOS API. EverOS and its LLM, embedding, and rerank provider credentials are intentionally not bundled in this repository. Before continuing, keep EverOS on the central indexer and verify that its health endpoint returns `status=ok`:

```bash
curl --fail --silent http://127.0.0.1:8765/health
```

Install the knowledge package on the central indexer:

```bash
cd ../nas-kb
scripts/install.sh
nas-kb --json doctor --path "/Team/Knowledge/Published"
```

This separate installer registers the optional `nas-knowledge-base` Skill. Do
not install that Skill on a teammate machine unless the `nas-kb` command and
gateway connection are also configured.

Create the private sync configuration and preview it before the first index:

```bash
mkdir -p ~/.config/nas-kb
cp config/team-sync.example.toml ~/.config/nas-kb/team-sync.toml
# Edit team-sync.toml so it contains only approved Published/ roots.
nas-kb --json sync --config ~/.config/nas-kb/team-sync.toml
nas-kb --json sync --config ~/.config/nas-kb/team-sync.toml --apply
```

Generate a read token of at least 32 characters and start the internal gateway:

```bash
export NAS_KB_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
nas-kb --json serve --host 127.0.0.1 --port 8787
```

`serve` now refuses to start when EverOS is unhealthy. In another shell, verify the gateway:

```bash
curl --fail --silent http://127.0.0.1:8787/health
```

For team access, bind the gateway to the central indexer's Tailscale or company-VPN address and store the token in a secret manager. Do not expose the gateway or EverOS directly to the public internet.

Install `nas-kb` on a teammate or Agent machine to use the read-only client:

```bash
export NAS_KB_API_URL="http://NAS_KB_TAILSCALE_ADDRESS:8787"
export NAS_KB_API_TOKEN="read-token-from-secret-store"
nas-kb --json remote-search "project decisions and constraints" --top-k 5
```

The complete operator workflow and permission boundaries are in [`nas-kb/README.md`](nas-kb/README.md) and [`nas-kb/docs/team-architecture.md`](nas-kb/docs/team-architecture.md).

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
3. dynamic DNS with strict firewall rules, only if your team understands the exposure

Avoid plain HTTP and avoid directly publishing NAS services to the public internet unless you have a clear network security plan.

## Security Model

- Each coworker uses their own NAS account.
- Credentials stay in the user's local environment or macOS Keychain.
- `allowed_roots` constrains all remote paths before network requests are made.
- `rm` requires `--yes`.
- `get` does not overwrite an existing local file unless `--overwrite` is provided.
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
nas-kb/
  scripts/install.sh
  config/team-sync.example.toml
  nas_kb/
skills/
  cli-anything-ugreen-nas/SKILL.md
  nas-knowledge-base/SKILL.md
```

## Development

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install ./agent-harness ./nas-kb pytest
python -m compileall -q agent-harness/cli_anything nas-kb/nas_kb
bash -n agent-harness/scripts/install.sh
bash -n nas-kb/scripts/install.sh
bash -n agent-harness/scripts/setup-profile-macos-keychain.sh
python -m pytest agent-harness/cli_anything/ugreen_nas/tests nas-kb/tests tests -q
```

## Notes

This project currently targets WebDAV. SMB, SFTP, and NFS are intentionally not wrapped because WebDAV gives the simplest HTTP-native command surface for local AI agents and scripts.

## License

This project is licensed under the [MIT License](LICENSE).
