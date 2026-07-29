"""Public endpoint contracts for batch command and batch script execution."""
from __future__ import annotations

import io
from types import SimpleNamespace

from flask import Flask


class _Column:
    def in_(self, _values):
        return self

    def is_(self, _value):
        return self

    def __eq__(self, _value):
        return self


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_conditions):
        return self

    def filter_by(self, **_values):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


def _table(rows, *columns):
    values = {
        "query": _Query(rows),
    }
    values.update({column: _Column() for column in columns})
    return SimpleNamespace(**values)


def test_command_endpoint_revalidates_asset_credential_pair(monkeypatch):
    from app.assets import ServerManagement, batch_service

    host = SimpleNamespace(
        id=7,
        alias="db-private",
        host_ip="192.0.2.7",
        host_port=22,
        group="private",
    )
    monkeypatch.setattr(
        ServerManagement,
        "t_host",
        _table([host], "id", "alias", "is_deleted"),
    )
    monkeypatch.setattr(
        batch_service,
        "t_host",
        _table([host], "id", "is_deleted"),
    )
    monkeypatch.setattr(
        batch_service,
        "t_sys_user",
        _table(
            [SimpleNamespace(alias="ops")],
            "alias",
            "is_deleted",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        batch_service,
        "t_acc_user",
        _table([SimpleNamespace(name="alice", group="dev")]),
        raising=False,
    )
    monkeypatch.setattr(
        batch_service,
        "t_auth_host",
        _table([SimpleNamespace(id=11)], "id", "is_deleted"),
        raising=False,
    )
    monkeypatch.setattr(
        batch_service,
        "t_auth_host_user",
        _table([SimpleNamespace(auth_id=11)]),
        raising=False,
    )
    monkeypatch.setattr(
        batch_service,
        "t_auth_host_user_group",
        _table([]),
        raising=False,
    )
    monkeypatch.setattr(
        batch_service,
        "t_auth_host_sys_user",
        _table(
            [SimpleNamespace(auth_id=11, sys_user_alias="ops")],
            "auth_id",
            "sys_user_alias",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        batch_service,
        "t_auth_host_host_group",
        _table(
            [SimpleNamespace(auth_id=11, group_name="production")],
            "auth_id",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user",
        lambda: (object(), "alice"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user_role",
        lambda: "user",
        raising=False,
    )
    monkeypatch.setattr(
        ServerManagement.ServerListCmd,
        "host_log",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        batch_service,
        "ComToolsLog",
        type("Log", (), {"host_log": lambda *_args, **_kwargs: None}),
    )
    connections = []

    def connect(*_args):
        connections.append(True)
        return SimpleNamespace(
            ssh_cmd=lambda *_args, **_kwargs: "should not run",
            close=lambda: None,
        )

    monkeypatch.setattr(ServerManagement, "get_ssh_connection", connect)
    app = Flask(__name__)
    with app.test_request_context(
        "/server/host_list_cmd",
        method="POST",
        json={
            "host_name": ["db-private"],
            "command": "df -h",
            "sys_user": "ops",
        },
    ):
        response = ServerManagement.ServerListCmd().sh_list_cmd

    assert response.get_json() == {
        "code": 100,
        "msg": "asset and system user permission denied",
    }
    assert connections == []


def test_command_endpoint_preserves_legacy_fields_and_adds_items(monkeypatch):
    from app.assets import ServerManagement, batch_service

    host = SimpleNamespace(
        id=9,
        alias="web-01",
        host_ip="192.0.2.9",
        host_port=22,
        group="production",
    )
    host_table = _table([host], "id", "alias", "is_deleted")
    monkeypatch.setattr(ServerManagement, "t_host", host_table)
    monkeypatch.setattr(batch_service, "t_host", host_table)
    monkeypatch.setattr(
        batch_service,
        "t_sys_user",
        _table([SimpleNamespace(alias="ops")], "alias", "is_deleted"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user",
        lambda: (object(), "alice"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user_role",
        lambda: "admin",
    )
    monkeypatch.setattr(
        batch_service,
        "ComToolsLog",
        type("Log", (), {"host_log": lambda *_args, **_kwargs: None}),
    )

    class Connection:
        def ssh_cmd(self, _command, audit_callback=None):
            return "disk ok"

        def close(self):
            return None

    monkeypatch.setattr(
        ServerManagement,
        "get_ssh_connection",
        lambda *_args: Connection(),
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/host_list_cmd",
        method="POST",
        json={
            "host_name": ["web-01"],
            "command": "df -h",
            "sys_user": "ops",
        },
    ):
        response = ServerManagement.ServerListCmd().sh_list_cmd

    assert response.get_json() == {
        "code": 0,
        "command_msg": ["disk ok"],
        "hostname_list": ["web-01"],
        "items": [
            {
                "alias": "web-01",
                "status": "success",
                "output": "disk ok",
                "error": "",
            }
        ],
    }


def test_command_endpoint_rejects_empty_targets(monkeypatch):
    from app.assets import ServerManagement

    monkeypatch.setattr(
        ServerManagement,
        "get_current_user",
        lambda: (object(), "alice"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user_role",
        lambda: "user",
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/host_list_cmd",
        method="POST",
        json={
            "host_name": [],
            "command": "df -h",
            "sys_user": "ops",
        },
    ):
        response = ServerManagement.ServerListCmd().sh_list_cmd

    assert response.get_json() == {
        "code": 100,
        "msg": "target hosts are required",
    }


def test_command_endpoint_rejects_audit_role_before_ssh(monkeypatch):
    from app.assets import ServerManagement

    host = SimpleNamespace(
        id=4,
        alias="web-01",
        host_ip="192.0.2.4",
        host_port=22,
        group="production",
    )
    monkeypatch.setattr(
        ServerManagement,
        "t_host",
        _table([host], "id", "alias", "is_deleted"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user",
        lambda: (object(), "auditor"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user_role",
        lambda: "audit",
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_ssh_connection",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("audit role must not reach SSH")
        ),
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/host_list_cmd",
        method="POST",
        json={
            "host_name": ["web-01"],
            "command": "df -h",
            "sys_user": "ops",
        },
    ):
        response = ServerManagement.ServerListCmd().sh_list_cmd

    assert response.get_json() == {
        "code": 100,
        "msg": "batch operation permission denied",
    }


def test_script_endpoint_rejects_missing_file_without_server_error(monkeypatch):
    from app.assets import ServerManagement

    app = Flask(__name__)
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user",
        lambda: (object(), "alice"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user_role",
        lambda: "admin",
        raising=False,
    )
    monkeypatch.setattr(
        ServerManagement.ServerScript,
        "host_log",
        lambda *_args, **_kwargs: None,
    )

    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "sh",
            "sys_user": "ops",
            "name_list": "web-01",
        },
    ):
        response = ServerManagement.ServerScript().sh_script()

    assert response.get_json() == {
        "code": 100,
        "msg": "script file is required",
    }


def _configure_admin_script_request(monkeypatch, ServerManagement, batch_service):
    host = SimpleNamespace(
        id=8,
        alias="web-01",
        host_ip="192.0.2.8",
        host_port=22,
        group="production",
    )
    host_table = _table([host], "id", "alias", "is_deleted")
    monkeypatch.setattr(ServerManagement, "t_host", host_table)
    monkeypatch.setattr(batch_service, "t_host", host_table)
    monkeypatch.setattr(
        batch_service,
        "t_sys_user",
        _table([SimpleNamespace(alias="ops")], "alias", "is_deleted"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user",
        lambda: (object(), "alice"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user_role",
        lambda: "admin",
    )
    monkeypatch.setattr(
        ServerManagement.ServerScript,
        "host_log",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        batch_service,
        "ComToolsLog",
        type("Log", (), {"host_log": lambda *_args, **_kwargs: None}),
    )
    return host


def test_script_endpoint_rejects_unsupported_extension_and_non_utf8(monkeypatch):
    from app.assets import ServerManagement, batch_service

    _configure_admin_script_request(
        monkeypatch,
        ServerManagement,
        batch_service,
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "sh",
            "sys_user": "ops",
            "name_list": "web-01",
            "file": (io.BytesIO(b"echo ok"), "check.ps1"),
        },
    ):
        unsupported = ServerManagement.ServerScript().sh_script()
    assert unsupported.get_json() == {
        "code": 100,
        "msg": "unsupported script type (allowed: .sh, .py)",
    }

    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "sh",
            "sys_user": "ops",
            "name_list": "web-01",
            "file": (io.BytesIO(b"\xff\xfe\x00"), "check.py"),
        },
    ):
        non_utf8 = ServerManagement.ServerScript().sh_script()
    assert non_utf8.get_json() == {
        "code": 100,
        "msg": "script must be UTF-8 text",
    }

    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "sh",
            "sys_user": "ops",
            "name_list": "web-01",
            "file": (io.BytesIO(b""), "empty.sh"),
        },
    ):
        empty = ServerManagement.ServerScript().sh_script()
    assert empty.get_json() == {
        "code": 100,
        "msg": "script file is empty",
    }

    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "sh",
            "sys_user": "ops",
            "name_list": "web-01",
            "file": (
                io.BytesIO(b"x" * (1024 * 1024 + 1)),
                "oversized.sh",
            ),
        },
    ):
        oversized = ServerManagement.ServerScript().sh_script()
    assert oversized.get_json() == {
        "code": 100,
        "msg": "script too large (max 1048576 bytes)",
    }


def test_script_endpoint_uses_fixed_interpreter_and_always_cleans_up(monkeypatch):
    from app.assets import ServerManagement, batch_service

    _configure_admin_script_request(
        monkeypatch,
        ServerManagement,
        batch_service,
    )
    uploaded = []
    commands = []

    class Connection:
        last_command_error = None

        def put_fileobj(self, fileobj, remote_path):
            uploaded.append((remote_path, fileobj.read()))

        def ssh_cmd(self, command, audit_callback=None):
            commands.append(command)
            if command.startswith("python3 "):
                return "healthy\n"
            return ""

        def close(self):
            return None

    monkeypatch.setattr(
        ServerManagement,
        "get_ssh_connection",
        lambda *_args: Connection(),
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "sh",
            "sys_user": "ops",
            "name_list": "web-01",
            "file": (
                io.BytesIO(b"print('healthy')\r\n"),
                "health.py",
            ),
        },
    ):
        response = ServerManagement.ServerScript().sh_script()

    payload = response.get_json()
    assert payload["code"] == 0
    assert payload["command_msg"] == ["healthy\n"]
    assert payload["hostname_list"] == ["web-01"]
    assert payload["items"] == [
        {
            "alias": "web-01",
            "status": "success",
            "output": "healthy\n",
            "error": "",
        }
    ]
    remote_path, content = uploaded[0]
    assert remote_path.startswith("/tmp/orangeserver-script-")
    assert remote_path.endswith(".py")
    assert content == b"print('healthy')\n"
    assert commands[0] == "python3 %s" % remote_path
    assert commands[-1] == "rm -f -- %s" % remote_path


def test_legacy_send_upload_is_preserved_without_execution(monkeypatch):
    from app.assets import ServerManagement, batch_service

    _configure_admin_script_request(
        monkeypatch,
        ServerManagement,
        batch_service,
    )
    uploaded = []

    class Connection:
        def put_fileobj(self, fileobj, remote_path):
            uploaded.append((remote_path, fileobj.read()))

        def close(self):
            return None

    monkeypatch.setattr(
        ServerManagement,
        "get_ssh_connection",
        lambda *_args: Connection(),
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "send",
            "sys_user": "ops",
            "name_list": "web-01",
            "file": (io.BytesIO(b"artifact-data"), "release.txt"),
        },
    ):
        response = ServerManagement.ServerScript().sh_script()

    payload = response.get_json()
    assert payload["code"] == 0
    assert payload["command_msg"] == ["上传成功"]
    assert payload["hostname_list"] == ["web-01"]
    assert uploaded == [("/tmp/release.txt", b"artifact-data")]


def test_legacy_send_keeps_single_message_and_upload_bin_fallback(monkeypatch):
    from app.assets import ServerManagement, batch_service

    hosts = [
        SimpleNamespace(
            id=index,
            alias=alias,
            host_ip="192.0.2.%d" % index,
            host_port=22,
            group="production",
        )
        for index, alias in ((1, "web-01"), (2, "web-02"))
    ]
    host_table = _table(hosts, "id", "alias", "is_deleted")
    monkeypatch.setattr(ServerManagement, "t_host", host_table)
    monkeypatch.setattr(batch_service, "t_host", host_table)
    monkeypatch.setattr(
        batch_service,
        "t_sys_user",
        _table([SimpleNamespace(alias="ops")], "alias", "is_deleted"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user",
        lambda: (object(), "admin"),
    )
    monkeypatch.setattr(
        ServerManagement,
        "get_current_user_role",
        lambda: "admin",
    )
    monkeypatch.setattr(
        batch_service,
        "ComToolsLog",
        type("Log", (), {"host_log": lambda *_args, **_kwargs: None}),
    )
    uploaded_paths = []

    class Connection:
        def put_fileobj(self, _fileobj, remote_path):
            uploaded_paths.append(remote_path)

        def close(self):
            return None

    monkeypatch.setattr(
        ServerManagement,
        "get_ssh_connection",
        lambda *_args: Connection(),
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "send",
            "sys_user": "ops",
            "name_list": ["web-01", "web-02"],
            "file": (io.BytesIO(b""), "测试"),
        },
    ):
        response = ServerManagement.ServerScript().sh_script()

    payload = response.get_json()
    assert payload["code"] == 0
    assert payload["command_msg"] == ["上传成功"]
    assert payload["hostname_list"] == ["web-01", "web-02"]
    assert uploaded_paths == ["/tmp/upload.bin", "/tmp/upload.bin"]


def test_script_cleanup_and_close_failures_do_not_hide_success(monkeypatch):
    from app.assets import ServerManagement, batch_service

    _configure_admin_script_request(
        monkeypatch,
        ServerManagement,
        batch_service,
    )

    class Connection:
        def put_fileobj(self, _fileobj, _remote_path):
            return None

        def ssh_cmd(self, command, audit_callback=None):
            if command.startswith("rm -f -- "):
                raise IOError("cleanup failed")
            return "ok"

        def close(self):
            raise IOError("close failed")

    monkeypatch.setattr(
        ServerManagement,
        "get_ssh_connection",
        lambda *_args: Connection(),
    )
    app = Flask(__name__)
    with app.test_request_context(
        "/server/file/put",
        method="POST",
        data={
            "put_type": "sh",
            "sys_user": "ops",
            "name_list": "web-01",
            "file": (io.BytesIO(b"echo ok"), "check.sh"),
        },
    ):
        response = ServerManagement.ServerScript().sh_script()

    payload = response.get_json()
    assert payload["code"] == 0
    assert payload["items"][0]["status"] == "success"
