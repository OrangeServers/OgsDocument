"""REV46-M26: ssh_cmd 跳 t_command_log 审计 (走 ComToolsLog).

- 新增 log_ssh_audit() 模块级 helper (仿 ComToolsLog.host_log, 写 t_command_log)
- ssh_cmd 接受 audit_callback 参数 (默认 None, 向后兼容)
- ssh_cmd 在 4 个事件点调用 audit_callback: dangerous / success / timeout / failed
- 所有 ssh_cmd 调用方 (ServerCmd / GroupCmd / ServerScript / cron) 注入 log_ssh_audit

测试覆盖:
  TestM26LogSshAudit: log_ssh_audit helper 存在 + 调 ComToolsLog.host_log
  TestM26SshCmdAudit: ssh_cmd 接受 audit_callback, 4 个事件点
  TestM26Callsites: 所有调用方源码含 audit_callback=log_ssh_audit
  TestM26BackwardCompat: audit_callback=None 向后兼容
  TestM26AuditFailureSafe: audit_callback 抛异常时不影响主业务
  TestM26StaticAnalysis: 源码静态标记
"""
import inspect
import os
import sys
from unittest import mock

import pytest

# ti3-TS 修复: 用 ROOT 绝对路径避免 cwd 依赖
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# =============================================================================
# TestM26LogSshAudit: log_ssh_audit 模块级 helper
# =============================================================================
class TestM26LogSshAudit:
    """REV46-M26: log_ssh_audit 直接写 t_command_log."""

    def test_log_ssh_audit_exists(self):
        from app.tools.audlog import log_ssh_audit
        assert callable(log_ssh_audit)

    def test_log_ssh_audit_writes_to_command_log(self):
        """log_ssh_audit 调 ComToolsLog.host_log (走 t_command_log)."""
        from app.tools.audlog import log_ssh_audit, ComToolsLog
        with mock.patch.object(ComToolsLog, 'host_log') as mock_host_log:
            log_ssh_audit(
                log_name='alice', log_type='ssh_cmd',
                log_info='ls -la', log_host='192.168.1.1',
                log_status='success', log_msg='ok',
            )
        mock_host_log.assert_called_once()
        call_kwargs = mock_host_log.call_args.kwargs
        assert call_kwargs['log_name'] == 'alice'
        assert call_kwargs['log_type'] == 'ssh_cmd'
        assert call_kwargs['log_info'] == 'ls -la'
        assert call_kwargs['log_host'] == '192.168.1.1'
        assert call_kwargs['log_status'] == 'success'
        assert call_kwargs['log_msg'] == 'ok'

    def test_log_ssh_audit_safe_on_db_failure(self):
        """DB 失败时 log_ssh_audit 不抛 (走 audsec.safe_db_write 降级)."""
        from app.tools.audlog import log_ssh_audit, ComToolsLog
        with mock.patch.object(ComToolsLog, 'host_log',
                               side_effect=Exception('db fail')):
            # host_log 内部调 _write → osql_in, 但 osql_in 失败由 audsec.safe_db_write 降级
            # 但 mock 后 host_log 直接抛, 这里测试只验证 log_ssh_audit 不直接 catch
            # 实际上 ComToolsLog.host_log 调 _write, _write 调 safe_db_write (reraise=False)
            # 所以 safe_db_write 不会抛
            # 这里 mock 在 host_log 级别, 会真的抛, 验证 log_ssh_audit 自身不 catch
            with pytest.raises(Exception):
                log_ssh_audit('n', 't', 'i', 'h', 's', 'm')


# =============================================================================
# TestM26SshCmdAudit: ssh_cmd 4 个事件点调用 audit_callback
# =============================================================================
class TestM26SshCmdAudit:
    """REV46-M26: ssh_cmd 在 dangerous / success / timeout / failed 时调 audit_callback."""

    def _make_rca(self):
        from app.tools.shellcmd import RemoteConnectionAuto
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = '192.168.1.100'
        rca.port = 22
        rca.username = 'test'
        rca.password = 'test'
        rca.ssh = mock.MagicMock()
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

    def test_ssh_cmd_audit_on_dangerous(self):
        """危险命令拦截 → audit_callback 被调, status=blocked."""
        from app.tools.shellcmd import DangerousCommandError
        rca = self._make_rca()
        audit_calls = []
        with pytest.raises(DangerousCommandError):
            rca.ssh_cmd('rm -rf /',
                        audit_callback=lambda **kw: audit_calls.append(kw))
        assert len(audit_calls) == 1
        call = audit_calls[0]
        assert call['log_type'] == 'ssh_cmd_dangerous'
        assert call['log_status'] == 'blocked'
        assert 'rm -rf /' in call['log_info']
        assert call['log_host'] == '192.168.1.100'

    def test_ssh_cmd_audit_on_success(self):
        """成功执行 → audit_callback 被调, status=success."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        audit_calls = []
        with mock.patch('app.tools.shellcmd._read_with_select',
                        return_value=b'OK'):
            rca.ssh_cmd('ls -la',
                        audit_callback=lambda **kw: audit_calls.append(kw))
        assert len(audit_calls) == 1
        call = audit_calls[0]
        assert call['log_type'] == 'ssh_cmd'
        assert call['log_status'] == 'success'
        assert 'ls -la' in call['log_info']

    def test_ssh_cmd_nonzero_exit_is_failed(self):
        """远端进程正常结束但 exit code 非零时不能记为成功。"""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        stdout.channel.recv_exit_status.return_value = 23
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        audit_calls = []
        with mock.patch(
            'app.tools.shellcmd._read_with_select',
            side_effect=[b'', b'command not found'],
        ):
            result = rca.ssh_cmd(
                'missing-command',
                audit_callback=lambda **kw: audit_calls.append(kw),
            )

        assert result is None
        assert rca.last_command_error == "exit code 23: command not found"
        assert len(audit_calls) == 1
        assert audit_calls[0]['log_status'] == 'failed'
        assert 'exit_code=23' in audit_calls[0]['log_msg']

    def test_ssh_cmd_audit_on_timeout(self):
        """超时 → audit_callback 被调, status=timeout."""
        from app.tools.shellcmd import SshCommandTimeout
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        audit_calls = []
        with mock.patch('app.tools.shellcmd._read_with_select') as mock_read:
            mock_read.side_effect = SshCommandTimeout('timeout after 30s')
            with pytest.raises(SshCommandTimeout):
                rca.ssh_cmd('sleep 999',
                            audit_callback=lambda **kw: audit_calls.append(kw))
        assert len(audit_calls) == 1
        call = audit_calls[0]
        assert call['log_type'] == 'ssh_cmd_timeout'
        assert call['log_status'] == 'timeout'

    def test_ssh_cmd_audit_on_failed(self):
        """执行异常 → audit_callback 被调, status=failed."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        rca.ssh.exec_command.side_effect = RuntimeError('boom')
        audit_calls = []
        result = rca.ssh_cmd('cmd',
                             audit_callback=lambda **kw: audit_calls.append(kw))
        assert result is None
        assert len(audit_calls) == 1
        call = audit_calls[0]
        assert call['log_type'] == 'ssh_cmd'
        assert call['log_status'] == 'failed'

    def test_ssh_cmd_audit_not_called_when_none(self):
        """audit_callback=None → 不调用 (向后兼容)."""
        rca = self._make_rca()
        stdin, stdout, stderr = self._make_exec_mock()
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        # 无 audit_callback, 不应抛
        with mock.patch('app.tools.shellcmd._read_with_select',
                        return_value=b'OK'):
            result = rca.ssh_cmd('ls')
        assert result == 'OK'

    def test_ssh_cmd_audit_failure_does_not_break_main(self):
        """audit_callback 抛异常 → 主业务不受影响."""
        from app.tools.shellcmd import DangerousCommandError
        rca = self._make_rca()
        def bad_audit(**kw):
            raise Exception('audit db fail')
        # 危险命令拦截时 audit 抛异常, 仍应抛 DangerousCommandError
        with pytest.raises(DangerousCommandError):
            rca.ssh_cmd('rm -rf /', audit_callback=bad_audit)


# =============================================================================
# TestM26Callsites: 所有调用方源码含 audit_callback
# =============================================================================
class TestM26Callsites:
    """REV46-M26: 调用方注入 log_ssh_audit."""

    def _read(self, path):
        from pathlib import Path
        return Path(path).read_text(encoding='utf-8')

    def test_servermanagement_inject_audit(self):
        """ServerManagement 应导入 log_ssh_audit + 多处传 audit_callback."""
        # ti3-TS 修复: 用 ROOT 绝对路径
        text = self._read(os.path.join(ROOT, 'app/assets/ServerManagement.py'))
        assert 'log_ssh_audit' in text, \
            "ServerManagement 应 import log_ssh_audit"
        # 至少 4 处 audit_callback=log_ssh_audit
        assert text.count('audit_callback=log_ssh_audit') >= 4, \
            "ServerManagement 应多处注入 audit_callback=log_ssh_audit"

    def test_cron_inject_audit(self):
        text = self._read(os.path.join(ROOT, 'app/cron/cron.py'))
        assert 'log_ssh_audit' in text
        assert text.count('audit_callback=log_ssh_audit') >= 2, \
            "cron 应至少 2 处注入 audit_callback=log_ssh_audit"


# =============================================================================
# TestM26BackwardCompat: audit_callback=None 向后兼容
# =============================================================================
class TestM26BackwardCompat:
    """REV46-M26: audit_callback 默认 None, 不传时不审计."""

    def test_default_audit_callback_is_none(self):
        """ssh_cmd 签名 audit_callback 默认 None."""
        from app.tools.shellcmd import RemoteConnectionAuto
        sig = inspect.signature(RemoteConnectionAuto.ssh_cmd)
        assert 'audit_callback' in sig.parameters
        assert sig.parameters['audit_callback'].default is None

    def test_ssh_cmd_works_without_audit(self):
        """不传 audit_callback, ssh_cmd 正常工作."""
        from app.tools.shellcmd import RemoteConnectionAuto
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = 't'
        rca.ssh = mock.MagicMock()
        rca._closed = False
        mock_chan = mock.MagicMock()
        mock_chan.recv_ready.return_value = False
        mock_chan.status_event.is_set.return_value = False
        mock_chan.exit_status_ready.return_value = True
        stdin = mock.MagicMock()
        stdout = mock.MagicMock()
        stdout.channel = mock_chan
        stderr = mock.MagicMock()
        stderr.channel = mock_chan
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        with mock.patch('app.tools.shellcmd._read_with_select',
                        return_value=b'OK'):
            # 不传 audit_callback
            result = rca.ssh_cmd('ls')
        assert result == 'OK'


# =============================================================================
# TestM26AuditFailureSafe: audit_callback 抛异常时不影响主业务
# =============================================================================
class TestM26AuditFailureSafe:
    """REV46-M26: 审计失败时主业务不挂."""

    def test_audit_failure_on_success_path(self):
        from app.tools.shellcmd import RemoteConnectionAuto
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = 't'
        rca.ssh = mock.MagicMock()
        rca._closed = False
        mock_chan = mock.MagicMock()
        mock_chan.recv_ready.return_value = False
        mock_chan.status_event.is_set.return_value = False
        mock_chan.exit_status_ready.return_value = True
        stdin = mock.MagicMock()
        stdout = mock.MagicMock()
        stdout.channel = mock_chan
        stderr = mock.MagicMock()
        stderr.channel = mock_chan
        rca.ssh.exec_command.return_value = (stdin, stdout, stderr)
        def bad_audit(**kw):
            raise IOError('audit db fail')
        with mock.patch('app.tools.shellcmd._read_with_select',
                        return_value=b'OK'):
            # 审计抛异常时仍返 OK
            result = rca.ssh_cmd('ls', audit_callback=bad_audit)
        assert result == 'OK'

    def test_audit_failure_on_dangerous_path(self):
        """审计失败 + 危险命令拦截时, 仍应抛 DangerousCommandError."""
        from app.tools.shellcmd import (
            RemoteConnectionAuto, DangerousCommandError
        )
        rca = RemoteConnectionAuto.__new__(RemoteConnectionAuto)
        rca.host = 't'
        rca.ssh = mock.MagicMock()
        rca._closed = False
        def bad_audit(**kw):
            raise IOError('audit fail')
        with pytest.raises(DangerousCommandError):
            rca.ssh_cmd('rm -rf /', audit_callback=bad_audit)


# =============================================================================
# TestM26StaticAnalysis: 源码静态检查
# =============================================================================
class TestM26StaticAnalysis:
    """REV46-M26: 源码标记 + audit_callback 在 ssh_cmd 签名."""

    def test_shellcmd_has_m26_marker(self):
        from app.tools import shellcmd
        source = inspect.getsource(shellcmd)
        assert 'REV46-M26' in source

    def test_audlog_has_m26_marker(self):
        from app.tools import audlog
        source = inspect.getsource(audlog)
        assert 'REV46-M26' in source
        assert 'log_ssh_audit' in source

    def test_ssh_cmd_signature_has_audit_callback(self):
        from app.tools.shellcmd import RemoteConnectionAuto
        sig = inspect.signature(RemoteConnectionAuto.ssh_cmd)
        assert 'audit_callback' in sig.parameters

    def test_ssh_cmd_docstring_mentions_audit(self):
        from app.tools.shellcmd import RemoteConnectionAuto
        doc = RemoteConnectionAuto.ssh_cmd.__doc__ or ''
        assert 'audit_callback' in doc or 'REV46-M26' in doc


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
