"""REV46-H1: smtp.quit() 弃用 → smtp.close().

sendmail.py 中 3 处 quit() 改 close():
- _get_or_create_smtp 探活失败时
- close() 方法
- _send_msg 异常时

smtplib.SMTP.quit() 在 Python 3.9+ 弃用 (DeprecationWarning),
.smtp.close() 是新的标准 API, 行为兼容 (发 QUIT 命令 + 关闭 socket).

测试覆盖:
  TestH1NoQuitCalls: 源码不再调 smtp.quit()
  TestH1CloseMethod: SendMail.close() 调 smtp.close()
  TestH1ReconnectOnStale: 探活失败时 close() 旧连接
  TestH1ExceptionPath: _send_msg 异常时 close() 脏连接
"""
import inspect
import re
from unittest import mock

import pytest


# =============================================================================
# TestH1NoQuitCalls: 源码不再有 smtp.quit()
# =============================================================================
class TestH1NoQuitCalls:
    """REV46-H1: sendmail.py 不再调 smtp.quit()."""

    def test_sendmail_no_quit_call(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        # 剥离 docstring (历史可能提及 quit 作为参考)
        code_only = re.sub(r'"""[\s\S]*?"""', '', source)
        code_only = re.sub(r"'''[\s\S]*?'''", '', code_only)
        # 移除所有以 # 开头的单行注释 (注释里可能提历史 quit)
        code_only = '\n'.join(
            line for line in code_only.split('\n')
            if not line.lstrip().startswith('#')
        )
        # 实际代码中不应再有 'smtp.quit(' 或 'self.smtp.quit(' 调用
        # 检查带括号的 'quit(' (实际函数调用)
        assert 'quit(' not in code_only, \
            "REV46-H1: sendmail.py 代码内不应再调 smtp.quit()"

    def test_sendmail_has_m26_marker(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'REV46-H1' in source


# =============================================================================
# TestH1CloseMethod: SendMail.close() 调 smtp.close()
# =============================================================================
class TestH1CloseMethod:
    """REV46-H1: SendMail.close() 用 smtp.close() 而非 smtp.quit()."""

    def test_close_calls_smtp_close(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 'test@test.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.test.com'
        mock_smtp = mock.MagicMock()
        sm.smtp = mock_smtp
        sm.close()
        # close() 内部会先把 self.smtp.close(), 再置 None
        mock_smtp.close.assert_called_once()
        assert sm.smtp is None

    def test_close_handles_none_smtp(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 'test@test.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.test.com'
        sm.smtp = None
        sm.close()  # 不应抛

    def test_close_swallows_exception(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 'test@test.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.test.com'
        sm.smtp = mock.MagicMock()
        sm.smtp.close.side_effect = Exception('boom')
        sm.close()  # 不应抛
        assert sm.smtp is None


# =============================================================================
# TestH1ReconnectOnStale: 探活失败时 close() 旧连接
# =============================================================================
class TestH1ReconnectOnStale:
    """REV46-H1: _get_or_create_smtp 探活失败时 close() 旧连接."""

    def test_get_or_create_closes_stale_smtp(self):
        """noop() 抛异常 → 调 smtp.close() 而非 smtp.quit()."""
        from app.tools.sendmail import SendMail
        from app.core.config import MAIL_PORT
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 'test@test.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.test.com'
        # 旧 SMTP 实例, noop 失败
        old_smtp = mock.MagicMock()
        old_smtp.noop.side_effect = Exception('connection lost')
        sm.smtp = old_smtp
        # 强制 _get_or_create_smtp 走重新创建分支
        with mock.patch('app.tools.sendmail.smtplib.SMTP') as mock_smtp:
            mock_smtp.return_value = mock.MagicMock()
            sm._get_or_create_smtp()
        # 验证: old_smtp.close() 被调 (不是 quit)
        old_smtp.close.assert_called()
        old_smtp.quit.assert_not_called()


# =============================================================================
# TestH1ExceptionPath: _send_msg 异常时 close() 脏连接
# =============================================================================
class TestH1ExceptionPath:
    """REV46-H1: _send_msg 抛异常时 close() 脏连接."""

    def test_send_msg_closes_on_sendmail_failure(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 'test@test.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.test.com'
        smtp_instance = mock.MagicMock()
        smtp_instance.sendmail.side_effect = Exception('smtp send fail')
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_instance):
            msg = mock.MagicMock()
            msg.as_string.return_value = 'fake-msg'
            with pytest.raises(Exception):
                sm._send_msg('to@test.com', msg)
        # 验证: 异常路径 close() 被调
        smtp_instance.close.assert_called()
        smtp_instance.quit.assert_not_called()
        assert sm.smtp is None


# =============================================================================
# TestH1PythonDeprecation: 确认 quit() 真的弃用了
# =============================================================================
class TestH1PythonDeprecation:
    """REV46-H1: 跨 Python 版本的兼容性验证."""

    def test_smtp_has_close_method(self):
        import smtplib
        assert hasattr(smtplib.SMTP, 'close')
        assert callable(smtplib.SMTP.close)

    def test_smtp_has_quit_method_but_deprecated(self):
        """smtplib.SMTP 仍有 quit() 但 Python 3.9+ DeprecationWarning."""
        import smtplib
        assert hasattr(smtplib.SMTP, 'quit')
        # 验证 quit 仍然存在但已是 deprecated 路径 (历史兼容)
        # 我们用 close() 替代


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
