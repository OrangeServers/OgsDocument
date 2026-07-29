from types import SimpleNamespace
from pathlib import Path

from cryptography.fernet import Fernet
from flask import Flask
import smtplib


class _Query:
    def __init__(self, row):
        self.row = row

    def filter_by(self, **_kwargs):
        return self

    def first(self):
        return self.row


def _row():
    return SimpleNamespace(
        mail_smtp_host=None,
        mail_smtp_port=None,
        mail_smtp_security=None,
        mail_from=None,
        mail_password_encrypted=None,
    )


def test_admin_can_save_and_read_smtp_without_secret_disclosure(
    monkeypatch,
):
    monkeypatch.setenv(
        "OGS_FERNET_KEYS", Fernet.generate_key().decode("ascii")
    )
    from app.local import MailSettings
    from app.tools.basesec import decrypt_secret

    app = Flask(__name__)
    row = _row()
    with app.app_context():
        monkeypatch.setattr(
            MailSettings.t_settings, "query", _Query(row), raising=False
        )
    commit_calls = []
    monkeypatch.setattr(
        MailSettings.db.session,
        "commit",
        lambda: commit_calls.append(True),
    )

    app.add_url_rule(
        "/local/settings/mail/get",
        "mail_get",
        MailSettings.MailSettings.settings_get,
        methods=["POST"],
    )
    app.add_url_rule(
        "/local/settings/mail/update",
        "mail_update",
        MailSettings.MailSettings.settings_update,
        methods=["POST"],
    )
    client = app.test_client()

    saved = client.post(
        "/local/settings/mail/update",
        json={
            "smtp_host": "smtp.126.com",
            "smtp_port": 465,
            "security": "ssl",
            "from_email": "orange-test@126.com",
            "password": "smtp-authorization-code",
        },
    )

    assert saved.status_code == 200
    assert saved.get_json() == {"code": 0}
    assert commit_calls == [True]
    assert row.mail_password_encrypted.startswith("gAAAAA")
    assert (
        decrypt_secret(row.mail_password_encrypted)
        == "smtp-authorization-code"
    )

    loaded = client.post("/local/settings/mail/get")
    body = loaded.get_json()
    assert body == {
        "code": 0,
        "smtp_host": "smtp.126.com",
        "smtp_port": 465,
        "security": "ssl",
        "from_email": "orange-test@126.com",
        "password_configured": True,
        "source": "database",
    }
    assert "password" not in body
    assert "mail_password_encrypted" not in body


def test_runtime_mail_configuration_prefers_database_over_environment(
    monkeypatch,
):
    monkeypatch.setenv(
        "OGS_FERNET_KEYS", Fernet.generate_key().decode("ascii")
    )
    monkeypatch.setenv("OGS_MAIL_USER", "fallback@example.com")
    monkeypatch.setenv("OGS_MAIL_PASSWORD", "fallback-password")
    monkeypatch.setenv("OGS_MAIL_SMTP", "smtp.example.com")
    monkeypatch.setenv("OGS_MAIL_PORT", "587")
    monkeypatch.setenv("OGS_MAIL_USE_TLS", "true")
    monkeypatch.setenv("OGS_MAIL_USE_SSL", "false")
    from app.mail.config import resolve_mail_configuration
    from app.tools.basesec import encrypt_secret

    row = _row()
    row.mail_smtp_host = "smtp.126.com"
    row.mail_smtp_port = 465
    row.mail_smtp_security = "ssl"
    row.mail_from = "database@126.com"
    row.mail_password_encrypted = encrypt_secret("database-password")

    resolved = resolve_mail_configuration(row=row)

    assert resolved.public_dict() == {
        "smtp_host": "smtp.126.com",
        "smtp_port": 465,
        "security": "ssl",
        "from_email": "database@126.com",
        "password_configured": True,
        "source": "database",
    }
    assert resolved.password == "database-password"


def test_runtime_mail_configuration_falls_back_to_environment(monkeypatch):
    monkeypatch.setenv("OGS_MAIL_USER", "fallback@example.com")
    monkeypatch.setenv("OGS_MAIL_PASSWORD", "fallback-password")
    monkeypatch.setenv("OGS_MAIL_SMTP", "smtp.example.com")
    monkeypatch.setenv("OGS_MAIL_PORT", "587")
    monkeypatch.setenv("OGS_MAIL_USE_TLS", "true")
    monkeypatch.setenv("OGS_MAIL_USE_SSL", "false")
    from app.mail.config import resolve_mail_configuration

    resolved = resolve_mail_configuration(row=_row())

    assert resolved.public_dict() == {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "security": "starttls",
        "from_email": "fallback@example.com",
        "password_configured": True,
        "source": "environment",
    }
    assert resolved.password == "fallback-password"


def test_admin_can_send_test_mail_without_saving_candidate(monkeypatch):
    from app.local import MailSettings

    calls = []
    monkeypatch.setattr(
        MailSettings,
        "test_mail_configuration",
        lambda payload, send_to=None, fallback_password=None: calls.append(
            (payload, send_to, fallback_password)
        ),
        raising=False,
    )
    app = Flask(__name__)
    app.add_url_rule(
        "/local/settings/mail/test",
        "mail_test",
        MailSettings.MailSettings.settings_test,
        methods=["POST"],
    )
    client = app.test_client()
    payload = {
        "smtp_host": "smtp.126.com",
        "smtp_port": 465,
        "security": "ssl",
        "from_email": "orange-test@126.com",
        "password": "candidate-authorization-code",
        "send_to": "receiver@example.com",
    }

    response = client.post("/local/settings/mail/test", json=payload)

    assert response.status_code == 200
    assert response.get_json() == {
        "code": 0,
        "msg": "SMTP test email sent",
    }
    assert calls == [(payload, "receiver@example.com", None)]


def test_smtp_test_failure_is_sanitized_and_never_echoes_authorization_code(
    monkeypatch,
):
    from app.local import MailSettings

    monkeypatch.setattr(
        MailSettings,
        "test_mail_configuration",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            smtplib.SMTPAuthenticationError(
                535,
                b"authorization-code-must-not-leak",
            )
        ),
    )
    app = Flask(__name__)
    app.add_url_rule(
        "/local/settings/mail/test",
        "mail_test_failure",
        MailSettings.MailSettings.settings_test,
        methods=["POST"],
    )

    response = app.test_client().post(
        "/local/settings/mail/test",
        json={
            "smtp_host": "smtp.126.com",
            "smtp_port": 465,
            "security": "ssl",
            "from_email": "orange-test@126.com",
            "password": "authorization-code-must-not-leak",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["code"] == 100
    assert body["msg"] == "SMTP authentication failed"
    assert "authorization-code" not in str(body)


def test_saved_authorization_code_can_be_reused_for_smtp_test(monkeypatch):
    monkeypatch.setenv(
        "OGS_FERNET_KEYS", Fernet.generate_key().decode("ascii")
    )
    from app.local import MailSettings
    from app.tools.basesec import encrypt_secret

    row = _row()
    row.mail_smtp_host = "smtp.126.com"
    row.mail_smtp_port = 465
    row.mail_smtp_security = "ssl"
    row.mail_from = "orange-test@126.com"
    row.mail_password_encrypted = encrypt_secret(
        "saved-authorization-code"
    )
    calls = []
    app = Flask(__name__)
    with app.app_context():
        monkeypatch.setattr(
            MailSettings.t_settings, "query", _Query(row), raising=False
        )
    monkeypatch.setattr(
        MailSettings,
        "test_mail_configuration",
        lambda payload, send_to=None, fallback_password=None: calls.append(
            fallback_password
        ),
    )
    app.add_url_rule(
        "/local/settings/mail/test",
        "mail_test_saved_secret",
        MailSettings.MailSettings.settings_test,
        methods=["POST"],
    )

    response = app.test_client().post(
        "/local/settings/mail/test",
        json={
            "smtp_host": "smtp.126.com",
            "smtp_port": 465,
            "security": "ssl",
            "from_email": "orange-test@126.com",
            "password": "",
        },
    )

    assert response.get_json()["code"] == 0
    assert calls == ["saved-authorization-code"]


def test_saving_environment_backed_form_can_keep_effective_secret(
    monkeypatch,
):
    monkeypatch.setenv(
        "OGS_FERNET_KEYS", Fernet.generate_key().decode("ascii")
    )
    monkeypatch.setenv("OGS_MAIL_USER", "fallback@example.com")
    monkeypatch.setenv("OGS_MAIL_PASSWORD", "environment-password")
    monkeypatch.setenv("OGS_MAIL_SMTP", "smtp.example.com")
    monkeypatch.setenv("OGS_MAIL_PORT", "587")
    monkeypatch.setenv("OGS_MAIL_USE_TLS", "true")
    monkeypatch.setenv("OGS_MAIL_USE_SSL", "false")
    from app.local import MailSettings
    from app.tools.basesec import decrypt_secret

    row = _row()
    app = Flask(__name__)
    with app.app_context():
        monkeypatch.setattr(
            MailSettings.t_settings, "query", _Query(row), raising=False
        )
    monkeypatch.setattr(
        MailSettings.db.session, "commit", lambda: None
    )
    app.add_url_rule(
        "/local/settings/mail/update",
        "mail_update_from_environment",
        MailSettings.MailSettings.settings_update,
        methods=["POST"],
    )

    response = app.test_client().post(
        "/local/settings/mail/update",
        json={
            "smtp_host": "smtp.custom.example",
            "smtp_port": 465,
            "security": "ssl",
            "from_email": "fallback@example.com",
            "password": "",
        },
    )

    assert response.get_json()["code"] == 0
    assert decrypt_secret(row.mail_password_encrypted) == (
        "environment-password"
    )


def test_invalid_saved_secret_returns_sanitized_business_error(monkeypatch):
    from app.local import MailSettings

    row = _row()
    row.mail_smtp_host = "smtp.126.com"
    row.mail_smtp_port = 465
    row.mail_smtp_security = "ssl"
    row.mail_from = "orange-test@126.com"
    row.mail_password_encrypted = "corrupt-ciphertext-must-not-leak"
    app = Flask(__name__)
    with app.app_context():
        monkeypatch.setattr(
            MailSettings.t_settings, "query", _Query(row), raising=False
        )
    app.add_url_rule(
        "/local/settings/mail/get",
        "mail_get_invalid_secret",
        MailSettings.MailSettings.settings_get,
        methods=["POST"],
    )
    app.add_url_rule(
        "/local/settings/mail/test",
        "mail_test_invalid_secret",
        MailSettings.MailSettings.settings_test,
        methods=["POST"],
    )

    client = app.test_client()
    loaded = client.post("/local/settings/mail/get")
    tested = client.post(
        "/local/settings/mail/test",
        json={
            "smtp_host": "smtp.126.com",
            "smtp_port": 465,
            "security": "ssl",
            "from_email": "orange-test@126.com",
            "password": "",
        },
    )

    for response in (loaded, tested):
        assert response.status_code == 200
        body = response.get_json()
        assert body == {
            "code": 100,
            "msg": "saved SMTP authorization code cannot be decrypted",
        }
        assert "corrupt-ciphertext" not in str(body)


def test_candidate_ssl_configuration_controls_the_real_smtp_transport(
    monkeypatch,
):
    from app.mail.config import MailConfiguration, build_mailer
    from app.tools import sendmail

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def login(self, username, password):
            calls.append(("login", username, password))

        def noop(self):
            calls.append(("noop",))
            return 250, b"ok"

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(sendmail.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(
        sendmail.smtplib,
        "SMTP",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("plain SMTP must not be used for SSL mode")
        ),
    )
    mailer = build_mailer(
        MailConfiguration(
            smtp_host="smtp.126.com",
            smtp_port=465,
            security="ssl",
            from_email="orange-test@126.com",
            password="authorization-code",
            source="candidate",
        )
    )

    mailer.verify()
    mailer.close()

    assert calls == [
        ("connect", "smtp.126.com", 465, sendmail.SMTP_CONNECT_TIMEOUT),
        ("login", "orange-test@126.com", "authorization-code"),
        ("noop",),
        ("close",),
    ]


def test_registration_mail_reports_unconfigured_service_instead_of_500(
    monkeypatch,
):
    from app.users import user

    monkeypatch.setattr(
        user, "resolve_mail_configuration", lambda: None, raising=False
    )
    monkeypatch.setattr(
        user,
        "build_mailer",
        lambda _config: (_ for _ in ()).throw(
            AssertionError("mailer must not be built without configuration")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        user,
        "ConnRedis",
        lambda: SimpleNamespace(conn=SimpleNamespace()),
    )
    app = Flask(__name__)
    app.add_url_rule(
        "/mail/send_user_mail",
        "registration_mail",
        lambda: user.CheckMail().send(),
        methods=["POST"],
    )

    response = app.test_client().post(
        "/mail/send_user_mail",
        json={"email": "new-user@example.com"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "code": 100,
        "msg": "管理员尚未配置邮件服务",
    }


def test_clean_and_existing_databases_have_smtp_setting_columns():
    from app.core.db.database import t_settings

    expected = {
        "mail_smtp_host",
        "mail_smtp_port",
        "mail_smtp_security",
        "mail_from",
        "mail_password_encrypted",
    }
    assert expected <= set(t_settings.__table__.columns.keys())

    backend_root = Path(__file__).resolve().parents[1]
    baseline = (
        backend_root / "mysqldir" / "orange.sql"
    ).read_text(encoding="utf-8")
    migration = (
        backend_root / "mysqldir" / "rev52_smtp_settings.sql"
    ).read_text(encoding="utf-8")
    for column in expected:
        assert f"`{column}`" in baseline
        assert f"`{column}`" in migration
