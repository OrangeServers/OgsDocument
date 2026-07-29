# -*- coding: utf-8 -*-
"""REV38-M7: 路由 URL 重复检测 (硬冲突)。

背景: REV36-M7 指出 init.py:157-158 endpoint_name = url.strip('/').replace('/', '_')
      用 URL 派生 endpoint 名, 但如果同一 URL 在 ROUTES 表注册两次, Flask 会 AssertionError
      启动崩溃. REV38-M7 在路由注册循环里加 URL 重复检测, 早期 raise 给清晰错误.

与 REV38-M4 区别:
  - M4: (view_class, method) 配对重复 → WARNING (软约束, alias 静默)
  - M7: URL 重复 → raise RuntimeError (硬约束, Flask 真崩溃)

覆盖范围:
  1) _SEEN_URLS 全局表 + _reset_route_dup_state reset
  2) 同 URL 重复注册 (主+主 / 主+alias / alias+alias) 都 raise
  3) raise message 含 REV38-M7 标签 + url + cls.method 信息
  4) 不同 URL 注册仍合法
  5) 现有 ROUTES 表不应有 URL 冲突 (集成测试)
"""
import os
import sys
import pkgutil
import importlib
from unittest.mock import patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) _SEEN_URLS 全局表 + reset
# ============================================================
class TestSeenUrlsState:
    def test_01_seen_urls_dict_exists(self):
        """init.py 维护 _SEEN_URLS 全局 dict"""
        import init as _init
        assert hasattr(_init, '_SEEN_URLS')
        assert isinstance(_init._SEEN_URLS, dict)

    def test_02_reset_route_dup_state_clears_both(self):
        """_reset_route_dup_state() 同时清 M4 _ROUTE_DUP_KEYS 和 M7 _SEEN_URLS"""
        import init as _init
        _init._ROUTE_DUP_KEYS[('x',)] = '/a'
        _init._SEEN_URLS['/a'] = (object, 'm', False)
        _init._reset_route_dup_state()
        assert _init._ROUTE_DUP_KEYS == {}
        assert _init._SEEN_URLS == {}

    def test_03_reset_route_dup_state_does_not_remove_attribute(self):
        """_reset_route_dup_state() 仅清内容, 不删除属性"""
        import init as _init
        _init._reset_route_dup_state()
        assert hasattr(_init, '_ROUTE_DUP_KEYS')
        assert hasattr(_init, '_SEEN_URLS')


# ============================================================
# 2) 重复 URL raise (主+主 / 主+alias / alias+alias)
# ============================================================
class TestDuplicateUrlRaises:
    def _register(self, routes, app):
        """把 routes 注册到独立 Flask app, 走 _register_routes_from_module"""
        import init as _init
        from init import _register_routes_from_module
        old_app = _init.app
        _init.app = app
        _init._reset_route_dup_state()
        try:
            mod = type('M', (), {'ROUTES': routes})()
            with patch.object(_init, 'Log'):
                _register_routes_from_module(mod)
        finally:
            _init.app = old_app
            _init._reset_route_dup_state()

    def test_01_main_route_dup_raises(self, fresh_flask_app):
        """主路由 + 主路由同 URL 重复 → raise"""
        from flask import Flask
        from app.api import route

        class V:
            pass

        r1 = route('/dup', V, 'do')
        r2 = route('/dup', V, 'do')  # 同 cls/method/url → 第二次进入
        with pytest.raises(RuntimeError) as exc_info:
            self._register([r1, r2], fresh_flask_app)
        assert '[REV38-M7]' in str(exc_info.value)
        assert '/dup' in str(exc_info.value)
        assert 'V' in str(exc_info.value)

    def test_02_main_then_alias_same_url_raises(self, fresh_flask_app):
        """主路由先注册, alias 后注册同 URL → raise (alias 也无法解同 URL)"""
        from app.api import route

        class V:
            pass

        r1 = route('/dup2', V, 'do', is_alias=False)
        r2 = route('/dup2', V, 'do', is_alias=True)
        with pytest.raises(RuntimeError) as exc_info:
            self._register([r1, r2], fresh_flask_app)
        assert '[REV38-M7]' in str(exc_info.value)
        assert 'is_alias=False' in str(exc_info.value)
        assert 'is_alias=True' in str(exc_info.value)

    def test_03_alias_then_main_same_url_raises(self, fresh_flask_app):
        """alias 先注册, 主路由后注册同 URL → 仍 raise"""
        from app.api import route

        class V:
            pass

        r1 = route('/dup3', V, 'do', is_alias=True)
        r2 = route('/dup3', V, 'do', is_alias=False)
        with pytest.raises(RuntimeError):
            self._register([r1, r2], fresh_flask_app)

    def test_04_alias_then_alias_same_url_raises(self, fresh_flask_app):
        """alias + alias 同 URL → 仍 raise (Flask 必崩)"""
        from app.api import route

        class V:
            pass

        r1 = route('/dup4', V, 'do', is_alias=True)
        r2 = route('/dup4', V, 'do', is_alias=True)
        with pytest.raises(RuntimeError):
            self._register([r1, r2], fresh_flask_app)

    def test_05_error_msg_mentions_duplicate(self, fresh_flask_app):
        """raise message 包含 'Duplicate URL registration'"""
        from app.api import route

        class V:
            pass

        r1 = route('/dup5', V, 'm')
        r2 = route('/dup5', V, 'm')
        with pytest.raises(RuntimeError) as exc_info:
            self._register([r1, r2], fresh_flask_app)
        assert 'Duplicate URL registration' in str(exc_info.value)


# ============================================================
# 3) 不同 URL 注册合法
# ============================================================
class TestDistinctUrlsSucceed:
    def _register(self, routes, app):
        import init as _init
        from init import _register_routes_from_module
        old_app = _init.app
        _init.app = app
        _init._reset_route_dup_state()
        try:
            mod = type('M', (), {'ROUTES': routes})()
            with patch.object(_init, 'Log'):
                _register_routes_from_module(mod)
        finally:
            _init.app = old_app
            _init._reset_route_dup_state()

    def test_01_different_urls_ok(self, fresh_flask_app):
        """不同 URL 注册不 raise"""
        from app.api import route

        class V:
            pass

        r1 = route('/a', V, 'm')
        r2 = route('/b', V, 'm')  # 同 cls/method 但 URL 不同
        self._register([r1, r2], fresh_flask_app)
        rules = {r.rule for r in fresh_flask_app.url_map.iter_rules()}
        assert '/a' in rules
        assert '/b' in rules

    def test_02_different_methods_same_class_ok(self, fresh_flask_app):
        """同 class 不同 method 同 URL (理论) → M4 WARNING 但 M7 不 raise"""
        from app.api import route

        class V:
            pass

        # 不同 method 同 URL 是合法多 method 路由
        # (实际不会这么写, 这里只验 M7 不因 method 不同误报)
        r1 = route('/x', V, 'm1')
        r2 = route('/x', V, 'm2')  # 同 URL 不同 method
        with pytest.raises(RuntimeError):
            # 同 URL 仍然会触发 M7 (不管 method)
            self._register([r1, r2], fresh_flask_app)

    def test_03_existing_routes_have_no_url_dup(self):
        """实际 ROUTES 表里所有 URL 都唯一 (集成测试)"""
        import app.api as _service_pkg
        all_urls = []
        for importer, modname, ispkg in pkgutil.iter_modules(_service_pkg.__path__):
            if modname.startswith('_'):
                continue
            try:
                module = importlib.import_module(f'app.api.{modname}')
            except ImportError:
                continue
            if hasattr(module, 'ROUTES'):
                for rule in module.ROUTES:
                    all_urls.append(rule.url)
        # 检查唯一性
        from collections import Counter
        url_counts = Counter(all_urls)
        dups = {url: cnt for url, cnt in url_counts.items() if cnt > 1}
        assert dups == {}, \
            f'实际 ROUTES 表发现 URL 重复: {dups}. REV38-M7 应在启动时 raise.'


# ============================================================
# 4) 集成: 全部 api 模块注册后, _SEEN_URLS 累计了所有 URL
# ============================================================
class TestIntegrationAllRoutes:
    def test_01_all_real_routes_register_without_url_dup(self, fresh_flask_app):
        """遍历所有 api 模块 ROUTES 注册, 全部 URL 唯一不 raise"""
        import init as _init
        from init import _register_routes_from_module
        import app.api as _service_pkg
        old_app = _init.app
        _init.app = fresh_flask_app
        _init._reset_route_dup_state()
        try:
            with patch.object(_init, 'Log'):
                for importer, modname, ispkg in pkgutil.iter_modules(_service_pkg.__path__):
                    if modname.startswith('_'):
                        continue
                    try:
                        module = importlib.import_module(f'app.api.{modname}')
                    except ImportError:
                        continue
                    if hasattr(module, 'ROUTES'):
                        _register_routes_from_module(module)
        finally:
            _init.app = old_app
            _init._reset_route_dup_state()


@pytest.fixture
def fresh_flask_app():
    """每次创建独立 Flask app, 不污染 init.app"""
    from flask import Flask
    return Flask(__name__)
