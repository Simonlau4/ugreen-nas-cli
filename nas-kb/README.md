# NAS Knowledge Base

`nas-kb` keeps NAS files as the source material and uses EverOS as a rebuildable document-extraction and semantic-search layer. It never modifies NAS source files while indexing.

## Scope

- Default EverOS scope: `app_id=nas-kb`, `project_id=simon-nas`.
- Default file types: Markdown, PDF, and DOCX.
- Default maximum file size: 50 MiB.
- Local NAS-to-EverOS mapping: `~/.local/state/nas-kb/state.sqlite`.
- Indexing is preview-only unless `--apply` is present.
- Files missing from a later scan are not automatically deleted from EverOS.

EverOS uses the configured LLM, embedding, and rerank providers. Applying an index can therefore send document content to those configured providers. Only index directories whose content is approved for that provider path.

## Prerequisites

- Python 3.11+
- an installed and configured `ugnas` / `nas-cli`
- a reachable EverOS API, normally on `http://127.0.0.1:8765`
- configured EverOS LLM, embedding, and rerank providers

EverOS is an external dependency and is not bundled by this repository. Keep it on the central indexer rather than exposing it to teammates or the public internet.

## Install

From the repository root:

```bash
cd nas-kb
scripts/install.sh
nas-kb --json doctor --path "/Team/Knowledge/Published"
```

The installer also registers the `nas-knowledge-base` Skill under
`$CODEX_HOME/skills` (default: `~/.codex/skills`). Open a new Codex task after
installation so Codex can discover the Skill.

The doctor command checks the NAS path, EverOS, the local state database, and the active EverOS document scope. Fix any failed component before indexing.

## Workflow

Preview changed documents:

```bash
nas-kb --json index \
  --under "/Team/Knowledge/Published" \
  --max-depth 4
```

Apply the index:

```bash
nas-kb --json index \
  --under "/Team/Knowledge/Published" \
  --max-depth 4 \
  --apply
```

Search and reveal the original NAS path:

```bash
nas-kb --json search "project decisions and constraints" --top-k 5 --include-content
```

Download the NAS original for a search-result `doc_id`:

```bash
nas-kb --json get-source d_123456789abc -o ./source.md
```

Inspect local state:

```bash
nas-kb --json status
```

## Team architecture

The team setup separates file access from shared retrieval:

1. Each teammate uses `ugnas` with an individual NAS account and a narrow `allowed_root`.
2. Teammates upload or update source documents in approved NAS knowledge directories.
3. One central `nas-kb` indexer reads changed files and updates the rebuildable EverOS copy.
4. Agents query the authenticated NAS knowledge gateway. They do not connect directly to EverOS or receive the central NAS indexing account.

Keep EverOS on loopback. Bind only the gateway to a Tailscale or company-VPN address.

### Start the shared read gateway

Store a high-entropy read token in the service environment:

```bash
export NAS_KB_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
nas-kb --json serve --host 127.0.0.1 --port 8787
```

For team access, replace `127.0.0.1` with the central indexer's Tailscale or VPN address. Do not expose this gateway directly to the public internet.

The token must contain at least 32 characters. Store it in a secret manager for persistent deployments. The server checks EverOS before binding and exits instead of advertising a gateway that cannot search.

The unauthenticated health endpoint returns service readiness without exposing index contents:

```bash
curl http://127.0.0.1:8787/health
```

### Connect an Agent to shared context

Provide the internal gateway URL and token through the Agent's secret store:

```bash
export NAS_KB_API_URL="http://NAS_KB_TAILSCALE_ADDRESS:8787"
export NAS_KB_API_TOKEN="read-token-from-secret-store"
nas-kb --json remote-search "项目当前决策和约束" --top-k 5 --include-content
```

Retrieve the current NAS source behind a result:

```bash
nas-kb --json remote-get-source d_123456789abc -o ./source.md
```

The gateway is intentionally read-only. Teammates update source documents through their own `ugnas` accounts; only the central indexer applies changes to EverOS.

Existing local source downloads are preserved unless `--overwrite` is explicitly supplied.

### Sync approved team directories

Copy [`config/team-sync.example.toml`](config/team-sync.example.toml) to a private operator config and list only approved `Published/` roots.

Preview every configured root:

```bash
nas-kb --json sync --config ~/.config/nas-kb/team-sync.toml
```

After reviewing the paths and counts, apply the incremental update:

```bash
nas-kb --json sync --config ~/.config/nas-kb/team-sync.toml --apply
```

The sync command does not scan NAS `/`, does not modify source files, and does not delete missing sources or EverOS documents.

See [`docs/team-architecture.md`](docs/team-architecture.md) for rollout stages and permission boundaries.
