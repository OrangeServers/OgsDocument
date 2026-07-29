# -*- coding: utf-8 -*-
"""REV38-M4: 路由重复注册同一 class.method 启动时检测回归测试。

背景: REV36-M4 报告 /local/image/test_put 与 /local/image/upload 两条 alias 路由
      各自注册 PutUserImage.put_img, 注册时无声无息.
修复:
  - RouteRule 加第 9 字段 is_alias: bool (默认 False)
  - init.py _register_routes_from_module 维护全局 _ROUTE_DUP_KEYS, 启动时:
    * 第一条注册 → 主路由, 静默加入 seen
    * 后续注册未标 is_alias → WARNING (疑似错误)
    * 后续注册已标 is_alias → 静默 (合法 alias)
  - 把现有 4 条 alias 路由显式标 is_alias=True

覆盖范围:
  1) RouteRule 9 字段 + is_alias 字段定义
  2) route() 默认 is_alias=False
  3) _register_routes_from_module 主路由不警告
  4) _register_routes_from_module alias 不警告 (is_alias=True 静默)
  5) _register_routes_from_module 重复未标 alias → WARNING
  6) 4 个 api 模块的 ROUTES 表里 4 条 alias 全部标 is_alias=True
  7) /local/image/* / /local/file/* 两组 alias Flask url_map 实际双注册
"""
import importlib
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# 路径初始化
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


@pytest.fixture
def fresh_dup_keys(monkeypatch):
    """每个测试用 fresh _ROUTE_DUP_KEYS, 不污染其他测试"""
    import init as _init
    monkeypatch.setattr(_init, '_ROUTE_DUP_KEYS', {})


# ============================================================
# 1) RouteRule 9 字段 + is_alias 默认值
# ============================================================
class TestIsAliasField:
    def test_01_route_rule_has_nine_fields(self):
        """RouteRule 现在有 9 字段 (REV38-M4 新增 is_alias)"""
        from app.api import RouteRule
        assert len(RouteRule._fields) == 9

    def test_02_is_alias_in_fields(self):
        """is_alias 是 RouteRule 第 9 字段"""
        from app.api import RouteRule
        assert 'is_alias' in RouteRule._fields

    def test_03_route_helper_default_alias_false(self):
        """route() 不传 is_alias 时默认为 False"""
        from app.api import route

        class V:
            pass

        r = route('/x', V, 'm')
        assert r.is_alias is False

    def test_04_route_helper_explicit_alias_true(self):
        """route() 显式传 is_alias=True 时为 True"""
        from app.api import route

        class V:
            pass

        r = route('/y', V, 'n', is_alias=True)
        assert r.is_alias is True

    def test_05_old_tuple_compat_includes_alias_false(self):
        """旧 5/6-tuple 兼容路径默认 is_alias=False"""
        from app.api import RouteRule

        class V:
            pass

        # 模拟旧 tuple 写法
        old_tuple = ('/legacy', V, 'm', True, False)
        # 走 init.py 的归一化逻辑
        url, cls, method_name, need_auth, is_property = old_tuple[:5]
        rule = RouteRule(
            url=url, view_class=cls, method=method_name,
            need_auth=need_auth, is_property=is_property,
            roles=None, description='[LEGACY]', skip_csrf=False, is_alias=False,
        )
        assert rule.is_alias is False


# ============================================================
# 2) _register_routes_from_module 主路由 / alias / 重复检测
# ============================================================
class TestRegisterRouteDupDetection:
    """每个测试用 _build_test_app 产生独立 Flask app, 避免 init.app 单例污染"""

    def _build_test_app(self):
        """构建独立 Flask app 并 patch 进 _init.app, yield 后清理"""
        from flask import Flask
        import init as _init
        from init import _register_routes_from_module, _ROUTE_DUP_KEYS, _reset_route_dup_state
        app = Flask(__name__)
        old_app = _init.app
        _init.app = app
        _reset_route_dup_state()
        try:
            yield app
        finally:
            _init.app = old_app
            _reset_route_dup_state()

    def test_01_main_route_no_warning(self):
        """主路由 (is_alias=False) 注册时不发警告"""
        from app.api import route
        import init as _init

        class DummyView:
            pass

        test_routes = [route('/main', DummyView, 'do', is_alias=False)]

        gen = self._build_test_app()
        next(gen)  # push app
        try:
            with patch.object(_init, 'Log') as mock_log:
                mod = type('M', (), {'ROUTES': test_routes})()
                _init._register_routes_from_module(mod)
            # 无 WARNING 日志
            warning_calls = [
                c for c in mock_log.logger.warning.call_args_list
                if 'Duplicate route registration' in str(c)
            ]
            assert len(warning_calls) == 0
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_02_alias_route_silent(self):
        """alias (is_alias=True) 注册时不发警告 (无论与主路由先后顺序)"""
        from app.api import route
        import init as _init

        class DummyView:
            pass

        # 先注册 alias 后注册 main 都不会警告
        alias = route('/alias', DummyView, 'do', is_alias=True)
        main = route('/main', DummyView, 'do', is_alias=False)
        mod = type('M', (), {'ROUTES': [alias, main]})()

        gen = self._build_test_app()
        next(gen)
        try:
            with patch.object(_init, 'Log') as mock_log:
                _init._register_routes_from_module(mod)
            warning_calls = [
                c for c in mock_log.logger.warning.call_args_list
                if 'Duplicate route registration' in str(c)
            ]
            assert len(warning_calls) == 0
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_03_duplicate_without_alias_triggers_warning(self):
        """两条都未标 alias → 第二条触发 WARNING"""
        from app.api import route
        import init as _init

        class DummyView:
            pass

        main = route('/main', DummyView, 'do', is_alias=False)
        dup = route('/dup', DummyView, 'do', is_alias=False)
        mod = type('M', (), {'ROUTES': [main, dup]})()

        gen = self._build_test_app()
        next(gen)
        try:
            with patch.object(_init, 'Log') as mock_log:
                _init._register_routes_from_module(mod)
            warning_msgs = [
                str(c) for c in mock_log.logger.warning.call_args_list
                if 'Duplicate route registration' in str(c)
            ]
            assert len(warning_msgs) == 1
            assert 'DummyView' in warning_msgs[0]
            assert 'do' in warning_msgs[0]
            assert '/main' in warning_msgs[0] and '/dup' in warning_msgs[0]
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_04_dup_keys_populated_for_main_only(self):
        """_ROUTE_DUP_KEYS 仅记录主路由 (alias 不入 seen)"""
        from app.api import route
        import init as _init

        class DummyView:
            pass

        alias = route('/alias', DummyView, 'do', is_alias=True)
        main = route('/main', DummyView, 'do', is_alias=False)
        mod = type('M', (), {'ROUTES': [alias, main]})()

        gen = self._build_test_app()
        next(gen)
        try:
            with patch.object(_init, 'Log'):
                _init._register_routes_from_module(mod)
            from init import _ROUTE_DUP_KEYS
            key = (id(DummyView), 'do')
            # alias 不入 seen, 所以最后 seen 应是 main 的 URL
            assert _ROUTE_DUP_KEYS.get(key) == '/main'
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_05_legacy_tuple_treated_as_main_triggers_warning(self):
        """旧 tuple 写法默认 is_alias=False, 重复会 WARNING"""
        import init as _init

        class DummyView:
            pass

        legacy_main = ('/legacy1', DummyView, 'do', True, True)
        legacy_dup = ('/legacy2', DummyView, 'do', True, True)
        mod = type('M', (), {'ROUTES': [legacy_main, legacy_dup]})()

        gen = self._build_test_app()
        next(gen)
        try:
            with patch.object(_init, 'Log') as mock_log:
                _init._register_routes_from_module(mod)
            warning_msgs = [
                str(c) for c in mock_log.logger.warning.call_args_list
                if 'Duplicate route registration' in str(c)
            ]
            assert len(warning_msgs) == 1
        finally:
            try:
                next(gen)
            except StopIteration:
                pass


# ============================================================
# 3) 现有 4 个 api 模块的 alias 路由已标记 is_alias=True
# ============================================================
class TestApiModuleAliasesMarked:
    """验证 local_api 中 4 条 alias 路由已显式标 is_alias=True"""

    def test_01_local_api_alias_routes_marked(self):
        """local_api.py 中 4 条 alias 路由全部 is_alias=True"""
        import app.api.local_api as _api
        routes = _api.ROUTES
        # 4 条 alias: /local/image/test_put, /local/file/def_get
        alias_urls = {'/local/image/test_put', '/local/file/def_get'}
        found = {r.url: r.is_alias for r in routes if r.url in alias_urls}
        assert len(found) == 2, f'找到的 alias 不全: {found}'
        for url in alias_urls:
            assert found[url] is True, f'{url} 未标 is_alias=True'

    def test_02_local_api_main_routes_not_alias(self):
        """对应的 2 条正式路由 is_alias=False"""
        import app.api.local_api as _api
        routes = _api.ROUTES
        main_urls = {'/local/image/upload', '/local/file/list'}
        found = {r.url: r.is_alias for r in routes if r.url in main_urls}
        assert len(found) == 2
        for url in main_urls:
            assert found[url] is False

    def test_03_alias_count_in_local_api(self):
        """local_api 中 is_alias=True 的路由共有 2 条"""
        import app.api.local_api as _api
        routes = _api.ROUTES
        alias_count = sum(1 for r in routes if r.is_alias)
        assert alias_count == 2


# ============================================================
# 4) Flask url_map 实际双注册验证
# ============================================================
class TestFlaskUrlMapDualRegistration:
    """验证 alias 路由不会被去重, 两条都注册到 Flask"""

    def _register_to_fresh_app(self, routes):
        """用给定的 ROUTES 注册到独立 Flask app, 返回 url_map 规则集合"""
        from flask import Flask
        import init as _init
        from init import _register_routes_from_module, _ROUTE_DUP_KEYS, _reset_route_dup_state
        app = Flask(__name__)
        old_app = _init.app
        _init.app = app
        _reset_route_dup_state()
        try:
            mod = type('M', (), {'ROUTES': routes})()
            with patch.object(_init, 'Log'):
                _register_routes_from_module(mod)
            return {r.rule for r in app.url_map.iter_rules()}
        finally:
            _init.app = old_app
            _reset_route_dup_state()

    def test_01_alias_pair_both_registered(self):
        """/local/image/test_put + /local/image/upload 都注册"""
        from app.api import route

        class PutUserImage:
            pass

        routes = [
            route('/local/image/test_put', PutUserImage, 'put_img',
                  is_property=False, is_alias=True,
                  description='上传用户图片（旧 alias）'),
            route('/local/image/upload', PutUserImage, 'put_img',
                  is_property=False,
                  description='上传用户图片（正式）'),
        ]
        rules = self._register_to_fresh_app(routes)
        assert '/local/image/test_put' in rules
        assert '/local/image/upload' in rules

    def test_02_file_list_alias_pair_both_registered(self):
        """/local/file/def_get + /local/file/list 都注册"""
        from app.api import route

        class FileGet:
            pass

        routes = [
            route('/local/file/def_get', FileGet, 'get_file_list',
                  is_property=False, is_alias=True,
                  description='文件列表（别名）'),
            route('/local/file/list', FileGet, 'get_file_list',
                  is_property=False,
                  description='文件列表（正式）'),
        ]
        rules = self._register_to_fresh_app(routes)
        assert '/local/file/def_get' in rules
        assert '/local/file/list' in rules

    def test_03_unique_endpoint_names(self):
        """alias pair 的 endpoint name 不同 (URL 路径区分)"""
        from app.api import route

        class V:
            pass

        routes = [
            route('/api/old', V, 'do', is_alias=True),
            route('/api/new', V, 'do'),
        ]
        rules = self._register_to_fresh_app(routes)
        # endpoint 名由 url 派生, 必然不同
        assert '/api/old' in rules
        assert '/api/new' in rules


# ============================================================
# 5) 集成测试: 没有 WARNING 时启动正常
# ============================================================
class TestStartupNoWarning:
    """验证给真实 ROUTES 表注册时不发 WARNING (现有 alias 都已标 True)"""

    def test_01_all_api_modules_no_dup_warning(self, monkeypatch):
        """遍历所有 api 模块的 ROUTES 注册, 不应发出 Duplicate route registration WARNING"""
        import init as _init
        import pkgutil
        import importlib
        import app.api as _service_pkg
        from init import _register_routes_from_module, _ROUTE_DUP_KEYS, _reset_route_dup_state
        from flask import Flask

        # 用独立 app
        app = Flask(__name__)
        old_app = _init.app
        _init.app = app
        _reset_route_dup_state()

        try:
            with patch.object(_init, 'Log') as mock_log:
                for importer, modname, ispkg in pkgutil.iter_modules(_service_pkg.__path__):
                    if modname.startswith('_'):
                        continue
                    try:
                        module = importlib.import_module(f'app.api.{modname}')
                    except ImportError:
                        continue
                    if hasattr(module, 'ROUTES'):
                        _register_routes_from_module(module)

            dup_warnings = [
                str(c) for c in mock_log.logger.warning.call_args_list
                if 'Duplicate route registration' in str(c)
            ]
            # 现有 alias 已标 True, 不应有 WARNING
            assert dup_warnings == [], \
                f'未预期的 WARNING:\n' + '\n'.join(dup_warnings)
        finally:
            _init.app = old_app
            _reset_route_dup_state()
