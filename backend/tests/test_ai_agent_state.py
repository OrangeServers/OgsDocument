"""AI Agent 会话状态与上下文压缩的行为测试。

测试缝隙：
1. AgentStore 是 Redis 会话/结果集/Action 的公开存储接口。
2. ContextManager 是 Runner 调用的上下文压缩接口。
"""
from __future__ import annotations

import fnmatch
import time


class FakeRedis:
    """覆盖 AgentStore 使用到的最小 redis-py 行为。"""

    def __init__(self):
        self.values = {}
        self.zsets = {}
        self.sets = {}
        self.ttls = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ex
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            deleted += int(key in self.values or key in self.zsets or key in self.sets)
            self.values.pop(key, None)
            self.zsets.pop(key, None)
            self.sets.pop(key, None)
            self.ttls.pop(key, None)
        return deleted

    def expire(self, key, ttl):
        exists = key in self.values or key in self.zsets or key in self.sets
        if exists:
            self.ttls[key] = ttl
        return exists

    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    def zcard(self, key):
        return len(self.zsets.get(key, {}))

    def zrange(self, key, start, end):
        rows = sorted(self.zsets.get(key, {}).items(), key=lambda row: row[1])
        if end == -1:
            end = len(rows) - 1
        return [item[0] for item in rows[start:end + 1]]

    def zrevrange(self, key, start, end):
        rows = sorted(self.zsets.get(key, {}).items(), key=lambda row: row[1], reverse=True)
        if end == -1:
            end = len(rows) - 1
        return [item[0] for item in rows[start:end + 1]]

    def zrem(self, key, *members):
        target = self.zsets.get(key, {})
        for member in members:
            target.pop(member, None)

    def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(members)

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def srem(self, key, *members):
        target = self.sets.get(key, set())
        for member in members:
            target.discard(member)

    def scan_iter(self, match):
        for key in list(self.values) + list(self.zsets) + list(self.sets):
            if fnmatch.fnmatch(key, match):
                yield key


def test_recent_conversations_keep_latest_twenty():
    from app.ai.storage import AgentStore

    clock = iter(range(100, 200))
    store = AgentStore(FakeRedis(), now=lambda: float(next(clock)))

    created = [
        store.create_conversation("alice", provider_code="minimax", model="MiniMax-Test")
        for _ in range(21)
    ]

    recent = store.list_conversations("alice")
    assert len(recent) == 20
    assert recent[0]["id"] == created[-1]["id"]
    assert all(item["id"] != created[0]["id"] for item in recent)


def test_conversation_context_mode_defaults_to_standard_and_persists_deep_mode():
    from app.ai.context import DEEP_CONTEXT_MODE, STANDARD_CONTEXT_MODE
    from app.ai.storage import AgentStore

    store = AgentStore(FakeRedis())
    standard = store.create_conversation("alice", "minimax", "demo")
    deep = store.create_conversation(
        "alice",
        "siliconflow",
        "demo",
        context_mode=DEEP_CONTEXT_MODE,
    )

    assert standard["context_mode"] == STANDARD_CONTEXT_MODE
    assert store.get_conversation("alice", deep["id"])["context_mode"] == DEEP_CONTEXT_MODE
    listed = {row["id"]: row for row in store.list_conversations("alice")}
    assert listed[deep["id"]]["context_mode"] == DEEP_CONTEXT_MODE


def test_deleting_conversation_invalidates_results_and_pending_actions():
    from app.ai.storage import AgentStore, AgentStoreNotFound

    redis = FakeRedis()
    store = AgentStore(redis)
    conversation = store.create_conversation("alice", "siliconflow", "demo-model")
    result = store.create_result_set(
        "alice", conversation["id"], "assets",
        rows=[{"id": 1, "alias": "web-01"}],
        resource_ids=[1],
    )
    action = store.create_action(
        "alice", conversation["id"], result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )

    store.delete_conversation("alice", conversation["id"])

    for getter, args in (
        (store.get_conversation, ("alice", conversation["id"])),
        (store.get_result_set, ("alice", result["id"])),
        (store.get_action, ("alice", action["id"])),
    ):
        try:
            getter(*args)
        except AgentStoreNotFound:
            pass
        else:
            raise AssertionError("deleted conversation descendants must be invalidated")


def test_action_can_only_be_claimed_once_by_its_owner():
    from app.ai.storage import AgentStore, AgentStoreConflict, AgentStoreNotFound

    store = AgentStore(FakeRedis())
    conversation = store.create_conversation("alice", "minimax", "demo")
    result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[1]
    )
    action = store.create_action(
        "alice", conversation["id"], result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )

    try:
        store.claim_action("bob", action["id"])
    except AgentStoreNotFound:
        pass
    else:
        raise AssertionError("another user must not observe or claim an action")

    claimed = store.claim_action("alice", action["id"])
    assert claimed["status"] == "running"
    assert store.redis.ttls[store._action_key(action["id"])] >= 60 * 60

    try:
        store.claim_action("alice", action["id"])
    except AgentStoreConflict:
        pass
    else:
        raise AssertionError("an action must not execute twice")


def test_listing_conversations_prunes_missing_pending_actions():
    from app.ai.storage import AgentStore

    redis = FakeRedis()
    store = AgentStore(redis)
    conversation = store.create_conversation("alice", "minimax", "demo")
    result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[1]
    )
    action = store.create_action(
        "alice", conversation["id"], result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )
    redis.delete(store._action_key(action["id"]))

    [listed] = store.list_conversations("alice")

    assert listed["has_pending_action"] is False
    assert listed["pending_action_ids"] == []
    assert store.get_conversation("alice", conversation["id"])["pending_action_ids"] == []


def test_listing_conversations_expires_stale_pending_actions():
    from app.ai.storage import AgentStore

    redis = FakeRedis()
    current_time = [100.0]
    store = AgentStore(redis, now=lambda: current_time[0], action_ttl=10)
    conversation = store.create_conversation("alice", "minimax", "demo")
    result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[1]
    )
    action = store.create_action(
        "alice", conversation["id"], result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )
    current_time[0] = 111.0

    [listed] = store.list_conversations("alice")

    assert listed["has_pending_action"] is False
    assert listed["pending_action_ids"] == []
    assert store.get_action("alice", action["id"])["status"] == "expired"


def test_cleanup_can_remove_conversation_with_missing_pending_action():
    from app.ai.storage import AgentStore, AgentStoreNotFound

    redis = FakeRedis()
    current_time = [100.0]
    store = AgentStore(
        redis,
        now=lambda: current_time[0],
        max_conversations=1,
    )
    old_conversation = store.create_conversation("alice", "minimax", "old")
    result = store.create_result_set(
        "alice", old_conversation["id"], "assets", rows=[], resource_ids=[1]
    )
    action = store.create_action(
        "alice", old_conversation["id"], result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )
    redis.delete(store._action_key(action["id"]))
    current_time[0] = 200.0

    new_conversation = store.create_conversation("alice", "minimax", "new")

    try:
        store.get_conversation("alice", old_conversation["id"])
    except AgentStoreNotFound:
        pass
    else:
        raise AssertionError("a missing action must not protect an old conversation")
    assert [row["id"] for row in store.list_conversations("alice")] == [
        new_conversation["id"]
    ]


def test_conversation_rejects_a_second_live_action():
    from app.ai.storage import AgentStore, AgentStoreConflict

    store = AgentStore(FakeRedis())
    conversation = store.create_conversation("alice", "minimax", "demo")
    first_result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[1]
    )
    second_result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[2]
    )
    first_action = store.create_action(
        "alice", conversation["id"], first_result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )

    try:
        store.create_action(
            "alice", conversation["id"], second_result["id"],
            sys_user="ops", command="free -m", reason="巡检",
        )
    except AgentStoreConflict:
        pass
    else:
        raise AssertionError("one conversation must not have two live actions")

    refreshed = store.get_conversation("alice", conversation["id"])
    assert refreshed["pending_action_ids"] == [first_action["id"]]


def test_expired_action_does_not_block_a_replacement():
    from app.ai.storage import AgentStore

    current_time = [100.0]
    store = AgentStore(
        FakeRedis(),
        now=lambda: current_time[0],
        action_ttl=10,
    )
    conversation = store.create_conversation("alice", "minimax", "demo")
    first_result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[1]
    )
    second_result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[2]
    )
    expired_action = store.create_action(
        "alice", conversation["id"], first_result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )
    current_time[0] = 111.0

    replacement = store.create_action(
        "alice", conversation["id"], second_result["id"],
        sys_user="ops", command="free -m", reason="巡检",
    )

    refreshed = store.get_conversation("alice", conversation["id"])
    assert refreshed["pending_action_ids"] == [replacement["id"]]
    assert refreshed["action_ids"] == [expired_action["id"], replacement["id"]]
    assert store.get_action("alice", expired_action["id"])["status"] == "expired"


def test_cancel_and_approve_share_one_action_lock():
    from app.ai.storage import AgentStore, AgentStoreConflict

    redis = FakeRedis()
    store = AgentStore(redis)
    conversation = store.create_conversation("alice", "minimax", "demo")
    result = store.create_result_set(
        "alice", conversation["id"], "assets", rows=[], resource_ids=[1]
    )
    action = store.create_action(
        "alice", conversation["id"], result["id"],
        sys_user="ops", command="df -h", reason="巡检",
    )
    lock_key = store._action_lock_key(action["id"])
    redis.set(lock_key, "approver", ex=30, nx=True)

    try:
        store.cancel_action("alice", action["id"])
    except AgentStoreConflict:
        pass
    else:
        raise AssertionError("cancel must not race an approval claim")

    redis.delete(lock_key)
    store.claim_action("alice", action["id"])
    try:
        store.cancel_action("alice", action["id"])
    except AgentStoreConflict:
        pass
    else:
        raise AssertionError("running action must not be cancelled")


def test_conversation_run_lock_blocks_parallel_runs_and_releases_by_token():
    from app.ai.storage import AgentStore, AgentStoreConflict

    store = AgentStore(FakeRedis())
    conversation = store.create_conversation("alice", "minimax", "demo")
    token = store.acquire_run_lock("alice", conversation["id"])

    try:
        store.acquire_run_lock("alice", conversation["id"])
    except AgentStoreConflict:
        pass
    else:
        raise AssertionError("parallel runs in one conversation must be rejected")

    store.release_run_lock("alice", conversation["id"], "wrong-token")
    try:
        store.acquire_run_lock("alice", conversation["id"])
    except AgentStoreConflict:
        pass
    else:
        raise AssertionError("another token must not release the run lock")

    store.release_run_lock("alice", conversation["id"], token)
    assert store.acquire_run_lock("alice", conversation["id"])


def test_context_compression_keeps_last_four_rounds_and_structured_state():
    from app.ai.context import ContextManager

    messages = []
    for index in range(7):
        messages.extend([
            {"role": "user", "content": f"request-{index}-" + ("x" * 40)},
            {"role": "assistant", "content": f"answer-{index}-" + ("y" * 40)},
        ])
    conversation = {
        "messages": messages,
        "summary": "",
        "state": {"last_result_set_id": "result-123"},
        "pending_action_ids": [],
    }
    captured = {}

    def summarize(old_messages, previous_summary):
        captured["old"] = old_messages
        captured["previous"] = previous_summary
        return "前面三轮请求已经完成。"

    manager = ContextManager(context_window=80, threshold_ratio=0.5, keep_rounds=4)
    compressed = manager.compress(conversation, summarize)

    assert compressed["summary"] == "前面三轮请求已经完成。"
    assert compressed["messages"][0]["content"].startswith("request-3-")
    assert len(compressed["messages"]) == 8
    assert compressed["state"] == {"last_result_set_id": "result-123"}
    assert len(captured["old"]) == 6


def test_context_policy_defaults_to_256k_and_only_enables_deep_with_1m_capability():
    from app.ai.context import (
        DEEP_CONTEXT_MODE,
        DEEP_CONTEXT_TOKENS,
        STANDARD_CONTEXT_MODE,
        STANDARD_CONTEXT_TOKENS,
        resolve_context_window,
    )

    assert resolve_context_window(None, STANDARD_CONTEXT_TOKENS) == STANDARD_CONTEXT_TOKENS
    assert (
        resolve_context_window(STANDARD_CONTEXT_MODE, DEEP_CONTEXT_TOKENS)
        == STANDARD_CONTEXT_TOKENS
    )
    assert (
        resolve_context_window(DEEP_CONTEXT_MODE, DEEP_CONTEXT_TOKENS)
        == DEEP_CONTEXT_TOKENS
    )

    for mode, capability in (
        (DEEP_CONTEXT_MODE, STANDARD_CONTEXT_TOKENS),
        ("unsupported", DEEP_CONTEXT_TOKENS),
    ):
        try:
            resolve_context_window(mode, capability)
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported context mode/capability must fail closed")


def test_context_manager_default_window_is_256k():
    from app.ai.context import ContextManager, STANDARD_CONTEXT_TOKENS

    assert ContextManager().context_window == STANDARD_CONTEXT_TOKENS


def test_context_does_not_compress_while_approval_is_pending():
    from app.ai.context import ContextManager

    conversation = {
        "messages": [
            {"role": "user", "content": "x" * 500},
            {"role": "assistant", "content": "y" * 500},
        ],
        "summary": "",
        "state": {},
        "pending_action_ids": ["action-1"],
    }
    manager = ContextManager(context_window=10, threshold_ratio=0.5)

    untouched = manager.compress(
        conversation,
        lambda *_: (_ for _ in ()).throw(AssertionError("must not summarize")),
    )

    assert untouched == conversation


def test_context_compression_keeps_history_when_summary_fails():
    from app.ai.context import ContextManager

    messages = []
    for index in range(7):
        messages.extend([
            {"role": "user", "content": f"request-{index}-" + ("x" * 40)},
            {"role": "assistant", "content": f"answer-{index}-" + ("y" * 40)},
        ])
    conversation = {
        "messages": messages,
        "summary": "previous summary",
        "state": {"last_result_set_id": "result-123"},
        "pending_action_ids": [],
    }
    manager = ContextManager(context_window=80, threshold_ratio=0.5, keep_rounds=4)

    untouched = manager.compress(
        conversation,
        lambda *_: (_ for _ in ()).throw(TimeoutError("provider timeout")),
    )

    assert untouched == conversation


def test_context_compression_keeps_history_when_summary_is_empty():
    from app.ai.context import ContextManager

    messages = []
    for index in range(7):
        messages.extend([
            {"role": "user", "content": f"request-{index}-" + ("x" * 40)},
            {"role": "assistant", "content": f"answer-{index}-" + ("y" * 40)},
        ])
    conversation = {
        "messages": messages,
        "summary": "",
        "state": {"last_result_set_id": "result-123"},
        "pending_action_ids": [],
    }
    manager = ContextManager(context_window=80, threshold_ratio=0.5, keep_rounds=4)

    untouched = manager.compress(conversation, lambda *_: "  ")

    assert untouched == conversation
