# -*- coding: utf-8 -*-
"""REV46-H4: 邮件模块 rate limit 覆盖测试 (P0-2 标记实现).

REV46-H4 业务问题: 同一用户大量触发邮件发送 -> SMTP server 限流 -> 全员发不出.
已实现两层限流:
  1) _mail_rate_limit     (MailApi, /mail/send_mail 路由, IP 维度)
       - 1 分钟最多 MAIL_RELAY_LIMIT_MIN 次 (默认 5)
       - 1 小时最多 MAIL_RELAY_LIMIT_HOUR 次 (默认 30)
       - 超限返 (False, retry_after, 429)
       - Redis 不可用 fail-open
  2) _check_captcha_rate_limit (user.py, 注册/重置验证码, 邮箱+IP 双维度)
       - 同一邮箱 60s 内最多 1 次
       - 同一邮箱 24h 内最多 10 次
       - 同一 IP 24h 内最多 30 次
       - Redis 不可用 fail-open

测试覆盖:
  A) _mail_rate_limit 核心逻辑 (Redis incr+expire 滑动窗口)
  B) OrangeMailApi.send 限流集成 (超限返 429)
  C) _check_captcha_rate_limit 三层限制 (last/day/ip)
  D) CheckMail.send / ForgotPwdSend.send 集成限流
  E) 配置常量可调节
"""
import os
import re
from unittest.mock import MagicMock, patch

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_APP = os.path.join(_BACKEND, 'app')


# ============================================================
# A) _mail_rate_limit 核心逻辑
# ============================================================
class TestRev46H4MailRateLimitLogic:
    """REV46-H4: MailApi._mail_rate_limit 滑动窗口."""

    def _make_redis_mock(self):
        """构造 Redis mock: incr 返回递增, ttl 返回合理值."""
        rm = MagicMock()
        # incr 每次 +1
        rm.incr.side_effect = [1, 1, 2, 3, 4, 5, 6, 1, 1, 1, 2, 31]
        rm.ttl.return_value = 30
        rm.expire.return_value = True
        return rm

    def _make_ords(self, rm):
        """构造 ords (ConnRedis 实例)."""
        ords = MagicMock()
        ords.conn = rm
        return ords

    def test_01_under_min_limit_allowed(self):
        """1分钟内未超限应允许通过."""
        from app.mail.MailApi import _mail_rate_limit
        ords = self._make_ords(self._make_redis_mock())
        allowed, retry, code = _mail_rate_limit(ords, '1.2.3.4')
        assert allowed is True
        assert retry == 0
        assert code == 0

    def test_02_min_limit_first_call_sets_expire(self):
        """第一次 incr == 1 必须设 expire (60s)."""
        from app.mail.MailApi import _mail_rate_limit
        rm = self._make_redis_mock()
        ords = self._make_ords(rm)
        _mail_rate_limit(ords, '1.2.3.4')
        # 检查 expire 被调用, TTL=60
        expire_calls = [c for c in rm.expire.call_args_list
                        if c.args[1] == 60]
        assert len(expire_calls) >= 1, '应设置 min key TTL=60'

    def test_03_over_min_limit_blocks(self):
        """超分钟限流应返 False + retry_after + 429."""
        from app.mail.MailApi import _mail_rate_limit
        rm = MagicMock()
        rm.incr.side_effect = [6, 1]  # 第6次 min incr -> 超 5 限流
        rm.ttl.return_value = 30
        rm.expire.return_value = True
        ords = self._make_ords(rm)
        allowed, retry, code = _mail_rate_limit(ords, '1.2.3.4')
        assert allowed is False
        assert code == 429
        assert retry > 0

    def test_04_over_hour_limit_blocks(self):
        """超小时限流应返 False + retry + 429."""
        from app.mail.MailApi import _mail_rate_limit
        rm = MagicMock()
        rm.incr.side_effect = [1, 31]  # min 1 (允许), hour 31 -> 超 30 限流
        rm.ttl.return_value = 300
        rm.expire.return_value = True
        ords = self._make_ords(rm)
        allowed, retry, code = _mail_rate_limit(ords, '1.2.3.4')
        assert allowed is False
        assert code == 429
        assert retry >= 60  # hour retry_after 至少 60s

    def test_05_empty_ip_allowed(self):
        """空 IP 应直接允许通过 (不限流)."""
        from app.mail.MailApi import _mail_rate_limit
        rm = MagicMock()
        ords = self._make_ords(rm)
        allowed, retry, code = _mail_rate_limit(ords, '')
        assert allowed is True
        assert retry == 0
        assert code == 0
        rm.incr.assert_not_called()

    def test_06_redis_failure_fail_open(self):
        """Redis 异常时 fail-open (允许通过, 防 Redis 挂掉阻塞邮件)."""
        from app.mail.MailApi import _mail_rate_limit
        rm = MagicMock()
        rm.incr.side_effect = Exception('redis down')
        ords = self._make_ords(rm)
        allowed, retry, code = _mail_rate_limit(ords, '1.2.3.4')
        assert allowed is True
        assert retry == 0
        assert code == 0

    def test_07_ip_uses_x_real_ip_header(self, monkeypatch):
        """_client_ip 应优先取 X-Real-IP header (Nginx 反代场景)."""
        from app.mail.MailApi import _client_ip
        # 在 Flask request context 中测试
        from app.app_factory import app
        with app.test_request_context(headers={'X-Real-IP': '203.0.113.1'}, environ_overrides={'REMOTE_ADDR': '127.0.0.1'}):
            ip = _client_ip()
            assert ip == '203.0.113.1', '_client_ip 应优先取 X-Real-IP, 实际: %s' % ip


# ============================================================
# B) OrangeMailApi.send 限流集成
# ============================================================
class TestRev46H4OrangeMailApiIntegration:
    """REV46-H4: OrangeMailApi.send 集成限流."""

    def test_01_send_rate_limit_blocks_request(self, monkeypatch):
        """超限调用 OrangeMailApi.send 应返 429 + retry_after."""
        # 在 Flask request context 中, 用 monkeypatch 替换 ConnRedis 和 _mail_rate_limit
        from app.app_factory import app
        from app.mail.MailApi import OrangeMailApi
        # 用 monkeypatch 替换 _mail_rate_limit 强制返 False
        from app import mail
        monkeypatch.setattr(mail.MailApi, '_mail_rate_limit',
                            lambda ords, ip: (False, 45, 429))
        monkeypatch.setattr(mail.MailApi, 'ConnRedis', MagicMock())
        with app.test_request_context(headers={'X-Real-IP': '1.2.3.4'},
                                     query_string={'to_mail': 'a@b.com',
                                                   'header': 'h',
                                                   'message': 'm',
                                                   'mime_type': 'plain'}):
            api = OrangeMailApi()
            result = api.send()
            json_obj = result[0] if isinstance(result, tuple) else result
            data = json_obj.get_json()
            assert data['code'] == 429, '超限应返 429, 实际: %s' % data
            assert data['send_status'] == 'fail'
            assert 'rate limit' in data['msg'].lower()
            assert data['retry_after'] == 45


# ============================================================
# C) _check_captcha_rate_limit 三层限制
# ============================================================
class TestRev46H4CaptchaRateLimitLogic:
    """REV46-H4: _check_captcha_rate_limit 邮箱+IP 双维度."""

    def _make_redis(self, last_ts=None, day_count=1, ip_count=1):
        rm = MagicMock()
        rm.get.return_value = last_ts  # cap_last key
        rm.incr.side_effect = [day_count, ip_count]
        rm.ttl.return_value = 100
        rm.expire.return_value = True
        rm.set.return_value = True
        return rm

    def test_01_under_all_limits_allowed(self):
        """三层都未超限应允许通过."""
        from app.users.user import _check_captcha_rate_limit
        ords = MagicMock()
        ords.conn = self._make_redis()
        allowed, retry, code = _check_captcha_rate_limit(ords, 'a@b.com', '1.2.3.4')
        assert allowed is True

    def test_02_last_60s_blocks(self):
        """60s 内重复 (cap_last) 应拦截."""
        from app.users.user import _check_captcha_rate_limit
        ords = MagicMock()
        ords.conn = self._make_redis(last_ts='1')  # 上次发送时间存在
        allowed, retry, code = _check_captcha_rate_limit(ords, 'a@b.com', '1.2.3.4')
        assert allowed is False
        assert code == 109
        assert retry == 60

    def test_03_day_over_limit_blocks(self):
        """同一邮箱 24h 内超 10 次应拦截."""
        from app.users.user import _check_captcha_rate_limit
        ords = MagicMock()
        ords.conn = self._make_redis(day_count=11)
        allowed, retry, code = _check_captcha_rate_limit(ords, 'a@b.com', '1.2.3.4')
        assert allowed is False
        assert code == 110

    def test_04_ip_over_limit_blocks(self):
        """同一 IP 24h 内超 30 次应拦截."""
        from app.users.user import _check_captcha_rate_limit
        ords = MagicMock()
        ords.conn = self._make_redis(ip_count=31)
        allowed, retry, code = _check_captcha_rate_limit(ords, 'a@b.com', '1.2.3.4')
        assert allowed is False
        assert code == 111

    def test_05_redis_failure_fail_open(self):
        """Redis 异常时 fail-open."""
        from app.users.user import _check_captcha_rate_limit
        ords = MagicMock()
        ords.conn.get.side_effect = Exception('redis down')
        allowed, retry, code = _check_captcha_rate_limit(ords, 'a@b.com', '1.2.3.4')
        assert allowed is True


# ============================================================
# D) 业务集成: CheckMail / ForgotPwdSend 调用限流
# ============================================================
class TestRev46H4BusinessIntegration:
    """REV46-H4: 注册/重置验证码路径调用限流."""

    USER_PY = os.path.join(_APP, 'users', 'user.py')

    def test_01_check_mail_send_calls_captcha_rate_limit(self):
        """CheckMail.send 应调用 _check_captcha_rate_limit."""
        with open(self.USER_PY, encoding='utf-8') as f:
            src = f.read()
        # 找 CheckMail.send 方法体
        m = re.search(r'class\s+CheckMail[\s\S]*?def\s+send\s*\([^)]*\)\s*:([\s\S]*?)(?=\n    def\s|\nclass\s|\Z)', src)
        assert m, 'CheckMail.send 方法体缺失'
        body = m.group(1)
        assert '_check_captcha_rate_limit' in body, \
            'CheckMail.send 应调用 _check_captcha_rate_limit'

    def test_02_forgot_pwd_send_calls_captcha_rate_limit(self):
        """ForgotPwdSend.send 应调用 _check_captcha_rate_limit."""
        with open(self.USER_PY, encoding='utf-8') as f:
            src = f.read()
        # 找 ForgotPwdSend.send 方法体
        m = re.search(r'class\s+ForgotPwdSend[\s\S]*?def\s+send\s*\([^)]*\)\s*:([\s\S]*?)(?=\n    def\s|\nclass\s|\Z)', src)
        assert m, 'ForgotPwdSend.send 方法体缺失'
        body = m.group(1)
        assert '_check_captcha_rate_limit' in body, \
            'ForgotPwdSend.send 应调用 _check_captcha_rate_limit'

    def test_03_mail_api_calls_mail_rate_limit(self):
        """OrangeMailApi.send 应调用 _mail_rate_limit."""
        mail_api = os.path.join(_APP, 'mail', 'MailApi.py')
        with open(mail_api, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'def\s+send\s*\([^)]*\)\s*:([\s\S]*?)(?=\n    def\s|\nclass\s|\Z)', src)
        assert m
        body = m.group(1)
        assert '_mail_rate_limit' in body, \
            'OrangeMailApi.send 应调用 _mail_rate_limit'

    def test_04_all_three_send_paths_have_rate_limit(self):
        """三个 send 路径 (注册/重置/中继) 都有 rate limit 调用."""
        with open(self.USER_PY, encoding='utf-8') as f:
            user_src = f.read()
        # CheckMail.send
        m1 = re.search(r'class\s+CheckMail[\s\S]*?def\s+send\s*\([^)]*\)\s*:([\s\S]*?)(?=\n    def\s|\nclass\s|\Z)', user_src)
        # ForgotPwdSend.send
        m2 = re.search(r'class\s+ForgotPwdSend[\s\S]*?def\s+send\s*\([^)]*\)\s*:([\s\S]*?)(?=\n    def\s|\nclass\s|\Z)', user_src)
        assert '_check_captcha_rate_limit' in m1.group(1), '注册路径缺限流'
        assert '_check_captcha_rate_limit' in m2.group(1), '重置路径缺限流'
        # MailApi.send
        with open(os.path.join(_APP, 'mail', 'MailApi.py'), encoding='utf-8') as f:
            mail_src = f.read()
        m3 = re.search(r'def\s+send\s*\([^)]*\)\s*:([\s\S]*?)(?=\n    def\s|\nclass\s|\Z)', mail_src)
        assert '_mail_rate_limit' in m3.group(1), '中继路径缺限流'


# ============================================================
# E) 配置常量
# ============================================================
class TestRev46H4ConfigConstants:
    """REV46-H4: 限流常量从配置读, 可调节."""

    def test_01_mail_relay_constants_defined(self):
        """config.py 应定义 MAIL_RELAY_LIMIT_MIN/HOUR + PREFIX."""
        config_py = os.path.join(_APP, 'core', 'config.py')
        with open(config_py, encoding='utf-8') as f:
            src = f.read()
        for name in ('MAIL_RELAY_LIMIT_MIN', 'MAIL_RELAY_LIMIT_HOUR',
                     'MAIL_RELAY_PREFIX_MIN', 'MAIL_RELAY_PREFIX_HOUR'):
            assert name in src, 'config.py 应定义 %s' % name

    def test_02_constants_have_env_overrides(self):
        """限流常量应支持环境变量覆盖."""
        config_py = os.path.join(_APP, 'core', 'config.py')
        with open(config_py, encoding='utf-8') as f:
            src = f.read()
        # OGS_MAIL_RELAY_LIMIT_MIN / OGS_MAIL_RELAY_LIMIT_HOUR
        assert 'OGS_MAIL_RELAY_LIMIT_MIN' in src
        assert 'OGS_MAIL_RELAY_LIMIT_HOUR' in src

    def test_03_default_min_limit_5(self):
        """默认 1 分钟限流 5 次."""
        config_py = os.path.join(_APP, 'core', 'config.py')
        with open(config_py, encoding='utf-8') as f:
            src = f.read()
        # 找 MAIL_RELAY_LIMIT_MIN 的默认值
        m = re.search(r'MAIL_RELAY_LIMIT_MIN\s*=\s*int\([^,]*,\s*[\'"](\d+)[\'"]\s*\)', src)
        assert m
        assert m.group(1) == '5', '默认 MAIL_RELAY_LIMIT_MIN 应为 5'

    def test_04_default_hour_limit_30(self):
        """默认 1 小时限流 30 次."""
        config_py = os.path.join(_APP, 'core', 'config.py')
        with open(config_py, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'MAIL_RELAY_LIMIT_HOUR\s*=\s*int\([^,]*,\s*[\'"](\d+)[\'"]\s*\)', src)
        assert m
        assert m.group(1) == '30', '默认 MAIL_RELAY_LIMIT_HOUR 应为 30'


# ============================================================
# F) Redis 命名空间防冲突
# ============================================================
class TestRev46H4RedisKeyNamespacing:
    """REV46-H4: Redis key 前缀防与其他业务冲突."""

    def test_01_mail_relay_min_prefix(self):
        """mail_relay_min: 前缀."""
        config_py = os.path.join(_APP, 'core', 'config.py')
        with open(config_py, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r"MAIL_RELAY_PREFIX_MIN\s*=\s*['\"]([^'\"]+)['\"]", src)
        assert m
        assert m.group(1) == 'mail_relay_min:'

    def test_02_mail_relay_hour_prefix(self):
        """mail_relay_hour: 前缀."""
        config_py = os.path.join(_APP, 'core', 'config.py')
        with open(config_py, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r"MAIL_RELAY_PREFIX_HOUR\s*=\s*['\"]([^'\"]+)['\"]", src)
        assert m
        assert m.group(1) == 'mail_relay_hour:'


# ============================================================
# G) 超限响应格式
# ============================================================
class TestRev46H4ErrorResponseFormat:
    """REV46-H4: 超限响应格式 (HTTP code 429, retry_after)."""

    def test_01_429_error_code(self):
        """超限返 429 (HTTP Too Many Requests)."""
        from app.mail.MailApi import _mail_rate_limit
        rm = MagicMock()
        rm.incr.side_effect = [6, 1]
        rm.ttl.return_value = 30
        rm.expire.return_value = True
        ords = MagicMock()
        ords.conn = rm
        allowed, retry, code = _mail_rate_limit(ords, '1.2.3.4')
        assert code == 429

    def test_02_captcha_error_codes(self):
        """captcha 限流错误码 109/110/111 区分."""
        from app.users.user import _check_captcha_rate_limit
        # 60s 内重复
        ords = MagicMock()
        ords.conn.get.return_value = '1'
        allowed, _, code = _check_captcha_rate_limit(ords, 'a@b.com', '1.2.3.4')
        assert code == 109
        # 24h 超 10 次 (day_count 11, ip_count 不被调因为已 return)
        ords2 = MagicMock()
        ords2.conn.get.return_value = None
        ords2.conn.incr.side_effect = [11, 1]
        ords2.conn.ttl.return_value = 100
        allowed, _, code = _check_captcha_rate_limit(ords2, 'a@b.com', '1.2.3.4')
        assert code == 110
        # IP 超 30 次 (day_count 1, ip_count 31)
        ords3 = MagicMock()
        ords3.conn.get.return_value = None
        ords3.conn.incr.side_effect = [1, 31]
        ords3.conn.ttl.return_value = 100
        allowed, _, code = _check_captcha_rate_limit(ords3, 'a@b.com', '1.2.3.4')
        assert code == 111


# ============================================================
# H) 端到端 smoke
# ============================================================
class TestRev46H4EndToEnd:
    """REV46-H4: 端到端 smoke (rate limit + send 集成)."""

    def test_01_mail_rate_limit_called_in_send(self, monkeypatch):
        """OrangeMailApi.send 入口必调 _mail_rate_limit."""
        from app.mail.MailApi import OrangeMailApi, _mail_rate_limit as orig_rl
        from app import mail
        calls = []

        def spy_rl(ords, ip):
            calls.append((ip,))
            return (True, 0, 0)

        monkeypatch.setattr(mail.MailApi, '_mail_rate_limit', spy_rl)
        monkeypatch.setattr(mail.MailApi, 'SendMail', MagicMock())
        monkeypatch.setattr(mail.MailApi, 'ConnRedis', MagicMock())
        # 用 Flask request context
        from app.app_factory import app
        with app.test_request_context(headers={'X-Real-IP': '1.2.3.4'},
                                     query_string={'to_mail': 'a@b.com',
                                                   'header': 'h',
                                                   'message': 'm'}):
            api = OrangeMailApi()
            try:
                api.send()
            except Exception:
                pass  # SendMail mock 可能 raise, 忽略
            # 验证 _mail_rate_limit 被调用过
            assert len(calls) >= 1, '_mail_rate_limit 应在 send 入口被调用'