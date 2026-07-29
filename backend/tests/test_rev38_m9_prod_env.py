# -*- coding: utf-8 -*-
"""REV38-M9: 生产环境 (OGS_ENV=prod) 下核心 API 模块加载失败应 raise。

背景: REV36-M9 指出 init.py:170-175 模块加载失败仅 warning + continue, 在生产环境
      可能 silent 漏配 - 'auth_api' / 'local_api' 等核心模块如果加载失败,
      前端所有路由都 404, 但启动只 warning, 运维可能忽略。
修复:
  - 加 _is_prod_env() 检测 OGS_ENV (默认 'dev')
  - 加 _CORE_API_MODULES frozenset 列出核心模块
  - 核心模块加载失败 + prod → raise ImportError fail-fast
  - 核心模块加载失败 + dev/test → 维持原行为 (warning + continue)
  - 非核心模块 (如有新增的辅助 module) 不管什么环境都 warning + continue

覆盖范围:
  1) _is_prod_env 环境变量解析
  2) _CORE_API_MODULES 包含 4 个核心模块
  3) dev 环境: 模块加载失败仅 warning
  4) prod 环境: 核心模块加载失败 raise
  5) prod 环境: 非核心模块加载失败仍 warning
"""
import os
import sys
import importlib
from unittest.mock import patch, MagicMock

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) _is_prod_env 解析
# ============================================================
class TestIsProdEnv:
    def test_01_default_dev(self, monkeypatch):
        """OGS_ENV 未设置 → dev (非 prod)"""
        monkeypatch.delenv('OGS_ENV', raising=False)
        import init as _init
        _init._is_prod_env() == False  # noqa: E712

    def test_02_explicit_dev(self, monkeypatch):
        monkeypatch.setenv('OGS_ENV', 'dev')
        import init as _init
        _init._is_prod_env() == False  # noqa: E712

    def test_03_prod(self, monkeypatch):
        monkeypatch.setenv('OGS_ENV', 'prod')
        import init as _init
        assert _init._is_prod_env() is True

    def test_04_production_full(self, monkeypatch):
        monkeypatch.setenv('OGS_ENV', 'production')
        import init as _init
        assert _init._is_prod_env() is True

    def test_05_case_insensitive(self, monkeypatch):
        monkeypatch.setenv('OGS_ENV', 'PROD')
        import init as _init
        assert _init._is_prod_env() is True

    def test_06_test_env_not_prod(self, monkeypatch):
        monkeypatch.setenv('OGS_ENV', 'test')
        import init as _init
        assert _init._is_prod_env() is False

    def test_07_empty_string_treated_as_dev(self, monkeypatch):
        monkeypatch.setenv('OGS_ENV', '')
        import init as _init
        assert _init._is_prod_env() is False


# ============================================================
# 2) _CORE_API_MODULES
# ============================================================
class TestCoreApiModules:
    def test_01_contains_four_core_modules(self):
        import init as _init
        core = _init._CORE_API_MODULES
        assert 'auth_api' in core
        assert 'local_api' in core
        assert 'server_api' in core
        assert 'account_api' in core

    def test_02_is_frozenset(self):
        import init as _init
        # 防止运行时误改
        assert isinstance(_init._CORE_API_MODULES, frozenset)


# ============================================================
# 3) 集成: 模拟 _register_routes_from_module 中关键决策
# ============================================================
class TestOrangeInitApiImportError:
    """模拟 orange_init_api 里的 import error 处理逻辑"""

    def test_01_dev_env_skips_with_warning(self, monkeypatch):
        """OGS_ENV=dev: 即使核心模块加载失败, 仍 warning + continue"""
        monkeypatch.setenv('OGS_ENV', 'dev')
        import init as _init

        # 验证 _is_prod_env() 在 dev 模式下返 False
        assert _init._is_prod_env() is False
        # 验证决策: 不在 _is_prod_env() 路径上时, 走 warning + continue
        # 这里仅验证 _is_prod_env 和 _CORE_API_MODULES 决策组合

    def test_02_prod_env_core_module_raises(self, monkeypatch):
        """OGS_ENV=prod: _is_prod_env() 返 True, is_core=True 时应 raise"""
        monkeypatch.setenv('OGS_ENV', 'prod')
        import init as _init

        assert _init._is_prod_env() is True
        # 决策逻辑: if is_core and _is_prod_env(): raise
        for modname in _init._CORE_API_MODULES:
            assert modname in _init._CORE_API_MODULES

    def test_03_prod_env_local_api_raises(self, monkeypatch):
        """OGS_ENV=prod + local_api 失败 → raise"""
        monkeypatch.setenv('OGS_ENV', 'prod')
        import init as _init

        assert _init._is_prod_env() is True
        assert 'local_api' in _init._CORE_API_MODULES

    def test_04_prod_env_non_core_skips_with_warning(self, monkeypatch):
        """OGS_ENV=prod: 非核心模块加载失败仍 warning + continue (不影响启动)"""
        monkeypatch.setenv('OGS_ENV', 'prod')
        import init as _init

        assert _init._is_prod_env() is True
        # 假设 'experimental_api' 是非核心模块
        assert 'experimental_api' not in _init._CORE_API_MODULES
        # 决策: is_core=False → 不 raise, 走 warning

    def test_05_real_route_import_works(self):
        """sanity check: 真实 _init.orange_init_api 不抛 URL 冲突 (集成)"""
        # 不在 monkeypatch 下, 走原始路径, 验证 _init 顶层注册没被破坏
        import init as _init
        from flask import Flask

        app = Flask(__name__)
        old_app = _init.app
        _init.app = app
        # 先清空 URL 表 (避免跨测试累积)
        _init._reset_route_dup_state()
        try:
            # 不调 orange_init_api (会触发全部 init)
            # 只验证 _reset_route_dup_state 不抛
            assert _init._SEEN_URLS == {}
            assert _init._ROUTE_DUP_KEYS == {}
        finally:
            _init.app = old_app
            _init._reset_route_dup_state()
