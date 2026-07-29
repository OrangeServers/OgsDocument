"""REV46-H2: noop() 无 timeout → socket.settimeout.

noop() 探活前显式设 socket.settimeout(SMTP_OP_TIMEOUT), 防止 SMTP 服务端
不响应时 noop() 永久阻塞, 占用 worker.

测试覆盖:
  TestH2Config: SMTP_OP_TIMEOUT 配置存在
  TestH2NoopTimeout: noop() 前设 socket timeout
  TestH2ReconnectOnStale: 探活失败时仍能重建
  TestH2StaticAnalysis: 源码标记
"""
import inspect
from unittest import mock

import pytest


# =============================================================================
# TestH2Config: SMTP_OP_TIMEOUT 配置
# =============================================================================
class TestH2Config:
    """REV46-H2: SMTP_OP_TIMEOUT 存在."""

    def test_smtp_op_timeout_exists(self):
        from app.core.config import SMTP_OP_TIMEOUT
        assert isinstance(SMTP_OP_TIMEOUT, int)
        assert SMTP_OP_TIMEOUT > 0

    def test_smtp_op_timeout_default_30(self):
        from app.core.config import SMTP_OP_TIMEOUT
        assert SMTP_OP_TIMEOUT == 30


# =============================================================================
# TestH2NoopTimeout: noop() 前设 socket timeout
# =============================================================================
class TestH2NoopTimeout:
    """REV46-H2: noop() 探活前显式设 socket.settimeout."""

    def test_noop_sets_socket_timeout(self):
        """复用 SMTP 时, noop 前应调 sock.settimeout(SMTP_OP_TIMEOUT)."""
        from app.tools.sendmail import SendMail, SMTP_OP_TIMEOUT
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        # mock 一个已有 smtp
        old_smtp = mock.MagicMock()
        old_smtp.sock = mock.MagicMock()  # 模拟 socket
        old_smtp.noop.return_value = (250, b'OK')  # 探活成功
        sm.smtp = old_smtp
        # 调用 _get_or_create_smtp 应复用 old_smtp
        result = sm._get_or_create_smtp()
        # 验证: sock.settimeout 被调
        old_smtp.sock.settimeout.assert_called_with(SMTP_OP_TIMEOUT)
        old_smtp.noop.assert_called_once()
        assert result is old_smtp

    def test_noop_no_sock_attribute(self):
        """smtp 没有 sock 属性时 (理论上罕见), 不抛异常."""
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        # mock 一个没有 sock 的 smtp (极少见)
        old_smtp = mock.MagicMock(spec=['noop'])  # 严格 spec, 无 sock
        old_smtp.noop.return_value = (250, b'OK')
        sm.smtp = old_smtp
        # 不应抛 AttributeError
        result = sm._get_or_create_smtp()
        assert result is old_smtp

    def test_noop_sock_is_none(self):
        """smtp.sock = None 时 (未连接), 不抛异常."""
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        old_smtp = mock.MagicMock()
        old_smtp.sock = None
        old_smtp.noop.return_value = (250, b'OK')
        sm.smtp = old_smtp
        # 不应抛
        result = sm._get_or_create_smtp()
        assert result is old_smtp


# =============================================================================
# TestH2ReconnectOnStale: 探活失败时仍能重建
# =============================================================================
class TestH2ReconnectOnStale:
    """REV46-H2: 探活失败时仍走 close 重建路径."""

    def test_noop_timeout_raises(self):
        """noop() 抛 socket.timeout → 旧连接 close, 重建."""
        from app.tools.sendmail import SendMail
        import socket
        sm = SendMail.__new__(SendMail)
        sm.form_mail = 't@t.com'
        sm.password = 'pwd'
        sm.smtp_server = 'smtp.t.com'
        old_smtp = mock.MagicMock()
        old_smtp.sock = mock.MagicMock()
        old_smtp.noop.side_effect = socket.timeout('read timeout')
        sm.smtp = old_smtp
        # 应能重建 (mock smtplib.SMTP)
        with mock.patch('app.tools.sendmail.smtplib.SMTP') as mock_smtp:
            mock_smtp.return_value = mock.MagicMock()
            result = sm._get_or_create_smtp()
        # 旧连接 close 被调
        old_smtp.close.assert_called()
        old_smtp.quit.assert_not_called()


# =============================================================================
# TestH2StaticAnalysis: 源码标记
# =============================================================================
class TestH2StaticAnalysis:
    """REV46-H2: sendmail.py 源码标记 + sock.settimeout 模式."""

    def test_sendmail_has_h2_marker(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'REV46-H2' in source

    def test_sendmail_calls_sock_settimeout(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'sock.settimeout' in source
        assert 'SMTP_OP_TIMEOUT' in source


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
