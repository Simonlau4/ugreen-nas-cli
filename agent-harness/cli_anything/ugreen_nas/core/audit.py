from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_audit(path: Path | None, event: dict[str, Any]) -> None:
    if path is None:
        return

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    with expanded.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    try:
        os.chmod(expanded, 0o600)
    except OSError:
        pass
