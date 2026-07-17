# AI Agent Usage

This file is safe to give to a coworker's AI agent after `ugnas` is installed and configured.

## Operating Rules

- Always use `--json`.
- Keep global flags before the command.
- Stay inside the configured allowed roots.
- Prefer `ls`, `stat`, and `cat` before any write.
- Preview writes with global `--dry-run` before executing them.
- Use `get` before editing binary files such as docx, xlsx, pptx, psd, ai, mov, mp4, or images.
- Never overwrite an existing local download unless the user requested it; `get` requires `--overwrite`.
- Do not use `rm` unless the user explicitly asks to delete something.
- `rm` requires `--yes`.

## Team startup

For the team Agent setup, start every new environment with:

```bash
ugnas --profile default --json doctor --path "/Agent_Knowledge_Base"
ugnas --profile default --json capabilities
ugnas --profile default --json cat "/Agent_Knowledge_Base/AGENT_ENTRY.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/PROJECTS.md"
ugnas --profile default --json cat "/Agent_Knowledge_Base/STARTUP_TEST_KNOWLEDGE.md"
```

For a project question, choose the relevant project from `PROJECTS.md`, then verify that exact project root:

```bash
ugnas --profile default --json doctor --path "/YOUR_TEAM_ROOT"
```

`PROJECTS.md` provides navigation; it does not grant access. If the knowledge root returns `401`, `403`, or `404`, report the missing permission and stop. Do not scan `/` or use a department project as the team entry.

## Answer questions with NAS knowledge

1. For the startup test, read `STARTUP_TEST_KNOWLEDGE.md` from its exact path.
2. For a project question, select the authorized project root from `PROJECTS.md`, then use `search`, `recent`, `ls`, and `stat` inside that root.
3. Read the current source with `cat`, or download a binary file with `get` before analyzing it.
4. Answer from the file contents and include the key NAS source paths.
5. If the available files are insufficient, state what is missing. Do not guess or expand the search beyond the configured roots.

## Generic health check

For a standalone setup without the team knowledge root:

```bash
ugnas --profile default --json doctor --path "/Shared"
ugnas --profile default --json capabilities
```

If this fails with a certificate error, the NAS is using a self-signed certificate. Ask the user whether the profile was intentionally created with `--insecure`.

## Read Commands

```bash
ugnas --profile default --json ls "/Shared"
ugnas --profile default --json stat "/Shared/path/to/file.md"
ugnas --profile default --json cat "/Shared/path/to/file.md"
ugnas --profile default --json get "/Shared/path/to/file.docx" -o "./file.docx"
ugnas --profile default --json search "keyword" --under "/Shared" --max-depth 4 --limit 50
ugnas --profile default --json recent --under "/Shared" --days 7 --max-depth 4 --limit 50
```

## Write Commands

```bash
ugnas --profile default --json mkdir "/Shared/NewFolder"
ugnas --profile default --json put "./local.md" "/Shared/NewFolder/local.md"
ugnas --profile default --json put "./local.md" "/Shared/NewFolder/local.md" --overwrite
ugnas --profile default --json edit "/Shared/NewFolder/local.md"
ugnas --profile default --json cp "/Shared/a.md" "/Shared/a-copy.md"
ugnas --profile default --json mv "/Shared/a-copy.md" "/Shared/archive/a-copy.md"
ugnas --profile default --json rm "/Shared/archive/a-copy.md" --yes
```

Preview any mutating command by putting `--dry-run` before the command:

```bash
ugnas --profile default --json --dry-run put "./local.md" "/Shared/NewFolder/local.md"
ugnas --profile default --json --dry-run mv "/Shared/a.md" "/Shared/archive/a.md"
ugnas --profile default --json --dry-run rm "/Shared/archive/a.md"
```

`rm` requires `--yes` only for the real deletion. Never turn a dry-run preview into a real deletion without explicit user approval.

## Remote Access Notes

The CLI needs a raw WebDAV endpoint, not just a browser login page. Prefer:

- Tailscale or company VPN to reach `https://NAS_IP_OR_MAGICDNS:5006`.
- Trusted HTTPS certificate when possible.

UGREENlink is useful for browser/client access, but only use it with this CLI if `ugnas --json doctor` succeeds.

## Optional semantic search

Only when ordinary NAS file search is insufficient and the user provides `NAS_KB_API_URL` and `NAS_KB_API_TOKEN` through the local secret environment, query the shared read-only gateway:

```bash
curl --silent --show-error \
  -X POST "$NAS_KB_API_URL/v1/search" \
  -H "Authorization: Bearer $NAS_KB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"question to answer","method":"hybrid","top_k":5,"include_content":true}'
```

Preserve the returned `remote_path`. Retrieve the original through `/v1/source/<doc_id>` before making high-confidence factual claims. Never print, log, or paste the gateway token.
