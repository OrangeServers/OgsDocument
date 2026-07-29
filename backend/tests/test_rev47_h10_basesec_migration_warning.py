# -*- coding: utf-8 -*-
"""
REV47-H10: decrypt_host_password 透明迁移 silent failure → Log.warning.

背景:
- 原实现: `except Exception: pass` 完全静默
- 问题: 迁移失败没人知道, 永远 base64, 永远不升级
- 修复: 失败时 log.warning (H8 实施已覆盖), 这里专门验证 silent → warning 语义

测试覆盖:
  1) 旧 key 解密 + callback 抛异常 → WARNING 'rehash failed', 仍返回明文
  2) 旧 key 解密 + encrypt 返回 None (短路) → WARNING 'rehash skipped'
  3) base64 兼容 + callback 抛异常 → WARNING 'rehash failed', 仍返回明文
  4) rehash 失败绝不阻断主业务 (明文仍返回)
  5) 失败日志含 err 详情
  6) logger 自身异常 → 仍正常返回
"""
import os
import base64
import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


def _gen_key():
    return Fernet.generate_key().decode('utf-8')


def _encrypt_with_key(plain, key_str):
    return Fernet(key_str.encode('utf-8')).encrypt(plain.encode('utf-8')).decode('utf-8')


@pytest.fixture
def fernet_env(monkeypatch):
    return monkeypatch


# 1) 旧 key 解密 + callback 抛异常
class TestRev47H10OldKeyRehashFailure:
    """H10: 旧 key 透明迁移失败 → WARNING, 不阻断解密."""

    def test_01_callback_raises_logs_warning_and_returns_plain(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('migration_fail_secret', k_old)

        def _bad_cb(_):
            raise RuntimeError('mock migration failure')

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            # 不应抛 (内部 try/except 吃掉, 主业务不阻断)
            plain = decrypt_host_password(ct_old, rehash_callback=_bad_cb)

        # 1) 仍返回明文 (主业务不阻断)
        assert plain == 'migration_fail_secret'
        # 2) 写 WARNING (不再 silent)
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash failed' in r.message for r in warnings)
        # 3) 含 err 详情 (便于排查)
        assert any('mock migration failure' in r.message for r in warnings)

    def test_02_encrypt_returns_none_logs_skipped(self, fernet_env, caplog):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('skip_secret', k_old)

        def _cb(_):
            pytest.fail("callback 不应被调用 when encrypt returns None")

        with patch('app.tools.basesec.encrypt_host_password', return_value=None):
            caplog.clear()
            with caplog.at_level(logging.WARNING, logger='basesec_audit'):
                plain = decrypt_host_password(ct_old, rehash_callback=_cb)

        assert plain == 'skip_secret'
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash skipped' in r.message for r in warnings)
        assert any('encrypt_returned_none' in r.message for r in warnings)

    def test_03_no_silent_pass(self, fernet_env, caplog):
        """核心断言: 失败路径绝不 silent pass, 必须留痕."""
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('no_silent', k_old)

        def _bad_cb(_):
            raise ValueError('db connection lost')

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            decrypt_host_password(ct_old, rehash_callback=_bad_cb)

        # 至少有 1 条 WARNING (非 silent)
        all_warnings = [r for r in caplog.records
                        if r.levelno == logging.WARNING and r.name == 'basesec_audit']
        assert len(all_warnings) >= 1, \
            f"迁移失败必须记录 WARNING, 实际为空 (silent pass!)"

    def test_04_key_index_in_warning(self, fernet_env, caplog):
        """WARNING 含 key_index, 便于定位是哪个历史 key 触发."""
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('idx_secret', k_old)

        def _bad_cb(_):
            raise RuntimeError('idx_test')

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            decrypt_host_password(ct_old, rehash_callback=_bad_cb)

        warnings = [r.message for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('key_index=1' in m for m in warnings)


# 2) base64 兼容 + callback 抛异常
class TestRev47H10Base64RehashFailure:
    """H10: base64 透明迁移失败 → WARNING, 不阻断解密."""

    def test_01_callback_raises_logs_warning_and_returns_plain(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'base64_migration_fail').decode('utf-8')

        def _bad_cb(_):
            raise RuntimeError('mock base64 cb failure')

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            plain = decrypt_host_password(legacy, rehash_callback=_bad_cb)

        assert plain == 'base64_migration_fail'
        warnings = [r for r in caplog.records
                    if r.name == 'basesec_audit' and r.levelno == logging.WARNING]
        assert any('rehash failed' in r.message for r in warnings)
        assert any('legacy_base64' in r.message for r in warnings)
        assert any('mock base64 cb failure' in r.message for r in warnings)

    def test_02_no_silent_pass_base64(self, fernet_env, caplog):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import decrypt_host_password
        legacy = base64.b64encode(b'no_silent_base64').decode('utf-8')

        def _bad_cb(_):
            raise ValueError('db write fail')

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger='basesec_audit'):
            decrypt_host_password(legacy, rehash_callback=_bad_cb)

        all_warnings = [r for r in caplog.records
                        if r.levelno == logging.WARNING and r.name == 'basesec_audit']
        assert len(all_warnings) >= 1


# 3) logger 异常不阻断
class TestRev47H10LoggerResilient:
    """H10: 日志系统异常时, 主业务仍正常返回."""

    def test_01_logger_dead_encrypt_still_works(self, fernet_env):
        fernet_env.setenv('OGS_FERNET_KEYS', _gen_key())
        from app.tools.basesec import encrypt_host_password
        with patch('app.tools.basesec.logging.getLogger') as mock_get:
            mock_log = mock_get.return_value
            mock_log.info.side_effect = RuntimeError('logger dead')
            mock_log.warning.side_effect = RuntimeError('logger dead')
            ct = encrypt_host_password('survive')
            assert ct is not None and ct.startswith('gAAAAA')

    def test_02_logger_dead_decrypt_old_key_still_returns_plain(self, fernet_env):
        k_old = _gen_key()
        k_new = _gen_key()
        fernet_env.setenv('OGS_FERNET_KEYS', '%s,%s' % (k_new, k_old))
        from app.tools.basesec import decrypt_host_password
        ct_old = _encrypt_with_key('survive_old', k_old)
        with patch('app.tools.basesec.logging.getLogger') as mock_get:
            mock_log = mock_get.return_value
            mock_log.info.side_effect = RuntimeError('logger dead')
            mock_log.warning.side_effect = RuntimeError('logger dead')
            plain = decrypt_host_password(ct_old)
            assert plain == 'survive_old'


# 4) 源码检查
class TestRev47H10SourceCode:
    """H10: 源码中必须含 'rehash failed' WARNING (不再 silent pass)."""

    def test_01_no_silent_pass_in_old_key_path(self):
        import re
        import inspect
        from app.tools import basesec
        source = inspect.getsource(basesec.decrypt_host_password)
        # 旧 key rehash 路径必须含 'rehash failed' 字串 (而非 pass)
        # 找到第一个 for 循环块 (i > 0 分支)
        # 简化: 全源码必须含 'rehash failed'
        assert 'rehash failed' in source, \
            "旧 key rehash 失败必须 log.warning 'rehash failed', 不能 silent pass"

    def test_02_no_silent_pass_in_base64_path(self):
        import inspect
        from app.tools import basesec
        source = inspect.getsource(basesec.decrypt_host_password)
        # base64 路径必须含 'rehash failed'
        assert source.count('rehash failed') >= 2, \
            "Fernet + base64 两条 rehash 路径都应含 'rehash failed'"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
