from __future__ import annotations

import io
import json
import runpy
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.error import URLError
from urllib import request

import pytest

from cli_anything.ugreen_nas import _cli
from cli_anything.ugreen_nas.core import updates
from cli_anything.ugreen_nas.tests.test_cli_webdav import write_config


REVISION = "a" * 40


@pytest.fixture
def installed(tmp_path, monkeypatch):
    installation = tmp_path / "installation.json"
    installation.write_text(json.dumps({"revision": REVISION}))
    cache = tmp_path / "state" / "update-check.json"
    monkeypatch.setattr(updates, "INSTALLATION_PATH", installation)
    monkeypatch.setattr(updates, "CACHE_PATH", cache)
    return installation, cache


@pytest.mark.parametrize(("status", "ahead", "expected"), [
    ("ahead", 1, True), ("diverged", 2, True),
    ("identical", 0, False), ("behind", 0, False),
    ("ahead", 0, False), ("ahead", "1", False), ("ahead", True, False), ("unknown", 1, False),
])
def test_github_comparison_respects_direction(monkeypatch, status, ahead, expected):
    def fetch(request, timeout):
        assert request.full_url.endswith(f"/compare/{REVISION}...main?per_page=1")
        assert timeout <= updates.CHECK_TIMEOUT
        assert "Authorization" not in request.headers
        return io.BytesIO(json.dumps({"status": status, "ahead_by": ahead}).encode())

    monkeypatch.setattr(updates, "urlopen", fetch)
    assert updates.github_has_update(REVISION) is expected


def test_update_notice_is_cached_and_only_uses_stderr(installed, monkeypatch, capsys):
    installation, cache = installed
    calls = []

    def check(command, **kwargs):
        calls.append(command)
        assert command[0] == sys.executable
        assert kwargs["timeout"] == 2
        return SimpleNamespace(returncode=0, stdout=updates.NOTICE + "\n")

    monkeypatch.setattr(updates.subprocess, "run", check)
    updates.notify_update()
    updates.notify_update()
    output = capsys.readouterr()
    assert output.out == "" and output.err == updates.NOTICE + "\n"
    assert len(calls) == 1
    assert calls[0][-1] == REVISION
    cached = json.loads(cache.read_text())
    assert cached["revision"] == REVISION
    cache.write_text(json.dumps({**cached, "checked_at": time.time() - updates.CHECK_INTERVAL - 1}))
    updates.notify_update()
    assert len(calls) == 2
    installation.write_text(json.dumps({"revision": "b" * 40}))
    updates.notify_update()
    assert calls[-1][-1] == "b" * 40 and len(calls) == 3


@pytest.mark.parametrize("contents", ["not json", "[]", '{"revision": null}', '{"revision": "invalid"}'])
def test_unknown_installation_does_not_check(installed, monkeypatch, capsys, contents):
    installation, cache = installed
    installation.write_text(contents)
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected check"))
    updates.notify_update()
    assert not cache.exists()
    assert capsys.readouterr().err == ""


def test_missing_installation_does_not_check(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(updates, "INSTALLATION_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected check"))
    updates.notify_update()
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("cached", ["broken", "[]", '{"checked_at": "invalid"}',
                                     json.dumps({"revision": REVISION, "checked_at": time.time() + 1000})])
def test_invalid_cache_is_replaced(installed, monkeypatch, cached):
    _, cache = installed
    cache.parent.mkdir()
    cache.write_text(cached)
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=""))
    updates.notify_update()
    assert json.loads(cache.read_text())["revision"] == REVISION


@pytest.mark.parametrize("failure", [OSError("offline"), subprocess.TimeoutExpired("checker", 2)])
def test_failed_check_is_silent_and_cached(installed, monkeypatch, capsys, failure):
    def check(*args, **kwargs):
        raise failure

    monkeypatch.setattr(updates.subprocess, "run", check)
    updates.notify_update()
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **kw: pytest.fail("retry before interval"))
    updates.notify_update()
    assert capsys.readouterr().err == ""


def test_unwritable_cache_skips_check(installed, monkeypatch, capsys):
    _, cache = installed
    cache.parent.write_text("not a directory")
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected check"))
    updates.notify_update()
    assert capsys.readouterr().err == ""


def test_slow_child_is_stopped(installed, tmp_path, monkeypatch, capsys):
    script = tmp_path / "slow.py"
    script.write_text("import time; time.sleep(10)\n")
    monkeypatch.setattr(updates, "__file__", str(script))
    monkeypatch.setattr(updates, "CHECK_TIMEOUT", 0.1)
    started = time.monotonic()
    updates.notify_update()
    assert time.monotonic() - started < 2
    assert capsys.readouterr().err == ""


def test_cli_json_is_not_changed_by_notice(installed, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("UGREEN_NAS_PASSWORD", "pw")
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=updates.NOTICE))
    config = write_config(tmp_path, "https://nas.example:5006")
    code = _cli.main(["--config", str(config), "--json", "capabilities"])
    output = capsys.readouterr()
    assert code == 0 and json.loads(output.out)["ok"] is True
    assert output.err == updates.NOTICE + "\n"


def test_script_quietly_skips_network_failure(monkeypatch, capsys):
    def fetch(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr(request, "urlopen", fetch)
    monkeypatch.setattr(sys, "argv", [updates.__file__, REVISION])
    runpy.run_path(updates.__file__, run_name="__main__")
    assert capsys.readouterr() == ("", "")
