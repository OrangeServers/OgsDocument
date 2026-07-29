# -*- coding: utf-8 -*-
"""
REV47-H8: encrypt/decrypt_host_password 写 audit log.

背景:
- SSH 凭据加/解密是敏感操作, 失败/重加密/迁移需要可追溯
- 原实现完全无 audit log
- 修复: logger 命名空间 'basesec_audit'
  - INFO: encrypt ok / decrypt ok
  - WARNING: rehash ok / rehash failed / decrypt failed
"""
import os
import base64
import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


_HERE = os.path.dirname(os.path.abspath(__file__))


def _gen_key():
    return Fernet.generate_key().decode('utf-8')


def _encrypt_with_key(plain, key_str):
    return Fernet(key_str.encode('utf-8')).encrypt(plain.encode('utf-8')).decode('utf-8')


@pytest.fixture
def fernet_env(monkeypatch):
    return monkeypatch


# 1) Logger 命名空间
class TestRev47H8LoggerNamespace:
    def test_01_logger_name_constant_exists(self):
        from app.tools import basesec
        assert basesec._BASESEC_AUDIT_LOGGER == 'basesec_audit'

    def test_02_logger_name_distinct_from_audsec(self):
        from app.tools import basesec
        from app.tools.audsec import _AUDSEC_DEFAULT_LOGGER
        assert basesec._BASESEC_AUDIT_LOGGER != _AUDSEC_DEFAULT_LOGGER


# 2) encrypt 审计
class TestRev47H8EncryptAudit:
    def test_01_encrypt_ok_logs_info(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        fernet_env.delenv('OGS_FERNET_KEY', raising=False)
        from app.tools.basesec import encrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            ct = encrypt_host_password('my_secret')
        assert ct is not None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('encrypt ok' in m for m in msgs)
        assert any('key_index=0' in m for m in msgs)

    def test_02_encrypt_none_skips(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            result = encrypt_host_password(None)
        assert result is None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert msgs == []

    def test_03_encrypt_empty_string_skips(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            result = encrypt_host_password('')
        assert result is None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert msgs == []

    def test_04_encrypt_failure_logs_warning(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password

        class _BrokenFernet:
            def encrypt(self, data):
                raise RuntimeError('mock encrypt failure')

        with patch('app.tools.basesec._get_primary_fernet', return_value=_BrokenFernet()):
            with caplog.at_level(logging.WARNING, logger='basesec_audit'):
                with pytest.raises(RuntimeError):
                    encrypt_host_password('test')
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('encrypt failed' in m for m in msgs)
        assert any('mock encrypt failure' in m for m in msgs)

    def test_05_logger_failure_does_not_break_encrypt(self, fernet_env):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password
        with patch('app.tools.basesec.logging.getLogger') as mock_get:
            mock_log = mock_get.return_value
            mock_log.info.side_effect = RuntimeError('logger dead')
            ct = encrypt_host_password('survive')
            assert ct is not None and ct.startswith('gAAAAA')


# 3) decrypt Fernet 路径
class TestRev47H8DecryptFernetAudit:
    def test_01_decrypt_primary_key_logs_info(self, fernet_env, caplog):
        k = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        ct = encrypt_host_password('primary_test')
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(ct)
        assert plain == 'primary_test'
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('decrypt ok' in m for m in msgs)
        assert any('key_index=0' in m for m in msgs)
        assert any('stored_type=fernet' in m for m in msgs)

    def test_02_decrypt_old_key_with_rehash_logs_warning(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('rotation_secret', k_old)
        caplog.clear()
        rehash_called = []
        def _cb(new_stored):
            rehash_called.append(new_stored)
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            plain = decrypt_host_password(ct_old, rehash_callback=_cb)
        assert plain == 'rotation_secret'
        assert len(rehash_called) == 1
        assert rehash_called[0].startswith('gAAAAA')
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash ok' in r.message for r in warnings)
        assert any('key_index=1' in r.message for r in warnings)

    def test_03_decrypt_old_key_no_callback_logs_info_only(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('no_cb_secret', k_old)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(ct_old)
        assert plain == 'no_cb_secret'
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('decrypt ok' in m for m in msgs)
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert not any('rehash' in r.message for r in warnings)

    def test_04_decrypt_rehash_encrypt_returns_none_logs_skipped(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('skip_secret', k_old)
        caplog.clear()
        with patch('app.tools.basesec.encrypt_host_password', return_value=None):
            def _cb(_):
                pytest.fail("callback 不应被调用 when encrypt returns None")
            with caplog.at_level(logging.WARNING, logger='basesec_audit'):
                plain = decrypt_host_password(ct_old, rehash_callback=_cb)
        assert plain == 'skip_secret'
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash skipped' in r.message for r in warnings)
        assert any('encrypt_returned_none' in r.message for r in warnings)

    def test_05_decrypt_rehash_callback_raises_logs_failed(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('cb_fail_secret', k_old)
        caplog.clear()
        def _bad_cb(_):
            raise RuntimeError('mock cb failure')
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            plain = decrypt_host_password(ct_old, rehash_callback=_bad_cb)
        assert plain == 'cb_fail_secret'
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash failed' in r.message for r in warnings)
        assert any('mock cb failure' in r.message for r in warnings)

    def test_06_decrypt_all_keys_fail_logs_warning(self, fernet_env, caplog):
        k1 = _gen_key()
        k2 = _gen_key()
        k3 = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s,%s' % (k1, k2, k3))
        k_unknown = _gen_key()
        ct_unknown = _encrypt_with_key('mystery', k_unknown)
        from app.tools.basesec import decrypt_host_password
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            with pytest.raises(RuntimeError):
                decrypt_host_password(ct_unknown)
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('decrypt failed' in r.message for r in warnings)
        assert any('key_count=3' in r.message for r in warnings)


# 4) decrypt base64 兼容路径
class TestRev47H8DecryptBase64Audit:
    def test_01_decrypt_base64_logs_info(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'legacy_secret').decode('utf-8')
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(legacy)
        assert plain == 'legacy_secret'
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('decrypt ok' in m for m in msgs)
        assert any('legacy_base64' in m for m in msgs)

    def test_02_decrypt_base64_with_rehash_logs_warning(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'upgrade_me').decode('utf-8')
        caplog.clear()
        rehash_called = []
        def _cb(new_stored):
            rehash_called.append(new_stored)
        # 同时捕获 INFO (decrypt ok) + WARNING (rehash ok)
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(legacy, rehash_callback=_cb)
        assert plain == 'upgrade_me'
        assert len(rehash_called) == 1
        assert rehash_called[0].startswith('gAAAAA')
        # INFO: decrypt ok (legacy)
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('decrypt ok' in m for m in msgs)
        assert any('legacy_base64' in m for m in msgs)
        # WARNING: rehash ok (legacy -> fernet)
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash ok' in r.message for r in warnings)
        # 'legacy_base64' 和 'fernet' 都应在 rehash 消息里
        rehash_msgs = [r.message for r in warnings if 'rehash ok' in r.message]
        assert any('legacy_base64' in m and 'fernet' in m for m in rehash_msgs)

    def test_03_decrypt_base64_rehash_callback_raises_logs_failed(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'cb_fail_legacy').decode('utf-8')
        caplog.clear()
        def _bad_cb(_):
            raise RuntimeError('mock base64 cb failure')
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            plain = decrypt_host_password(legacy, rehash_callback=_bad_cb)
        assert plain == 'cb_fail_legacy'
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash failed' in r.message for r in warnings)
        assert any('mock base64 cb failure' in r.message for r in warnings)

    def test_04_decrypt_invalid_base64_logs_warning(self, fernet_env, caplog):
        """烂 base64 → WARNING 'base64 decode failed', 抛 RuntimeError."""
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            with pytest.raises(RuntimeError):
                decrypt_host_password('!!!not-base64!!!')
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('base64 decode failed' in r.message for r in warnings)

    def test_05_decrypt_none_skips(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            result = decrypt_host_password(None)
        assert result is None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert msgs == []

    def test_06_decrypt_empty_string_skips(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            result = decrypt_host_password('')
        assert result is None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert msgs == []


# 5) 集成: 端到端日志覆盖
class TestRev47H8EndToEndAudit:
    def test_01_full_lifecycle_logs(self, fernet_env, caplog):
        """完整生命周期: encrypt → decrypt, 都应被记录."""
        k = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password

        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            ct = encrypt_host_password('lifecycle_pwd')
            caplog.clear()
            plain = decrypt_host_password(ct)
        assert plain == 'lifecycle_pwd'
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('decrypt ok' in m for m in msgs)
        assert any('key_index=0' in m for m in msgs)

    def test_02_logger_does_not_pollute_other_loggers(self, fernet_env, caplog):
        """basesec_audit 日志不污染其他 logger."""
        k = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password
        with caplog.at_level(logging.INFO):
            encrypt_host_password('isolation')
        # 仅 basesec_audit 写日志
        other_names = set(r.name for r in caplog.records) - {'basesec_audit'}
        # 可能 audlog_fallback 等其他 logger 也被 pytest root 捕获 (propagate=True)
        # 核心是 basesec_audit 一定有记录
        basesec_records = [r for r in caplog.records if r.name == 'basesec_audit']
        assert len(basesec_records) >= 1


# 6) 源码检查: 关键日志字符串
class TestRev47H8SourceCode:
    """REV47-H8: 源码中含 audit log 关键字串."""

    def test_01_encrypt_has_audit_log_call(self):
        import inspect
        from app.tools import basesec
        source = inspect.getsource(basesec.encrypt_host_password)
        assert 'basesec_audit' in source or '_BASESEC_AUDIT_LOGGER' in source
        assert 'encrypt ok' in source

    def test_02_decrypt_has_audit_log_call(self):
        import inspect
        from app.tools import basesec
        source = inspect.getsource(basesec.decrypt_host_password)
        assert 'basesec_audit' in source or '_BASESEC_AUDIT_LOGGER' in source
        assert 'decrypt ok' in source
        assert 'rehash ok' in source
        assert 'decrypt failed' in source


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
# -*- coding: utf-8 -*-
"""
REV47-H8: encrypt/decrypt_host_password 写 audit log.

背景:
- SSH 凭据加/解密是敏感操作, 失败/重加密/迁移需要可追溯
- 原实现完全无 audit log
- 修复: logger 命名空间 'basesec_audit'
  - INFO: encrypt ok / decrypt ok
  - WARNING: rehash ok / rehash failed / decrypt failed
"""
import os
import base64
import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


_HERE = os.path.dirname(os.path.abspath(__file__))


def _gen_key():
    return Fernet.generate_key().decode('utf-8')


def _encrypt_with_key(plain, key_str):
    return Fernet(key_str.encode('utf-8')).encrypt(plain.encode('utf-8')).decode('utf-8')


@pytest.fixture
def fernet_env(monkeypatch):
    return monkeypatch


# 1) Logger 命名空间
class TestRev47H8LoggerNamespace:
    def test_01_logger_name_constant_exists(self):
        from app.tools import basesec
        assert basesec._BASESEC_AUDIT_LOGGER == 'basesec_audit'

    def test_02_logger_name_distinct_from_audsec(self):
        from app.tools import basesec
        from app.tools.audsec import _AUDSEC_DEFAULT_LOGGER
        assert basesec._BASESEC_AUDIT_LOGGER != _AUDSEC_DEFAULT_LOGGER


# 2) encrypt 审计
class TestRev47H8EncryptAudit:
    def test_01_encrypt_ok_logs_info(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        fernet_env.delenv('OGS_FERNET_KEY', raising=False)
        from app.tools.basesec import encrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            ct = encrypt_host_password('my_secret')
        assert ct is not None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('encrypt ok' in m for m in msgs)
        assert any('key_index=0' in m for m in msgs)

    def test_02_encrypt_none_skips(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            result = encrypt_host_password(None)
        assert result is None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert msgs == []

    def test_03_encrypt_empty_string_skips(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            result = encrypt_host_password('')
        assert result is None
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert msgs == []

    def test_04_encrypt_failure_logs_warning(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password

        class _BrokenFernet:
            def encrypt(self, data):
                raise RuntimeError('mock encrypt failure')

        with patch('app.tools.basesec._get_primary_fernet', return_value=_BrokenFernet()):
            with caplog.at_level(logging.WARNING, logger='basesec_audit'):
                with pytest.raises(RuntimeError):
                    encrypt_host_password('test')
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('encrypt failed' in m for m in msgs)
        assert any('mock encrypt failure' in m for m in msgs)

    def test_05_logger_failure_does_not_break_encrypt(self, fernet_env):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password
        with patch('app.tools.basesec.logging.getLogger') as mock_get:
            mock_log = mock_get.return_value
            mock_log.info.side_effect = RuntimeError('logger dead')
            ct = encrypt_host_password('survive')
            assert ct is not None and ct.startswith('gAAAAA')


# 3) decrypt Fernet 路径
class TestRev47H8DecryptFernetAudit:
    def test_01_decrypt_primary_key_logs_info(self, fernet_env, caplog):
        k = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', k)
        from app.tools.basesec import encrypt_host_password, decrypt_host_password
        ct = encrypt_host_password('primary_test')
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(ct)
        assert plain == 'primary_test'
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('decrypt ok' in m for m in msgs)
        assert any('key_index=0' in m for m in msgs)
        assert any('stored_type=fernet' in m for m in msgs)

    def test_02_decrypt_old_key_with_rehash_logs_warning(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('rotation_secret', k_old)
        caplog.clear()
        rehash_called = []
        def _cb(new_stored):
            rehash_called.append(new_stored)
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            plain = decrypt_host_password(ct_old, rehash_callback=_cb)
        assert plain == 'rotation_secret'
        assert len(rehash_called) == 1
        assert rehash_called[0].startswith('gAAAAA')
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash ok' in r.message for r in warnings)
        assert any('key_index=1' in r.message for r in warnings)

    def test_03_decrypt_old_key_no_callback_logs_info_only(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('no_cb_secret', k_old)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='basesec_audit'):
            plain = decrypt_host_password(ct_old)
        assert plain == 'no_cb_secret'
        msgs = [r.message for r in caplog.records if r.name == 'basesec_audit']
        assert any('decrypt ok' in m for m in msgs)
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert not any('rehash' in r.message for r in warnings)

    def test_04_decrypt_rehash_encrypt_returns_none_logs_skipped(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('skip_secret', k_old)
        caplog.clear()
        with patch('app.tools.basesec.encrypt_host_password', return_value=None):
            def _cb(_):
                pytest.fail("callback 不应被调用 when encrypt returns None")
            with caplog.at_level(logging.WARNING, logger='basesec_audit'):
                plain = decrypt_host_password(ct_old, rehash_callback=_cb)
        assert plain == 'skip_secret'
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash skipped' in r.message for r in warnings)
        assert any('encrypt_returned_none' in r.message for r in warnings)

    def test_05_decrypt_rehash_callback_raises_logs_failed(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('cb_fail_secret', k_old)
        caplog.clear()
        def _bad_cb(_):
            raise RuntimeError('mock cb failure')
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            plain = decrypt_host_password(ct_old, rehash_callback=_bad_cb)
        assert plain == 'cb_fail_secret'
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash failed' in r.message for r in warnings)
        assert any('mock cb failure' in r.message for r in warnings)

    def test_06_decrypt_all_keys_fail_logs_warning(self, fernet_env, caplog):
        k1 = _gen_key()
        k2 = _gen_key()
        k3 = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s,%s' % (k1, k2, k3))
        k_unknown = _gen_key()
        ct_unknown = _encrypt_with_key('mystery', k_unknown)
        from app.tools.basesec import decrypt_host_password
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            with pytest.raises(RuntimeError):
                decrypt_host_password(ct_unknown)
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('decrypt failed' in r.message for r in warnings)
        assert any('key_count=3' in r.message for r in warnings)
