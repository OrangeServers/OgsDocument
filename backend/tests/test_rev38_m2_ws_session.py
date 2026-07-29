# -*- coding: utf-8 -*-
"""REV38-M2: WebSocket session 续期回归测试。

背景: REV36-M2 报告原 ws_auth 仅握手时校验一次 token, 长连接 1h 但 Redis TTL 30min
       → 长连接中途 token 过期, 前端不知情。
修复: at.py 加 _ws_session_check_and_renew / _ws_session_renew_loop
       ws_auth 通过后立即续期一次 + 启动后台 greenlet 定期检查 + 失效时关 WS。

覆盖范围:
  1) WS_SESSION_RENEW_INTERVAL 常量与环境变量
  2) _ws_session_check_and_renew 续期逻辑 (alive / renewed 返回值)
  3) ws_auth 装饰器: 401 路径不启动后台, 通过路径启动
  4) _ws_session_renew_loop 后台循环: WS 关/未关/token 失效分支
  5) end-to-end: 装饰过的 view_func 集成测试
"""
import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# 路径初始化
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


@pytest.fixture
def at_module():
    """每次重新加载 at.py 以响应 env 变量变化"""
    import app.tools.at as _at
    importlib.reload(_at)
    return _at


# ============================================================
# 1) WS_SESSION_RENEW_INTERVAL 常量
# ============================================================
class TestWsSessionRenewInterval:
    def test_01_default_300_seconds(self, at_module):
        """默认 300 秒 (5 分钟)"""
        assert at_module.WS_SESSION_RENEW_INTERVAL == 300

    def test_02_env_override(self, monkeypatch):
        """OGS_WS_SESSION_RENEW_INTERVAL 环境变量可覆盖"""
        monkeypatch.setenv('OGS_WS_SESSION_RENEW_INTERVAL', '60')
        import app.tools.at as _at
        importlib.reload(_at)
        assert _at.WS_SESSION_RENEW_INTERVAL == 60

    def test_03_env_zero_disables(self, monkeypatch):
        """设 0 禁用后台续期"""
        monkeypatch.setenv('OGS_WS_SESSION_RENEW_INTERVAL', '0')
        import app.tools.at as _at
        importlib.reload(_at)
        assert _at.WS_SESSION_RENEW_INTERVAL == 0
        # 还原
        monkeypatch.delenv('OGS_WS_SESSION_RENEW_INTERVAL', raising=False)
        importlib.reload(_at)


# ============================================================
# 2) _ws_session_check_and_renew 续期逻辑
# ============================================================
class TestWsSessionCheckAndRenew:
    def test_01_empty_token_returns_dead(self, at_module):
        """空 token → (False, False)"""
        alive, renewed = at_module._ws_session_check_and_renew('')
        assert alive is False
        assert renewed is False
        alive, renewed = at_module._ws_session_check_and_renew(None)
        assert alive is False

    def test_02_valid_token_renewed_true_when_ttl_low(self, at_module):
        """TTL 不足阈值时触发续期"""
        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'  # token 有效
        mock_ords.conn.ttl.return_value = 60  # TTL 60s (低于阈值)
        with patch.object(at_module, 'ConnRedis', return_value=mock_ords):
            alive, renewed = at_module._ws_session_check_and_renew('tk-valid')
        assert alive is True
        assert renewed is True
        mock_ords.conn.expire.assert_called_once()

    def test_03_valid_token_renewed_false_when_ttl_sufficient(self, at_module):
        """TTL 充足时不触发续期
        SESSION_DEFAULT_EXP_SECONDS=10800, 阈值=5400, TTL=8000>5400 不续期
        """
        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'
        mock_ords.conn.ttl.return_value = 8000  # 远大于阈值
        with patch.object(at_module, 'ConnRedis', return_value=mock_ords):
            alive, renewed = at_module._ws_session_check_and_renew('tk-valid')
        assert alive is True
        assert renewed is False
        mock_ords.conn.expire.assert_not_called()

    def test_04_token_expired_returns_dead(self, at_module):
        """token 失效 (get 返回 None) → (False, False)"""
        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = None
        with patch.object(at_module, 'ConnRedis', return_value=mock_ords):
            alive, renewed = at_module._ws_session_check_and_renew('tk-expired')
        assert alive is False
        assert renewed is False

    def test_05_token_persisted_with_no_ttl(self, at_module):
        """ttl == -1 (永不过期) 也触发续期到默认值"""
        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'
        mock_ords.conn.ttl.return_value = -1
        with patch.object(at_module, 'ConnRedis', return_value=mock_ords):
            alive, renewed = at_module._ws_session_check_and_renew('tk-no-ttl')
        assert alive is True
        assert renewed is True
        mock_ords.conn.expire.assert_called_once()

    def test_06_redis_error_returns_alive(self, at_module):
        """Redis 异常时保守视为 alive, 避免误杀活跃会话"""
        with patch.object(at_module, 'ConnRedis', side_effect=Exception('redis down')):
            alive, renewed = at_module._ws_session_check_and_renew('tk')
        assert alive is True
        assert renewed is False


# ============================================================
# 3) ws_auth 装饰器
# ============================================================
class TestWsAuthDecorator:
    def test_01_missing_cookie_returns_401(self, at_module):
        """缺 cookie → 立即返 ('', 401)"""
        @at_module.ws_auth
        def view():
            return 'should not be called'

        mock_req = MagicMock()
        mock_req.cookies.get.return_value = None
        with patch.object(at_module, 'request', new=mock_req):
            result = view()
        assert result == ('', 401)

    def test_02_invalid_token_returns_401(self, at_module):
        """token 在 Redis 中不存在 → 返 ('', 401)"""
        @at_module.ws_auth
        def view():
            return 'should not be called'

        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = None
        mock_req = MagicMock()
        mock_req.cookies.get.return_value = 'tk-invalid'
        with patch.object(at_module, 'request', new=mock_req), \
             patch.object(at_module, 'ConnRedis', return_value=mock_ords):
            result = view()
        assert result == ('', 401)

    def test_03_valid_token_calls_view(self, at_module):
        """token 有效 → 调 view_func"""
        called = []

        @at_module.ws_auth
        def view():
            called.append(True)
            return 'view-result'

        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'
        mock_ords.conn.ttl.return_value = 1500  # 充足
        mock_req = MagicMock()
        mock_req.cookies.get.return_value = 'tk-valid'
        mock_req.environ.get.return_value = None  # 无 wsgi.websocket
        with patch.object(at_module, 'request', new=mock_req), \
             patch.object(at_module, 'ConnRedis', return_value=mock_ords), \
             patch.object(at_module, 'g_spawn', create=True) as mock_g_spawn:
            result = view()
        assert result == 'view-result'
        assert called == [True]
        # 无 WS ref 时不启动 greenlet
        mock_g_spawn.assert_not_called()

    def test_04_valid_token_with_ws_spawns_renew_loop(self, at_module):
        """token 有效 + 有 WS ref → 启动后台续期 greenlet"""
        @at_module.ws_auth
        def view():
            return 'ok'

        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'
        mock_ords.conn.ttl.return_value = 60  # 触发续期
        mock_req = MagicMock()
        mock_req.cookies.get.return_value = 'tk-valid'
        mock_ws = MagicMock()
        mock_req.environ.get.return_value = mock_ws
        with patch.object(at_module, 'request', new=mock_req), \
             patch.object(at_module, 'ConnRedis', return_value=mock_ords), \
             patch.object(at_module, 'g_spawn', create=True) as mock_g_spawn:
            view()
        # 验证 spawn 被调用 1 次（_ws_session_renew_loop）
        assert mock_g_spawn.call_count == 1
        args = mock_g_spawn.call_args[0]
        # spawn(target, *args) → target = _ws_session_renew_loop
        assert args[0] is at_module._ws_session_renew_loop
        # 第二个位置参数是 tk
        assert args[1] == 'tk-valid'
        # 第三个位置参数是 ws
        assert args[2] is mock_ws

    def test_05_renew_failure_does_not_block_handshake(self, at_module):
        """续期异常不影响握手"""
        @at_module.ws_auth
        def view():
            return 'ok'

        # token 校验通过, 但后续 _ws_session_check_and_renew 抛异常
        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'
        mock_req = MagicMock()
        mock_req.cookies.get.return_value = 'tk-valid'
        mock_req.environ.get.return_value = None  # 无 WS, 不会 spawn
        with patch.object(at_module, 'request', new=mock_req), \
             patch.object(at_module, 'ConnRedis', return_value=mock_ords), \
             patch.object(at_module, '_ws_session_check_and_renew',
                          side_effect=Exception('redis blip during renew')):
            result = view()
        assert result == 'ok'

    def test_06_zero_interval_disables_renew_loop(self, monkeypatch, at_module):
        """WS_SESSION_RENEW_INTERVAL=0 时不启动 greenlet"""
        monkeypatch.setenv('OGS_WS_SESSION_RENEW_INTERVAL', '0')
        import app.tools.at as _at
        importlib.reload(_at)
        # 注: at_module fixture 加载的是旧值, 需要用 reload 后的模块
        @_at.ws_auth
        def view():
            return 'ok'

        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'
        mock_ords.conn.ttl.return_value = 1500
        mock_req = MagicMock()
        mock_req.cookies.get.return_value = 'tk-valid'
        mock_req.environ.get.return_value = MagicMock()
        with patch.object(_at, 'request', new=mock_req), \
             patch.object(_at, 'ConnRedis', return_value=mock_ords), \
             patch.object(_at, 'g_spawn', create=True) as mock_g_spawn:
            view()
        assert mock_g_spawn.call_count == 0
        # 还原
        monkeypatch.delenv('OGS_WS_SESSION_RENEW_INTERVAL', raising=False)
        importlib.reload(_at)


# ============================================================
# 4) _ws_session_renew_loop 后台循环
# ============================================================
class TestWsSessionRenewLoop:
    def test_01_ws_closed_exits_loop(self, at_module):
        """WS 已关闭时立即退出 (不调 _ws_session_check_and_renew)"""
        mock_ws = MagicMock()
        mock_ws.closed = True
        mock_check = MagicMock(return_value=(True, False))
        with patch.object(at_module, '_ws_session_check_and_renew', new=mock_check), \
             patch.object(at_module, 'g_sleep', new=MagicMock()):
            at_module._ws_session_renew_loop('tk', mock_ws)
        # 第一次 sleep 后检测 ws.closed → 立即 return, 不再 check
        assert mock_check.call_count == 0

    def test_02_ws_ref_none_exits_loop(self, at_module):
        """ws_ref 为 None 时退出"""
        mock_check = MagicMock(return_value=(True, False))
        with patch.object(at_module, '_ws_session_check_and_renew', new=mock_check), \
             patch.object(at_module, 'g_sleep', new=MagicMock()):
            at_module._ws_session_renew_loop('tk', None)
        assert mock_check.call_count == 0

    def test_03_token_dead_closes_ws_with_1008(self, at_module):
        """token 失效时主动 close WS (1008=policy violation)"""
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_check = MagicMock(return_value=(False, False))
        with patch.object(at_module, '_ws_session_check_and_renew', new=mock_check), \
             patch.object(at_module, 'g_sleep', new=MagicMock()):
            at_module._ws_session_renew_loop('tk', mock_ws)
        assert mock_check.call_count == 1
        # close(code=1008, reason=...)
        mock_ws.close.assert_called_once()
        args = mock_ws.close.call_args[0]
        assert args[0] == 1008
        assert 'session' in args[1].lower() or 'expired' in args[1].lower()

    def test_04_token_alive_continues_loop(self, at_module):
        """token 有效时继续循环, 不调 close"""
        # 模拟: 第一次 sleep 后检查 alive, 继续 → 第二次 sleep 后 ws 已关 → 退出
        mock_ws = MagicMock()
        # closed 第一次是 False, 第二次设为 True 模拟中途断开
        closed_seq = iter([False, True])

        def get_closed():
            try:
                return next(closed_seq)
            except StopIteration:
                return True
        type(mock_ws).closed = property(lambda self: get_closed())

        check_call_count = [0]

        def check(tk):
            check_call_count[0] += 1
            return True, False  # alive

        with patch.object(at_module, '_ws_session_check_and_renew', new=check), \
             patch.object(at_module, 'g_sleep', new=MagicMock()):
            at_module._ws_session_renew_loop('tk', mock_ws)
        # alive 时 check 至少被调一次（直到 ws 关闭）
        assert check_call_count[0] >= 1
        # 不应 close
        mock_ws.close.assert_not_called()

    def test_05_check_exception_continues_loop(self, at_module):
        """_ws_session_check_and_renew 异常时不退出循环 (consume 一次异常)"""
        # closed 第一次 False (进入循环) → 第二次 True (退出)
        # check 第一次异常 → continue → 第二次正常返回 alive → 第三次 ws 关 → 退出
        mock_ws = MagicMock()
        closed_seq = iter([False, False, True])

        def get_closed():
            try:
                return next(closed_seq)
            except StopIteration:
                return True
        type(mock_ws).closed = property(lambda self: get_closed())

        check_call_count = [0]

        def check(tk):
            check_call_count[0] += 1
            if check_call_count[0] == 1:
                raise Exception('redis blip')
            return True, False  # alive

        with patch.object(at_module, '_ws_session_check_and_renew', new=check), \
             patch.object(at_module, 'g_sleep', new=MagicMock()):
            at_module._ws_session_renew_loop('tk', mock_ws)
        # 异常被吞, 继续循环
        assert check_call_count[0] >= 2


# ============================================================
# 5) end-to-end 集成测试
# ============================================================
class TestEndToEnd:
    def test_01_full_flow_with_renewed_session(self, at_module):
        """完整流程: 握手 → 立即续期 → view_func 执行"""
        @at_module.ws_auth
        def view():
            return 'view-ok'

        mock_ords = MagicMock()
        mock_ords.conn.get.return_value = b'alice'
        mock_ords.conn.ttl.return_value = 60  # 低于阈值 → 续期
        mock_req = MagicMock()
        mock_req.cookies.get.return_value = 'tk-e2e'
        mock_ws = MagicMock()
        mock_req.environ.get.return_value = mock_ws
        with patch.object(at_module, 'request', new=mock_req), \
             patch.object(at_module, 'ConnRedis', return_value=mock_ords), \
             patch.object(at_module, 'g_spawn', create=True) as mock_g_spawn:
            result = view()
        # 1. view_func 被调
        assert result == 'view-ok'
        # 2. 续期被触发 (expire 调一次)
        mock_ords.conn.expire.assert_called_once()
        # 3. 后台 greenlet 被启动
        assert mock_g_spawn.call_count == 1
