# UGREEN NAS CLI

UGREEN NAS CLI is a small, agent-friendly command-line interface for working with UGREEN NAS files over WebDAV. It is designed for teams that want coworkers, scripts, or AI agents to list, read, upload, edit, move, copy, delete, and search NAS files without opening the NAS web UI or installing a desktop client.

The CLI uses each user's own NAS account. Passwords are not stored in this repository; on macOS, the setup script stores them in Keychain and writes only a local profile.

## Shared knowledge layer

V0.1.0 uses `ugnas` / `nas-cli` as the default team path: each teammate connects with an individual NAS account and reads only explicitly allowed roots.

The current team deployment uses only the NAS CLI and its base Skill. The
shared semantic-search service and knowledge gateway were retired on
2026-09-18; the `nas-kb` material below describes the historical optional layer.

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
ugnas --profile default --json scan --under "/Shared" -o manifest.json
ugnas --profile default --json get-many --manifest manifest.json -o ./download --workers 4
ugnas --profile default --json get-many --manifest manifest.json -o ./download --resume
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

`scan` lists every depth inside the specified roots; omit `--under` to use the profile's allowed roots. `get-many` mirrors NAS paths under the local output directory, downloads with four workers by default, and keeps a private checkpoint in `.ugnas-downloads/`. Use one active download process per output directory. `--resume` rechecks remote metadata, reuses completed files, and resumes partial files when the server supports Range; changed remote files restart. Existing or manually edited local files still require `--overwrite`.

Agents can share a scan manifest even when they use different NAS accounts or connection addresses. A manifest supplies paths; each download checks the current profile's allowed roots and the current NAS account's actual access.

`search` and `recent` default to depth 4 and 100 results; `--all` removes those bounds. Search checks filenames. A skipped directory, depth bound, or result limit produces `complete: false` and exit code 3, with `errors`, `depth_limited`, and `truncated` explaining the coverage. Readable siblings remain available when a directory returns 403 or 404. A 401 credential failure stops requests. A complete scan describes the directories actually read during that run; it is not a frozen NAS snapshot.

## Requirements

- Python 3.11+
- `git`
- a reachable UGREEN NAS WebDAV endpoint, usually:

```text
https://NAS_IP_OR_DOMAIN:5006
```

For remote use, prefer Tailscale or a company VPN so the WebDAV service is not exposed directly to the public internet.

macOS is required only for the included Keychain helper. The CLI itself also runs on Linux when credentials are supplied through environment variables or another local password command.

## Codex Skills

This repository contains two Codex Skills. They are installed separately because
they depend on different command-line tools.

| Skill | Who needs it | What it does | Required command |
| --- | --- | --- | --- |
| `cli-anything-ugreen-nas` | **Required for every teammate.** | Guides the Agent to check the personal NAS connection and allowed roots, load the shared Agent knowledge entry, search and read source files, preserve NAS source paths in answers, and safely perform authorized file operations. | `ugnas` / `nas-cli` |
| `nas-knowledge-base` | **Historical. Not installed for the current team deployment.** | Describes the former semantic-search and indexing layer. | `nas-kb`; indexing required EverOS |

For teammate connection and first-time Q&A acceptance, install only
`cli-anything-ugreen-nas`. Ordinary NAS access and the startup acceptance test
do not require `nas-knowledge-base`.

The installers register the matching Skill automatically:

- `agent-harness/scripts/install.sh` installs `ugnas` and
  `cli-anything-ugreen-nas`.
- `nas-kb/scripts/install.sh` installs `nas-kb` and
  `nas-knowledge-base`.

Open a new Codex task after installation so Codex can discover the Skill.

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
  --allowed-root "/Shared" \
  --audit-root "/Shared/CLI_AUDIT_LOGS"
```

If your NAS still uses a self-signed HTTPS certificate, add `--insecure`:

```bash
scripts/setup-profile-macos-keychain.sh \
  --base-url https://NAS_IP_OR_DOMAIN:5006 \
  --username YOUR_NAS_USERNAME \
  --allowed-root "/Shared" \
  --audit-root "/Shared/CLI_AUDIT_LOGS" \
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
  --allowed-root "/Agent_Knowledge_Base" \
  --audit-root "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"

ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

Repeat `--allowed-root` for an approved project root only when the teammate needs project data. The Agent knowledge base does not grant project access. First-time read-only acceptance is complete when a teammate's local Agent reads `STARTUP_TEST_KNOWLEDGE.md` and answers a listed question with that NAS source path. Before team file writes, also verify the configured NAS audit archive and one approved write receipt.

For administrator and teammate rollout, follow [`docs/team-onboarding.md`](docs/team-onboarding.md).

## Update an existing installation

In the existing repository, preserve any local changes, then run:

```bash
git switch main
git pull --ff-only origin main
cd agent-harness
scripts/install.sh
```

The installer keeps the existing NAS profile and Keychain password. It replaces
the CLI and repository-managed Skill, so preserve any personal Skill changes
first. Do not rerun account setup merely to upgrade. Missing or empty
`audit_root` now defaults to `/Agent_Knowledge_Base/CLI_AUDIT_LOGS`; existing
custom archives are preserved. Keep the credentials and authorized roots, and confirm
`capabilities.audit.remote_root` before team writes. Follow the
[complete update and write-verification steps](docs/team-onboarding.md#update-an-existing-installation).

## Historical shared knowledge layer

This optional layer is not part of current team installation or updates.
The team's shared semantic-search service and gateway are retired.

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

## NAS audit archive

CLI writes automatically create local and NAS audit records. Missing or empty
`audit_root` defaults to `/Agent_Knowledge_Base/CLI_AUDIT_LOGS`, so existing
team profiles gain NAS logging after upgrading without a configuration rewrite.
To select a different archive, set `audit_root` in the profile:

```toml
[profile.default]
# Keep the existing connection and password_command settings.
allowed_roots = ["/Agent_Knowledge_Base", "/YOUR_APPROVED_PROJECT"]
audit_root = "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"
```

The setup script and `profile-init` also accept `--audit-root`. For a short-lived
process, use `UGREEN_NAS_AUDIT_ROOT`. The archive must be inside `allowed_roots`
and writable by the personal NAS account; no permissions are changed by the CLI.
The CLI does not silently fall back to local-only logging. If the archive is
outside the configured allowed roots or cannot save the start record, the
file operation is blocked. For a standalone profile without the shared Agent
root, select an authorized archive such as `/Team/CLI_AUDIT_LOGS`.

`put`, `edit`, `mkdir`, `mv`, `cp`, and `rm` record the NAS username, UTC time,
command, affected NAS paths, and result. Uploads include byte count, SHA-256,
and the overwrite flag; edits also include the SHA-256 of the version read
before editing. File bodies,
passwords, local upload paths, and authentication headers are excluded.

Each operation writes separate `<event_id>.started.json` and
`<event_id>.succeeded.json` (or `.failed.json`) files under a UTC date directory.
Unique IDs and create-only PUTs keep simultaneous users from replacing one
another's records. A `started` record without a result requires checking the
target file; it does not prove that the file was changed. `failed` means the
command failed; after a network interruption the server's final state may
still need checking.

The start record must be saved before the file operation. If it cannot be
saved, the command exits 2 without attempting the file change. If the file
operation succeeds but its completion receipt cannot be saved, the command
exits 3 with `mutation_applied: true` and the available local/NAS receipt paths.
Do not repeat the file operation in that case. Read commands, dry runs, and
unchanged edits create no records. Successful JSON responses include `audit`;
`capabilities` shows the configured archive root.

Inspect the archive with existing read commands:

```bash
ugnas --json ls "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"
ugnas --json recent --under "/Agent_Knowledge_Base/CLI_AUDIT_LOGS" --days 7 --all
ugnas --json cat "/Agent_Knowledge_Base/CLI_AUDIT_LOGS/YYYY-MM-DD/EVENT_ID.succeeded.json"
```

The CLI blocks file mutations inside the configured archive and moves/deletes
of its ancestors. NAS permissions still govern access from other tools. This
is a cooperative CLI activity archive: only upgraded CLI clients are
covered, and older clients or direct WebDAV access can bypass it. Existing
activity cannot be reconstructed from these records. Use NAS administrator
access controls and backups when stronger retention is required.

Before create-only uploads, the client also checks whether the path exists.
This protects existing files on NAS servers that ignore `If-None-Match: *`.
The HTTP condition is still sent; on servers that ignore it, a client-side
existence check cannot make competing writes to the same path atomic. Audit
records use unique event IDs to avoid sharing a destination path.

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
