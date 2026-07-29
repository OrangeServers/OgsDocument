# -*- coding: utf-8 -*-
"""REV46-H5: sendmail._build_msg message body 允许 \r\n (RFC 5322 MIME 合法).

背景:
- REV46 H5: sendmail.py L147-150 对 message body 也校验 _HEADER_FORBIDDEN (CR/LF/NUL),
            拒绝合法的 MIME 多行内容 (RFC 5322 允许 body 含 CRLF).
- 业务影响: 多行通知消息 / 验证码 HTML 模板 / 表格内容会被拒发.
- 修复: 移除 message body 的 _HEADER_FORBIDDEN 校验, 只保留 header/to_send/to_mail 校验.
        message 保留: 字符串类型转换 + 长度截断 (防 OOM).

测试覆盖:
  1) message body 允许 \r\n (多行明文)
  2) message body 允许 \n (单 LF)
  3) message body 允许 HTML 多段
  4) message body 允许空字符串
  5) message body 允许 None (转为 '')
  6) header 含 \r\n 仍被拒绝 (防止 SMTP header 注入)
  7) to_send 含 \r\n 仍被拒绝 (防止 From 注入)
  8) message 超长仍截断
  9) MIME 多行内容被正确编码到 MIMEText
 10) 静态分析: 源码中 message body 的 _HEADER_FORBIDDEN 校验已被删除
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_SENDMAIL = os.path.join(_BACKEND, 'app', 'tools', 'sendmail.py')


def _make_sendmail():
    """构造 SendMail 实例 (跳过真实 SMTP 通信)."""
    from app.tools.sendmail import SendMail
    return SendMail('sender@example.com', 'pwd', 'smtp.example.com')


def _read_source():
    with open(_SENDMAIL, encoding='utf-8') as f:
        return f.read()


# ============================================================
# 1) message body 允许 \r\n (核心修复)
# ============================================================
class TestRev46H5MessageMultiline:
    """REV46-H5: message body 允许 \\r\\n."""

    def test_01_message_with_crlf_accepted(self):
        """message 含 \\r\\n 应被接受 (RFC 5322 MIME body 合法)."""
        m = _make_sendmail()
        msg = m._build_msg(
            'to@example.com', 'Sender', 'Subject',
            '第一行\r\n第二行\r\n第三行', 'plain',
        )
        assert msg is not None

    def test_02_message_with_lf_only_accepted(self):
        """message 含 \\n (单 LF) 应被接受."""
        m = _make_sendmail()
        msg = m._build_msg(
            'to@example.com', 'Sender', 'Subject',
            '第一行\n第二行', 'plain',
        )
        assert msg is not None

    def test_03_message_with_cr_only_accepted(self):
        """message 含 \\r (单 CR) 应被接受."""
        m = _make_sendmail()
        msg = m._build_msg(
            'to@example.com', 'Sender', 'Subject',
            '第一行\r第二行', 'plain',
        )
        assert msg is not None

    def test_04_message_html_multiparagraph_accepted(self):
        """HTML 多段 message 应被接受."""
        m = _make_sendmail()
        msg = m._build_msg(
            'to@example.com', 'Sender', 'Subject',
            '<p>第一段</p>\n<p>第二段</p>\n<p>第三段</p>', 'html',
        )
        assert msg is not None

    def test_05_message_with_table_html_accepted(self):
        """HTML 表格 message (含换行) 应被接受."""
        m = _make_sendmail()
        html = '<table>\n<tr><td>行1</td></tr>\n<tr><td>行2</td></tr>\n</table>'
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', html, 'html')
        assert msg is not None

    def test_06_message_empty_accepted(self):
        """空 message 应被接受."""
        m = _make_sendmail()
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', '', 'plain')
        assert msg is not None

    def test_07_message_none_accepted(self):
        """None message 应被转为空串接受."""
        m = _make_sendmail()
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', None, 'plain')
        assert msg is not None

    def test_08_message_non_string_accepted(self):
        """非字符串 message 应被 str() 转换接受."""
        m = _make_sendmail()
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', 12345, 'plain')
        assert msg is not None

    def test_09_message_with_crlf_in_content(self):
        """message 含 CRLF 在 MIMEText 编码中保留."""
        m = _make_sendmail()
        original = 'Hello\r\nWorld\r\n!'
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', original, 'plain')
        # MIMEText 会 base64 编码, 编码后内容应能反向解码
        encoded = msg.as_string()
        # 找 base64 body
        import email as em
        parsed = em.message_from_string(encoded)
        # base64 解码
        import base64
        if parsed.is_multipart():
            body_part = parsed.get_payload(0)
        else:
            body_part = parsed
        decoded = base64.b64decode(body_part.get_payload()).decode('utf-8')
        assert decoded == original, \
            'MIMEText 应保留 CRLF, 实际解码: %r' % decoded


# ============================================================
# 2) header / to_send 仍拒绝 \r\n (防御保留)
# ============================================================
class TestRev46H5HeaderStillSafe:
    """REV46-H5: header / to_send 含 \\r\\n 仍被拒绝 (防 SMTP header 注入)."""

    def test_01_header_with_crlf_rejected(self):
        """header 含 \\r\\n 应被拒绝 (Bcc 注入载体)."""
        from app.tools.sendmail import InvalidHeaderError
        m = _make_sendmail()
        with pytest.raises(InvalidHeaderError) as exc:
            m._build_msg('to@example.com', 'Sender',
                         'subject\r\nBcc: evil@example.com', 'msg', 'plain')
        assert 'header' in str(exc.value).lower() or 'forbidden' in str(exc.value).lower()

    def test_02_header_with_lf_only_rejected(self):
        """header 含 \\n 应被拒绝."""
        from app.tools.sendmail import InvalidHeaderError
        m = _make_sendmail()
        with pytest.raises(InvalidHeaderError):
            m._build_msg('to@example.com', 'Sender',
                         'subject\nBcc: evil@example.com', 'msg', 'plain')

    def test_03_header_with_nul_rejected(self):
        """header 含 \\0 应被拒绝."""
        from app.tools.sendmail import InvalidHeaderError
        m = _make_sendmail()
        with pytest.raises(InvalidHeaderError):
            m._build_msg('to@example.com', 'Sender',
                         'subject\0Bcc: evil@example.com', 'msg', 'plain')

    def test_04_to_send_with_crlf_rejected(self):
        """to_send 含 \\r\\n 应被拒绝 (From 注入载体)."""
        from app.tools.sendmail import InvalidHeaderError
        m = _make_sendmail()
        with pytest.raises(InvalidHeaderError) as exc:
            m._build_msg('to@example.com',
                         'Sender\r\nBcc: evil@example.com',
                         'subject', 'msg', 'plain')
        assert 'to_send' in str(exc.value).lower() or 'forbidden' in str(exc.value).lower()

    def test_05_to_mail_with_crlf_rejected(self):
        """to_mail 含 \\r\\n 应被拒绝 (To 注入载体, _validate_email 内)."""
        from app.tools.sendmail import InvalidEmailError
        m = _make_sendmail()
        with pytest.raises(InvalidEmailError):
            m._build_msg('to@example.com\r\nBcc: evil@example.com',
                         'Sender', 'subject', 'msg', 'plain')

    def test_06_to_mail_invalid_format_rejected(self):
        """to_mail 格式非法仍被拒绝 (保留业务校验)."""
        from app.tools.sendmail import InvalidEmailError
        m = _make_sendmail()
        with pytest.raises(InvalidEmailError):
            m._build_msg('not-an-email', 'Sender', 'subject', 'msg', 'plain')

    def test_07_header_too_long_truncated(self):
        """header 超长应被截断 (防御保留, _sanitize_header)."""
        from app.core.config import HEADER_MAX_LEN
        m = _make_sendmail()
        long_header = 'A' * (HEADER_MAX_LEN + 100)
        # header 中无 \r\n, 应被截断而非拒绝
        msg = m._build_msg('to@example.com', 'Sender', long_header, 'msg', 'plain')
        # Subject 截断 (Header 对象转 str 取长度)
        assert HEADER_MAX_LEN >= len(str(msg['Subject']))


# ============================================================
# 3) message 长度截断 (防御保留)
# ============================================================
class TestRev46H5MessageLength:
    """REV46-H5: message 超长仍截断 (防 OOM)."""

    def test_01_message_truncated(self):
        """message 超长应被截断到 MESSAGE_MAX_LEN."""
        from app.core.config import MESSAGE_MAX_LEN
        m = _make_sendmail()
        long_msg = 'x' * (MESSAGE_MAX_LEN + 500)
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', long_msg, 'plain')
        import email as em
        import base64
        encoded = msg.as_string()
        parsed = em.message_from_string(encoded)
        body_part = parsed.get_payload(0) if parsed.is_multipart() else parsed
        decoded = base64.b64decode(body_part.get_payload()).decode('utf-8')
        # 解码后长度应 <= MESSAGE_MAX_LEN
        assert len(decoded) <= MESSAGE_MAX_LEN, \
            'message 应被截断到 <= %d, 实际 %d' % (MESSAGE_MAX_LEN, len(decoded))

    def test_02_message_with_crlf_and_overlong(self):
        """message 含 \\r\\n 且超长: 仍接受并截断."""
        from app.core.config import MESSAGE_MAX_LEN
        m = _make_sendmail()
        # 构造超长多行 message
        line = 'A' * 100
        long_msg = '\r\n'.join([line] * (MESSAGE_MAX_LEN // 100 + 100))
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', long_msg, 'plain')
        # 应不抛异常
        assert msg is not None


# ============================================================
# 4) MIME 编码正确
# ============================================================
class TestRev46H5MIMEEncoding:
    """REV46-H5: 多行 message 应被正确 MIME 编码."""

    def test_01_plain_multiline_preserved(self):
        """plain text 多行 message 应原样保留 (经 base64 编码后解码不变)."""
        import base64
        import email as em
        m = _make_sendmail()
        original = 'Line 1\r\nLine 2\r\nLine 3'
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', original, 'plain')
        encoded = msg.as_string()
        parsed = em.message_from_string(encoded)
        body_part = parsed.get_payload(0) if parsed.is_multipart() else parsed
        decoded = base64.b64decode(body_part.get_payload()).decode('utf-8')
        assert decoded == original

    def test_02_html_paragraphs_preserved(self):
        """HTML 多段 message 应原样保留."""
        import base64
        import email as em
        m = _make_sendmail()
        original = '<p>First</p>\n<p>Second</p>\n<p>Third</p>'
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', original, 'html')
        encoded = msg.as_string()
        parsed = em.message_from_string(encoded)
        body_part = parsed.get_payload(0) if parsed.is_multipart() else parsed
        decoded = base64.b64decode(body_part.get_payload()).decode('utf-8')
        assert decoded == original

    def test_03_charset_utf8(self):
        """MIME charset 应是 utf-8."""
        m = _make_sendmail()
        msg = m._build_msg('to@example.com', 'Sender', 'Subject', '中文\r\n消息', 'plain')
        encoded = msg.as_string()
        assert 'utf-8' in encoded.lower(), 'MIME 应使用 utf-8 charset'

    def test_04_mime_type_set(self):
        """MIME type 应被正确设置 (plain 或 html)."""
        m = _make_sendmail()
        msg_plain = m._build_msg('to@example.com', 'Sender', 'Subject', 'msg', 'plain')
        assert 'text/plain' in msg_plain.as_string()

        msg_html = m._build_msg('to@example.com', 'Sender', 'Subject', '<p>msg</p>', 'html')
        assert 'text/html' in msg_html.as_string()


# ============================================================
# 5) 静态分析: 源码 message body 校验已被删除
# ============================================================
class TestRev46H5StaticAnalysis:
    """REV46-H5: 静态分析源码 - message body 的 CR/LF 校验已删除."""

    def test_01_build_msg_no_header_forbidden_on_message(self):
        """_build_msg 中不再对 message 应用 _HEADER_FORBIDDEN."""
        src = _read_source()
        # 找 _build_msg 函数体
        m = re.search(r'def\s+_build_msg\([\s\S]*?\n(?=\s{0,4}def\s|\Z)', src)
        assert m, '应找到 _build_msg 函数'
        body = m.group(0)

        # 函数体里不应有 "message" 与 "_HEADER_FORBIDDEN.search" 的组合
        # 找所有 _HEADER_FORBIDDEN.search 调用
        for match in re.finditer(r'_HEADER_FORBIDDEN\.search\(([^)]+)\)', body):
            arg = match.group(1)
            # arg 不应是 'message'
            assert 'message' not in arg, \
                '_build_msg 中 _HEADER_FORBIDDEN.search(message) 应已被删除, 实际调用: %s' % arg

    def test_02_build_msg_no_message_raises_invalid_header(self):
        """_build_msg 中不应再 raise 'message contains forbidden'."""
        src = _read_source()
        m = re.search(r'def\s+_build_msg\([\s\S]*?\n(?=\s{0,4}def\s|\Z)', src)
        assert m
        body = m.group(0)
        assert 'message contains forbidden' not in body, \
            '_build_msg 应不再 raise InvalidHeaderError(message contains forbidden)'

    def test_03_build_msg_still_validates_header_to_send(self):
        """_build_msg 仍校验 header / to_send 的 CR/LF/NUL (防御保留)."""
        src = _read_source()
        m = re.search(r'def\s+_build_msg\([\s\S]*?\n(?=\s{0,4}def\s|\Z)', src)
        body = m.group(0)

        # 仍应有 to_send 的 _HEADER_FORBIDDEN 检查
        assert re.search(r'_HEADER_FORBIDDEN\.search\(\s*to_send', body), \
            '_build_msg 应保留对 to_send 的 CR/LF/NUL 校验'

    def test_04_build_msg_still_sanitizes_header(self):
        """_build_msg 仍调用 _sanitize_header (Subject 校验)."""
        src = _read_source()
        m = re.search(r'def\s+_build_msg\([\s\S]*?\n(?=\s{0,4}def\s|\Z)', src)
        body = m.group(0)
        assert '_sanitize_header' in body, \
            '_build_msg 应保留 _sanitize_header 调用'

    def test_05_build_msg_still_validates_email(self):
        """_build_msg 仍校验 to_mail 邮箱格式."""
        src = _read_source()
        m = re.search(r'def\s+_build_msg\([\s\S]*?\n(?=\s{0,4}def\s|\Z)', src)
        body = m.group(0)
        assert '_validate_email' in body, \
            '_build_msg 应保留 _validate_email 调用'

    def test_06_rev46_h5_marker_in_source(self):
        """sendmail.py 应有 REV46-H5 标记注释."""
        src = _read_source()
        assert 'REV46-H5' in src, 'sendmail.py 应含 REV46-H5 标签注释'

    def test_07_header_forbidden_pattern_unchanged(self):
        """_HEADER_FORBIDDEN 正则定义不变 (仍含 CR/LF/NUL)."""
        src = _read_source()
        m = re.search(r'_HEADER_FORBIDDEN\s*=\s*re\.compile\(([^)]+)\)', src)
        assert m
        pattern = m.group(1)
        # 应仍检测 \r\n\0 (用于 header/to_send 校验)
        assert '\\r' in pattern
        assert '\\n' in pattern
        assert '\\0' in pattern


# ============================================================
# 6) 业务集成: MailApi 仍正常工作
# ============================================================
class TestRev46H5BusinessIntegration:
    """REV46-H5: 业务入口 MailApi 不依赖被删除的 message 校验."""

    def test_01_mail_api_still_uses_helpers(self):
        """MailApi.py 仍使用 _validate_email / _sanitize_header."""
        mail_api = os.path.join(_BACKEND, 'app', 'mail', 'MailApi.py')
        with open(mail_api, encoding='utf-8') as f:
            src = f.read()
        # MailApi 自己负责入口校验, 不依赖 _build_msg 的 message 校验
        assert '_validate_email' in src
        assert '_sanitize_header' in src

    def test_02_user_py_email_validation_unchanged(self):
        """user.py 仍使用 _validate_email (注册/重置密码)."""
        user_py = os.path.join(_BACKEND, 'app', 'users', 'user.py')
        with open(user_py, encoding='utf-8') as f:
            src = f.read()
        assert '_validate_email' in src, 'user.py 应仍调用 _validate_email'