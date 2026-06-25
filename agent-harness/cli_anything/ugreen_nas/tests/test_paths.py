import pytest

from cli_anything.ugreen_nas.core.paths import PathAccessError, assert_allowed, normalize_remote_path


def test_normalize_remote_path():
    assert normalize_remote_path("Team/../Team/file.txt") == "/Team/file.txt"
    assert normalize_remote_path("/Team//A") == "/Team/A"


def test_reject_url_path():
    with pytest.raises(PathAccessError):
        normalize_remote_path("https://example.com/file")


def test_allowed_roots():
    assert assert_allowed("/Team/a.txt", ("/Team",)) == "/Team/a.txt"
    with pytest.raises(PathAccessError):
        assert_allowed("/Other/a.txt", ("/Team",))
