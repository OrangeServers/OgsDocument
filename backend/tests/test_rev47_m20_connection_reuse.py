"""REV46-M20: ssh_cmd 每次 close → 复用连接 + 显式 close().

- RemoteConnectionAuto 新增 close() 方法 (显式关闭)
- RemoteConnectionAuto 新增 __enter__/__exit__ (上下文管理器)
- ssh_cmd 移除 finally 自动 close, 连接生命周期由调用方管理
- 所有 ssh_cmd 调用方 (ServerManagement / cron) 改用 try/finally 显式 close

测试覆盖:
  TestM20CloseMethod: close() 方法 + 幂等
  TestM20ContextManager: __enter__/__exit__ 上下文
  TestM20SshCmdNoAutoClose: ssh_cmd 多次调用不触发 close
  TestM20Callsites: 调用方源码含 try/finally conn.close()
  TestM20StaticAnalysis: 源码静态标记
"""
import inspect
import os
import re
import sys
from unittest import mock

import pytest

# ti3-TS 修复: 用 ROOT 绝对路径避免 cwd 依赖
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# =============================================================================
# TestM20CloseMethod: close() 方法
# =============================================================================
class TestM20CloseMethod:
    """REV46-M20: RemoteConnectionAuto.close() 存在 + 幂等 + 安全."""

    def _make_rca(self):
        from app.tools.shellcmd import RemoteConnectionAuto
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = 'test'
        rca.port = 22
        rca.username = 'test'
        rca.password = 'test'
        rca.ssh = mock.MagicMock()
        rca._closed = False
        return rca

    def test_close_method_exists(self):
        from app.tools.shellcmd import RemoteConnectionAuto
        assert hasattr(RemoteConnectionAuto, 'close')
        assert callable(RemoteConnectionAuto.close)

    def test_close_calls_ssh_close(self):
        rca = self._make_rca()
        rca.close()
        rca.ssh.close.assert_called_once()

    def test_close_is_idempotent(self):
        """close() 多次调用安全, 只关一次."""
        rca = self._make_rca()
        rca.close()
        rca.close()
        rca.close()
        # 幂等: 第二次起 self.ssh.close 不再被调
        assert rca.ssh.close.call_count == 1

    def test_close_sets_closed_flag(self):
        rca = self._make_rca()
        assert rca._closed is False
        rca.close()
        assert rca._closed is True

    def test_close_swallows_ssh_close_exception(self):
        """ssh.close() 抛异常时 close() 自身不抛."""
        rca = self._make_rca()
        rca.ssh.close.side_effect = Exception('boom')
        # 不应抛
        rca.close()
        assert rca._closed is True


# =============================================================================
# TestM20ContextManager: __enter__/__exit__
# =============================================================================
class TestM20ContextManager:
    """REV46-M20: RemoteConnectionAuto 支持 with 语句."""

    def _make_rca(self):
        from app.tools.shellcmd import RemoteConnectionAuto
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = 'test'
        rca.ssh = mock.MagicMock()
        rca._closed = False
        return rca

    def test_with_statement_calls_close(self):
        rca = self._make_rca()
        with rca as conn:
            assert conn is rca
        rca.ssh.close.assert_called_once()

    def test_with_statement_closes_on_exception(self):
        rca = self._make_rca()
        with pytest.raises(RuntimeError):
            with rca as conn:
                raise RuntimeError('test')
        rca.ssh.close.assert_called_once()

    def test_enter_returns_self(self):
        rca = self._make_rca()
        with rca as conn:
            assert conn is rca

    def test_exit_does_not_swallow_exception(self):
        """__exit__ 不返回 True, 异常应正常传播."""
        rca = self._make_rca()
        with pytest.raises(ValueError) as exc_info:
            with rca as conn:
                raise ValueError('propagate me')
        assert 'propagate me' in str(exc_info.value)
        rca.ssh.close.assert_called_once()


# =============================================================================
# TestM20SshCmdNoAutoClose: ssh_cmd 不再自动 close
# =============================================================================
class TestM20SshCmdNoAutoClose:
    """REV46-M20: ssh_cmd 多次调用, 连接复用 (不自动 close)."""

    def _make_rca(self, ssh=None):
        from app.tools.shellcmd import RemoteConnectionAuto
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = 'test'
        rca.port = 22
        rca.username = 'test'
        rca.password = 'test'
        rca.ssh = ssh or mock.MagicMock()
        rca._closed = False
        return rca

    def _make_exec_mock(self):
        mock_chan = mock.MagicMock()
        mock_chan.recv_ready.return_value = False
        mock_chan.status_event.is_set.return_value = False
        mock_chan.exit_status_ready.return_value = True
        stdin = mock.MagicMock()
        stdout = mock.MagicMock()
        stdout.channel = mock_chan
        stderr = mock.MagicMock()
        stderr.channel = mock_chan
        return stdin, stdout, stderr

    def test_ssh_cmd_does_not_close_after_call(self):
        """ssh_cmd 调完后, self.ssh.close 不应被自动调."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        with mock.patch('app.tools.shellcmd._read_with_select') as mock_read:
            mock_read.return_value = b'OK'
            rca.ssh_cmd('ls')
        # 关键断言: ssh.close 未被自动调
        rca.ssh.close.assert_not_called()

    def test_ssh_cmd_reuse_connection(self):
        """多次 ssh_cmd 共用同一连接, 最后才显式 close."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        with mock.patch('app.tools.shellcmd._read_with_select') as mock_read:
            mock_read.return_value = b'OK'
            rca.ssh_cmd('cmd1')
            rca.ssh_cmd('cmd2')
            rca.ssh_cmd('cmd3')
        # 三次 ssh_cmd 共用一个 exec_command
        assert rca.ssh.exec_command.call_count == 3
        # 整个过程中 close 未被自动调
        rca.ssh.close.assert_not_called()
        # 显式 close
        rca.close()
        rca.ssh.close.assert_called_once()

    def test_explicit_close_via_with(self):
        """with 语句也能复用连接."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        with mock.patch('app.tools.shellcmd._read_with_select',
                        return_value=b'OK'):
            with rca as conn:
                conn.ssh_cmd('cmd1')
                conn.ssh_cmd('cmd2')
        # with 退出时调用 close
        rca.ssh.close.assert_called_once()


# =============================================================================
# TestM20Callsites: 调用方源码含 try/finally conn.close()
# =============================================================================
class TestM20Callsites:
    """REV46-M20: 所有 ssh_cmd 调用方都用 try/finally conn.close()."""

    def _check_source_has_m20_pattern(self, filepath, min_count=1):
        """检查源文件含 'conn.close()' 至少 min_count 次 (M20 模式)."""
        from pathlib import Path
        full = Path(filepath)
        if not full.exists():
            pytest.skip(f'{filepath} 不存在')
        text = full.read_text(encoding='utf-8')
        count = text.count('conn.close()')
        assert count >= min_count, \
            f'{filepath} 应含 conn.close() 至少 {min_count} 次, 实际 {count}'

    def test_servermanagement_has_m20_close(self):
        # 批量执行路径重构后改走 batch_service（connection_factory 注入，
        # 连接在 batch_service 的 finally 中关闭），入口文件剩 3 处直连调用点。
        self._check_source_has_m20_pattern(
            'app/assets/ServerManagement.py', min_count=3
        )

    def test_cron_has_m20_close(self):
        self._check_source_has_m20_pattern(
            'app/cron/cron.py', min_count=2
        )

    def test_servermanagement_uses_try_finally(self):
        """入口和共享批量服务都必须用 finally 关闭连接。"""
        from pathlib import Path
        entry_text = Path(os.path.join(ROOT, 'app/assets/ServerManagement.py')).read_text(
            encoding='utf-8'
        )
        service_text = Path(os.path.join(ROOT, 'app/assets/batch_service.py')).read_text(
            encoding='utf-8'
        )
        assert 'conn.close()' in entry_text
        assert 'connection.close()' in service_text
        assert entry_text.count('finally:') + service_text.count('finally:') >= 5

    def test_cron_uses_try_finally(self):
        from pathlib import Path
        # ti3-TS 修复: 用 ROOT 绝对路径
        text = Path(os.path.join(ROOT, 'app/cron/cron.py')).read_text(encoding='utf-8')
        assert 'conn.close()' in text
        assert text.count('finally:') >= 2


# =============================================================================
# TestM20StaticAnalysis: 源码静态检查
# =============================================================================
class TestM20StaticAnalysis:
    """REV46-M20: 源码标记 + 旧 finally 自动 close 已删除."""

    def test_shellcmd_has_m20_marker(self):
        from app.tools import shellcmd
        source = inspect.getsource(shellcmd)
        assert 'REV46-M20' in source

    def test_ssh_cmd_no_autoclose_finally(self):
        """ssh_cmd 不应再有 'finally: self.ssh.close' 模式."""
        from app.tools.shellcmd import RemoteConnectionAuto
        source = inspect.getsource(RemoteConnectionAuto.ssh_cmd)
        # 剥离 docstring + 注释
        code_only = re.sub(r'"""[\s\S]*?"""', '', source)
        code_only = re.sub(r"'''[\s\S]*?'''", '', code_only)
        # 关键: ssh_cmd 函数体内部不应有 'self.ssh.close()' (旧 finally 模式)
        assert 'self.ssh.close()' not in code_only, \
            "REV46-M20: ssh_cmd 不应再直接调 self.ssh.close() (改由 close() 方法)"

    def test_close_method_docstring(self):
        """close() 方法应有 docstring 说明 M20."""
        from app.tools.shellcmd import RemoteConnectionAuto
        assert RemoteConnectionAuto.close.__doc__ is not None
        assert 'REV46-M20' in RemoteConnectionAuto.close.__doc__ or \
               'M20' in RemoteConnectionAuto.close.__doc__ or \
               '复用' in RemoteConnectionAuto.close.__doc__

    def test_context_manager_protocol(self):
        """RemoteConnectionAuto 应实现 __enter__/__exit__."""
        from app.tools.shellcmd import RemoteConnectionAuto
        assert hasattr(RemoteConnectionAuto, '__enter__')
        assert hasattr(RemoteConnectionAuto, '__exit__')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
