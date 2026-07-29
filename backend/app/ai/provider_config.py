"""Database-backed configuration for OpenAI-compatible model providers."""
from __future__ import annotations

import json
import ipaddress
import socket
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

from app.ai.context import (
    DEEP_CONTEXT_MODE,
    DEEP_CONTEXT_TOKENS,
    STANDARD_CONTEXT_MODE,
    STANDARD_CONTEXT_TOKENS,
    normalize_context_mode,
    resolve_context_window,
)
from app.ai.provider import (
    PROVIDER_PRESETS,
    OpenAICompatibleAdapter,
    ProviderPreset,
)
from app.core.db.database import db, t_ai_provider
from app.tools.basesec import decrypt_secret, encrypt_secret
from app.core.config import _env


MAX_DISCOVERED_MODELS = 200


class ProviderConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderRuntime:
    adapter: OpenAICompatibleAdapter
    context_window_tokens: int


def _json_object(value: Any) -> Dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError) as exc:
        raise ProviderConfigError("extra_body 必须是合法 JSON object") from exc
    if not isinstance(parsed, dict):
        raise ProviderConfigError("extra_body 必须是 JSON object")
    return parsed


def _valid_base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ProviderConfigError("Base URL 必须是有效的 HTTPS 地址")
    if parsed.username or parsed.password:
        raise ProviderConfigError("Base URL 不能包含用户名或密码")
    if not parsed.hostname:
        raise ProviderConfigError("Base URL 缺少主机名")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(".local"):
        raise ProviderConfigError("Base URL 不允许指向本机或本地域名")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    ):
        raise ProviderConfigError("Base URL 不允许指向私网或保留地址")
    return value


def _assert_public_destination(value: str) -> None:
    if _env("OGS_AI_ALLOW_PRIVATE_PROVIDER", "0") == "1":
        return
    parsed = urlparse(_valid_base_url(value))
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or 443,
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise ProviderConfigError("模型服务域名无法解析") from exc
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            raise ProviderConfigError("模型服务域名解析到私网或保留地址")


def _strict_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "1", "0"):
        return value.strip().lower() in ("true", "1")
    raise ProviderConfigError(f"{field} 必须是 boolean")


def _context_window_tokens(value: Any) -> int:
    if isinstance(value, bool):
        raise ProviderConfigError("模型上下文能力只支持 256K 或 1M")
    try:
        tokens = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ProviderConfigError("模型上下文能力只支持 256K 或 1M") from exc
    if tokens not in (STANDARD_CONTEXT_TOKENS, DEEP_CONTEXT_TOKENS):
        raise ProviderConfigError("模型上下文能力只支持 256K 或 1M")
    return tokens


def _row_context_window_tokens(row: Optional[t_ai_provider]) -> int:
    if row is None:
        return STANDARD_CONTEXT_TOKENS
    value = getattr(row, "context_window_tokens", STANDARD_CONTEXT_TOKENS)
    try:
        return _context_window_tokens(value)
    except ProviderConfigError:
        return STANDARD_CONTEXT_TOKENS


class ProviderConfigService:
    """Keeps secrets server-side and centralizes default-provider invariants."""

    def _row(self, code: str) -> Optional[t_ai_provider]:
        return t_ai_provider.query.filter_by(provider_code=code).first()

    @staticmethod
    def _preset(code: str) -> ProviderPreset:
        preset = PROVIDER_PRESETS.get(code)
        if preset is None:
            raise ProviderConfigError("不支持的模型厂商")
        return preset

    @staticmethod
    def _configured(row: Optional[t_ai_provider]) -> bool:
        return bool(row and row.api_key_ciphertext and row.model)

    def public_rows(self) -> Dict[str, Any]:
        rows = sorted(
            t_ai_provider.query.all(),
            key=lambda row: (
                not bool(row.is_default),
                int(row.id or 0),
            ),
        )
        providers = []
        default_provider = None
        for row in rows:
            # Empty seed rows are admin configuration placeholders, not useful
            # choices for the Agent page. Partially configured or explicitly
            # enabled rows remain visible with a machine-readable reason.
            if not row.enabled and not row.api_key_ciphertext and not row.model:
                continue
            preset = self._preset(row.provider_code)
            if not row.enabled:
                reason = "disabled"
            elif not row.api_key_ciphertext:
                reason = "key_missing"
            elif not row.model:
                reason = "model_missing"
            else:
                reason = None
            available = reason is None
            providers.append({
                "provider_code": row.provider_code,
                "name": preset.name,
                "display_name": preset.name,
                "model": row.model,
                "context_window_tokens": _row_context_window_tokens(row),
                "is_default": bool(row.is_default),
                "available": available,
                "reason": reason,
            })
            if available and row.is_default and default_provider is None:
                default_provider = row.provider_code
        if default_provider is None and providers:
            default_provider = next(
                (
                    item["provider_code"]
                    for item in providers
                    if item["available"]
                ),
                None,
            )
        return {"providers": providers, "default_provider": default_provider}

    def admin_rows(self) -> list[Dict[str, Any]]:
        saved = {
            row.provider_code: row
            for row in t_ai_provider.query.all()
        }
        result = []
        for code, preset in PROVIDER_PRESETS.items():
            row = saved.get(code)
            result.append({
                "provider_code": code,
                "name": preset.name,
                "display_name": preset.name,
                "base_url": row.base_url if row else preset.base_url,
                "model": row.model if row else "",
                "note": preset.note,
                "context_window_tokens": _row_context_window_tokens(row),
                "enabled": bool(row and row.enabled),
                "is_default": bool(row and row.is_default),
                "api_key_configured": bool(row and row.api_key_ciphertext),
                "extra_body": _json_object(row.extra_body_json) if row else {},
                "created_at": row.created_at.isoformat() if row and row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            })
        return result

    def save(self, code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        preset = self._preset(code)
        row = self._row(code)
        if row is None:
            row = t_ai_provider(
                provider_code=code,
                base_url=preset.base_url,
                model="",
            )
            db.session.add(row)

        if "base_url" in payload:
            row.base_url = _valid_base_url(payload.get("base_url"))
        elif not row.base_url:
            row.base_url = preset.base_url

        if "model" in payload:
            row.model = str(payload.get("model") or "").strip()[:128]
        if "context_window_tokens" in payload:
            row.context_window_tokens = _context_window_tokens(
                payload.get("context_window_tokens")
            )
        if "extra_body" in payload or "extra_body_json" in payload:
            extra = _json_object(payload.get("extra_body", payload.get("extra_body_json")))
            row.extra_body_json = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))

        api_key = payload.get("api_key")
        if api_key is not None and str(api_key).strip():
            row.api_key_ciphertext = encrypt_secret(str(api_key).strip())

        enabled = _strict_bool(payload.get("enabled", bool(row.enabled)), "enabled")
        is_default = _strict_bool(
            payload.get("is_default", bool(row.is_default)),
            "is_default",
        )
        if (enabled or is_default) and (not row.model or not row.api_key_ciphertext):
            raise ProviderConfigError("启用模型服务前必须填写模型名称和 API Key")
        if is_default:
            enabled = True
            t_ai_provider.query.with_for_update().all()
            t_ai_provider.query.filter(
                t_ai_provider.provider_code != code
            ).update({"is_default": False}, synchronize_session=False)
        row.enabled = enabled
        row.is_default = is_default
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return next(item for item in self.admin_rows() if item["provider_code"] == code)

    def clear_key(self, code: str) -> Dict[str, Any]:
        self._preset(code)
        row = self._row(code)
        if row is None:
            raise ProviderConfigError("模型服务尚未配置")
        row.api_key_ciphertext = None
        row.enabled = False
        row.is_default = False
        db.session.commit()
        return next(item for item in self.admin_rows() if item["provider_code"] == code)

    def configured_row(
        self,
        code: Optional[str] = None,
        *,
        require_enabled: bool = True,
    ) -> t_ai_provider:
        query = t_ai_provider.query
        if require_enabled:
            query = query.filter_by(enabled=True)
        if code:
            row = query.filter_by(provider_code=code).first()
        else:
            row = query.filter_by(is_default=True).first()
            if row is None:
                row = query.order_by(t_ai_provider.id.asc()).first()
        if row is None or not self._configured(row):
            raise ProviderConfigError("所选模型服务未启用或配置不完整")
        return row

    def adapter(
        self,
        code: Optional[str] = None,
        *,
        require_enabled: bool = True,
    ) -> OpenAICompatibleAdapter:
        return self.runtime(
            code,
            require_enabled=require_enabled,
            context_mode=STANDARD_CONTEXT_MODE,
        ).adapter

    @staticmethod
    def context_mode(
        row: t_ai_provider,
        requested: Any = None,
    ) -> str:
        try:
            mode = normalize_context_mode(requested)
            resolve_context_window(mode, _row_context_window_tokens(row))
        except ValueError as exc:
            raise ProviderConfigError(str(exc)) from exc
        return mode

    def runtime(
        self,
        code: Optional[str] = None,
        *,
        require_enabled: bool = True,
        context_mode: Any = None,
    ) -> ProviderRuntime:
        row = self.configured_row(code, require_enabled=require_enabled)
        mode = self.context_mode(row, context_mode)
        context_window_tokens = resolve_context_window(
            mode,
            _row_context_window_tokens(row),
        )
        _assert_public_destination(row.base_url)
        api_key = decrypt_secret(row.api_key_ciphertext)
        if not api_key:
            raise ProviderConfigError("模型服务 API Key 无法读取")
        return ProviderRuntime(
            adapter=OpenAICompatibleAdapter(
                api_key=api_key,
                base_url=row.base_url,
                model=row.model,
                extra_body=_json_object(row.extra_body_json),
            ),
            context_window_tokens=context_window_tokens,
        )

    def discover_models(
        self,
        code: str,
        *,
        client_factory=None,
    ) -> Dict[str, Any]:
        """Fetch model IDs without exposing the saved provider credential."""
        self._preset(code)
        row = self._row(code)
        if row is None or not row.api_key_ciphertext:
            raise ProviderConfigError("模型服务尚未配置 API Key")

        _assert_public_destination(row.base_url)
        api_key = decrypt_secret(row.api_key_ciphertext)
        if not api_key:
            raise ProviderConfigError("模型服务 API Key 无法读取")

        # Reuse the existing OpenAI-compatible client construction and timeout.
        # Model discovery intentionally works before a model is selected or the
        # provider is enabled.
        adapter = OpenAICompatibleAdapter(
            api_key=api_key,
            base_url=row.base_url,
            model=row.model or "__model_discovery__",
            client_factory=client_factory,
        )
        response = adapter.list_models()
        values = response.get("data", []) if isinstance(response, dict) else getattr(
            response,
            "data",
            response,
        )
        normalized = set()
        for item in values or []:
            raw_id = (
                item.get("id")
                if isinstance(item, dict)
                else getattr(item, "id", None)
            )
            if not isinstance(raw_id, str):
                continue
            model_id = raw_id.strip()
            if model_id:
                normalized.add(model_id)

        sorted_ids = sorted(normalized)
        models = sorted_ids[:MAX_DISCOVERED_MODELS]
        return {
            "provider_code": row.provider_code,
            "models": models,
            "total": len(models),
            "truncated": len(sorted_ids) > MAX_DISCOVERED_MODELS,
        }

    def test(self, code: str) -> Dict[str, Any]:
        row = self.configured_row(code, require_enabled=False)
        adapter = self.adapter(code, require_enabled=False)
        tool_name = "orangeserver_connection_test"
        result = adapter.complete(
            messages=[{
                "role": "user",
                "content": "调用 orangeserver_connection_test 工具，不要直接回答。",
            }],
            tools=[{
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": "验证模型是否支持 Tool Calling。",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }],
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )
        if not any(call.name == tool_name for call in result.tool_calls):
            raise ProviderConfigError("连接成功，但模型未返回 Tool Call")
        return {
            "provider_code": row.provider_code,
            "model": row.model,
            "tool_calling": True,
            "streaming": bool(result.used_stream),
        }
