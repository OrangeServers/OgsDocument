"""Approval-time revalidation and batch-command execution."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from app.ai.storage import AgentStore, AgentStoreConflict, AgentStoreError
from app.ai.tools import MAX_BATCH_HOSTS, PlatformQueryService


logger = logging.getLogger(__name__)


class ActionValidationError(RuntimeError):
    pass


class ActionExecutionError(RuntimeError):
    pass


class ActionService:
    def __init__(
        self,
        *,
        store: AgentStore,
        platform_factory: Callable[[str, str], PlatformQueryService] = PlatformQueryService,
        batch_executor: Optional[Callable[..., Dict[str, Any]]] = None,
        command_checker: Optional[Callable[[str], Optional[str]]] = None,
    ):
        self.store = store
        self.platform_factory = platform_factory
        self.batch_executor = batch_executor or self._default_batch_executor
        self.command_checker = command_checker or self._default_command_checker

    @staticmethod
    def _default_command_checker(command: str) -> Optional[str]:
        from app.tools.shellcmd import _check_dangerous_command
        return _check_dangerous_command(command)

    @staticmethod
    def _default_batch_executor(**kwargs):
        from app.assets.batch_service import execute_batch_command
        return execute_batch_command(**kwargs)

    def approve(
        self,
        owner: str,
        role: str,
        action_id: str,
        *,
        remote_ip: str = "",
        user_agent: str = "",
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        run_lock_token = None
        conversation_id = ""
        claimed = False
        try:
            try:
                pending = self.store.get_action(owner, action_id)
                conversation_id = str(pending.get("conversation_id") or "")
                run_lock_token = self.store.acquire_run_lock(
                    owner, conversation_id, ttl=60 * 60
                )
                action = self.store.claim_action(owner, action_id)
                claimed = True
            except AgentStoreError as exc:
                raise ActionValidationError(str(exc)) from exc

            result_set = self.store.get_result_set(owner, action["result_set_id"])
            if result_set.get("conversation_id") != action.get("conversation_id"):
                raise ActionValidationError("result set belongs to another conversation")
            if result_set.get("kind") != "assets":
                raise ActionValidationError("action target is not an asset result set")
            asset_ids = list(result_set.get("resource_ids") or [])
            if not asset_ids or len(asset_ids) > MAX_BATCH_HOSTS:
                raise ActionValidationError(f"invalid target count (max {MAX_BATCH_HOSTS})")

            platform = self.platform_factory(owner, role)
            if not platform.validate_asset_ids(asset_ids):
                raise ActionValidationError("asset permission changed; query again")
            if not platform.validate_asset_sys_user_pair(
                asset_ids, str(action.get("sys_user") or "")
            ):
                raise ActionValidationError(
                    "asset and system user permission changed"
                )
            danger = self.command_checker(str(action.get("command") or ""))
            if danger:
                raise ActionValidationError(f"dangerous command blocked: {danger}")

            def progress(item: Dict[str, Any]) -> None:
                self.store.touch_action(action_id, ttl=60 * 60)
                if on_progress is not None:
                    on_progress(item)

            result = self.batch_executor(
                username=owner,
                host_ids=asset_ids,
                sys_user=action["sys_user"],
                command=action["command"],
                audit_source="AI Agent",
                audit_ref="%s/%s" % (conversation_id, action_id),
                max_output_chars=32 * 1024,
                on_progress=progress,
            )
            if not isinstance(result, dict):
                raise ActionExecutionError("batch executor returned invalid result")
            return self.store.update_action(
                owner, action_id, "completed", result=result
            )
        except ActionValidationError as exc:
            if claimed:
                self.store.update_action(
                    owner, action_id, "rejected", result={"error": str(exc)}
                )
            raise
        except Exception as exc:
            logger.exception(
                "AI batch action failed: owner=%s action_id=%s",
                owner,
                action_id,
            )
            if claimed:
                self.store.update_action(
                    owner, action_id, "failed",
                    result={"error": "batch_execution_failed", "message": "批量命令执行失败"},
                )
            raise ActionExecutionError("批量命令执行失败") from exc
        finally:
            if run_lock_token and conversation_id:
                self.store.release_run_lock(
                    owner, conversation_id, run_lock_token
                )

    def cancel(self, owner: str, action_id: str) -> Dict[str, Any]:
        try:
            return self.store.cancel_action(owner, action_id)
        except (AgentStoreError, AgentStoreConflict) as exc:
            raise ActionValidationError(str(exc)) from exc
