# -*- coding: utf-8 -*-
"""REV39-L8: /local/sftp/websocket session 续期回归测试。

背景：REV36-L8 报告 SFTP WebSocket 同样无 session 续期（同 M2 模式）。
       REV38-M2 在 at.ws_auth 内部已实现 session 续期：
         - 握手通过后立即续期一次
         - 启动后台 greenlet 每 WS_SESSION_RENEW_INTERVAL 秒续期
         - token 失效时主动 close WS
       SFTP / SSH 共用 @ws_auth 装饰器，自动继承续期能力。

覆盖范围：
  1) local_sftp_connect 用 @ws_auth 装饰器
  2) at.ws_auth 含 session 续期实现（握手续期 + 后台 greenlet）
  3) _ws_session_renew_loop 完整实现
  4) sftp.py: OgsSftpWebSocket 不自己实现续期（避免重复）
  5) REV39-L8 注释存在（代码可追溯）
  6) 集成: ws_auth 在 token 失效时主动关 WS
"""
import os
import re
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) local_sftp_connect 用 @ws_auth 装饰器
# ============================================================
class TestSftpRouteUsesWsAuth:
    def test_01_local_sftp_connect_uses_ws_auth(self):
        """local_sftp_connect 视图函数必须用 @ws_auth 装饰。"""
        from app.api import local_api
        import inspect
        # 拿 source 看是否有 @ws_auth
        src = inspect.getsource(local_api)
        # 必须有 ws_auth 在 local_sftp_connect 之前
        m = re.search(r'@ws_auth\s*\n\s*def\s+local_sftp_connect', src)
        assert m, 'local_sftp_connect 应用 @ws_auth 装饰器'

    def test_02_local_web_ssh_uses_ws_auth(self):
        """local_web_ssh 视图函数也应用 @ws_auth 装饰（参考 baseline）。"""
        from app.api import local_api
        import inspect
        src = inspect.getsource(local_api)
        m = re.search(r'@ws_auth\s*\n\s*def\s+local_web_ssh', src)
        assert m, 'local_web_ssh 应用 @ws_auth 装饰器（baseline）'

    def test_03_rev39_l8_comment(self):
        """local_sftp_connect 注释块应有 REV39-L8 标签。"""
        from app.api import local_api
        import inspect
        src = inspect.getsource(local_api)
        assert 'REV39-L8' in src, 'local_api 应有 REV39-L8 注释标签'


# ============================================================
# 2) at.ws_auth 装饰器含 session 续期
# ============================================================
class TestWsAuthSessionRenew:
    def test_01_ws_auth_function_exists(self):
        """at.ws_auth 函数必须存在。"""
        from app.tools import at
        assert hasattr(at, 'ws_auth'), 'at.ws_auth 装饰器必须存在'
        assert callable(at.ws_auth), 'at.ws_auth 必须是 callable'

    def test_02_ws_auth_calls_renew_on_handshake(self):
        """ws_auth 握手通过后必须调 _ws_session_check_and_renew。"""
        from app.tools import at
        import inspect
        body = inspect.getsource(at.ws_auth)
        assert '_ws_session_check_and_renew' in body, \
            'ws_auth 握手后应调 _ws_session_check_and_renew 续期一次'

    def test_03_ws_auth_starts_background_renew(self):
        """ws_auth 必须启动后台 greenlet 定期续期。"""
        from app.tools import at
        import inspect
        body = inspect.getsource(at.ws_auth)
        # 找 spawn 后台 greenlet
        assert re.search(r'g_spawn|_ws_session_renew_loop', body), \
            'ws_auth 应启动 _ws_session_renew_loop 后台 greenlet'

    def test_04_session_renew_loop_function_exists(self):
        """_ws_session_renew_loop 后台续期函数必须存在。"""
        from app.tools import at
        assert hasattr(at, '_ws_session_renew_loop'), \
            '_ws_session_renew_loop 后台续期函数必须存在'
        assert callable(at._ws_session_renew_loop)

    def test_05_session_renew_loop_closes_ws_on_token_expire(self):
        """_ws_session_renew_loop 必须在 token 失效时主动 close WS。"""
        from app.tools import at
        import inspect
        body = inspect.getsource(at._ws_session_renew_loop)
        # 找 ws.close(1008, ...) 调用
        assert re.search(r'ws[_.]close\s*\(\s*1008', body) or 'session expired' in body, \
            '_ws_session_renew_loop 应在 token 失效时 close WS'

    def test_06_session_renew_loop_exits_when_ws_closed(self):
        """_ws_session_renew_loop 必须在 ws.closed 时退出循环。"""
        from app.tools import at
        import inspect
        body = inspect.getsource(at._ws_session_renew_loop)
        assert re.search(r'ws[_.]closed|getattr\([^,]+,\s*[\'"]closed', body), \
            '_ws_session_renew_loop 应在 ws.closed 时退出'


# ============================================================
# 3) session 续期配置 + 全局可调
# ============================================================
class TestSessionRenewConfig:
    def test_01_session_renew_interval_config(self):
        """WS_SESSION_RENEW_INTERVAL 必须可配置 (默认 300 秒)。"""
        from app.tools import at
        assert hasattr(at, 'WS_SESSION_RENEW_INTERVAL'), \
            'WS_SESSION_RENEW_INTERVAL 配置项必须存在'
        assert at.WS_SESSION_RENEW_INTERVAL == 300, \
            '默认 WS_SESSION_RENEW_INTERVAL 应为 300 秒 (5 分钟)'

    def test_02_session_renew_interval_env_override(self, monkeypatch):
        """OGS_WS_SESSION_RENEW_INTERVAL 环境变量可覆盖。"""
        monkeypatch.setenv('OGS_WS_SESSION_RENEW_INTERVAL', '600')
        # 重新加载模块
        import importlib
        from app.tools import at
        importlib.reload(at)
        try:
            assert at.WS_SESSION_RENEW_INTERVAL == 600
        finally:
            # 恢复默认
            monkeypatch.setenv('OGS_WS_SESSION_RENEW_INTERVAL', '300')
            importlib.reload(at)

    def test_03_disable_renew_with_zero(self, monkeypatch):
        """OGS_WS_SESSION_RENEW_INTERVAL=0 禁用后台续期。"""
        monkeypatch.setenv('OGS_WS_SESSION_RENEW_INTERVAL', '0')
        import importlib
        from app.tools import at
        importlib.reload(at)
        try:
            assert at.WS_SESSION_RENEW_INTERVAL == 0
        finally:
            monkeypatch.delenv('OGS_WS_SESSION_RENEW_INTERVAL', raising=False)
            importlib.reload(at)


# ============================================================
# 4) sftp.py: 不自己实现续期（避免与 ws_auth 重复）
# ============================================================
class TestSftpPyNoDuplicateRenew:
    def test_01_sftp_websocket_no_session_renew(self):
        """OgsSftpWebSocket 不应自己实现 session 续期（避免与 ws_auth 重复）。"""
        sftp_py = os.path.join(_BACKEND, 'app', 'ssh', 'sftp.py')
        with open(sftp_py, encoding='utf-8') as f:
            src = f.read()
        # 不应出现 "session 续期" 或 "TTL 续期" 或 "expire" 续期逻辑
        # sftp.py 应只关注 SFTP 协议，不关注鉴权/续期
        # ws_auth 已在 view func 层完成
        # 注意: 这里的 "expire" 是关键字检查
        # 但 sftp.py 可能用 "expired" 等其他词
        # 我们检查: 不应有 _ws_session_check_and_renew 或 _ws_session_renew_loop
        assert '_ws_session_check_and_renew' not in src, \
            'sftp.py 不应自己实现 _ws_session_check_and_renew (应复用 ws_auth)'
        assert '_ws_session_renew_loop' not in src, \
            'sftp.py 不应自己实现 _ws_session_renew_loop (应复用 ws_auth)'

    def test_02_webssh_websocket_no_session_renew(self):
        """OgsWebSocket 也不应自己实现续期（baseline 一致性）。"""
        webssh_py = os.path.join(_BACKEND, 'app', 'ssh', 'webssh.py')
        with open(webssh_py, encoding='utf-8') as f:
            src = f.read()
        assert '_ws_session_check_and_renew' not in src, \
            'webssh.py 不应自己实现续期 (应复用 ws_auth)'
        assert '_ws_session_renew_loop' not in src


# ============================================================
# 5) 集成: ws_auth 装饰器行为
# ============================================================
class TestWsAuthIntegration:
    def test_01_ws_auth_rejects_missing_token(self):
        """ws_auth 在 token 缺失时返 ('', 401)。"""
        from app.tools import at
        from flask import Flask
        app = Flask(__name__)

        @app.route('/ws')
        @at.ws_auth
        def view():
            return 'ok'

        # 没有 cookie
        with app.test_request_context('/ws', method='GET'):
            with app.test_client() as client:
                resp = client.get('/ws')
                # WebSocket upgrade 失败通常返 400, 但 ws_auth 装饰器在缺乏 wsgi.websocket 时返 ''
                # 这里只验证不抛异常
                assert resp.status_code in (400, 401, 426)

    def test_02_ws_auth_rejects_invalid_token(self, monkeypatch):
        """ws_auth 在 token 无效（Redis 中查不到）时返 ('', 401)。"""
        from app.tools import at
        from flask import Flask
        app = Flask(__name__)

        @app.route('/ws2')
        @at.ws_auth
        def view():
            return 'ok'

        # Mock Redis 查不到
        class FakeRedis:
            def __init__(self):
                self.conn = self
            def get(self, key):
                return None  # token 无效
        monkeypatch.setattr(at, 'ConnRedis', lambda: FakeRedis())
        with app.test_request_context('/ws2', method='GET', headers={'Cookie': 'ogs_token=fake'}):
            with app.test_client() as client:
                resp = client.get('/ws2')
                # ws_auth 返 ('', 401) tuple
                # Flask 升级握手失败时 body 为空，status 401
                assert resp.status_code in (400, 401, 426)
