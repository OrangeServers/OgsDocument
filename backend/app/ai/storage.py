"""Redis-backed ephemeral state for the OrangeServer Web AI Agent."""
from __future__ import annotations

import copy
import json
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.ai.context import normalize_context_mode


CONVERSATION_TTL_SECONDS = 7 * 24 * 60 * 60
ACTION_TTL_SECONDS = 10 * 60
ACTION_EXECUTION_TTL_SECONDS = 60 * 60
MAX_CONVERSATIONS_PER_USER = 20


class AgentStoreError(RuntimeError):
    pass


class AgentStoreNotFound(AgentStoreError):
    pass


class AgentStoreConflict(AgentStoreError):
    pass


class AgentStore:
    """Owns all Agent Redis keys and enforces owner-scoped access."""

    def __init__(
        self,
        redis_client: Any,
        *,
        now: Callable[[], float] = time.time,
        conversation_ttl: int = CONVERSATION_TTL_SECONDS,
        action_ttl: int = ACTION_TTL_SECONDS,
        action_execution_ttl: int = ACTION_EXECUTION_TTL_SECONDS,
        max_conversations: int = MAX_CONVERSATIONS_PER_USER,
    ):
        self.redis = redis_client
        self.now = now
        self.conversation_ttl = conversation_ttl
        self.action_ttl = action_ttl
        self.action_execution_ttl = action_execution_ttl
        self.max_conversations = max_conversations

    @staticmethod
    def _json(value: Dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _loads(value: Any) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    @staticmethod
    def _conversation_key(owner: str, conversation_id: str) -> str:
        return f"ai:conversation:{owner}:{conversation_id}"

    @staticmethod
    def _conversation_index(owner: str) -> str:
        return f"ai:conversation-index:{owner}"

    @staticmethod
    def _result_key(owner: str, result_id: str) -> str:
        return f"ai:result:{owner}:{result_id}"

    @staticmethod
    def _conversation_results(owner: str, conversation_id: str) -> str:
        return f"ai:conversation-results:{owner}:{conversation_id}"

    @staticmethod
    def _action_key(action_id: str) -> str:
        return f"ai:action:{action_id}"

    @staticmethod
    def _action_lock_key(action_id: str) -> str:
        return f"ai:action-lock:{action_id}"

    @staticmethod
    def _conversation_actions(owner: str, conversation_id: str) -> str:
        return f"ai:conversation-actions:{owner}:{conversation_id}"

    @staticmethod
    def _run_lock_key(owner: str, conversation_id: str) -> str:
        return f"ai:run-lock:{owner}:{conversation_id}"

    def create_conversation(
        self,
        owner: str,
        provider_code: str,
        model: str,
        *,
        title: str = "新会话",
        context_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        conversation_id = uuid.uuid4().hex
        now = self.now()
        conversation = {
            "id": conversation_id,
            "owner": owner,
            "title": title[:60] or "新会话",
            "provider_code": provider_code,
            "model": model,
            "context_mode": normalize_context_mode(context_mode),
            "summary": "",
            "messages": [],
            "events": [],
            "state": {},
            "pending_action_ids": [],
            "action_ids": [],
            "created_at": now,
            "updated_at": now,
        }
        self._save_conversation(conversation)
        self._cleanup_old_conversations(owner)
        return copy.deepcopy(conversation)

    def _save_conversation(self, conversation: Dict[str, Any]) -> None:
        owner = conversation["owner"]
        conversation_id = conversation["id"]
        key = self._conversation_key(owner, conversation_id)
        score = float(conversation.get("updated_at") or self.now())
        self.redis.set(key, self._json(conversation), ex=self.conversation_ttl)
        index = self._conversation_index(owner)
        self.redis.zadd(index, {conversation_id: score})
        self.redis.expire(index, self.conversation_ttl)

    def save_conversation(self, owner: str, conversation: Dict[str, Any]) -> Dict[str, Any]:
        if conversation.get("owner") != owner:
            raise AgentStoreNotFound("conversation not found")
        conversation = copy.deepcopy(conversation)
        conversation["updated_at"] = self.now()
        self._save_conversation(conversation)
        return conversation

    def get_conversation(self, owner: str, conversation_id: str) -> Dict[str, Any]:
        value = self._loads(self.redis.get(self._conversation_key(owner, conversation_id)))
        if not value or value.get("owner") != owner:
            raise AgentStoreNotFound("conversation not found")
        return self._reconcile_pending_actions(value)

    def _reconcile_pending_actions(
        self,
        conversation: Dict[str, Any],
    ) -> Dict[str, Any]:
        owner = conversation["owner"]
        conversation_id = conversation["id"]
        pending_ids = conversation.get("pending_action_ids", [])
        live_ids = []
        for action_id in pending_ids:
            action = self._loads(self.redis.get(self._action_key(action_id)))
            if (
                action
                and action.get("owner") == owner
                and action.get("conversation_id") == conversation_id
            ):
                status = action.get("status")
                if status == "pending":
                    now = self.now()
                    if float(action.get("expires_at") or 0) <= now:
                        action["status"] = "expired"
                        action["updated_at"] = now
                        self._save_action(action)
                    else:
                        live_ids.append(action_id)
                elif status == "running":
                    live_ids.append(action_id)
            else:
                self.redis.srem(
                    self._conversation_actions(owner, conversation_id),
                    action_id,
                )
        if live_ids != pending_ids:
            conversation["pending_action_ids"] = live_ids
            self._save_conversation(conversation)
        return conversation

    def list_conversations(self, owner: str) -> List[Dict[str, Any]]:
        ids = self.redis.zrevrange(self._conversation_index(owner), 0, self.max_conversations - 1)
        rows = []
        for conversation_id in ids:
            if isinstance(conversation_id, bytes):
                conversation_id = conversation_id.decode("utf-8")
            try:
                conversation = self.get_conversation(owner, conversation_id)
            except AgentStoreNotFound:
                self.redis.zrem(self._conversation_index(owner), conversation_id)
                continue
            rows.append({
                key: conversation.get(key)
                for key in (
                    "id", "title", "provider_code", "model", "context_mode",
                    "created_at", "updated_at", "pending_action_ids",
                )
            })
            rows[-1]["has_pending_action"] = bool(
                conversation.get("pending_action_ids")
            )
        return rows

    def append_message(
        self,
        owner: str,
        conversation_id: str,
        message: Dict[str, Any],
    ) -> Dict[str, Any]:
        conversation = self.get_conversation(owner, conversation_id)
        conversation["messages"].append(copy.deepcopy(message))
        if conversation["title"] == "新会话" and message.get("role") == "user":
            content = str(message.get("content") or "").strip()
            if content:
                conversation["title"] = content[:30]
        return self.save_conversation(owner, conversation)

    def append_event(
        self,
        owner: str,
        conversation_id: str,
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        conversation = self.get_conversation(owner, conversation_id)
        conversation["events"].append(copy.deepcopy(event))
        conversation["events"] = conversation["events"][-200:]
        return self.save_conversation(owner, conversation)

    def acquire_run_lock(
        self,
        owner: str,
        conversation_id: str,
        *,
        ttl: int = 10 * 60,
    ) -> str:
        self.get_conversation(owner, conversation_id)
        token = uuid.uuid4().hex
        if not self.redis.set(
            self._run_lock_key(owner, conversation_id),
            token,
            ex=max(30, int(ttl)),
            nx=True,
        ):
            raise AgentStoreConflict("conversation is already running")
        return token

    def release_run_lock(
        self,
        owner: str,
        conversation_id: str,
        token: str,
    ) -> None:
        key = self._run_lock_key(owner, conversation_id)
        current = self.redis.get(key)
        if isinstance(current, bytes):
            current = current.decode("utf-8")
        if current == token:
            self.redis.delete(key)

    def delete_conversation(self, owner: str, conversation_id: str) -> None:
        conversation = self.get_conversation(owner, conversation_id)
        running = []
        action_index = self._conversation_actions(owner, conversation_id)
        for action_id in self.redis.smembers(action_index):
            if isinstance(action_id, bytes):
                action_id = action_id.decode("utf-8")
            action = self._loads(self.redis.get(self._action_key(action_id)))
            if action and action.get("status") == "running":
                running.append(action_id)
        if running:
            raise AgentStoreConflict("conversation has a running action")

        result_index = self._conversation_results(owner, conversation_id)
        result_keys = [
            self._result_key(owner, rid.decode("utf-8") if isinstance(rid, bytes) else rid)
            for rid in self.redis.smembers(result_index)
        ]
        action_keys = [
            self._action_key(aid.decode("utf-8") if isinstance(aid, bytes) else aid)
            for aid in self.redis.smembers(action_index)
        ]
        keys = result_keys + action_keys + [
            result_index,
            action_index,
            self._conversation_key(owner, conversation_id),
        ]
        if keys:
            self.redis.delete(*keys)
        self.redis.zrem(self._conversation_index(owner), conversation_id)

    def _cleanup_old_conversations(self, owner: str) -> None:
        index = self._conversation_index(owner)
        while self.redis.zcard(index) > self.max_conversations:
            oldest = self.redis.zrange(index, 0, 0)
            if not oldest:
                break
            conversation_id = oldest[0]
            if isinstance(conversation_id, bytes):
                conversation_id = conversation_id.decode("utf-8")
            try:
                conversation = self.get_conversation(owner, conversation_id)
            except AgentStoreNotFound:
                self.redis.zrem(index, conversation_id)
                continue
            if conversation.get("pending_action_ids"):
                # Move protected conversations to the newest edge and try the next oldest.
                self.redis.zadd(index, {conversation_id: self.now()})
                candidates = self.redis.zrange(index, 0, -1)
                if all(
                    self.get_conversation(
                        owner, c.decode("utf-8") if isinstance(c, bytes) else c
                    ).get("pending_action_ids")
                    for c in candidates
                ):
                    break
                continue
            self.delete_conversation(owner, conversation_id)

    def create_result_set(
        self,
        owner: str,
        conversation_id: str,
        kind: str,
        *,
        rows: List[Dict[str, Any]],
        resource_ids: Iterable[Any],
        filters: Optional[Dict[str, Any]] = None,
        summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.get_conversation(owner, conversation_id)
        result_id = uuid.uuid4().hex
        result = {
            "id": result_id,
            "owner": owner,
            "conversation_id": conversation_id,
            "kind": kind,
            "rows": copy.deepcopy(rows),
            "resource_ids": list(resource_ids),
            "filters": copy.deepcopy(filters or {}),
            "summary": copy.deepcopy(summary or {}),
            "created_at": self.now(),
        }
        key = self._result_key(owner, result_id)
        self.redis.set(key, self._json(result), ex=self.conversation_ttl)
        index = self._conversation_results(owner, conversation_id)
        self.redis.sadd(index, result_id)
        self.redis.expire(index, self.conversation_ttl)
        return copy.deepcopy(result)

    def get_result_set(self, owner: str, result_id: str) -> Dict[str, Any]:
        result = self._loads(self.redis.get(self._result_key(owner, result_id)))
        if not result or result.get("owner") != owner:
            raise AgentStoreNotFound("result set not found")
        return result

    def create_action(
        self,
        owner: str,
        conversation_id: str,
        result_set_id: str,
        *,
        sys_user: str,
        command: str,
        reason: str,
    ) -> Dict[str, Any]:
        conversation = self.get_conversation(owner, conversation_id)
        if conversation.get("pending_action_ids"):
            raise AgentStoreConflict(
                "conversation already has a pending action"
            )
        result = self.get_result_set(owner, result_set_id)
        if result.get("conversation_id") != conversation_id:
            raise AgentStoreConflict("result set belongs to another conversation")
        action_id = uuid.uuid4().hex
        now = self.now()
        action = {
            "id": action_id,
            "owner": owner,
            "conversation_id": conversation_id,
            "result_set_id": result_set_id,
            "sys_user": sys_user,
            "command": command,
            "reason": reason,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "expires_at": now + self.action_ttl,
            "result": None,
        }
        self.redis.set(self._action_key(action_id), self._json(action), ex=self.action_ttl)
        index = self._conversation_actions(owner, conversation_id)
        self.redis.sadd(index, action_id)
        self.redis.expire(index, self.conversation_ttl)
        conversation["pending_action_ids"].append(action_id)
        conversation.setdefault("action_ids", []).append(action_id)
        self.save_conversation(owner, conversation)
        return copy.deepcopy(action)

    def get_action(self, owner: str, action_id: str) -> Dict[str, Any]:
        action = self._loads(self.redis.get(self._action_key(action_id)))
        if not action or action.get("owner") != owner:
            raise AgentStoreNotFound("action not found")
        return action

    def claim_action(self, owner: str, action_id: str) -> Dict[str, Any]:
        lock_key = self._action_lock_key(action_id)
        lock_token = uuid.uuid4().hex
        if not self.redis.set(lock_key, lock_token, ex=30, nx=True):
            raise AgentStoreConflict("action is already being processed")
        try:
            action = self.get_action(owner, action_id)
            if action.get("status") != "pending":
                raise AgentStoreConflict("action is not pending")
            if float(action.get("expires_at") or 0) <= self.now():
                action["status"] = "expired"
                self._save_action(action)
                raise AgentStoreConflict("action expired")
            action["status"] = "running"
            action["updated_at"] = self.now()
            self._save_action(action)
            return action
        finally:
            current = self.redis.get(lock_key)
            if isinstance(current, bytes):
                current = current.decode("utf-8")
            if current == lock_token:
                self.redis.delete(lock_key)

    def update_action(
        self,
        owner: str,
        action_id: str,
        status: str,
        *,
        result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        action = self.get_action(owner, action_id)
        if status in ("completed", "failed", "rejected") and action.get("status") != "running":
            raise AgentStoreConflict(
                "action state changed before completion"
            )
        action["status"] = status
        action["updated_at"] = self.now()
        if result is not None:
            action["result"] = copy.deepcopy(result)
        self._save_action(action)
        if status not in ("pending", "running"):
            conversation = self.get_conversation(owner, action["conversation_id"])
            conversation["pending_action_ids"] = [
                item for item in conversation.get("pending_action_ids", [])
                if item != action_id
            ]
            self.save_conversation(owner, conversation)
        return action

    def cancel_action(self, owner: str, action_id: str) -> Dict[str, Any]:
        lock_key = self._action_lock_key(action_id)
        lock_token = uuid.uuid4().hex
        if not self.redis.set(lock_key, lock_token, ex=30, nx=True):
            raise AgentStoreConflict("action is already being processed")
        try:
            action = self.get_action(owner, action_id)
            if action.get("status") != "pending":
                raise AgentStoreConflict("only pending actions can be cancelled")
            action["status"] = "cancelled"
            action["updated_at"] = self.now()
            self._save_action(action)
            conversation = self.get_conversation(owner, action["conversation_id"])
            conversation["pending_action_ids"] = [
                item for item in conversation.get("pending_action_ids", [])
                if item != action_id
            ]
            self.save_conversation(owner, conversation)
            return action
        finally:
            current = self.redis.get(lock_key)
            if isinstance(current, bytes):
                current = current.decode("utf-8")
            if current == lock_token:
                self.redis.delete(lock_key)

    def touch_action(self, action_id: str, *, ttl: Optional[int] = None) -> None:
        self.redis.expire(
            self._action_key(action_id),
            max(60, int(ttl or self.action_execution_ttl)),
        )

    def _save_action(self, action: Dict[str, Any]) -> None:
        remaining = max(60, int(float(action.get("expires_at") or 0) - self.now()))
        if action.get("status") == "running":
            remaining = max(remaining, self.action_execution_ttl)
        elif action.get("status") != "pending":
            remaining = max(remaining, self.conversation_ttl)
        self.redis.set(self._action_key(action["id"]), self._json(action), ex=remaining)
