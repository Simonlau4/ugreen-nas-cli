from __future__ import annotations

import os
import shlex
import stat
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path("~/.config/ugreen-nas-cli/config.toml").expanduser()
DEFAULT_AUDIT_LOG = Path("~/.local/state/ugreen-nas-cli/audit.log").expanduser()


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    base_url: str
    username: str
    password: str
    allowed_roots: tuple[str, ...]
    audit_log: Path | None
    verify_tls: bool
    timeout: float


def _truthy(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"invalid boolean value: {value!r}")


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _split_roots(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    roots = tuple(part.strip() for part in value.split(":") if part.strip())
    return roots or None


def _password_from_command(command: str) -> str:
    if not command.strip():
        raise ConfigError("password_command is empty")
    result = subprocess.run(
        command,
        shell=True,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ConfigError(f"password_command failed: {detail}")
    password = result.stdout.strip()
    if not password:
        raise ConfigError("password_command returned an empty password")
    return password


def load_profile(name: str, config_path: Path | None = None, timeout: float | None = None) -> Profile:
    config_path = config_path or DEFAULT_CONFIG_PATH
    raw = _load_toml(config_path)
    profile_data = raw.get("profile", {}).get(name, {})

    base_url = os.environ.get("UGREEN_NAS_BASE_URL") or profile_data.get("base_url")
    username = os.environ.get("UGREEN_NAS_USERNAME") or profile_data.get("username")
    password = os.environ.get("UGREEN_NAS_PASSWORD")
    password_command = os.environ.get("UGREEN_NAS_PASSWORD_COMMAND") or profile_data.get(
        "password_command"
    )
    allowed_roots = _split_roots(os.environ.get("UGREEN_NAS_ALLOWED_ROOTS"))
    if allowed_roots is None:
        allowed_roots = tuple(profile_data.get("allowed_roots") or ["/"])

    insecure_env = _truthy(os.environ.get("UGREEN_NAS_INSECURE"))
    verify_tls = bool(profile_data.get("verify_tls", True))
    if insecure_env is not None:
        verify_tls = not insecure_env

    audit_log_raw = os.environ.get("UGREEN_NAS_AUDIT_LOG") or profile_data.get("audit_log")
    audit_log = Path(audit_log_raw).expanduser() if audit_log_raw else DEFAULT_AUDIT_LOG

    if not base_url:
        raise ConfigError("missing base_url; set UGREEN_NAS_BASE_URL or run profile-init")
    if not username:
        raise ConfigError("missing username; set UGREEN_NAS_USERNAME or run profile-init")
    if password is None and password_command:
        password = _password_from_command(password_command)
    if password is None:
        raise ConfigError(
            "missing password; set UGREEN_NAS_PASSWORD or configure password_command"
        )

    resolved_timeout = timeout
    if resolved_timeout is None:
        resolved_timeout = float(os.environ.get("UGREEN_NAS_TIMEOUT") or profile_data.get("timeout", 30))

    return Profile(
        name=name,
        base_url=str(base_url).rstrip("/"),
        username=str(username),
        password=str(password),
        allowed_roots=tuple(str(root) for root in allowed_roots),
        audit_log=audit_log,
        verify_tls=verify_tls,
        timeout=float(resolved_timeout),
    )


def write_profile(
    name: str,
    base_url: str,
    username: str,
    allowed_roots: list[str],
    password_command: str | None,
    verify_tls: bool,
    config_path: Path | None = None,
) -> Path:
    config_path = config_path or DEFAULT_CONFIG_PATH
    existing = _load_toml(config_path)
    profiles = dict(existing.get("profile", {}))
    profiles[name] = {
        "base_url": base_url.rstrip("/"),
        "username": username,
        "allowed_roots": allowed_roots or ["/"],
        "verify_tls": verify_tls,
        "audit_log": str(DEFAULT_AUDIT_LOG),
    }
    if password_command:
        profiles[name]["password_command"] = password_command

    lines = [
        "# UGREEN NAS CLI config. Do not store plaintext passwords here.",
        "",
    ]
    for profile_name, values in sorted(profiles.items()):
        lines.append(f"[profile.{profile_name}]")
        for key in ("base_url", "username", "password_command", "audit_log"):
            if key in values and values[key] is not None:
                lines.append(f'{key} = "{_escape_toml(str(values[key]))}"')
        roots = values.get("allowed_roots") or ["/"]
        encoded_roots = ", ".join(f'"{_escape_toml(str(root))}"' for root in roots)
        lines.append(f"allowed_roots = [{encoded_roots}]")
        lines.append(f"verify_tls = {'true' if values.get('verify_tls', True) else 'false'}")
        if "timeout" in values:
            lines.append(f"timeout = {float(values['timeout'])}")
        lines.append("")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(config_path, stat.S_IRUSR | stat.S_IWUSR)
    return config_path


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def macos_keychain_password_command(service: str, account: str) -> str:
    return " ".join(
        shlex.quote(part)
        for part in [
            "security",
            "find-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
        ]
    )
