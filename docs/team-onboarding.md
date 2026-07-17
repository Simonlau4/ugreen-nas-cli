# Team onboarding

This repository gives each teammate and their AI Agent a controlled file interface to the NAS. Every person uses an individual NAS account. Do not share one administrator account across the team.

## Administrator preparation

1. Create one NAS account per teammate.
2. Grant only the shared directories required for that person's role.
3. Provide a WebDAV address reachable through Tailscale or the company VPN.
4. Send the teammate the allowed NAS root, not an unrestricted `/` root.

The knowledge-search gateway is separate from NAS file credentials. Teammates receive a read token for the gateway; the central indexer keeps the NAS indexing account and model-provider credentials private.

## Teammate setup on macOS

```bash
git clone https://github.com/Simonlau4/ugreen-nas-cli.git
cd ugreen-nas-cli/agent-harness
scripts/install.sh
scripts/setup-profile-macos-keychain.sh \
  --base-url "https://NAS_TAILSCALE_OR_VPN_ADDRESS:5006" \
  --username "YOUR_NAS_USERNAME" \
  --allowed-root "/YOUR_TEAM_ROOT"
```

Verify the exact directory granted by the administrator:

```bash
ugnas --profile default --json doctor --path "/YOUR_TEAM_ROOT"
ugnas --profile default --json capabilities
ugnas --profile default --json ls "/YOUR_TEAM_ROOT"
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

The central indexer detects approved changed files and rebuilds the retrieval copy. The NAS file remains the source of truth.

## Give access to an AI Agent

Give the Agent `agent-harness/AI_AGENT_USAGE.md` and the configured profile name. The Agent should begin every new environment with:

```bash
ugnas --profile default --json doctor --path "/YOUR_TEAM_ROOT"
ugnas --profile default --json capabilities
```

For shared knowledge context, also provide the internal knowledge-gateway URL and a read token through the Agent's secret store. Never paste the NAS password or gateway token into prompts, repositories, or shared documents.

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

The read token cannot upload, edit, delete, or re-index NAS content.
