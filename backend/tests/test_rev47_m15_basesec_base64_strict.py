# -*- coding: utf-8 -*-
"""
REV47-M15: base64 兼容路径强制 rehash 后清空兼容 (env-controlled).

背景:
- 历史 SSH 凭据用 base64 编码 (无加密, DB 拿到即可解)
- 升级到 Fernet 后, base64 路径仍保留兼容, 长期保留 = 安全债
- 修复: OGS_DISABLE_BASE64_COMPAT=1 时, base64 数据直接抛 RuntimeError
        强制要求业务侧先 rehash 升级到 Fernet, 才能解密
- 默认 0 (向后兼容), 业务侧跑迁移脚本后设 env=1

测试覆盖:
  1) env=0 (默认) base64 仍能解, 行为不变
  2) env=1 base64 直接抛 RuntimeError, 含迁移指引
  3) env=1 ERROR log 'base64 compat disabled'
  4) env=1 + Fernet 密文仍能正常解 (门控只针对 base64)
  5) env=1 + callback 提供也抛 (门控优先)
  6) env=0 默认值检查
  7) 源码含 _BASESEC_BASE64_COMPAT_DISABLED 常量
"""
import os
import base64
import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


def _gen_key():
    return Fernet.generate_key().decode('utf-8')


@pytest.fixture
def fernet_env(monkeypatch):
    return monkeypatch


# 1) 常量定义
class TestRev47M15Constant:
    def test_01_helper_function_exists(self):
        from app.tools import basesec
        assert hasattr(basesec, '_is_base64_compat_disabled')
        assert callable(basesec._is_base64_compat_disabled)

    def test_02_default_value_is_false(self, monkeypatch):
        """默认 (env 未设或='0') 时, 兼容保持开启 (返回 False)."""
        monkeypatch.delenv('OGS_DISABLE_BASE64_COMPAT', raising=False)
        from app.tools import basesec
        assert basesec._is_base64_compat_disabled() is False

    def test_03_env_var_docstring(self):
        from app.tools import basesec
        import inspect
        src = inspect.getsource(basesec)
        assert 'OGS_DISABLE_BASE64_COMPAT' in src


# 2) env=0 行为 (向后兼容)
class TestRev47M15DefaultBehavior:
    """REV47-M15: 默认 OGS_DISABLE_BASE64_COMPAT=0 时, base64 仍能解."""

    def test_01_base64_decrypt_succeeds_by_default(self, fernet_env, caplog):
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '0')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'compat_default_secret').decode('utf-8')

        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(legacy)

        assert plain == 'compat_default_secret'

    def test_02_no_error_log_when_enabled(self, fernet_env, caplog):
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '0')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'no_error').decode('utf-8')

        caplog.clear()
        with caplog.at_level(logging.ERROR, logger='basesec_audit'):
            decrypt_host_password(legacy)

        # 无 ERROR 级别
        errors = [r for r in caplog.records
                  if r.name == 'basesec_audit' and r.levelno == logging.ERROR]
        assert not any('compat disabled' in r.message for r in errors)


# 3) env=1 行为 (强制 rehash)
class TestRev47M15DisabledBehavior:
    """REV47-M15: OGS_DISABLE_BASE64_COMPAT=1 时, base64 直接抛 RuntimeError."""

    def test_01_base64_raises_runtime_error(self, fernet_env):
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'should_not_decrypt').decode('utf-8')

        with pytest.raises(RuntimeError) as exc_info:
            decrypt_host_password(legacy)

        # 错误信息含迁移指引
        assert 'OGS_DISABLE_BASE64_COMPAT' in str(exc_info.value)
        assert 'rehash' in str(exc_info.value).lower()

    def test_02_logs_error_when_disabled(self, fernet_env, caplog):
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'err_log_secret').decode('utf-8')

        caplog.clear()
        with caplog.at_level(logging.ERROR, logger='basesec_audit'):
            with pytest.raises(RuntimeError):
                decrypt_host_password(legacy)

        errors = [r for r in caplog.records
                  if r.name == 'basesec_audit' and r.levelno == logging.ERROR]
        assert any('compat disabled' in r.message for r in errors)

    def test_03_fernet_ciphertext_still_works(self, fernet_env, caplog):
        """env=1 时, Fernet 密文仍能解 (门控只针对 base64)."""
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        k = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password

        ct = encrypt_host_password('fernet_works')

        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(ct)

        assert plain == 'fernet_works'

    def test_04_callback_provided_still_raises(self, fernet_env):
        """env=1 + callback 提供仍抛 (门控优先于 callback, 因为是强制清空)."""
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'cb_still_blocks').decode('utf-8')

        cb_called = []

        def _cb(_):
            cb_called.append(_)

        with pytest.raises(RuntimeError):
            decrypt_host_password(legacy, rehash_callback=_cb)

        # callback 不应被调用 (门控直接抛)
        assert cb_called == []

    def test_05_error_msg_contains_rehash_guidance(self, fernet_env):
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'guidance').decode('utf-8')

        with pytest.raises(RuntimeError) as exc_info:
            decrypt_host_password(legacy)

        msg = str(exc_info.value)
        # 含迁移指引
        assert 'rehash' in msg.lower()
        assert 'decrypt_host_password' in msg  # 提示用 callback 升级
        assert 'env' in msg  # 提示改 env 关闭

    def test_06_error_log_indicates_callback_status(self, fernet_env, caplog):
        """ERROR log 区分 callback 提供 / 未提供."""
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'cb_status').decode('utf-8')

        # 无 callback
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger='basesec_audit'):
            with pytest.raises(RuntimeError):
                decrypt_host_password(legacy)
        errors = [r.message for r in caplog.records
                  if r.name == 'basesec_audit' and r.levelno == logging.ERROR]
        assert any('missing' in m for m in errors)


# 4) None / 空 不受影响
class TestRev47M15NoneStillReturnsNone:
    def test_01_none_input_unaffected_by_gate(self, fernet_env):
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        assert decrypt_host_password(None) is None

    def test_02_empty_input_unaffected_by_gate(self, fernet_env):
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        assert decrypt_host_password('') is None


# 5) 源码检查
class TestRev47M15SourceCode:
    def test_01_helper_in_source(self):
        import inspect
        from app.tools import basesec
        src = inspect.getsource(basesec)
        assert '_is_base64_compat_disabled' in src

    def test_02_gate_check_in_decrypt(self):
        import inspect
        from app.tools import basesec
        src = inspect.getsource(basesec.decrypt_host_password)
        # decrypt 必须检查门控 helper
        assert '_is_base64_compat_disabled' in src
        # 必须含 'compat' 错误信息 (迁移指引)
        assert 'compat' in src.lower() or '兼容' in src


# 6) 集成: 完整升级流程
class TestRev47M15Integration:
    """完整迁移流程: env=0 升级所有 base64 → env=1 严格模式."""

    def test_01_full_migration_flow(self, fernet_env, caplog):
        # 1) env=0 时, 用 callback 升级 base64 → Fernet
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '0')
        k = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password

        legacy = base64.b64encode(b'will_upgrade').decode('utf-8')

        upgraded = []

        def _cb(new_stored):
            upgraded.append(new_stored)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(legacy, rehash_callback=_cb)

        assert plain == 'will_upgrade'
        assert len(upgraded) == 1
        # 新存储是 Fernet 密文
        assert upgraded[0].startswith('gAAAAA')

        # 2) env=1 时, base64 直接拒绝
        fernet_env.setenv('OGS_DISABLE_BASE64_COMPAT', '1')
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger='basesec_audit'):
            with pytest.raises(RuntimeError):
                decrypt_host_password(legacy)

        # 但 Fernet 密文仍能解
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain2 = decrypt_host_password(upgraded[0])
        assert plain2 == 'will_upgrade'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
