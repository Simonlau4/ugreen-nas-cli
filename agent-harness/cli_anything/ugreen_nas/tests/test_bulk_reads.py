from __future__ import annotations

import json
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

from cli_anything.ugreen_nas._cli import main
from cli_anything.ugreen_nas.tests.test_cli_webdav import Handler, Store, write_config


class BulkHandler(Handler):
    @contextmanager
    def request_slot(self, method):
        with self.store.lock:
            self.store.active += 1
            self.store.peak = max(self.store.peak, self.store.active)
            self.store.requests.append((method, self.path, self.headers.get("Range")))
        try:
            time.sleep(self.store.delay)
            yield
        finally:
            with self.store.lock:
                self.store.active -= 1

    def do_PROPFIND(self):
        with self.request_slot("PROPFIND"):
            status = self.store.errors.get(self.path)
            if status:
                self.send_error(status)
            else:
                super().do_PROPFIND()

    def _multistatus(self, paths):
        root = ET.fromstring(super()._multistatus(paths))
        for tag in root.iter("{DAV:}getetag"):
            tag.text = f'"v{self.store.version}"'
        return ET.tostring(root)

    def do_GET(self):
        with self.request_slot("GET"):
            path = urllib.parse.unquote(self.path)
            data = self.store.items.get(path)
            if data is None:
                self.send_error(404)
                return
            etag = f'"v{self.store.version}"'
            if self.headers.get("If-Match", etag) != etag:
                self.send_error(412)
                return
            offset = 0
            if self.headers.get("Range") and not self.store.ignore_range and self.headers.get("If-Range") == etag:
                offset = int(self.headers["Range"].split("=")[1].rstrip("-"))
            self.send_response(206 if offset else 200)
            self.send_header("Content-Length", str(len(data) - offset))
            if offset:
                self.send_header("Content-Range", f"bytes {offset}-{len(data) - 1}/{len(data)}")
            self.end_headers()
            if self.store.interrupt == path:
                self.store.interrupt = None
                self.wfile.write(data[: 2 * 1024 * 1024])
                self.wfile.flush()
                self.close_connection = True
            else:
                self.wfile.write(data[offset:])


@pytest.fixture
def server():
    store = Store()
    store.lock = threading.Lock()
    store.active = store.peak = 0
    store.requests = []
    store.errors = {}
    store.delay = 0
    store.version = 1
    store.ignore_range = False
    store.interrupt = None
    BulkHandler.store = store
    http = ThreadingHTTPServer(("127.0.0.1", 0), BulkHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", store
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def add(store, path, data=b"file"):
    parts = path.strip("/").split("/")
    for count in range(1, len(parts)):
        store.items["/" + "/".join(parts[:count])] = None
    store.items[path] = data


def call(config, capsys, *command):
    code = main(["--config", str(config), "--json", *command])
    return code, json.loads(capsys.readouterr().out)


def test_search_reports_limit_and_all_returns_complete_results(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    for number in range(150):
        add(store, f"/Team/match-{number:03}.txt")
    code, result = call(config, capsys, "search", "match")
    assert code == 3 and len(result["matches"]) == 100
    assert result["truncated"] and not result["complete"]
    code, result = call(config, capsys, "search", "match", "--all")
    assert code == 0 and result["complete"] and len(result["matches"]) == 150


def test_search_exact_limit_is_complete(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    for number in range(100):
        add(store, f"/Team/match-{number}.txt")
    code, result = call(config, capsys, "search", "match")
    assert code == 0 and result["complete"] and not result["truncated"]


def test_search_recent_and_scan_report_depth_coverage(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    deep = "/Team/a/b/c/d/e/f/deep-match.txt"
    add(store, deep)
    for command in [("search", "deep-match"), ("recent", "--under", "/Team")]:
        code, result = call(config, capsys, *command)
        assert code == 3 and result["depth_limited"] and not result["complete"]
        code, result = call(config, capsys, *command, "--all")
        assert code == 0 and result["complete"]
        assert deep in [item["path"] for item in result.get("matches", result.get("items"))]
    code, result = call(config, capsys, "scan")
    assert code == 0 and deep in [item["path"] for item in result["items"]]


@pytest.mark.parametrize("status", [403, 404])
def test_denied_directory_does_not_block_readable_sibling(server, tmp_path, capsys, status):
    url, store = server
    config = write_config(tmp_path, url)
    add(store, "/Team/Blocked/file.txt")
    add(store, "/Team/Readable/match.txt")
    store.errors["/Team/Blocked"] = status
    code, result = call(config, capsys, "search", "match", "--all")
    assert code == 3 and result["errors"][0]["status"] == status
    assert [item["path"] for item in result["matches"]] == ["/Team/Readable/match.txt"]


def test_scan_and_download_use_concurrent_requests(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    store.delay = 0.04
    for number in range(8):
        add(store, f"/Team/dir-{number}/file.txt")
    manifest = tmp_path / "manifest.json"
    code, listing = call(config, capsys, "scan", "-o", str(manifest), "--workers", "4")
    assert code == 0 and listing["complete"] and store.peak > 1
    assert json.loads(manifest.read_text()) == listing
    assert sum(item["type"] == "file" for item in listing["items"]) == 9
    store.peak = 0
    code, result = call(config, capsys, "get-many", "--manifest", str(manifest), "-o", str(tmp_path / "download"))
    assert code == 0 and result["complete"] and store.peak > 1
    assert (tmp_path / "download/Team/dir-0/file.txt").read_bytes() == b"file"


@pytest.mark.parametrize("ignore_range", [False, True])
def test_interrupted_file_resumes_or_restarts_when_range_is_ignored(server, tmp_path, capsys, ignore_range):
    url, store = server
    config = write_config(tmp_path, url)
    path = "/Team/large.bin"
    content = b"a" * (2 * 1024 * 1024) + b"b" * (2 * 1024 * 1024)
    add(store, path, content)
    store.interrupt = path
    output = tmp_path / "download"
    code, result = call(config, capsys, "get-many", path, "-o", str(output))
    assert code == 3 and not result["complete"]
    assert not (output / "Team/large.bin").exists()
    assert (output / ".ugnas-downloads/partial/Team/large.bin").stat().st_size == 2 * 1024 * 1024
    store.ignore_range = ignore_range
    code, result = call(config, capsys, "get-many", path, "-o", str(output), "--resume")
    assert code == 0 and (output / "Team/large.bin").read_bytes() == content
    assert ("GET", path, "bytes=2097152-") in store.requests
    gets = sum(method == "GET" for method, _, _ in store.requests)
    code, result = call(config, capsys, "get-many", path, "-o", str(output), "--resume")
    assert code == 0 and result["items"][0]["resumed"]
    assert sum(method == "GET" for method, _, _ in store.requests) == gets


def test_changed_remote_version_restarts_partial_download(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    path = "/Team/large.bin"
    add(store, path, b"old!" * (1024 * 1024))
    store.interrupt = path
    output = tmp_path / "download"
    assert call(config, capsys, "get-many", path, "-o", str(output))[0] == 3
    store.version = 2
    store.items[path] = b"new!" * (1024 * 1024)
    code, _ = call(config, capsys, "get-many", path, "-o", str(output), "--resume")
    assert code == 0 and (output / "Team/large.bin").read_bytes() == store.items[path]
    assert [request for request in store.requests if request[0] == "GET"][-1][2] is None


def test_resume_preserves_manually_modified_local_file(server, tmp_path, capsys):
    url, _ = server
    config = write_config(tmp_path, url)
    output = tmp_path / "download"
    assert call(config, capsys, "get-many", "/Team/readme.txt", "-o", str(output))[0] == 0
    local = output / "Team/readme.txt"
    local.write_text("my edited file")
    code, result = call(config, capsys, "get-many", "/Team/readme.txt", "-o", str(output), "--resume")
    assert code == 3 and "--overwrite" in result["items"][0]["message"]
    assert local.read_text() == "my edited file"


def test_bulk_read_checks_permissions_before_network_or_local_writes(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    code, _ = call(config, capsys, "get-many", "/Team/readme.txt", "/Other/private.txt", "-o", str(tmp_path / "download"))
    assert code == 2 and not store.requests and not (tmp_path / "download").exists()
    code, _ = call(config, capsys, "scan", "--under", "/Other")
    assert code == 2 and not store.requests


def test_partial_manifest_stays_partial_after_downloading_known_files(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    add(store, "/Team/Blocked/file.txt")
    store.errors["/Team/Blocked"] = 403
    manifest = tmp_path / "manifest.json"
    assert call(config, capsys, "scan", "-o", str(manifest))[0] == 3
    code, result = call(config, capsys, "get-many", "--manifest", str(manifest), "-o", str(tmp_path / "download"))
    assert code == 3 and not result["source_complete"] and result["source_errors"]
    assert result["items"][0]["ok"]


def test_authentication_failure_stops_scan(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    store.errors["/Team"] = 401
    code, result = call(config, capsys, "scan")
    assert code == 2 and result["status"] == 401


def test_bulk_download_continues_after_denied_file(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    add(store, "/Team/blocked.txt")
    store.errors["/Team/blocked.txt"] = 403
    code, result = call(config, capsys, "get-many", "/Team/blocked.txt", "/Team/readme.txt", "-o", str(tmp_path / "download"))
    assert code == 3 and result["items"][0]["status"] == 403
    assert result["items"][1]["ok"]
    assert (tmp_path / "download/Team/readme.txt").read_bytes() == b"hello"


def test_bulk_download_requires_overwrite_for_unmanaged_file(server, tmp_path, capsys):
    url, _ = server
    config = write_config(tmp_path, url)
    output = tmp_path / "download"
    local = output / "Team/readme.txt"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"keep me")
    code, _ = call(config, capsys, "get-many", "/Team/readme.txt", "-o", str(output), "--resume")
    assert code == 3 and local.read_bytes() == b"keep me"
    code, _ = call(config, capsys, "get-many", "/Team/readme.txt", "-o", str(output), "--overwrite")
    assert code == 0 and local.read_bytes() == b"hello"


def test_bulk_download_refuses_output_symlink_escape(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    output = tmp_path / "download"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (output / "Team").symlink_to(outside, target_is_directory=True)
    code, _ = call(config, capsys, "get-many", "/Team/readme.txt", "-o", str(output))
    assert code == 2 and not store.requests and not list(outside.iterdir())


def test_manifest_can_be_shared_while_current_profile_controls_access(server, tmp_path, capsys):
    url, store = server
    config = write_config(tmp_path, url)
    manifest = tmp_path / "shared.json"
    manifest.write_text(json.dumps({
        "source": {"base_url": "https://another-route-to-nas:5006", "username": "teammate"},
        "complete": True,
        "items": [{"path": "/Team/readme.txt", "type": "file"}],
    }))
    code, result = call(config, capsys, "get-many", "--manifest", str(manifest), "-o", str(tmp_path / "download"))
    assert code == 0 and result["complete"]
    manifest.write_text(json.dumps({"complete": True, "items": [{"path": "/Other/private.txt", "type": "file"}]}))
    store.requests.clear()
    code, _ = call(config, capsys, "get-many", "--manifest", str(manifest), "-o", str(tmp_path / "other"))
    assert code == 2 and not store.requests
