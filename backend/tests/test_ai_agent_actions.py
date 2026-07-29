"""Pending Action 审批执行的公开行为测试。"""
from __future__ import annotations

from test_ai_agent_state import FakeRedis


class PermissionSnapshot:
    def __init__(self, valid=True, sys_users=None):
        self.valid = valid
        self.sys_users = set(sys_users or {"ops"})

    def validate_asset_ids(self, _asset_ids):
        return self.valid

    def authorized_system_user_aliases(self):
        return self.sys_users

    def validate_asset_sys_user_pair(self, _asset_ids, sys_user):
        return self.valid and sys_user in self.sys_users


def _pending_action():
    from app.ai.storage import AgentStore

    store = AgentStore(FakeRedis())
    conversation = store.create_conversation("alice", "minimax", "demo")
    result = store.create_result_set(
        "alice", conversation["id"], "assets",
        rows=[{"id": 1, "alias": "web-01"}], resource_ids=[1],
    )
    action = store.create_action(
        "alice", conversation["id"], result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )
    return store, action


def test_approval_revalidates_permissions_and_streams_progress():
    from app.ai.actions import ActionService

    store, action = _pending_action()
    progress = []

    def execute(**kwargs):
        kwargs["on_progress"]({"alias": "web-01", "status": "success"})
        return {
            "total": 1,
            "success": 1,
            "failed": 0,
            "items": [{"alias": "web-01", "status": "success"}],
        }

    service = ActionService(
        store=store,
        platform_factory=lambda owner, role: PermissionSnapshot(),
        batch_executor=execute,
        command_checker=lambda _command: None,
    )

    result = service.approve(
        "alice", "user", action["id"],
        remote_ip="127.0.0.1", user_agent="pytest",
        on_progress=progress.append,
    )

    assert progress == [{"alias": "web-01", "status": "success"}]
    assert result["status"] == "completed"
    assert result["result"]["success"] == 1
    assert store.get_action("alice", action["id"])["status"] == "completed"


def test_approval_fails_closed_when_permission_changes():
    from app.ai.actions import ActionService, ActionValidationError

    store, action = _pending_action()
    called = []
    service = ActionService(
        store=store,
        platform_factory=lambda owner, role: PermissionSnapshot(valid=False),
        batch_executor=lambda **kwargs: called.append(kwargs),
        command_checker=lambda _command: None,
    )

    try:
        service.approve("alice", "user", action["id"])
    except ActionValidationError:
        pass
    else:
        raise AssertionError("permission drift must block execution")

    assert called == []
    assert store.get_action("alice", action["id"])["status"] == "rejected"


def test_approval_rechecks_dangerous_command():
    from app.ai.actions import ActionService, ActionValidationError

    store, action = _pending_action()
    service = ActionService(
        store=store,
        platform_factory=lambda owner, role: PermissionSnapshot(),
        batch_executor=lambda **kwargs: None,
        command_checker=lambda _command: "blocked-now",
    )

    try:
        service.approve("alice", "user", action["id"])
    except ActionValidationError:
        pass
    else:
        raise AssertionError("dangerous command must be checked again at approval")

    assert store.get_action("alice", action["id"])["status"] == "rejected"


def test_approval_preserves_failed_outcome_and_marks_ai_audit_source():
    """执行器正常结束和主机执行成功是两个不同维度。"""
    from app.ai.actions import ActionService

    store, action = _pending_action()
    called = []

    def execute(**kwargs):
        called.append(kwargs)
        return {
            "total": 1,
            "success": 0,
            "failed": 1,
            "outcome": "failed",
            "status": "失败",
            "items": [{"alias": "web-01", "status": "failed", "error": "exit 1"}],
        }

    service = ActionService(
        store=store,
        platform_factory=lambda owner, role: PermissionSnapshot(),
        batch_executor=execute,
        command_checker=lambda _command: None,
    )

    result = service.approve("alice", "user", action["id"])

    assert result["status"] == "completed"
    assert result["result"]["outcome"] == "failed"
    assert called[0]["audit_source"] == "AI Agent"
    assert called[0]["audit_ref"].endswith("/" + action["id"])
    assert "remote_ip" not in called[0]
    assert "user_agent" not in called[0]
