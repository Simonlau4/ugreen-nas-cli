# AI Agent Usage

This file is safe to give to a coworker's AI agent after `ugnas` is installed and configured.

## Operating Rules

- Always use `--json`.
- Keep global flags before the command.
- Stay inside the configured shared root, for example `/Shared`.
- Prefer `ls`, `stat`, and `cat` before any write.
- Preview writes with global `--dry-run` before executing them.
- Use `get` before editing binary files such as docx, xlsx, pptx, psd, ai, mov, mp4, or images.
- Do not use `rm` unless the user explicitly asks to delete something.
- `rm` requires `--yes`.

## Health Check

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

## Shared knowledge context

When the user provides `NAS_KB_API_URL` and `NAS_KB_API_TOKEN` through the local secret environment, query the shared read-only gateway:

```bash
curl --silent --show-error \
  -X POST "$NAS_KB_API_URL/v1/search" \
  -H "Authorization: Bearer $NAS_KB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"question to answer","method":"hybrid","top_k":5,"include_content":true}'
```

Preserve the returned `remote_path`. Retrieve the original through `/v1/source/<doc_id>` before making high-confidence factual claims. Never print, log, or paste the gateway token.
