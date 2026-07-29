"""Durable orchestration for controlled, evidence-backed diagnostics."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence
from uuid import uuid4

from app.ai.diagnostic_adapters import (
    CollectedEvidence,
    DiagnosticSourceAdapter,
    SSHProbeAdapter,
)
from app.ai.diagnostic_analyzers import DeterministicAnalyzer
from app.ai.diagnostic_profiles import (
    DiagnosticProfileError,
    get_profile,
)
from app.core.config import (
    AI_DIAGNOSTIC_EVIDENCE_RETENTION_DAYS as EVIDENCE_RETENTION_DAYS,
    AI_DIAGNOSTIC_REPORT_RETENTION_DAYS as REPORT_RETENTION_DAYS,
)


MAX_DIAGNOSTIC_TARGETS = 10
TERMINAL_STATUSES = frozenset({
    "completed", "partial", "failed", "cancelled", "interrupted", "expired",
})


class DiagnosticError(RuntimeError):
    pass


class DiagnosticValidationError(DiagnosticError):
    pass


class DiagnosticNotFound(DiagnosticError):
    pass


class DiagnosticConflict(DiagnosticError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return None


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return copy.deepcopy(default)
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return copy.deepcopy(default)
    return decoded


def _public_run(run: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": run.get("id"),
        "conversation_id": run.get("conversation_id"),
        "profile_id": run.get("profile_id"),
        "profile_name": run.get("profile_name"),
        "status": run.get("status"),
        "target_count": int(run.get("target_count") or 0),
        "success_count": int(run.get("success_count") or 0),
        "failed_count": int(run.get("failed_count") or 0),
        "system_user": {
            "id": run.get("system_user_id"),
            "alias": run.get("system_user_alias"),
            "is_privileged": bool(run.get("is_privileged")),
        },
        "parameters": _json(run.get("parameters"), {}),
        "asset_progress": _json(run.get("asset_progress"), []),
        "latest_event_seq": int(run.get("latest_event_seq") or 0),
        "summary": _json(run.get("summary"), {
            "severity": "info",
            "finding_count": 0,
            "evidence_count": 0,
        }),
        "started_at": _iso(run.get("started_at")),
        "completed_at": _iso(run.get("completed_at")),
        "evidence_expires_at": _iso(run.get("evidence_expires_at")),
        "audit_expires_at": _iso(run.get("audit_expires_at")),
        "created_at": _iso(run.get("created_at")),
        "updated_at": _iso(run.get("updated_at")),
    }


class MemoryDiagnosticRepository:
    """Deterministic repository used by boundary tests and local composition."""

    def __init__(self) -> None:
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.events: Dict[str, list[Dict[str, Any]]] = {}
        self.evidence: Dict[str, list[Dict[str, Any]]] = {}
        self.reports: Dict[str, Dict[str, Any]] = {}

    def create_run(self, value: Mapping[str, Any]) -> Dict[str, Any]:
        row = {
            "id": uuid4().hex,
            "owner": "",
            "conversation_id": None,
            "profile_id": "",
            "profile_name": "",
            "status": "queued",
            "target_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "system_user_id": 0,
            "system_user_alias": "",
            "is_privileged": False,
            "parameters": {},
            "summary": {},
            "asset_progress": [],
            "latest_event_seq": 0,
            "cancel_requested": False,
            "started_at": None,
            "completed_at": None,
            "evidence_expires_at": (
                _now() + timedelta(days=EVIDENCE_RETENTION_DAYS)
            ),
            "audit_expires_at": (
                _now() + timedelta(days=REPORT_RETENTION_DAYS)
            ),
            "created_at": _now(),
            "updated_at": _now(),
        }
        row.update(copy.deepcopy(dict(value)))
        if row["id"] in self.runs:
            raise DiagnosticConflict("diagnostic run already exists")
        self.runs[str(row["id"])] = row
        return copy.deepcopy(row)

    def get_run(self, owner: str, run_id: str) -> Dict[str, Any]:
        row = self.runs.get(str(run_id))
        if row is None or row.get("owner") != owner:
            raise DiagnosticNotFound("诊断任务不存在")
        return copy.deepcopy(row)

    def update_run(
        self, owner: str, run_id: str, **changes: Any
    ) -> Dict[str, Any]:
        self.get_run(owner, run_id)
        self.runs[run_id].update(copy.deepcopy(changes))
        self.runs[run_id]["updated_at"] = _now()
        return copy.deepcopy(self.runs[run_id])

    def append_event(
        self,
        owner: str,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        self.get_run(owner, run_id)
        sequence = int(self.runs[run_id].get("latest_event_seq") or 0) + 1
        event = {
            "type": event_type,
            "event_seq": sequence,
            "run_id": run_id,
            **copy.deepcopy(dict(payload)),
            "created_at": _iso(_now()),
        }
        self.events.setdefault(run_id, []).append(event)
        self.runs[run_id]["latest_event_seq"] = sequence
        self.runs[run_id]["updated_at"] = _now()
        return copy.deepcopy(event)

    def list_events(
        self, owner: str, run_id: str, after_seq: int = 0
    ) -> list[Dict[str, Any]]:
        self.get_run(owner, run_id)
        return [
            copy.deepcopy(event)
            for event in self.events.get(run_id, [])
            if int(event.get("event_seq") or 0) > int(after_seq)
        ][:200]

    def add_evidence(
        self,
        owner: str,
        run_id: str,
        value: Mapping[str, Any],
    ) -> Dict[str, Any]:
        run = self.get_run(owner, run_id)
        row = {
            "id": uuid4().hex,
            "run_id": run_id,
            **copy.deepcopy(dict(value)),
            "collected_at": _now(),
            "expires_at": run["evidence_expires_at"],
        }
        self.evidence.setdefault(run_id, []).append(row)
        return copy.deepcopy(row)

    def list_evidence(self, owner: str, run_id: str) -> list[Dict[str, Any]]:
        self.get_run(owner, run_id)
        now = _now()
        return [
            copy.deepcopy(item)
            for item in self.evidence.get(run_id, [])
            if item.get("expires_at") is None or item["expires_at"] > now
        ]

    def save_report(
        self,
        owner: str,
        run_id: str,
        value: Mapping[str, Any],
    ) -> Dict[str, Any]:
        self.get_run(owner, run_id)
        row = {
            "run_id": run_id,
            **copy.deepcopy(dict(value)),
            "generated_at": _now(),
            "expires_at": _now() + timedelta(days=REPORT_RETENTION_DAYS),
        }
        self.reports[run_id] = row
        return copy.deepcopy(row)

    def get_report(self, owner: str, run_id: str) -> Dict[str, Any]:
        self.get_run(owner, run_id)
        row = self.reports.get(run_id)
        if (
            row is None
            or (
                row.get("expires_at") is not None
                and row["expires_at"] <= _now()
            )
        ):
            raise DiagnosticNotFound("诊断报告不存在")
        return copy.deepcopy(row)

    def purge_expired(self) -> Dict[str, int]:
        now = _now()
        evidence_count = 0
        for run_id, items in list(self.evidence.items()):
            kept = []
            for item in items:
                if item.get("expires_at") is not None and item["expires_at"] <= now:
                    evidence_count += 1
                else:
                    kept.append(item)
            self.evidence[run_id] = kept
        expired_reports = [
            run_id for run_id, report in self.reports.items()
            if report.get("expires_at") is not None
            and report["expires_at"] <= now
        ]
        for run_id in expired_reports:
            self.reports.pop(run_id, None)
        expired_runs = [
            run_id for run_id, run in self.runs.items()
            if run.get("audit_expires_at") is not None
            and run["audit_expires_at"] <= now
        ]
        for run_id in expired_runs:
            self.runs.pop(run_id, None)
            self.events.pop(run_id, None)
            self.evidence.pop(run_id, None)
            self.reports.pop(run_id, None)
        return {
            "evidence": evidence_count,
            "reports": len(expired_reports),
            "runs": len(expired_runs),
        }

    def list_for_conversation(
        self, owner: str, conversation_id: str, limit: int = 5
    ) -> list[Dict[str, Any]]:
        rows = [
            copy.deepcopy(row)
            for row in self.runs.values()
            if row.get("owner") == owner
            and row.get("conversation_id") == conversation_id
        ]
        rows.sort(key=lambda row: row.get("created_at") or _now(), reverse=True)
        return rows[:max(1, int(limit))]


class SQLDiagnosticRepository:
    """MySQL-backed repository with owner checks at every read/write."""

    @staticmethod
    def _run_dict(row: Any) -> Dict[str, Any]:
        summary = _json(row.summary_json, {})
        is_privileged = bool(summary.pop("is_privileged", False))
        return {
            "id": row.id,
            "owner": row.owner,
            "conversation_id": row.conversation_id,
            "profile_id": row.profile_id,
            "profile_name": row.profile_name,
            "status": row.status,
            "target_count": row.target_count,
            "success_count": row.success_count,
            "failed_count": row.failed_count,
            "system_user_id": row.system_user_id,
            "system_user_alias": row.system_user_alias,
            "is_privileged": is_privileged,
            "parameters": _json(row.parameters_json, {}),
            "summary": summary,
            "asset_progress": _json(row.asset_progress_json, []),
            "latest_event_seq": row.latest_event_seq,
            "cancel_requested": bool(row.cancel_requested),
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "evidence_expires_at": row.evidence_expires_at,
            "audit_expires_at": row.audit_expires_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def create_run(self, value: Mapping[str, Any]) -> Dict[str, Any]:
        from app.core.db.database import db, t_ai_diagnostic_run

        summary = dict(value.get("summary") or {})
        summary["is_privileged"] = bool(value.get("is_privileged"))
        row = t_ai_diagnostic_run(
            id=value.get("id") or uuid4().hex,
            owner=value["owner"],
            conversation_id=value.get("conversation_id"),
            profile_id=value["profile_id"],
            profile_name=value["profile_name"],
            status=value.get("status") or "queued",
            target_count=int(value.get("target_count") or 0),
            success_count=int(value.get("success_count") or 0),
            failed_count=int(value.get("failed_count") or 0),
            system_user_id=int(value["system_user_id"]),
            system_user_alias=value["system_user_alias"],
            parameters_json=json.dumps(
                value.get("parameters") or {}, ensure_ascii=False
            ),
            summary_json=json.dumps(summary, ensure_ascii=False),
            asset_progress_json=json.dumps(
                value.get("asset_progress") or [], ensure_ascii=False
            ),
            latest_event_seq=0,
            cancel_requested=False,
            started_at=value.get("started_at"),
            completed_at=value.get("completed_at"),
            evidence_expires_at=value["evidence_expires_at"],
            audit_expires_at=value["audit_expires_at"],
        )
        db.session.add(row)
        db.session.commit()
        return self._run_dict(row)

    def _owned_row(self, owner: str, run_id: str, *, lock: bool = False) -> Any:
        from app.core.db.database import t_ai_diagnostic_run

        query = t_ai_diagnostic_run.query.filter_by(id=run_id, owner=owner)
        if lock:
            query = query.with_for_update()
        row = query.first()
        if row is None:
            raise DiagnosticNotFound("诊断任务不存在")
        return row

    def get_run(self, owner: str, run_id: str) -> Dict[str, Any]:
        return self._run_dict(self._owned_row(owner, run_id))

    def update_run(
        self, owner: str, run_id: str, **changes: Any
    ) -> Dict[str, Any]:
        from app.core.db.database import db

        row = self._owned_row(owner, run_id, lock=True)
        fields = {
            "status", "target_count", "success_count", "failed_count",
            "latest_event_seq", "cancel_requested", "started_at",
            "completed_at", "evidence_expires_at", "audit_expires_at",
        }
        for name in fields & set(changes):
            setattr(row, name, changes[name])
        if "parameters" in changes:
            row.parameters_json = json.dumps(
                changes["parameters"], ensure_ascii=False
            )
        if "asset_progress" in changes:
            row.asset_progress_json = json.dumps(
                changes["asset_progress"], ensure_ascii=False
            )
        if "summary" in changes or "is_privileged" in changes:
            summary = _json(row.summary_json, {})
            if "summary" in changes:
                summary.update(changes["summary"])
            if "is_privileged" in changes:
                summary["is_privileged"] = bool(changes["is_privileged"])
            row.summary_json = json.dumps(summary, ensure_ascii=False)
        db.session.commit()
        return self._run_dict(row)

    def append_event(
        self,
        owner: str,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        from app.core.db.database import db, t_ai_diagnostic_event

        row = self._owned_row(owner, run_id, lock=True)
        sequence = int(row.latest_event_seq or 0) + 1
        event = {
            "type": event_type,
            "event_seq": sequence,
            "run_id": run_id,
            **dict(payload),
            "created_at": _iso(_now()),
        }
        db.session.add(t_ai_diagnostic_event(
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            payload_json=json.dumps(event, ensure_ascii=False),
        ))
        row.latest_event_seq = sequence
        db.session.commit()
        return event

    def list_events(
        self, owner: str, run_id: str, after_seq: int = 0
    ) -> list[Dict[str, Any]]:
        from app.core.db.database import t_ai_diagnostic_event

        self.get_run(owner, run_id)
        rows = t_ai_diagnostic_event.query.filter(
            t_ai_diagnostic_event.run_id == run_id,
            t_ai_diagnostic_event.sequence > max(0, int(after_seq)),
        ).order_by(t_ai_diagnostic_event.sequence.asc()).limit(200).all()
        return [_json(row.payload_json, {}) for row in rows]

    def add_evidence(
        self,
        owner: str,
        run_id: str,
        value: Mapping[str, Any],
    ) -> Dict[str, Any]:
        from app.core.db.database import db, t_ai_diagnostic_evidence
        from app.tools.basesec import encrypt_secret

        run = self.get_run(owner, run_id)
        content_ciphertext = encrypt_secret(json.dumps(
            {"value": str(value.get("content") or "")},
            ensure_ascii=False,
        ))
        error_ciphertext = encrypt_secret(json.dumps(
            {"value": str(value.get("error") or "")},
            ensure_ascii=False,
        ))
        if content_ciphertext is None or error_ciphertext is None:
            raise DiagnosticError("诊断证据加密失败")
        row = t_ai_diagnostic_evidence(
            id=uuid4().hex,
            run_id=run_id,
            target_id=value.get("target_id"),
            asset_alias=str(value.get("asset_alias") or "")[:25],
            probe_id=str(value.get("probe_id") or "")[:64],
            title=str(value.get("title") or "")[:128],
            kind=str(value.get("kind") or "")[:32],
            status=str(value.get("status") or "failed")[:16],
            content_ciphertext=content_ciphertext,
            error_ciphertext=error_ciphertext,
            truncated=bool(value.get("truncated")),
            expires_at=run["evidence_expires_at"],
        )
        db.session.add(row)
        db.session.commit()
        return self._evidence_dict(row)

    @staticmethod
    def _evidence_dict(row: Any) -> Dict[str, Any]:
        from app.tools.basesec import decrypt_secret

        def plaintext(ciphertext: str) -> str:
            decoded = decrypt_secret(ciphertext)
            value = _json(decoded, {})
            return str(value.get("value") or "")

        return {
            "id": row.id,
            "run_id": row.run_id,
            "target_id": row.target_id,
            "asset_alias": row.asset_alias,
            "probe_id": row.probe_id,
            "title": row.title,
            "kind": row.kind,
            "status": row.status,
            "content": plaintext(row.content_ciphertext),
            "error": plaintext(row.error_ciphertext),
            "truncated": bool(row.truncated),
            "untrusted": True,
            "collected_at": row.collected_at,
            "expires_at": row.expires_at,
        }

    def list_evidence(self, owner: str, run_id: str) -> list[Dict[str, Any]]:
        from app.core.db.database import t_ai_diagnostic_evidence

        self.get_run(owner, run_id)
        now = _now().replace(tzinfo=None)
        rows = t_ai_diagnostic_evidence.query.filter(
            t_ai_diagnostic_evidence.run_id == run_id,
            t_ai_diagnostic_evidence.expires_at > now,
        ).order_by(t_ai_diagnostic_evidence.collected_at.asc()).all()
        return [self._evidence_dict(row) for row in rows]

    def save_report(
        self,
        owner: str,
        run_id: str,
        value: Mapping[str, Any],
    ) -> Dict[str, Any]:
        from app.core.db.database import db, t_ai_diagnostic_report

        self.get_run(owner, run_id)
        row = t_ai_diagnostic_report.query.filter_by(run_id=run_id).first()
        if row is None:
            row = t_ai_diagnostic_report(run_id=run_id)
            db.session.add(row)
        row.status = str(value.get("status") or "completed")
        row.severity = str(value.get("severity") or "info")
        row.summary = str(value.get("summary") or "")
        row.findings_json = json.dumps(
            value.get("findings") or [], ensure_ascii=False
        )
        row.evidence_insufficient = bool(value.get("evidence_insufficient"))
        row.generated_at = _now().replace(tzinfo=None)
        row.expires_at = (
            _now() + timedelta(days=REPORT_RETENTION_DAYS)
        ).replace(tzinfo=None)
        db.session.commit()
        return self._report_dict(row)

    @staticmethod
    def _report_dict(row: Any) -> Dict[str, Any]:
        return {
            "run_id": row.run_id,
            "status": row.status,
            "summary": row.summary,
            "severity": row.severity,
            "findings": _json(row.findings_json, []),
            "evidence_insufficient": bool(row.evidence_insufficient),
            "generated_at": row.generated_at,
            "expires_at": row.expires_at,
        }

    def get_report(self, owner: str, run_id: str) -> Dict[str, Any]:
        from app.core.db.database import t_ai_diagnostic_report

        self.get_run(owner, run_id)
        row = t_ai_diagnostic_report.query.filter(
            t_ai_diagnostic_report.run_id == run_id,
            t_ai_diagnostic_report.expires_at > _now().replace(tzinfo=None),
        ).first()
        if row is None:
            raise DiagnosticNotFound("诊断报告不存在")
        return self._report_dict(row)

    def purge_expired(self) -> Dict[str, int]:
        from app.core.db.database import (
            db,
            t_ai_diagnostic_evidence,
            t_ai_diagnostic_report,
            t_ai_diagnostic_run,
        )

        now = _now().replace(tzinfo=None)
        evidence_count = t_ai_diagnostic_evidence.query.filter(
            t_ai_diagnostic_evidence.expires_at <= now
        ).delete(synchronize_session=False)
        report_count = t_ai_diagnostic_report.query.filter(
            t_ai_diagnostic_report.expires_at <= now
        ).delete(synchronize_session=False)
        run_count = t_ai_diagnostic_run.query.filter(
            t_ai_diagnostic_run.audit_expires_at <= now
        ).delete(synchronize_session=False)
        db.session.commit()
        return {
            "evidence": int(evidence_count or 0),
            "reports": int(report_count or 0),
            "runs": int(run_count or 0),
        }

    def list_for_conversation(
        self, owner: str, conversation_id: str, limit: int = 5
    ) -> list[Dict[str, Any]]:
        from app.core.db.database import t_ai_diagnostic_run

        rows = t_ai_diagnostic_run.query.filter_by(
            owner=owner, conversation_id=conversation_id
        ).order_by(t_ai_diagnostic_run.created_at.desc()).limit(
            max(1, int(limit))
        ).all()
        return [self._run_dict(row) for row in rows]


def _default_target_resolver(target_ids: Sequence[int]) -> list[Dict[str, Any]]:
    from app.core.db.database import t_host

    rows = t_host.query.filter(
        t_host.id.in_(target_ids),
        t_host.is_deleted.is_(False),
    ).all()
    by_id = {int(row.id): row for row in rows}
    return [
        {"id": target_id, "alias": by_id[target_id].alias}
        for target_id in target_ids
        if target_id in by_id
    ]


def _default_privilege_resolver(credential: Mapping[str, Any]) -> bool:
    return str(credential.get("host_user") or "").strip().lower() == "root"


class DiagnosticService:
    def __init__(
        self,
        *,
        repository: Optional[Any] = None,
        platform_factory: Optional[Callable[[str, str], Any]] = None,
        target_resolver: Optional[
            Callable[[Sequence[int]], list[Dict[str, Any]]]
        ] = None,
        privilege_resolver: Optional[
            Callable[[Mapping[str, Any]], bool]
        ] = None,
        adapter: Optional[DiagnosticSourceAdapter] = None,
        analyzer: Optional[DeterministicAnalyzer] = None,
        agent_store: Optional[Any] = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.repository = repository or SQLDiagnosticRepository()
        if platform_factory is None:
            from app.ai.tools import PlatformQueryService

            platform_factory = PlatformQueryService
        self.platform_factory = platform_factory
        self.target_resolver = target_resolver or _default_target_resolver
        self.privilege_resolver = (
            privilege_resolver or _default_privilege_resolver
        )
        self.adapter = adapter or SSHProbeAdapter()
        self.analyzer = analyzer or DeterministicAnalyzer()
        self.agent_store = agent_store
        self.clock = clock

    def _purge_expired(self) -> None:
        try:
            self.repository.purge_expired()
        except Exception:
            # Retention cleanup must not turn an otherwise valid read-only
            # diagnosis into a user-visible outage.
            pass

    def _targets(
        self,
        owner: str,
        payload: Mapping[str, Any],
    ) -> tuple[list[int], Optional[str]]:
        raw_ids = payload.get("target_ids")
        conversation_id = str(payload.get("conversation_id") or "").strip() or None
        result_set_id = str(payload.get("result_set_id") or "").strip()
        if result_set_id:
            if self.agent_store is None:
                raise DiagnosticValidationError(
                    "result_set_id is unavailable in this request"
                )
            try:
                result = self.agent_store.get_result_set(owner, result_set_id)
            except Exception as exc:
                raise DiagnosticValidationError("资产结果集不存在") from exc
            if result.get("kind") != "assets":
                raise DiagnosticValidationError("诊断需要资产结果集")
            if conversation_id and result.get("conversation_id") != conversation_id:
                raise DiagnosticValidationError("资产结果集不属于当前会话")
            conversation_id = conversation_id or result.get("conversation_id")
            raw_ids = result.get("resource_ids")
        if not isinstance(raw_ids, list):
            raise DiagnosticValidationError(
                "target_ids 或 result_set_id 至少提供一个"
            )
        try:
            target_ids = list(dict.fromkeys(int(item) for item in raw_ids))
        except (TypeError, ValueError):
            raise DiagnosticValidationError("target_ids 格式无效") from None
        if not target_ids:
            raise DiagnosticValidationError("诊断目标不能为空")
        if len(target_ids) > MAX_DIAGNOSTIC_TARGETS:
            raise DiagnosticValidationError(
                f"单次诊断最多 {MAX_DIAGNOSTIC_TARGETS} 台资产"
            )
        return target_ids, conversation_id

    def _emit(
        self,
        owner: str,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        on_event: Optional[Callable[[Dict[str, Any]], None]],
    ) -> Dict[str, Any]:
        event = self.repository.append_event(
            owner, run_id, event_type, payload
        )
        if on_event is not None:
            on_event(copy.deepcopy(event))
        return event

    def start(
        self,
        *,
        owner: str,
        role: str,
        payload: Mapping[str, Any],
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        self._purge_expired()
        try:
            profile = get_profile(str(payload.get("profile_id") or ""))
            parameters = profile.validate_parameters(payload.get("parameters"))
        except DiagnosticProfileError as exc:
            raise DiagnosticValidationError(str(exc)) from exc
        target_ids, conversation_id = self._targets(owner, payload)
        try:
            system_user_id = int(payload.get("system_user_id"))
        except (TypeError, ValueError):
            raise DiagnosticValidationError(
                "system_user_id is required"
            ) from None
        if system_user_id <= 0:
            raise DiagnosticValidationError("system_user_id is invalid")
        platform = self.platform_factory(owner, role)
        if not platform.validate_asset_ids(target_ids):
            raise DiagnosticValidationError("资产权限已变化，请重新查询")
        credential = platform.resolve_system_user(system_user_id)
        if (
            credential is None
            or not platform.validate_asset_sys_user_id_pair(
                target_ids, system_user_id
            )
        ):
            raise DiagnosticValidationError("系统用户未获全部目标资产授权")
        system_user = str(credential["alias"])
        targets = self.target_resolver(target_ids)
        if {int(item["id"]) for item in targets} != set(target_ids):
            raise DiagnosticValidationError("一个或多个资产已不存在")

        privileged = bool(self.privilege_resolver(credential))
        started_at = self.clock()
        expiry = started_at + timedelta(days=EVIDENCE_RETENTION_DAYS)
        audit_expiry = started_at + timedelta(days=REPORT_RETENTION_DAYS)
        progress = [{
            "target_id": int(target["id"]),
            "alias": str(target["alias"]),
            "status": "queued",
            "completed_probes": 0,
            "total_probes": len(profile.probes),
            "finding_count": 0,
        } for target in targets]
        run = self.repository.create_run({
            "owner": owner,
            "conversation_id": conversation_id,
            "profile_id": profile.id,
            "profile_name": profile.name,
            "status": "queued",
            "target_count": len(target_ids),
            "system_user_id": system_user_id,
            "system_user_alias": system_user,
            "is_privileged": privileged,
            "parameters": parameters,
            "summary": {
                "severity": "info",
                "finding_count": 0,
                "evidence_count": 0,
            },
            "asset_progress": progress,
            "evidence_expires_at": expiry,
            "audit_expires_at": audit_expiry,
        })
        run_id = str(run["id"])
        self.repository.update_run(
            owner, run_id, status="running", started_at=started_at
        )
        self._emit(owner, run_id, "diagnostic_started", {
            "status": "running",
            "profile_id": profile.id,
            "target_count": len(target_ids),
            "system_user": {
                "id": system_user_id,
                "alias": system_user,
                "is_privileged": privileged,
            },
        }, on_event)
        progress_by_id = {
            int(item["target_id"]): item for item in progress
        }

        def on_progress(item: Dict[str, Any]) -> None:
            target_id = int(item.get("target_id") or 0)
            target = progress_by_id.get(target_id)
            if target is None:
                return
            target["status"] = (
                "running" if item.get("status") == "success" else "failed"
            )
            target["completed_probes"] = min(
                target["total_probes"],
                int(target["completed_probes"]) + 1,
            )
            if item.get("status") != "success":
                target["error"] = "探针采集失败"
            self.repository.update_run(
                owner, run_id, asset_progress=list(progress_by_id.values())
            )
            self._emit(owner, run_id, "diagnostic_progress", {
                "status": "running",
                "asset": dict(target),
            }, on_event)

        permission_changed = False

        def should_cancel() -> bool:
            nonlocal permission_changed
            try:
                if bool(
                    self.repository.get_run(owner, run_id).get(
                        "cancel_requested"
                    )
                ):
                    return True
            except DiagnosticNotFound:
                return True
            if (
                not platform.validate_asset_ids(target_ids)
                or not platform.validate_asset_sys_user_id_pair(
                    target_ids, system_user_id
                )
            ):
                permission_changed = True
                return True
            return False

        try:
            collected = self.adapter.collect(
                profile=profile,
                targets=targets,
                system_user_id=system_user_id,
                system_user=system_user,
                parameters=parameters,
                username=owner,
                on_progress=on_progress,
                should_cancel=should_cancel,
            )
        except Exception:
            completed_at = self.clock()
            for target in progress_by_id.values():
                target["status"] = "failed"
                target["error"] = "证据采集失败"
            failed_report = self.repository.save_report(
                owner, run_id, {
                    "status": "failed",
                    "summary": "证据采集失败，无法形成可靠结论",
                    "severity": "warning",
                    "findings": [],
                    "evidence_insufficient": True,
                },
            )
            self.repository.update_run(
                owner,
                run_id,
                status="failed",
                failed_count=len(target_ids),
                completed_at=completed_at,
                asset_progress=list(progress_by_id.values()),
                summary={
                    "severity": "warning",
                    "finding_count": 0,
                    "evidence_count": 0,
                },
            )
            self._emit(owner, run_id, "diagnostic_failed", {
                "status": "failed",
                "target_count": len(target_ids),
                "success_count": 0,
                "failed_count": len(target_ids),
                "asset_progress": list(progress_by_id.values()),
                "completed_at": _iso(completed_at),
                "message": "诊断采集失败，请查看服务端日志",
                "report": self.public_report(failed_report),
            }, on_event)
            return self.get_run(owner, run_id)

        stored_evidence = []
        for item in collected:
            evidence = self.repository.add_evidence(
                owner, run_id, {
                    "target_id": item.target_id,
                    "asset_alias": item.asset_alias,
                    "probe_id": item.probe_id,
                    "title": item.title,
                    "kind": item.kind,
                    "status": item.status,
                    "content": item.content,
                    "error": item.error,
                    "truncated": item.truncated,
                    "untrusted": True,
                },
            )
            stored_evidence.append(evidence)
            self._emit(owner, run_id, "diagnostic_evidence", {
                "status": "running",
                "evidence_id": evidence["id"],
                "asset_alias": evidence["asset_alias"],
                "probe_id": evidence["probe_id"],
                "title": evidence["title"],
                "truncated": bool(evidence.get("truncated")),
            }, on_event)

        cancelled = should_cancel()
        report = self.analyzer.analyze(stored_evidence)
        evidence_ids = {str(item["id"]) for item in stored_evidence}
        for finding in report["findings"]:
            cited = set(str(item) for item in finding.get("evidence_ids") or [])
            if not cited or not cited <= evidence_ids:
                raise DiagnosticError(
                    "analyzer returned evidence from another diagnostic run"
                )

        by_target: Dict[int, list[Mapping[str, Any]]] = {
            int(target["id"]): [] for target in targets
        }
        for item in stored_evidence:
            by_target.setdefault(int(item.get("target_id") or 0), []).append(item)
        success_count = 0
        for target_id, target in progress_by_id.items():
            items = by_target.get(target_id) or []
            successful = bool(items) and all(
                item.get("status") == "success" for item in items
            )
            target["completed_probes"] = len(items)
            target["status"] = "completed" if successful else "failed"
            target["finding_count"] = sum(
                finding.get("asset_alias") == target.get("alias")
                for finding in report["findings"]
            )
            if not successful:
                target["error"] = "部分或全部探针采集失败"
            else:
                target.pop("error", None)
                success_count += 1
        failed_count = len(target_ids) - success_count
        if permission_changed:
            status = "interrupted"
        elif cancelled:
            status = "cancelled"
        elif success_count == len(target_ids):
            status = "completed"
        elif success_count == 0:
            status = "failed"
        else:
            status = "partial"
        report["status"] = status
        stored_report = self.repository.save_report(
            owner, run_id, report
        )
        summary = {
            "severity": report["severity"],
            "finding_count": len(report["findings"]),
            "evidence_count": len(stored_evidence),
        }
        self.repository.update_run(
            owner,
            run_id,
            status=status,
            success_count=success_count,
            failed_count=failed_count,
            completed_at=self.clock(),
            asset_progress=list(progress_by_id.values()),
            summary=summary,
        )
        event_type = (
            "diagnostic_completed"
            if status in ("completed", "partial") else "diagnostic_failed"
        )
        self._emit(owner, run_id, event_type, {
            "status": status,
            "target_count": len(target_ids),
            "success_count": success_count,
            "failed_count": failed_count,
            "asset_progress": list(progress_by_id.values()),
            "summary": summary,
            "report": self.public_report(stored_report),
            **({
                "message": "诊断期间权限发生变化，已停止后续探针"
            } if permission_changed else {}),
        }, on_event)
        return self.get_run(owner, run_id)

    def _owned_authorized_run(
        self, owner: str, run_id: str, role: Optional[str]
    ) -> Dict[str, Any]:
        run = self.repository.get_run(owner, run_id)
        if role is None:
            return run
        target_ids = [
            int(item["target_id"])
            for item in _json(run.get("asset_progress"), [])
            if item.get("target_id") is not None
        ]
        platform = self.platform_factory(owner, role)
        if (
            not target_ids
            or not platform.validate_asset_ids(target_ids)
            or not platform.validate_asset_sys_user_id_pair(
                target_ids, int(run.get("system_user_id") or 0)
            )
        ):
            raise DiagnosticNotFound("诊断任务不存在")
        return run

    def get_run(
        self, owner: str, run_id: str, role: Optional[str] = None
    ) -> Dict[str, Any]:
        return _public_run(
            self._owned_authorized_run(owner, run_id, role)
        )

    def cancel(
        self, owner: str, run_id: str, role: Optional[str] = None
    ) -> Dict[str, Any]:
        run = self._owned_authorized_run(owner, run_id, role)
        if run.get("status") in TERMINAL_STATUSES:
            return _public_run(run)
        self.repository.update_run(
            owner, run_id, cancel_requested=True, status="cancelled",
            completed_at=self.clock(),
        )
        self._emit(
            owner, run_id, "diagnostic_failed",
            {"status": "cancelled", "message": "诊断已取消"}, None,
        )
        return self.get_run(owner, run_id)

    def evidence(
        self, owner: str, run_id: str, role: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        self._purge_expired()
        self._owned_authorized_run(owner, run_id, role)
        items = self.repository.list_evidence(owner, run_id)
        return [{
            "id": item["id"],
            "run_id": item["run_id"],
            "target_id": item.get("target_id"),
            "asset_alias": item.get("asset_alias"),
            "probe_id": item.get("probe_id"),
            "title": item.get("title"),
            "kind": item.get("kind"),
            "status": item.get("status"),
            "content": item.get("content") or "",
            "error": item.get("error") or "",
            "truncated": bool(item.get("truncated")),
            "untrusted": True,
            "collected_at": _iso(item.get("collected_at")),
            "expires_at": _iso(item.get("expires_at")),
        } for item in items]

    def events(
        self,
        owner: str,
        run_id: str,
        after_seq: int = 0,
        role: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        self._owned_authorized_run(owner, run_id, role)
        return self.repository.list_events(owner, run_id, after_seq)

    @staticmethod
    def public_report(report: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "run_id": report.get("run_id"),
            "status": report.get("status"),
            "summary": report.get("summary"),
            "severity": report.get("severity"),
            "evidence_insufficient": bool(
                report.get("evidence_insufficient")
            ),
            "findings": copy.deepcopy(report.get("findings") or []),
            "generated_at": _iso(report.get("generated_at")),
            "expires_at": _iso(report.get("expires_at")),
        }

    def report(
        self, owner: str, run_id: str, role: Optional[str] = None
    ) -> Dict[str, Any]:
        self._purge_expired()
        self._owned_authorized_run(owner, run_id, role)
        return self.public_report(
            self.repository.get_report(owner, run_id)
        )

    def conversation_runs(
        self,
        owner: str,
        conversation_id: str,
        limit: int = 5,
        role: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        runs = []
        for row in self.repository.list_for_conversation(
            owner, conversation_id, limit
        ):
            try:
                if role is not None:
                    row = self._owned_authorized_run(
                        owner, str(row.get("id") or ""), role
                    )
            except DiagnosticNotFound:
                continue
            runs.append(_public_run(row))
        return runs
