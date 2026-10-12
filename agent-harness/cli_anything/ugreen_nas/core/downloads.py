from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import ConfigError, Profile
from .paths import assert_allowed
from .webdav import WebDavClient, WebDavError


def download_many(
    client: WebDavClient,
    profile: Profile,
    paths: list[str],
    output: Path,
    *,
    workers: int = 4,
    resume: bool = False,
    overwrite: bool = False,
) -> list[dict]:
    if workers <= 0:
        raise ConfigError("workers must be positive")
    paths = list(dict.fromkeys(assert_allowed(path, profile.allowed_roots) for path in paths))
    root = output.expanduser().resolve()
    control = root / ".ugnas-downloads"
    state_path = control / "state.json"
    for path in paths:
        if path == "/" or path.split("/")[1] == ".ugnas-downloads":
            raise ConfigError("get-many requires files; .ugnas-downloads is reserved for checkpoints")
        target = root / path.lstrip("/")
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ConfigError(f"output path escapes the download directory: {target}")
    if control.is_symlink() or state_path.is_symlink():
        raise ConfigError("download checkpoint must not be a symlink")
    identity = {"base_url": profile.base_url, "username": profile.username}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ConfigError(f"cannot read download checkpoint: {exc}") from exc
        if not isinstance(state, dict) or state.get("identity") != identity or not isinstance(state.get("files"), dict):
            raise ConfigError("download checkpoint belongs to another NAS account or endpoint")
    else:
        state = {"identity": identity, "files": {}}
    control.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def save(path, record):
        with lock:
            state["files"][path] = record
            temporary = control / "state.tmp"
            if temporary.is_symlink():
                raise ConfigError("download checkpoint must not be a symlink")
            temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(state_path)

    def download(path):
        target = root / path.lstrip("/")
        partial = control / "partial" / path.lstrip("/")
        try:
            item = client.stat(path)
            if item.is_dir:
                raise ConfigError(f"get-many expects files, received directory: {path}")
            signature = {"etag": item.etag, "modified": item.modified, "size": item.size}
            previous = state["files"].get(path, {})
            local = None
            if target.exists():
                info = target.stat()
                local = {"size": info.st_size, "mtime_ns": info.st_mtime_ns}
                owned = resume and previous.get("local") == local
                if not overwrite and not owned:
                    raise ConfigError(f"output exists; use --overwrite: {target}")
                if owned and previous.get("complete") and previous.get("remote") == signature and (item.etag or item.modified):
                    return {"path": path, "output": str(target), "ok": True, "resumed": True, "bytes": info.st_size}
            if partial.is_symlink() or not partial.resolve().is_relative_to(control):
                raise ConfigError(f"partial download escapes the checkpoint directory: {partial}")
            partial.parent.mkdir(parents=True, exist_ok=True)
            if partial.exists() and (not resume or previous.get("remote") != signature):
                partial.write_bytes(b"")
            record = {"remote": signature, "complete": False, "local": local if resume and previous.get("local") == local else None}
            save(path, record)
            if not (partial.exists() and item.size is not None and partial.stat().st_size == item.size and (item.etag or item.modified)):
                client.download(path, partial, item)
            target.parent.mkdir(parents=True, exist_ok=True)
            partial.replace(target)
            info = target.stat()
            record.update({"complete": True, "local": {"size": info.st_size, "mtime_ns": info.st_mtime_ns}})
            save(path, record)
            return {"path": path, "output": str(target), "ok": True, "resumed": False, "bytes": info.st_size}
        except (ConfigError, WebDavError, OSError) as exc:
            if isinstance(exc, WebDavError) and exc.status == 401:
                raise
            return {"path": path, "ok": False, "status": getattr(exc, "status", None), "message": str(exc)}

    # Bound queued work as well as active requests so an authentication failure stops dispatch.
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for offset in range(0, len(paths), workers):
            results.extend(pool.map(download, paths[offset : offset + workers]))
    return results
