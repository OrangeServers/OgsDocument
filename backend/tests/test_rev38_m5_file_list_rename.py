# -*- coding: utf-8 -*-
"""REV38-M5: /local/file/def_get → /local/file/list 重命名回归测试。

背景: REV36-M5 报告原 /local/file/def_get 路径名有冲突风险（def 是 Python 关键字），
      命名不规范，用户视觉负担。
修复:
  - 后端：/local/file/list 作为正式 endpoint，/local/file/def_get 保留为 alias
    (REV38-M4 阶段已标 is_alias=True)
  - 前端：getFileList 改调 /local/file/list 正式 endpoint
  - alias 仍可调用以兼容历史客户端

覆盖范围:
  1) local_api.py ROUTES 表中 /local/file/list 是主路由 is_alias=False
  2) /local/file/def_get 是 alias is_alias=True
  3) Flask url_map 两条都注册
  4) alias 与主路由 endpoint name 不同
  5) 前端 getFileList 现在调 /local/file/list (源码静态扫描)
  6) 前端不再调用 def_get (除注释外)
"""
import os
import re
import sys
from unittest.mock import patch

import pytest

# 路径初始化
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) local_api.py 中路由标记验证
# ============================================================
class TestLocalApiRouteMarking:
    def test_01_file_list_is_main_route(self):
        """/local/file/list 是主路由 (is_alias=False)"""
        import app.api.local_api as _api
        file_list = [r for r in _api.ROUTES if r.url == '/local/file/list']
        assert len(file_list) == 1
        assert file_list[0].is_alias is False

    def test_02_file_def_get_is_alias(self):
        """/local/file/def_get 是 alias (is_alias=True)"""
        import app.api.local_api as _api
        def_get = [r for r in _api.ROUTES if r.url == '/local/file/def_get']
        assert len(def_get) == 1
        assert def_get[0].is_alias is True

    def test_03_both_routes_share_view_class_method(self):
        """alias 与主路由共享 view_class 和 method (FileGet.get_file_list)"""
        import app.api.local_api as _api
        routes = _api.ROUTES
        main = next(r for r in routes if r.url == '/local/file/list')
        alias = next(r for r in routes if r.url == '/local/file/def_get')
        assert main.view_class is alias.view_class
        assert main.method == alias.method == 'get_file_list'

    def test_04_descriptions_distinguish_alias_from_main(self):
        """description 区分 alias 与主路由 (用户阅读友好)"""
        import app.api.local_api as _api
        routes = _api.ROUTES
        main = next(r for r in routes if r.url == '/local/file/list')
        alias = next(r for r in routes if r.url == '/local/file/def_get')
        # alias description 应包含 "alias" 或 "兼容"
        assert 'alias' in alias.description.lower() or '兼容' in alias.description
        # main description 不应包含 "alias"
        assert 'alias' not in main.description.lower()


# ============================================================
# 2) Flask url_map 双注册
# ============================================================
class TestFlaskUrlMapDualRegistration:
    def _register_routes(self, routes):
        """用 ROUTES 注册到独立 Flask app, 返回 url_map 规则集合"""
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
            return {r.rule for r in app.url_map.iter_rules()}, app
        finally:
            _init.app = old_app
            _reset_route_dup_state()
    
    def test_01_both_routes_in_url_map(self):
        """alias 与主路由都注册到 Flask"""
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
        rules, _ = self._register_routes(routes)
        assert '/local/file/def_get' in rules
        assert '/local/file/list' in rules
    
    def test_02_distinct_endpoint_names(self):
        """alias 与主路由 endpoint name 不同 (URL 路径派生)"""
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
        _, app = self._register_routes(routes)
        endpoints = sorted([r.endpoint for r in app.url_map.iter_rules()
                            if r.rule in ('/local/file/list', '/local/file/def_get')])
        assert endpoints == ['local_file_def_get', 'local_file_list']
    
    def test_03_alias_no_warning_during_register(self):
        """def_get 是 alias, 注册时不发 WARNING"""
        from app.api import route
        from flask import Flask
        import init as _init
        from init import _register_routes_from_module, _ROUTE_DUP_KEYS, _reset_route_dup_state
    
        class FileGet:
            pass
    
        app = Flask(__name__)
        old_app = _init.app
        _init.app = app
        _reset_route_dup_state()
        try:
            routes = [
                route('/local/file/def_get', FileGet, 'get_file_list',
                      is_property=False, is_alias=True,
                      description='文件列表（别名）'),
                route('/local/file/list', FileGet, 'get_file_list',
                      is_property=False,
                      description='文件列表（正式）'),
            ]
            mod = type('M', (), {'ROUTES': routes})()
            with patch.object(_init, 'Log') as mock_log:
                _register_routes_from_module(mod)
            dup_warnings = [
                str(c) for c in mock_log.logger.warning.call_args_list
                if 'Duplicate route registration' in str(c)
            ]
            assert dup_warnings == []
        finally:
            _init.app = old_app
            _reset_route_dup_state()


# ============================================================
# 3) 前端迁移验证 (源码静态扫描)
# ============================================================
class TestFrontendMigration:
    """验证前端 api/index.ts 已迁移到 /local/file/list"""

    def test_01_frontend_uses_file_list_not_def_get(self):
        """getFileList 现在调 /local/file/list"""
        api_path = os.path.normpath(
            os.path.join(_BACKEND, '..', 'frontend', 'src', 'api', 'index.ts')
        )
        with open(api_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # ti3-TS: 验证 getFileList 已迁移到 /local/file/list
        # 写法为: export const getFileList: ApiCall = pj('/local/file/list')
        # 容忍多种写法: http.post('URL') 或 pj('URL') 或 http.get<...>('URL')
        patterns = [
            # ti3-TS 新写法: ApiCall 类型 + pj 调用
            r"export\s+const\s+getFileList\s*:\s*ApiCall\s*=\s*[^=]*pj\(\s*['\"]([^'\"]+)['\"]",
            # 旧写法: arrow function + http.post
            r"export\s+const\s+getFileList\s*=\s*data\s*=>\s*http\.post\(\s*['\"]([^'\"]+)['\"]",
            # 通用写法: 找 getFileList 后面最近的 URL 字符串
            r"getFileList[^=]*=\s*[^;]*?['\"]([^'\"]*file/list[^'\"]*)['\"]",
        ]
        url = None
        for pat in patterns:
            m = re.search(pat, content)
            if m:
                url = m.group(1)
                break
        assert url is not None, 'getFileList 未找到'
        assert url == '/local/file/list', \
            f'getFileList 应调 /local/file/list, 实际: {url}'

    def test_02_no_active_def_get_call_in_frontend(self):
        """前端无对 def_get 的可执行调用 (注释除外)"""
        for root, dirs, files in os.walk(
            os.path.join(_BACKEND, '..', 'frontend', 'src')
        ):
            # 跳过 node_modules / dist
            dirs[:] = [d for d in dirs if d not in ('node_modules', 'dist')]
            for fn in files:
                if not fn.endswith(('.js', '.vue', '.ts')):
                    continue
                fp = os.path.join(root, fn)
                with open(fp, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                for i, line in enumerate(lines, 1):
                    # 跳过注释行
                    stripped = line.strip()
                    if stripped.startswith('//') or stripped.startswith('*') \
                            or stripped.startswith('/*'):
                        continue
                    if 'def_get' in line:
                        pytest.fail(
                            f'前端 {fn}:{i} 仍调用 def_get:\n{line.rstrip()}'
                        )

    def test_03_frontend_comment_marks_migration(self):
        """前端 api/index.ts 注释标注 REV38-M5 迁移提示"""
        api_path = os.path.normpath(
            os.path.join(_BACKEND, '..', 'frontend', 'src', 'api', 'index.ts')
        )
        with open(api_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 在 getFileList 上方应有 REV38-M5 注释
        m = re.search(
            r'(//[^\n]*REV38-M5[^\n]*\n\s*)?export\s+const\s+getFileList',
            content,
        )
        assert m is not None, 'REV38-M5 迁移注释未找到'
        assert m.group(1) is not None, \
            'getFileList 上方缺少 REV38-M5 迁移说明注释'
