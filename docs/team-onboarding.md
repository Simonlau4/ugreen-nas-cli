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

## Teammate setup on macOS

```bash
git clone https://github.com/Simonlau4/ugreen-nas-cli.git
cd ugreen-nas-cli/agent-harness
scripts/install.sh
scripts/setup-profile-macos-keychain.sh \
  --base-url "https://NAS_TAILSCALE_OR_VPN_ADDRESS:5006" \
  --username "YOUR_NAS_USERNAME" \
  --allowed-root "/Agent_Knowledge_Base"
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

Give the Agent `agent-harness/AI_AGENT_USAGE.md` and the configured profile name. The Agent should begin every new environment with:

```bash
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

This direct NAS workflow is the default team knowledge path. Do not use a department project as the team-level entry, and do not scan NAS `/`.

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
