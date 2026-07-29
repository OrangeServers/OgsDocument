"""REV46-H3: SMTP 暂时性失败 3 次重试 + 指数 backoff (1s, 2s, 4s).

_send_msg 加重试逻辑:
- 暂时性错误 (SMTPServerDisconnected / SMTPConnectError / SMTPHeloError /
  socket.timeout / ConnectionError / OSError) → 关闭脏连接, 重建, 重试
- 业务错误 (SMTPAuthenticationError / SMTPRecipientsRefused / SMTPDataError /
  SMTPSenderRefused) → 关闭脏连接, 直接抛, 不重试
- 最多 3 次重试 (即尝试 4 次: 第 1 次 + 重试 3 次)
- backoff 序列: (1, 2, 4) 秒

测试覆盖:
  TestH3RetryOnTransient: 暂时性错误自动重试
  TestH3NoRetryOnBusiness: 业务错误不重试
  TestH3MaxRetries: 超过最大重试次数后抛
  TestH3BackoffSequence: backoff 序列验证
  TestH3SuccessNoRetry: 一次成功不重试
  TestH3StaticAnalysis: 源码标记
"""
import inspect
import smtplib
import socket
from unittest import mock

import pytest


# =============================================================================
# TestH3RetryOnTransient: 暂时性错误重试
# =============================================================================
class TestH3RetryOnTransient:
    """REV46-H3: 暂时性 SMTP 错误自动重试."""

    def _make_sm(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        return sm

    def test_retry_on_server_disconnected(self):
        """SMTPServerDisconnected 触发重试."""
        from app.tools.sendmail import SendMail
        sm = self._make_sm()
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = [
            smtplib.SMTPServerDisconnected('first'),
            (250, b'OK'),  # 第二次成功
        ]
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            sm._send_msg('to@t.com', msg)
        # 第二次 sendmail 成功
        assert smtp_inst.sendmail.call_count == 2
        # backoff 1 秒
        mock_sleep.assert_called_with(1)

    def test_retry_on_socket_timeout(self):
        """socket.timeout 触发重试."""
        from app.tools.sendmail import SendMail
        sm = self._make_sm()
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = [
            socket.timeout('first'),
            socket.timeout('second'),
            (250, b'OK'),
        ]
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            sm._send_msg('to@t.com', msg)
        assert smtp_inst.sendmail.call_count == 3
        # backoff 1s, 2s
        assert mock_sleep.call_args_list == [mock.call(1), mock.call(2)]

    def test_retry_on_connect_error(self):
        """SMTPConnectError 触发重试."""
        from app.tools.sendmail import SendMail
        sm = self._make_sm()
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = [
            smtplib.SMTPConnectError(421, 'try later'),
            (250, b'OK'),
        ]
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep'):
            sm._send_msg('to@t.com', msg)
        assert smtp_inst.sendmail.call_count == 2


# =============================================================================
# TestH3NoRetryOnBusiness: 业务错误不重试
# =============================================================================
class TestH3NoRetryOnBusiness:
    """REV46-H3: 业务错误 (认证/收件人拒绝) 不重试."""

    def _make_sm(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        return sm

    def test_no_retry_on_auth_error(self):
        """SMTPAuthenticationError 不重试."""
        from app.tools.sendmail import SendMail
        sm = self._make_sm()
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = smtplib.SMTPAuthenticationError(
            535, b'auth fail'
        )
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            with pytest.raises(smtplib.SMTPAuthenticationError):
                sm._send_msg('to@t.com', msg)
        # 仅调用 1 次 (不重试)
        assert smtp_inst.sendmail.call_count == 1
        # 无 backoff
        mock_sleep.assert_not_called()

    def test_no_retry_on_recipient_refused(self):
        """SMTPRecipientsRefused 不重试."""
        from app.tools.sendmail import SendMail
        sm = self._make_sm()
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = smtplib.SMTPRecipientsRefused({
            'to@t.com': (550, b'no such user')
        })
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            with pytest.raises(smtplib.SMTPRecipientsRefused):
                sm._send_msg('to@t.com', msg)
        assert smtp_inst.sendmail.call_count == 1
        mock_sleep.assert_not_called()

    def test_no_retry_on_data_error(self):
        """SMTPDataError 不重试."""
        from app.tools.sendmail import SendMail
        sm = self._make_sm()
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = smtplib.SMTPDataError(554, b'data err')
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            with pytest.raises(smtplib.SMTPDataError):
                sm._send_msg('to@t.com', msg)
        assert smtp_inst.sendmail.call_count == 1
        mock_sleep.assert_not_called()


# =============================================================================
# TestH3MaxRetries: 超过最大重试次数后抛
# =============================================================================
class TestH3MaxRetries:
    """REV46-H3: 达到 max_retries 后抛最后一次的异常."""

    def test_max_retries_3_then_raise(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = smtplib.SMTPServerDisconnected('always')
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            with pytest.raises(smtplib.SMTPServerDisconnected):
                sm._send_msg('to@t.com', msg)
        # 总共 4 次尝试 (1 + 3 retries)
        assert smtp_inst.sendmail.call_count == 4
        # backoff 1s, 2s, 4s (3 次)
        assert mock_sleep.call_args_list == [
            mock.call(1), mock.call(2), mock.call(4)
        ]


# =============================================================================
# TestH3BackoffSequence: 指数 backoff
# =============================================================================
class TestH3BackoffSequence:
    """REV46-H3: backoff 序列 (1, 2, 4) 秒."""

    def test_backoff_is_exponential(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        # 全失败, 触发 3 次 backoff
        smtp_inst.sendmail.side_effect = smtplib.SMTPServerDisconnected('always')
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            with pytest.raises(smtplib.SMTPServerDisconnected):
                sm._send_msg('to@t.com', msg)
        # backoff 序列: 1, 2, 4
        backoff_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert backoff_calls == [1, 2, 4]


# =============================================================================
# TestH3SuccessNoRetry: 一次成功不重试
# =============================================================================
class TestH3SuccessNoRetry:
    """REV46-H3: 一次成功不触发 backoff."""

    def test_first_attempt_success(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.return_value = {}
        with mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep') as mock_sleep:
            sm._send_msg('to@t.com', msg)
        assert smtp_inst.sendmail.call_count == 1
        mock_sleep.assert_not_called()


# =============================================================================
# TestH3StaticAnalysis: 源码标记
# =============================================================================
class TestH3StaticAnalysis:
    """REV46-H3: 源码标记 + 重试/backoff 模式."""

    def test_sendmail_has_h3_marker(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'REV46-H3' in source

    def test_sendmail_has_retry_logic(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'max_retries' in source
        assert 'backoff' in source
        assert 'SMTPServerDisconnected' in source


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
