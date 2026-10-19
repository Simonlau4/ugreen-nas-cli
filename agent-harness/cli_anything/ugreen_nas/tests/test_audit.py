from __future__ import annotations

import hashlib
import json
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

import pytest

from cli_anything.ugreen_nas._cli import main
from cli_anything.ugreen_nas.core.audit import AuditError, audited_write
from cli_anything.ugreen_nas.core.config import load_profile, write_profile
from cli_anything.ugreen_nas.core.webdav import WebDavClient
from cli_anything.ugreen_nas.tests.test_cli_webdav import Handler, Store, write_config


ROOT = "/Team/CLI_AUDIT_LOGS"


class AuditHandler(Handler):
    def do_PUT(self):
        self.store.puts.append((self.path, self.headers.get("If-None-Match")))
        if self.store.fail_suffix and self.path.endswith(self.store.fail_suffix):
            self.send_error(403)
        else:
            if self.store.ignore_create_condition and "If-None-Match" in self.headers:
                del self.headers["If-None-Match"]
            super().do_PUT()

    def do_MKCOL(self):
        if self.path == self.store.denied_root:
            self.send_error(403)
        else:
            super().do_MKCOL()


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("UGREEN_NAS_PASSWORD", "pw")
    store = Store()
    store.puts = []
    store.fail_suffix = None
    store.denied_root = None
    store.ignore_create_condition = False
    AuditHandler.store = store
    http = ThreadingHTTPServer(("127.0.0.1", 0), AuditHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    config = write_config(tmp_path, f"http://127.0.0.1:{http.server_port}")
    try:
        yield config, store
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def call(config, capsys, *command):
    code = main(["--config", str(config), "--json", *command])
    return code, json.loads(capsys.readouterr().out)


def records(store):
    return [json.loads(data) for path, data in store.items.items() if path.startswith(ROOT + "/") and data is not None]


def local_records(config):
    return [json.loads(line) for line in (config.parent / "audit.log").read_text().splitlines()]


def test_upload_overwrite_and_edit_archive_identity_and_versions(server, tmp_path, capsys, monkeypatch):
    config, store = server
    local = tmp_path / "upload.txt"
    local.write_bytes(b"uploaded")
    code, result = call(config, capsys, "put", str(local), "/Team/report.txt")
    assert code == 0 and result["audit"]["remote_status"] == "succeeded"
    assert json.loads(store.items[result["audit"]["remote_path"]])["sha256"] == hashlib.sha256(b"uploaded").hexdigest()

    local.write_bytes(b"revised")
    code, result = call(config, capsys, "put", str(local), "/Team/report.txt", "--overwrite")
    assert code == 0
    assert json.loads(store.items[result["audit"]["remote_path"]])["overwrite"] is True

    def edit(command, check):
        Path(command[1]).write_bytes(b"edited")

    monkeypatch.setenv("VISUAL", "fake-editor")
    monkeypatch.setattr("cli_anything.ugreen_nas._cli.subprocess.run", edit)
    code, result = call(config, capsys, "edit", "/Team/report.txt")
    assert code == 0 and store.items["/Team/report.txt"] == b"edited"
    saved = json.loads(store.items[result["audit"]["remote_path"]])
    assert saved["before_sha256"] == hashlib.sha256(b"revised").hexdigest()
    assert saved["sha256"] == hashlib.sha256(b"edited").hexdigest()
    assert saved["action"] == "edit" and saved["created"] is False
    assert len(records(store)) == 6
    assert local_records(config) == records(store)
    for record in records(store):
        assert record["username"] == "alice" and record["path"] == "/Team/report.txt"
        assert record["ts"].endswith("+00:00")
        assert set(record).isdisjoint({"password", "authorization", "content", "local_path", "base_url"})
    assert all(header == "*" for path, header in store.puts if path.startswith(ROOT + "/"))


def test_failed_upload_has_failed_record_without_success(server, tmp_path, capsys):
    config, store = server
    local = tmp_path / "upload.txt"
    local.write_bytes(b"replacement")
    code, result = call(config, capsys, "put", str(local), "/Team/readme.txt")
    assert code == 2 and result["status"] == 412
    assert store.items["/Team/readme.txt"] == b"hello"
    assert [record["status"] for record in records(store)] == ["started", "failed"]
    assert records(store)[-1]["error"] == {"type": "WebDavError", "http_status": 412}


def test_no_overwrite_guard_survives_nas_ignoring_http_condition(server, tmp_path, capsys):
    config, store = server
    store.ignore_create_condition = True
    local = tmp_path / "upload.txt"
    local.write_bytes(b"must not overwrite")
    code, result = call(config, capsys, "put", str(local), "/Team/readme.txt")
    assert code == 2 and result["status"] == 412
    assert "--overwrite" in result["message"]
    assert store.items["/Team/readme.txt"] == b"hello"
    assert all(path != "/Team/readme.txt" for path, _ in store.puts)
    assert [record["status"] for record in records(store)] == ["started", "failed"]


def test_archive_record_is_not_replaced_when_nas_ignores_condition(server, monkeypatch):
    config, store = server
    store.ignore_create_condition = True
    monkeypatch.setattr("cli_anything.ugreen_nas.core.audit.uuid.uuid4", lambda: UUID(int=1))
    profile = load_profile("default", config)
    client = WebDavClient(profile)
    with audited_write(profile, client, "put", path="/Team/one.txt"):
        client.put("/Team/one.txt", b"original")
    before = records(store)
    with pytest.raises(AuditError) as failure:
        with audited_write(profile, client, "put", path="/Team/two.txt"):
            client.put("/Team/two.txt", b"replacement")
    assert failure.value.mutation_applied is False
    assert "/Team/two.txt" not in store.items and records(store) == before


@pytest.mark.parametrize("failure", ["directory", "start_record", "local_log"])
def test_audit_start_failure_prevents_file_mutation(server, tmp_path, capsys, failure):
    config, store = server
    if failure == "directory":
        store.denied_root = ROOT
    elif failure == "start_record":
        store.fail_suffix = ".started.json"
    else:
        (tmp_path / "audit.log").mkdir()
    local = tmp_path / "upload.txt"
    local.write_bytes(b"replacement")
    code, result = call(config, capsys, "put", str(local), "/Team/readme.txt", "--overwrite")
    assert code == 2 and result["error"] == "AuditError"
    assert result["mutation_applied"] is False
    assert store.items["/Team/readme.txt"] == b"hello"
    assert all(path != "/Team/readme.txt" for path, _ in store.puts)


def test_completion_failure_reports_applied_change_and_preserves_receipts(server, tmp_path, capsys):
    config, store = server
    store.fail_suffix = ".succeeded.json"
    local = tmp_path / "upload.txt"
    local.write_bytes(b"replacement")
    code, result = call(config, capsys, "put", str(local), "/Team/readme.txt", "--overwrite")
    assert code == 3 and result["mutation_applied"] is True
    assert "do not repeat" in result["message"]
    assert store.items["/Team/readme.txt"] == b"replacement"
    assert result["audit"]["remote_status"] == "started"
    assert json.loads(store.items[result["audit"]["remote_path"]])["status"] == "started"
    assert result["audit"]["local_status"] == "succeeded"
    assert local_records(config)[-1]["status"] == "succeeded"


def test_failed_operation_and_failed_receipt_do_not_report_success(server, tmp_path, capsys):
    config, store = server
    store.fail_suffix = ".failed.json"
    local = tmp_path / "upload.txt"
    local.write_bytes(b"replacement")
    code, result = call(config, capsys, "put", str(local), "/Team/readme.txt")
    assert code == 3 and result["mutation_applied"] is None
    assert result["audit"]["local_status"] == "failed"
    assert local_records(config)[-1]["error"]["http_status"] == 412
    assert store.items["/Team/readme.txt"] == b"hello"


def test_read_dry_run_and_unchanged_edit_create_no_records(server, tmp_path, capsys, monkeypatch):
    config, store = server
    local = tmp_path / "upload.txt"
    local.write_bytes(b"preview")
    assert call(config, capsys, "--dry-run", "put", str(local), "/Team/report.txt")[0] == 0
    assert call(config, capsys, "cat", "/Team/readme.txt")[0] == 0
    monkeypatch.setenv("VISUAL", "fake-editor")
    monkeypatch.setattr("cli_anything.ugreen_nas._cli.subprocess.run", lambda *args, **kwargs: None)
    code, result = call(config, capsys, "edit", "/Team/readme.txt")
    assert code == 0 and result["changed"] is False
    assert not records(store) and ROOT not in store.items
    assert not (tmp_path / "audit.log").exists()


def test_edit_create_records_new_file(server, capsys, monkeypatch):
    config, store = server
    monkeypatch.setenv("VISUAL", "fake-editor")
    monkeypatch.setattr("cli_anything.ugreen_nas._cli.subprocess.run", lambda command, **kwargs: Path(command[1]).write_bytes(b"created"))
    code, result = call(config, capsys, "edit", "/Team/created.txt", "--create")
    assert code == 0
    record = json.loads(store.items[result["audit"]["remote_path"]])
    assert record["created"] is True and record["before_sha256"] is None


def test_other_mutations_archive_paths(server, capsys):
    config, store = server
    for command in [
        ["mkdir", "/Team/New"],
        ["cp", "/Team/readme.txt", "/Team/copied.txt"],
        ["mv", "/Team/copied.txt", "/Team/moved.txt"],
        ["rm", "/Team/moved.txt", "--yes"],
    ]:
        code, result = call(config, capsys, *command)
        assert code == 0
        record = json.loads(store.items[result["audit"]["remote_path"]])
        assert record["action"] == command[0] and record["status"] == "succeeded"
        if command[0] in {"cp", "mv"}:
            assert (record["src"], record["dst"]) == tuple(command[1:3])
        else:
            assert record["path"] == command[1]


def test_audit_root_must_be_allowed_before_any_writes(server, tmp_path, capsys, monkeypatch):
    config, store = server
    monkeypatch.setenv("UGREEN_NAS_AUDIT_ROOT", "/Other/Logs")
    code, result = call(config, capsys, "mkdir", "/Team/New")
    assert code == 2 and result["error"] == "PathAccessError"
    assert "/Team/New" not in store.items and not store.puts
    assert not (tmp_path / "audit.log").exists()


@pytest.mark.parametrize("command", [
    ["mkdir", ROOT + "/manual"],
    ["rm", ROOT, "--yes"],
    ["rm", "/Team", "--yes"],
    ["mv", "/Team", "/Team/elsewhere"],
    ["cp", "/Team/readme.txt", ROOT + "/manual.txt"],
])
def test_archive_and_ancestors_are_protected(server, capsys, command):
    config, store = server
    code, result = call(config, capsys, *command)
    assert code == 2 and "protected" in result["message"]
    assert store.items["/Team/readme.txt"] == b"hello" and not store.puts


def test_concurrent_users_do_not_replace_each_others_records(server, tmp_path):
    config, store = server
    profile = load_profile("default", config)

    def upload(index):
        personal = replace(profile, username=f"user-{index}", audit_log=tmp_path / f"user-{index}.log")
        client = WebDavClient(personal)
        path = f"/Team/upload-{index}.txt"
        with audited_write(personal, client, "put", path=path) as receipt:
            client.put(path, b"content")
        return receipt

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(upload, range(8)))
    assert len({receipt["event_id"] for receipt in receipts}) == 8
    archived = records(store)
    assert len(archived) == 16
    assert {record["username"] for record in archived} == {f"user-{index}" for index in range(8)}
    assert sum(record["status"] == "succeeded" for record in archived) == 8


def test_profile_init_accepts_and_preserves_audit_root(tmp_path, capsys):
    config = tmp_path / "config.toml"
    args = ["profile-init", "--base-url", "https://nas.example:5006", "--username", "alice", "--allowed-root", "/Team"]
    code, result = call(config, capsys, *args, "--audit-root", ROOT)
    assert code == 0
    write_profile("other", "https://nas.example:5006", "bob", ["/Team"], None, True, config_path=config)
    write_profile("default", "https://nas.example:5006", "alice", ["/Team"], None, True, config_path=config)
    assert tomllib.loads(config.read_text())["profile"]["default"]["audit_root"] == ROOT
    before = config.read_bytes()
    code, result = call(config, capsys, *args, "--audit-root", "/Other/Logs")
    assert code == 2 and result["error"] == "PathAccessError"
    assert config.read_bytes() == before
    code, result = call(config, capsys, "profile-init", "--base-url", "https://nas.example:5006",
                        "--username", "alice", "--allowed-root", "/Other")
    assert code == 2 and result["error"] == "PathAccessError"
    assert config.read_bytes() == before


def test_capabilities_reports_profile_and_environment_audit_root(server, capsys, monkeypatch):
    config, store = server
    code, result = call(config, capsys, "capabilities")
    assert code == 0 and result["audit"]["remote_root"] == ROOT
    monkeypatch.setenv("UGREEN_NAS_AUDIT_ROOT", "/Team/OtherLogs")
    code, result = call(config, capsys, "capabilities")
    assert code == 0 and result["audit"]["remote_root"] == "/Team/OtherLogs"
    assert not store.puts


@pytest.mark.parametrize("setting", ["", 'audit_root = ""'])
def test_missing_or_empty_audit_root_archives_upload_results(server, tmp_path, capsys, monkeypatch, setting):
    config, store = server
    root = "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"
    monkeypatch.delenv("UGREEN_NAS_AUDIT_ROOT", raising=False)
    config.write_text(config.read_text().replace(f'audit_root = "{ROOT}"', setting).replace(
        'allowed_roots = ["/Team"]', 'allowed_roots = ["/Team", "/Agent_Knowledge_Base"]'
    ))
    original_config = config.read_bytes()
    store.items["/Agent_Knowledge_Base"] = None
    local = tmp_path / "upload.txt"
    local.write_bytes(b"uploaded")

    code, capabilities = call(config, capsys, "capabilities")
    assert code == 0 and capabilities["audit"]["remote_root"] == root
    code, result = call(config, capsys, "put", str(local), "/Team/report.txt")
    assert code == 0 and result["audit"]["remote_path"].startswith(root + "/")
    code, result = call(config, capsys, "put", str(local), "/Team/report.txt")
    assert code == 2 and result["status"] == 412
    archived = [json.loads(data) for path, data in store.items.items()
                if path.startswith(root + "/") and data is not None]
    assert [record["status"] for record in archived] == ["started", "succeeded", "started", "failed"]
    assert local_records(config) == archived
    assert all(record["username"] == "alice" for record in archived)
    assert all(record["sha256"] == hashlib.sha256(b"uploaded").hexdigest() for record in archived)
    assert config.read_bytes() == original_config


def test_default_audit_archive_does_not_expand_allowed_roots(server, tmp_path, capsys, monkeypatch):
    config, store = server
    monkeypatch.delenv("UGREEN_NAS_AUDIT_ROOT", raising=False)
    config.write_text(config.read_text().replace(f'audit_root = "{ROOT}"', ""))
    original_config = config.read_bytes()
    local = tmp_path / "upload.txt"
    local.write_bytes(b"uploaded")
    code, result = call(config, capsys, "put", str(local), "/Team/report.txt")
    assert code == 2 and result["error"] == "PathAccessError"
    assert "/Team/report.txt" not in store.items and not store.puts
    assert config.read_bytes() == original_config
    assert not (tmp_path / "audit.log").exists()


def test_default_audit_archive_failure_prevents_upload(server, tmp_path, capsys, monkeypatch):
    config, store = server
    monkeypatch.delenv("UGREEN_NAS_AUDIT_ROOT", raising=False)
    config.write_text(config.read_text().replace(f'audit_root = "{ROOT}"', "").replace(
        'allowed_roots = ["/Team"]', 'allowed_roots = ["/Team", "/Agent_Knowledge_Base"]'
    ))
    store.denied_root = "/Agent_Knowledge_Base/CLI_AUDIT_LOGS"
    local = tmp_path / "upload.txt"
    local.write_bytes(b"uploaded")
    code, result = call(config, capsys, "put", str(local), "/Team/report.txt")
    assert code == 2 and result["error"] == "AuditError"
    assert result["mutation_applied"] is False
    assert "/Team/report.txt" not in store.items and not store.puts
