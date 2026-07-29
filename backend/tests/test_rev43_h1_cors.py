# -*- coding: utf-8 -*-
"""REV43-H1: init.py CORS 配置单测.

背景:
- 之前 init.py 没装 flask-cors, 也没手工设置 Access-Control-Allow-Origin
- 前端 Vite dev server (默认 5173) 跨域调后端 (28000), 浏览器拦截, dev 环境无法调试
- 生产环境通过 Nginx 同源反代可绕过, 但 dev 环境无法调试

修复:
- 手工实现 CORS, 支持 OGS_CORS_ORIGINS 配置白名单
- 严格白名单匹配 (不允许通配 '*' 与 credentials 共存, 浏览器会拒绝)
- 凭据请求必须 echo back 精确 origin
- OPTIONS 预检直接 204, 不进 view_func
- Vary: Origin 防止 CDN / 浏览器缓存污染

覆盖范围:
  1) _parse_cors_origins 解析逻辑
  2) _set_cors_headers helper 行为
  3) _cors_preflight before_request 钩子
  4) _cors_actual after_request 钩子
  5) 安全: 白名单严格匹配, 无通配
  6) 集成: 与 trace_id 共存, /local/health 带 CORS 头
  7) 静态分析: init.py 含 REV43-H1 标记
"""
import os
import re
import sys
from unittest.mock import MagicMock

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) _parse_cors_origins 解析逻辑
# ============================================================
class TestParseCorsOrigins:
    """REV43-H1: OGS_CORS_ORIGINS 字符串解析."""

    def test_01_default_string_parses(self):
        """默认 Vite dev 端口 (5173) 解析为 frozenset."""
        from init import _parse_cors_origins
        result = _parse_cors_origins('http://localhost:5173,http://127.0.0.1:5173')
        assert result == frozenset({'http://localhost:5173', 'http://127.0.0.1:5173'})

    def test_02_empty_string_returns_empty(self):
        """空字符串 → 空 frozenset (CORS 完全关闭)."""
        from init import _parse_cors_origins
        assert _parse_cors_origins('') == frozenset()

    def test_03_none_returns_empty(self):
        """None (env 未设时 fallback) → 空 frozenset."""
        from init import _parse_cors_origins
        assert _parse_cors_origins(None) == frozenset()

    def test_04_single_origin(self):
        """单个 origin."""
        from init import _parse_cors_origins
        assert _parse_cors_origins('https://app.example.com') == frozenset({'https://app.example.com'})

    def test_05_trims_whitespace(self):
        """每个 origin 两端空白 trim."""
        from init import _parse_cors_origins
        result = _parse_cors_origins('  http://a.com , http://b.com  ')
        assert result == frozenset({'http://a.com', 'http://b.com'})

    def test_06_skips_empty_segments(self):
        """跳过空段 ('a, ,b' → {'a', 'b'}, 避免 ',,' 产生空 origin)."""
        from init import _parse_cors_origins
        result = _parse_cors_origins('http://a.com,,http://b.com,')
        assert result == frozenset({'http://a.com', 'http://b.com'})

    def test_07_case_sensitive(self):
        """origin 大小写敏感 (标准 CORS / URL 标准要求).

        'HTTPS://A.COM' != 'https://a.com'
        """
        from init import _parse_cors_origins
        result = _parse_cors_origins('https://A.com')
        assert 'https://A.com' in result
        assert 'https://a.com' not in result

    def test_08_returns_frozenset(self):
        """返回类型 frozenset (immutable, 防止运行时被改)."""
        from init import _parse_cors_origins
        result = _parse_cors_origins('http://a.com')
        assert isinstance(result, frozenset)


# ============================================================
# 2) _set_cors_headers helper 行为
# ============================================================
class TestSetCorsHeaders:
    """REV43-H1: _set_cors_headers(resp, origin) 在响应上设 CORS 头."""

    def test_01_sets_acao_echo(self):
        """Access-Control-Allow-Origin 必须 echo 精确 origin (不能用 *)."""
        from init import _set_cors_headers
        resp = MagicMock()
        resp.headers = {}
        _set_cors_headers(resp, 'http://localhost:5173')
        assert resp.headers['Access-Control-Allow-Origin'] == 'http://localhost:5173'
        assert resp.headers['Access-Control-Allow-Origin'] != '*'

    def test_02_sets_credentials_true(self):
        """Allow-Credentials=true (凭据请求 csrf_token / cookie)."""
        from init import _set_cors_headers
        resp = MagicMock()
        resp.headers = {}
        _set_cors_headers(resp, 'http://localhost:5173')
        assert resp.headers['Access-Control-Allow-Credentials'] == 'true'

    def test_03_sets_allow_methods(self):
        """Allow-Methods 含 GET/POST/OPTIONS."""
        from init import _set_cors_headers
        resp = MagicMock()
        resp.headers = {}
        _set_cors_headers(resp, 'http://localhost:5173')
        methods = resp.headers['Access-Control-Allow-Methods']
        assert 'GET' in methods
        assert 'POST' in methods
        assert 'OPTIONS' in methods

    def test_04_sets_allow_headers_including_csrf(self):
        """Allow-Headers 含 X-CSRF-Token (OrangeServer 鉴权必需)."""
        from init import _set_cors_headers
        resp = MagicMock()
        resp.headers = {}
        _set_cors_headers(resp, 'http://localhost:5173')
        headers = resp.headers['Access-Control-Allow-Headers']
        assert 'X-CSRF-Token' in headers
        assert 'Content-Type' in headers

    def test_05_sets_vary_origin(self):
        """Vary: Origin (防 CDN / 浏览器缓存污染)."""
        from init import _set_cors_headers
        resp = MagicMock()
        resp.headers = {}
        _set_cors_headers(resp, 'http://localhost:5173')
        assert 'Origin' in resp.headers['Vary']


# ============================================================
# 3) _cors_preflight before_request 钩子
# ============================================================
class TestCorsPreflight:
    """REV43-H1: OPTIONS 预检行为."""

    def test_01_options_whitelist_origin_returns_204(self, monkeypatch):
        """OPTIONS + 白名单 origin → 204."""
        from flask import Flask
        from init import _set_cors_headers

        _TEST_SET = frozenset({'http://localhost:5173'})

        app = Flask(__name__)

        @app.before_request
        def _preflight():
            from flask import request, make_response
            if request.method != 'OPTIONS':
                return None
            origin = request.headers.get('Origin')
            if not origin or origin not in _TEST_SET:
                return make_response('forbidden', 403)
            resp = make_response('', 204)
            _set_cors_headers(resp, origin)
            resp.headers['Access-Control-Max-Age'] = '600'
            return resp

        @app.route('/test', methods=['GET', 'POST', 'OPTIONS'])
        def view():
            return {'ok': True}

        with app.test_client() as c:
            resp = c.options('/test', headers={'Origin': 'http://localhost:5173'})
            assert resp.status_code == 204, \
                '白名单 OPTIONS 应返 204, 实际: %d' % resp.status_code
            assert resp.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5173'

    def test_02_options_non_whitelist_origin_returns_403(self):
        """OPTIONS + 非白名单 origin → 403 (拒绝探测允许列表)."""
        from flask import Flask
        from init import _set_cors_headers

        _TEST_SET = frozenset({'http://localhost:5173'})

        app = Flask(__name__)

        @app.before_request
        def _preflight():
            from flask import request, make_response
            if request.method != 'OPTIONS':
                return None
            origin = request.headers.get('Origin')
            if not origin or origin not in _TEST_SET:
                return make_response('forbidden', 403)
            resp = make_response('', 204)
            _set_cors_headers(resp, origin)
            resp.headers['Access-Control-Max-Age'] = '600'
            return resp

        @app.route('/test', methods=['GET', 'POST', 'OPTIONS'])
        def view():
            return {'ok': True}

        with app.test_client() as c:
            resp = c.options('/test', headers={'Origin': 'http://evil.com'})
            assert resp.status_code == 403, \
                '非白名单 OPTIONS 应返 403, 实际: %d' % resp.status_code
            # 拒绝时不应回写 ACAO (防止泄露允许列表)
            assert 'Access-Control-Allow-Origin' not in resp.headers

    def test_03_options_no_origin_returns_403(self):
        """OPTIONS 无 Origin 头 → 403."""
        from flask import Flask
        from init import _set_cors_headers

        _TEST_SET = frozenset({'http://localhost:5173'})

        app = Flask(__name__)

        @app.before_request
        def _preflight():
            from flask import request, make_response
            if request.method != 'OPTIONS':
                return None
            origin = request.headers.get('Origin')
            if not origin or origin not in _TEST_SET:
                return make_response('forbidden', 403)
            resp = make_response('', 204)
            _set_cors_headers(resp, origin)
            resp.headers['Access-Control-Max-Age'] = '600'
            return resp

        @app.route('/test', methods=['GET', 'POST', 'OPTIONS'])
        def view():
            return {'ok': True}

        with app.test_client() as c:
            resp = c.options('/test')  # 无 Origin header
            assert resp.status_code == 403

    def test_04_get_not_intercepted(self):
        """GET 请求不被 _cors_preflight 拦截 (返回 None, 进 view_func)."""
        from flask import Flask
        from init import _set_cors_headers

        _TEST_SET = frozenset({'http://localhost:5173'})
        view_called = []

        app = Flask(__name__)

        @app.before_request
        def _preflight():
            from flask import request, make_response
            if request.method != 'OPTIONS':
                return None
            origin = request.headers.get('Origin')
            if not origin or origin not in _TEST_SET:
                return make_response('forbidden', 403)
            resp = make_response('', 204)
            _set_cors_headers(resp, origin)
            resp.headers['Access-Control-Max-Age'] = '600'
            return resp

        @app.route('/test', methods=['GET', 'POST', 'OPTIONS'])
        def view():
            view_called.append(True)
            return {'ok': True}

        with app.test_client() as c:
            resp = c.get('/test', headers={'Origin': 'http://localhost:5173'})
            assert resp.status_code == 200
            assert view_called, 'GET 应进 view_func'

    def test_05_options_max_age_set(self):
        """预检响应含 Access-Control-Max-Age (浏览器缓存预检结果)."""
        from flask import Flask
        from init import _set_cors_headers

        _TEST_SET = frozenset({'http://localhost:5173'})

        app = Flask(__name__)

        @app.before_request
        def _preflight():
            from flask import request, make_response
            if request.method != 'OPTIONS':
                return None
            origin = request.headers.get('Origin')
            if not origin or origin not in _TEST_SET:
                return make_response('forbidden', 403)
            resp = make_response('', 204)
            _set_cors_headers(resp, origin)
            resp.headers['Access-Control-Max-Age'] = '600'
            return resp

        @app.route('/test', methods=['GET', 'POST', 'OPTIONS'])
        def view():
            return {'ok': True}

        with app.test_client() as c:
            resp = c.options('/test', headers={'Origin': 'http://localhost:5173'})
            assert resp.headers.get('Access-Control-Max-Age') == '600'

    def test_06_options_exact_match_no_subdomain(self):
        """白名单精确匹配 (不匹配子域名/路径).

        'http://localhost:5173' 不匹配 'http://localhost:5173/' (尾斜杠).
        """
        from flask import Flask
        from init import _set_cors_headers

        _TEST_SET = frozenset({'http://localhost:5173'})

        app = Flask(__name__)

        @app.before_request
        def _preflight():
            from flask import request, make_response
            if request.method != 'OPTIONS':
                return None
            origin = request.headers.get('Origin')
            if not origin or origin not in _TEST_SET:
                return make_response('forbidden', 403)
            resp = make_response('', 204)
            _set_cors_headers(resp, origin)
            resp.headers['Access-Control-Max-Age'] = '600'
            return resp

        @app.route('/test', methods=['GET', 'POST', 'OPTIONS'])
        def view():
            return {'ok': True}

        with app.test_client() as c:
            # 尾斜杠应不匹配 (origin 标准不含尾斜杠)
            resp = c.options('/test', headers={'Origin': 'http://localhost:5173/'})
            assert resp.status_code == 403, \
                '尾斜杠 origin 应被拒绝 (origin 标准不含尾斜杠)'


# ============================================================
# 4) _cors_actual after_request 钩子
# ============================================================
class TestCorsActual:
    """REV43-H1: 实际请求附 CORS 响应头."""

    def test_01_actual_whitelist_origin_sets_acao(self):
        """白名单 origin → 响应头 ACAO echo."""
        from flask import Flask
        from init import _set_cors_headers, _OGS_CORS_ORIGINS_SET

        app = Flask(__name__)

        @app.route('/test')
        def view():
            return {'ok': True}

        @app.after_request
        def _actual(resp):
            from flask import request
            origin = request.headers.get('Origin')
            if origin and origin in _OGS_CORS_ORIGINS_SET:
                _set_cors_headers(resp, origin)
            return resp

        with app.test_client() as c:
            resp = c.get('/test', headers={'Origin': 'http://localhost:5173'})
            assert resp.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5173'

    def test_02_actual_non_whitelist_origin_no_acao(self):
        """非白名单 origin → 响应头不含 ACAO (浏览器拦截响应)."""
        from flask import Flask
        from init import _set_cors_headers, _OGS_CORS_ORIGINS_SET

        app = Flask(__name__)

        @app.route('/test')
        def view():
            return {'ok': True}

        @app.after_request
        def _actual(resp):
            from flask import request
            origin = request.headers.get('Origin')
            if origin and origin in _OGS_CORS_ORIGINS_SET:
                _set_cors_headers(resp, origin)
            return resp

        with app.test_client() as c:
            resp = c.get('/test', headers={'Origin': 'http://evil.com'})
            assert 'Access-Control-Allow-Origin' not in resp.headers, \
                '非白名单 origin 不应回写 ACAO'

    def test_03_actual_no_origin_no_acao(self):
        """无 Origin 头 (同源请求) → 不设 ACAO (同源请求不需要 CORS 头)."""
        from flask import Flask
        from init import _set_cors_headers, _OGS_CORS_ORIGINS_SET

        app = Flask(__name__)

        @app.route('/test')
        def view():
            return {'ok': True}

        @app.after_request
        def _actual(resp):
            from flask import request
            origin = request.headers.get('Origin')
            if origin and origin in _OGS_CORS_ORIGINS_SET:
                _set_cors_headers(resp, origin)
            return resp

        with app.test_client() as c:
            resp = c.get('/test')  # 无 Origin
            # 同源请求不强制要求 ACAO, 但 _cors_actual 不应主动设 (避免浪费)
            assert 'Access-Control-Allow-Origin' not in resp.headers

    def test_04_actual_credentials_true(self):
        """白名单 origin → Allow-Credentials=true."""
        from flask import Flask
        from init import _set_cors_headers, _OGS_CORS_ORIGINS_SET

        app = Flask(__name__)

        @app.route('/test')
        def view():
            return {'ok': True}

        @app.after_request
        def _actual(resp):
            from flask import request
            origin = request.headers.get('Origin')
            if origin and origin in _OGS_CORS_ORIGINS_SET:
                _set_cors_headers(resp, origin)
            return resp

        with app.test_client() as c:
            resp = c.get('/test', headers={'Origin': 'http://localhost:5173'})
            assert resp.headers.get('Access-Control-Allow-Credentials') == 'true'

    def test_05_actual_vary_origin(self):
        """白名单 origin → Vary 包含 Origin (防缓存污染)."""
        from flask import Flask
        from init import _set_cors_headers, _OGS_CORS_ORIGINS_SET

        app = Flask(__name__)

        @app.route('/test')
        def view():
            return {'ok': True}

        @app.after_request
        def _actual(resp):
            from flask import request
            origin = request.headers.get('Origin')
            if origin and origin in _OGS_CORS_ORIGINS_SET:
                _set_cors_headers(resp, origin)
            return resp

        with app.test_client() as c:
            resp = c.get('/test', headers={'Origin': 'http://localhost:5173'})
            assert 'Origin' in resp.headers.get('Vary', '')


# ============================================================
# 5) 安全: 白名单严格匹配, 无通配
# ============================================================
class TestCorsSecurity:
    """REV43-H1: CORS 安全不变量."""

    def test_01_origins_set_is_frozenset(self):
        """模块级白名单必须是 frozenset (immutable, 防运行时被改)."""
        import init
        assert isinstance(init._OGS_CORS_ORIGINS_SET, frozenset), \
            '_OGS_CORS_ORIGINS_SET 应是 frozenset, 实际: %s' % type(init._OGS_CORS_ORIGINS_SET)

    def test_02_default_origins_includes_vite_dev(self):
        """默认白名单含 Vite dev 默认端口 (5173)."""
        import init
        # 默认 _env('OGS_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173')
        assert 'http://localhost:5173' in init._OGS_CORS_ORIGINS_SET
        assert 'http://127.0.0.1:5173' in init._OGS_CORS_ORIGINS_SET

    def test_03_no_wildcard_in_default(self):
        """默认白名单不含 '*' (与 Allow-Credentials 冲突)."""
        import init
        assert '*' not in init._OGS_CORS_ORIGINS_SET

    def test_04_no_wildcard_in_set_cors_headers(self):
        """_set_cors_headers 不设 ACAO='*'."""
        from init import _set_cors_headers
        resp = MagicMock()
        resp.headers = {}
        _set_cors_headers(resp, 'http://localhost:5173')
        assert resp.headers['Access-Control-Allow-Origin'] != '*'


# ============================================================
# 6) 集成: 真实 init.app 上的 CORS 行为
# ============================================================
class TestCorsIntegration:
    """REV43-H1: init.app 真实集成测试."""

    def test_01_init_app_has_cors_preflight_hook(self):
        """init.app 已注册 _cors_preflight 钩子."""
        import init
        from app.app_factory import app as _af_app
        # 检查 before_request_funcs 中是否含 _cors_preflight
        funcs = _af_app.before_request_funcs.get(None, [])
        names = [getattr(f, '__name__', repr(f)) for f in funcs]
        assert '_cors_preflight' in names, \
            'init.app 应注册 _cors_preflight before_request 钩子, 当前: %s' % names

    def test_02_init_app_has_cors_actual_hook(self):
        """init.app 已注册 _cors_actual 钩子."""
        from app.app_factory import app as _af_app
        funcs = _af_app.after_request_funcs.get(None, [])
        names = [getattr(f, '__name__', repr(f)) for f in funcs]
        assert '_cors_actual' in names, \
            'init.app 应注册 _cors_actual after_request 钩子, 当前: %s' % names

    def test_03_health_endpoint_has_cors_for_whitelist(self):
        """/local/health 对白名单 origin 返 CORS 头."""
        import init  # noqa: F401 触发 hook 注册
        from app.app_factory import app
        with app.test_client() as c:
            resp = c.get('/local/health', headers={'Origin': 'http://localhost:5173'})
            assert resp.status_code == 200
            assert resp.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5173'
            assert resp.headers.get('Access-Control-Allow-Credentials') == 'true'

    def test_04_health_endpoint_no_cors_for_evil(self):
        """/local/health 对非白名单 origin 不返 ACAO."""
        import init  # noqa: F401
        from app.app_factory import app
        with app.test_client() as c:
            resp = c.get('/local/health', headers={'Origin': 'http://evil.com'})
            assert resp.status_code == 200
            assert 'Access-Control-Allow-Origin' not in resp.headers

    def test_05_trace_id_and_cors_coexist(self):
        """X-Trace-Id 与 CORS 头共存 (after_request 顺序不冲突)."""
        import init  # noqa: F401
        from app.app_factory import app
        with app.test_client() as c:
            resp = c.get(
                '/local/health',
                headers={
                    'Origin': 'http://localhost:5173',
                    'X-Trace-Id': 'cors-test-trace',
                },
            )
            assert resp.status_code == 200
            # X-Trace-Id header 应在
            assert resp.headers.get('X-Trace-Id') == 'cors-test-trace'
            # ACAO 也应在
            assert resp.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5173'

    def test_06_options_to_health_returns_204(self):
        """OPTIONS 预检到 /local/health → 204 (不进 view_func)."""
        import init  # noqa: F401
        from app.app_factory import app
        with app.test_client() as c:
            resp = c.options(
                '/local/health',
                headers={'Origin': 'http://localhost:5173'},
            )
            assert resp.status_code == 204, \
                'OPTIONS 应返 204, 实际: %d' % resp.status_code
            assert resp.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5173'

    def test_07_options_to_health_non_whitelist_403(self):
        """OPTIONS 预检到 /local/health, 非白名单 origin → 403."""
        import init  # noqa: F401
        from app.app_factory import app
        with app.test_client() as c:
            resp = c.options(
                '/local/health',
                headers={'Origin': 'http://evil.com'},
            )
            assert resp.status_code == 403


# ============================================================
# 7) 静态分析: init.py 必含 CORS 关键组件
# ============================================================
class TestCorsStaticAnalysis:
    """REV43-H1: 静态分析 init.py 含 CORS 修复标记."""

    def _read_init(self):
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            return f.read()

    def test_01_init_has_cors_preflight_def(self):
        """init.py 必含 _cors_preflight 函数."""
        src = self._read_init()
        assert re.search(r'@app\.before_request\s*\n\s*def\s+_cors_preflight', src), \
            'init.py 应注册 @app.before_request _cors_preflight'

    def test_02_init_has_cors_actual_def(self):
        """init.py 必含 _cors_actual 函数."""
        src = self._read_init()
        assert re.search(r'@app\.after_request\s*\n\s*def\s+_cors_actual', src), \
            'init.py 应注册 @app.after_request _cors_actual'

    def test_03_init_has_set_cors_headers_helper(self):
        """init.py 必含 _set_cors_headers helper."""
        src = self._read_init()
        assert re.search(r'def\s+_set_cors_headers', src), \
            'init.py 应有 _set_cors_headers helper'

    def test_04_init_has_parse_cors_origins(self):
        """init.py 必含 _parse_cors_origins 解析函数."""
        src = self._read_init()
        assert re.search(r'def\s+_parse_cors_origins', src), \
            'init.py 应有 _parse_cors_origins 解析函数'

    def test_05_init_has_rev43_h1_marker(self):
        """init.py 必含 REV43-H1 注释标记."""
        src = self._read_init()
        assert 'REV43-H1' in src, 'init.py 应含 REV43-H1 标签注释'

    def test_06_init_uses_env_for_origins(self):
        """init.py 应通过 _env('OGS_CORS_ORIGINS', ...) 配置白名单."""
        src = self._read_init()
        assert re.search(r"_env\(\s*['\"]OGS_CORS_ORIGINS['\"]", src), \
            'init.py 应用 _env("OGS_CORS_ORIGINS", ...) 配置白名单'

    def test_07_init_explicitly_handles_options_preflight(self):
        """init.py _cors_preflight 应显式处理 OPTIONS (防止 csrf 误拦截)."""
        src = self._read_init()
        m = re.search(r'def\s+_cors_preflight[^:]*:\s*([\s\S]*?)(?=\n@|\nclass |\ndef\s+\w+\(|$)', src)
        assert m, '_cors_preflight 应存在'
        body = m.group(1)
        assert "'OPTIONS'" in body or '"OPTIONS"' in body, \
            '_cors_preflight 应检查 method == OPTIONS'
        assert '403' in body, \
            '_cors_preflight 非白名单 origin 应返 403'