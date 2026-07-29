# -*- coding: utf-8 -*-
"""setup 阶段安全件：一次性 token、限流、Origin 同源校验、密钥生成。

setup app 不接 Redis，不能用业务侧 csrf.py 的 nonce 机制；防线组合：
1. 自定义头 X-Setup-Token（跨站表单/资源加载无法携带自定义头）
2. Origin/Referer 同源校验（简化自 app/tools/csrf.py 的同源判定）
3. 全程无 cookie，无会话可被 CSRF
"""
from __future__ import annotations

import base64
import hmac
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

from setup import state

_LOCK = threading.Lock()
_FAILS = {'count': 0, 'locked_until': 0.0}
FAIL_LIMIT = 10
LOCK_SECONDS = 60


def ensure_token() -> str:
    """读取或生成一次性 setup token（0600 落盘 + 打印 stdout 日志）。

    已存在则复用：worker 重生/用户翻页不换 token。
    """
    path = state.token_path()
    try:
        if path.exists():
            existing = path.read_text(encoding='utf-8').strip()
            if existing:
                return existing
    except OSError:
        pass
    token = secrets.token_urlsafe(24)
    state.data_dir().mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(token + '\n')
    print(
        '[setup] 首次部署向导已启动。Setup Token（配置页第一步需要）: %s\n'
        '[setup] 也可读取文件: %s' % (token, path),
        flush=True,
    )
    return token


def drop_token() -> None:
    try:
        state.token_path().unlink(missing_ok=True)
    except OSError:
        pass


def verify_token(provided: str) -> bool:
    """恒时比较 + 进程内失败限流（10 次锁 60 秒）。"""
    now = time.monotonic()
    with _LOCK:
        if now < _FAILS['locked_until']:
            return False
    expected = ensure_token()
    ok = bool(provided) and hmac.compare_digest(expected, provided)
    with _LOCK:
        if ok:
            _FAILS['count'] = 0
        else:
            _FAILS['count'] += 1
            if _FAILS['count'] >= FAIL_LIMIT:
                _FAILS['count'] = 0
                _FAILS['locked_until'] = now + LOCK_SECONDS
    return ok


def same_origin(request) -> bool:
    """Origin/Referer 与 Host 同源校验；两者都缺失时放行（curl 等本机操作）。"""
    origin = request.headers.get('Origin') or request.headers.get('Referer') or ''
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return bool(parsed.netloc) and parsed.netloc == request.host


def generate_secret_key() -> str:
    return secrets.token_urlsafe(48)


def generate_fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii')
