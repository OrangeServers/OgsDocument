"""Soft-deleted SSH resources must not remain usable through direct WebSockets."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / "app" / "ssh" / name).read_text(encoding="utf-8")


def _assert_active_lookup(source: str, model: str, alias_expression: str) -> None:
    pattern = (
        rf"{model}\.query\.filter_by\(\s*"
        rf"alias={alias_expression},\s*is_deleted=False\s*"
        rf"\)\.first\(\)"
    )
    assert re.search(pattern, source)


def test_webssh_only_resolves_active_hosts_and_system_users():
    source = _source("webssh.py")

    _assert_active_lookup(source, "t_host", "host_alias")
    _assert_active_lookup(source, "t_host", "hostname")
    _assert_active_lookup(source, "t_sys_user", "username")


def test_sftp_only_resolves_active_hosts_and_system_users():
    source = _source("sftp.py")

    _assert_active_lookup(source, "t_host", "host_alias")
    _assert_active_lookup(source, "t_host", "hostname")
    _assert_active_lookup(source, "t_sys_user", "username")
