from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable


DEFAULT_STATE_PATH = Path("~/.local/state/nas-kb/state.sqlite").expanduser()
DEFAULT_EVEROS_URL = "http://127.0.0.1:8765"
DEFAULT_APP_ID = "nas-kb"
DEFAULT_PROJECT_ID = "simon-nas"
DEFAULT_EXTENSIONS = (".md", ".pdf", ".docx")
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_GATEWAY_PORT = 8787
DEFAULT_GATEWAY_TOKEN_ENV = "NAS_KB_API_TOKEN"
DEFAULT_GATEWAY_URL_ENV = "NAS_KB_API_URL"
MAX_GATEWAY_BODY_BYTES = 64 * 1024
MIN_GATEWAY_TOKEN_LENGTH = 32


class NasKbError(RuntimeError):
    pass


class HttpError(NasKbError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class RemoteItem:
    path: str
    item_type: str
    size: int | None
    modified: str | None
    etag: str | None

    @property
    def fingerprint(self) -> str:
        return "|".join(
            [self.etag or "", self.modified or "", str(self.size if self.size is not None else "")]
        )


class NasClient:
    def __init__(self, executable: str, profile: str):
        self.executable = executable
        self.profile = profile

    def _run(self, args: list[str]) -> dict[str, Any]:
        command = [self.executable, "--profile", self.profile, "--json", *args]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            detail = result.stderr.strip() or result.stdout.strip() or "no output"
            raise NasKbError(f"nas-cli returned invalid JSON: {detail}") from exc
        if result.returncode != 0 or not payload.get("ok", False):
            raise NasKbError(payload.get("message") or f"nas-cli failed: {' '.join(args)}")
        return payload

    def doctor(self, path: str | None = None) -> dict[str, Any]:
        args = ["doctor"]
        if path:
            args.extend(["--path", path])
        return self._run(args)

    def list(self, remote_path: str) -> list[RemoteItem]:
        payload = self._run(["ls", remote_path])
        return [
            RemoteItem(
                path=item["path"],
                item_type=item["type"],
                size=item.get("size"),
                modified=item.get("modified"),
                etag=item.get("etag"),
            )
            for item in payload.get("items", [])
        ]

    def get(self, remote_path: str, output: Path) -> None:
        self._run(["get", remote_path, "-o", str(output)])


class EverOSClient:
    def __init__(self, base_url: str, app_id: str, project_id: str):
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.project_id = project_id

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 120,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers or {},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw)
                message = payload.get("error", {}).get("message") or str(payload)
            except json.JSONDecodeError:
                message = raw.decode("utf-8", errors="replace") or str(exc)
            raise HttpError(message, exc.code) from exc
        except urllib.error.URLError as exc:
            raise HttpError(f"EverOS unavailable: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HttpError("EverOS returned invalid JSON") from exc

    def health(self) -> dict[str, Any]:
        return self._request("/health", timeout=5)

    def document_count(self) -> int:
        query = urllib.parse.urlencode(
            {
                "app_id": self.app_id,
                "project_id": self.project_id,
                "page": 1,
                "page_size": 1,
            }
        )
        payload = self._request(f"/api/v1/knowledge/documents?{query}")
        return int(payload.get("data", {}).get("total", 0))

    def upload(
        self,
        file_path: Path,
        *,
        title: str,
        remote_path: str,
        doc_id: str | None = None,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        fields = {
            "title": title,
            "source_type": f"nas:{remote_path}",
            "app_id": self.app_id,
            "project_id": self.project_id,
        }
        if category_id:
            fields["category_id"] = category_id
        body, content_type = build_multipart(fields, "file", file_path)
        endpoint = "/api/v1/knowledge/documents"
        method = "POST"
        if doc_id:
            endpoint = f"{endpoint}/{urllib.parse.quote(doc_id)}"
            method = "PUT"
        payload = self._request(
            endpoint,
            method=method,
            body=body,
            headers={"Content-Type": content_type},
            timeout=300,
        )
        return payload.get("data", {})

    def search(
        self,
        query: str,
        *,
        method: str,
        top_k: int,
        include_content: bool,
    ) -> dict[str, Any]:
        body = json.dumps(
            {
                "query": query,
                "method": method,
                "top_k": top_k,
                "include_content": include_content,
                "app_id": self.app_id,
                "project_id": self.project_id,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        payload = self._request(
            "/api/v1/knowledge/search",
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        return payload.get("data", {})


class StateStore:
    def __init__(self, path: Path, app_id: str, project_id: str):
        self.path = path
        self.app_id = app_id
        self.project_id = project_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                app_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                remote_path TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                etag TEXT,
                modified TEXT,
                size INTEGER,
                doc_id TEXT,
                status TEXT NOT NULL,
                last_error TEXT,
                indexed_at TEXT,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (app_id, project_id, remote_path)
            )
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def get(self, remote_path: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM documents
            WHERE app_id = ? AND project_id = ? AND remote_path = ?
            """,
            (self.app_id, self.project_id, remote_path),
        ).fetchone()
        return dict(row) if row else None

    def save(
        self,
        item: RemoteItem,
        *,
        status: str,
        doc_id: str | None,
        error: str | None = None,
    ) -> None:
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO documents (
                app_id, project_id, remote_path, fingerprint, etag, modified,
                size, doc_id, status, last_error, indexed_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (app_id, project_id, remote_path) DO UPDATE SET
                fingerprint = excluded.fingerprint,
                etag = excluded.etag,
                modified = excluded.modified,
                size = excluded.size,
                doc_id = COALESCE(excluded.doc_id, documents.doc_id),
                status = excluded.status,
                last_error = excluded.last_error,
                indexed_at = CASE
                    WHEN excluded.status = 'indexed' THEN excluded.indexed_at
                    ELSE documents.indexed_at
                END,
                last_seen_at = excluded.last_seen_at
            """,
            (
                self.app_id,
                self.project_id,
                item.path,
                item.fingerprint,
                item.etag,
                item.modified,
                item.size,
                doc_id,
                status,
                error,
                now if status == "indexed" else None,
                now,
            ),
        )
        self.connection.commit()

    def list(self, limit: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM documents
            WHERE app_id = ? AND project_id = ?
            ORDER BY last_seen_at DESC, remote_path ASC
            LIMIT ?
            """,
            (self.app_id, self.project_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        rows = self.connection.execute(
            """
            SELECT status, COUNT(*) AS count FROM documents
            WHERE app_id = ? AND project_id = ?
            GROUP BY status
            """,
            (self.app_id, self.project_id),
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}

    def by_doc_ids(self, doc_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        values = [value for value in doc_ids if value]
        if not values:
            return {}
        placeholders = ",".join("?" for _ in values)
        rows = self.connection.execute(
            f"""
            SELECT * FROM documents
            WHERE app_id = ? AND project_id = ? AND doc_id IN ({placeholders})
            """,
            (self.app_id, self.project_id, *values),
        ).fetchall()
        return {row["doc_id"]: dict(row) for row in rows}

    def by_doc_id(self, doc_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM documents
            WHERE app_id = ? AND project_id = ? AND doc_id = ?
            """,
            (self.app_id, self.project_id, doc_id),
        ).fetchone()
        return dict(row) if row else None


def discover_documents(
    nas: NasClient,
    under: str,
    *,
    max_depth: int,
    limit: int,
    extensions: set[str],
) -> tuple[list[RemoteItem], bool]:
    if max_depth < 0:
        raise NasKbError("--max-depth must be 0 or greater")
    if limit <= 0:
        raise NasKbError("--limit must be greater than 0")
    queue: list[tuple[str, int]] = [(under, 0)]
    seen: set[str] = set()
    documents: list[RemoteItem] = []
    while queue:
        current, depth = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        for item in nas.list(current):
            if item.path == current:
                continue
            if item.item_type == "dir":
                if depth < max_depth:
                    queue.append((item.path, depth + 1))
                continue
            if Path(item.path).suffix.lower() not in extensions:
                continue
            documents.append(item)
            if len(documents) >= limit:
                return documents, True
    return documents, False


def index_documents(
    nas: NasClient,
    everos: EverOSClient,
    state: StateStore,
    *,
    under: str,
    max_depth: int,
    limit: int,
    extensions: set[str],
    max_bytes: int,
    category_id: str | None,
    apply: bool,
) -> dict[str, Any]:
    if max_bytes <= 0:
        raise NasKbError("--max-bytes must be greater than 0")
    if not extensions:
        raise NasKbError("at least one file extension is required")
    documents, truncated = discover_documents(
        nas,
        under,
        max_depth=max_depth,
        limit=limit,
        extensions=extensions,
    )
    results: list[dict[str, Any]] = []
    counts = {"planned": 0, "indexed": 0, "updated": 0, "skipped": 0, "failed": 0}
    for item in documents:
        previous = state.get(item.path)
        if previous and previous["fingerprint"] == item.fingerprint and previous["status"] == "indexed":
            counts["skipped"] += 1
            results.append({"remote_path": item.path, "status": "skipped", "doc_id": previous["doc_id"]})
            continue
        if previous and previous["fingerprint"] == item.fingerprint and previous["status"] == "indexing":
            message = "previous indexing was interrupted; inspect EverOS before retrying"
            counts["failed"] += 1
            results.append({"remote_path": item.path, "status": "error", "error": message})
            continue
        if item.size is not None and item.size > max_bytes:
            message = f"file exceeds max bytes ({item.size} > {max_bytes})"
            counts["failed"] += 1
            state.save(item, status="error", doc_id=previous.get("doc_id") if previous else None, error=message)
            results.append({"remote_path": item.path, "status": "error", "error": message})
            continue
        if not apply:
            counts["planned"] += 1
            results.append(
                {
                    "remote_path": item.path,
                    "status": "planned",
                    "action": "update" if previous and previous.get("doc_id") else "create",
                }
            )
            continue
        state.save(
            item,
            status="indexing",
            doc_id=previous.get("doc_id") if previous else None,
        )
        try:
            suffix = Path(item.path).suffix.lower()
            with tempfile.TemporaryDirectory(prefix="nas-kb-") as temp_dir:
                local_path = Path(temp_dir) / f"source{suffix}"
                nas.get(item.path, local_path)
                existing_doc_id = previous.get("doc_id") if previous else None
                try:
                    uploaded = everos.upload(
                        local_path,
                        title=Path(item.path).stem,
                        remote_path=item.path,
                        doc_id=existing_doc_id,
                        category_id=category_id,
                    )
                except HttpError as exc:
                    if exc.status != 404 or not existing_doc_id:
                        raise
                    uploaded = everos.upload(
                        local_path,
                        title=Path(item.path).stem,
                        remote_path=item.path,
                        category_id=category_id,
                    )
            doc_id = uploaded.get("doc_id")
            if not doc_id:
                raise NasKbError("EverOS upload did not return doc_id")
            status = "updated" if previous and previous.get("doc_id") else "indexed"
            counts[status] += 1
            state.save(item, status="indexed", doc_id=doc_id)
            results.append({"remote_path": item.path, "status": status, "doc_id": doc_id})
        except Exception as exc:  # Continue indexing other documents and record the failure.
            counts["failed"] += 1
            message = str(exc)
            state.save(item, status="error", doc_id=previous.get("doc_id") if previous else None, error=message)
            results.append({"remote_path": item.path, "status": "error", "error": message})
    return {
        "ok": counts["failed"] == 0,
        "apply": apply,
        "under": under,
        "discovered": len(documents),
        "truncated": truncated,
        "counts": counts,
        "items": results,
    }


def load_sync_roots(path: Path) -> list[dict[str, Any]]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise NasKbError(f"cannot read sync config {path}: {exc}") from exc
    roots = payload.get("roots")
    if not isinstance(roots, list) or not roots:
        raise NasKbError("sync config must contain at least one [[roots]] entry")
    normalized: list[dict[str, Any]] = []
    for position, root in enumerate(roots, start=1):
        if not isinstance(root, dict):
            raise NasKbError(f"sync root {position} must be a table")
        remote_path = root.get("path")
        if not isinstance(remote_path, str) or not remote_path.startswith("/"):
            raise NasKbError(f"sync root {position} path must be an absolute NAS path")
        extensions = root.get("extensions", list(DEFAULT_EXTENSIONS))
        if not isinstance(extensions, list) or not extensions:
            raise NasKbError(f"sync root {position} extensions must be a non-empty list")
        normalized_extensions = {
            value.lower() if value.startswith(".") else f".{value.lower()}"
            for value in extensions
            if isinstance(value, str) and value
        }
        if len(normalized_extensions) != len(extensions):
            raise NasKbError(f"sync root {position} contains an invalid extension")
        try:
            max_depth = int(root.get("max_depth", 4))
            limit = int(root.get("limit", 100))
            max_bytes = int(root.get("max_bytes", DEFAULT_MAX_BYTES))
        except (TypeError, ValueError) as exc:
            raise NasKbError(f"sync root {position} contains a non-integer limit") from exc
        if max_depth < 0 or limit <= 0 or max_bytes <= 0:
            raise NasKbError(
                f"sync root {position} requires max_depth >= 0, limit > 0, and max_bytes > 0"
            )
        category_id = root.get("category_id")
        if category_id is not None and not isinstance(category_id, str):
            raise NasKbError(f"sync root {position} category_id must be a string")
        normalized.append(
            {
                "path": remote_path,
                "max_depth": max_depth,
                "limit": limit,
                "extensions": normalized_extensions,
                "max_bytes": max_bytes,
                "category_id": category_id,
            }
        )
    return normalized


def sync_documents(
    nas: NasClient,
    everos: EverOSClient,
    state: StateStore,
    roots: list[dict[str, Any]],
    *,
    apply: bool,
) -> dict[str, Any]:
    totals = {"planned": 0, "indexed": 0, "updated": 0, "skipped": 0, "failed": 0}
    results = []
    for root in roots:
        result = index_documents(
            nas,
            everos,
            state,
            under=root["path"],
            max_depth=root["max_depth"],
            limit=root["limit"],
            extensions=root["extensions"],
            max_bytes=root["max_bytes"],
            category_id=root["category_id"],
            apply=apply,
        )
        for name, count in result["counts"].items():
            totals[name] += count
        results.append(result)
    return {
        "ok": totals["failed"] == 0,
        "apply": apply,
        "root_count": len(roots),
        "counts": totals,
        "roots": results,
    }


def search_documents(
    everos: EverOSClient,
    state: StateStore,
    query: str,
    *,
    method: str,
    top_k: int,
    include_content: bool,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise NasKbError("query must be a non-empty string")
    if method not in {"keyword", "vector", "hybrid"}:
        raise NasKbError("method must be keyword, vector, or hybrid")
    if not 1 <= top_k <= 50:
        raise NasKbError("top-k must be between 1 and 50")
    payload = everos.search(
        query,
        method=method,
        top_k=top_k,
        include_content=include_content,
    )
    hits = payload.get("hits", [])
    doc_ids = [hit.get("document", {}).get("doc_id") for hit in hits]
    sources = state.by_doc_ids(doc_ids)
    for hit in hits:
        doc_id = hit.get("document", {}).get("doc_id")
        source = sources.get(doc_id, {})
        hit["remote_path"] = source.get("remote_path")
        hit["source_status"] = source.get("status")
    return {"ok": True, **payload}


class GatewayServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        nas: NasClient,
        everos: EverOSClient,
        state_path: Path,
        app_id: str,
        project_id: str,
        token: str,
    ):
        validate_gateway_token(token)
        super().__init__(server_address, GatewayHandler)
        self.nas = nas
        self.everos = everos
        self.state_path = state_path
        self.app_id = app_id
        self.project_id = project_id
        self.token = token


class GatewayHandler(BaseHTTPRequestHandler):
    server: GatewayServer

    def do_GET(self) -> None:
        if self.path == "/health":
            try:
                healthy = self.server.everos.health().get("status") == "ok"
            except HttpError:
                healthy = False
            self._send_json(
                200 if healthy else 503,
                {"ok": healthy, "service": "nas-kb-gateway"},
            )
            return
        if self.path.startswith("/v1/source/"):
            if not self._authorized():
                return
            doc_id = urllib.parse.unquote(self.path.removeprefix("/v1/source/"))
            self._send_source(doc_id)
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/v1/search":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        if not self._authorized():
            return
        try:
            payload = self._read_json()
            query = payload.get("query")
            method = payload.get("method", "hybrid")
            top_k = payload.get("top_k", 10)
            include_content = payload.get("include_content", False)
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query must be a non-empty string")
            if method not in {"keyword", "vector", "hybrid"}:
                raise ValueError("method must be keyword, vector, or hybrid")
            if not isinstance(top_k, int) or not 1 <= top_k <= 50:
                raise ValueError("top_k must be an integer between 1 and 50")
            if not isinstance(include_content, bool):
                raise ValueError("include_content must be a boolean")
            state = StateStore(
                self.server.state_path,
                self.server.app_id,
                self.server.project_id,
            )
            try:
                result = search_documents(
                    self.server.everos,
                    state,
                    query.strip(),
                    method=method,
                    top_k=top_k,
                    include_content=include_content,
                )
            finally:
                state.close()
            self._send_json(200, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "error": "invalid_request", "message": str(exc)})
        except (NasKbError, HttpError, sqlite3.Error) as exc:
            self._send_json(502, {"ok": False, "error": "gateway_error", "message": str(exc)})

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.token}"
        supplied = self.headers.get("Authorization", "")
        if hmac.compare_digest(supplied, expected):
            return True
        self._send_json(401, {"ok": False, "error": "unauthorized"})
        return False

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        length = int(raw_length)
        if length <= 0 or length > MAX_GATEWAY_BODY_BYTES:
            raise ValueError(f"request body must be between 1 and {MAX_GATEWAY_BODY_BYTES} bytes")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _send_source(self, doc_id: str) -> None:
        if not doc_id:
            self._send_json(400, {"ok": False, "error": "invalid_doc_id"})
            return
        state = StateStore(
            self.server.state_path,
            self.server.app_id,
            self.server.project_id,
        )
        try:
            source = state.by_doc_id(doc_id)
        finally:
            state.close()
        if not source:
            self._send_json(404, {"ok": False, "error": "unknown_doc_id"})
            return
        remote_path = source["remote_path"]
        suffix = Path(remote_path).suffix
        try:
            with tempfile.TemporaryDirectory(prefix="nas-kb-gateway-") as temp_dir:
                local_path = Path(temp_dir) / f"source{suffix}"
                self.server.nas.get(remote_path, local_path)
                data = local_path.read_bytes()
        except (NasKbError, OSError) as exc:
            self._send_json(502, {"ok": False, "error": "source_unavailable", "message": str(exc)})
            return
        filename = Path(remote_path).name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}",
        )
        self.send_header("X-NAS-Remote-Path", urllib.parse.quote(remote_path, safe="/"))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def gateway_search(
    api_url: str,
    token: str,
    query: str,
    *,
    method: str,
    top_k: int,
    include_content: bool,
) -> dict[str, Any]:
    body = json.dumps(
        {
            "query": query,
            "method": method,
            "top_k": top_k,
            "include_content": include_content,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/v1/search",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    return gateway_request_json(request)


def gateway_get_source(api_url: str, token: str, doc_id: str, output: Path) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/v1/source/{urllib.parse.quote(doc_id)}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
            remote_path = urllib.parse.unquote(response.headers.get("X-NAS-Remote-Path", ""))
    except urllib.error.HTTPError as exc:
        raise gateway_http_error(exc) from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"NAS knowledge gateway unavailable: {exc.reason}") from exc
    output.write_bytes(data)
    return {
        "ok": True,
        "doc_id": doc_id,
        "remote_path": remote_path or None,
        "output": str(output),
        "bytes": len(data),
    }


def gateway_request_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise gateway_http_error(exc) from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"NAS knowledge gateway unavailable: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HttpError("NAS knowledge gateway returned invalid JSON") from exc


def gateway_http_error(exc: urllib.error.HTTPError) -> HttpError:
    raw = exc.read()
    try:
        payload = json.loads(raw)
        message = payload.get("message") or payload.get("error") or str(payload)
    except json.JSONDecodeError:
        message = raw.decode("utf-8", errors="replace") or str(exc)
    return HttpError(f"NAS knowledge gateway error: {message}", exc.code)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise NasKbError(f"required environment variable is not set: {name}")
    return value


def validate_gateway_token(token: str) -> None:
    if len(token) < MIN_GATEWAY_TOKEN_LENGTH:
        raise NasKbError(
            f"gateway token must contain at least {MIN_GATEWAY_TOKEN_LENGTH} characters"
        )


def build_multipart(
    fields: dict[str, str],
    file_field: str,
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = f"----nas-kb-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    filename = file_path.name.replace('"', "_")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    chunks.append(file_path.read_bytes())
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Index NAS documents through EverOS knowledge search.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--profile", default="default", help="nas-cli profile name.")
    parser.add_argument("--nas-cli", default="nas-cli", help="nas-cli executable.")
    parser.add_argument("--everos-url", default=DEFAULT_EVEROS_URL)
    parser.add_argument("--app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check NAS, EverOS, and local state.")
    doctor.add_argument("--path", help="Verify access to this configured NAS path.")

    index = subparsers.add_parser("index", help="Preview or apply incremental NAS indexing.")
    index.add_argument("--under", required=True, help="Remote NAS directory to scan.")
    index.add_argument("--max-depth", type=int, default=4)
    index.add_argument("--limit", type=int, default=100)
    index.add_argument("--extension", action="append", default=[])
    index.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    index.add_argument("--category-id")
    index.add_argument("--apply", action="store_true", help="Download and index changed files.")

    status = subparsers.add_parser("status", help="Show local NAS-to-EverOS index state.")
    status.add_argument("--limit", type=int, default=100)

    sync = subparsers.add_parser("sync", help="Preview or apply configured knowledge roots.")
    sync.add_argument("--config", type=Path, required=True)
    sync.add_argument("--apply", action="store_true")

    search = subparsers.add_parser("search", help="Search indexed NAS knowledge.")
    search.add_argument("query")
    search.add_argument("--method", choices=("keyword", "vector", "hybrid"), default="hybrid")
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--include-content", action="store_true")

    get_source = subparsers.add_parser("get-source", help="Download the NAS original for a result doc_id.")
    get_source.add_argument("doc_id")
    get_source.add_argument("-o", "--output", type=Path)
    get_source.add_argument("--overwrite", action="store_true")

    serve = subparsers.add_parser("serve", help="Serve authenticated team knowledge search.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT)
    serve.add_argument("--token-env", default=DEFAULT_GATEWAY_TOKEN_ENV)

    remote_search = subparsers.add_parser(
        "remote-search",
        help="Search a shared NAS knowledge gateway.",
    )
    remote_search.add_argument("query")
    remote_search.add_argument("--api-url")
    remote_search.add_argument("--token-env", default=DEFAULT_GATEWAY_TOKEN_ENV)
    remote_search.add_argument(
        "--method",
        choices=("keyword", "vector", "hybrid"),
        default="hybrid",
    )
    remote_search.add_argument("--top-k", type=int, default=10)
    remote_search.add_argument("--include-content", action="store_true")

    remote_source = subparsers.add_parser(
        "remote-get-source",
        help="Download an original NAS file through the shared gateway.",
    )
    remote_source.add_argument("doc_id")
    remote_source.add_argument("-o", "--output", type=Path)
    remote_source.add_argument("--overwrite", action="store_true")
    remote_source.add_argument("--api-url")
    remote_source.add_argument("--token-env", default=DEFAULT_GATEWAY_TOKEN_ENV)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "remote-search":
            api_url = args.api_url or require_env(DEFAULT_GATEWAY_URL_ENV)
            payload = gateway_search(
                api_url,
                require_env(args.token_env),
                args.query,
                method=args.method,
                top_k=args.top_k,
                include_content=args.include_content,
            )
            emit(args.json, payload)
            return 0 if payload.get("ok", True) else 2
        if args.command == "remote-get-source":
            api_url = args.api_url or require_env(DEFAULT_GATEWAY_URL_ENV)
            output = args.output or Path(args.doc_id)
            output = Path(output)
            if output.exists() and not args.overwrite:
                raise NasKbError(f"output exists; use --overwrite: {output}")
            payload = gateway_get_source(
                api_url,
                require_env(args.token_env),
                args.doc_id,
                output,
            )
            emit(args.json, payload)
            return 0

        nas = NasClient(args.nas_cli, args.profile)
        everos = EverOSClient(args.everos_url, args.app_id, args.project_id)
        if args.command == "serve":
            token = require_env(args.token_env)
            everos_health = everos.health()
            if everos_health.get("status") != "ok":
                raise NasKbError("EverOS health check did not return status=ok")
            server = GatewayServer(
                (args.host, args.port),
                nas=nas,
                everos=everos,
                state_path=args.state.expanduser(),
                app_id=args.app_id,
                project_id=args.project_id,
                token=token,
            )
            emit(
                args.json,
                {
                    "ok": True,
                    "service": "nas-kb-gateway",
                    "host": args.host,
                    "port": server.server_address[1],
                    "scope": {"app_id": args.app_id, "project_id": args.project_id},
                },
            )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0

        state = StateStore(args.state.expanduser(), args.app_id, args.project_id)
        try:
            if args.command == "doctor":
                nas_health = nas.doctor(args.path)
                everos_health = everos.health()
                payload = {
                    "ok": nas_health.get("ok") is True and everos_health.get("status") == "ok",
                    "nas": {
                        "ok": nas_health.get("ok"),
                        "profile": nas_health.get("profile"),
                        "allowed_roots": nas_health.get("allowed_roots"),
                    },
                    "everos": everos_health,
                    "scope": {"app_id": args.app_id, "project_id": args.project_id},
                    "state": str(state.path),
                    "indexed_documents": everos.document_count(),
                }
            elif args.command == "index":
                extensions = {
                    value.lower() if value.startswith(".") else f".{value.lower()}"
                    for value in (args.extension or DEFAULT_EXTENSIONS)
                }
                if args.apply:
                    everos.health()
                payload = index_documents(
                    nas,
                    everos,
                    state,
                    under=args.under,
                    max_depth=args.max_depth,
                    limit=args.limit,
                    extensions=extensions,
                    max_bytes=args.max_bytes,
                    category_id=args.category_id,
                    apply=args.apply,
                )
            elif args.command == "status":
                if args.limit <= 0:
                    raise NasKbError("status --limit must be greater than 0")
                payload = {
                    "ok": True,
                    "scope": {"app_id": args.app_id, "project_id": args.project_id},
                    "state": str(state.path),
                    "counts": state.counts(),
                    "everos_documents": everos.document_count(),
                    "items": state.list(args.limit),
                }
            elif args.command == "sync":
                roots = load_sync_roots(args.config.expanduser())
                if args.apply:
                    everos.health()
                payload = sync_documents(
                    nas,
                    everos,
                    state,
                    roots,
                    apply=args.apply,
                )
            elif args.command == "search":
                payload = search_documents(
                    everos,
                    state,
                    args.query,
                    method=args.method,
                    top_k=args.top_k,
                    include_content=args.include_content,
                )
            elif args.command == "get-source":
                source = state.by_doc_id(args.doc_id)
                if not source:
                    raise NasKbError(f"unknown doc_id: {args.doc_id}")
                output = args.output or Path(source["remote_path"]).name
                output = Path(output)
                if output.exists() and not args.overwrite:
                    raise NasKbError(f"output exists; use --overwrite: {output}")
                nas.get(source["remote_path"], output)
                payload = {
                    "ok": True,
                    "doc_id": args.doc_id,
                    "remote_path": source["remote_path"],
                    "output": str(output),
                }
            else:
                raise NasKbError(f"unknown command: {args.command}")
            emit(args.json, payload)
            return 0 if payload.get("ok", True) else 2
        finally:
            state.close()
    except (NasKbError, OSError, sqlite3.Error) as exc:
        emit(args.json, {"ok": False, "error": exc.__class__.__name__, "message": str(exc)})
        return 2


def emit(as_json: bool, payload: dict[str, Any]) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
        return
    if not payload.get("ok", True):
        print(f"error: {payload.get('message', 'unknown error')}", file=sys.stderr)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
