import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_fake_python(path: Path) -> None:
    path.write_text(
        f"""#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["-c"]:
    raise SystemExit(0)
if args[:2] == ["-m", "venv"]:
    bin_dir = Path(args[2]) / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(__file__, bin_dir / "python")
    for name in ("ugnas", "cli-anything-ugreen-nas", "nas-kb"):
        command = bin_dir / name
        command.write_text("#!/usr/bin/env bash\\nexit 0\\n")
        command.chmod(0o755)
    raise SystemExit(0)
if args[:2] == ["-m", "pip"]:
    raise SystemExit(0)
raise SystemExit(subprocess.call([{sys.executable!r}, *args]))
"""
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.mark.parametrize(
    ("script", "skill", "install_home_var", "bin_dir_var"),
    [
        (
            "agent-harness/scripts/install.sh",
            "cli-anything-ugreen-nas",
            "UGNAS_INSTALL_HOME",
            "UGNAS_BIN_DIR",
        ),
        (
            "nas-kb/scripts/install.sh",
            "nas-knowledge-base",
            "NAS_KB_INSTALL_HOME",
            "NAS_KB_BIN_DIR",
        ),
    ],
)
def test_installer_registers_matching_codex_skill(
    tmp_path: Path,
    script: str,
    skill: str,
    install_home_var: str,
    bin_dir_var: str,
) -> None:
    fake_python = tmp_path / "fake-python"
    _write_fake_python(fake_python)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "CODEX_HOME": str(tmp_path / "codex"),
            "PYTHON": str(fake_python),
            install_home_var: str(tmp_path / "install"),
            bin_dir_var: str(tmp_path / "bin"),
        }
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / script)],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    installed_skill = tmp_path / "codex" / "skills" / skill
    assert (installed_skill / "SKILL.md").read_bytes() == (
        REPO_ROOT / "skills" / skill / "SKILL.md"
    ).read_bytes()
    assert (installed_skill / "agents" / "openai.yaml").is_file()
    assert f"Installed Codex skill {skill}" in result.stdout
