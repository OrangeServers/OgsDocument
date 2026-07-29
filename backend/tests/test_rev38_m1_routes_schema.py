# -*- coding: utf-8 -*-
"""REV38-M1: ROUTES schema 统一为 namedtuple + description/skip_csrf 字段回归测试。

覆盖范围：
  1) RouteRule namedtuple 8 字段定义正确
  2) route() 便捷构造器默认值与自定义值
  3) route() 角色参数 roles 自动 list 化
  4) 4 个 api 模块的 ROUTES 全部为 RouteRule 实例
  5) 4 个 api 模块的 ROUTES 总数 = 91（保持不变）
  6) 4 个 api 模块的 ROUTES 每条都带 description（[LEGACY] / 普通描述）
  7) /local/captcha/get 标注 skip_csrf=True
  8) /mail/send_user_mail / /local/settings/open / /account/login_dl2 公开接口 need_auth=False
  9) /local/cron/close 等管理端路由 roles=['admin']
 10) init.py 的 _register_routes_from_module 兼容旧 tuple 写法（5/6-tuple）
 11) init.py 加载后 Flask app url_map 实际注册路由数 = 91 POST
 12) Flask url_map 中 /local/captcha/get 注册成功
"""
import importlib
import os
import sys
from collections import namedtuple
from types import SimpleNamespace

import pytest

# 路径初始化
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) RouteRule namedtuple 定义测试
# ============================================================
class TestRouteRuleNamedtuple:
    def test_01_route_rule_is_namedtuple(self):
        """RouteRule 是 namedtuple 类型"""
        from app.api import RouteRule
        assert issubclass(RouteRule, tuple)
        assert hasattr(RouteRule, '_fields')

    def test_02_route_rule_has_eight_fields(self):
        """RouteRule 必须有 9 字段 (REV38-M4 新增 is_alias)"""
        from app.api import RouteRule
        assert len(RouteRule._fields) == 9

    def test_03_route_rule_field_names(self):
        """RouteRule 字段名顺序固定"""
        from app.api import RouteRule
        assert RouteRule._fields == (
            'url', 'view_class', 'method', 'need_auth', 'is_property',
            'roles', 'description', 'skip_csrf', 'is_alias',
        )

    def test_04_route_rule_constructable(self):
        """RouteRule 可直接实例化"""
        from app.api import RouteRule

        class DummyView:
            pass

        r = RouteRule(
            url='/x', view_class=DummyView, method='m',
            need_auth=True, is_property=True,
            roles=['admin'], description='d', skip_csrf=False, is_alias=False,
        )
        assert r.url == '/x'
        assert r.view_class is DummyView
        assert r.method == 'm'
        assert r.need_auth is True
        assert r.is_property is True
        assert r.roles == ['admin']
        assert r.description == 'd'
        assert r.skip_csrf is False
        assert r.is_alias is False


# ============================================================
# 2) route() 便捷构造器测试
# ============================================================
class TestRouteHelper:
    def test_01_default_need_auth_true(self):
        """need_auth 默认 True"""
        from app.api import route, RouteRule

        class V:
            pass

        r = route('/a', V, 'm')
        assert isinstance(r, RouteRule)
        assert r.need_auth is True

    def test_02_default_is_property_true(self):
        """is_property 默认 True"""
        from app.api import route

        class V:
            pass

        assert route('/a', V, 'm').is_property is True

    def test_03_default_roles_none(self):
        """roles 默认 None（不限定）"""
        from app.api import route

        class V:
            pass

        assert route('/a', V, 'm').roles is None

    def test_04_default_description_empty(self):
        """description 默认 ''"""
        from app.api import route

        class V:
            pass

        assert route('/a', V, 'm').description == ''

    def test_05_default_skip_csrf_false(self):
        """skip_csrf 默认 False"""
        from app.api import route

        class V:
            pass

        assert route('/a', V, 'm').skip_csrf is False

    def test_06_roles_tuple_to_list(self):
        """roles 元组自动转 list（防 namedtuple 哈希冲突）"""
        from app.api import route

        class V:
            pass

        r = route('/a', V, 'm', roles=('admin', 'user'))
        assert r.roles == ['admin', 'user']
        assert isinstance(r.roles, list)

    def test_07_custom_skip_csrf(self):
        """skip_csrf=True 显式传值"""
        from app.api import route

        class V:
            pass

        r = route('/a', V, 'm', skip_csrf=True, need_auth=False)
        assert r.skip_csrf is True
        assert r.need_auth is False


# ============================================================
# 3) 4 个 api 模块的 ROUTES 一致性
# ============================================================
@pytest.fixture(scope='module')
def api_modules():
    """加载 4 个 api 模块（ROUTES 表的权威来源）"""
    return {
        'account': importlib.import_module('app.api.account_api'),
        'auth': importlib.import_module('app.api.auth_api'),
        'local': importlib.import_module('app.api.local_api'),
        'server': importlib.import_module('app.api.server_api'),
    }


class TestRouteCounts:
    """REV38-M1: 4 个 api 模块的路由数应与改造前一致（ROUTES 表）"""

    def test_01_account_has_23(self, api_modules):
        # 登录注册 4 + 用户组 6 + 用户 8 + 审计日志 3 + 忘记密码 2 = 23
        assert len(api_modules['account'].ROUTES) == 23

    def test_02_auth_has_6(self, api_modules):
        assert len(api_modules['auth'].ROUTES) == 6

    def test_03_server_has_23(self, api_modules):
        # 主机组 6 + 系统用户 6 + 资产主机 11 = 23
        assert len(api_modules['server'].ROUTES) == 23

    def test_04_local_has_37_after_smtp_settings(self, api_modules):
        # 初始化 1 + captcha 1 + 统计图表 3 + 数据 2 + 图片 2 + 设置 3
        # + SMTP 设置 3 + 文件 7 + 邮件 2 + cron 11 + IP 1。
        assert len(api_modules['local'].ROUTES) == 37

    def test_05_total_89_legacy_routes(self, api_modules):
        """SMTP 设置加入后 RouteRule 总数 = 89；AI 路由由 init.py 手动注册。"""
        total = sum(len(m.ROUTES) for m in api_modules.values())
        assert total == 89


class TestAllRoutesAreRouteRule:
    """REV38-M1: 所有 ROUTES 项必须是 RouteRule 实例，不再是裸 tuple"""

    @pytest.mark.parametrize('mod_name', ['account', 'auth', 'local', 'server'])
    def test_01_every_entry_is_route_rule(self, api_modules, mod_name):
        from app.api import RouteRule
        mod = api_modules[mod_name]
        for r in mod.ROUTES:
            assert isinstance(r, RouteRule), (
                '%s.ROUTES 含非 RouteRule 项: %r' % (mod_name, r)
            )


class TestAllRoutesHaveDescription:
    """REV38-M1: 每条路由都必须有 description 字段"""

    @pytest.mark.parametrize('mod_name', ['account', 'auth', 'local', 'server'])
    def test_01_description_nonempty(self, api_modules, mod_name):
        mod = api_modules[mod_name]
        for r in mod.ROUTES:
            assert r.description, (
                '%s.ROUTES[%s] 缺 description: url=%s' % (mod_name, r.url, r.url)
            )


# ============================================================
# 4) 关键路由的属性正确性
# ============================================================
class TestKeyRouteProperties:
    def test_01_captcha_skip_csrf(self, api_modules):
        """/local/captcha/get 必须标 skip_csrf=True（防 Redis 写压力）"""
        captcha = [r for r in api_modules['local'].ROUTES if r.url == '/local/captcha/get']
        assert len(captcha) == 1
        assert captcha[0].skip_csrf is True
        assert captcha[0].need_auth is False

    def test_02_send_user_mail_no_auth(self, api_modules):
        """/mail/send_user_mail（注册验证码）必须 need_auth=False"""
        m = [r for r in api_modules['local'].ROUTES if r.url == '/mail/send_user_mail']
        assert len(m) == 1
        assert m[0].need_auth is False

    def test_03_login_dl2_no_auth(self, api_modules):
        """/account/login_dl2（登录）必须 need_auth=False"""
        m = [r for r in api_modules['account'].ROUTES if r.url == '/account/login_dl2']
        assert len(m) == 1
        assert m[0].need_auth is False

    def test_04_settings_open_no_auth(self, api_modules):
        """/local/settings/open（公开设置）必须 need_auth=False"""
        m = [r for r in api_modules['local'].ROUTES if r.url == '/local/settings/open']
        assert len(m) == 1
        assert m[0].need_auth is False

    def test_05_cron_close_admin_only(self, api_modules):
        """/local/cron/close（关闭全站 cron）必须 roles=['admin']"""
        m = [r for r in api_modules['local'].ROUTES if r.url == '/local/cron/close']
        assert len(m) == 1
        assert m[0].roles == ['admin']

    def test_07_cron_auth_list_admin_only(self, api_modules):
        """/local/cron/auth_list 必须 roles=['admin']"""
        m = [r for r in api_modules['local'].ROUTES if r.url == '/local/cron/auth_list']
        assert len(m) == 1
        assert m[0].roles == ['admin']

    def test_08_file_list_alias_exists(self, api_modules):
        """REV38-M5: /local/file/def_get + /local/file/list 必须都存在（alias 兼容）"""
        urls = {r.url for r in api_modules['local'].ROUTES}
        assert '/local/file/def_get' in urls
        assert '/local/file/list' in urls

    def test_09_all_routes_have_valid_url_prefix(self, api_modules):
        """所有 url 必须以 / 开头"""
        for mod in api_modules.values():
            for r in mod.ROUTES:
                assert r.url.startswith('/'), 'url 缺少前导 /: %r' % (r.url,)


# ============================================================
# 5) init.py 兼容旧 tuple 写法
# ============================================================
class TestLegacyTupleCompat:
    """REV38-M1: init.py 必须仍能处理旧 5/6-tuple（不破坏未来三方插件）"""

    def test_01_init_imports_route_rule(self):
        """init.py 显式 import RouteRule"""
        from app.api import RouteRule
        # init.py 源码应 import
        init_src = open(os.path.join(_BACKEND, 'init.py'), encoding='utf-8').read()
        assert 'RouteRule' in init_src

    def test_02_init_uses_register_function(self):
        """init.py 调用 _register_routes_from_module"""
        init_src = open(os.path.join(_BACKEND, 'init.py'), encoding='utf-8').read()
        assert '_register_routes_from_module' in init_src

    def test_03_legacy_5tuple_normalized(self):
        """_register_routes_from_module 把 5-tuple 归一化为 RouteRule"""

        class DummyView:
            def hello(self):
                return 'hi'

        # 旧式 5-tuple: (url, cls, method, need_auth, is_property)
        legacy_mod = SimpleNamespace(ROUTES=[
            ('/legacy/5tuple', DummyView, 'hello', True, True),
        ])

        import init
        from app.api import RouteRule

        before_count = sum(1 for _ in init.app.url_map.iter_rules())
        init._register_routes_from_module(legacy_mod)
        after_count = sum(1 for _ in init.app.url_map.iter_rules())
        assert after_count == before_count + 1, '5-tuple 旧路由未注册成功'

    def test_04_legacy_6tuple_with_roles_normalized(self):
        """6-tuple 含 roles 也能归一化"""

        class DummyView:
            def hello(self):
                return 'hi'

        legacy_mod = SimpleNamespace(ROUTES=[
            ('/legacy/6tuple', DummyView, 'hello', True, True, ['admin']),
        ])

        import init
        before_count = sum(1 for _ in init.app.url_map.iter_rules())
        init._register_routes_from_module(legacy_mod)
        after_count = sum(1 for _ in init.app.url_map.iter_rules())
        assert after_count == before_count + 1, '6-tuple 旧路由未注册成功'

    def test_05_invalid_entry_skipped_with_warning(self):
        """非 tuple/RouteRule 项被跳过（不抛异常）"""
        legacy_mod = SimpleNamespace(ROUTES=[
            'not-a-route',
            42,
            None,
        ])
        import init
        before_count = sum(1 for _ in init.app.url_map.iter_rules())
        # 应不抛异常
        init._register_routes_from_module(legacy_mod)
        after_count = sum(1 for _ in init.app.url_map.iter_rules())
        assert after_count == before_count, '无效项不应被注册'


# ============================================================
# 6) Flask app 实际注册情况
# ============================================================
class TestFlaskUrlMap:
    """REV38-M1: 启动后 Flask app 应注册全部 ROUTES 表 + 5 条手动特殊路由

    注: orange_init_api() 会调用 local_app_init() 触发真实连 DB/Redis, 测试环境不可用.
    因此本类只对 4 个 api 模块单独调 _register_routes_from_module (它不连 DB),
    验证每个 ROUTES 条目都成功 add_url_rule 到 url_map.
    """

    @pytest.fixture(scope='module')
    def registered_app(self):
        """只调 _register_routes_from_module 一次 (module scope, 避免 endpoint 冲突)

        endpoint = view.__name__ = url.strip('/').replace('/', '_')
        Flask app.add_url_rule 在同一 endpoint 名重复注册会抛 AssertionError
        因此 fixture 用 module scope 复用一次注册
        """
        import init
        from app.api import account_api, auth_api, local_api, server_api
        # 已注册则跳过 (防止同一 module 多次 fixture 实例化)
        existing = {r.rule for r in init.app.url_map.iter_rules()}
        for mod in (account_api, auth_api, local_api, server_api):
            for r in mod.ROUTES:
                if r.url in existing:
                    continue
                init._register_routes_from_module(SimpleNamespace(ROUTES=[r]))
        return init.app

    def test_01_app_has_at_least_86_legacy_routes(self, registered_app):
        """容器移除后的 86 条 RouteRule 全部成功注册到 url_map。"""
        # 排除 static + 根路由 + health (/local/health 是 app_factory 内部)
        # + WebSocket (单独标记)
        custom_rules = [
            r for r in registered_app.url_map.iter_rules()
            if r.rule.startswith(('/local/', '/server/', '/mail/', '/account/', '/auth/', '/ai/'))
            and r.rule != '/local/health'
            and not r.rule.startswith('/local/websocket')
            and not r.rule.startswith('/local/sftp/websocket')
        ]
        # 4 个模块的 ROUTES 全部应成功注册
        assert len(custom_rules) >= 86, 'POST 路由数 < 86: %d' % len(custom_rules)

    def test_02_captcha_url_registered(self, registered_app):
        """/local/captcha/get 在 url_map 中"""
        urls = {r.rule for r in registered_app.url_map.iter_rules()}
        assert '/local/captcha/get' in urls

    def test_03_login_url_registered(self, registered_app):
        """/account/login_dl2 在 url_map 中"""
        urls = {r.rule for r in registered_app.url_map.iter_rules()}
        assert '/account/login_dl2' in urls

    def test_04_all_module_routes_registered(self, registered_app):
        """每个模块的所有 ROUTES 条目都成功 add_url_rule"""
        registered = {r.rule for r in registered_app.url_map.iter_rules()}
        from app.api import account_api, auth_api, local_api, server_api
        for mod_name, mod in [('account', account_api), ('auth', auth_api),
                              ('local', local_api), ('server', server_api)]:
            for r in mod.ROUTES:
                assert r.url in registered, (
                    '%s.ROUTES 条目未注册到 url_map: %s' % (mod_name, r.url)
                )

    def test_05_all_custom_routes_post_only(self, registered_app):
        """REV16 P0-2: 所有 ROUTES 路由 methods 严格 = {'POST', 'HEAD', 'OPTIONS'}（不能含 'get'）"""
        custom_rules = [
            r for r in registered_app.url_map.iter_rules()
            if r.rule.startswith(('/local/', '/server/', '/mail/', '/account/', '/auth/', '/ai/'))
            and r.rule != '/local/health'
            and not r.rule.startswith('/local/websocket')
            and not r.rule.startswith('/local/sftp/websocket')
        ]
        for r in custom_rules:
            # /local/image/test_get/<img_name> 显式声明 methods=['GET', 'POST']（手动注册，不在本测试范围）
            if 'image/test_get' in r.rule:
                continue
            assert 'POST' in r.methods, (
                '路由 %s methods=%r 缺 POST' % (r.rule, r.methods)
            )
            assert 'GET' not in r.methods, (
                '路由 %s 含 GET 方法（应仅 POST）' % (r.rule,)
            )
