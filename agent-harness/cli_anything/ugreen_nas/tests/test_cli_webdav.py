from __future__ import annotations

import base64
import json
import threading
import urllib.parse
import xml.sax.saxutils
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cli_anything.ugreen_nas._cli import main


class Store:
    def __init__(self):
        self.items = {
            "/": None,
            "/Team": None,
            "/Team/readme.txt": b"hello",
        }
        now = datetime.now(timezone.utc)
        self.modified = {
            "/": now,
            "/Team": now,
            "/Team/readme.txt": now - timedelta(hours=1),
        }


class Handler(BaseHTTPRequestHandler):
    store: Store

    def log_message(self, format, *args):
        return

    def do_PROPFIND(self):
        path = self.path.rstrip("/") or "/"
        if path not in self.store.items:
            self.send_error(404)
            return
        depth = self.headers.get("Depth", "1")
        paths = [path]
        if depth == "1":
            prefix = path.rstrip("/") + "/"
            paths.extend(
                child
                for child in sorted(self.store.items)
                if child != path and child.startswith(prefix) and "/" not in child[len(prefix) :]
            )
        body = self._multistatus(paths)
        self.send_response(207)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.rstrip("/") or "/"
        data = self.store.items.get(path)
        if data is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_PUT(self):
        path = self.path.rstrip("/") or "/"
        if self.headers.get("If-None-Match") == "*" and path in self.store.items:
            self.send_error(412)
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.store.items[path] = self.rfile.read(length)
        self.send_response(201)
        self.end_headers()

    def do_DELETE(self):
        path = self.path.rstrip("/") or "/"
        if path not in self.store.items:
            self.send_error(404)
            return
        del self.store.items[path]
        self.send_response(204)
        self.end_headers()

    def do_MKCOL(self):
        path = self.path.rstrip("/") or "/"
        if path in self.store.items:
            self.send_error(405)
            return
        self.store.items[path] = None
        self.store.modified[path] = datetime.now(timezone.utc)
        self.send_response(201)
        self.end_headers()

    def do_MOVE(self):
        self._copy_or_move(move=True)

    def do_COPY(self):
        self._copy_or_move(move=False)

    def _copy_or_move(self, *, move):
        source = self.path.rstrip("/") or "/"
        destination = urllib.parse.urlsplit(self.headers["Destination"]).path.rstrip("/") or "/"
        destination = urllib.parse.unquote(destination)
        if source not in self.store.items:
            self.send_error(404)
            return
        if destination in self.store.items and self.headers.get("Overwrite") != "T":
            self.send_error(412)
            return
        self.store.items[destination] = self.store.items[source]
        self.store.modified[destination] = datetime.now(timezone.utc)
        if move:
            del self.store.items[source]
            self.store.modified.pop(source, None)
        self.send_response(201)
        self.end_headers()

    def _multistatus(self, paths):
        responses = []
        for path in paths:
            data = self.store.items[path]
            is_dir = data is None
            escaped = xml.sax.saxutils.escape(path)
            size = "" if is_dir else f"<d:getcontentlength>{len(data)}</d:getcontentlength>"
            resource_type = "<d:collection/>" if is_dir else ""
            modified = format_datetime(self.store.modified.get(path, datetime.now(timezone.utc)), usegmt=True)
            responses.append(
                f"""
                <d:response>
                  <d:href>{escaped}</d:href>
                  <d:propstat>
                    <d:prop>
                      <d:resourcetype>{resource_type}</d:resourcetype>
                      {size}
                      <d:getetag>"{len(path)}"</d:getetag>
                      <d:getlastmodified>{modified}</d:getlastmodified>
                    </d:prop>
                    <d:status>HTTP/1.1 200 OK</d:status>
                  </d:propstat>
                </d:response>
                """
            )
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:multistatus xmlns:d="DAV:">'
            + "".join(responses)
            + "</d:multistatus>"
        )
        return body.encode("utf-8")


def test_doctor_and_ls_json(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)
        assert main(["--config", str(config), "--json", "doctor", "--path", "/Team"]) == 0
        doctor = json.loads(capsys.readouterr().out)
        assert doctor["ok"] is True
        assert doctor["checked_path"] == "/Team"
        assert doctor["path_items"][0]["path"] == "/Team"

        assert main(["--config", str(config), "--json", "ls", "/Team"]) == 0
        listing = json.loads(capsys.readouterr().out)
        assert listing["items"][0]["path"] == "/Team/readme.txt"


def test_capabilities_reports_agent_safety_surface(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)
        assert main(["--config", str(config), "--json", "capabilities"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["allowed_roots"] == ["/Team"]
        assert "recent" in payload["read_commands"]
        assert "put" in payload["write_commands"]
        assert payload["dangerous_commands"] == ["rm"]
        assert payload["safety"]["preview_writes_with"] == "--dry-run"


def test_cat_put_and_rm_gate(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)

        assert main(["--config", str(config), "--json", "cat", "/Team/readme.txt"]) == 0
        body = json.loads(capsys.readouterr().out)
        assert body["content"] == "hello"

        local = tmp_path / "upload.txt"
        local.write_text("uploaded", encoding="utf-8")
        assert main(["--config", str(config), "--json", "put", str(local), "/Team/upload.txt"]) == 0
        uploaded = json.loads(capsys.readouterr().out)
        assert uploaded["bytes"] == 8

        assert main(["--config", str(config), "--json", "rm", "/Team/upload.txt"]) == 2
        denied = json.loads(capsys.readouterr().out)
        assert denied["error"] == "ConfigError"

        assert main(["--config", str(config), "--json", "rm", "/Team/upload.txt", "--yes"]) == 0
        deleted = json.loads(capsys.readouterr().out)
        assert deleted["ok"] is True


def test_get_requires_explicit_local_overwrite(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)
        output = tmp_path / "readme.txt"
        output.write_text("keep me", encoding="utf-8")

        assert main(
            ["--config", str(config), "--json", "get", "/Team/readme.txt", "-o", str(output)]
        ) == 2
        denied = json.loads(capsys.readouterr().out)
        assert "use --overwrite" in denied["message"]
        assert output.read_text(encoding="utf-8") == "keep me"

        assert main(
            [
                "--config",
                str(config),
                "--json",
                "get",
                "/Team/readme.txt",
                "-o",
                str(output),
                "--overwrite",
            ]
        ) == 0
        capsys.readouterr()
        assert output.read_text(encoding="utf-8") == "hello"


def test_mkdir_copy_and_move_use_real_webdav_methods(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)

        assert main(["--config", str(config), "--json", "mkdir", "/Team/New"]) == 0
        capsys.readouterr()
        assert Handler.store.items["/Team/New"] is None

        assert main(
            [
                "--config",
                str(config),
                "--json",
                "cp",
                "/Team/readme.txt",
                "/Team/copied.txt",
            ]
        ) == 0
        capsys.readouterr()
        assert Handler.store.items["/Team/copied.txt"] == b"hello"

        assert main(
            [
                "--config",
                str(config),
                "--json",
                "mv",
                "/Team/copied.txt",
                "/Team/moved.txt",
            ]
        ) == 0
        capsys.readouterr()
        assert "/Team/copied.txt" not in Handler.store.items
        assert Handler.store.items["/Team/moved.txt"] == b"hello"


def test_search_rejects_invalid_bounds(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)
        cases = [
            ["search", " ", "--under", "/Team"],
            ["search", "readme", "--under", "/Team", "--max-depth", "-1"],
            ["search", "readme", "--under", "/Team", "--limit", "0"],
        ]
        for command in cases:
            assert main(["--config", str(config), "--json", *command]) == 2
            payload = json.loads(capsys.readouterr().out)
            assert payload["error"] == "ConfigError"


def test_path_outside_allowed_root_is_denied(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)
        assert main(["--config", str(config), "--json", "ls", "/Other"]) == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["error"] == "PathAccessError"


def test_dry_run_previews_writes_without_mutating(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)
        local = tmp_path / "upload.txt"
        local.write_text("preview", encoding="utf-8")

        assert main(
            [
                "--config",
                str(config),
                "--json",
                "--dry-run",
                "put",
                str(local),
                "/Team/upload.txt",
            ]
        ) == 0
        preview = json.loads(capsys.readouterr().out)
        assert preview == {
            "action": "put",
            "bytes": 7,
            "dry_run": True,
            "local_path": str(local),
            "ok": True,
            "overwrite": False,
            "remote_path": "/Team/upload.txt",
        }
        assert "/Team/upload.txt" not in Handler.store.items

        assert main(
            ["--config", str(config), "--json", "--dry-run", "rm", "/Team/readme.txt"]
        ) == 0
        preview = json.loads(capsys.readouterr().out)
        assert preview["action"] == "rm"
        assert "/Team/readme.txt" in Handler.store.items

        cases = [
            (["mkdir", "/Team/NewFolder"], "mkdir"),
            (["edit", "/Team/readme.txt"], "edit"),
            (["mv", "/Team/readme.txt", "/Team/moved.txt"], "mv"),
            (["cp", "/Team/readme.txt", "/Team/copied.txt"], "cp"),
        ]
        for command, expected_action in cases:
            assert main(
                ["--config", str(config), "--json", "--dry-run", *command]
            ) == 0
            preview = json.loads(capsys.readouterr().out)
            assert preview["action"] == expected_action
            assert preview["dry_run"] is True


def test_recent_returns_only_files_inside_window(tmp_path, capsys):
    with webdav_server() as base_url:
        config = write_config(tmp_path, base_url)
        Handler.store.items["/Team/old.txt"] = b"old"
        Handler.store.modified["/Team/old.txt"] = datetime.now(timezone.utc) - timedelta(days=30)

        assert main(
            [
                "--config",
                str(config),
                "--json",
                "recent",
                "--under",
                "/Team",
                "--days",
                "2",
            ]
        ) == 0
        payload = json.loads(capsys.readouterr().out)
        assert [item["path"] for item in payload["items"]] == ["/Team/readme.txt"]
        assert payload["scanned_files"] == 2
        assert payload["matched_files"] == 1
        assert payload["truncated"] is False


class webdav_server:
    def __enter__(self):
        Handler.store = Store()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.thread.join()


def write_config(tmp_path: Path, base_url: str) -> Path:
    config = tmp_path / "config.toml"
    password = base64.b64encode(b"pw").decode("ascii")
    config.write_text(
        f"""
        [profile.default]
        base_url = "{base_url}"
        username = "alice"
        password_command = "python3 -c 'import base64; print(base64.b64decode(\\"{password}\\").decode())'"
        allowed_roots = ["/Team"]
        verify_tls = true
        audit_log = "{tmp_path / 'audit.log'}"
        """,
        encoding="utf-8",
    )
    return config
