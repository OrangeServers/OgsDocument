# -*- coding: utf-8 -*-
"""
R2-3 (REV46-M21): put_file / put_fileobj fd 泄漏

问题: 旧代码 sftp_client 在异常时不 close, fd 泄漏
修复: try/finally + sftp_cilent = None, 确保 close 被调用
测试维度:
  1) put_file 正常: sftp close 被调用
  2) put_file 异常: sftp close 仍被调用
  3) put_fileobj 正常: sftp close 被调用
  4) put_fileobj 异常: sftp close 仍被调用
  5) close() 自身抛异常被吞掉
  6) 路径校验失败不创建 sftp client
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def _make_mock_connection():
    """创建 RemoteConnectionAuto 实例, 不真连 SSH.

    把 paramiko.SSHClient 类整个 mock, 让 connect() no-op.
    然后单独 patch sftp client.
    """
    from app.tools.shellcmd import RemoteConnectionAuto

    # 直接 mock paramiko.SSHClient 类
    mock_ssh_instance = MagicMock()
    mock_ssh_instance.get_transport.return_value = MagicMock()

    with patch('app.tools.shellcmd.paramiko.SSHClient',
               return_value=mock_ssh_instance), \
         patch('os.path.isfile', return_value=True):
        rc = RemoteConnectionAuto('1.2.3.4', 22, 'user', password='pwd')

    return rc, mock_ssh_instance


# =============================================================================
# 1) put_file 正常流程
# =============================================================================
class TestPutFileHappyPath:
    """R2-3: put_file 正常完成时 sftp client 必须 close"""

    def test_01_put_file_closes_sftp_on_success(self):
        """put_file 正常成功, sftp_client.close() 必须被调用"""
        mock_sftp = MagicMock()
        close_calls = []
        mock_sftp.close = lambda: close_calls.append('closed')

        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   return_value=mock_sftp), \
             patch('app.tools.shellcmd._safe_remote_path',
                   return_value='/home/x/test.txt'):
            rc, _ = _make_mock_connection()
            rc.put_file('/local/path.txt', '/home/x/test.txt')

        assert len(close_calls) == 1, f"sftp close 未调用: {close_calls}"
        mock_sftp.put.assert_called_once_with('/local/path.txt', '/home/x/test.txt')


# =============================================================================
# 2) put_file 异常路径
# =============================================================================
class TestPutFileException:
    """R2-3: put_file 任何异常路径下 sftp client 也必须 close (不漏 fd)"""

    def test_01_sftp_put_raises_sftp_still_closed(self):
        """sftp.put 抛异常时 (e.g. disk full) sftp 仍要 close"""
        mock_sftp = MagicMock()
        mock_sftp.put = MagicMock(side_effect=IOError('disk full'))
        close_calls = []
        mock_sftp.close = lambda: close_calls.append('closed')

        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   return_value=mock_sftp), \
             patch('app.tools.shellcmd._safe_remote_path',
                   return_value='/home/x/test.txt'):
            rc, _ = _make_mock_connection()
            with pytest.raises(IOError):
                rc.put_file('/local/path.txt', '/home/x/test.txt')

        # 关键: 即使 put 抛异常, close 必须被调 (防 fd 泄漏)
        assert len(close_calls) == 1, \
            f"sftp close 未在异常路径调用 (fd 泄漏风险): {close_calls}"

    def test_02_sftpclient_from_transport_raises_no_close(self):
        """SFTPClient.from_transport 抛异常时, 没有 sftp client 可 close, 不出错"""
        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   side_effect=Exception('transport broken')), \
             patch('app.tools.shellcmd._safe_remote_path',
                   return_value='/home/x/test.txt'):
            rc, _ = _make_mock_connection()
            # 透传原始异常
            with pytest.raises(Exception, match='transport broken'):
                rc.put_file('/local/path.txt', '/home/x/test.txt')


# =============================================================================
# 3) put_fileobj 正常 / 异常
# =============================================================================
class TestPutFileObj:
    """R2-3: put_fileobj 也必须 try/finally close"""

    def test_01_put_fileobj_closes_sftp_on_success(self):
        """put_fileobj 正常成功, sftp close 被调"""
        mock_sftp = MagicMock()
        close_calls = []
        mock_sftp.close = lambda: close_calls.append('closed')

        fake_file = MagicMock()

        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   return_value=mock_sftp), \
             patch('app.tools.shellcmd._safe_remote_path',
                   return_value='/home/x/obj.txt'):
            rc, _ = _make_mock_connection()
            rc.put_fileobj(fake_file, '/home/x/obj.txt')

        assert len(close_calls) == 1
        mock_sftp.putfo.assert_called_once()

    def test_02_put_fileobj_exception_still_closes(self):
        """put_fileobj 异常时 sftp 仍 close"""
        mock_sftp = MagicMock()
        mock_sftp.putfo = MagicMock(side_effect=IOError('net error'))
        close_calls = []
        mock_sftp.close = lambda: close_calls.append('closed')

        fake_file = MagicMock()

        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   return_value=mock_sftp), \
             patch('app.tools.shellcmd._safe_remote_path',
                   return_value='/home/x/obj.txt'):
            rc, _ = _make_mock_connection()
            with pytest.raises(IOError):
                rc.put_fileobj(fake_file, '/home/x/obj.txt')

        # 异常路径仍要 close
        assert len(close_calls) == 1, \
            f"sftp close 未在 put_fileobj 异常路径调用 (fd 泄漏): {close_calls}"


# =============================================================================
# 4) close() 自身异常被吞掉
# =============================================================================
class TestCloseErrorSwallowed:
    """R2-3: close() 自身异常被吞掉, 不阻断主流程"""

    def test_01_sftp_close_raises_swallowed(self):
        """sftp.close() 抛异常不影响 put_file 主流程"""
        mock_sftp = MagicMock()
        # close 抛异常 - 应被 except 吞掉
        mock_sftp.close = MagicMock(side_effect=Exception('close error'))

        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   return_value=mock_sftp), \
             patch('app.tools.shellcmd._safe_remote_path',
                   return_value='/home/x/test.txt'):
            rc, _ = _make_mock_connection()
            # 不应抛 close 的异常
            rc.put_file('/local/path.txt', '/home/x/test.txt')

        mock_sftp.put.assert_called_once()
        mock_sftp.close.assert_called_once()


# =============================================================================
# 5) 路径校验失败: 不创建 sftp client
# =============================================================================
class TestPathValidationNoSftp:
    """R2-3: _safe_remote_path 失败时, sftp client 不应被创建"""

    def test_01_path_validation_fails_no_sftp(self):
        """路径不安全时 (白名单外/../) 不创建 sftp client, 直接抛"""
        mock_sftp_class = MagicMock()

        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   mock_sftp_class):
            rc, _ = _make_mock_connection()

            # 路径含 .. 应被 _safe_remote_path 拒绝
            with pytest.raises(ValueError, match='path traversal'):
                rc.put_file('/local/x', '/home/../../../etc/passwd')

        # sftp client 创建函数不应被调
        mock_sftp_class.assert_not_called()

    def test_02_path_not_in_whitelist_no_sftp(self):
        """路径不在白名单前缀 (/etc, /root, /) 不创建 sftp"""
        mock_sftp_class = MagicMock()

        with patch('app.tools.shellcmd.paramiko.SFTPClient.from_transport',
                   mock_sftp_class):
            rc, _ = _make_mock_connection()

            with pytest.raises(ValueError, match='not in allowed'):
                rc.put_file('/local/x', '/etc/passwd')

        mock_sftp_class.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
