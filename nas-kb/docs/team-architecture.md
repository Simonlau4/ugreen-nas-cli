# NAS team knowledge architecture

## Target workflow

```text
Teammate or Agent
  ├─ ugnas + personal NAS account ──> approved NAS source directory
  └─ read token ──> nas-kb gateway ──> EverOS retrieval copy
                                      └─ source lookup ──> NAS original

Central indexer
  └─ restricted indexing account ──> preview/apply changed approved directories
```

The NAS source file is authoritative. EverOS and the local mapping database are rebuildable retrieval infrastructure.

## Permission roles

| Role | NAS source access | Shared search | Apply index |
| --- | --- | --- | --- |
| Teammate | Personal account, assigned roots | Read token | No |
| Teammate Agent | Same local profile, user-approved writes | Read token | No |
| Central indexer | Approved knowledge roots | Local access | Yes |
| Administrator | Account and directory management | Optional | Yes |

Do not share one NAS administrator account, the EverOS provider credentials, or the central indexing token with the whole team.

## Source directory convention

Create the narrowest directories required by each team. A recommended pattern is:

```text
/<Team>/Knowledge/
  Inbox/       new sources awaiting review
  Published/   approved sources included in the shared index
  Archive/     superseded source files retained for traceability
```

The central indexer should scan `Published/`, not the entire NAS and not `Inbox/`.

## Rollout stages

### Stage 1: controlled file access

- Create one NAS account per teammate.
- Assign role-specific roots.
- Install `ugnas`.
- Verify with `doctor --path` and `capabilities`.
- Require `--dry-run` before writes.

### Stage 2: shared read context

- Keep EverOS on `127.0.0.1`.
- Start `nas-kb serve` on a Tailscale or company-VPN interface.
- Distribute only the read token through a secret manager.
- Verify remote search and source retrieval from a second machine.

### Stage 3: governed updates

- Teammates upload new material to `Inbox/`.
- A reviewer moves approved material into `Published/`.
- The central indexer previews and applies only `Published/`.
- Record index failures without deleting NAS originals.

### Stage 4: automation

- Run scheduled incremental previews.
- Notify an administrator when changes or errors are detected.
- Apply approved changes through a reviewed job.
- Rotate gateway tokens and review NAS account permissions periodically.

## Current boundary

The gateway supports authenticated search and original-source retrieval. It does not expose indexing or NAS write endpoints. This prevents an Agent with a read token from publishing, deleting, or re-indexing team knowledge.
