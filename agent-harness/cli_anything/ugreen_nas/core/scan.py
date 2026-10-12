from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .config import ConfigError, Profile
from .paths import PathAccessError, assert_allowed, is_under_root
from .webdav import WebDavClient, WebDavError, WebDavItem


def scan_tree(
    client: WebDavClient,
    profile: Profile,
    roots: list[str],
    *,
    max_depth: int | None = None,
    workers: int = 4,
    match: Callable[[WebDavItem], bool] | None = None,
    limit: int | None = None,
) -> dict:
    if workers <= 0 or (max_depth is not None and max_depth < 0):
        raise ConfigError("workers must be positive and max-depth must be 0 or greater")
    roots = list(dict.fromkeys(assert_allowed(root, profile.allowed_roots) for root in roots))
    queue = deque((root, 0) for root in roots)
    seen: set[str] = set()
    found: dict[str, WebDavItem] = {}
    errors = []
    depth_limited = set()
    scanned_dirs = 0
    limit_reached = False

    def fetch(entry):
        path, depth = entry
        try:
            return path, depth, client.propfind(path, depth="1"), None
        except WebDavError as exc:
            if exc.status == 401:
                raise
            return path, depth, [], {"path": path, "status": exc.status, "message": str(exc)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue and not limit_reached:
            batch = []
            while queue and len(batch) < workers:
                entry = queue.popleft()
                if entry[0] not in seen:
                    seen.add(entry[0])
                    batch.append(entry)
            for current, depth, items, error in pool.map(fetch, batch):
                scanned_dirs += 1
                if error:
                    errors.append(error)
                    continue
                for item in sorted(items, key=lambda item: item.path):
                    if item.path == current:
                        continue
                    try:
                        assert_allowed(item.path, profile.allowed_roots)
                        if not is_under_root(item.path, current):
                            raise PathAccessError("WebDAV item is outside the requested directory")
                    except PathAccessError as exc:
                        errors.append({"path": item.path, "status": None, "message": str(exc)})
                        continue
                    if match is None or match(item):
                        found[item.path] = item
                        if limit is not None and len(found) > limit:
                            limit_reached = True
                            break
                    if item.is_dir:
                        if max_depth is None or depth < max_depth:
                            queue.append((item.path, depth + 1))
                        else:
                            depth_limited.add(item.path)
                if limit_reached:
                    break

    items = list(found.values())
    depth_limited.difference_update(seen)
    return {
        "items": items[:limit] if limit is not None else items,
        "roots": roots,
        "scanned_dirs": scanned_dirs,
        "errors": errors,
        "depth_limited": sorted(depth_limited),
        "truncated": limit_reached,
        "complete": not (limit_reached or depth_limited or errors),
    }
