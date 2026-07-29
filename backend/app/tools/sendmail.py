import re
import socket  # REV46-H2/H3: socket timeout + retry
import time  # REV46-H3: backoff sleep
import logging  # REV46-M5: 发送成功/失败日志
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from app.core.config import (
    MAIL_CONF,
    EMAIL_REGEX, EMAIL_MAX_LEN, HEADER_MAX_LEN, MESSAGE_MAX_LEN,
    SMTP_CONNECT_TIMEOUT, SMTP_OP_TIMEOUT,
    MAIL_PORT, MAIL_USE_TLS, MAIL_USE_SSL,
    EMAIL_TEMPLATES,  # REV46-M3
)


_EMAIL_RE = re.compile(EMAIL_REGEX)
# REVIEW-13 P0-1: SMTP header 注入检测 (RFC 5322 允许字段内换行, 攻击者可注入 Bcc:/To:/From:)
_HEADER_FORBIDDEN = re.compile(r'[\r\n\0]')


class InvalidEmailError(Exception):
    """邮箱格式非法或包含 header 注入载体。"""
    pass


class InvalidHeaderError(Exception):
    """邮件 header (Subject) 包含非法字符。"""
    pass


def _validate_email(addr):
    """P0-1: 邮箱格式校验。
    - 匹配 EMAIL_REGEX (RFC 5322 简化版)
    - 长度 <= EMAIL_MAX_LEN
    - 不允许 \r / \n / \0 (Header 注入载体)
    返回: 通过返回 True, 失败 raise InvalidEmailError。"""
    if not isinstance(addr, str):
        raise InvalidEmailError('email must be a string')
    if len(addr) == 0 or len(addr) > EMAIL_MAX_LEN:
        raise InvalidEmailError('email length out of range (1..%d)' % EMAIL_MAX_LEN)
    if _HEADER_FORBIDDEN.search(addr):
        raise InvalidEmailError('email contains forbidden chars (CR/LF/NUL)')
    if not _EMAIL_RE.fullmatch(addr):
        raise InvalidEmailError('email format invalid: %r' % addr[:40])
    return True


def _sanitize_header(s):
    """P0-1: header / Subject 校验 + 长度截断。
    - 不允许 \r / \n / \0 (Bcc 注入载体)
    - 长度 <= HEADER_MAX_LEN (超长则截断)
    - 任何 str 类型入参都按字符串处理 (utf-8 解码)
    返回: 通过返回 (safe_str,), 失败 raise InvalidHeaderError。"""
    if s is None:
        raise InvalidHeaderError('header is None')
    if isinstance(s, bytes):
        try:
            s = s.decode('utf-8', errors='replace')
        except Exception:
            s = ''
    if not isinstance(s, str):
        s = str(s)
    if _HEADER_FORBIDDEN.search(s):
        raise InvalidHeaderError('header contains forbidden chars (CR/LF/NUL)')
    # 截断超长 header (防内存耗尽 + RFC 5322 line length 限制)
    if len(s) > HEADER_MAX_LEN:
        s = s[:HEADER_MAX_LEN]
    return s


# 发送电子邮件
# REV46-M5: 发送成功/失败日志
#   - 成功: INFO 级别, 含 to_mail + subject (前 50 字符) + 耗时 ms
#   - 失败: ERROR 级别, 含 to_mail + subject + 异常类型 + 耗时 ms
#   - 重试: WARNING 级别, attempt n/max
_sendmail_logger = logging.getLogger('sendmail')


class SendMail:
    def __init__(
        self,
        form_mail,
        password,
        smtp_server,
        *,
        port=None,
        use_tls=None,
        use_ssl=None,
    ):
        """
        form_mail-->发送端配置的邮箱名,str类型
        password-->发送端配置的邮箱密码,str类型
        smtp_server-->使用的邮件服务器地址,str类型
        """
        # P0-1: 发送方 form_mail 也需要校验, 防止配置错误导致 SMTP 信封异常
        _validate_email(form_mail)
        self.form_mail = form_mail
        self.password = password
        self.smtp_server = smtp_server
        self.port = MAIL_PORT if port is None else int(port)
        self.use_tls = MAIL_USE_TLS if use_tls is None else bool(use_tls)
        self.use_ssl = MAIL_USE_SSL if use_ssl is None else bool(use_ssl)
        # P2-1: 延迟创建 SMTP 连接 (send 时才连接, 避免每个 SendMail 实例启动时建连)
        self.smtp = None

    def _get_or_create_smtp(self):
        """P2-1 + P1-1 + P1-2: 获取或创建 SMTP 连接。
        - 根据 MAIL_USE_SSL 选 SMTP_SSL 或 SMTP
        - 根据 MAIL_USE_TLS 在 SMTP 模式下调用 starttls() (推荐)
        - 全部带 timeout 防 hang 住
        - 复用已有 self.smtp (若未关闭)
        - REV46-H2: noop() 探活前显式设 socket.settimeout(SMTP_OP_TIMEOUT),
                    防止 SMTP 服务端不响应时 noop() 永久阻塞
        """
        # 已存在且未关闭则复用
        if self.smtp is not None:
            try:
                # REV46-H2: 探活前先设短 timeout 防 hang
                sock = getattr(self.smtp, 'sock', None)
                if sock is not None:
                    sock.settimeout(SMTP_OP_TIMEOUT)
                # 探活: 检查底层 socket 是否还活着
                self.smtp.noop()
                return self.smtp
            except Exception:
                try:
                    # REV46-H1: smtp.quit() Python 3.9+ 弃用 → smtp.close()
                    # SMTP.close() 行为兼容 (发 QUIT 命令, 关闭 socket)
                    self.smtp.close()
                except Exception:
                    pass
                self.smtp = None

        # P1-2: 根据配置选 SMTP / SMTP_SSL
        use_ssl = getattr(self, 'use_ssl', MAIL_USE_SSL)
        use_tls = getattr(self, 'use_tls', MAIL_USE_TLS)
        port = getattr(self, 'port', MAIL_PORT)
        if use_ssl:
            smtp = smtplib.SMTP_SSL(
                self.smtp_server,
                port,
                timeout=SMTP_CONNECT_TIMEOUT,
            )
        else:
            smtp = smtplib.SMTP(timeout=SMTP_CONNECT_TIMEOUT)
            smtp.connect(
                self.smtp_server,
                port,
                SMTP_CONNECT_TIMEOUT,
            )
            # P1-2: 587 端口默认 STARTTLS 升级
            if use_tls:
                smtp.starttls()
                # STARTTLS 后 hello 需重发
                smtp.ehlo()
        smtp.login(self.form_mail, self.password)
        self.smtp = smtp
        return smtp

    def verify(self):
        """Connect, authenticate and verify that the SMTP session responds."""
        smtp = self._get_or_create_smtp()
        code, _message = smtp.noop()
        if int(code) >= 400:
            raise smtplib.SMTPConnectError(code, "SMTP NOOP failed")

    def close(self):
        """P2-1: 显式关闭 SMTP 连接 (进程退出前调用, 释放 socket).

        REV46-H1: 改用 smtp.close() 替代 smtp.quit() (后者 Python 3.9+ 弃用).
        """
        if self.smtp is not None:
            try:
                self.smtp.close()
            except Exception:
                pass
            self.smtp = None

    def _build_msg(self, to_mail, to_send, header, message, mime_type):
        """REV28-L5: 拆分自 send() —— 校验 + 构造 MIME 文本.

        返回 MIMEText 对象 (as_string 会被 send 时调用).

        REV46-H5: message body 允许 \r\n (RFC 5322 MIME body 合法含换行),
                  只校验 header / to_mail / to_send 不含 CR/LF/NUL.
        """
        # mime_type 白名单 (防任意 MIME 覆盖)
        if mime_type not in ('plain', 'html'):
            mime_type = 'plain'
        # 入口校验 —— 任何一项失败直接拒绝, 不进入 SMTP 信封
        _validate_email(to_mail)
        # REV46-M1: to_send 显示名长度截断 (防内存耗尽 + RFC 5322 line length 限制)
        # 与 subject header 一致, 限制 HEADER_MAX_LEN
        # 先做类型归一化 (None → '', bytes/非 str → str), 再做 forbidden 检查
        if to_send is None:
            to_send = ''
        if isinstance(to_send, bytes):
            try:
                to_send = to_send.decode('utf-8', errors='replace')
            except Exception:
                to_send = ''
        if not isinstance(to_send, str):
            to_send = str(to_send)
        if len(to_send) > HEADER_MAX_LEN:
            to_send = to_send[:HEADER_MAX_LEN]
        # to_send 是显示名, 不强制邮箱格式, 但要去 \r\n 防止 From 注入
        if _HEADER_FORBIDDEN.search(to_send):
            raise InvalidHeaderError('to_send contains forbidden chars (CR/LF/NUL)')
        safe_header = _sanitize_header(header)
        # message 限制最大长度 (防 OOM), 但允许 \r\n (MIME body 换行)
        # REV46-H5: 不再校验 message 中的 \r\n\0 (RFC 5322 MIME body 合法)
        if not isinstance(message, str):
            message = '' if message is None else str(message)
        if len(message) > MESSAGE_MAX_LEN:
            message = message[:MESSAGE_MAX_LEN]

        msg = MIMEText(message, mime_type, 'utf-8')
        # Header() 不会去掉 \r\n, 必须先用 _sanitize_header 过滤
        msg['From'] = Header(to_send)
        msg['To'] = Header(to_mail)
        msg['Subject'] = Header(safe_header)
        return msg

    def _send_msg(self, to_mail, msg):
        """REV28-L5: 拆分自 send() —— SMTP 连接 + 发送, 异常时主动关闭脏连接.

        REV46-H3: 加 3 次重试 + 指数 backoff (1s, 2s, 4s), 仅对暂时性错误重试.
        暂时性错误: SMTPServerDisconnected / socket.timeout / SMTPConnectError /
                    SMTPHeloError / OSError / ConnectionError.
        不可重试: SMTPAuthenticationError / SMTPRecipientsRefused / SMTPDataError
                  等业务错误 (重试也无效).

        REV46-M5: 发送成功/失败/重试日志.
        """
        smtp = self._get_or_create_smtp()
        max_retries = 3
        backoff_seq = (1, 2, 4)
        last_exc = None
        subject_for_log = str(msg.get('Subject', '') or '')[:50]
        # REV46-M5: 记录开始时间用于耗时统计
        t_start = time.monotonic()
        for attempt in range(max_retries + 1):
            try:
                smtp.sendmail(self.form_mail, to_mail, msg.as_string())
                # REV46-M5: 成功日志
                elapsed_ms = int((time.monotonic() - t_start) * 1000)
                _sendmail_logger.info(
                    'sendmail success: to=%s subject=%r elapsed=%dms attempt=%d/%d',
                    to_mail, subject_for_log,
                    elapsed_ms, attempt + 1, max_retries + 1,
                )
                return  # 成功
            except (smtplib.SMTPServerDisconnected,
                    smtplib.SMTPConnectError,
                    smtplib.SMTPHeloError,
                    smtplib.SMTPException,  # 父类兜底
                    socket.timeout,
                    ConnectionError,
                    OSError) as e:
                last_exc = e
                # REV46-M5: 重试日志 (仅当还未达最大重试)
                if attempt < max_retries:
                    _sendmail_logger.warning(
                        'sendmail retry: to=%s attempt=%d/%d err=%s: %s',
                        to_mail, attempt + 1, max_retries + 1,
                        e.__class__.__name__, e,
                    )
                # 业务错误 (认证/收件人) 不重试
                if isinstance(e, (smtplib.SMTPAuthenticationError,
                                  smtplib.SMTPRecipientsRefused,
                                  smtplib.SMTPDataError,
                                  smtplib.SMTPSenderRefused)):
                    # REV28-M3: 关闭脏连接
                    try:
                        smtp.close()
                    except Exception:
                        pass
                    self.smtp = None
                    # REV46-M5: 失败日志
                    elapsed_ms = int((time.monotonic() - t_start) * 1000)
                    _sendmail_logger.error(
                        'sendmail failed (business): to=%s subject=%r err=%s: %s elapsed=%dms',
                        to_mail, subject_for_log,
                        e.__class__.__name__, e, elapsed_ms,
                    )
                    raise
                # 暂时性错误, 关闭脏连接后重试
                try:
                    smtp.close()
                except Exception:
                    pass
                self.smtp = None
                if attempt >= max_retries:
                    # 已达最大重试次数
                    # REV46-M5: 失败日志
                    elapsed_ms = int((time.monotonic() - t_start) * 1000)
                    _sendmail_logger.error(
                        'sendmail failed (max retries): to=%s subject=%r err=%s: %s elapsed=%dms',
                        to_mail, subject_for_log,
                        e.__class__.__name__, e, elapsed_ms,
                    )
                    raise
                # 指数 backoff: 1s, 2s, 4s
                backoff = backoff_seq[min(attempt, len(backoff_seq) - 1)]
                time.sleep(backoff)
                # 重建连接
                smtp = self._get_or_create_smtp()
            except Exception as e:
                # 未知错误, 不重试
                try:
                    smtp.close()
                except Exception:
                    pass
                self.smtp = None
                # REV46-M5: 失败日志
                elapsed_ms = int((time.monotonic() - t_start) * 1000)
                _sendmail_logger.error(
                    'sendmail failed (unknown): to=%s subject=%r err=%s: %s elapsed=%dms',
                    to_mail, subject_for_log,
                    e.__class__.__name__, e, elapsed_ms,
                )
                raise
        # 不可达, 仅占位
        if last_exc:
            raise last_exc

    def send(self, to_mail, to_send, header, message, mime_type='plain'):
        """
        to_mail-->发送到目的邮箱的邮箱名,str类型
        to_send-->指定发送的名称,str类型
        header-->发送的邮箱标题,str类型
        message-->发送的邮件内容信息,str类型
        mime_type-->MIME 类型: 'plain' (默认) 或 'html'
        REV28-L5: 拆分为 _build_msg (校验+构造) 和 _send_msg (SMTP 发送),
                  本方法只剩顶层调度, 可读性 + 单元可测性提升.
        REV46-M3: 支持 template_id + 模板渲染:
                  - send_template(template_id, **kwargs) 走模板系统
                  - send 仍可独立调用 (向后兼容)
        """
        msg = self._build_msg(to_mail, to_send, header, message, mime_type)
        self._send_msg(to_mail, msg)

    def send_template(self, template_id, to_mail, to_send='', **kwargs):
        """REV46-M3: 用模板 ID 渲染并发送邮件.

        Args:
            template_id: 模板 ID, 对应 EMAIL_TEMPLATES 的 key
            to_mail: 收件人
            to_send: 发件人显示名 (可选, 默认空)
            **kwargs: 模板占位符替换值 (如 code='1234', username='alice')

        Raises:
            ValueError: 模板 ID 不存在
            InvalidHeaderError: 模板渲染后 subject 含 CR/LF/NUL
        """
        subject, body, mime_type = render_email_template(template_id, **kwargs)
        self.send(to_mail, to_send, subject, body, mime_type=mime_type)


# REV46-M3: 模板渲染
class EmailTemplateError(Exception):
    """邮件模板错误 (模板 ID 不存在 / 渲染失败)."""
    pass


def render_email_template(template_id, **kwargs):
    """REV46-M3: 从 EMAIL_TEMPLATES 查模板, 用 kwargs 替换 {key} 占位符.

    Returns:
        (subject, body, mime_type) 元组

    Raises:
        EmailTemplateError: 模板 ID 不存在
    """
    if not isinstance(EMAIL_TEMPLATES, dict) or template_id not in EMAIL_TEMPLATES:
        raise EmailTemplateError(
            'email template not found: %r (available: %s)' % (
                template_id, list(EMAIL_TEMPLATES.keys()) if isinstance(EMAIL_TEMPLATES, dict) else 'N/A'
            )
        )
    tmpl = EMAIL_TEMPLATES[template_id]
    if not isinstance(tmpl, dict):
        raise EmailTemplateError('email template %r is not a dict' % template_id)
    subject = tmpl.get('subject', '')
    body = tmpl.get('body', '')
    mime_type = tmpl.get('mime_type', 'plain')
    # 占位符替换: {key} → str(kwargs[key])
    # 策略: 仅当模板含 { 占位符时尝试替换 (空 kwargs 不抛)
    str_kwargs = {k: str(v) for k, v in kwargs.items()}
    if isinstance(subject, str) and '{' in subject:
        try:
            subject = subject.format(**str_kwargs)
        except (KeyError, IndexError, ValueError) as e:
            raise EmailTemplateError(
                'template %r subject render failed: %s' % (template_id, e)
            )
    if isinstance(body, str) and '{' in body:
        try:
            body = body.format(**str_kwargs)
        except (KeyError, IndexError, ValueError) as e:
            raise EmailTemplateError(
                'template %r body render failed: %s' % (template_id, e)
            )
    if mime_type not in ('plain', 'html'):
        mime_type = 'plain'
    return subject, body, mime_type
