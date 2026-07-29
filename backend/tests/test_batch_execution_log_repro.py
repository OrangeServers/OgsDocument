"""Regression reproducer for missing multi-host execution audit rows."""
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("operation", ["command", "script"])
def test_completed_multi_host_operation_persists_execution_log(
    monkeypatch,
    operation,
):
    """A successful batch must remain visible even on an upgraded legacy DB.

    The deployed database still has ``t_command_log.log_host NOT NULL``.
    Audit writes are intentionally isolated from the main operation, so a NULL
    aggregate host makes the write disappear while execution still succeeds.
    """
    from app.assets import batch_service
    from app.tools import audlog

    hosts = [
        SimpleNamespace(
            id=1,
            alias="host-a",
            host_ip="192.0.2.11",
            host_port=22,
            group="production",
        ),
        SimpleNamespace(
            id=2,
            alias="host-b",
            host_ip="192.0.2.12",
            host_port=22,
            group="production",
        ),
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

    persisted = []

    def legacy_schema_insert(table, **values):
        if table == "t_command_log" and values.get("log_host") is None:
            raise RuntimeError("Column 'log_host' cannot be null")
        persisted.append((table, values))

    monkeypatch.setattr(audlog, "osql_in", legacy_schema_insert)

    class Connection:
        last_command_error = None

        def put_fileobj(self, _fileobj, _remote_path):
            return None

        def ssh_cmd(self, command, audit_callback=None):
            return "" if command.startswith("rm -f -- ") else "ok"

        def close(self):
            return None

    connect = lambda *_args: Connection()
    if operation == "command":
        result = batch_service.execute_batch_command(
            username="admin",
            role="admin",
            host_ids=[1, 2],
            sys_user="ops",
            command="df -h",
            connection_factory=connect,
        )
    else:
        result = batch_service.execute_batch_script(
            username="admin",
            role="admin",
            host_ids=[1, 2],
            sys_user="ops",
            filename="check.sh",
            script_bytes=b"echo ok\n",
            connection_factory=connect,
        )

    assert result["outcome"] == "success"
    command_logs = [values for table, values in persisted if table == "t_command_log"]
    assert len(command_logs) == 2, "each completed target must remain visible in execution logs"
    assert [row["log_host"] for row in command_logs] == ["host-a", "host-b"]
    assert all(row["log_status"] == "成功" for row in command_logs)
