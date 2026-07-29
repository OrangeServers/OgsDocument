"""REV46-M5: sendmail 发送成功/失败/重试日志.

_send_msg 加日志:
- 成功: INFO 'sendmail success: to=... subject=... elapsed=...ms attempt=.../...'
- 重试: WARNING 'sendmail retry: to=... attempt=.../... err=...'
- 业务失败: ERROR 'sendmail failed (business): ...'
- 最大重试失败: ERROR 'sendmail failed (max retries): ...'
- 未知错误: ERROR 'sendmail failed (unknown): ...'

测试覆盖:
  TestM5LoggerExists: _sendmail_logger 存在
  TestM5SuccessLog: 成功路径 INFO 日志
  TestM5RetryLog: 重试 WARNING 日志
  TestM5BusinessFailLog: 业务失败 ERROR 日志
  TestM5MaxRetriesFailLog: 最大重试失败 ERROR 日志
  TestM5StaticAnalysis: 源码标记
"""
import inspect
import smtplib
import socket
from unittest import mock

import pytest


# =============================================================================
# TestM5LoggerExists: _sendmail_logger 存在
# =============================================================================
class TestM5LoggerExists:
    """REV46-M5: sendmail 模块级 logger 存在."""

    def test_sendmail_logger_exists(self):
        from app.tools import sendmail
        assert hasattr(sendmail, '_sendmail_logger')
        assert sendmail._sendmail_logger.name == 'sendmail'

    def test_sendmail_logger_is_logger_instance(self):
        from app.tools import sendmail
        import logging
        assert isinstance(sendmail._sendmail_logger, logging.Logger)


# =============================================================================
# TestM5SuccessLog: 成功路径 INFO 日志
# =============================================================================
class TestM5SuccessLog:
    """REV46-M5: 成功时写 INFO 日志."""

    def test_success_logs_info(self, caplog):
        from app.tools.sendmail import SendMail
        import logging
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        msg.get.return_value = 'Test Subject'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.return_value = {}
        with caplog.at_level(logging.INFO, logger='sendmail'), \
             mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep'):
            sm._send_msg('to@t.com', msg)
        # 验证: 有 INFO 日志
        info_logs = [r for r in caplog.records
                     if r.name == 'sendmail' and r.levelno == logging.INFO]
        assert len(info_logs) >= 1
        log_text = info_logs[0].getMessage()
        assert 'success' in log_text.lower()
        assert 'to@t.com' in log_text
        assert 'elapsed=' in log_text

    def test_success_log_accepts_real_mime_header(self, caplog):
        """日志记录不能把已成功发送的 Header 对象误判为发送失败."""
        from email.header import Header
        from email.mime.text import MIMEText
        import logging
        from app.tools.sendmail import SendMail

        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.smtp = None
        msg = MIMEText('body', 'plain', 'utf-8')
        msg['Subject'] = Header('OrangeServer SMTP test')
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.return_value = {}

        with caplog.at_level(logging.INFO, logger='sendmail'), \
             mock.patch.object(
                 SendMail, '_get_or_create_smtp', return_value=smtp_inst
             ):
            sm._send_msg('to@t.com', msg)

        smtp_inst.sendmail.assert_called_once()
        assert any(
            'OrangeServer SMTP test' in record.getMessage()
            for record in caplog.records
            if record.name == 'sendmail'
        )


# =============================================================================
# TestM5RetryLog: 重试 WARNING 日志
# =============================================================================
class TestM5RetryLog:
    """REV46-M5: 重试时写 WARNING 日志."""

    def test_retry_logs_warning(self, caplog):
        from app.tools.sendmail import SendMail
        import logging
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = [
            smtplib.SMTPServerDisconnected('first'),
            (250, b'OK'),
        ]
        with caplog.at_level(logging.WARNING, logger='sendmail'), \
             mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep'):
            sm._send_msg('to@t.com', msg)
        # 验证: 有 WARNING 日志
        warn_logs = [r for r in caplog.records
                     if r.name == 'sendmail' and r.levelno == logging.WARNING]
        assert len(warn_logs) >= 1
        log_text = warn_logs[0].getMessage()
        assert 'retry' in log_text.lower()
        assert 'attempt=' in log_text


# =============================================================================
# TestM5BusinessFailLog: 业务失败 ERROR 日志
# =============================================================================
class TestM5BusinessFailLog:
    """REV46-M5: 业务错误 (认证/收件人) 失败时写 ERROR 日志."""

    def test_auth_fail_logs_error(self, caplog):
        from app.tools.sendmail import SendMail
        import logging
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = smtplib.SMTPAuthenticationError(
            535, b'auth fail'
        )
        with caplog.at_level(logging.ERROR, logger='sendmail'), \
             mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep'):
            with pytest.raises(smtplib.SMTPAuthenticationError):
                sm._send_msg('to@t.com', msg)
        err_logs = [r for r in caplog.records
                    if r.name == 'sendmail' and r.levelno == logging.ERROR]
        assert len(err_logs) >= 1
        log_text = err_logs[0].getMessage()
        assert 'failed' in log_text.lower()
        assert 'business' in log_text.lower()

    def test_recipient_refused_logs_error(self, caplog):
        from app.tools.sendmail import SendMail
        import logging
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = smtplib.SMTPRecipientsRefused({
            'to@t.com': (550, b'no user')
        })
        with caplog.at_level(logging.ERROR, logger='sendmail'), \
             mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep'):
            with pytest.raises(smtplib.SMTPRecipientsRefused):
                sm._send_msg('to@t.com', msg)
        err_logs = [r for r in caplog.records
                    if r.name == 'sendmail' and r.levelno == logging.ERROR]
        assert len(err_logs) >= 1


# =============================================================================
# TestM5MaxRetriesFailLog: 最大重试失败 ERROR 日志
# =============================================================================
class TestM5MaxRetriesFailLog:
    """REV46-M5: 最大重试失败时写 ERROR 日志."""

    def test_max_retries_fail_logs_error(self, caplog):
        from app.tools.sendmail import SendMail
        import logging
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        sm.smtp = None
        msg = mock.MagicMock()
        msg.as_string.return_value = 'fake-msg'
        smtp_inst = mock.MagicMock()
        smtp_inst.sendmail.side_effect = smtplib.SMTPServerDisconnected('always')
        with caplog.at_level(logging.ERROR, logger='sendmail'), \
             mock.patch.object(SendMail, '_get_or_create_smtp',
                               return_value=smtp_inst), \
             mock.patch('app.tools.sendmail.time.sleep'):
            with pytest.raises(smtplib.SMTPServerDisconnected):
                sm._send_msg('to@t.com', msg)
        err_logs = [r for r in caplog.records
                    if r.name == 'sendmail' and r.levelno == logging.ERROR]
        assert len(err_logs) >= 1
        log_text = err_logs[0].getMessage()
        assert 'max retries' in log_text.lower()


# =============================================================================
# TestM5StaticAnalysis: 源码标记
# =============================================================================
class TestM5StaticAnalysis:
    """REV46-M5: 源码标记."""

    def test_sendmail_has_m5_marker(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'REV46-M5' in source

    def test_sendmail_has_logger(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert '_sendmail_logger' in source
        assert 'logging.getLogger' in source

    def test_sendmail_logs_three_levels(self):
        """日志应包含 INFO/WARNING/ERROR 三个级别."""
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'INFO' in source or '_sendmail_logger.info' in source
        assert 'WARNING' in source or '_sendmail_logger.warning' in source
        assert 'ERROR' in source or '_sendmail_logger.error' in source


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
