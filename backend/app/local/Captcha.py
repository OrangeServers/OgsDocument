"""P1-5: 后端图形验证码生成 + 校验。

UI改造：由「扭曲字符图片验证码」改为「算术验证码」。原图片验证码字符扭曲+噪点，
用户难辨认（登录摩擦高）且与 Mission Control 干净视觉违和。算术题（如 3 + 5 = ?）
人极易、机器人需先解析表达式再计算，配合既有 IP/账号限流足够内部系统使用，
前端以品牌风格文本渲染表达式，不再依赖图片。

- GET  /local/captcha/get   -> 返回 captcha_id + captcha_expr 表达式文本 (匿名)
- 登录时 POST 多带 captcha_id + captcha_answer 字段（答案为计算结果数字）
"""
import os
import random

from flask import request, jsonify

from app.tools.redisdb import ConnRedis
from app.tools.at import Log
from app.core.config import CAPTCHA_GET_LIMIT_MIN, CAPTCHA_GET_PREFIX_MIN


_CAPTCHA_TTL = 180  # 3 分钟
_CAPTCHA_PREFIX = 'captcha:'

# 算术验证码数值范围：加法两数各 1~_ARITH_MAX（结果最大 2*_ARITH_MAX），减法保证非负
_ARITH_MAX = 20


def _gen_arithmetic():
    """生成算术验证码，返回 (展示表达式, 答案字符串)。

    随机加法/减法：加法两数各 1~20，减法保证 a>=b（结果非负）。
    表达式形如 "3 + 5 = ?"，答案为 "8"。
    """
    rng = random.SystemRandom()
    op = rng.choice(['+', '-'])
    a = rng.randint(1, _ARITH_MAX)
    if op == '+':
        b = rng.randint(1, _ARITH_MAX)
        ans = a + b
    else:
        b = rng.randint(1, a)
        ans = a - b
    return '%d %s %d = ?' % (a, op, b), str(ans)


def _gen_captcha_id():
    """32 字符随机 ID（hex 16 字节），用作 Redis key 的唯一标识。"""
    return os.urandom(16).hex()


class CaptchaGet:
    """GET /local/captcha/get — 匿名端点，返回 captcha_id + base64 PNG。"""

    def __init__(self):
        self.ords = ConnRedis()

    @staticmethod
    def _client_ip():
        """P1-3: 限流键与登录/邮件限流保持一致。"""
        return request.headers.get('X-Real-IP', request.remote_addr or '127.0.0.1')

    def _captcha_rate_limit(self, ip):
        """P1-3: 单 IP 维度滑动限流。
        - 1 分钟最多 CAPTCHA_GET_LIMIT_MIN 次
        Redis 不可用时 fail-open。
        返回 (allowed, retry_after_sec)。"""
        try:
            if not ip:
                return True, 0
            k = CAPTCHA_GET_PREFIX_MIN + ip
            n = self.ords.conn.incr(k)
            if n == 1:
                self.ords.conn.expire(k, 60)
            if n > CAPTCHA_GET_LIMIT_MIN:
                ttl = self.ords.conn.ttl(k)
                return False, max(ttl, 1)
            return True, 0
        except Exception:
            return True, 0

    def get(self):
        # P1-3: 单 IP 限流 (防攻击者每分钟刷 1000 次 → Redis 内存膨胀)
        ip = self._client_ip()
        allowed, retry_sec = self._captcha_rate_limit(ip)
        if not allowed:
            # REV30-L10: 限流命中记录 warning 日志, 便于安全审计 (攻击者刷 captcha 时能看到)
            Log.logger.warning('captcha rate limit: ip=%s retry_after=%d' % (ip, retry_sec))
            return jsonify({
                'code': 429,
                'msg': 'captcha get rate limit exceeded, retry after %d sec' % retry_sec,
                'retry_after': retry_sec,
            })
        expr, answer = _gen_arithmetic()
        captcha_id = _gen_captcha_id()
        # 写 Redis: captcha:<id> -> 答案 (TTL 180s)，前端仅拿到表达式不拿到答案
        self.ords.conn.set(_CAPTCHA_PREFIX + captcha_id, answer, ex=_CAPTCHA_TTL)
        return jsonify({
            'code': 0,
            'captcha_id': captcha_id,
            'captcha_expr': expr,
            'ttl': _CAPTCHA_TTL,
        })


def verify_captcha(ords, captcha_id, captcha_answer):
    """登录/注册时调用。校验通过会**先 delete 再返回 True**（防重放）。

    返回:
        True  - 校验通过
        False - 校验失败（id 不存在 / 已过期 / 答案不对 / 参数缺失）
    """
    if not captcha_id or not captcha_answer:
        return False
    key = _CAPTCHA_PREFIX + captcha_id
    stored = ords.conn.get(key)
    if not stored:
        return False
    # 比较前先删除（防重放 / 防暴力比对后绕过）
    ords.conn.delete(key)
    if isinstance(stored, bytes):
        try:
            # REV30-L11: 严格 decode, 异常走 except 返 False (极端 Unicode 损坏时)
            stored = stored.decode('utf-8', errors='strict')
        except (UnicodeDecodeError, AttributeError):
            return False
    return str(captcha_answer).strip().lower() == str(stored).strip().lower()
