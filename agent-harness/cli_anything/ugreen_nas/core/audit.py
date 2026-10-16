from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ConfigError, Profile
from .paths import assert_allowed, is_under_root
from .webdav import WebDavClient, WebDavError


class AuditError(RuntimeError):
    def __init__(self, message: str, mutation_applied: bool | None, receipt: dict[str, Any]):
        super().__init__(message)
        self.mutation_applied = mutation_applied
        self.receipt = receipt


def append_audit(path: Path | None, event: dict[str, Any]) -> None:
    if path is None:
        return

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    with expanded.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    try:
        os.chmod(expanded, 0o600)
    except OSError:
        pass


@contextmanager
def audited_write(profile: Profile, client: WebDavClient, action: str, **fields: Any):
    root = assert_allowed(profile.audit_root, profile.allowed_roots) if profile.audit_root else None
    if root:
        targets = [fields["dst"]] if action in {"mv", "cp"} else [fields["path"]]
        if action == "mv":
            targets.append(fields["src"])
        if any(is_under_root(path, root) or is_under_root(root, path) for path in targets):
            raise ConfigError("the configured NAS audit archive is protected from file mutations")

    now = datetime.now(timezone.utc)
    event = {
        "schema_version": 1,
        "event_id": uuid.uuid4().hex,
        "source": "ugreen-nas-cli",
        "username": profile.username,
        "profile": profile.name,
        "action": action,
        **fields,
    }
    directory = f"{root}/{now:%Y-%m-%d}" if root else None
    receipt = {
        "event_id": event["event_id"],
        "local_log": str(profile.audit_log) if profile.audit_log else None,
        "local_status": None,
        "remote_path": None,
        "remote_status": None,
    }

    def save(status: str, **extra: Any) -> None:
        record = {**event, "ts": datetime.now(timezone.utc).isoformat(), "status": status, **extra}
        append_audit(profile.audit_log, record)
        if profile.audit_log:
            receipt["local_status"] = status
        if directory:
            if status == "started":
                client.mkdir(root)
                client.mkdir(directory)
            remote = f"{directory}/{event['event_id']}.{status}.json"
            data = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            client.put(remote, data)
            receipt.update(remote_path=remote, remote_status=status)

    try:
        save("started")
    except (WebDavError, OSError) as exc:
        raise AuditError("audit start could not be saved; file operation was not attempted", False, receipt) from exc
    try:
        yield receipt
    except (WebDavError, OSError) as exc:
        error = {"type": type(exc).__name__, "http_status": getattr(exc, "status", None)}
        try:
            save("failed", error=error)
        except (WebDavError, OSError) as audit_exc:
            raise AuditError(
                "file operation failed and its audit receipt is incomplete; inspect the target before retrying",
                None, receipt,
            ) from audit_exc
        raise
    else:
        try:
            save("succeeded")
        except (WebDavError, OSError) as exc:
            raise AuditError(
                "file operation succeeded but its audit receipt is incomplete; do not repeat the file operation",
                True, receipt,
            ) from exc
