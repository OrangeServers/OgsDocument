"""AI action -> command audit navigation contract."""
from __future__ import annotations

from types import SimpleNamespace


VALID_REF = "{}{}".format("c" * 32 + "/", "a" * 32)


class _Column:
    def __init__(self, name):
        self.name = name

    def __eq__(self, value):
        return ("eq", self.name, value)

    def contains(self, value, **kwargs):
        return ("contains", self.name, value, kwargs)

    def desc(self):
        return ("desc", self.name)


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def order_by(self, *_columns):
        return self

    def offset(self, _offset):
        return self

    def limit(self, _limit):
        return self

    def all(self):
        return self.rows

    def count(self):
        return len(self.rows)


def _request_values(monkeypatch, module, values):
    monkeypatch.setattr(
        module,
        "request_param",
        lambda name, default=None: values.get(name, default),
    )


def test_logs_meta_accepts_only_command_uuid_pair(monkeypatch):
    from app.audit import loginlogs

    _request_values(
        monkeypatch,
        loginlogs,
        {"log_type": "command", "audit_ref": VALID_REF, "page": "1", "limit": "10"},
    )
    valid = loginlogs.LogsMeta()
    assert valid.audit_ref == VALID_REF
    assert valid.invalid_audit_ref is False

    _request_values(
        monkeypatch,
        loginlogs,
        {"log_type": "command", "audit_ref": "bad%_ref", "page": "1", "limit": "10"},
    )
    invalid = loginlogs.LogsMeta()
    assert invalid.audit_ref is None
    assert invalid.invalid_audit_ref is True

    _request_values(
        monkeypatch,
        loginlogs,
        {"log_type": "login", "audit_ref": VALID_REF, "page": "1", "limit": "10"},
    )
    wrong_log = loginlogs.LogsMeta()
    assert wrong_log.audit_ref is None
    assert wrong_log.invalid_audit_ref is True


def test_command_log_list_filters_by_ai_type_and_exact_ref(monkeypatch):
    from app.audit import loginlogs

    query = _Query([SimpleNamespace(id=1, log_time="2026-07-24 12:00:00")])
    command_table = SimpleNamespace(
        query=query,
        log_type=_Column("log_type"),
        log_reason=_Column("log_reason"),
        log_time=_Column("log_time"),
    )
    monkeypatch.setattr(loginlogs, "t_command_log", command_table)
    monkeypatch.setattr(loginlogs, "jsonify", lambda payload: payload)

    service = loginlogs.LogList.__new__(loginlogs.LogList)
    service.table = command_table
    service.table_offset = 0
    service.table_limit = 10
    service.audit_ref = VALID_REF
    service.invalid_audit_ref = False
    service.lt = SimpleNamespace(time_ls_dict_que=lambda rows, *_args: rows)

    payload = service.get_logs()

    assert payload["code"] == 0
    assert payload["log_len_msg"] == 1
    assert ("eq", "log_type", "AI 批量命令") in query.filters
    assert (
        "contains",
        "log_reason",
        "ref={}".format(VALID_REF),
        {"autoescape": True},
    ) in query.filters


def test_invalid_audit_ref_returns_empty_instead_of_all_logs(monkeypatch):
    from app.audit import loginlogs

    monkeypatch.setattr(
        loginlogs,
        "api_response",
        lambda **payload: ({"code": 0, "msg": "ok", **payload}, 200),
    )
    service = loginlogs.LogList.__new__(loginlogs.LogList)
    service.invalid_audit_ref = True

    payload = service.get_logs()

    assert payload["code"] == 0
    assert payload["log_list_msg"] == []
    assert payload["log_len_msg"] == 0


def test_command_log_writer_preserves_null_aggregate_host(monkeypatch):
    from app.tools import audlog

    written = []
    monkeypatch.setattr(
        audlog,
        "safe_db_write",
        lambda writer, **_kwargs: writer(),
    )
    monkeypatch.setattr(
        audlog,
        "osql_in",
        lambda table, **values: written.append((table, values)),
    )

    logger = audlog.ComToolsLog.__new__(audlog.ComToolsLog)
    logger.host_log(
        "alice",
        "AI 批量命令",
        "df -h",
        None,
        "成功",
        "targets=2",
    )

    assert written[0][0] == "t_command_log"
    assert written[0][1]["log_host"] is None
