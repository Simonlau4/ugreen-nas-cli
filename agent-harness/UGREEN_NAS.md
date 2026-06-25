# UGREEN NAS Harness Notes

## Scope

This harness provides file operations for an UGREEN NAS through WebDAV. It is intended for coworkers or their AI agents to run locally with their own NAS accounts.

## Transport Decision

UGREEN NAS supports WebDAV, SMB, FTP, SFTP, and NFS. For an agent-facing CLI, WebDAV over HTTPS is the first target because it has stable HTTP methods, works without mounting drives, and exposes enough metadata for conflict checks.

UGREENlink is not treated as a guaranteed WebDAV transport. It is useful for browser or client-app remote access. The `doctor` command verifies whether a configured URL responds to WebDAV `PROPFIND`; if it does not, use Tailscale or DDNS/VPN to reach the NAS WebDAV endpoint.

## Safety Model

- Each coworker uses their own NAS account.
- Credentials are supplied by environment variables or a local password command.
- On macOS, `scripts/setup-profile-macos-keychain.sh` stores the password in Keychain and writes a profile that calls `security find-generic-password`.
- No real credentials are stored in this repository.
- Allowed roots constrain remote paths before any network request.
- Destructive operations require explicit flags.
- Write operations append a local audit log.

## Commands

- `doctor`: validate profile and WebDAV reachability.
- `ls`, `stat`, `cat`, `get`: read and inspect files.
- `put`, `edit`, `mkdir`, `mv`, `cp`, `rm`: mutate files.
- `search`: bounded recursive name search.

All commands support `--json` for AI agents.
