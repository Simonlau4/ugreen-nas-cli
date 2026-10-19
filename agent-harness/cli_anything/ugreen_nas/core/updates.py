from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


INSTALLATION_PATH = Path(sys.prefix).parent / "installation.json"
CACHE_PATH = Path("~/.local/state/ugreen-nas-cli/update-check.json").expanduser()
CHECK_INTERVAL = 6 * 60 * 60
CHECK_TIMEOUT = 2
NOTICE = (
    "ugnas: An update is available on GitHub. Update instructions: "
    "https://github.com/Simonlau4/ugreen-nas-cli#update-an-existing-installation"
)


def notify_update() -> None:
    try:
        installation = json.loads(INSTALLATION_PATH.read_text(encoding="utf-8"))
        revision = installation.get("revision") if isinstance(installation, dict) else None
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            return
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
        now = time.time()
        if isinstance(cached, dict) and cached.get("revision") == revision:
            checked = cached.get("checked_at")
            if isinstance(checked, (int, float)) and 0 <= now - checked < CHECK_INTERVAL:
                return
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({"revision": revision, "checked_at": now}), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), revision],
            capture_output=True, text=True, timeout=CHECK_TIMEOUT,
        )
        if result.returncode == 0 and result.stdout.strip() == NOTICE:
            print(NOTICE, file=sys.stderr)
    except (OSError, ValueError, subprocess.SubprocessError):
        return


def github_has_update(revision: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        return False
    request = Request(
        f"https://api.github.com/repos/Simonlau4/ugreen-nas-cli/compare/{revision}...main?per_page=1",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ugreen-nas-cli"},
    )
    with urlopen(request, timeout=1.5) as response:
        comparison = json.loads(response.read(1024 * 1024))
    return (
        isinstance(comparison, dict)
        and comparison.get("status") in ("ahead", "diverged")
        and type(comparison.get("ahead_by")) is int
        and comparison["ahead_by"] > 0
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) == 2 and github_has_update(sys.argv[1]):
            print(NOTICE)
    except (OSError, ValueError):
        pass
