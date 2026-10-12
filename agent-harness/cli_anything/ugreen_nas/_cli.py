from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from .core.audit import append_audit
from .core.config import ConfigError, load_profile, macos_keychain_password_command, write_profile
from .core.downloads import download_many
from .core.paths import PathAccessError, assert_allowed
from .core.scan import scan_tree
from .core.webdav import WebDavClient, WebDavError, WebDavItem


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        return run(args)
    except (ConfigError, PathAccessError, WebDavError, OSError) as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }
        if isinstance(exc, WebDavError) and exc.status is not None:
            payload["status"] = exc.status
            if exc.status in {404, 405}:
                payload["hint"] = (
                    "This URL may not be a WebDAV endpoint. If you used a UGREENlink "
                    "browser URL, try Tailscale/DDNS/VPN access to the NAS WebDAV HTTPS port."
                )
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"error: {payload['message']}", file=sys.stderr)
            if "hint" in payload:
                print(f"hint: {payload['hint']}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ugnas",
        description="Agent-friendly UGREEN NAS CLI over WebDAV.",
    )
    parser.add_argument("--profile", default="default", help="Profile name in config.toml.")
    parser.add_argument("--config", type=Path, help="Config file path.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--timeout", type=float, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview a mutating command without changing the NAS.",
    )
    subparsers = parser.add_subparsers(dest="command")

    profile = subparsers.add_parser("profile-init", help="Write a local profile without storing a password.")
    profile.add_argument("--base-url", required=True)
    profile.add_argument("--username", required=True)
    profile.add_argument("--allowed-root", action="append", default=[])
    profile.add_argument("--password-command")
    profile.add_argument("--macos-keychain-service")
    profile.add_argument("--insecure", action="store_true", help="Disable TLS verification.")

    doctor = subparsers.add_parser("doctor", help="Validate config and WebDAV reachability.")
    doctor.add_argument("--path", help="Also verify access to this configured NAS path.")

    subparsers.add_parser(
        "capabilities",
        help="Describe the configured Agent command and safety surface.",
    )

    ls = subparsers.add_parser("ls", help="List a remote directory.")
    ls.add_argument("remote_path")

    stat = subparsers.add_parser("stat", help="Inspect a remote path.")
    stat.add_argument("remote_path")

    cat = subparsers.add_parser("cat", help="Print a remote file.")
    cat.add_argument("remote_path")
    cat.add_argument("--base64", action="store_true", help="Emit base64 content in human mode.")

    get = subparsers.add_parser("get", help="Download a remote file.")
    get.add_argument("remote_path")
    get.add_argument("-o", "--output", type=Path)
    get.add_argument("--overwrite", action="store_true")

    put = subparsers.add_parser("put", help="Upload a local file or stdin.")
    put.add_argument("local_path", help="Local file path, or '-' for stdin.")
    put.add_argument("remote_path")
    put.add_argument("--overwrite", action="store_true")

    edit = subparsers.add_parser("edit", help="Edit a remote text file using $EDITOR.")
    edit.add_argument("remote_path")
    edit.add_argument("--create", action="store_true")

    mkdir = subparsers.add_parser("mkdir", help="Create a remote directory.")
    mkdir.add_argument("remote_path")

    mv = subparsers.add_parser("mv", help="Move or rename a remote path.")
    mv.add_argument("src")
    mv.add_argument("dst")
    mv.add_argument("--overwrite", action="store_true")

    cp = subparsers.add_parser("cp", help="Copy a remote path.")
    cp.add_argument("src")
    cp.add_argument("dst")
    cp.add_argument("--overwrite", action="store_true")

    rm = subparsers.add_parser("rm", help="Delete a remote path.")
    rm.add_argument("remote_path")
    rm.add_argument("--yes", action="store_true", help="Required for deletion.")

    search = subparsers.add_parser("search", help="Bounded recursive file-name search.")
    search.add_argument("query")
    search.add_argument("--under", action="append", help="Root to search; defaults to configured allowed roots.")
    search.add_argument("--max-depth", type=int, default=4)
    search.add_argument("--limit", type=int, default=100)
    search.add_argument("--all", action="store_true", help="Search every depth and return all matches.")
    search.add_argument("--workers", type=int, default=4)

    recent = subparsers.add_parser("recent", help="List recently modified files under a directory.")
    recent.add_argument("--under", required=True)
    recent.add_argument("--days", type=float, default=7)
    recent.add_argument("--max-depth", type=int, default=4)
    recent.add_argument("--limit", type=int, default=100)
    recent.add_argument("--all", action="store_true", help="Scan every depth and return all recent files.")
    recent.add_argument("--workers", type=int, default=4)

    scan = subparsers.add_parser("scan", help="Build a complete recursive file and directory manifest.")
    scan.add_argument("--under", action="append", help="Root to scan; defaults to configured allowed roots.")
    scan.add_argument("--max-depth", type=int, help="Optional depth bound; defaults to every depth.")
    scan.add_argument("--workers", type=int, default=4)
    scan.add_argument("-o", "--output", type=Path)
    scan.add_argument("--overwrite", action="store_true")

    bulk = subparsers.add_parser("get-many", help="Download files or a scan manifest with resumable parallel reads.")
    bulk.add_argument("remote_paths", nargs="*")
    bulk.add_argument("--manifest", type=Path)
    bulk.add_argument("-o", "--output", type=Path, required=True)
    bulk.add_argument("--workers", type=int, default=4)
    bulk.add_argument("--resume", action="store_true")
    bulk.add_argument("--overwrite", action="store_true")

    return parser


def run(args: argparse.Namespace) -> int:
    if args.command == "profile-init":
        return cmd_profile_init(args)

    profile = load_profile(args.profile, args.config, args.timeout)
    client = WebDavClient(profile)

    mutating_commands = {"put", "edit", "mkdir", "mv", "cp", "rm"}
    if args.dry_run:
        if args.command not in mutating_commands:
            raise ConfigError("--dry-run is only supported for put, edit, mkdir, mv, cp, and rm")
        return cmd_dry_run(args, profile)

    if args.command == "capabilities":
        return cmd_capabilities(args, profile)
    if args.command == "doctor":
        return cmd_doctor(args, profile, client)
    if args.command == "ls":
        path = assert_allowed(args.remote_path, profile.allowed_roots)
        items = client.propfind(path, depth="1")
        if path != "/":
            items = [item for item in items if item.path != path]
        return emit(args, {"ok": True, "items": [item_to_json(item) for item in items]}, _format_items(items))
    if args.command == "stat":
        path = assert_allowed(args.remote_path, profile.allowed_roots)
        item = client.stat(path)
        return emit(args, {"ok": True, "item": item_to_json(item)}, _format_item(item))
    if args.command == "cat":
        path = assert_allowed(args.remote_path, profile.allowed_roots)
        data = client.get(path)
        if args.json:
            return emit(
                args,
                {
                    "ok": True,
                    "path": path,
                    "encoding": "utf-8",
                    "content": data.decode("utf-8", errors="replace"),
                },
                "",
            )
        if args.base64:
            print(base64.b64encode(data).decode("ascii"))
        else:
            sys.stdout.write(data.decode("utf-8", errors="replace"))
        return 0
    if args.command == "get":
        return cmd_get(args, profile, client)
    if args.command == "put":
        return cmd_put(args, profile, client)
    if args.command == "edit":
        return cmd_edit(args, profile, client)
    if args.command == "mkdir":
        path = assert_allowed(args.remote_path, profile.allowed_roots)
        client.mkdir(path)
        audit(profile, "mkdir", path=path)
        return emit(args, {"ok": True, "path": path}, f"created {path}")
    if args.command == "mv":
        src = assert_allowed(args.src, profile.allowed_roots)
        dst = assert_allowed(args.dst, profile.allowed_roots)
        client.move(src, dst, overwrite=args.overwrite)
        audit(profile, "mv", src=src, dst=dst, overwrite=args.overwrite)
        return emit(args, {"ok": True, "src": src, "dst": dst}, f"moved {src} -> {dst}")
    if args.command == "cp":
        src = assert_allowed(args.src, profile.allowed_roots)
        dst = assert_allowed(args.dst, profile.allowed_roots)
        client.copy(src, dst, overwrite=args.overwrite)
        audit(profile, "cp", src=src, dst=dst, overwrite=args.overwrite)
        return emit(args, {"ok": True, "src": src, "dst": dst}, f"copied {src} -> {dst}")
    if args.command == "rm":
        if not args.yes:
            raise ConfigError("rm requires --yes")
        path = assert_allowed(args.remote_path, profile.allowed_roots)
        client.delete(path)
        audit(profile, "rm", path=path)
        return emit(args, {"ok": True, "path": path}, f"deleted {path}")
    if args.command == "search":
        return cmd_search(args, profile, client)
    if args.command == "recent":
        return cmd_recent(args, profile, client)
    if args.command == "scan":
        return cmd_scan(args, profile, client)
    if args.command == "get-many":
        return cmd_get_many(args, profile, client)

    raise ConfigError(f"unknown command: {args.command}")


def cmd_profile_init(args: argparse.Namespace) -> int:
    password_command = args.password_command
    if args.macos_keychain_service:
        password_command = macos_keychain_password_command(
            args.macos_keychain_service,
            args.username,
        )
    path = write_profile(
        name=args.profile,
        base_url=args.base_url,
        username=args.username,
        allowed_roots=args.allowed_root or ["/"],
        password_command=password_command,
        verify_tls=not args.insecure,
        config_path=args.config,
    )
    payload = {"ok": True, "config": str(path), "profile": args.profile}
    return emit(args, payload, f"wrote profile {args.profile} to {path}")


def cmd_dry_run(args: argparse.Namespace, profile) -> int:
    payload: dict[str, Any] = {
        "ok": True,
        "dry_run": True,
        "action": args.command,
    }
    if args.command == "put":
        remote = assert_allowed(args.remote_path, profile.allowed_roots)
        payload.update(
            {
                "local_path": args.local_path,
                "remote_path": remote,
                "overwrite": args.overwrite,
                "bytes": None if args.local_path == "-" else Path(args.local_path).stat().st_size,
            }
        )
    elif args.command == "edit":
        payload.update(
            {
                "remote_path": assert_allowed(args.remote_path, profile.allowed_roots),
                "create": args.create,
            }
        )
    elif args.command == "mkdir":
        payload["remote_path"] = assert_allowed(args.remote_path, profile.allowed_roots)
    elif args.command in {"mv", "cp"}:
        payload.update(
            {
                "src": assert_allowed(args.src, profile.allowed_roots),
                "dst": assert_allowed(args.dst, profile.allowed_roots),
                "overwrite": args.overwrite,
            }
        )
    elif args.command == "rm":
        payload["remote_path"] = assert_allowed(args.remote_path, profile.allowed_roots)
    return emit(args, payload, f"dry-run: {args.command}")


def cmd_capabilities(args: argparse.Namespace, profile) -> int:
    payload = {
        "ok": True,
        "profile": profile.name,
        "allowed_roots": profile.allowed_roots,
        "read_commands": ["doctor", "capabilities", "ls", "stat", "cat", "get", "search", "recent", "scan", "get-many"],
        "write_commands": ["put", "edit", "mkdir", "mv", "cp"],
        "dangerous_commands": ["rm"],
        "bulk_read": {"default_workers": 4, "partial_exit_code": 3, "resume": "get-many --resume"},
        "safety": {
            "global_flags_before_command": True,
            "preview_writes_with": "--dry-run",
            "delete_requires": "--yes",
            "overwrite_requires": "--overwrite",
        },
    }
    return emit(args, payload, json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_doctor(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    checked_path = "/"
    if args.path:
        checked_path = assert_allowed(args.path, profile.allowed_roots)
    try:
        items = client.propfind(checked_path, depth="0")
    except WebDavError as exc:
        hint = None
        if exc.status in {301, 302, 303, 307, 308, 404, 405}:
            hint = "Configured URL does not look like a raw WebDAV endpoint."
        elif exc.status == 401:
            hint = "Authentication failed; check the NAS account credentials."
        payload = {
            "ok": False,
            "profile": profile.name,
            "base_url": profile.base_url,
            "checked_path": checked_path,
            "status": exc.status,
            "message": str(exc),
            "hint": hint,
        }
        return emit(args, payload, f"doctor failed: {payload['message']}")
    payload = {
        "ok": True,
        "profile": profile.name,
        "base_url": profile.base_url,
        "username": profile.username,
        "allowed_roots": profile.allowed_roots,
        "checked_path": checked_path,
        "path_items": [item_to_json(item) for item in items],
    }
    lines = [
        "profile ok",
        f"base_url: {profile.base_url}",
        f"username: {profile.username}",
        f"checked_path: {checked_path}",
        "webdav: reachable",
    ]
    return emit(args, payload, "\n".join(lines))


def cmd_get(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    remote = assert_allowed(args.remote_path, profile.allowed_roots)
    output = args.output
    if output is None:
        output = Path(remote.rstrip("/").split("/")[-1] or "download")
    if output.exists() and not args.overwrite:
        raise ConfigError(f"output exists; use --overwrite: {output}")
    data = client.get(remote)
    output.write_bytes(data)
    payload = {"ok": True, "remote_path": remote, "output": str(output), "bytes": len(data)}
    return emit(args, payload, f"downloaded {remote} -> {output} ({len(data)} bytes)")


def cmd_put(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    remote = assert_allowed(args.remote_path, profile.allowed_roots)
    if args.local_path == "-":
        data = sys.stdin.buffer.read()
    else:
        data = Path(args.local_path).read_bytes()
    client.put(remote, data, overwrite=args.overwrite)
    audit(profile, "put", path=remote, bytes=len(data), overwrite=args.overwrite)
    payload = {"ok": True, "remote_path": remote, "bytes": len(data), "overwrite": args.overwrite}
    return emit(args, payload, f"uploaded {len(data)} bytes to {remote}")


def cmd_edit(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    remote = assert_allowed(args.remote_path, profile.allowed_roots)
    etag = None
    try:
        item = client.stat(remote)
        etag = item.etag
        original = client.get(remote)
    except WebDavError as exc:
        if exc.status != 404 or not args.create:
            raise
        original = b""

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise ConfigError("edit requires VISUAL or EDITOR")
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(original)
    try:
        subprocess.run([editor, str(temp_path)], check=True)
        updated = temp_path.read_bytes()
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

    if updated == original:
        return emit(args, {"ok": True, "changed": False, "remote_path": remote}, "unchanged")
    client.put(remote, updated, overwrite=args.create, etag=etag)
    audit(profile, "edit", path=remote, bytes=len(updated), had_etag=bool(etag))
    return emit(args, {"ok": True, "changed": True, "remote_path": remote}, f"saved {remote}")


def cmd_search(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    if not args.query.strip():
        raise ConfigError("search query must not be empty")
    if args.max_depth < 0:
        raise ConfigError("search --max-depth must be 0 or greater")
    if args.limit <= 0:
        raise ConfigError("search --limit must be greater than 0")

    query = args.query.strip().lower()
    result = scan_tree(
        client, profile, args.under or list(profile.allowed_roots),
        max_depth=None if args.all else args.max_depth,
        workers=args.workers,
        match=lambda item: query in item.path.rstrip("/").split("/")[-1].lower(),
        limit=None if args.all else args.limit,
    )
    matches = result.pop("items")
    payload = {"ok": True, **result, "matches": [item_to_json(item) for item in matches]}
    return emit_read(args, payload, _format_items(matches))


def cmd_recent(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    if args.days <= 0:
        raise ConfigError("recent --days must be greater than 0")
    if args.max_depth < 0:
        raise ConfigError("recent --max-depth must be 0 or greater")
    if args.limit <= 0:
        raise ConfigError("recent --limit must be greater than 0")

    start = assert_allowed(args.under, profile.allowed_roots)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    result = scan_tree(client, profile, [start], max_depth=None if args.all else args.max_depth, workers=args.workers)
    files = [item for item in result.pop("items") if not item.is_dir]
    matches = [(modified, item) for item in files if (modified := _parse_modified(item.modified)) is not None and modified >= cutoff]
    matches.sort(key=lambda pair: (pair[0], pair[1].path), reverse=True)
    recent_items = [item for _, item in (matches if args.all else matches[: args.limit])]
    truncated = len(recent_items) < len(matches)
    payload = {
        "ok": True,
        **result,
        "under": start,
        "cutoff": cutoff.isoformat(),
        "scanned_files": len(files),
        "matched_files": len(matches),
        "truncated": truncated,
        "complete": result["complete"] and not truncated,
        "items": [item_to_json(item) for item in recent_items],
    }
    return emit_read(args, payload, _format_items(recent_items))


def cmd_scan(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    if args.output and args.output.exists() and not args.overwrite:
        raise ConfigError(f"output exists; use --overwrite: {args.output}")
    result = scan_tree(client, profile, args.under or list(profile.allowed_roots), max_depth=args.max_depth, workers=args.workers)
    items = result.pop("items")
    payload = {
        "ok": True, **result,
        "source": {"base_url": profile.base_url, "username": profile.username},
        "items": [item_to_json(item) for item in items],
    }
    if args.output:
        with args.output.open("x" if not args.overwrite else "w", encoding="utf-8") as handle:
            args.output.chmod(0o600)
            json.dump(payload, handle, ensure_ascii=False)
    return emit_read(args, payload, _format_items(items))


def cmd_get_many(args: argparse.Namespace, profile, client: WebDavClient) -> int:
    if bool(args.manifest) == bool(args.remote_paths):
        raise ConfigError("provide file paths or --manifest, but not both")
    source_complete = True
    source_errors = []
    paths = args.remote_paths
    if args.manifest:
        try:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            paths = [item["path"] for item in manifest["items"] if item["type"] == "file"]
            if not all(isinstance(path, str) for path in paths):
                raise ValueError("manifest paths must be strings")
            source_complete = manifest["complete"] is True
            source_errors = manifest.get("errors", [])
        except (ValueError, KeyError, TypeError) as exc:
            raise ConfigError(f"invalid scan manifest: {exc}") from exc
    results = download_many(client, profile, paths, args.output, workers=args.workers, resume=args.resume, overwrite=args.overwrite)
    complete = source_complete and all(item["ok"] for item in results)
    payload = {"ok": True, "complete": complete, "source_complete": source_complete, "source_errors": source_errors, "items": results}
    return emit_read(args, payload, json.dumps(payload, ensure_ascii=False, indent=2))


def emit_read(args: argparse.Namespace, payload: dict, human: str) -> int:
    code = emit(args, payload, human)
    if not payload["complete"]:
        if not args.json:
            print("Incomplete result: inspect errors, depth_limited and truncated using --json.", file=sys.stderr)
        return 3
    return code


def _parse_modified(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def audit(profile, action: str, **fields: Any) -> None:
    append_audit(
        profile.audit_log,
        {
            "username": profile.username,
            "profile": profile.name,
            "action": action,
            **fields,
        },
    )


def emit(args: argparse.Namespace, payload: dict[str, Any], human: str) -> int:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        if human:
            print(human)
    return 0 if payload.get("ok", True) else 2


def item_to_json(item: WebDavItem) -> dict[str, Any]:
    return {
        "path": item.path,
        "type": "dir" if item.is_dir else "file",
        "size": item.size,
        "modified": item.modified,
        "etag": item.etag,
    }


def _format_item(item: WebDavItem) -> str:
    suffix = "/" if item.is_dir else ""
    size = "-" if item.size is None else str(item.size)
    return f"{item.path}{suffix}\t{size}\t{item.modified or '-'}"


def _format_items(items: list[WebDavItem]) -> str:
    if not items:
        return ""
    return "\n".join(_format_item(item) for item in items)
