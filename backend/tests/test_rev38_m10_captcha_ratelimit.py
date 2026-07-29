# -*- coding: utf-8 -*-
"""REV38-M10: /local/captcha/get IP rate limit。

背景: REV36-M10 指出 captcha 匿名接口无 rate limit, 攻击者刷请求会耗 CPU
      (PIL 画 PNG 耗时) + Redis 内存膨胀。
修复:
  - 已有 IP rate limit (CaptchaGet._captcha_rate_limit) - REV30 P1-3 实现
  - REV38-M10: 把默认限流从 10/分钟 → 30/分钟 (REV36 建议值, 留重试余量)
  - 限流 key = 'captcha_get_min:<ip>', TTL 60s, incr+expire 滑动窗口
  - 超限返 429 + retry_after
  - Redis 不可用 fail-open (不阻断合法用户)

覆盖范围:
  1) config CAPTCHA_GET_LIMIT_MIN 默认 30 (REV36 建议)
  2) CaptchaGet._captcha_rate_limit 走 Redis incr+expire
  3) 超限返 False, retry_after_sec = ttl
  4) Redis 失败 fail-open
  5) get() 端点超限返 429
  6) get() 端点正常返 0 + captcha_id + captcha_expr
  7) 不同 IP 互不影响
"""
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) config CAPTCHA_GET_LIMIT_MIN 默认 30
# ============================================================
class TestCaptchaLimitConfig:
    def test_01_default_is_30(self, clean_env):
        """OGS_CAPTCHA_GET_LIMIT_MIN 未设时默认 30 (REV36 建议)"""
        from app.core import config
        # 重新读取 (clean_env 已 delenv, config 模块已加载默认值)
        # 重新 import 拿到最新值
        import importlib
        importlib.reload(config)
        try:
            assert config.CAPTCHA_GET_LIMIT_MIN == 30
        finally:
            # reload 之前已 import 的模块可能引用了旧值, 还原
            importlib.reload(config)

    def test_02_explicit_override(self, clean_env):
        """OGS_CAPTCHA_GET_LIMIT_MIN=50 → 50"""
        clean_env.setenv('OGS_CAPTCHA_GET_LIMIT_MIN', '50')
        from app.core import config
        import importlib
        importlib.reload(config)
        try:
            assert config.CAPTCHA_GET_LIMIT_MIN == 50
        finally:
            importlib.reload(config)

    def test_03_prefix_default(self, clean_env):
        """OGS_CAPTCHA_GET_PREFIX_MIN 未设时默认 'captcha_get_min:'"""
        from app.core import config
        import importlib
        importlib.reload(config)
        try:
            assert config.CAPTCHA_GET_PREFIX_MIN == 'captcha_get_min:'
        finally:
            importlib.reload(config)


# ============================================================
# 2) CaptchaGet._captcha_rate_limit 走 Redis incr+expire
# ============================================================
class TestCaptchaRateLimitLogic:
    def _make_get(self, redis_mock):
        """构造 CaptchaGet, 把其 ords.conn 替换为 redis_mock"""
        from app.local.Captcha import CaptchaGet
        cg = CaptchaGet.__new__(CaptchaGet)
        cg.ords = MagicMock()
        cg.ords.conn = redis_mock
        return cg

    def test_01_first_request_allowed(self):
        """首次请求 allowed=True, retry=0"""
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 1  # 第一次 incr 返 1
        redis_mock.expire.return_value = True
        cg = self._make_get(redis_mock)
        allowed, retry = cg._captcha_rate_limit('1.2.3.4')
        assert allowed is True
        assert retry == 0
        # 第一次必须设 expire
        redis_mock.expire.assert_called_once()
        # key 应是 prefix + ip
        call_args = redis_mock.incr.call_args
        assert '1.2.3.4' in call_args.args[0]

    def test_02_under_limit_allowed(self):
        """第 N 次请求 (N<=limit) 仍 allowed"""
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 5  # 5 < 30
        cg = self._make_get(redis_mock)
        allowed, retry = cg._captcha_rate_limit('1.2.3.4')
        assert allowed is True
        assert retry == 0

    def test_03_at_limit_allowed(self):
        """第 limit 次允许"""
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 30  # 30 == 30 (允许)
        cg = self._make_get(redis_mock)
        allowed, _ = cg._captcha_rate_limit('1.2.3.4')
        assert allowed is True

    def test_04_over_limit_blocked(self):
        """第 limit+1 次拒绝, retry = ttl"""
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 31  # 31 > 30
        redis_mock.ttl.return_value = 42
        cg = self._make_get(redis_mock)
        allowed, retry = cg._captcha_rate_limit('1.2.3.4')
        assert allowed is False
        assert retry == 42  # 用 ttl 作为 retry

    def test_05_expire_only_on_first(self):
        """expire 仅在 n==1 时调用 (避免重置 TTL)"""
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 5
        cg = self._make_get(redis_mock)
        cg._captcha_rate_limit('1.2.3.4')
        # 5 != 1, 不应调 expire
        redis_mock.expire.assert_not_called()

    def test_06_redis_down_fail_open(self):
        """Redis 异常时 fail-open (allowed=True, retry=0)"""
        redis_mock = MagicMock()
        redis_mock.incr.side_effect = ConnectionError('redis down')
        cg = self._make_get(redis_mock)
        allowed, retry = cg._captcha_rate_limit('1.2.3.4')
        assert allowed is True
        assert retry == 0

    def test_07_empty_ip_fail_open(self):
        """ip 为空时直接 allowed=True (无 key)"""
        redis_mock = MagicMock()
        cg = self._make_get(redis_mock)
        allowed, retry = cg._captcha_rate_limit('')
        assert allowed is True
        # 不应调 redis
        redis_mock.incr.assert_not_called()

    def test_08_different_ips_isolated(self):
        """不同 IP 用不同 key"""
        redis_mock = MagicMock()
        redis_mock.incr.return_value = 1
        cg = self._make_get(redis_mock)
        cg._captcha_rate_limit('1.1.1.1')
        cg._captcha_rate_limit('2.2.2.2')
        # incr 应被调 2 次, 第二次 ip 不同
        assert redis_mock.incr.call_count == 2
        k1 = redis_mock.incr.call_args_list[0].args[0]
        k2 = redis_mock.incr.call_args_list[1].args[0]
        assert '1.1.1.1' in k1
        assert '2.2.2.2' in k2
        assert k1 != k2


# ============================================================
# 3) get() 端点行为
# ============================================================
class TestCaptchaGetEndpoint:
    def _setup_request(self, ip='1.2.3.4'):
        from flask import Flask, request as flask_req
        app = Flask(__name__)
        ctx = app.test_request_context(
            '/local/captcha/get',
            method='GET',
            headers={'X-Real-IP': ip},
        )
        ctx.push()
        return ctx

    def test_01_normal_request_returns_captcha(self):
        """正常请求返 code=0 + captcha_id + captcha_expr"""
        from app.local.Captcha import CaptchaGet

        ctx = self._setup_request('1.2.3.4')
        try:
            redis_mock = MagicMock()
            redis_mock.incr.return_value = 1
            redis_mock.set.return_value = True
            cg = CaptchaGet()
            cg.ords = MagicMock()
            cg.ords.conn = redis_mock
            with patch(
                'app.local.Captcha._gen_arithmetic',
                return_value=('3 + 5 = ?', '8'),
            ), patch(
                'app.local.Captcha._gen_captcha_id',
                return_value='fixed-captcha-id',
            ):
                resp = cg.get()
            assert resp.status_code == 200
            body = resp.get_json()
            assert body['code'] == 0
            assert body['captcha_id'] == 'fixed-captcha-id'
            assert body['captcha_expr'] == '3 + 5 = ?'
            assert 'png_base64' not in body
            assert body['ttl'] == 180
            redis_mock.set.assert_called_once_with(
                'captcha:fixed-captcha-id',
                '8',
                ex=180,
            )
        finally:
            ctx.pop()

    def test_02_rate_limited_returns_429(self):
        """超限返 429 + retry_after"""
        from app.local.Captcha import CaptchaGet

        ctx = self._setup_request('1.2.3.4')
        try:
            redis_mock = MagicMock()
            redis_mock.incr.return_value = 999  # 超 30
            redis_mock.ttl.return_value = 37
            cg = CaptchaGet()
            cg.ords = MagicMock()
            cg.ords.conn = redis_mock
            resp = cg.get()
            assert resp.status_code == 200  # jsonify 默认 200, body code 429
            body = resp.get_json()
            assert body['code'] == 429
            assert 'retry_after' in body
            assert body['retry_after'] == 37
            assert 'rate limit' in body['msg']
        finally:
            ctx.pop()

    def test_03_uses_x_real_ip(self):
        """rate limit key 用 X-Real-IP (防伪造绕过)"""
        from app.local.Captcha import CaptchaGet

        ctx = self._setup_request('203.0.113.5')
        try:
            redis_mock = MagicMock()
            redis_mock.incr.return_value = 1
            redis_mock.set.return_value = True
            cg = CaptchaGet()
            cg.ords = MagicMock()
            cg.ords.conn = redis_mock
            with patch(
                'app.local.Captcha._gen_arithmetic',
                return_value=('1 + 1 = ?', '2'),
            ):
                cg.get()
            # incr 的 key 应含 '203.0.113.5'
            key = redis_mock.incr.call_args.args[0]
            assert '203.0.113.5' in key
            # 不应是 127.0.0.1 (默认 fallback)
            assert '127.0.0.1' not in key
        finally:
            ctx.pop()

    def test_04_fallback_remote_addr(self):
        """无 X-Real-IP 时降级用 request.remote_addr"""
        from flask import Flask
        from app.local.Captcha import CaptchaGet

        app = Flask(__name__)
        # 不设 X-Real-IP, 用 environ_base 模拟 remote_addr
        ctx = app.test_request_context('/local/captcha/get', method='GET')
        ctx.push()
        try:
            redis_mock = MagicMock()
            redis_mock.incr.return_value = 1
            redis_mock.set.return_value = True
            cg = CaptchaGet()
            cg.ords = MagicMock()
            cg.ords.conn = redis_mock
            with patch(
                'app.local.Captcha._gen_arithmetic',
                return_value=('1 + 1 = ?', '2'),
            ):
                cg.get()
            # incr 用了某个 IP (127.0.0.1 or remote_addr), 验证 key 非空
            key = redis_mock.incr.call_args.args[0]
            assert 'captcha_get_min:' in key
        finally:
            ctx.pop()


@pytest.fixture
def clean_env(monkeypatch):
    """清除 OGS_CAPTCHA_GET_* 让默认值生效"""
    monkeypatch.delenv('OGS_CAPTCHA_GET_LIMIT_MIN', raising=False)
    monkeypatch.delenv('OGS_CAPTCHA_GET_PREFIX_MIN', raising=False)
    return monkeypatch
