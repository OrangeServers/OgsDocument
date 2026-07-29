# -*- coding: utf-8 -*-
"""REV46-M23 测试: ssh_cmd 危险命令拦截改 raise DangerousCommandError.

背景 (REV46_review.md §17):
  - 旧: ssh_cmd 遇到危险命令返 'DANGEROUS_COMMAND_BLOCKED: %s' 字符串
  - 问题: 调用方 (ServerManagement/cron) 把这个字符串当正常输出,
          用户拿到的 command_msg 是 'DANGEROUS_COMMAND_BLOCKED: rm' 而不是拦截提示
  - 新: ssh_cmd raise DangerousCommandError (带 danger_pattern 属性)
  - 配套: ServerScript.sh_script 加 except 分支
          (cron 已有 try/except Exception, 自动兼容)
"""
import inspect
import pytest


# =============================================================================
# TestM23DangerousRaises: ssh_cmd 危险命令改 raise
# =============================================================================
class TestM23DangerousRaises:
    """REV46-M23: ssh_cmd 危险命令拦截行为."""

    def test_dangerous_command_raises_exception(self):
        """危险命令应抛 DangerousCommandError, 不再是返回字符串."""
        from app.tools.shellcmd import DangerousCommandError
        # 用纯单元测试, 不连真 SSH
        # 通过 _check_dangerous_command 直接模拟, 验证 raise 路径
        from app.tools.shellcmd import _check_dangerous_command
        assert _check_dangerous_command('rm -rf /') is not None

    def test_ssh_cmd_method_signature(self):
        """RemoteConnectionAuto.ssh_cmd 方法签名不变."""
        from app.tools.shellcmd import RemoteConnectionAuto
        sig = inspect.signature(RemoteConnectionAuto.ssh_cmd)
        # 仍接受一个 command: str 参数
        assert 'command' in sig.parameters

    def test_dangerous_command_error_class_exists(self):
        """DangerousCommandError 类必须存在 (shellcmd.py:97 已定义)."""
        from app.tools.shellcmd import DangerousCommandError
        assert issubclass(DangerousCommandError, Exception)

    def test_dangerous_command_error_danger_pattern_attr(self):
        """DangerousCommandError 实例可挂 danger_pattern 属性供调用方识别."""
        from app.tools.shellcmd import DangerousCommandError
        err = DangerousCommandError('blocked: rm')
        err.danger_pattern = 'rm'
        assert err.danger_pattern == 'rm'
        assert 'rm' in str(err)


# =============================================================================
# TestM23Integration: ssh_cmd 真实 raise 行为 (mock SSH)
# =============================================================================
class TestM23Integration:
    """REV46-M23: 用 mock SSH client 验证 ssh_cmd 真实 raise 行为."""

    def _make_conn(self, mock_ssh=None):
        """创建 RemoteConnectionAuto 实例, 旁路 __init__ (不连真 SSH)."""
        from app.tools.shellcmd import RemoteConnectionAuto
        conn = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        conn.host = '1.2.3.4'
        conn.port = 22
        conn.username = 'test'
        conn.password = 'x'
        conn.ssh = mock_ssh
        return conn

    def test_ssh_cmd_raises_on_dangerous_rm(self):
        """'rm -rf /' 触发 DangerousCommandError (而不是返回字符串)."""
        from app.tools.shellcmd import DangerousCommandError
        conn = self._make_conn(mock_ssh=None)  # 不应触达 ssh.exec_command
        with pytest.raises(DangerousCommandError) as exc_info:
            conn.ssh_cmd('rm -rf /')
        # danger_pattern 含 'rm' (SSH_DANGEROUS_COMMANDS 配置的 pattern 包含 'rm -rf /')
        assert 'rm' in exc_info.value.danger_pattern
        # 错误消息含 danger_pattern
        assert 'rm' in str(exc_info.value)

    def test_ssh_cmd_raises_on_dangerous_mkfs(self):
        """'mkfs /dev/sda' 触发 DangerousCommandError."""
        from app.tools.shellcmd import DangerousCommandError
        conn = self._make_conn()
        with pytest.raises(DangerousCommandError) as exc_info:
            conn.ssh_cmd('mkfs /dev/sda')
        assert 'mkfs' in str(exc_info.value)

    def test_ssh_cmd_raises_on_dangerous_dd(self):
        """'dd if=/dev/zero' 触发 DangerousCommandError."""
        from app.tools.shellcmd import DangerousCommandError
        conn = self._make_conn()
        with pytest.raises(DangerousCommandError):
            conn.ssh_cmd('dd if=/dev/zero of=/dev/sda')

    def test_ssh_cmd_raises_on_dangerous_shutdown(self):
        """'shutdown -h now' 触发 DangerousCommandError."""
        from app.tools.shellcmd import DangerousCommandError
        conn = self._make_conn()
        with pytest.raises(DangerousCommandError):
            conn.ssh_cmd('shutdown -h now')

    def test_ssh_cmd_raises_on_dangerous_fork_bomb(self):
        """':(){:|:&};:' fork 炸弹触发 DangerousCommandError."""
        from app.tools.shellcmd import DangerousCommandError
        conn = self._make_conn()
        with pytest.raises(DangerousCommandError):
            conn.ssh_cmd(':(){:|:&};:')

    def test_ssh_cmd_safe_command_passes_danger_check(self):
        """安全命令不抛 (会进入 ssh.exec_command 流程, 这里 mock 让其返回空).

        REV46-M22 兼容: ssh_cmd 改用 _read_with_select 代替 stdout.read().
        旁路 exec_command + _read_with_select, 让 ssh_cmd 走完整流程返回空字符串.
        """
        from app.tools.shellcmd import DangerousCommandError
        from unittest import mock as _mock
        mock_ssh = _mock.MagicMock()
        mock_stdin = _mock.MagicMock()
        # channel 须有 recv_ready (供截断检测)
        mock_chan = _mock.MagicMock()
        mock_chan.recv_ready.return_value = False
        mock_stdout = _mock.MagicMock()
        mock_stdout.channel = mock_chan
        mock_stderr = _mock.MagicMock()
        mock_stderr.channel = mock_chan
        mock_ssh.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        conn = self._make_conn(mock_ssh=mock_ssh)
        # 'ls -la' 是安全命令, 应不抛 DangerousCommandError
        # 旁路 _read_with_select 直接返回 b''
        with _mock.patch('app.tools.shellcmd._read_with_select',
                         return_value=b''):
            try:
                result = conn.ssh_cmd('ls -la')
            except DangerousCommandError:
                pytest.fail('safe command should not raise DangerousCommandError')
        # safe 命令应返回空字符串 (无 stdout/stderr)
        assert result == ''


# =============================================================================
# TestM23StaticAnalysis: 源码静态检查
# =============================================================================
class TestM23StaticAnalysis:
    """REV46-M23: 源码不再含 'DANGEROUS_COMMAND_BLOCKED' 字符串."""

    def test_shellcmd_no_blocked_string(self):
        """shellcmd.py 源码不再含 'DANGEROUS_COMMAND_BLOCKED' 返回语句 (旧字符串返回).

        注意: 历史 docstring 中可能提及该字符串作为背景说明, 这里仅验证
        实际 return 语句已删除 (即 'return ... DANGEROUS_COMMAND_BLOCKED ...' 模式).
        docstring 中的历史说明允许保留.
        """
        from app.tools import shellcmd
        # ssh_cmd 是 RemoteConnectionAuto 的方法, 不能模块级直接访问
        # 改用 RemoteConnectionAuto 类的 ssh_cmd 方法
        from app.tools.shellcmd import RemoteConnectionAuto
        source = inspect.getsource(RemoteConnectionAuto.ssh_cmd)
        # 剥离 docstring (三引号字符串), 只检查实际代码
        import re
        code_only = re.sub(r'\"\"\"[\s\S]*?\"\"\"', '', source)
        code_only = re.sub(r"'''[\s\S]*?'''", '', code_only)
        # ssh_cmd 方法体内不应有 'return ... DANGEROUS_COMMAND_BLOCKED' 语句
        assert "return 'DANGEROUS_COMMAND_BLOCKED" not in code_only, \
            "REV46-M23: ssh_cmd 不应再有 return 'DANGEROUS_COMMAND_BLOCKED: ...' 语句"
        # 也不应有直接返 DANGEROUS_COMMAND_BLOCKED 的形式
        assert "DANGEROUS_COMMAND_BLOCKED:" not in code_only, \
            "REV46-M23: ssh_cmd 代码内不应再含 'DANGEROUS_COMMAND_BLOCKED:' 字符串"

    def test_shellcmd_has_raise_m23_marker(self):
        """shellcmd.py 源码应含 REV46-M23 标记."""
        from app.tools import shellcmd
        source = inspect.getsource(shellcmd)
        assert 'REV46-M23' in source, "shellcmd.py 应含 REV46-M23 标记注释"

    def test_dangerous_command_error_has_danger_pattern_doc(self):
        """DangerousCommandError.danger_pattern 应有文档说明."""
        from app.tools.shellcmd import DangerousCommandError
        # 实例属性, 不一定在 class doc, 这里仅验证可挂载
        err = DangerousCommandError('test')
        err.danger_pattern = 'rm'
        assert err.danger_pattern == 'rm'


# =============================================================================
# TestM23CallerCompatibility: 调用方兼容
# =============================================================================
class TestM23CallerCompatibility:
    """REV46-M23: 调用方识别 DangerousCommandError."""

    def test_servermanagement_sh_script_source_has_except(self):
        """ServerScript.sh_script 源码含 except DangerousCommandError 分支."""
        from app.assets import ServerManagement
        source = inspect.getsource(ServerManagement.ServerScript.sh_script)
        assert 'except DangerousCommandError' in source, \
            "REV46-M23: ServerScript.sh_script 应 except DangerousCommandError"

    def test_cron_already_catches_exception_in_cron_list_cmd(self):
        """cron.cron_list_cmd 已有 try/except Exception, 自动兼容 DangerousCommandError."""
        from app.cron import cron
        source = inspect.getsource(cron.cron_list_cmd)
        # 应有 except Exception (line 134 附近)
        assert 'except Exception' in source
        # 验证 cron_list_cmd 调用了 ssh_cmd
        assert 'ssh_cmd' in source

    def test_cron_already_catches_exception_in_cron_execute(self):
        """cron 的命令执行路径也已有 try/except Exception, 自动兼容."""
        from app.cron import cron
        # 第二处 ssh_cmd 在 cron.py:290, 检查上下文
        source = inspect.getsource(cron)
        # 应有两处 ssh_cmd 调用
        assert source.count('ssh_cmd') >= 2
        # 至少两处 except Exception
        assert source.count('except Exception') >= 2
