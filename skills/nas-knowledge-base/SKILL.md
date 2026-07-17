---
name: nas-knowledge-base
description: Search and incrementally index the user's NAS knowledge through the local nas-kb and EverOS tools. Use when the user asks to search or query NAS knowledge, index a NAS folder containing Markdown/PDF/DOCX files, inspect NAS knowledge-index status, retrieve the original NAS file behind a search result, or use the NAS as an Agent knowledge source.
---

# NAS Knowledge Base

Use `nas-kb` for knowledge retrieval and indexing. Use `nas-cli` directly for ordinary file operations that do not need semantic search.

## Check health

Run:

```bash
nas-kb --json doctor
```

The normal scope is `app_id=nas-kb`, `project_id=simon-nas`. Keep it isolated from Codex memory and project knowledge scopes.

## Search

Search the existing index before scanning NAS directories:

```bash
nas-kb --json search "query" --top-k 5 --include-content
```

Return the matched conclusion together with `remote_path`. Use the search-result `doc_id` to retrieve the NAS original when needed:

```bash
nas-kb --json get-source <doc_id> -o <local-path>
```

## Team shared retrieval

Keep EverOS on loopback and expose only the authenticated read gateway over Tailscale or a company VPN:

```bash
NAS_KB_API_TOKEN="<secret-store-value>" \
  nas-kb --json serve --host 127.0.0.1 --port 8787
```

Team Agents receive the gateway URL and read token through their secret store:

```bash
nas-kb --json remote-search "query" --top-k 5 --include-content
nas-kb --json remote-get-source <doc_id> -o <local-path>
```

Use `NAS_KB_API_URL` and `NAS_KB_API_TOKEN`; do not paste the token into prompts or repositories. The gateway is read-only and must not replace each teammate's personal NAS account for source uploads.

## Index

Always select the narrowest relevant NAS directory. Never scan `/` merely because the profile allows all NAS paths.

Preview first:

```bash
nas-kb --json index --under "/target/folder" --max-depth 4
```

Only add `--apply` when the user has authorized indexing that directory:

```bash
nas-kb --json index --under "/target/folder" --max-depth 4 --apply
```

For multiple approved team directories, keep a private TOML config containing only `Published/` roots:

```bash
nas-kb --json sync --config ~/.config/nas-kb/team-sync.toml
nas-kb --json sync --config ~/.config/nas-kb/team-sync.toml --apply
```

Applying an index downloads the supported source files and sends their content to the configured EverOS LLM, embedding, and rerank providers. Treat provider approval as part of indexing authorization.

Default supported files are Markdown, PDF, and DOCX up to 50 MiB. Use repeated `--extension` flags only when the user requests a narrower supported set.

## Safety and boundaries

- Treat NAS files as source material, EverOS as a rebuildable retrieval layer, and Simon as the destination for reviewed long-term conclusions.
- Do not modify NAS source files during indexing.
- Do not automatically delete NAS files or EverOS documents when a source disappears.
- Preserve and report the original NAS path for every result.
- Stop and inspect EverOS when an item reports interrupted indexing; do not blindly retry and create a duplicate.
- Use `nas-kb --json status` to inspect the current mapping and errors.
