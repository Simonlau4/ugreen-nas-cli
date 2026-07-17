#!/usr/bin/env python3
"""Install one repository skill into Codex's skill discovery directory."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "skill",
        choices=sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()),
    )
    args = parser.parse_args()

    source = SKILLS_ROOT / args.skill
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    destination = codex_home / "skills" / args.skill

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)

    if not (destination / "SKILL.md").is_file():
        raise RuntimeError(f"Skill installation failed: {destination / 'SKILL.md'} is missing")

    print(f"Installed Codex skill {args.skill} to {destination}")
    print("Open a new Codex task to load the skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
