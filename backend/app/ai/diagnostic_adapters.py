"""Controlled evidence collection adapters for AI diagnostics."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from app.ai.diagnostic_profiles import DiagnosticProfile, Probe


_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ASSIGNED_SECRET = re.compile(
    r"(?im)\b(api[_-]?key|access[_-]?token|token|secret|"
    r"password|passwd)\s*([:=])\s*([^\s,;]+)"
)
_JSON_SECRET = re.compile(
    r"""(?i)(["'](?:api[_-]?key|access[_-]?token|token|secret|"""
    r"""password|passwd)["']\s*:\s*["'])[^"']*(["'])"""
)
_AUTHORIZATION = re.compile(
    r"(?im)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?"
    r"-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)


def sanitize_evidence(value: Any) -> str:
    """Remove terminal controls and common credential material."""
    text = _ANSI_ESCAPE.sub("", str(value or ""))
    text = _CONTROL.sub("", text)
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _AUTHORIZATION.sub(r"\1[REDACTED]", text)
    text = _JSON_SECRET.sub(r"\1[REDACTED]\2", text)
    return _ASSIGNED_SECRET.sub(r"\1\2[REDACTED]", text)


@dataclass(frozen=True)
class CollectedEvidence:
    target_id: int
    asset_alias: str
    probe_id: str
    title: str
    kind: str
    status: str
    content: str
    error: str
    truncated: bool
    untrusted: bool = True


class DiagnosticSourceAdapter(ABC):
    """Internal adapter interface; it is not a third-party plugin API."""

    @abstractmethod
    def collect(
        self,
        *,
        profile: DiagnosticProfile,
        targets: Sequence[Mapping[str, Any]],
        system_user_id: int,
        system_user: str,
        parameters: Mapping[str, Any],
        username: str = "AI Agent",
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> list[CollectedEvidence]:
        raise NotImplementedError


class SSHProbeAdapter(DiagnosticSourceAdapter):
    """Run only server-owned profile commands through the existing SSH path."""

    def __init__(
        self,
        *,
        batch_executor: Optional[Callable[..., Dict[str, Any]]] = None,
        max_item_chars: int = 32_768,
        max_total_chars: int = 262_144,
    ) -> None:
        if batch_executor is None:
            from app.assets.batch_service import execute_batch_command

            batch_executor = execute_batch_command
        self.batch_executor = batch_executor
        self.max_item_chars = max(256, int(max_item_chars))
        self.max_total_chars = max(self.max_item_chars, int(max_total_chars))

    def collect(
        self,
        *,
        profile: DiagnosticProfile,
        targets: Sequence[Mapping[str, Any]],
        system_user_id: int,
        system_user: str,
        parameters: Mapping[str, Any],
        username: str = "AI Agent",
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> list[CollectedEvidence]:
        validated = profile.validate_parameters(parameters)
        host_ids = [int(target["id"]) for target in targets]
        aliases = {int(target["id"]): str(target["alias"]) for target in targets}
        remaining = self.max_total_chars
        collected: list[CollectedEvidence] = []

        for probe in profile.probes:
            if remaining <= 0 or (should_cancel is not None and should_cancel()):
                break
            command = probe.command(validated)
            item_limit = min(
                self.max_item_chars,
                probe.max_output_chars,
                remaining,
            )

            def progress(
                item: Dict[str, Any],
                current_probe: Probe = probe,
            ) -> None:
                if on_progress is not None:
                    on_progress({
                        "target_id": item.get("host_id"),
                        "alias": item.get("alias"),
                        "probe_id": current_probe.id,
                        "status": item.get("status"),
                    })

            result = self.batch_executor(
                username=username,
                host_ids=host_ids,
                sys_user=system_user,
                sys_user_id=system_user_id,
                command=command,
                audit_source="AI Diagnostic",
                audit_ref=profile.id,
                max_output_chars=item_limit,
                command_timeout=probe.timeout_seconds,
                on_progress=progress,
            )
            for item in result.get("items") or []:
                target_id = int(item.get("host_id") or 0)
                raw_content = str(item.get("output") or "")
                content = sanitize_evidence(raw_content)
                truncated = bool(item.get("truncated"))
                if len(content) > item_limit:
                    content = content[:item_limit]
                    truncated = True
                if len(content) > remaining:
                    content = content[:remaining]
                    truncated = True
                remaining -= len(content)
                collected.append(CollectedEvidence(
                    target_id=target_id,
                    asset_alias=str(
                        item.get("alias") or aliases.get(target_id) or ""
                    ),
                    probe_id=probe.id,
                    title=probe.title,
                    kind=probe.kind,
                    status=str(item.get("status") or "failed"),
                    content=content,
                    error=sanitize_evidence(item.get("error"))[:2048],
                    truncated=truncated,
                ))
        return collected
