"""AI 批量命令服务的结果与审计契约。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Column:
    def in_(self, _values):
        return self

    def is_(self, _value):
        return self


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_conditions):
        return self

    def all(self):
        return self.rows


def test_batch_execution_rejects_blank_command_before_connecting():
    from app.assets import batch_service

    with pytest.raises(
        batch_service.BatchCommandValidationError,
        match="command is required",
    ):
        batch_service.execute_batch_command(
            username="alice",
            host_ids=[1],
            sys_user="ops",
            command="   ",
            connection_factory=lambda *_args: pytest.fail(
                "blank command must not reach SSH"
            ),
        )


def test_batch_execution_writes_one_command_audit_per_target(monkeypatch):
    """批量执行按目标写日志，兼容旧库 log_host NOT NULL 与新库主机 FK。"""
    from app.assets import batch_service

    hosts = [
        SimpleNamespace(id=1, alias="web-01", host_ip="10.0.0.1", host_port=22),
        SimpleNamespace(id=2, alias="web-02", host_ip="10.0.0.2", host_port=22),
    ]
    monkeypatch.setattr(
        batch_service,
        "t_host",
        SimpleNamespace(
            id=_Column(),
            is_deleted=_Column(),
            query=_Query(hosts),
        ),
    )
    monkeypatch.setattr(batch_service, "_check_dangerous_command", lambda _cmd: None)

    command_audits = []
    operation_audits = []
    per_host_audits = []
    audit_callbacks = []

    class CommandLog:
        def host_log(self, *args, **kwargs):
            command_audits.append((args, kwargs))

    class OperationLog:
        def host_log(self, *args, **kwargs):
            operation_audits.append((args, kwargs))

    class Connection:
        def __init__(self, output):
            self.output = output
            self.last_command_error = (
                "exit code 7: permission denied" if output is None else None
            )

        def ssh_cmd(self, _command, audit_callback=None):
            audit_callbacks.append(audit_callback)
            if audit_callback is not None:
                audit_callback(
                    log_type="ssh_cmd",
                    log_info="df -h",
                    log_host="10.0.0.1",
                    log_status="success",
                    log_msg="ok",
                )
            return self.output

        def close(self):
            return None

    monkeypatch.setattr(batch_service, "ComToolsLog", CommandLog)
    monkeypatch.setattr(batch_service, "CzToolsLog", OperationLog, raising=False)
    monkeypatch.setattr(
        batch_service,
        "log_ssh_audit",
        lambda **values: per_host_audits.append(values),
        raising=False,
    )

    outputs = iter(["disk ok", None])
    audit_ref = "{}{}".format("c" * 32 + "/", "a" * 32)
    result = batch_service.execute_batch_command(
        username="alice",
        host_ids=[1, 2],
        sys_user="ops",
        command="df -h",
        audit_source="AI Agent",
        audit_ref=audit_ref,
        connection_factory=lambda *_args: Connection(next(outputs)),
    )

    assert result["outcome"] == "partial"
    assert result["status"] == "部分失败"
    assert [item["status"] for item in result["items"]] == ["success", "failed"]
    assert result["items"][1]["error"] == "exit code 7: permission denied"
    assert len(command_audits) == 2
    assert [args[3] for args, _kwargs in command_audits] == ["web-01", "web-02"]
    assert [args[4] for args, _kwargs in command_audits] == ["成功", "失败"]
    for audit_args, _audit_kwargs in command_audits:
        assert audit_args[1] == "AI 批量命令"
        assert "targets=2" in audit_args[5]
        assert "source=AI Agent" in audit_args[5]
        assert "ref={}".format(audit_ref) in audit_args[5]
    assert "exit code 7: permission denied" in command_audits[1][0][5]
    assert operation_audits == []
    assert per_host_audits == []
    assert audit_callbacks == [None, None]


def test_batch_script_writes_one_command_audit_per_target(monkeypatch):
    """脚本批量执行也必须按目标进入执行日志，不能写 NULL 聚合主机。"""
    from app.assets import batch_service

    hosts = [
        SimpleNamespace(id=1, alias="web-01", host_ip="10.0.0.1", host_port=22),
        SimpleNamespace(id=2, alias="web-02", host_ip="10.0.0.2", host_port=22),
    ]
    monkeypatch.setattr(
        batch_service,
        "validate_batch_targets",
        lambda **_kwargs: hosts,
    )
    monkeypatch.setattr(
        batch_service,
        "_check_dangerous_command",
        lambda _command: None,
    )
    command_audits = []

    class CommandLog:
        def host_log(self, *args, **kwargs):
            command_audits.append((args, kwargs))

    class Connection:
        def __init__(self, output):
            self.output = output
            self.last_command_error = (
                "python3 missing" if output is None else None
            )

        def put_fileobj(self, _stream, _remote_path):
            return None

        def ssh_cmd(self, command, audit_callback=None):
            if command.startswith("rm -f -- "):
                return ""
            return self.output

        def close(self):
            return None

    outputs = iter(["script ok", None])
    monkeypatch.setattr(batch_service, "ComToolsLog", CommandLog)

    result = batch_service.execute_batch_script(
        username="alice",
        role="admin",
        host_ids=[1, 2],
        sys_user="ops",
        filename="health.py",
        script_bytes=b"print('ok')\n",
        connection_factory=lambda *_args: Connection(next(outputs)),
    )

    assert result["outcome"] == "partial"
    assert len(command_audits) == 2
    assert [args[3] for args, _kwargs in command_audits] == ["web-01", "web-02"]
    assert [args[4] for args, _kwargs in command_audits] == ["成功", "失败"]
    assert "python3 missing" in command_audits[1][0][5]


def test_batch_execution_uses_exact_system_user_id_when_provided(monkeypatch):
    from app.assets import batch_service

    host = SimpleNamespace(
        id=1,
        alias="web-01",
        host_ip="10.0.0.1",
        host_port=22,
    )
    monkeypatch.setattr(
        batch_service,
        "t_host",
        SimpleNamespace(
            id=_Column(),
            is_deleted=_Column(),
            query=_Query([host]),
        ),
    )
    monkeypatch.setattr(
        batch_service,
        "_check_dangerous_command",
        lambda _cmd: None,
    )
    calls = []

    class Connection:
        def ssh_cmd(self, _command, audit_callback=None):
            assert audit_callback is None
            return "ok"

        def close(self):
            return None

    def connect(sys_user_id, host_ip, host_port):
        calls.append((sys_user_id, host_ip, host_port))
        return Connection()

    class CommandLog:
        def host_log(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(batch_service, "get_ssh_connection_by_id", connect)
    monkeypatch.setattr(batch_service, "ComToolsLog", CommandLog)

    result = batch_service.execute_batch_command(
        username="alice",
        host_ids=[1],
        sys_user="duplicate-alias",
        sys_user_id=19,
        command="df -h",
    )

    assert result["outcome"] == "success"
    assert calls == [(19, "10.0.0.1", 22)]
