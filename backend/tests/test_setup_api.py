# -*- coding: utf-8 -*-
"""SETUP-WIZARD: setup app 接口门禁与编排。"""
import importlib
import json
import os
from unittest import mock

import pytest

from setup import security, state
import setup.app as setup_app_module


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith('OGS_'):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('OGS_DATA_DIR', str(tmp_path))
    importlib.reload(state)
    # 重置进程内限流状态
    security._FAILS.update({'count': 0, 'locked_until': 0.0})
    yield


@pytest.fixture()
def client():
    app = setup_app_module.create_setup_app()
    app.testing = True
    return app.test_client()


def _token():
    return state.token_path().read_text(encoding='utf-8').strip()


class TestGuards:
    def test_status_is_anonymous(self, client):
        res = client.get('/setup/api/status')
        assert res.status_code == 200
        body = res.get_json()
        assert body['mode'] == 'setup'
        assert 'OGS_FLASK_SECRET_KEY' in body['missing']

    def test_write_requires_token(self, client):
        assert client.post('/setup/api/verify_token', json={}).status_code == 401

    def test_valid_token_passes(self, client):
        res = client.post(
            '/setup/api/verify_token', headers={'X-Setup-Token': _token()},
        )
        assert res.status_code == 200

    def test_cross_origin_rejected(self, client):
        res = client.post(
            '/setup/api/verify_token',
            headers={'X-Setup-Token': _token(), 'Origin': 'http://evil.example'},
        )
        assert res.status_code == 403

    def test_token_rate_limit_locks(self, client):
        for _ in range(security.FAIL_LIMIT):
            client.post('/setup/api/verify_token', headers={'X-Setup-Token': 'wrong'})
        # 锁定期内即使正确 token 也拒绝
        res = client.post(
            '/setup/api/verify_token', headers={'X-Setup-Token': _token()},
        )
        assert res.status_code == 401

    def test_business_catchall_503(self, client):
        res = client.post('/ai/chat')
        assert res.status_code == 503
        assert res.get_json()['setup_required'] is True

    def test_setup_health_is_live_while_configuration_is_pending(self, client):
        res = client.get('/local/health')
        assert res.status_code == 200
        assert res.get_json() == {
            'status': 'setup',
            'setup_required': True,
        }

    def test_setup_auth_probe_redirect_signal_does_not_log_http_error(self, client):
        res = client.post('/local/app_auth_ck')
        assert res.status_code == 200
        assert res.get_json()['setup_required'] is True

    def test_prefill_requires_token_and_never_returns_passwords(self, client, monkeypatch):
        monkeypatch.setenv('OGS_MYSQL_HOST', 'mysql')
        monkeypatch.setenv('OGS_MYSQL_PORT', '3306')
        monkeypatch.setenv('OGS_MYSQL_DBNAME', 'orange')
        monkeypatch.setenv('OGS_MYSQL_USER', 'app_user')
        monkeypatch.setenv('OGS_MYSQL_PASSWORD', 'must-not-leak')
        monkeypatch.setenv('OGS_REDIS_HOST', 'redis')
        monkeypatch.setenv('OGS_REDIS_PASSWORD', 'must-not-leak-either')

        assert client.get('/setup/api/prefill').status_code == 401
        res = client.get(
            '/setup/api/prefill', headers={'X-Setup-Token': _token()},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body['mysql'] == {
            'host': 'mysql',
            'port': 3306,
            'dbname': 'orange',
            'user': 'app_user',
            'password_configured': True,
        }
        assert body['redis']['host'] == 'redis'
        assert body['redis']['password_configured'] is True
        assert 'must-not-leak' not in json.dumps(body)

    def test_locked_environment_is_used_for_connection_tests(self, client, monkeypatch):
        locked = {
            'OGS_MYSQL_HOST': 'mysql',
            'OGS_MYSQL_PORT': '3306',
            'OGS_MYSQL_DBNAME': 'orange',
            'OGS_MYSQL_USER': 'app_user',
            'OGS_MYSQL_PASSWORD': 'mysql-secret',
            'OGS_REDIS_HOST': 'redis',
            'OGS_REDIS_PORT': '6379',
            'OGS_REDIS_PASSWORD': 'redis-secret',
            'OGS_REDIS_DB': '0',
        }
        for key, value in locked.items():
            monkeypatch.setenv(key, value)

        with mock.patch.object(
            setup_app_module.checks, 'test_mysql',
            return_value={'ok': True, 'msg': 'ok'},
        ) as mysql_check, mock.patch.object(
            setup_app_module.checks, 'test_redis',
            return_value={'ok': True, 'msg': 'ok'},
        ) as redis_check:
            mysql_res = client.post(
                '/setup/api/test_mysql',
                headers={'X-Setup-Token': _token()},
                json={'host': '', 'user': '', 'password': ''},
            )
            redis_res = client.post(
                '/setup/api/test_redis',
                headers={'X-Setup-Token': _token()},
                json={'host': '', 'password': ''},
            )

        assert mysql_res.get_json()['ok'] is True
        assert redis_res.get_json()['ok'] is True
        assert mysql_check.call_args.args[0] == {
            'host': 'mysql',
            'port': '3306',
            'dbname': 'orange',
            'user': 'app_user',
            'password': 'mysql-secret',
        }
        assert redis_check.call_args.args[0] == {
            'host': 'redis',
            'port': '6379',
            'password': 'redis-secret',
            'db': '0',
        }

    def test_optional_smtp_connection_test_is_token_protected(
        self, client,
    ):
        payload = {
            'smtp_host': 'smtp.126.com',
            'smtp_port': 465,
            'security': 'ssl',
            'from_email': 'orange-test@126.com',
            'password': 'authorization-code',
            'send_to': 'receiver@example.com',
        }
        assert client.post(
            '/setup/api/test_smtp', json=payload,
        ).status_code == 401

        with mock.patch.object(
            setup_app_module.checks,
            'test_smtp',
            return_value={'ok': True, 'msg': 'SMTP test email sent'},
        ) as smtp_check:
            response = client.post(
                '/setup/api/test_smtp',
                headers={'X-Setup-Token': _token()},
                json=payload,
            )

        assert response.status_code == 200
        assert response.get_json() == {
            'ok': True,
            'msg': 'SMTP test email sent',
        }
        smtp_check.assert_called_once_with(payload)


class TestApply:
    def test_apply_rejects_weak_admin(self, client):
        res = client.post(
            '/setup/api/apply', headers={'X-Setup-Token': _token()},
            json={'admin': {'username': 'ops', 'password': 'short'}},
        )
        assert res.status_code == 400

    def test_apply_rejects_reserved_username(self, client):
        res = client.post(
            '/setup/api/apply', headers={'X-Setup-Token': _token()},
            json={'admin': {'username': 'system', 'password': 'x' * 12}},
        )
        assert res.status_code == 400

    def test_apply_conflict_when_configured(self, client, monkeypatch):
        """幂等再校验：配置齐全后 apply 必须 409。"""
        monkeypatch.setenv('OGS_MYSQL_USER', 'app_user')
        monkeypatch.setenv('OGS_MYSQL_PASSWORD', 'not-a-placeholder')
        monkeypatch.setenv('OGS_MYSQL_HOST', 'db')
        monkeypatch.setenv('OGS_FLASK_SECRET_KEY', 'k' * 40)
        monkeypatch.setenv('OGS_FERNET_KEYS', 'f' * 44)
        res = client.post(
            '/setup/api/apply', headers={'X-Setup-Token': _token()},
            json={'admin': {'username': 'ops', 'password': 'x' * 12}},
        )
        assert res.status_code == 409

    def test_apply_happy_path_writes_env_and_sentinel(self, client, tmp_path):
        ok = {'ok': True, 'msg': 'ok'}
        bootstrap_stdout = json.dumps({'ok': True, 'steps': [{'name': 'seed', 'ok': True, 'msg': ''}]})
        fake_proc = mock.Mock(returncode=0, stdout=bootstrap_stdout, stderr='')
        with mock.patch.object(setup_app_module.checks, 'test_mysql', return_value=dict(ok, server_version='8.0')), \
                mock.patch.object(setup_app_module.checks, 'test_redis', return_value=dict(ok)), \
                mock.patch.object(setup_app_module.subprocess, 'run', return_value=fake_proc), \
                mock.patch.object(setup_app_module.threading, 'Timer') as timer:
            res = client.post(
                '/setup/api/apply', headers={'X-Setup-Token': _token()},
                json={
                    'mysql': {'host': 'db', 'port': 3306, 'user': 'app', 'password': 'p', 'dbname': 'orange'},
                    'redis': {'host': 'cache', 'port': 6379},
                    'admin': {'username': 'ops', 'password': 'x' * 12, 'email': 'ops@x.io'},
                },
            )
        assert res.status_code == 200
        body = res.get_json()
        assert body['ok'] is True
        # runtime.env 落盘且含全部必需 key
        content = state.runtime_env_path().read_text(encoding='utf-8')
        for key in ('OGS_MYSQL_HOST', 'OGS_FLASK_SECRET_KEY', 'OGS_FERNET_KEYS'):
            assert key in content
        assert state.sentinel_exists()
        assert not state.token_path().exists()
        timer.assert_called_once()

    def test_apply_retests_and_passes_optional_smtp_to_bootstrap(
        self, client,
    ):
        ok = {'ok': True, 'msg': 'ok'}
        fake_proc = mock.Mock(
            returncode=0,
            stdout=json.dumps({'ok': True, 'steps': []}),
            stderr='',
        )
        mail = {
            'smtp_host': 'smtp.126.com',
            'smtp_port': 465,
            'security': 'ssl',
            'from_email': 'orange-test@126.com',
            'password': 'authorization-code',
        }
        with mock.patch.object(
            setup_app_module.checks, 'test_mysql',
            return_value=dict(ok, server_version='8.0'),
        ), mock.patch.object(
            setup_app_module.checks, 'test_redis',
            return_value=dict(ok),
        ), mock.patch.object(
            setup_app_module.checks, 'test_smtp',
            return_value=dict(ok),
        ) as smtp_check, mock.patch.object(
            setup_app_module.subprocess, 'run', return_value=fake_proc,
        ) as subprocess_run, mock.patch.object(
            setup_app_module.threading, 'Timer',
        ):
            response = client.post(
                '/setup/api/apply',
                headers={'X-Setup-Token': _token()},
                json={
                    'mysql': {
                        'host': 'db', 'port': 3306, 'user': 'app',
                        'password': 'p', 'dbname': 'orange',
                    },
                    'redis': {'host': 'cache', 'port': 6379},
                    'admin': {
                        'username': 'ops',
                        'password': 'x' * 12,
                    },
                    'mail': mail,
                },
            )

        assert response.status_code == 200
        smtp_check.assert_called_once_with(mail)
        child_payload = json.loads(
            subprocess_run.call_args.kwargs['input']
        )
        assert child_payload['mail'] == mail

    def test_apply_failed_check_writes_nothing(self, client):
        with mock.patch.object(
            setup_app_module.checks, 'test_mysql',
            return_value={'ok': False, 'msg': 'refused'},
        ):
            res = client.post(
                '/setup/api/apply', headers={'X-Setup-Token': _token()},
                json={
                    'mysql': {'host': 'db', 'user': 'app'},
                    'redis': {'host': 'cache'},
                    'admin': {'username': 'ops', 'password': 'x' * 12},
                },
            )
        assert res.status_code == 400
        assert not state.runtime_env_path().exists()
        assert not state.sentinel_exists()


class TestMaintenanceApp:
    def test_status_and_catchall(self):
        app = setup_app_module.create_maintenance_app(error=RuntimeError('boom'))
        app.testing = True
        client = app.test_client()
        status = client.get('/setup/api/status').get_json()
        assert status['mode'] == 'maintenance'
        assert 'boom' in status['error']
        assert client.post('/local/status/x').status_code == 503
