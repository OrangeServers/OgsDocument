"""Runtime SMTP configuration backed by encrypted settings."""
from __future__ import annotations

import re
import os
from dataclasses import dataclass
from typing import Any, Mapping
from sqlalchemy.exc import SQLAlchemyError

from app.tools.basesec import decrypt_secret, encrypt_secret
from app.tools.sendmail import _validate_email


_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[A-Za-z0-9-]{1,63}\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62})$"
)
_SECURITY = frozenset({"ssl", "starttls", "none"})
_ROW_UNSET = object()


class MailConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class MailConfiguration:
    smtp_host: str
    smtp_port: int
    security: str
    from_email: str
    password: str
    source: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "security": self.security,
            "from_email": self.from_email,
            "password_configured": bool(self.password),
            "source": self.source,
        }


def _normalized_fields(payload: Mapping[str, Any]) -> tuple[str, int, str, str]:
    smtp_host = str(payload.get("smtp_host") or "").strip()
    if not _HOST_RE.fullmatch(smtp_host):
        raise MailConfigurationError("invalid SMTP host")
    try:
        smtp_port = int(payload.get("smtp_port"))
    except (TypeError, ValueError) as exc:
        raise MailConfigurationError("invalid SMTP port") from exc
    if not 1 <= smtp_port <= 65535:
        raise MailConfigurationError("invalid SMTP port")
    security = str(payload.get("security") or "").strip().lower()
    if security not in _SECURITY:
        raise MailConfigurationError("invalid SMTP security mode")
    from_email = str(payload.get("from_email") or "").strip()
    try:
        _validate_email(from_email)
    except Exception as exc:
        raise MailConfigurationError("invalid sender email") from exc
    return smtp_host, smtp_port, security, from_email


def configuration_from_row(row: Any) -> MailConfiguration | None:
    if row is None:
        return None
    ciphertext = getattr(row, "mail_password_encrypted", None)
    values = (
        getattr(row, "mail_smtp_host", None),
        getattr(row, "mail_smtp_port", None),
        getattr(row, "mail_smtp_security", None),
        getattr(row, "mail_from", None),
        ciphertext,
    )
    if not all(values):
        return None
    password = decrypt_secret(ciphertext)
    if not password:
        return None
    return MailConfiguration(
        smtp_host=str(values[0]),
        smtp_port=int(values[1]),
        security=str(values[2]),
        from_email=str(values[3]),
        password=password,
        source="database",
    )


def resolve_mail_configuration(
    *, row: Any = _ROW_UNSET
) -> MailConfiguration | None:
    if row is _ROW_UNSET:
        from app.core.db.database import t_settings

        try:
            row = t_settings.query.filter_by(name="default").first()
        except SQLAlchemyError:
            row = None
    database_config = configuration_from_row(row)
    if database_config is not None:
        return database_config

    password = os.getenv("OGS_MAIL_PASSWORD", "").strip()
    payload = {
        "smtp_host": os.getenv("OGS_MAIL_SMTP", "").strip(),
        "smtp_port": os.getenv("OGS_MAIL_PORT", "587").strip(),
        "security": (
            "ssl"
            if os.getenv("OGS_MAIL_USE_SSL", "false").lower()
            in ("1", "true", "yes", "on")
            else "starttls"
            if os.getenv("OGS_MAIL_USE_TLS", "true").lower()
            in ("1", "true", "yes", "on")
            else "none"
        ),
        "from_email": os.getenv("OGS_MAIL_USER", "").strip(),
    }
    if not password:
        return None
    try:
        smtp_host, smtp_port, security, from_email = _normalized_fields(
            payload
        )
    except MailConfigurationError:
        return None
    return MailConfiguration(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        security=security,
        from_email=from_email,
        password=password,
        source="environment",
    )


def save_configuration(
    row: Any,
    payload: Mapping[str, Any],
    *,
    fallback_password: str | None = None,
) -> None:
    smtp_host, smtp_port, security, from_email = _normalized_fields(payload)
    password_value = payload.get("password")
    password = str(password_value).strip() if password_value is not None else ""
    if password:
        row.mail_password_encrypted = encrypt_secret(password)
    elif getattr(row, "mail_password_encrypted", None):
        pass
    elif fallback_password:
        row.mail_password_encrypted = encrypt_secret(fallback_password)
    else:
        raise MailConfigurationError("SMTP authorization code is required")
    row.mail_smtp_host = smtp_host
    row.mail_smtp_port = smtp_port
    row.mail_smtp_security = security
    row.mail_from = from_email


def configuration_from_payload(
    payload: Mapping[str, Any],
    *,
    fallback_password: str | None = None,
) -> MailConfiguration:
    smtp_host, smtp_port, security, from_email = _normalized_fields(payload)
    password = str(payload.get("password") or fallback_password or "").strip()
    if not password:
        raise MailConfigurationError("SMTP authorization code is required")
    return MailConfiguration(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        security=security,
        from_email=from_email,
        password=password,
        source="candidate",
    )


def build_mailer(config: MailConfiguration, *, mailer_factory=None):
    if mailer_factory is None:
        from app.tools.sendmail import SendMail

        mailer_factory = SendMail

    return mailer_factory(
        config.from_email,
        config.password,
        config.smtp_host,
        port=config.smtp_port,
        use_ssl=config.security == "ssl",
        use_tls=config.security == "starttls",
    )


def test_mail_configuration(
    payload: Mapping[str, Any],
    send_to: str | None = None,
    fallback_password: str | None = None,
) -> None:
    config = configuration_from_payload(
        payload, fallback_password=fallback_password
    )
    mailer = build_mailer(config)
    try:
        if send_to:
            try:
                _validate_email(send_to)
            except Exception as exc:
                raise MailConfigurationError(
                    "invalid test recipient email"
                ) from exc
            mailer.send(
                send_to,
                "OrangeServer",
                "OrangeServer SMTP test",
                "Your OrangeServer SMTP configuration is working.",
            )
        else:
            mailer.verify()
    finally:
        mailer.close()
