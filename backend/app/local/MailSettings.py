"""Administrator-facing SMTP settings endpoints."""
import smtplib
import socket

from flask import jsonify, request

from app.core.db.database import db, t_settings
from app.mail.config import (
    MailConfigurationError,
    resolve_mail_configuration,
    save_configuration,
    test_mail_configuration,
)

_SAVED_SECRET_ERROR = "saved SMTP authorization code cannot be decrypted"


class MailSettings:
    @staticmethod
    def settings_get():
        row = t_settings.query.filter_by(name="default").first()
        try:
            config = resolve_mail_configuration(row=row)
        except (RuntimeError, ValueError):
            return jsonify({"code": 100, "msg": _SAVED_SECRET_ERROR})
        if config is None:
            return jsonify({
                "code": 0,
                "smtp_host": "",
                "smtp_port": 587,
                "security": "starttls",
                "from_email": "",
                "password_configured": False,
                "source": "none",
            })
        return jsonify({"code": 0, **config.public_dict()})

    @staticmethod
    def settings_update():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = request.form.to_dict(flat=True)
        row = t_settings.query.filter_by(name="default").first()
        if row is None:
            return jsonify({"code": 100, "msg": "system settings not found"})
        try:
            effective = resolve_mail_configuration(row=row)
            save_configuration(
                row,
                payload,
                fallback_password=(
                    effective.password if effective is not None else None
                ),
            )
            db.session.commit()
        except MailConfigurationError as exc:
            db.session.rollback()
            return jsonify({"code": 100, "msg": str(exc)})
        except (RuntimeError, ValueError):
            db.session.rollback()
            return jsonify({"code": 100, "msg": _SAVED_SECRET_ERROR})
        return jsonify({"code": 0})

    @staticmethod
    def settings_test():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = request.form.to_dict(flat=True)
        send_to = str(payload.get("send_to") or "").strip() or None
        fallback_password = None
        try:
            if not str(payload.get("password") or "").strip():
                row = t_settings.query.filter_by(name="default").first()
                existing = resolve_mail_configuration(row=row)
                fallback_password = existing.password if existing else None
            test_mail_configuration(
                payload,
                send_to=send_to,
                fallback_password=fallback_password,
            )
        except MailConfigurationError as exc:
            return jsonify({"code": 100, "msg": str(exc)[:200]})
        except (RuntimeError, ValueError):
            return jsonify({"code": 100, "msg": _SAVED_SECRET_ERROR})
        except smtplib.SMTPAuthenticationError:
            return jsonify({
                "code": 100,
                "msg": "SMTP authentication failed",
            })
        except (
            smtplib.SMTPException,
            socket.timeout,
            ConnectionError,
            OSError,
        ):
            return jsonify({
                "code": 100,
                "msg": "SMTP connection or delivery failed",
            })
        return jsonify({
            "code": 0,
            "msg": (
                "SMTP test email sent"
                if send_to
                else "SMTP connection verified"
            ),
        })
