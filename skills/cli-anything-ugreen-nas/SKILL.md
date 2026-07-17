---
name: cli-anything-ugreen-nas
description: Operate UGREEN NAS files through the local agent-friendly WebDAV CLI. Use when the user asks to search or find NAS assets, list recent NAS files, download or read files from NAS, upload deliverables, create folders, archive or reorganize NAS paths, or preview and perform NAS file changes.
---

# UGREEN NAS CLI

Use this skill when a user wants AI agents to operate files on an UGREEN NAS through a local CLI.

## Preconditions

- The CLI is installed from this repository's `agent-harness/` directory.
- Install with `scripts/install.sh`.
- On macOS, configure each user profile with `scripts/setup-profile-macos-keychain.sh`.
- Each user has their own NAS account.
- The configured endpoint must be a raw WebDAV endpoint. Run `ugnas --json doctor` first.
- Do not store plaintext NAS passwords in project files.

## Commands

Use global flags before subcommands:

```bash
ugnas --profile default --json doctor
ugnas --profile default --json doctor --path /Team
ugnas --profile default --json capabilities
ugnas --profile default --json ls /Team
ugnas --profile default --json cat /Team/brief.md
ugnas --profile default --json get /Team/file.docx -o ./file.docx
ugnas --profile default --json put ./file.docx /Team/file.docx --overwrite
ugnas --profile default --json mkdir /Team/NewFolder
ugnas --profile default --json mv /Team/a.md /Team/archive/a.md --overwrite
ugnas --profile default --json cp /Team/a.md /Team/a-copy.md --overwrite
ugnas --profile default --json rm /Team/a-copy.md --yes
ugnas --profile default --json search "contract" --under /Team --max-depth 4
ugnas --profile default --json recent --under /Team --days 7 --max-depth 4
```

## Safety

- Respect profile `allowed_roots`.
- For a new teammate or Agent environment, verify the exact assigned root with `doctor --path`, then read `capabilities`.
- Use `--json` for agent parsing.
- Inspect with `ls`, `stat`, or `cat`, then preview every write with global `--dry-run`.
- Put global flags before the command, for example `ugnas --json --dry-run mv ...`.
- Require explicit `--yes` for deletion.
- Never convert a deletion preview into a real `rm --yes` without explicit user approval.
- Prefer Tailscale or VPN for remote CLI access if UGREENlink does not pass `doctor`.
- For coworker agent handoff, provide `AI_AGENT_USAGE.md`.
