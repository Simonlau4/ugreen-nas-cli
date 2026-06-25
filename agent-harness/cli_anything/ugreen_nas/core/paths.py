from __future__ import annotations

import posixpath


class PathAccessError(ValueError):
    pass


def normalize_remote_path(value: str) -> str:
    if value is None:
        raise PathAccessError("remote path is required")
    if "\x00" in value:
        raise PathAccessError("remote path contains a null byte")
    if "://" in value:
        raise PathAccessError("remote path must not be a URL")

    stripped = value.strip()
    if not stripped:
        raise PathAccessError("remote path is empty")

    normalized = posixpath.normpath("/" + stripped.lstrip("/"))
    if normalized == "/.":
        return "/"
    return normalized


def is_under_root(path: str, root: str) -> bool:
    path = normalize_remote_path(path)
    root = normalize_remote_path(root)
    if root == "/":
        return True
    return path == root or path.startswith(root.rstrip("/") + "/")


def assert_allowed(path: str, allowed_roots: tuple[str, ...]) -> str:
    normalized = normalize_remote_path(path)
    if not allowed_roots:
        raise PathAccessError("profile has no allowed roots")
    if not any(is_under_root(normalized, root) for root in allowed_roots):
        raise PathAccessError(
            f"remote path {normalized!r} is outside allowed roots: "
            + ", ".join(allowed_roots)
        )
    return normalized
