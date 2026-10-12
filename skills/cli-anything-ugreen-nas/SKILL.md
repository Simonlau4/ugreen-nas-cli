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
- The configured endpoint must be a raw WebDAV endpoint. Run `ugnas --json doctor --path` on the task's assigned root first.
- Do not store plaintext NAS passwords in project files.

## Team bootstrap

For first-time team onboarding and its startup acceptance test, begin with:

```bash
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

Then:

1. For the startup test, answer from `STARTUP_TEST_KNOWLEDGE.md`.
2. When the user has not supplied a project root, select it from `PROJECTS.md`, then confirm that exact root with `doctor --path`.
3. Operate only inside roots listed by `capabilities` and actually granted to the current NAS account.
4. Treat `PROJECTS.md` as navigation, not permission.

If `/Agent_Knowledge_Base` returns `401`, `403`, or `404` during team onboarding, report the failure and stop that onboarding test. Do not infer the cause from 404 alone or discover a substitute entry by scanning `/`.

## Direct assigned-path tasks

When the user supplies a NAS path, read `capabilities`, verify that exact path with `doctor --path`, then operate inside the assigned scope. This flow does not require the shared entry or `PROJECTS.md`; a failed onboarding test does not block an independently authorized project task. A failed credential check (401) stops requests; a denied directory (403) remains inaccessible.

For complete library reads, use `scan --under /AssignedRoot -o manifest.json`, then `get-many --manifest manifest.json -o ./download --workers 4`. Use a separate local output directory for each Agent's download. Rerun `get-many` with `--resume` after interruption; changed remote files restart and manually modified local files still require `--overwrite`.

Agents may share a manifest across NAS accounts and connection addresses. The manifest supplies paths; the current profile and NAS account determine access for each download.

`search` and `recent` retain bounded defaults; use `--all` when the task needs every depth and match. Inspect `complete`, `truncated`, `depth_limited`, and `errors`. Exit code 3 means partial results: report skipped paths and coverage, and use readable results without claiming a complete scan. Increasing depth or result count stays inside the assigned roots and existing NAS permissions.

## Knowledge Q&A

When answering a question with NAS knowledge:

1. For the startup test, read `STARTUP_TEST_KNOWLEDGE.md` from its exact path.
2. Use the user-assigned root, or select one from `PROJECTS.md` when needed; verify access, search inside that root, then read candidate source files with `cat` or `get`.
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
ugnas --profile default --json search "contract" --under /Team --all
ugnas --profile default --json scan --under /Team -o manifest.json
ugnas --profile default --json get-many --manifest manifest.json -o ./download --workers 4
ugnas --profile default --json get-many --manifest manifest.json -o ./download --resume
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
