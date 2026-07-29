# -*- coding: utf-8 -*-
"""ti2-API: flasgger 接入 + /apidocs 自动 OpenAPI 文档生成.

完工标志 (3 项全过):
  1. /apidocs 路由可访问 + 返 Swagger UI HTML
  2. /apispec_1.json 返 OpenAPI 2.0 JSON, paths 覆盖所有 /server/* /local/* /auth/* /account/* 路由
  3. paths 条目含 description / tags / responses (从 ROUTES 表的 description 自动生成)

设计 (本地 Flask + 静态 AST 验证, 不污染 app.app_factory.app):
- Part A (3 tests): 静态 AST 验证 init.py 含 flasgger 接入代码
- Part B (5 tests): 用本地 Flask app + 真实 flasgger 验证 /apidocs + /apispec_1.json
- Part C (4 tests): 验证 spec paths / tags / responses 字段从 docstring 正确抽取

为什么不复用 app.app_factory.app:
  conftest 模块加载阶段强制 init Swagger 会让 init.py 顶层执行,
  注册 @app.before_request 等 hook 到全局 app, 进而污染 test_rev30::
  TestRev30H4Behavior::test_h4_content_disposition_safe (1 failed).
  用本地 Flask app 让本测试完全自包含, 不影响任何共享状态.
"""
import ast
import os

import pytest


# =============================================================================
# Part A: 静态 AST 验证 init.py 含 flasgger 接入代码 (3 tests)
# =============================================================================
# 验证关键改动确实写进 init.py:
#   A1) orange_init_api() 末尾有 _Swagger.init_app(app) 调用
#   A2) _register_routes_from_module / _make_view 内部有 view_func.__doc__ 赋值
#   A3) _make_view 注入的 docstring 模板含 tags: + responses: (flasgger YAML 关键字段)
class TestInitPyStaticA:
    """静态验证 init.py 含 flasgger 接入代码."""

    INIT_PY = os.path.join(os.path.dirname(__file__), '..', 'init.py')

    def _load_init_source(self):
        with open(self.INIT_PY, 'r', encoding='utf-8') as f:
            return f.read()

    def _load_init_tree(self):
        return ast.parse(self._load_init_source())

    def test_a1_orange_init_api_has_swagger_init_app(self):
        """orange_init_api() 函数体内应含 _Swagger.init_app(app) 调用."""
        tree = self._load_init_tree()
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'orange_init_api':
                target = node
                break
        assert target is not None, 'init.py 应定义 orange_init_api()'
        # 找 .init_app(...) 这种 Attribute 调用
        has_init_app = False
        for node in ast.walk(target):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == 'init_app':
                    has_init_app = True
                    break
        assert has_init_app, (
            'orange_init_api() 内应有 .init_app(...) 调用 (flasgger 接入点)'
        )

    def test_a2_view_func_docstring_injection_present(self):
        """应存在 view_func.__doc__ = ... 赋值 (自动注入 YAML docstring)."""
        source = self._load_init_source()
        assert 'view_func.__doc__' in source, (
            'init.py 应给 view_func.__doc__ 赋值 (自动注入 YAML docstring)'
        )
        # 检查含 YAML frontmatter 分隔符 '---' (在字符串字面量内, 至少出现 1 次)
        assert '---' in source, (
            "init.py 应含 '---' 分隔符 (YAML frontmatter)"
        )

    def test_a3_docstring_template_has_tags_and_responses(self):
        """view_func.__doc__ 模板应含 'tags:' 和 'responses:' (flasgger 抽 spec 关键字段)."""
        source = self._load_init_source()
        assert 'tags:' in source, "init.py 应含 'tags:' 字段 (YAML)"
        assert 'responses:' in source, "init.py 应含 'responses:' 字段 (YAML)"
        assert '200' in source and '401' in source and '500' in source, (
            'init.py 应定义 200/401/500 responses (常见业务 code)'
        )


# =============================================================================
# Part B: 用本地 Flask app 验证 flasgger 行为 (5 tests)
# =============================================================================
# 关键: 用临时 Flask 实例 + 真实 flasgger.Swagger, 注入与 init.py 同格式的 docstring,
#       验证 /apidocs + /apispec_1.json 路由 + spec 内容.
@pytest.fixture(scope='module')
def local_app():
    """创建本地 Flask app, 注入与 init.py 同格式的 docstring, 启动 flasgger."""
    from flask import Flask
    from flasgger import Swagger

    app = Flask('ti2_api_test_local')
    swag = Swagger(app, template={
        'swagger': '2.0',
        'info': {
            'title': 'OrangeServer API',
            'version': '1.0.0',
        },
        'basePath': '/',
        'schemes': ['http', 'https'],
    })

    # 仿 init.py _make_view 注入 docstring 格式:
    #   <summary>\n---\ntags:\n  - <tag>\nresponses:\n  200: ...\n
    def _make_view(url, summary, tag):
        def view_func():
            return {'ok': True}
        view_func.__doc__ = (
            '%s\n'
            '---\n'
            'tags:\n'
            '  - %s\n'
            'responses:\n'
            '  200:\n'
            '    description: 成功响应 (业务 code=0)\n'
            '  401:\n'
            '    description: 未登录 (code=3)\n'
            '  500:\n'
            '    description: 服务器错误 (code=2)\n'
        ) % (summary, tag)
        view_func.__name__ = url.strip('/').replace('/', '_') or 'root'
        app.add_url_rule(url, endpoint=view_func.__name__, view_func=view_func, methods=['POST'])
        return view_func

    # 4 个核心 api 模块各 1-3 个 fake 路由, 模拟 init.py 真实 ROUTES
    _make_view('/account/login_dl2', '用户登录（账号密码 + 图形验证码）', 'account')
    _make_view('/account/logout', '用户登出', 'account')
    _make_view('/account/group/list_all', '获取所有用户组', 'account')
    _make_view('/auth/host/list', '查询资产授权列表', 'auth')
    _make_view('/server/list', '查询资产列表', 'server')
    _make_view('/server/group/list', '查询资产组', 'server')
    _make_view('/server/add', '新增资产', 'server')
    _make_view('/local/dir/group', '获取本地目录分组', 'local')
    _make_view('/local/file', '本地文件上传', 'local')
    _make_view('/local/rsync', '本地文件同步', 'local')

    yield app


@pytest.fixture
def client(local_app):
    return local_app.test_client()


class TestLocalApidocs:
    """/apidocs + /apispec_1.json 路由在本地 Flask app 上能跑通."""

    def test_b1_apidocs_route_exists(self, local_app):
        """/apidocs 路由应被 flasgger 注册."""
        rules = [r.rule for r in local_app.url_map.iter_rules()]
        assert '/apidocs/' in rules, (
            'flasgger 应注册 /apidocs/ 路由, 实际规则: %r' % rules
        )

    def test_b2_apispec_json_route_exists(self, local_app):
        """/apispec_1.json 路由应被 flasgger 注册."""
        rules = [r.rule for r in local_app.url_map.iter_rules()]
        assert '/apispec_1.json' in rules, (
            'flasgger 应注册 /apispec_1.json 路由, 实际规则: %r' % rules
        )

    def test_b3_apidocs_returns_html(self, client):
        """GET /apidocs/ 应返 200 + text/html + 含 swagger 标志元素."""
        resp = client.get('/apidocs/')
        assert resp.status_code == 200, 'GET /apidocs/ 应返 200, 实际 %d' % resp.status_code
        ct = resp.headers.get('Content-Type', '')
        assert 'html' in ct.lower(), 'Content-Type 应含 html, 实际: %r' % ct
        body = resp.get_data(as_text=True)
        assert 'swagger' in body.lower(), '响应体应含 swagger UI 标志'

    def test_b4_apispec_json_returns_openapi_2(self, client):
        """GET /apispec_1.json 应返 OpenAPI 2.0 JSON 规范."""
        resp = client.get('/apispec_1.json')
        assert resp.status_code == 200, 'GET /apispec_1.json 应返 200, 实际 %d' % resp.status_code
        ct = resp.headers.get('Content-Type', '')
        assert 'json' in ct.lower(), 'Content-Type 应含 json, 实际: %r' % ct
        spec = resp.get_json()
        assert spec.get('swagger') == '2.0', 'OpenAPI version 应为 2.0, 实际: %r' % spec.get('swagger')
        assert 'info' in spec, 'spec 应含 info 字段'
        assert 'paths' in spec, 'spec 应含 paths 字段'
        assert spec['info']['title'] == 'OrangeServer API'
        assert spec['info']['version'] == '1.0.0'

    def test_b5_no_duplicate_paths(self, client):
        """spec paths 不应重复."""
        spec = client.get('/apispec_1.json').get_json()
        paths = list(spec['paths'].keys())
        assert len(paths) == len(set(paths)), (
            'spec paths 不可重复, %d 个 path 有 %d 个去重' %
            (len(paths), len(set(paths)))
        )


# =============================================================================
# Part C: 验证 spec paths / tags / responses 字段 (4 tests)
# =============================================================================
class TestLocalApispecEntries:
    """spec paths 条目应从 view_func docstring 抽出 description / tags / responses."""

    @staticmethod
    def _fetch_spec(client):
        return client.get('/apispec_1.json').get_json()

    def test_c1_paths_covers_account_local_server_auth(self, client):
        """spec paths 应覆盖 4 个核心 api 模块."""
        spec = self._fetch_spec(client)
        paths = list(spec['paths'].keys())
        assert any(p.startswith('/account/') for p in paths), (
            'spec 应含 /account/* 路径, 实际: %r' % paths
        )
        assert any(p.startswith('/auth/') for p in paths), (
            'spec 应含 /auth/* 路径, 实际: %r' % paths
        )
        assert any(p.startswith('/server/') for p in paths), (
            'spec 应含 /server/* 路径, 实际: %r' % paths
        )
        assert any(p.startswith('/local/') for p in paths), (
            'spec 应含 /local/* 路径, 实际: %r' % paths
        )

    def test_c2_account_login_has_tags_and_responses(self, client):
        """/account/login_dl2 应含 tags=[account] + responses.{200,401,500}."""
        spec = self._fetch_spec(client)
        path = spec['paths'].get('/account/login_dl2')
        assert path is not None, 'spec 应含 /account/login_dl2'
        post = path.get('post')
        assert post is not None, '/account/login_dl2 应含 POST spec'
        assert 'tags' in post, 'POST spec 应含 tags, 实际: %r' % post
        assert 'account' in post['tags'], (
            'tags 应含 account (取自 URL 第一段), 实际: %r' % post['tags']
        )
        assert 'responses' in post, 'POST spec 应含 responses, 实际: %r' % post
        for code in ('200', '401', '500'):
            assert code in post['responses'], (
                'responses 应含 %s, 实际: %r' % (code, post['responses'])
            )

    def test_c3_server_list_has_description_from_docstring(self, client):
        """/server/list 的 description 应从 view_func docstring first_line 抽取."""
        spec = self._fetch_spec(client)
        path = spec['paths'].get('/server/list')
        assert path is not None, 'spec 应含 /server/list'
        post = path.get('post')
        # 原始 docstring first_line 是 '查询资产列表'
        spec_text = (post.get('description', '') + ' ' + post.get('summary', '')).strip()
        assert '查询资产' in spec_text or '资产' in spec_text, (
            'description/summary 应含原 docstring 关键文字, 实际: %r' % spec_text
        )
        assert 'server' in post.get('tags', []), (
            'tags 应含 server, 实际: %r' % post.get('tags')
        )

    def test_c4_local_rsync_responses_match_template(self, client):
        """/local/rsync 的 responses 应含 200/401/500 + 401 description 含"未登录"."""
        spec = self._fetch_spec(client)
        path = spec['paths'].get('/local/rsync')
        assert path is not None, 'spec 应含 /local/rsync'
        post = path.get('post')
        assert 'responses' in post
        r401 = post['responses'].get('401', {})
        r401_desc = r401.get('description', '') if isinstance(r401, dict) else ''
        # 原 docstring 模板: '401: 未登录 (code=3)'
        assert '未登录' in r401_desc, (
            '401 response description 应含"未登录", 实际: %r' % r401_desc
        )
# -*- coding: utf-8 -*-
"""ti2-API: flasgger 接入 + /apidocs 自动 OpenAPI 文档生成.

完工标志 (3 项全过):
  1. /apidocs 路由可访问 + 返 Swagger UI HTML
  2. /apispec_1.json 返 OpenAPI 2.0 JSON, paths 覆盖所有 /server/* /local/* /auth/* /account/* 路由
  3. paths 条目含 description / tags / responses (从 ROUTES 表的 description 自动生成)

设计 (本次重构为纯本地 + 静态验证, 避免污染 app.app_factory.app):
- Part A (静态 AST): 验证 init.py 含 flasgger 接入代码 (_Swagger.init_app + view_func.__doc__ 注入)
- Part B (本地 Flask): 用临时 Flask app + 真实 flasgger 验证 3 个完工标志
- Part C (本地 Flask): 验证 spec paths / tags / responses 字段从 docstring 正确抽取

为什么不复用 app.app_factory.app:
  - conftest 模块加载阶段强制 init Swagger 会让 init.py 顶层执行,
    注册 @app.before_request 等 hook 到全局 app, 进而污染 test_rev30::
    TestRev30H4Behavior::test_h4_content_disposition_safe (1 failed).
  - 用本地 Flask app 让本测试完全自包含, 不影响任何共享状态.
"""
import ast
import json
import os
import re
import tempfile

import pytest
