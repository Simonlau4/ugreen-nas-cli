# Team onboarding

This repository gives each teammate and their AI Agent a controlled file interface to the NAS. Every person uses an individual NAS account. Do not share one administrator account across the team.

First-time acceptance covers connection and read-only knowledge Q&A. Team file
writes use the current CLI with NAS audit logging enabled. Existing users can
follow [Update an existing installation](#update-an-existing-installation)
without resetting their account or authorized roots.

## Administrator preparation

1. Create one NAS account per teammate.
2. Grant read access to `/Agent_Knowledge_Base`.
   Members who write files also need read/write access to
   `/Agent_Knowledge_Base/CLI_AUDIT_LOGS`; this does not require write access to
   the entire knowledge root.
3. When project access is needed, grant only the department or project directories required for that person's role.
4. Provide a WebDAV address reachable through Tailscale or the company VPN.
5. Send the teammate the knowledge root and assigned project roots, not an unrestricted `/` root.

The Agent knowledge base contains the shared entry, project navigation, and approved startup test material. Department and project source files remain in their own NAS roots.

## Required Skill

- Install `cli-anything-ugreen-nas` for every teammate. It guides the Agent to
  verify the personal NAS connection and allowed roots, load the shared
  knowledge entry, read current source files, preserve NAS paths in answers,
  and safely use authorized file operations.
- Do not install `nas-knowledge-base` for the current team deployment. The shared
  semantic-search service and knowledge gateway were retired on 2026-09-18.

See the repository [Codex Skills overview](../README.md#codex-skills) for the
runtime dependency and installation mapping for each Skill.

## Teammate setup on macOS

```bash
git clone https://github.com/Simonlau4/ugreen-nas-cli.git
cd ugreen-nas-cli/agent-harness
scripts/install.sh
scripts/setup-profile-macos-keychain.sh \
  --base-url "https://NAS_TAILSCALE_OR_VPN_ADDRESS:5006" \
  --username "YOUR_NAS_USERNAME" \
  --allowed-root "/Agent_Knowledge_Base" \
  --audit-root "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"
```

`scripts/install.sh` installs both the `ugnas` command and the
`cli-anything-ugreen-nas` Codex Skill. Confirm that
`~/.codex/skills/cli-anything-ugreen-nas/SKILL.md` exists, then open a new Codex
task before the Q&A acceptance test.

If the CLI was installed from an earlier repository version, repair only the
missing Skill from the repository root:

```bash
python3 scripts/install-codex-skill.py cli-anything-ugreen-nas
```

On Windows PowerShell, use:

```powershell
py scripts\install-codex-skill.py cli-anything-ugreen-nas
```

Repeat `--allowed-root` for an approved project root only when project access is needed. Verify the knowledge root:

```bash
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

The `audit.remote_root` field in `capabilities` must be
`/Agent_Knowledge_Base/CLI_AUDIT_LOGS` before team file writes. Read-only startup
acceptance does not create audit records or test write access.

## Update an existing installation

Open the existing repository directory and inspect local changes first:

```bash
cd /path/to/your/ugreen-nas-cli
git status --short
```

Replace the example path with the actual checkout. Preserve any local changes
before continuing. With a clean checkout, update and reinstall:

```bash
git switch main
git pull --ff-only origin main
cd agent-harness
scripts/install.sh
```

The installer replaces CLI launchers and the repository-managed Codex Skill.
It leaves `~/.config/ugreen-nas-cli/config.toml` and the Keychain password
untouched. Preserve any personal Skill customizations before reinstalling.
Do not rerun the account setup script merely to update the CLI. If the old
checkout is unavailable, clone into a new directory and run only the install
step; the existing profile remains usable.

The updated CLI automatically uses `/Agent_Knowledge_Base/CLI_AUDIT_LOGS` when
`audit_root` is missing or empty. No profile edit is required for that default;
existing custom archives are preserved. To select the archive explicitly,
set this key in the existing profile section:

```toml
audit_root = "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"
```

Keep the existing connection, username, password command, TLS settings, and
authorized roots. Do not create duplicate profile sections or duplicate keys.
For a named profile, edit that section and use its name with `--profile`.
If the archive is outside the existing allowed roots, an administrator must
confirm account access before adding that exact archive path to the roots;
do not replace the existing roots or grant `/` access.

Check the updated executable and profile:

```bash
command -v ugnas
ugnas --profile default --json capabilities
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"
```

Verify the `audit` field exists and `audit.remote_root` matches the configured
archive. The package version alone does not establish that auditing is present.
An unsupported `--audit-root` option or a missing `audit` field means an older
CLI is still running; check `command -v ugnas` and the shell PATH. Open a new
Codex task after the Skill is installed.

## Verify an audited write

Use an approved writable project directory and a new, personal test filename.
Replace the project root and username placeholders below. This creates one
small file; the read-only startup test above is separate.

```bash
ugnas --profile default --json doctor --path "/YOUR_APPROVED_PROJECT"
ugnas --profile default --json --dry-run put - "/YOUR_APPROVED_PROJECT/cli-audit-check-YOUR_NAS_USERNAME.txt"
printf '%s\n' 'NAS CLI audit check' | ugnas --profile default --json put - "/YOUR_APPROVED_PROJECT/cli-audit-check-YOUR_NAS_USERNAME.txt"
ugnas --profile default --json cat "/YOUR_APPROVED_PROJECT/cli-audit-check-YOUR_NAS_USERNAME.txt"
```

Read the `audit.remote_path` returned by the upload with `ugnas --json cat`.
It must contain the personal NAS username, the exact test path, action `put`,
and status `succeeded`. Do not delete the test file without approval.

An inaccessible or uncreatable audit archive blocks the file write. Exit code
3 with `mutation_applied: true` means the file change succeeded but its receipt
is incomplete: inspect the file and receipt paths, and do not repeat the write.
No NAS permissions are changed by installation. Older clients, non-CLI uploads
and historical operations are outside coverage. See the
[audit archive behavior](../README.md#nas-audit-archive).

## Upload or update a knowledge source

Inspect the destination and preview the upload:

```bash
ugnas --profile default --json ls "/YOUR_TEAM_ROOT/Knowledge"
ugnas --profile default --json --dry-run put "./new-note.md" "/YOUR_TEAM_ROOT/Knowledge/new-note.md"
```

After reviewing the preview, perform the upload:

```bash
ugnas --profile default --json put "./new-note.md" "/YOUR_TEAM_ROOT/Knowledge/new-note.md"
```

Updating an existing source requires both a preview and an explicit overwrite:

```bash
ugnas --profile default --json --dry-run put "./new-note.md" "/YOUR_TEAM_ROOT/Knowledge/new-note.md" --overwrite
ugnas --profile default --json put "./new-note.md" "/YOUR_TEAM_ROOT/Knowledge/new-note.md" --overwrite
```

The NAS file is immediately available to authorized Agents and remains the source of truth. Confirm the returned audit receipt after each team write.

## Give access to an AI Agent

Give the Agent `agent-harness/AI_AGENT_USAGE.md` and the configured profile name. For first-time onboarding and its acceptance test, the Agent begins with:

```bash
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

This is the team onboarding workflow. For later tasks where the user supplies a project path, check that exact path against `capabilities` and `doctor --path`, then operate inside the assigned scope. The shared entry is unnecessary for those tasks. A failed onboarding check stops that test; it does not block another project whose access has been independently verified. Do not scan NAS `/` to find a substitute onboarding entry.

## Q&A acceptance test

Ask the teammate's Agent one question listed in `STARTUP_TEST_KNOWLEDGE.md`. The Agent passes when it:

1. Reads `AGENT_ENTRY.md` and `PROJECTS.md`.
2. Reads `STARTUP_TEST_KNOWLEDGE.md` from its exact NAS path.
3. Answers from the file contents instead of relying on a filename alone.
4. Answers the question and includes the key NAS source path.
5. Reports missing evidence instead of guessing when the authorized files are insufficient.

Use `search --all`, `scan`, and `get-many` inside the approved roots for larger
file sets. The current team deployment uses individual NAS access, without a
central semantic indexer or shared knowledge gateway.
