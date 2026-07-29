from types import SimpleNamespace
from unittest.mock import Mock

from app.app_factory import app
from app.assets import ServerManagement as server_management


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _HostQuery:
    def __init__(self, deleted_row):
        self.deleted_row = deleted_row

    def filter_by(self, **kwargs):
        if kwargs.get("is_deleted") is False:
            return _Result(None)
        if kwargs.get("is_deleted") is True:
            if kwargs.get("alias") == self.deleted_row.alias:
                return _Result(self.deleted_row)
            if kwargs.get("host_ip") == self.deleted_row.host_ip:
                return _Result(self.deleted_row)
            return _Result(None)
        if kwargs.get("host_ip") == self.deleted_row.host_ip:
            return _Result(self.deleted_row)
        return _Result(None)


def test_host_add_reactivates_matching_soft_deleted_asset(monkeypatch):
    deleted = SimpleNamespace(
        alias="qa-host",
        host_ip="192.0.2.197",
        host_port=2200,
        group="old",
        is_deleted=True,
    )
    host_model = SimpleNamespace(query=_HostQuery(deleted))
    commit = Mock()
    insert = Mock()

    monkeypatch.setattr(server_management, "t_host", host_model)
    monkeypatch.setattr(
        server_management,
        "db",
        SimpleNamespace(session=SimpleNamespace(commit=commit)),
    )
    monkeypatch.setattr(server_management, "osql_in", insert)
    monkeypatch.setattr(
        server_management.AuthAutoUpdate,
        "host_grp_count",
        Mock(),
    )

    endpoint = object.__new__(server_management.ServerAdd)
    endpoint.alias = "qa-host"
    endpoint.host_ip = "192.0.2.197"
    endpoint.host_port = 22
    endpoint.group = "qa-group"
    endpoint.cz_name = "admin"
    endpoint.host_log = Mock()

    with app.test_request_context("/server/host/add", method="POST"):
        response = endpoint.host_add

    assert response.get_json()["code"] == 0
    assert deleted.alias == "qa-host"
    assert deleted.host_ip == "192.0.2.197"
    assert deleted.host_port == 22
    assert deleted.group == "qa-group"
    assert deleted.is_deleted is False
    commit.assert_called_once_with()
    insert.assert_not_called()


def test_host_add_with_new_alias_preserves_deleted_asset_audit_identity(
        monkeypatch):
    deleted = SimpleNamespace(
        alias="old-host",
        host_ip="192.0.2.197",
        host_port=22,
        group="old",
        is_deleted=True,
    )
    host_model = SimpleNamespace(query=_HostQuery(deleted))
    commit = Mock()
    insert = Mock()

    monkeypatch.setattr(server_management, "t_host", host_model)
    monkeypatch.setattr(
        server_management,
        "db",
        SimpleNamespace(session=SimpleNamespace(commit=commit)),
    )
    monkeypatch.setattr(server_management, "osql_in", insert)
    monkeypatch.setattr(
        server_management.AuthAutoUpdate,
        "host_grp_count",
        Mock(),
    )

    endpoint = object.__new__(server_management.ServerAdd)
    endpoint.alias = "new-host"
    endpoint.host_ip = "192.0.2.197"
    endpoint.host_port = 22
    endpoint.group = "qa-group"
    endpoint.cz_name = "admin"
    endpoint.host_log = Mock()

    with app.test_request_context("/server/host/add", method="POST"):
        response = endpoint.host_add

    assert response.get_json()["code"] == 0
    assert deleted.alias == "old-host"
    assert deleted.is_deleted is True
    commit.assert_not_called()
    insert.assert_called_once_with(
        "t_host",
        alias="new-host",
        host_ip="192.0.2.197",
        host_port=22,
        group="qa-group",
    )
