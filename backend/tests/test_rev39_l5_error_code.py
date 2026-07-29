# -*- coding: utf-8 -*-
"""REV39-L5: 错误码 100 vs 3/4 语义重叠修复回归测试。

背景：REV36-L5 报告 at.py:77/84 用 code=100 同时表示"未登录"和"权限不足",
       但 init.py:70-96 docstring 明确说 code=3=未授权, code=4=权限不够。
       REV37-H4 已通过 ApiCode.UNAUTHORIZED(3)/FORBIDDEN(4) 修复。
       本测试:
         1) 验证 at.py:91/98 仍走 ApiCode.UNAUTHORIZED/FORBIDDEN
         2) 扫雷: 全 backend 不应残留 'code': 100 用作错误响应
         3) _STATUS_BY_CODE 映射: 3→401, 4→403, 100→401
         4) apierr._resolve_status 行为正确
         5) init.py docstring 与 ApiCode 常量语义对齐
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
# 1) at.py:91/98 走 ApiCode 而非裸 100
# ============================================================
class TestAtPyRoleDecorator:
    def test_01_require_role_uses_apicode_unauthorized(self):
        """require_role 未登录分支必须用 ApiCode.UNAUTHORIZED(3)。"""
        from app.tools import at
        import inspect
        body = inspect.getsource(at.require_role)
        # 必须有 ApiCode.UNAUTHORIZED
        assert 'ApiCode.UNAUTHORIZED' in body, \
            'require_role 应使用 ApiCode.UNAUTHORIZED(3) 而非裸 code=100'
        # 不应有裸 100
        assert not re.search(r"['\"]code['\"]\s*:\s*100", body), \
            'require_role 不应再使用裸 code=100 (REV36-L5 REV37-H4 已修复)'

    def test_02_require_role_uses_apicode_forbidden(self):
        """require_role 权限不足分支必须用 ApiCode.FORBIDDEN(4)。"""
        from app.tools import at
        import inspect
        body = inspect.getsource(at.require_role)
        assert 'ApiCode.FORBIDDEN' in body, \
            'require_role 应使用 ApiCode.FORBIDDEN(4) 而非裸 code=100'

    def test_03_require_role_uses_api_error(self):
        """require_role 必须走 api_error 包装器。"""
        from app.tools import at
        import inspect
        body = inspect.getsource(at.require_role)
        assert 'api_error' in body, 'require_role 应走 api_error 统一响应'

    def test_04_rev39_l5_comment(self):
        """require_role 文档字符串应有 REV39-L5 标签。"""
        from app.tools import at
        import inspect
        doc = at.require_role.__doc__ or ''
        assert 'REV39-L5' in doc, 'require_role docstring 应含 REV39-L5 标签'


# ============================================================
# 2) 全 backend 扫雷: 不应残留 code=100 当错误响应
# ============================================================
class TestNoBareCode100:
    def test_01_no_code100_in_at_py(self):
        """at.py 不应有裸 code=100 错误响应。"""
        at_py = os.path.join(_BACKEND, 'app', 'tools', 'at.py')
        with open(at_py, encoding='utf-8') as f:
            src = f.read()
        # 匹配 {'code': 100, ...} 或 {'code':100, ...}
        assert not re.search(r"['\"]code['\"]\s*:\s*100\b", src), \
            'at.py 仍有裸 code=100 错误响应，需替换为 ApiCode.UNAUTHORIZED/FORBIDDEN'

    def test_02_no_code100_in_apierr_py(self):
        """apierr.py 允许 100 在 _STATUS_BY_CODE dict 里（映射键），但不应在业务响应里。"""
        apierr_py = os.path.join(_BACKEND, 'app', 'tools', 'apierr.py')
        with open(apierr_py, encoding='utf-8') as f:
            src = f.read()
        # 剥离 docstring ("""...""")
        src_no_doc = re.sub(r'"""[\s\S]*?"""', '', src)
        # _STATUS_BY_CODE 中 100 是映射键（业务码），允许
        # 但不应在 jsonify({'code': 100, ...}) 响应体里
        assert not re.search(r"jsonify\(\{[^}]*['\"]code['\"]\s*:\s*100\b", src_no_doc), \
            'apierr.py 不应使用裸 code=100 业务响应（应走 ApiCode.BUSINESS_UNAUTHORIZED）'

    def test_03_no_code100_in_init_py(self):
        """init.py 不应有裸 code=100 错误响应（docstring 注释里的 100 是文档说明，允许）。"""
        init_py = os.path.join(_BACKEND, 'init.py')
        with open(init_py, encoding='utf-8') as f:
            src = f.read()
        # docstring 块 ("""...""") 内的数字说明不算
        # 关注实际 jsonify / api_error 调用
        assert not re.search(r"jsonify\(\{[^}]*['\"]code['\"]\s*:\s*100\b", src), \
            'init.py 不应有裸 code=100 错误响应'

    def test_04_no_code100_in_api_modules(self):
        """4 个 api 模块不应有裸 code=100 错误响应。"""
        api_dir = os.path.join(_BACKEND, 'app', 'api')
        for fname in os.listdir(api_dir):
            if not fname.endswith('.py') or fname.startswith('_'):
                continue
            fpath = os.path.join(api_dir, fname)
            with open(fpath, encoding='utf-8') as f:
                src = f.read()
            assert not re.search(r"jsonify\(\{[^}]*['\"]code['\"]\s*:\s*100\b", src), \
                '%s 仍有裸 code=100 错误响应' % fname


# ============================================================
# 3) _STATUS_BY_CODE 映射 + _resolve_status 行为
# ============================================================
class TestStatusByCode:
    def test_01_unauthorized_401(self):
        """code=3 (UNAUTHORIZED) → HTTP 401。"""
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[3] == 401

    def test_02_forbidden_403(self):
        """code=4 (FORBIDDEN) → HTTP 403。"""
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[4] == 403

    def test_03_business_unauthorized_401(self):
        """code=100 (BUSINESS_UNAUTHORIZED) → HTTP 401 (与 code=3 同语义)。"""
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[100] == 401

    def test_04_resolve_status_unauthorized(self):
        """_resolve_status(3) → 401。"""
        from app.tools.apierr import _resolve_status
        assert _resolve_status(3) == 401

    def test_05_resolve_status_forbidden(self):
        """_resolve_status(4) → 403。"""
        from app.tools.apierr import _resolve_status
        assert _resolve_status(4) == 403

    def test_06_resolve_status_explicit_override(self):
        """_resolve_status 显式 status 优先于映射。"""
        from app.tools.apierr import _resolve_status
        assert _resolve_status(3, status=200) == 200

    def test_07_resolve_status_unknown_code(self):
        """_resolve_status 未知 code 默认 400。"""
        from app.tools.apierr import _resolve_status
        assert _resolve_status(99999) == 400


# ============================================================
# 4) ApiCode 常量值正确
# ============================================================
class TestApiCodeConstants:
    def test_01_ok_zero(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.OK == 0

    def test_02_unauthorized_three(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.UNAUTHORIZED == 3

    def test_03_forbidden_four(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.FORBIDDEN == 4

    def test_04_business_unauthorized_100(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.BUSINESS_UNAUTHORIZED == 100


# ============================================================
# 5) init.py docstring 与 ApiCode 语义对齐
# ============================================================
class TestInitDocstring:
    def test_01_docstring_documents_code_3(self):
        """init.py 应有"各接口详解" docstring 块且明确 code=3=未授权。"""
        init_py = os.path.join(_BACKEND, 'init.py')
        with open(init_py, encoding='utf-8') as f:
            src = f.read()
        # 找含"接口详解"或"各接口详解"的 docstring
        m = re.search(r'"""([\s\S]*?(?:接口详解|接口未授权|权限不够)[\s\S]*?)"""', src)
        assert m, 'init.py 应有含"接口详解"的 docstring 块'
        doc = m.group(1)
        assert re.search(r'\b3\s+接口未授权访问|\b3\s+未授权', doc), \
            'docstring 应说明 code=3=未授权, doc 头部: %r' % doc[:300]

    def test_02_docstring_documents_code_4(self):
        """docstring 应明确 code=4=权限不够。"""
        init_py = os.path.join(_BACKEND, 'init.py')
        with open(init_py, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'"""([\s\S]*?(?:接口详解|接口未授权|权限不够)[\s\S]*?)"""', src)
        assert m
        doc = m.group(1)
        assert re.search(r'\b4\s+权限不够|\b4\s+权限', doc), \
            'docstring 应说明 code=4=权限不够, doc 头部: %r' % doc[:300]

    def test_03_docstring_documents_code_100(self):
        """docstring 中 code=100 不应与"未授权/权限"混用。"""
        init_py = os.path.join(_BACKEND, 'init.py')
        with open(init_py, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'"""([\s\S]*?(?:接口详解|接口未授权|权限不够)[\s\S]*?)"""', src)
        assert m
        doc = m.group(1)
        assert not re.search(r'\b100\s+(?:未授权|权限)', doc), \
            'docstring 不应将 code=100 与未授权/权限混用'


# ============================================================
# 6) 集成: 实际跑 require_role 走 ApiCode
# ============================================================
class TestRequireRoleIntegration:
    def test_01_require_role_unauth_returns_401(self, monkeypatch):
        """require_role 未登录时返 ApiCode.UNAUTHORIZED(3) + HTTP 401。"""
        from app.tools import at
        from flask import Flask
        app = Flask(__name__)

        @app.route('/test_role')
        @at.require_role('admin')
        def view():
            return 'ok'

        # Mock _session 返 (None, None) 模拟未登录
        monkeypatch.setattr(at, '_session', lambda: (None, None))
        # Mock request context
        with app.test_request_context('/test_role', method='GET'):
            with app.test_client() as client:
                resp = client.get('/test_role')
                assert resp.status_code == 401, \
                    'require_role 未登录应返 401，实际: %d' % resp.status_code
                data = resp.get_json()
                assert data['code'] == 3, \
                    'require_role 未登录应 code=3 (UNAUTHORIZED)，实际: %d' % data['code']
                assert '未授权' in data['msg']

    def test_02_require_role_forbidden_returns_403(self, monkeypatch):
        """require_role 权限不足时返 ApiCode.FORBIDDEN(4) + HTTP 403。"""
        from app.tools import at
        from flask import Flask
        app = Flask(__name__)

        @app.route('/test_role2')
        @at.require_role('admin')
        def view():
            return 'ok'

        # Mock _session 返登录态, 角色 user
        # at.require_role 用 ords.conn.get(role_key) 取角色, 所以 mock 完整 redis
        class FakeRedis:
            def __init__(self):
                self.conn = self  # at.require_role 用 ords.conn.get(role_key)
                self._data = {'alice_role': 'user'}
            def get(self, key):
                return self._data.get(key)
        monkeypatch.setattr(at, '_session', lambda: (FakeRedis(), 'alice'))
        with app.test_request_context('/test_role2', method='GET'):
            with app.test_client() as client:
                resp = client.get('/test_role2')
                assert resp.status_code == 403, \
                    'require_role 权限不足应返 403，实际: %d' % resp.status_code
                data = resp.get_json()
                assert data['code'] == 4, \
                    'require_role 权限不足应 code=4 (FORBIDDEN)，实际: %d' % data['code']
                assert '权限' in data['msg']
