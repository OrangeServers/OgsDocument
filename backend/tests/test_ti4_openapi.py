# -*- coding: utf-8 -*-
"""ti4-OPENAPI: OpenAPI 3.0 规范导出 (flasgger 升级).

完工标志 (5 项全过):
  1. /openapi.json 路由可访问, 返 OpenAPI 3.0.x JSON 规范
  2. /openapi.yaml 路由可访问, 返 OpenAPI 3.0.x YAML 规范
  3. 3.0 spec 含 openapi=3.0.3 + info + servers + paths + components
  4. 2.0→3.0 转换层 (app.tools.openapi3.convert_swagger2_to_openapi3) 正确处理
     关键映射: servers / components.schemas / components.securitySchemes /
     requestBody (body/formData) / responses.content (含 schema)
  5. /apispec_1.json (2.0) 兼容性保持, 不破坏 ti2-API 既有测试

设计 (本地 Flask + 静态 AST 验证, 不污染 app.app_factory.app):
- Part A (10 tests): 静态验证 init.py 含 /openapi.json + /openapi.yaml 接入
- Part B (12 tests): 验证 openapi3.py 转换器单元行为 (servers/components/requestBody/responses)
- Part C (8 tests): 端到端, 用本地 Flask app + flasgger 验证 3.0 spec 完整 + 2.0 兼容

为什么不复用 app.app_factory.app:
  - conftest 模块加载阶段强制 init Swagger 会让 init.py 顶层执行,
    注册 @app.before_request 等 hook 到全局 app, 进而污染 test_rev30::    .
  - 用本地 Flask app 让本测试完全自包含, 不影响任何共享状态.
"""
import ast
import importlib
import os

import pytest


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT_PY = os.path.join(BACKEND_DIR, 'init.py')
APP_TOOLS_DIR = os.path.join(BACKEND_DIR, 'app', 'tools')


# =============================================================================
# Part A: 静态验证 init.py 含 /openapi.json + /openapi.yaml 接入 (10 tests)
# =============================================================================
class TestInitPyStatic:
    """静态验证 init.py 含 ti4-OPENAPI 接入代码."""

    @staticmethod
    def _load_source():
        with open(INIT_PY, 'r', encoding='utf-8') as f:
            return f.read()

    def test_a1_openapi3_json_view_func_defined(self):
        """init.py 应含 _openapi3_json view_func 定义."""
        source = self._load_source()
        assert 'def _openapi3_json' in source, (
            'init.py 应定义 _openapi3_json view_func (ti4-OPENAPI)'
        )

    def test_a2_openapi3_yaml_view_func_defined(self):
        """init.py 应含 _openapi3_yaml view_func 定义."""
        source = self._load_source()
        assert 'def _openapi3_yaml' in source, (
            'init.py 应定义 _openapi3_yaml view_func (ti4-OPENAPI)'
        )

    def test_a3_route_openapi_json_registered(self):
        """init.py 应调用 add_url_rule 注册 /openapi.json."""
        source = self._load_source()
        # 检查 /openapi.json 出现在 add_url_rule 调用里
        assert "'/openapi.json'" in source or '"/openapi.json"' in source, (
            'init.py 应注册 /openapi.json 路由 (ti4-OPENAPI)'
        )
        # 进一步验证在 add_url_rule 调用里
        assert "add_url_rule('/openapi.json'" in source or 'add_url_rule("/openapi.json"' in source, (
            '/openapi.json 应通过 add_url_rule 注册, 不应误用 @app.route'
        )

    def test_a4_route_openapi_yaml_registered(self):
        """init.py 应调用 add_url_rule 注册 /openapi.yaml."""
        source = self._load_source()
        assert "add_url_rule('/openapi.yaml'" in source or 'add_url_rule("/openapi.yaml"' in source, (
            'init.py 应通过 add_url_rule 注册 /openapi.yaml (ti4-OPENAPI)'
        )

    def test_a5_imports_openapi3_converter(self):
        """init.py 应 from app.tools.openapi3 import convert_swagger2_to_openapi3."""
        source = self._load_source()
        assert 'from app.tools.openapi3 import convert_swagger2_to_openapi3' in source, (
            'init.py 应 import convert_swagger2_to_openapi3 (ti4-OPENAPI 转换层)'
        )

    def test_a6_log_openapi3_enabled(self):
        """init.py 应输出 [ti4-OPENAPI] 启动日志."""
        source = self._load_source()
        assert '[ti4-OPENAPI]' in source, (
            'init.py 应输出 [ti4-OPENAPI] 日志 (便于诊断 OpenAPI 端点是否启用)'
        )
        assert 'OpenAPI 3.0 spec enabled' in source, (
            'init.py 应在 init 成功时打 "OpenAPI 3.0 spec enabled" 标志'
        )

    def test_a7_routes_use_get_only(self):
        """/openapi.json 与 /openapi.yaml 路由 methods=['GET'] (无 csrf 副作用)."""
        source = self._load_source()
        # 验证两个路由都明确 methods=['GET']
        assert "add_url_rule('/openapi.json', view_func=_openapi3_json, methods=['GET'])" in source, (
            '/openapi.json 应 methods=["GET"] (ti4-OPENAPI 公开端点, 不可 POST 触发副作用)'
        )
        assert "add_url_rule('/openapi.yaml', view_func=_openapi3_yaml, methods=['GET'])" in source, (
            '/openapi.yaml 应 methods=["GET"]'
        )

    def test_a8_uses_sweg_get_apispecs(self):
        """_openapi3_json/yaml 应调 _swag.get_apispecs() 拿 2.0 spec (无参, 依赖 current_app)."""
        source = self._load_source()
        # 期望无参调用 (flasgger 0.9.7.1 get_apispecs 默认 endpoint='apispec_1',
        # 在视图函数上下文内, current_app 自动注入, 无需传 app)
        assert '_swag.get_apispecs()' in source, (
            'init.py 应调 _swag.get_apispecs() 拿 flasgger 内部 spec (ti4-OPENAPI)'
        )
        # 反向断言: 不应误传 Flask app 对象 (flasgger 0.9.7.1 端点参数是字符串)
        assert '_swag.get_apispecs(app)' not in source, (
            'init.py 不应传 Flask app 对象给 get_apispecs (其 endpoint 参数是字符串, '
            '传 app 会导致 RuntimeError: Can`t find specs by endpoint <Flask ...>)'
        )

    def test_a9_uses_json_and_yaml_dump(self):
        """_openapi3_json 用 json.dumps, _openapi3_yaml 用 yaml.safe_dump."""
        source = self._load_source()
        assert 'json.dumps' in source, '_openapi3_json 应调 json.dumps'
        assert 'yaml.safe_dump' in source, '_openapi3_yaml 应调 yaml.safe_dump'
        # YAML 需 allow_unicode=True 保中文 (业务接口含中文)
        assert 'allow_unicode=True' in source, (
            'yaml.safe_dump 应传 allow_unicode=True (业务 description 含中文, 防 \\uXXXX 转义)'
        )

    def test_a10_routes_after_sweg_init(self):
        """/openapi.json + /openapi.yaml 注册必须发生在 _swag.init_app(app) 之后."""
        source = self._load_source()
        # 用文本扫描验证顺序 (允许中间有其他代码, 但 init_app 必须在 add_url_rule 之前)
        pos_init_app = source.find('_swag.init_app(app)')
        pos_openapi_json = source.find("add_url_rule('/openapi.json'")
        pos_openapi_yaml = source.find("add_url_rule('/openapi.yaml'")
        assert pos_init_app > 0, 'init.py 应调 _swag.init_app(app)'
        assert pos_openapi_json > pos_init_app, (
            '/openapi.json 路由必须在 _swag.init_app(app) 之后注册 '
            '(init_app 初始化 spec 收集机制, 之前注册路由拿不到 spec)'
        )
        assert pos_openapi_yaml > pos_init_app, (
            '/openapi.yaml 路由必须在 _swag.init_app(app) 之后注册'
        )


# =============================================================================
# Part B: openapi3.py 转换器单元行为 (12 tests)
# =============================================================================
class TestOpenapi3Converter:
    """验证 openapi3.py 转换器 (2.0→3.0) 关键映射."""

    @staticmethod
    def _load_converter():
        """从 app.tools.openapi3 动态 import 转换函数 (不依赖 flasgger)."""
        from app.tools.openapi3 import convert_swagger2_to_openapi3
        return convert_swagger2_to_openapi3

    def test_b1_basic_fields_present(self):
        """转换后 spec 应含 openapi=3.0.3 + info + servers + paths."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'Test API', 'version': '1.0.0'},
            'paths': {},
        }
        spec3 = convert(spec2)
        assert spec3.get('openapi') == '3.0.3', (
            'openapi 字段应等于 3.0.3, 实际: %r' % spec3.get('openapi')
        )
        assert 'info' in spec3, '3.0 spec 应保留 info 字段'
        assert 'servers' in spec3, '3.0 spec 应含 servers 字段 (从 host+basePath+schemes 派生)'
        assert 'paths' in spec3, '3.0 spec 应含 paths 字段'

    def test_b2_servers_from_host_basepath_schemes(self):
        """servers 列表应从 host + basePath + schemes 派生."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'host': 'api.example.com',
            'basePath': '/v1',
            'schemes': ['https', 'http'],
            'info': {'title': 'T', 'version': '1.0.0'},
            'paths': {},
        }
        spec3 = convert(spec2)
        servers = spec3['servers']
        assert isinstance(servers, list), 'servers 应是 list, 实际: %r' % type(servers)
        urls = [s['url'] for s in servers]
        assert 'https://api.example.com/v1' in urls, (
            'servers[0] 应为 https://api.example.com/v1, 实际: %r' % urls
        )
        assert 'http://api.example.com/v1' in urls, (
            'servers[1] 应为 http://api.example.com/v1, 实际: %r' % urls
        )

    def test_b3_responses_description_kept(self):
        """responses.{code}.description 转换后保持 (无 schema 时)."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'paths': {
                '/x': {
                    'post': {
                        'tags': ['test'],
                        'responses': {
                            '200': {'description': 'OK'},
                            '401': {'description': 'Unauthorized'},
                        }
                    }
                }
            }
        }
        spec3 = convert(spec2)
        post = spec3['paths']['/x']['post']
        assert post['responses']['200']['description'] == 'OK', (
            '200 response description 应保持, 实际: %r' % post['responses']
        )
        assert post['responses']['401']['description'] == 'Unauthorized', (
            '401 response description 应保持'
        )

    def test_b4_responses_with_schema_to_content(self):
        """responses.{code}.schema → 3.0 responses.{code}.content.application/json.schema."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'paths': {
                '/x': {
                    'get': {
                        'responses': {
                            '200': {
                                'description': 'OK',
                                'schema': {'$ref': '#/definitions/User'},
                            }
                        }
                    }
                }
            }
        }
        spec3 = convert(spec2)
        r200 = spec3['paths']['/x']['get']['responses']['200']
        assert 'content' in r200, '含 schema 的 response 应转 content, 实际: %r' % r200
        assert 'application/json' in r200['content'], (
            'content 应含 application/json, 实际 keys: %r' % list(r200['content'].keys())
        )
        schema = r200['content']['application/json']['schema']
        assert schema == {'$ref': '#/components/schemas/User'}, (
            'schema 应原样保留, 实际: %r' % schema
        )

    def test_b5_body_param_to_request_body(self):
        """parameters[?in=body] 应转 requestBody.content.application/json.schema."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'paths': {
                '/x': {
                    'post': {
                        'parameters': [
                            {'name': 'body', 'in': 'body', 'required': True,
                             'schema': {'type': 'object', 'properties': {'name': {'type': 'string'}}}}
                        ],
                        'responses': {'200': {'description': 'OK'}}
                    }
                }
            }
        }
        spec3 = convert(spec2)
        post = spec3['paths']['/x']['post']
        assert 'requestBody' in post, 'body param 应转 requestBody, 实际: %r' % post
        assert 'parameters' not in post, 'body param 转出后, parameters 列表应清空'
        rb = post['requestBody']
        assert rb.get('required') is True, 'required=True 应传递到 3.0 requestBody'
        schema = rb['content']['application/json']['schema']
        assert schema['type'] == 'object', 'schema.type 应保持 object'
        assert 'name' in schema['properties'], 'schema.properties 应含 name'

    def test_b6_formdata_param_to_urlencoded_request_body(self):
        """parameters[?in=formData] 应转 requestBody.content.application/x-www-form-urlencoded.schema."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'paths': {
                '/upload': {
                    'post': {
                        'parameters': [
                            {'name': 'file', 'in': 'formData', 'type': 'file', 'required': True},
                            {'name': 'desc', 'in': 'formData', 'type': 'string'},
                        ],
                        'responses': {'200': {'description': 'OK'}}
                    }
                }
            }
        }
        spec3 = convert(spec2)
        path_item = spec3['paths']['/upload']
        op = path_item['post']
        rb = op['requestBody']
        assert 'application/x-www-form-urlencoded' in rb['content'], (
            'formData 应转 application/x-www-form-urlencoded, 实际: %r' % rb['content']
        )
        schema = rb['content']['application/x-www-form-urlencoded']['schema']
        assert 'file' in schema['properties'], 'schema 应含 file 字段'
        assert 'desc' in schema['properties'], 'schema 应含 desc 字段'
        assert 'file' in schema['required'], 'file 标 required=True 应传到 schema.required'

    def test_b7_definitions_to_components_schemas(self):
        """2.0 definitions 应转 3.0 components.schemas."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'definitions': {
                'User': {'type': 'object', 'properties': {'id': {'type': 'integer'}}},
                'Order': {'type': 'object'},
            },
            'paths': {},
        }
        spec3 = convert(spec2)
        assert 'components' in spec3, 'definitions 存在时, 应生成 components 字段'
        schemas = spec3['components'].get('schemas', {})
        assert 'User' in schemas, 'components.schemas 应含 User'
        assert 'Order' in schemas, 'components.schemas 应含 Order'
        assert schemas['User']['type'] == 'object', 'schema 内容应原样保留'

    def test_b8_security_definitions_to_components_security_schemes(self):
        """2.0 securityDefinitions 应转 3.0 components.securitySchemes."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'securityDefinitions': {
                'ApiKeyAuth': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'},
            },
            'paths': {},
        }
        spec3 = convert(spec2)
        assert 'components' in spec3
        schemes = spec3['components'].get('securitySchemes', {})
        assert 'ApiKeyAuth' in schemes, 'components.securitySchemes 应含 ApiKeyAuth'
        assert schemes['ApiKeyAuth']['type'] == 'apiKey', 'securityScheme 内容应原样保留'

    def test_b9_top_level_security_and_tags_kept(self):
        """2.0 顶层 security / tags 字段应直接保留 (3.0 兼容)."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'security': [{'ApiKeyAuth': []}],
            'tags': [{'name': 'user', 'description': '用户相关'}],
            'paths': {},
        }
        spec3 = convert(spec2)
        assert 'security' in spec3, '顶层 security 应保留'
        assert spec3['security'] == [{'ApiKeyAuth': []}], 'security 内容应一致'
        assert 'tags' in spec3, '顶层 tags 应保留'
        assert spec3['tags'][0]['name'] == 'user', 'tags 内容应一致'

    def test_b10_consumes_produces_removed(self):
        """2.0 consumes/produces 在 3.0 已废弃, 转换后应删除."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'paths': {
                '/x': {
                    'post': {
                        'consumes': ['application/json'],
                        'produces': ['application/json'],
                        'responses': {'200': {'description': 'OK'}}
                    }
                }
            }
        }
        spec3 = convert(spec2)
        post = spec3['paths']['/x']['post']
        assert 'consumes' not in post, '3.0 不应保留 consumes (3.0 用 requestBody.content)'
        assert 'produces' not in post, '3.0 不应保留 produces (3.0 用 responses.content)'

    def test_b11_input_not_mutated(self):
        """转换函数不应修改输入 spec2 (深拷贝隔离)."""
        convert = self._load_converter()
        spec2 = {
            'swagger': '2.0',
            'info': {'title': 'T', 'version': '1.0.0'},
            'paths': {'/x': {'get': {'responses': {'200': {'description': 'OK'}}}}},
        }
        spec2_snapshot = {
            'swagger': spec2['swagger'],
            'info': dict(spec2['info']),
            'paths': {k: {k2: dict(v2) for k2, v2 in v.items()}
                      for k, v in spec2['paths'].items()},
        }
        convert(spec2)
        # 验证 spec2 没被改
        assert spec2 == spec2_snapshot, (
            'convert_swagger2_to_openapi3 不应修改输入, 实际: %r' % spec2
        )

    def test_b12_invalid_input_raises(self):
        """输入非 dict 时应抛 TypeError (防御性)."""
        convert = self._load_converter()
        with pytest.raises(TypeError):
            convert('not a dict')  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            convert(None)  # type: ignore[arg-type]


# =============================================================================
# Part C: 端到端, 用本地 Flask + flasgger 验证 3.0 spec 完整 + 2.0 兼容 (8 tests)
# =============================================================================
class TestEndToEndOpenAPI3:
    """用本地 Flask + flasgger 端到端验证 /openapi.json + /openapi.yaml 端点."""

    @pytest.fixture(scope='class')
    def local_app(self):
        from flask import Flask
        from flasgger import Swagger

        app = Flask('ti4_openapi_test_local')
        # 用与 OrangeServer 真实 app_factory 相同的 2.0 template
        swag = Swagger(app, template={
            'swagger': '2.0',
            'info': {
                'title': 'OrangeServer API',
                'version': '1.0.0',
            },
            'basePath': '/',
            'schemes': ['http', 'https'],
        })

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
                '    description: 成功响应\n'
                '  401:\n'
                '    description: 未登录\n'
            ) % (summary, tag)
            view_func.__name__ = url.strip('/').replace('/', '_') or 'root'
            app.add_url_rule(url, endpoint=view_func.__name__,
                             view_func=view_func, methods=['POST'])
            return view_func

        # 仿业务 4 大模块, 注入与 OrangeServer 一致的 docstring 模板
        _make_view('/account/login_dl2', '用户登录', 'account')
        _make_view('/auth/host/list', '查询资产授权', 'auth')
        _make_view('/server/list', '查询资产', 'server')
        _make_view('/local/file', '文件上传', 'local')

        # 注册 /openapi.json + /openapi.yaml (仿 init.py ti4-OPENAPI 段)
        from app.tools.openapi3 import convert_swagger2_to_openapi3
        import json as _json
        import yaml as _yaml

        def _openapi3_json():
            # view_func 内部 Flask 已 push app context, 可直接调
            # flasgger 0.9.7.1 get_apispecs() 直接返 dict (非 list)
            spec2 = swag.get_apispecs()
            spec3 = convert_swagger2_to_openapi3(spec2)
            return app.response_class(
                response=_json.dumps(spec3, ensure_ascii=False, sort_keys=True),
                status=200, mimetype='application/json',
            )

        def _openapi3_yaml():
            spec2 = swag.get_apispecs()
            spec3 = convert_swagger2_to_openapi3(spec2)
            return app.response_class(
                response=_yaml.safe_dump(spec3, allow_unicode=True, sort_keys=True),
                status=200, mimetype='application/yaml',
            )

        app.add_url_rule('/openapi.json', view_func=_openapi3_json, methods=['GET'])
        app.add_url_rule('/openapi.yaml', view_func=_openapi3_yaml, methods=['GET'])
        yield app

    @pytest.fixture
    def client(self, local_app):
        return local_app.test_client()

    def test_c1_openapi_json_route_registered(self, local_app):
        """/openapi.json 路由应被注册."""
        rules = [r.rule for r in local_app.url_map.iter_rules()]
        assert '/openapi.json' in rules, (
            '/openapi.json 路由应被 add_url_rule 注册, 实际: %r' % rules
        )

    def test_c2_openapi_yaml_route_registered(self, local_app):
        """/openapi.yaml 路由应被注册."""
        rules = [r.rule for r in local_app.url_map.iter_rules()]
        assert '/openapi.yaml' in rules, (
            '/openapi.yaml 路由应被 add_url_rule 注册, 实际: %r' % rules
        )

    def test_c3_openapi_json_returns_openapi_3(self, client):
        """GET /openapi.json 应返 200 + JSON + openapi=3.0.3."""
        import json
        resp = client.get('/openapi.json')
        assert resp.status_code == 200, 'GET /openapi.json 应返 200, 实际 %d' % resp.status_code
        ct = resp.headers.get('Content-Type', '')
        assert 'json' in ct.lower(), 'Content-Type 应含 json, 实际: %r' % ct
        spec = json.loads(resp.get_data(as_text=True))
        assert spec.get('openapi') == '3.0.3', (
            'openapi 字段应等于 3.0.3, 实际: %r' % spec.get('openapi')
        )
        assert 'info' in spec, '3.0 spec 应含 info'
        assert 'servers' in spec, '3.0 spec 应含 servers'
        assert 'paths' in spec, '3.0 spec 应含 paths'
        assert spec['info']['title'] == 'OrangeServer API', 'info.title 应保持'

    def test_c4_openapi_yaml_returns_openapi_3(self, client):
        """GET /openapi.yaml 应返 200 + YAML + openapi=3.0.3."""
        import yaml
        resp = client.get('/openapi.yaml')
        assert resp.status_code == 200, 'GET /openapi.yaml 应返 200, 实际 %d' % resp.status_code
        ct = resp.headers.get('Content-Type', '')
        assert 'yaml' in ct.lower(), 'Content-Type 应含 yaml, 实际: %r' % ct
        spec = yaml.safe_load(resp.get_data(as_text=True))
        assert spec.get('openapi') == '3.0.3', (
            'YAML 端点也应返 openapi=3.0.3, 实际: %r' % spec.get('openapi')
        )
        assert 'paths' in spec

    def test_c5_paths_cover_all_business_modules(self, client):
        """3.0 spec paths 应覆盖 OrangeServer 4 大业务模块 (account/auth/server/local)."""
        import json
        spec = json.loads(client.get('/openapi.json').get_data(as_text=True))
        paths = list(spec['paths'].keys())
        for prefix in ('/account/', '/auth/', '/server/', '/local/'):
            assert any(p.startswith(prefix) for p in paths), (
                '3.0 spec paths 应含 %s*, 实际: %r' % (prefix, paths)
            )

    def test_c6_components_field_present(self, client):
        """3.0 spec 应含 components 字段 (即便为空 dict, 表示支持扩展)."""
        import json
        spec = json.loads(client.get('/openapi.json').get_data(as_text=True))
        assert 'components' in spec, (
            '3.0 spec 应含 components 字段 (OrangeServer 业务无 definitions/'
            'securityDefinitions 时, 仍保留空 dict 表示支持扩展)'
        )
        assert isinstance(spec['components'], dict), 'components 应是 dict'

    def test_c7_servers_array_present(self, client):
        """3.0 spec servers 数组应非空 (OrangeServer 业务无 host, 产相对 URL)."""
        import json
        spec = json.loads(client.get('/openapi.json').get_data(as_text=True))
        servers = spec.get('servers', [])
        assert isinstance(servers, list), 'servers 应是 list'
        assert len(servers) >= 1, 'servers 至少应含 1 项, 实际: %r' % servers
        # OrangeServer template 未设 host, 业务用 Nginx 反代, 转换器应产相对 URL (RFC 3986)
        # 相对 URL 不写 scheme/host, 客户端按当前 base 解析
        urls = [s.get('url', '') for s in servers]
        # 期望: 至少有一条 URL 以 '/' 开头 (相对路径)
        assert any(u.startswith('/') for u in urls), (
            'OrangeServer 业务无 host, servers 应含相对 URL (以 / 开头), 实际: %r' % urls
        )

    def test_c8_apispec_1_json_still_swagger_2(self, local_app, client):
        """/apispec_1.json 仍应返 Swagger 2.0 (ti2-API 兼容性保持)."""
        # 验证 /apispec_1.json 路由仍由 flasgger 注册, 输出 2.0
        rules = [r.rule for r in local_app.url_map.iter_rules()]
        assert '/apispec_1.json' in rules, (
            'flasgger 应仍注册 /apispec_1.json (ti2-API 兼容), 实际: %r' % rules
        )
        # 本地 flasgger 实例不通过 swag.template 注入 basePath+schemes 时,
        # 输出 spec 可能是 2.0 但结构略有不同. 这里只验证字段 swagger 存在.
        resp = client.get('/apispec_1.json')
        assert resp.status_code == 200
        spec = resp.get_json()
        assert spec.get('swagger') == '2.0', (
            'ti2-API 兼容性: /apispec_1.json 应仍返 Swagger 2.0, 实际: %r' % spec.get('swagger')
        )


# =============================================================================
# Part D: 工具模块本身存在性 + 可导入 (2 tests)
# =============================================================================
class TestOpenapi3ModuleExists:
    """验证 app.tools.openapi3 模块可被导入 + 关键 API 暴露."""

    def test_d1_module_importable(self):
        """app.tools.openapi3 模块应可被 import."""
        spec = importlib.util.find_spec('app.tools.openapi3')
        assert spec is not None, 'app.tools.openapi3 模块应存在 (ti4-OPENAPI 转换层)'

    def test_d2_module_apis_exposed(self):
        """openapi3 模块应暴露 convert_swagger2_to_openapi3 / is_openapi3 / is_swagger2."""
        from app.tools import openapi3
        for api_name in ('convert_swagger2_to_openapi3', 'is_openapi3', 'is_swagger2'):
            assert hasattr(openapi3, api_name), (
                'app.tools.openapi3 应暴露 %s API' % api_name
            )
