# -*- coding: utf-8 -*-
"""
R2-2 (REV46-H20): get_ssh_password 透明迁移改走 osql_up

问题: 旧实现 _rehash 直接 db.session.commit() 绕过统一封装
修复: 走 osql_up + 失败降级为 Log.warning
测试维度:
  1) 正常 Fernet 解密 (无需 rehash)
  2) base64 旧格式触发 rehash, 走 osql_up
  3) osql_up 抛 SqlOpError 时降级为 warning, 不阻断主流程
  4) sys_user_row=None 返回 None
  5) 用 id 而非 ORM 对象引用 (避免 stale state)
"""
import os
import sys
import logging
import pytest
from unittest.mock import patch, MagicMock

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# 1) 正常 Fernet 解密
# =============================================================================
class TestFernetDecrypt:
    """R2-2: 已加密的 Fernet 密文应直接解密, 不走 rehash"""

    def test_01_fernet_ciphertext_returns_plain(self):
        """Fernet 密文直接解密, 不调用 rehash"""
        from app.tools.shellcmd import get_ssh_password
        from cryptography.fernet import Fernet

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)
        plain_pwd = 'my_plain_password_123'
        ciphertext = f.encrypt(plain_pwd.encode()).decode()

        mock_row = MagicMock()
        mock_row.id = 42
        mock_row.host_password = ciphertext

        rehash_called = []
        def fake_rehash(new_stored):
            rehash_called.append(new_stored)

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up') as mock_osql_up:
            result = get_ssh_password(mock_row)

        assert result == plain_pwd
        # Fernet 密文 (list[0] 加密) 不触发 rehash
        assert rehash_called == [], "Fernet 密文不应用 rehash"
        mock_osql_up.assert_not_called()

    def test_02_none_sys_user_returns_none(self):
        """sys_user_row=None 直接返 None, 不抛异常"""
        from app.tools.shellcmd import get_ssh_password
        assert get_ssh_password(None) is None


# =============================================================================
# 2) base64 旧格式触发 rehash
# =============================================================================
class TestBase64Rehash:
    """R2-2: base64 旧格式触发 rehash, 走 osql_up"""

    def test_01_base64_triggers_osql_up(self):
        """base64 格式 (非 Fernet) 解密后应走 osql_up 写回"""
        from app.tools.shellcmd import get_ssh_password
        from app.tools.basesec import base64_auto
        from cryptography.fernet import Fernet

        plain_pwd = 'legacy_base64_password'
        legacy_stored = base64_auto('en', plain_pwd)
        assert legacy_stored != plain_pwd  # 确认编码了

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)

        mock_row = MagicMock()
        mock_row.id = 99
        mock_row.host_password = legacy_stored

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up') as mock_osql_up:
            result = get_ssh_password(mock_row)

        assert result == plain_pwd
        # 必须调用 osql_up 一次
        assert mock_osql_up.call_count == 1
        call_args = mock_osql_up.call_args
        args = call_args[0]
        assert args[0] == 't_sys_user'
        assert args[1] == {'id': 99}
        assert 'host_password' in args[2]
        new_val = args[2]['host_password']
        assert new_val.startswith('gAAAAA'), f'新值应是 Fernet 密文, 实际: {new_val[:20]}'

    def test_02_uses_id_not_orm_reference(self):
        """rehash 用 id 而非 ORM 对象引用, 避免 stale state"""
        from app.tools.shellcmd import get_ssh_password
        from app.tools.basesec import base64_auto
        from cryptography.fernet import Fernet

        legacy_stored = base64_auto('en', 'legacy_pwd')

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)

        mock_row = MagicMock()
        mock_row.id = 7
        mock_row.host_password = legacy_stored

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up') as mock_osql_up:
            get_ssh_password(mock_row)

        call_args = mock_osql_up.call_args
        where_clause = call_args[0][1]
        assert where_clause == {'id': 7}
        assert 'row' not in str(where_clause).lower()


# =============================================================================
# 3) osql_up 失败时降级
# =============================================================================
class TestRehashFailure:
    """R2-2: osql_up 抛 SqlOpError 时降级, 不阻断主流程"""

    def test_01_osql_up_raises_warning_logged(self, caplog):
        """osql_up 抛任意异常 → Log.warning, 不抛回 caller"""
        from app.tools.shellcmd import get_ssh_password
        from app.tools.basesec import base64_auto
        from cryptography.fernet import Fernet

        legacy_stored = base64_auto('en', 'legacy_pwd')

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)

        mock_row = MagicMock()
        mock_row.id = 11
        mock_row.host_password = legacy_stored

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up',
                   side_effect=Exception('mock DB error')), \
             caplog.at_level(logging.WARNING, logger='shellcmd'):
            result = get_ssh_password(mock_row)

        assert result == 'legacy_pwd'
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) >= 1
        # REV47-T3: 日志消息由 audsec 统一格式 'audsec write failed: op=...',
        # 替代原内联 'R2-2: ...' 格式. 验证 op_name 与 sys_user_id 仍在.
        assert 'ssh_password_rehash' in warnings[0].message
        assert 'sys_user_id=11' in warnings[0].message
        assert '11' in warnings[0].message

    def test_02_osql_up_sqluerror_degrades(self, caplog):
        """osql_up 抛 SqlOpError (统一封装异常) 也应降级"""
        from app.tools.shellcmd import get_ssh_password
        from app.tools.basesec import base64_auto
        from app.core.db.insert import SqlOpError
        from cryptography.fernet import Fernet

        legacy_stored = base64_auto('en', 'legacy_pwd')

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)

        mock_row = MagicMock()
        mock_row.id = 22
        mock_row.host_password = legacy_stored

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up',
                   side_effect=SqlOpError('mock data conflict')), \
             caplog.at_level(logging.WARNING, logger='shellcmd'):
            result = get_ssh_password(mock_row)

        assert result == 'legacy_pwd'
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        # REV47-T3: 日志消息由 audsec 统一格式, 验证 op_name 与 sys_user_id 仍在
        assert any('ssh_password_rehash' in r.message and 'sys_user_id=22' in r.message
                   for r in warnings)


# =============================================================================
# 4) 不会绕过 osql_up 直接 commit
# =============================================================================
class TestNoDirectCommit:
    """R2-2: 验证 _rehash 不再直接 db.session.commit()"""

    def test_01_rehash_does_not_direct_commit(self):
        """rehash 必须走 osql_up, 不能用 db.session.commit()"""
        from app.tools.shellcmd import get_ssh_password
        from app.tools.basesec import base64_auto
        from cryptography.fernet import Fernet

        legacy_stored = base64_auto('en', 'legacy_pwd')

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)

        mock_row = MagicMock()
        mock_row.id = 33
        mock_row.host_password = legacy_stored

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up') as mock_osql_up, \
             patch('app.tools.shellcmd.db.session.commit') as mock_commit:
            get_ssh_password(mock_row)

        mock_osql_up.assert_called_once()
        mock_commit.assert_not_called()

    def test_02_rehash_does_not_setattr_orm_row(self):
        """rehash 不应再 sys_user_row.host_password = new"""
        from app.tools.shellcmd import get_ssh_password
        from app.tools.basesec import base64_auto
        from cryptography.fernet import Fernet

        legacy_stored = base64_auto('en', 'legacy_pwd')

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)

        mock_row = MagicMock()
        mock_row.id = 44
        mock_row.host_password = legacy_stored

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up'):
            get_ssh_password(mock_row)

        assert mock_row.host_password == legacy_stored


# =============================================================================
# 5) 兼容性 (回退测试)
# =============================================================================
class TestBackwardsCompat:
    """R2-2: 不破坏现有 Fernet 解密流程"""

    def test_01_modern_fernet_no_rehash_no_osql(self):
        """现代 Fernet 密文, 不调 rehash, 不调 osql_up"""
        from app.tools.shellcmd import get_ssh_password
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        f = Fernet(key)
        ciphertext = f.encrypt(b'super_secret').decode()

        mock_row = MagicMock()
        mock_row.id = 55
        mock_row.host_password = ciphertext

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up') as mock_osql_up:
            result = get_ssh_password(mock_row)

        assert result == 'super_secret'
        mock_osql_up.assert_not_called()

    def test_02_invalid_stored_returns_none_or_raises(self):
        """非法 stored 值应抛 RuntimeError (decrypt 内部)"""
        from app.tools.shellcmd import get_ssh_password
        mock_row = MagicMock()
        mock_row.id = 66
        mock_row.host_password = 'not-base64-not-fernet-garbage'

        with pytest.raises(Exception):
            get_ssh_password(mock_row)


# =============================================================================
# 6) 集成: end-to-end 透明迁移
# =============================================================================
class TestEndToEndMigration:
    """R2-2: 端到端 base64 → Fernet 透明迁移"""

    def test_01_first_call_writes_fernet(self):
        """首次调用 (stored=base64) 走 osql_up 写 Fernet"""
        from app.tools.shellcmd import get_ssh_password
        from app.tools.basesec import base64_auto
        from cryptography.fernet import Fernet

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)
        plain = 'user_actual_password'
        legacy = base64_auto('en', plain)

        mock_row = MagicMock()
        mock_row.id = 77
        mock_row.host_password = legacy

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up') as mock_osql_up:
            result = get_ssh_password(mock_row)

        assert result == plain
        mock_osql_up.assert_called_once()
        new_pwd = mock_osql_up.call_args[0][2]['host_password']
        assert new_pwd.startswith('gAAAAA')
        decrypted = f.decrypt(new_pwd.encode()).decode()
        assert decrypted == plain

    def test_02_subsequent_call_no_rehash(self):
        """第二次调用 (stored=新 Fernet) 不应再 rehash"""
        from app.tools.shellcmd import get_ssh_password
        from cryptography.fernet import Fernet

        fernet_key = Fernet.generate_key().decode()
        f = Fernet(fernet_key)
        ciphertext = f.encrypt(b'user_password').decode()

        mock_row = MagicMock()
        mock_row.id = 88
        mock_row.host_password = ciphertext

        with patch.dict(os.environ, {'OGS_FERNET_KEYS': fernet_key,
                                     'OGS_ENV': 'dev'}), \
             patch('app.tools.basesec._get_fernet_list', return_value=[f]), \
             patch('app.core.db.insert.osql_up') as mock_osql_up:
            get_ssh_password(mock_row)

        mock_osql_up.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
