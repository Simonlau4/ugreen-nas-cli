from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from nas_kb.cli import (
    GatewayServer,
    NasKbError,
    RemoteItem,
    StateStore,
    discover_documents,
    gateway_get_source,
    gateway_search,
    index_documents,
    load_sync_roots,
    search_documents,
    sync_documents,
)


class FakeNas:
    def __init__(self, listings):
        self.listings = listings
        self.downloads = []

    def list(self, path):
        return self.listings.get(path, [])

    def get(self, remote_path, output):
        self.downloads.append(remote_path)
        output.write_text("knowledge content", encoding="utf-8")


class FakeEverOS:
    def __init__(self):
        self.uploads = []

    def upload(self, file_path, **kwargs):
        self.uploads.append(kwargs)
        return {"doc_id": kwargs.get("doc_id") or "d_123456789abc"}

    def search(self, query, **kwargs):
        return {
            "hits": [
                {
                    "document": {"doc_id": "d_123456789abc", "title": "Guide"},
                    "topic_name": "Usage",
                    "score": 0.9,
                }
            ],
            "total": 1,
            "took_ms": 1.0,
        }

    def health(self):
        return {"status": "ok"}


def item(path, item_type="file", etag='"1"'):
    return RemoteItem(path, item_type, 10, "Thu, 16 Jul 2026 10:00:00 GMT", etag)


def test_discover_documents_filters_extensions_and_depth():
    nas = FakeNas(
        {
            "/Inbox": [item("/Inbox/a.md"), item("/Inbox/image.jpg"), item("/Inbox/Sub", "dir")],
            "/Inbox/Sub": [item("/Inbox/Sub/b.pdf")],
        }
    )
    documents, truncated = discover_documents(
        nas,
        "/Inbox",
        max_depth=1,
        limit=10,
        extensions={".md", ".pdf", ".docx"},
    )
    assert [document.path for document in documents] == ["/Inbox/a.md", "/Inbox/Sub/b.pdf"]
    assert truncated is False

    limited, truncated = discover_documents(
        nas,
        "/Inbox",
        max_depth=1,
        limit=1,
        extensions={".md", ".pdf", ".docx"},
    )
    assert [document.path for document in limited] == ["/Inbox/a.md"]
    assert truncated is True


def test_index_requires_apply_then_skips_unchanged(tmp_path):
    source = item("/Inbox/guide.md")
    nas = FakeNas({"/Inbox": [source]})
    everos = FakeEverOS()
    state = StateStore(tmp_path / "state.sqlite", "nas-kb", "test")
    try:
        preview = index_documents(
            nas,
            everos,
            state,
            under="/Inbox",
            max_depth=0,
            limit=10,
            extensions={".md"},
            max_bytes=100,
            category_id=None,
            apply=False,
        )
        assert preview["counts"]["planned"] == 1
        assert nas.downloads == []
        assert everos.uploads == []

        applied = index_documents(
            nas,
            everos,
            state,
            under="/Inbox",
            max_depth=0,
            limit=10,
            extensions={".md"},
            max_bytes=100,
            category_id="Business",
            apply=True,
        )
        assert applied["counts"]["indexed"] == 1
        assert nas.downloads == ["/Inbox/guide.md"]
        assert everos.uploads[0]["remote_path"] == "/Inbox/guide.md"

        unchanged = index_documents(
            nas,
            everos,
            state,
            under="/Inbox",
            max_depth=0,
            limit=10,
            extensions={".md"},
            max_bytes=100,
            category_id=None,
            apply=True,
        )
        assert unchanged["counts"]["skipped"] == 1
        assert len(everos.uploads) == 1
    finally:
        state.close()


def test_search_adds_remote_source_path(tmp_path):
    state = StateStore(tmp_path / "state.sqlite", "nas-kb", "test")
    source = item("/Inbox/guide.md")
    state.save(source, status="indexed", doc_id="d_123456789abc")
    try:
        result = search_documents(
            FakeEverOS(),
            state,
            "how to use",
            method="hybrid",
            top_k=5,
            include_content=False,
        )
        assert result["hits"][0]["remote_path"] == "/Inbox/guide.md"
        assert result["hits"][0]["source_status"] == "indexed"
    finally:
        state.close()


def test_interrupted_index_is_not_retried_automatically(tmp_path):
    source = item("/Inbox/interrupted.md")
    nas = FakeNas({"/Inbox": [source]})
    everos = FakeEverOS()
    state = StateStore(tmp_path / "state.sqlite", "nas-kb", "test")
    state.save(source, status="indexing", doc_id=None)
    try:
        result = index_documents(
            nas,
            everos,
            state,
            under="/Inbox",
            max_depth=0,
            limit=10,
            extensions={".md"},
            max_bytes=100,
            category_id=None,
            apply=True,
        )
        assert result["counts"]["failed"] == 1
        assert "interrupted" in result["items"][0]["error"]
        assert everos.uploads == []
    finally:
        state.close()


def test_sync_config_previews_multiple_approved_roots(tmp_path):
    config = tmp_path / "team-sync.toml"
    config.write_text(
        """
        [[roots]]
        path = "/Team-A/Knowledge/Published"
        max_depth = 2
        extensions = ["md"]

        [[roots]]
        path = "/Team-B/Knowledge/Published"
        limit = 25
        """,
        encoding="utf-8",
    )
    roots = load_sync_roots(config)
    assert roots[0]["extensions"] == {".md"}
    assert roots[1]["extensions"] == {".md", ".pdf", ".docx"}

    nas = FakeNas(
        {
            "/Team-A/Knowledge/Published": [item("/Team-A/Knowledge/Published/a.md")],
            "/Team-B/Knowledge/Published": [item("/Team-B/Knowledge/Published/b.pdf")],
        }
    )
    state = StateStore(tmp_path / "state.sqlite", "nas-kb", "test")
    try:
        result = sync_documents(
            nas,
            FakeEverOS(),
            state,
            roots,
            apply=False,
        )
        assert result["root_count"] == 2
        assert result["counts"]["planned"] == 2
        assert nas.downloads == []
    finally:
        state.close()


def test_team_gateway_search_and_source_download(tmp_path):
    state_path = tmp_path / "state.sqlite"
    state = StateStore(state_path, "nas-kb", "test")
    state.save(item("/Inbox/guide.md"), status="indexed", doc_id="d_123456789abc")
    state.close()

    server = GatewayServer(
        ("127.0.0.1", 0),
        nas=FakeNas({}),
        everos=FakeEverOS(),
        state_path=state_path,
        app_id="nas-kb",
        project_id="test",
        token="team-read-token-with-at-least-32-chars",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    api_url = f"http://{host}:{port}"
    try:
        result = gateway_search(
            api_url,
            "team-read-token-with-at-least-32-chars",
            "how to use",
            method="hybrid",
            top_k=5,
            include_content=False,
        )
        assert result["hits"][0]["remote_path"] == "/Inbox/guide.md"

        output = tmp_path / "guide.md"
        downloaded = gateway_get_source(
            api_url,
            "team-read-token-with-at-least-32-chars",
            "d_123456789abc",
            output,
        )
        assert downloaded["remote_path"] == "/Inbox/guide.md"
        assert output.read_text(encoding="utf-8") == "knowledge content"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_team_gateway_rejects_missing_token(tmp_path):
    server = GatewayServer(
        ("127.0.0.1", 0),
        nas=FakeNas({}),
        everos=FakeEverOS(),
        state_path=tmp_path / "state.sqlite",
        app_id="nas-kb",
        project_id="test",
        token="team-read-token-with-at-least-32-chars",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    request = urllib.request.Request(
        f"http://{host}:{port}/v1/search",
        data=json.dumps({"query": "test"}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        try:
            urllib.request.urlopen(request)
            raise AssertionError("request without a token should fail")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_team_gateway_rejects_short_server_token(tmp_path):
    with pytest.raises(NasKbError, match="at least 32 characters"):
        GatewayServer(
            ("127.0.0.1", 0),
            nas=FakeNas({}),
            everos=FakeEverOS(),
            state_path=tmp_path / "state.sqlite",
            app_id="nas-kb",
            project_id="test",
            token="too-short",
        )
