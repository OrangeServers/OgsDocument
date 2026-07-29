# -*- coding: utf-8 -*-
"""REV46-H16/H17: shellcmd 路径校验单测.

背景:
- H16: 之前 put_file / put_fileobj 无 to_path 校验, 攻击者可写任意远程路径
       (如 /etc/passwd, ~/.ssh/authorized_keys)
- H17: 之前 FILE_CONF['key_path'] + pkey 字符串拼接无校验,
       pkey 含 ../../ 可读取任意文件
- M21: 之前 put_file 异常不 close sftp_client (fd 泄漏)

修复:
- _safe_remote_path: 白名单 + .. 检测 + NUL 检测
- _safe_key_path: realpath + 在 key_path 目录下
- put_file/put_fileobj: finally 块 close sftp_client
"""
import os
import tempfile
from unittest.mock import MagicMock, patch


# =============================================================================
# 测试 1: _safe_remote_path 白名单
# =============================================================================
class TestSafeRemotePath:
    """H16: SFTP 目标路径白名单校验."""

    def test_allowed_prefix_accepted(self):
        """/home/, /tmp/, /var/upload/, /opt/, /data/ 下路径通过."""
        from app.tools.shellcmd import _safe_remote_path
        for ok in ('/home/alice/file.txt', '/tmp/upload.zip',
                   '/var/upload/data.bin', '/opt/app/conf.yaml',
                   '/data/file.csv'):
            assert _safe_remote_path(ok) is not None

    def test_disallowed_prefix_rejected(self):
        """/etc/, /root/, /usr/ 等不在白名单下的路径被拒."""
        from app.tools.shellcmd import _safe_remote_path
        for bad in ('/etc/passwd', '/root/.bashrc', '/usr/bin/python',
                    '/var/lib/mysql/data', '/bin/sh'):
            with pytest_raises(ValueError):
                _safe_remote_path(bad)

    def test_path_traversal_rejected(self):
        """含 .. 路径分隔符被拒 (路径穿越)."""
        from app.tools.shellcmd import _safe_remote_path
        for traversal in (
            '/home/../../../etc/passwd',
            '/tmp/../etc/shadow',
            '/data/./../../etc/hosts',
        ):
            with pytest_raises(ValueError):
                _safe_remote_path(traversal)

    def test_relative_path_rejected(self):
        """相对路径被拒 (必须绝对路径)."""
        from app.tools.shellcmd import _safe_remote_path
        with pytest_raises(ValueError):
            _safe_remote_path('home/alice/file.txt')  # 不以 / 开头

    def test_nul_char_rejected(self):
        """含 NUL 字符被拒."""
        from app.tools.shellcmd import _safe_remote_path
        with pytest_raises(ValueError):
            _safe_remote_path('/home/alice/\x00file.txt')

    def test_non_string_rejected(self):
        """非字符串入参被拒."""
        from app.tools.shellcmd import _safe_remote_path
        for bad in (None, 123, b'/home/alice/file.txt', ['/home/alice']):
            with pytest_raises(ValueError):
                _safe_remote_path(bad)

    def test_path_normalized(self):
        """合法路径被 os.path.normpath 规范化."""
        from app.tools.shellcmd import _safe_remote_path
        result = _safe_remote_path('/home/alice/./file.txt')
        # normpath 应去掉 ./
        assert '/./' not in result


# =============================================================================
# 测试 2: _safe_key_path realpath 校验
# =============================================================================
class TestSafeKeyPath:
    """H17: SSH 私钥路径 realpath 校验."""

    def test_legit_key_accepted(self, tmp_path, monkeypatch):
        """正常私钥文件名 (无 ../, 在 key_path 下) 通过."""
        # 创建临时 key 文件
        key_dir = tmp_path / 'key'
        key_dir.mkdir()
        key_file = key_dir / 'alice_rsa'
        key_file.write_text('fake private key')

        # REV47-T1: keypath.safe_key_path 内部 from app.core.config import FILE_CONF
        # 每次都重读, 所以 monkeypatch 必须打到 config 模块, 而不是 shellcmd.
        from app.core import config as _config_mod
        fake_conf = dict(_config_mod.FILE_CONF)
        fake_conf['key_path'] = str(key_dir) + os.sep
        monkeypatch.setattr(_config_mod, 'FILE_CONF', fake_conf)

        from app.tools.shellcmd import _safe_key_path
        result = _safe_key_path('alice_rsa')
        assert result == str(key_file)

    def test_absolute_path_rejected(self):
        """绝对路径被拒 (必须相对)."""
        from app.tools.shellcmd import _safe_key_path
        with pytest_raises(ValueError):
            _safe_key_path('/etc/passwd')

    def test_path_traversal_rejected(self):
        """含 ../ 被拒."""
        from app.tools.shellcmd import _safe_key_path
        for traversal in ('../../../etc/passwd', '../outside/file', 'a/b/../../../etc'):
            with pytest_raises(ValueError):
                _safe_key_path(traversal)

    def test_empty_string_rejected(self):
        """空字符串被拒."""
        from app.tools.shellcmd import _safe_key_path
        with pytest_raises(ValueError):
            _safe_key_path('')

    def test_none_rejected(self):
        """None 被拒."""
        from app.tools.shellcmd import _safe_key_path
        with pytest_raises(ValueError):
            _safe_key_path(None)

    def test_non_string_rejected(self):
        """非字符串被拒."""
        from app.tools.shellcmd import _safe_key_path
        for bad in (123, ['a'], b'bytes'):
            with pytest_raises(ValueError):
                _safe_key_path(bad)

    def test_symlink_escape_rejected(self, tmp_path, monkeypatch):
        """symlink 指向 key_dir 外被拒 (realpath 防 symlink 逃逸)."""
        # 准备 key_dir 和一个 symlink 指向外部
        key_dir = tmp_path / 'key'
        key_dir.mkdir()
        outside = tmp_path / 'outside'
        outside.mkdir()
        evil_target = outside / 'evil'
        evil_target.write_text('evil content')

        # key_dir/evil -> outside/evil
        link = key_dir / 'evil'
        try:
            link.symlink_to(evil_target)
        except (OSError, NotImplementedError):
            pytest.skip('symlink not supported on this platform')

        # monkeypatch shellcmd 模块内的 FILE_CONF
        from app.tools import shellcmd as _sc
        fake_conf = dict(_sc.FILE_CONF)
        fake_conf['key_path'] = str(key_dir) + os.sep
        monkeypatch.setattr(_sc, 'FILE_CONF', fake_conf)

        from app.tools.shellcmd import _safe_key_path
        # evil 是 symlink, realpath 后会跳出 key_dir, 拒绝
        with pytest_raises(ValueError):
            _safe_key_path('evil')


# =============================================================================
# 测试 3: put_file / put_fileobj 异常时 close
# =============================================================================
class TestPutFileSftpCleanup:
    """M21: put_file / put_fileobj 异常时也 close sftp_client (fd 泄漏)."""

    def test_put_file_exception_closes_sftp(self):
        """put_file 抛异常时 sftp_client.close() 被调用."""
        from app.tools import shellcmd as _sc

        # mock SSH transport
        mock_ssh = MagicMock()
        mock_ssh.get_transport.return_value = MagicMock()

        # patch paramiko.SFTPClient.from_transport 避免真实连接
        with patch.object(_sc.paramiko, 'SFTPClient') as MockSFTP:
            mock_sftp = MockSFTP.from_transport.return_value
            mock_sftp.put.side_effect = IOError('disk full')

            # 创建 instance (绕过 __init__)
            instance = _sc.RemoteConnectionAuto.__new__(_sc.RemoteConnectionAuto)
            instance.ssh = mock_ssh

            with pytest_raises(IOError):
                instance.put_file('/local/file', '/tmp/upload/file.txt')

            # close 应被调用 (即使抛异常)
            assert mock_sftp.close.called

    def test_put_fileobj_exception_closes_sftp(self):
        """put_fileobj 抛异常时 sftp_client.close() 被调用."""
        from app.tools import shellcmd as _sc

        mock_ssh = MagicMock()
        mock_ssh.get_transport.return_value = MagicMock()

        with patch.object(_sc.paramiko, 'SFTPClient') as MockSFTP:
            mock_sftp = MockSFTP.from_transport.return_value
            mock_sftp.putfo.side_effect = IOError('disk full')

            instance = _sc.RemoteConnectionAuto.__new__(_sc.RemoteConnectionAuto)
            instance.ssh = mock_ssh

            with pytest_raises(IOError):
                instance.put_fileobj(MagicMock(), '/tmp/upload/file.txt')

            assert mock_sftp.close.called

    def test_put_file_rejects_path_traversal(self):
        """put_file to_path 含 .. 被 _safe_remote_path 拒绝."""
        from app.tools import shellcmd as _sc

        mock_ssh = MagicMock()
        instance = _sc.RemoteConnectionAuto.__new__(_sc.RemoteConnectionAuto)
        instance.ssh = mock_ssh

        with pytest_raises(ValueError):
            instance.put_file('/local/file', '/home/../../../etc/passwd')

    def test_put_fileobj_rejects_disallowed_prefix(self):
        """put_fileobj to_path 不在白名单被拒绝."""
        from app.tools import shellcmd as _sc

        mock_ssh = MagicMock()
        instance = _sc.RemoteConnectionAuto.__new__(_sc.RemoteConnectionAuto)
        instance.ssh = mock_ssh

        with pytest_raises(ValueError):
            instance.put_fileobj(MagicMock(), '/etc/passwd')


# 兼容 pytest.raises
class _PytestRaises:
    def __call__(self, exc):
        import pytest as _p
        return _p.raises(exc)


pytest_raises = _PytestRaises()


import pytest  # noqa: E402