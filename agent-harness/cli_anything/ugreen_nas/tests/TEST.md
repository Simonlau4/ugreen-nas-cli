# Test Plan

## Test Inventory

- `test_paths.py`: path normalization and allowed-root checks.
- `test_cli_webdav.py`: CLI commands against an in-process WebDAV test server.

## Unit Coverage

- Reject URL-looking remote paths.
- Normalize `..` without escaping allowed roots.
- Enforce allowed roots before network calls.

## E2E Coverage

- `doctor` validates a WebDAV endpoint.
- `ls`, `cat`, `put`, `rm` work through HTTP methods.
- `rm` refuses to run without `--yes`.
- JSON output is parseable by agents.

## Result Log

Append pytest results here after verification.

### 2026-06-25

```text
......                                                                   [100%]
6 passed in 1.79s
```
