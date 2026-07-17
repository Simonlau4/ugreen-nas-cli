---
name: cli-anything-ugreen-nas
description: Operate UGREEN NAS files and bootstrap shared team context through the local agent-friendly WebDAV CLI. Use when the user asks to connect an Agent to the team NAS knowledge base, search or find NAS assets, list recent NAS files, download or read files, upload deliverables, create folders, archive or reorganize NAS paths, or preview and perform NAS file changes.
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

## Team bootstrap

For a team Agent environment, always begin with:

```bash
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

Then:

1. For the startup test, answer from `STARTUP_TEST_KNOWLEDGE.md`.
2. For a project question, select the relevant department or project root from `PROJECTS.md`, then confirm that exact root with `doctor --path`.
3. Operate only inside roots listed by `capabilities` and actually granted to the current NAS account.
4. Treat `PROJECTS.md` as navigation, not permission.

If `/Agent_Knowledge_Base` returns `401`, `403`, or `404` during team onboarding, stop and report that the account is missing knowledge-base access. Do not fall back to scanning `/` or use a department project as the team entry.

## Knowledge Q&A

When answering a question with NAS knowledge:

1. For the startup test, read `STARTUP_TEST_KNOWLEDGE.md` from its exact path.
2. For a project question, select the authorized project root from `PROJECTS.md`, search only inside that root, then read candidate source files with `cat` or `get`.
3. Treat filenames and search matches as discovery clues, not evidence; base the answer on file contents.
4. Include the key NAS source paths in the answer and distinguish sourced facts from inference.
5. If the authorized files do not support an answer, state the evidence gap instead of scanning `/` or guessing.

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
- For a team startup test, require `/Agent_Knowledge_Base`.
- Before using project data, require and verify the explicitly assigned department or project root with `doctor --path`.
- Use `--json` for agent parsing.
- Inspect with `ls`, `stat`, or `cat`, then preview every write with global `--dry-run`.
- Put global flags before the command, for example `ugnas --json --dry-run mv ...`.
- Require explicit `--yes` for deletion.
- Do not overwrite an existing local download unless requested; `get` requires `--overwrite`.
- Never convert a deletion preview into a real `rm --yes` without explicit user approval.
- Prefer Tailscale or VPN for remote CLI access if UGREENlink does not pass `doctor`.
- For coworker agent handoff, provide `AI_AGENT_USAGE.md`.
