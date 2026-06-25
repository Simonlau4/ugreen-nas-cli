---
name: cli-anything-ugreen-nas
description: Use the UGREEN NAS CLI harness to let agents list, read, upload, edit, move, copy, delete, and search NAS files over WebDAV.
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
ugnas --profile default --json ls /Team
ugnas --profile default --json cat /Team/brief.md
ugnas --profile default --json get /Team/file.docx -o ./file.docx
ugnas --profile default --json put ./file.docx /Team/file.docx --overwrite
ugnas --profile default --json mkdir /Team/NewFolder
ugnas --profile default --json mv /Team/a.md /Team/archive/a.md --overwrite
ugnas --profile default --json cp /Team/a.md /Team/a-copy.md --overwrite
ugnas --profile default --json rm /Team/a-copy.md --yes
ugnas --profile default --json search "contract" --under /Team --max-depth 4
```

## Safety

- Respect profile `allowed_roots`.
- Use `--json` for agent parsing.
- Require explicit `--yes` for deletion.
- Prefer Tailscale or VPN for remote CLI access if UGREENlink does not pass `doctor`.
- For coworker agent handoff, provide `AI_AGENT_USAGE.md`.
