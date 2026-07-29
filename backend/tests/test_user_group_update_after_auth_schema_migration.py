from unittest.mock import MagicMock

from flask import Flask


def test_user_group_remarks_update_does_not_read_removed_csv_column(monkeypatch):
    """授权迁移到关联表后，同名更新不能再访问 t_auth_host.user_group。"""
    from app.users import group as group_module

    old_group = MagicMock(id=7, name="qa_group")
    group_query = MagicMock()
    group_query.filter_by.return_value.first.return_value = old_group
    group_query.filter_by.return_value.update.return_value = 1

    user_query = MagicMock()
    user_query.filter_by.return_value.all.return_value = []

    monkeypatch.setattr(
        group_module,
        "t_acc_group",
        MagicMock(query=group_query),
    )
    monkeypatch.setattr(
        group_module,
        "t_acc_user",
        MagicMock(query=user_query),
    )
    monkeypatch.setattr(group_module.db, "session", MagicMock())
    monkeypatch.setattr(group_module, "AuthAutoUpdate", MagicMock())
    monkeypatch.setattr(
        group_module,
        "get_current_user",
        lambda: (MagicMock(), "admin"),
    )
    monkeypatch.setattr(
        "app.users.user.get_current_user_role",
        lambda: "admin",
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/account/group/update",
        method="POST",
        json={
            "id": 7,
            "name": "qa_group",
            "remarks": "updated",
        },
    ):
        response = group_module.AccGroupUpdate().update

    assert response.get_json() == {"code": 0}
