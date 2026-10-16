# Team onboarding

This repository gives each teammate and their AI Agent a controlled file interface to the NAS. Every person uses an individual NAS account. Do not share one administrator account across the team.

The current team pilot covers connection and read-only knowledge Q&A. File writes and the optional semantic-search gateway are not required for this pilot.

## Administrator preparation

1. Create one NAS account per teammate.
2. Grant read access to `/Agent_Knowledge_Base`.
3. When project access is needed, grant only the department or project directories required for that person's role.
4. Provide a WebDAV address reachable through Tailscale or the company VPN.
5. Send the teammate the knowledge root and assigned project roots, not an unrestricted `/` root.

The Agent knowledge base contains the shared entry, project navigation, and approved startup test material. Department and project source files remain in their own NAS roots.

## Skills required for the current pilot

- Install `cli-anything-ugreen-nas` for every teammate. It guides the Agent to
  verify the personal NAS connection and allowed roots, load the shared
  knowledge entry, read current source files, preserve NAS paths in answers,
  and safely use authorized file operations.
- Do not install `nas-knowledge-base` for the current pilot. It is an optional
  semantic-search Skill for the central indexer or an Agent machine that
  already has the `nas-kb` command and shared gateway connection.

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

For existing installations, update the CLI from the approved repository version
and add `audit_root = "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"` to each member's
existing `[profile.default]` configuration. Preserve the existing credentials
and authorized roots. Confirm `capabilities.audit.remote_root` and verify an
authorized upload's `audit.remote_path` by reading that NAS record back.
The personal account needs write access to the archive. An inaccessible or
uncreatable archive blocks writes before the business file operation. Do not widen NAS
permissions as part of setup without administrator approval. See the
[audit archive behavior and receipt handling](../README.md#nas-audit-archive).

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

The NAS file is immediately available to authorized Agents and remains the source of truth. If the optional semantic indexer is enabled later, it can detect approved changed files and rebuild its retrieval copy.

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

If ordinary file search later proves insufficient, an administrator can optionally provide the internal semantic-search gateway URL and a read token through the Agent's secret store. Never paste the NAS password or gateway token into prompts, repositories, or shared documents.

The gateway uses a small HTTP contract that any Agent can call:

```bash
export NAS_KB_API_URL="http://NAS_KB_TAILSCALE_ADDRESS:8787"
export NAS_KB_API_TOKEN="read-token-from-secret-store"

curl --silent --show-error \
  -X POST "$NAS_KB_API_URL/v1/search" \
  -H "Authorization: Bearer $NAS_KB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"project decisions and constraints","method":"hybrid","top_k":5,"include_content":true}'
```

Download the authoritative NAS source for a returned `doc_id`:

```bash
curl --silent --show-error \
  "$NAS_KB_API_URL/v1/source/DOC_ID" \
  -H "Authorization: Bearer $NAS_KB_API_TOKEN" \
  -o "./source-file"
```

The optional read token cannot upload, edit, delete, or re-index NAS content.
