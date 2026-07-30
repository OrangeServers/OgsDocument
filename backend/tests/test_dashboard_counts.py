from app.local import Basics


class _QueryStub:
    def __init__(self, *, total: int, active: int):
        self._total = total
        self._active = active

    def count(self) -> int:
        return self._total

    def filter_by(self, **kwargs):
        assert kwargs == {"is_deleted": False}
        return _CountStub(self._active)


class _CountStub:
    def __init__(self, value: int):
        self._value = value

    def count(self) -> int:
        return self._value


class _ModelStub:
    def __init__(self, *, total: int, active: int):
        self.query = _QueryStub(total=total, active=active)


def test_dashboard_counts_exclude_soft_deleted_rows(monkeypatch):
    monkeypatch.setattr(Basics, "t_host", _ModelStub(total=5, active=0))
    monkeypatch.setattr(Basics, "t_acc_user", _ModelStub(total=3, active=2))
    monkeypatch.setattr(Basics, "t_group", _ModelStub(total=5, active=0))
    monkeypatch.setattr(Basics, "jsonify", lambda payload: payload)

    response = Basics.CountList().server_count_all

    assert response == {
        "code": 0,
        "host_len": 0,
        "user_len": 2,
        "group_len": 0,
    }
