"""REV46-M22: ssh_cmd stdout.read 同步阻塞 → 加 select timeout.

- 新增 SshCommandTimeout 异常类 (供调用方识别)
- 新增 _read_with_select helper (select 轮询 + SSH_CMD_TIMEOUT)
- 新增 SSH_CMD_TIMEOUT 配置 (默认 30s, env OGS_SSH_CMD_TIMEOUT)
- ssh_cmd 改用 _read_with_select 读取 stdout/stderr

测试覆盖:
  TestM22Config: SSH_CMD_TIMEOUT 配置存在, 默认 30
  TestM22Exception: SshCommandTimeout 异常类
  TestM22Helper: _read_with_select 单元 (mock channel)
  TestM22Integration: ssh_cmd 集成 (mock ssh_client.exec_command)
  TestM22StaticAnalysis: 源码静态标记
"""
import inspect
import time
from unittest import mock

import pytest


# =============================================================================
# TestM22Config: SSH_CMD_TIMEOUT 配置
# =============================================================================
class TestM22Config:
    """REV46-M22: SSH_CMD_TIMEOUT 配置存在 + 默认值."""

    def test_ssh_cmd_timeout_imported(self):
        from app.core.config import SSH_CMD_TIMEOUT
        assert isinstance(SSH_CMD_TIMEOUT, int)
        assert SSH_CMD_TIMEOUT > 0

    def test_ssh_cmd_timeout_default_30(self):
        """默认 30s 兼容 apt/dnf 等慢命令."""
        from app.core.config import SSH_CMD_TIMEOUT
        # 默认值由 _env 决定, 显式未设时为 30
        assert SSH_CMD_TIMEOUT == 30

    def test_ssh_cmd_timeout_importable_from_shellcmd(self):
        from app.tools.shellcmd import SSH_CMD_TIMEOUT
        assert isinstance(SSH_CMD_TIMEOUT, int)
        assert SSH_CMD_TIMEOUT > 0


# =============================================================================
# TestM22Exception: SshCommandTimeout 异常类
# =============================================================================
class TestM22Exception:
    """REV46-M22: SshCommandTimeout 异常类存在且可抛可接."""

    def test_ssh_command_timeout_exists(self):
        from app.tools.shellcmd import SshCommandTimeout
        assert issubclass(SshCommandTimeout, Exception)

    def test_ssh_command_timeout_raisable(self):
        from app.tools.shellcmd import SshCommandTimeout
        with pytest.raises(SshCommandTimeout) as exc_info:
            raise SshCommandTimeout('test timeout after 30s')
        assert '30s' in str(exc_info.value)

    def test_ssh_command_timeout_distinct_from_dangerous(self):
        from app.tools.shellcmd import (
            SshCommandTimeout, DangerousCommandError
        )
        # 两种异常类型必须可区分
        assert SshCommandTimeout is not DangerousCommandError
        assert not issubclass(SshCommandTimeout, DangerousCommandError)
        assert not issubclass(DangerousCommandError, SshCommandTimeout)


# =============================================================================
# TestM22Helper: _read_with_select 单元
# =============================================================================
class TestM22Helper:
    """REV46-M22: _read_with_select 单元测试 (mock channel)."""

    def test_read_with_select_importable(self):
        from app.tools.shellcmd import _read_with_select
        assert callable(_read_with_select)

    def test_read_with_select_normal_data(self):
        """正常路径: select 立即可读, 一次 recv 返回所有数据."""
        from app.tools.shellcmd import _read_with_select
        fake_channel = mock.MagicMock()
        fake_channel.status_event.is_set.return_value = False
        fake_channel.exit_status_ready.return_value = True
        # select 立即返回可读
        with mock.patch('app.tools.shellcmd.select.select') as mock_sel:
            mock_sel.return_value = ([fake_channel], [], [])
            fake_channel.recv.return_value = b'hello world'
            result = _read_with_select(fake_channel, 1024, timeout=5)
        assert result == b'hello world'

    def test_read_with_select_empty_channel(self):
        """空通道: EOF 立即返回 b''."""
        from app.tools.shellcmd import _read_with_select
        fake_channel = mock.MagicMock()
        fake_channel.status_event.is_set.return_value = False
        fake_channel.exit_status_ready.return_value = True
        with mock.patch('app.tools.shellcmd.select.select') as mock_sel:
            mock_sel.return_value = ([fake_channel], [], [])
            fake_channel.recv.return_value = b''  # EOF
            result = _read_with_select(fake_channel, 1024, timeout=5)
        assert result == b''

    def test_read_with_select_timeout_raises(self):
        """超时路径: select 始终不可读 → 抛 SshCommandTimeout."""
        from app.tools.shellcmd import (
            _read_with_select, SshCommandTimeout
        )
        fake_channel = mock.MagicMock()
        fake_channel.status_event.is_set.return_value = False
        fake_channel.exit_status_ready.return_value = False
        # select 始终返回空 (无可读) → 触发超时
        with mock.patch('app.tools.shellcmd.select.select') as mock_sel:
            mock_sel.return_value = ([], [], [])
            # 缩短 timeout 让测试快
            with pytest.raises(SshCommandTimeout) as exc_info:
                _read_with_select(fake_channel, 1024, timeout=1)
        # 超时消息应包含秒数
        assert 'timeout' in str(exc_info.value).lower()
        assert '1s' in str(exc_info.value)

    def test_read_with_select_socket_timeout_raises(self):
        """recv 抛 socket.timeout → 抛 SshCommandTimeout."""
        from app.tools.shellcmd import (
            _read_with_select, SshCommandTimeout
        )
        fake_channel = mock.MagicMock()
        fake_channel.status_event.is_set.return_value = False
        fake_channel.exit_status_ready.return_value = True
        with mock.patch('app.tools.shellcmd.select.select') as mock_sel:
            mock_sel.return_value = ([fake_channel], [], [])
            fake_channel.recv.side_effect = socket_timeout_factory()
            with pytest.raises(SshCommandTimeout):
                _read_with_select(fake_channel, 1024, timeout=5)

    def test_read_with_select_select_oserror_break(self):
        """select 抛 OSError → 跳出循环, 不抛异常."""
        from app.tools.shellcmd import _read_with_select
        fake_channel = mock.MagicMock()
        with mock.patch('app.tools.shellcmd.select.select') as mock_sel:
            mock_sel.side_effect = OSError('channel closed')
            result = _read_with_select(fake_channel, 1024, timeout=5)
        # OSError 触发 break, 返回空 bytes
        assert result == b''

    def test_read_with_select_multi_chunk(self):
        """多次 recv 拼接, 读到 EOF 结束."""
        from app.tools.shellcmd import _read_with_select
        fake_channel = mock.MagicMock()
        # 第一次 recv 返回 'abc', 第二次 'def', 第三次空 (EOF)
        chunks = [b'abc', b'def', b'']
        fake_channel.recv.side_effect = lambda n: chunks.pop(0) if chunks else b''
        # 每次 select 都立即可读
        call_count = {'n': 0}

        def fake_select(rlist, wlist, xlist, timeout):
            call_count['n'] += 1
            if call_count['n'] <= 2:
                return ([fake_channel], [], [])
            # 第三次后退出
            return ([], [], [])

        with mock.patch('app.tools.shellcmd.select.select',
                        side_effect=fake_select):
            # 第二次后 exit_status_ready=True → 退出循环
            fake_channel.exit_status_ready.side_effect = [False, True, True]
            result = _read_with_select(fake_channel, 1024, timeout=10)
        assert result == b'abcdef'


def socket_timeout_factory():
    import socket
    return socket.timeout('read timeout')


# =============================================================================
# TestM22Integration: ssh_cmd 集成
# =============================================================================
class TestM22Integration:
    """REV46-M22: ssh_cmd 改用 _read_with_select."""

    def _make_rca(self):
        """构造一个旁路 __init__ 的 RemoteConnectionAuto."""
        from app.tools.shellcmd import RemoteConnectionAuto
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = 'test'
        rca.port = 22
        rca.username = 'test'
        rca.password = 'test'
        rca.ssh = mock.MagicMock()
        return rca

    def _make_exec_command_mock(self, stdout_bytes=b'hello\n',
                                 stderr_bytes=b''):
        """构造 ssh.exec_command 返回的 (stdin, stdout, stderr) 三元组."""
        stdin = mock.MagicMock()
        stdout = mock.MagicMock()
        stderr = mock.MagicMock()
        # channel 用于 select 读取
        stdout.channel = mock.MagicMock()
        stderr.channel = mock.MagicMock()
        stdout.channel.status_event.is_set.return_value = False
        stdout.channel.exit_status_ready.return_value = True
        stderr.channel.status_event.is_set.return_value = False
        stderr.channel.exit_status_ready.return_value = True
        stdout.channel.recv_ready.return_value = False
        stderr.channel.recv_ready.return_value = False
        return stdin, stdout, stderr

    def test_ssh_cmd_uses_select(self):
        """ssh_cmd 调 exec_command 后应走 select-based 读取."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_command_mock(
            stdout_bytes=b'OK'
        )
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)

        with mock.patch('app.tools.shellcmd._read_with_select') as mock_read:
            mock_read.side_effect = [b'OK', b'']
            result = rca.ssh_cmd('ls')
        assert result == 'OK'
        # 至少被调用 2 次 (stdout + stderr)
        assert mock_read.call_count >= 2

    def test_ssh_cmd_normal_path(self):
        """正常路径: select 立即可读, 返回 stdout 解码结果."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_command_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)

        def fake_read(channel, max_bytes, timeout):
            if channel is stdout.channel:
                return b'stdout-data'
            return b'stderr-data'

        with mock.patch('app.tools.shellcmd._read_with_select',
                        side_effect=fake_read):
            result = rca.ssh_cmd('echo hi')
        assert result == 'stdout-data'

    def test_ssh_cmd_timeout_propagates(self):
        """超时路径: _read_with_select 抛 SshCommandTimeout → ssh_cmd 透传."""
        from app.tools.shellcmd import SshCommandTimeout
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_command_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        with mock.patch('app.tools.shellcmd._read_with_select') as mock_read:
            mock_read.side_effect = SshCommandTimeout('timeout after 30s')
            with pytest.raises(SshCommandTimeout) as exc_info:
                rca.ssh_cmd('sleep 999')
        assert '30s' in str(exc_info.value)

    def test_ssh_cmd_close_even_on_timeout(self):
        """超时后连接生命周期由调用方管理 (M20).

        REV46-M20 修订: ssh_cmd 不再自动 close, 改由调用方 try/finally conn.close().
        本测试验证: 即使 ssh_cmd 抛 SshCommandTimeout, 调用方 try/finally 仍可
        通过 conn.close() 关闭连接 (防 fd 泄漏).
        """
        from app.tools.shellcmd import SshCommandTimeout
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_command_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        with mock.patch('app.tools.shellcmd._read_with_select') as mock_read:
            mock_read.side_effect = SshCommandTimeout('timeout')
            with pytest.raises(SshCommandTimeout):
                # 调用方模式: try/finally 显式 close
                try:
                    rca.ssh_cmd('sleep 999')
                finally:
                    rca.close()
        # 关键: 异常传播 + close 被调用 (调用方 finally 块)
        rca.ssh.close.assert_called_once()


# =============================================================================
# TestM22StaticAnalysis: 源码静态检查
# =============================================================================
class TestM22StaticAnalysis:
    """REV46-M22: 源码含标记, 同步 read 已替换."""

    def test_shellcmd_has_m22_marker(self):
        from app.tools import shellcmd
        source = inspect.getsource(shellcmd)
        assert 'REV46-M22' in source, "shellcmd.py 应含 REV46-M22 标记"

    def test_config_has_m22_marker(self):
        from app.core import config
        source = inspect.getsource(config)
        assert 'REV46-M22' in source, "config.py 应含 REV46-M22 标记"
        assert 'SSH_CMD_TIMEOUT' in source

    def test_ssh_cmd_no_sync_stdout_read(self):
        """ssh_cmd 内不应再有 'stdout.read(' 同步调用."""
        from app.tools.shellcmd import RemoteConnectionAuto
        source = inspect.getsource(RemoteConnectionAuto.ssh_cmd)
        # 剥离 docstring
        import re
        code_only = re.sub(r'"""[\s\S]*?"""', '', source)
        code_only = re.sub(r"'''[\s\S]*?'''", '', code_only)
        assert 'stdout.read(' not in code_only, \
            "REV46-M22: ssh_cmd 不应再调 stdout.read() 同步读"

    def test_ssh_cmd_uses_read_with_select(self):
        """ssh_cmd 应调 _read_with_select 读取 stdout/stderr."""
        from app.tools.shellcmd import RemoteConnectionAuto
        source = inspect.getsource(RemoteConnectionAuto.ssh_cmd)
        assert '_read_with_select' in source, \
            "REV46-M22: ssh_cmd 应调 _read_with_select"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
