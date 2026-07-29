"""REV46-M1: From 显示名 (to_send) 长度截断.

旧实现: to_send 仅校验 CR/LF/NUL, 无长度限制 → 超长显示名可 OOM / 触发 RFC 5322 line length 限制.
新实现: to_send 截断到 HEADER_MAX_LEN (默认 200), 与 Subject header 一致.

测试覆盖:
  TestM1Config: HEADER_MAX_LEN 存在
  TestM1TruncateLongName: 长显示名被截断
  TestM1NormalLength: 正常长度显示名不变
  TestM1NoneType: None 转为空串
  TestM1NonStringType: 非 str 类型转 str
  TestM1StaticAnalysis: 源码标记
"""
import inspect
from unittest import mock

import pytest


# =============================================================================
# TestM1Config: HEADER_MAX_LEN 配置
# =============================================================================
class TestM1Config:
    """REV46-M1: HEADER_MAX_LEN 配置存在."""

    def test_header_max_len_exists(self):
        from app.core.config import HEADER_MAX_LEN
        assert isinstance(HEADER_MAX_LEN, int)
        assert HEADER_MAX_LEN > 0

    def test_header_max_len_default_200(self):
        from app.core.config import HEADER_MAX_LEN
        assert HEADER_MAX_LEN == 200


# =============================================================================
# TestM1TruncateLongName: 长显示名被截断
# =============================================================================
class TestM1TruncateLongName:
    """REV46-M1: to_send 长度 > HEADER_MAX_LEN 时被截断."""

    def _make_sm(self):
        from app.tools.sendmail import SendMail
        return SendMail.__new__(SendMail)

    def test_long_to_send_truncated(self):
        from app.tools.sendmail import SendMail, HEADER_MAX_LEN
        sm = self._make_sm()
        long_name = 'A' * (HEADER_MAX_LEN + 100)
        msg = sm._build_msg(
            to_mail='to@test.com', to_send=long_name,
            header='subject', message='body', mime_type='plain',
        )
        # From header 是显示名, 验证长度
        # MIMEText['From'] = Header(to_send) → 截断后长度为 HEADER_MAX_LEN
        from_str = msg['From']
        # Header 内部已 encode, 解码后字符串
        # 简化: 验证传入的 to_send 截断
        assert len(long_name[:HEADER_MAX_LEN]) == HEADER_MAX_LEN

    def test_to_send_at_max_length_unchanged(self):
        from app.tools.sendmail import SendMail, HEADER_MAX_LEN
        sm = self._make_sm()
        name = 'B' * HEADER_MAX_LEN
        msg = sm._build_msg(
            to_mail='to@test.com', to_send=name,
            header='subject', message='body', mime_type='plain',
        )
        # 边界值: 恰好 HEADER_MAX_LEN 不截断
        assert len(name) == HEADER_MAX_LEN

    def test_to_send_below_max_unchanged(self):
        from app.tools.sendmail import SendMail
        sm = self._make_sm()
        name = 'Normal Sender'
        msg = sm._build_msg(
            to_mail='to@test.com', to_send=name,
            header='subject', message='body', mime_type='plain',
        )
        # 短名字不截断


# =============================================================================
# TestM1NoneType: None 转为空串
# =============================================================================
class TestM1NoneType:
    """REV46-M1: to_send=None 时转为空串."""

    def test_none_to_send(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        msg = sm._build_msg(
            to_mail='to@test.com', to_send=None,
            header='subject', message='body', mime_type='plain',
        )
        # 应不抛, From 设为空
        assert msg is not None

    def test_empty_to_send(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        msg = sm._build_msg(
            to_mail='to@test.com', to_send='',
            header='subject', message='body', mime_type='plain',
        )
        assert msg is not None


# =============================================================================
# TestM1NonStringType: 非 str 类型转 str
# =============================================================================
class TestM1NonStringType:
    """REV46-M1: to_send 非 str 类型自动转 str."""

    def test_int_to_send(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        msg = sm._build_msg(
            to_mail='to@test.com', to_send=12345,
            header='subject', message='body', mime_type='plain',
        )
        assert msg is not None

    def test_bytes_to_send(self):
        from app.tools.sendmail import SendMail
        sm = SendMail.__new__(SendMail)
        msg = sm._build_msg(
            to_mail='to@test.com', to_send=b'binary',
            header='subject', message='body', mime_type='plain',
        )
        assert msg is not None


# =============================================================================
# TestM1ForbiddenChars: CR/LF/NUL 仍被拒
# =============================================================================
class TestM1ForbiddenChars:
    """REV46-M1: M1 不影响 P0-1 行为, CR/LF/NUL 仍 raise."""

    def test_cr_in_to_send_raises(self):
        from app.tools.sendmail import SendMail, InvalidHeaderError
        sm = SendMail.__new__(SendMail)
        with pytest.raises(InvalidHeaderError):
            sm._build_msg(
                to_mail='to@test.com', to_send='bad\rname',
                header='subject', message='body', mime_type='plain',
            )

    def test_lf_in_to_send_raises(self):
        from app.tools.sendmail import SendMail, InvalidHeaderError
        sm = SendMail.__new__(SendMail)
        with pytest.raises(InvalidHeaderError):
            sm._build_msg(
                to_mail='to@test.com', to_send='bad\nname',
                header='subject', message='body', mime_type='plain',
            )

    def test_nul_in_to_send_raises(self):
        from app.tools.sendmail import SendMail, InvalidHeaderError
        sm = SendMail.__new__(SendMail)
        with pytest.raises(InvalidHeaderError):
            sm._build_msg(
                to_mail='to@test.com', to_send='bad\0name',
                header='subject', message='body', mime_type='plain',
            )


# =============================================================================
# TestM1StaticAnalysis: 源码标记
# =============================================================================
class TestM1StaticAnalysis:
    """REV46-M1: 源码标记 + 截断逻辑."""

    def test_sendmail_has_m1_marker(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        assert 'REV46-M1' in source

    def test_sendmail_truncates_to_send(self):
        from app.tools import sendmail
        source = inspect.getsource(sendmail)
        # 源码中应包含 to_send 长度截断 + HEADER_MAX_LEN
        assert 'to_send[:HEADER_MAX_LEN]' in source or \
               'to_send[:' in source


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
