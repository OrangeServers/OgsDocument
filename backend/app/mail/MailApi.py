from flask import request, jsonify
from app.tools.at import request_param
from app.tools.sendmail import SendMail, _validate_email, _sanitize_header, InvalidEmailError, InvalidHeaderError
from app.mail.config import build_mailer, resolve_mail_configuration
from app.tools.redisdb import ConnRedis
from app.core.config import (
    MAIL_RELAY_LIMIT_MIN, MAIL_RELAY_LIMIT_HOUR,
    MAIL_RELAY_PREFIX_MIN, MAIL_RELAY_PREFIX_HOUR,
    HEADER_MAX_LEN, MESSAGE_MAX_LEN,
)


def _client_ip():
    """P0-2: 限流键 —— 与登录失败限流一致, 取 X-Real-IP (Nginx 反向代理场景)。"""
    return request.headers.get('X-Real-IP', request.remote_addr or '127.0.0.1')


def _mail_rate_limit(ords, ip):
    """P0-2: 单 IP 维度滑动限流。
    - 1 分钟最多 MAIL_RELAY_LIMIT_MIN 次
    - 1 小时最多 MAIL_RELAY_LIMIT_HOUR 次
    返回 (allowed, retry_after_sec, error_code)。
    Redis 不可用时 fail-open (允许通过), 与 _check_captcha_rate_limit 风格一致。"""
    try:
        if not ip:
            return True, 0, 0
        k_min = MAIL_RELAY_PREFIX_MIN + ip
        n_min = ords.conn.incr(k_min)
        if n_min == 1:
            ords.conn.expire(k_min, 60)
        if n_min > MAIL_RELAY_LIMIT_MIN:
            ttl = ords.conn.ttl(k_min)
            return False, max(ttl, 1), 429
        k_hour = MAIL_RELAY_PREFIX_HOUR + ip
        n_hour = ords.conn.incr(k_hour)
        if n_hour == 1:
            ords.conn.expire(k_hour, 3600)
        if n_hour > MAIL_RELAY_LIMIT_HOUR:
            ttl = ords.conn.ttl(k_hour)
            return False, max(ttl, 60), 429
        return True, 0, 0
    except Exception:
        return True, 0, 0


class OrangeMailApi:
    def __init__(self):
        self.to_mail = request_param('to_mail')
        self.header = request_param('header')
        self.message = request_param('message')
        # P2-3: MIME 类型 (前端可指定 plain/html, 默认 plain 防滥用)
        raw_mime = (request_param('mime_type') or 'plain').lower()
        self.mime_type = raw_mime if raw_mime in ('plain', 'html') else 'plain'
        self.ords = ConnRedis()
        self.client_ip = _client_ip()

    def send(self):
        # P0-2: 单 IP 限流 (防匿名访客滥发导致 SMTP 服务商封号)
        allowed, retry_sec, err_code = _mail_rate_limit(self.ords, self.client_ip)
        if not allowed:
            return jsonify({
                'send_status': 'fail',
                'code': err_code,
                'msg': 'mail rate limit exceeded, retry after %d sec' % retry_sec,
                'retry_after': retry_sec,
            })
        # P0-1: 入口校验 —— to_mail / header / message 全部先验再发
        try:
            _validate_email(self.to_mail)
        except InvalidEmailError as e:
            return jsonify({'send_status': 'fail', 'code': 100, 'msg': 'invalid to_mail: %s' % e})
        try:
            safe_header = _sanitize_header(self.header)
        except InvalidHeaderError as e:
            return jsonify({'send_status': 'fail', 'code': 100, 'msg': 'invalid header: %s' % e})
        # message 长度限制
        if self.message is not None and len(str(self.message)) > MESSAGE_MAX_LEN:
            return jsonify({'send_status': 'fail', 'code': 100, 'msg': 'message too long (max %d)' % MESSAGE_MAX_LEN})

        mail_config = resolve_mail_configuration()
        if mail_config is None:
            return jsonify({
                'send_status': 'fail',
                'code': 100,
                'msg': '管理员尚未配置邮件服务',
            })
        sendmail = build_mailer(mail_config, mailer_factory=SendMail)
        try:
            sendmail.send(self.to_mail, 'OrangeServer', safe_header, self.message, mime_type=self.mime_type)
            return jsonify({'send_status': 'true'})
        except Exception as e:
            return jsonify({'send_status': 'fail', 'code': 100, 'msg': 'send failed: %s' % str(e)[:120]})
