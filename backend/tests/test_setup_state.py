# -*- coding: utf-8 -*-
"""SETUP-WIZARD: setup/state.py 三态判定矩阵。"""
import importlib
import os

import pytest

from setup import state

FULL_ENV = {
    'OGS_MYSQL_USER': 'app_user',
    'OGS_MYSQL_PASSWORD': 'not-a-placeholder-pass',
    'OGS_MYSQL_HOST': 'db.internal',
    'OGS_FLASK_SECRET_KEY': 'k' * 40,
    'OGS_FERNET_KEYS': 'f' * 44,
}


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """清空 OGS_* 并把 DATA_DIR 指到临时目录，测试间互不污染。"""
    for key in list(os.environ):
        if key.startswith('OGS_'):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('OGS_DATA_DIR', str(tmp_path))
    importlib.reload(state)
    yield


def _set_full(monkeypatch, **overrides):
    merged = dict(FULL_ENV, **overrides)
    for key, value in merged.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


class TestMissingRequired:
    def test_empty_env_reports_all(self):
        missing = state.missing_required()
        assert 'OGS_MYSQL_USER' in missing
        assert 'OGS_FLASK_SECRET_KEY' in missing
        assert 'OGS_FERNET_KEYS' in missing

    def test_full_env_is_clean(self, monkeypatch):
        _set_full(monkeypatch)
        assert state.missing_required() == []

    @pytest.mark.parametrize('bad', ['', 'root', 'changeme', 'zkfc123', '192.0.2.1'])
    def test_mysql_placeholder_blacklist(self, monkeypatch, bad):
        _set_full(monkeypatch, OGS_MYSQL_PASSWORD=bad)
        assert 'OGS_MYSQL_PASSWORD' in state.missing_required()

    def test_short_secret_rejected(self, monkeypatch):
        _set_full(monkeypatch, OGS_FLASK_SECRET_KEY='short')
        assert 'OGS_FLASK_SECRET_KEY' in state.missing_required()

    def test_placeholder_secret_rejected(self, monkeypatch):
        _set_full(monkeypatch, OGS_FLASK_SECRET_KEY='change-me-' + 'x' * 30)
        assert 'OGS_FLASK_SECRET_KEY' in state.missing_required()

    def test_single_fernet_key_accepted(self, monkeypatch):
        _set_full(monkeypatch, OGS_FERNET_KEYS=None)
        monkeypatch.setenv('OGS_FERNET_KEY', 'f' * 44)
        assert 'OGS_FERNET_KEYS' not in state.missing_required()

    def test_template_placeholders_treated_as_missing(self, monkeypatch):
        """env.example 的 __REQUIRED_*__ 占位值不得被视为已配置。"""
        _set_full(
            monkeypatch,
            OGS_MYSQL_PASSWORD='__REQUIRED_EXISTING_APP_USER_PASSWORD__',
            OGS_FLASK_SECRET_KEY='__REQUIRED_GENERATE_RANDOM_48_BYTES__',
            OGS_FERNET_KEYS='__REQUIRED_GENERATE_FERNET_KEY__',
        )
        missing = state.missing_required()
        assert 'OGS_MYSQL_PASSWORD' in missing
        assert 'OGS_FLASK_SECRET_KEY' in missing
        assert 'OGS_FERNET_KEYS' in missing


class TestResolveMode:
    def test_empty_enters_setup(self):
        assert state.resolve_mode() == 'setup'

    def test_full_is_normal(self, monkeypatch):
        _set_full(monkeypatch)
        assert state.resolve_mode() == 'normal'

    def test_broken_with_sentinel_is_maintenance(self, monkeypatch):
        """已配置系统被破坏 → 绝不重开向导。"""
        state.mark_configured()
        assert state.resolve_mode() == 'maintenance'

    def test_force_overrides_sentinel(self, monkeypatch):
        state.mark_configured()
        monkeypatch.setenv('OGS_SETUP_MODE', 'force')
        assert state.resolve_mode() == 'setup'

    def test_off_disables_setup(self, monkeypatch):
        monkeypatch.setenv('OGS_SETUP_MODE', 'off')
        assert state.resolve_mode() == 'maintenance'

    def test_empty_string_process_env_still_missing(self, monkeypatch):
        """compose 注入空串的场景：空串按未设置处理。"""
        _set_full(monkeypatch, OGS_MYSQL_PASSWORD='')
        assert state.resolve_mode() == 'setup'


class TestRuntimeEnvView:
    def test_runtime_env_fills_missing(self, monkeypatch, tmp_path):
        runtime = tmp_path / 'runtime.env'
        runtime.write_text("OGS_MYSQL_USER='from-runtime'\n", encoding='utf-8')
        env = state.resolve_env()
        assert env.get('OGS_MYSQL_USER') == 'from-runtime'

    def test_nonempty_process_env_wins(self, monkeypatch, tmp_path):
        runtime = tmp_path / 'runtime.env'
        runtime.write_text("OGS_MYSQL_USER='from-runtime'\n", encoding='utf-8')
        monkeypatch.setenv('OGS_MYSQL_USER', 'from-process')
        assert state.resolve_env().get('OGS_MYSQL_USER') == 'from-process'

    def test_env_locked_only_nonempty(self, monkeypatch):
        monkeypatch.setenv('OGS_MYSQL_HOST', 'db')
        monkeypatch.setenv('OGS_MYSQL_USER', '')
        locked = state.env_locked_keys()
        assert 'OGS_MYSQL_HOST' in locked
        assert 'OGS_MYSQL_USER' not in locked
