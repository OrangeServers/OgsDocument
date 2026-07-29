# -*- coding: utf-8 -*-
"""MySQL / Redis 连通性检测（setup 向导"测试连接"与 apply 前置复测共用）。

只依赖 pymysql / redis 两个业务侧本就存在的库；不 import app.*。
"""
from __future__ import annotations

from typing import Any, Dict
from email.mime.text import MIMEText
import re
import smtplib

CONNECT_TIMEOUT = 5
_EMAIL_RE = re.compile(r'^[^@\s\r\n\0]+@[^@\s\r\n\0]+\.[^@\s\r\n\0]+$')


def _port(value: Any, default: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError('端口必须是数字')
    if not 1 <= port <= 65535:
        raise ValueError('端口必须在 1-65535 之间')
    return port


def test_mysql(payload: Dict[str, Any]) -> Dict[str, Any]:
    import pymysql

    from setup import state

    host = str(payload.get('host') or '').strip()
    user = str(payload.get('user') or '').strip()
    password = str(payload.get('password') or '')
    dbname = str(payload.get('dbname') or 'orange').strip()
    if not host or not user:
        return {'ok': False, 'msg': '主机与用户名必填'}
    # 与 config.py 的安全黑名单对齐：root/占位账号在正式启动时会被拒绝，
    # 在这里前置拦截，避免用户走完向导才失败
    if user in state.MYSQL_INSECURE or password in state.MYSQL_INSECURE:
        return {
            'ok': False,
            'msg': '出于安全策略，业务数据库不允许使用 root/占位账号或弱密码，'
                   '请为 OrangeServer 创建独立的数据库账号',
        }
    try:
        port = _port(payload.get('port'), 3306)
    except ValueError as exc:
        return {'ok': False, 'msg': str(exc)}
    try:
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            connect_timeout=CONNECT_TIMEOUT, charset='utf8mb4',
        )
    except Exception as exc:
        return {'ok': False, 'msg': '连接失败: %s' % _short(exc)}
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT VERSION()')
            version = str(cursor.fetchone()[0])
            cursor.execute('SHOW DATABASES LIKE %s', (dbname,))
            db_exists = cursor.fetchone() is not None
            has_tables = False
            if db_exists:
                cursor.execute(
                    'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s',
                    (dbname,),
                )
                has_tables = int(cursor.fetchone()[0]) > 0
        return {
            'ok': True,
            'server_version': version,
            'db_exists': db_exists,
            'has_tables': has_tables,
            'msg': 'MySQL %s 连接成功' % version,
        }
    except Exception as exc:
        return {'ok': False, 'msg': '查询失败: %s' % _short(exc)}
    finally:
        conn.close()


def test_redis(payload: Dict[str, Any]) -> Dict[str, Any]:
    import redis

    host = str(payload.get('host') or '').strip()
    password = str(payload.get('password') or '') or None
    if not host:
        return {'ok': False, 'msg': '主机必填'}
    try:
        port = _port(payload.get('port'), 6379)
        db = int(payload.get('db') or 0)
    except ValueError as exc:
        return {'ok': False, 'msg': str(exc)}
    try:
        client = redis.Redis(
            host=host, port=port, db=db, password=password,
            socket_timeout=CONNECT_TIMEOUT, socket_connect_timeout=CONNECT_TIMEOUT,
        )
        client.ping()
        return {'ok': True, 'msg': 'Redis 连接成功'}
    except Exception as exc:
        return {'ok': False, 'msg': '连接失败: %s' % _short(exc)}


def test_smtp(payload: Dict[str, Any]) -> Dict[str, Any]:
    host = str(payload.get('smtp_host') or '').strip()
    sender = str(payload.get('from_email') or '').strip()
    password = str(payload.get('password') or '')
    send_to = str(payload.get('send_to') or '').strip()
    security_mode = str(payload.get('security') or '').strip().lower()
    if not host or not sender or not password:
        return {'ok': False, 'msg': 'SMTP 主机、发件邮箱和授权码必填'}
    if not _EMAIL_RE.fullmatch(sender):
        return {'ok': False, 'msg': '发件邮箱格式不正确'}
    if send_to and not _EMAIL_RE.fullmatch(send_to):
        return {'ok': False, 'msg': '测试收件邮箱格式不正确'}
    if security_mode not in ('ssl', 'starttls', 'none'):
        return {'ok': False, 'msg': '加密方式不正确'}
    try:
        port = _port(payload.get('smtp_port'), 587)
    except ValueError as exc:
        return {'ok': False, 'msg': str(exc)}

    smtp = None
    try:
        if security_mode == 'ssl':
            smtp = smtplib.SMTP_SSL(host, port, timeout=CONNECT_TIMEOUT)
        else:
            smtp = smtplib.SMTP(host, port, timeout=CONNECT_TIMEOUT)
            if security_mode == 'starttls':
                smtp.starttls()
                smtp.ehlo()
        smtp.login(sender, password)
        smtp.noop()
        if send_to:
            message = MIMEText(
                'Your OrangeServer SMTP configuration is working.',
                'plain',
                'utf-8',
            )
            message['From'] = sender
            message['To'] = send_to
            message['Subject'] = 'OrangeServer SMTP test'
            smtp.sendmail(sender, send_to, message.as_string())
            return {'ok': True, 'msg': 'SMTP test email sent'}
        return {'ok': True, 'msg': 'SMTP connection verified'}
    except Exception as exc:
        return {'ok': False, 'msg': '连接失败: %s' % _short(exc)}
    finally:
        if smtp is not None:
            try:
                smtp.close()
            except Exception:
                pass


def _short(exc: Exception) -> str:
    """异常摘要：类型 + 首行消息，截断防日志注入/超长。"""
    text = '%s: %s' % (type(exc).__name__, str(exc).splitlines()[0] if str(exc) else '')
    return text[:200]
