# -*- coding: utf-8 -*-
"""REV40-H1: sftp.py mkdir/rm/rename 路径沙箱单测.

背景:
- 之前 _handle_mkdir / _handle_rm / _handle_rename 三个方法直接接受前端传的 path
  调 self.sftp.mkdir/rmdir/remove/rename, 无任何校验
- 攻击者可写 /etc/passwd / ~/.ssh/authorized_keys / /var/spool/cron 等
- 修复: 加 _safe_sftp_path 沙箱, 路径必须在白名单前缀下
"""
import os
from unittest.mock import MagicMock

import pytest


# =============================================================================
# 测试 1: _safe_sftp_path 白名单
# =============================================================================
class TestSafeSftpPath:
    """H1: SFTP 路径白名单校验."""

    def test_allowed_prefix_accepted(self):
        """白名单前缀下路径通过."""
        from app.ssh.sftp import _safe_sftp_path
        for ok in (
            '/tmp/ogs_uploads/2024/file.txt',
            '/tmp/ogs_uploads/dir',
            '/tmp/ogs_uploads/',
            '/home/alice/upload.bin',
            '/data/file.csv',
            '/opt/app/conf.yaml',
            '/var/upload/data.bin',
        ):
            assert _safe_sftp_path(ok) is not None

    def test_disallowed_prefix_rejected(self):
        """白名单外路径被拒."""
        from app.ssh.sftp import _safe_sftp_path
        for bad in (
            '/etc/passwd',
            '/etc/shadow',
            '/root/.bashrc',
            '/root/.ssh/authorized_keys',
            '/var/spool/cron/root',
            '/usr/bin/python',
            '/bin/sh',
        ):
            with pytest.raises(ValueError):
                _safe_sftp_path(bad)

    def test_path_traversal_rejected(self):
        """路径穿越被拒."""
        from app.ssh.sftp import _safe_sftp_path
        for traversal in (
            '/tmp/../../../etc/passwd',
            '/home/alice/../../etc/shadow',
            '/data/./../../var/spool/cron/root',
            '/tmp/ogs_uploads/../../../etc/crontab',
        ):
            with pytest.raises(ValueError):
                _safe_sftp_path(traversal)

    def test_relative_path_rejected(self):
        """相对路径被拒 (必须绝对路径)."""
        from app.ssh.sftp import _safe_sftp_path
        with pytest.raises(ValueError):
            _safe_sftp_path('tmp/ogs_uploads/file.txt')

    def test_empty_path_rejected(self):
        """空路径被拒."""
        from app.ssh.sftp import _safe_sftp_path
        with pytest.raises(ValueError):
            _safe_sftp_path('')

    def test_nul_char_rejected(self):
        """含 NUL 字符被拒."""
        from app.ssh.sftp import _safe_sftp_path
        with pytest.raises(ValueError):
            _safe_sftp_path('/tmp/ogs_uploads/\x00file.txt')

    def test_non_string_rejected(self):
        """非字符串被拒."""
        from app.ssh.sftp import _safe_sftp_path
        for bad in (None, 123, b'/tmp/file', ['list'], {'dict': 1}):
            with pytest.raises(ValueError):
                _safe_sftp_path(bad)


# =============================================================================
# 测试 2: _handle_mkdir / _handle_rm / _handle_rename 沙箱拦截
# =============================================================================
class TestSftpHandlersSandbox:
    """H1: 三个 handler 必须调 _safe_sftp_path, 攻击者传入非法路径时拒绝."""

    def _make_bridge(self):
        """创建 SftpBridge 实例, 旁路 __init__ / websocket."""
        from app.ssh.sftp import SftpBridge
        bridge = SftpBridge.__new__(SftpBridge)
        bridge.sftp = MagicMock()
        bridge.ws = MagicMock()
        # _send_success / _send_error 也 mock
        bridge._send_success = MagicMock()
        bridge._send_error = MagicMock()
        return bridge

    # ---- mkdir ----
    def test_handle_mkdir_safe_path_calls_sftp(self):
        """/tmp/ogs_uploads/foo 路径允许, 应调 sftp.mkdir."""
        bridge = self._make_bridge()
        bridge._handle_mkdir({'path': '/tmp/ogs_uploads/foo'})
        bridge.sftp.mkdir.assert_called_once()
        bridge._send_success.assert_called_once()
        bridge._send_error.assert_not_called()

    def test_handle_mkdir_path_traversal_blocked(self):
        """路径穿越 /etc/passwd 被拦, 不调 sftp.mkdir."""
        bridge = self._make_bridge()
        bridge._handle_mkdir({'path': '/tmp/../../etc/passwd'})
        bridge.sftp.mkdir.assert_not_called()
        bridge._send_success.assert_not_called()
        bridge._send_error.assert_called_once()
        # 调用参数含 "traversal" 字样
        call_args = bridge._send_error.call_args
        assert 'traversal' in str(call_args).lower() or 'passwd' in str(call_args).lower()

    def test_handle_mkdir_disallowed_prefix_blocked(self):
        """/root/.ssh 路径被拦."""
        bridge = self._make_bridge()
        bridge._handle_mkdir({'path': '/root/.ssh/backdoor'})
        bridge.sftp.mkdir.assert_not_called()
        bridge._send_error.assert_called_once()

    # ---- rm ----
    def test_handle_rm_safe_path_calls_sftp_rm(self):
        """安全路径调 sftp.remove."""
        bridge = self._make_bridge()
        bridge._handle_rm({'path': '/tmp/ogs_uploads/old.txt', 'isDir': False})
        bridge.sftp.remove.assert_called_once()
        bridge.sftp.rmdir.assert_not_called()
        bridge._send_success.assert_called_once()

    def test_handle_rm_safe_path_calls_sftp_rmdir(self):
        """目录删调用 sftp.rmdir."""
        bridge = self._make_bridge()
        bridge._handle_rm({'path': '/tmp/ogs_uploads/dir', 'isDir': True})
        bridge.sftp.rmdir.assert_called_once()
        bridge.sftp.remove.assert_not_called()

    def test_handle_rm_path_traversal_blocked(self):
        """rm /etc/passwd 被拦."""
        bridge = self._make_bridge()
        bridge._handle_rm({'path': '/etc/passwd', 'isDir': False})
        bridge.sftp.remove.assert_not_called()
        bridge._send_error.assert_called_once()

    # ---- rename ----
    def test_handle_rename_safe_paths(self):
        """合法 rename 调 sftp.rename."""
        bridge = self._make_bridge()
        bridge._handle_rename({
            'old_path': '/tmp/ogs_uploads/old.txt',
            'new_path': '/tmp/ogs_uploads/new.txt',
        })
        bridge.sftp.rename.assert_called_once()
        bridge._send_success.assert_called_once()

    def test_handle_rename_old_path_traversal_blocked(self):
        """old_path 含 .. 被拦."""
        bridge = self._make_bridge()
        bridge._handle_rename({
            'old_path': '/tmp/../etc/passwd',
            'new_path': '/tmp/ogs_uploads/file.txt',
        })
        bridge.sftp.rename.assert_not_called()
        bridge._send_error.assert_called_once()

    def test_handle_rename_new_path_traversal_blocked(self):
        """new_path 含 .. 被拦 (即使 old_path 合法)."""
        bridge = self._make_bridge()
        bridge._handle_rename({
            'old_path': '/tmp/ogs_uploads/old.txt',
            'new_path': '/home/../../etc/shadow',
        })
        bridge.sftp.rename.assert_not_called()
        bridge._send_error.assert_called_once()

    def test_handle_rename_to_disallowed_dir_blocked(self):
        """new_path 落到白名单外被拦."""
        bridge = self._make_bridge()
        bridge._handle_rename({
            'old_path': '/tmp/ogs_uploads/old.txt',
            'new_path': '/etc/passwd',
        })
        bridge.sftp.rename.assert_not_called()


# =============================================================================
# 测试 3: _safe_local_key_path 私钥校验 (REV40-H2)
# =============================================================================
class TestSafeLocalKeyPath:
    """H2 + REV46-H17 一致: 私钥路径 realpath 校验."""

    def test_legit_key_accepted(self, tmp_path, monkeypatch):
        """合法私钥文件路径通过."""
        from app.ssh import sftp as _sftp_module
        from app.core import config as _config_mod

        key_dir = tmp_path / 'key'
        key_dir.mkdir()
        key_file = key_dir / 'alice_rsa'
        key_file.write_text('fake private key')

        # REV47-T1: keypath.safe_key_path 内部 from app.core.config import FILE_CONF
        # 每次都重读, 所以 monkeypatch 必须打到 config 模块, 而不是业务模块.
        fake_conf = dict(_config_mod.FILE_CONF)
        fake_conf['key_path'] = str(key_dir) + os.sep
        monkeypatch.setattr(_config_mod, 'FILE_CONF', fake_conf)

        result = _sftp_module._safe_local_key_path('alice_rsa')
        assert result == str(key_file)

    def test_path_traversal_rejected(self):
        """../ 路径被拒."""
        from app.ssh.sftp import _safe_local_key_path
        with pytest.raises(ValueError):
            _safe_local_key_path('../../../etc/passwd')

    def test_absolute_path_rejected(self):
        """绝对路径被拒."""
        from app.ssh.sftp import _safe_local_key_path
        with pytest.raises(ValueError):
            _safe_local_key_path('/etc/passwd')

    def test_empty_rejected(self):
        """空串被拒."""
        from app.ssh.sftp import _safe_local_key_path
        with pytest.raises(ValueError):
            _safe_local_key_path('')

    def test_none_rejected(self):
        """None 被拒."""
        from app.ssh.sftp import _safe_local_key_path
        with pytest.raises(ValueError):
            _safe_local_key_path(None)

    def test_symlink_escape_rejected(self, tmp_path, monkeypatch):
        """symlink 指向 key_dir 外被拒."""
        from app.ssh import sftp as _sftp_module

        key_dir = tmp_path / 'key'
        key_dir.mkdir()
        outside = tmp_path / 'outside'
        outside.mkdir()
        evil_target = outside / 'evil'
        evil_target.write_text('evil')
        link = key_dir / 'evil'
        try:
            link.symlink_to(evil_target)
        except (OSError, NotImplementedError):
            pytest.skip('symlink not supported on this platform')

        fake_conf = dict(_sftp_module.FILE_CONF)
        fake_conf['key_path'] = str(key_dir) + os.sep
        monkeypatch.setattr(_sftp_module, 'FILE_CONF', fake_conf)

        with pytest.raises(ValueError):
            _sftp_module._safe_local_key_path('evil')