# -*- coding: utf-8 -*-
"""REV38-M12: /local/file/put vs /server/file/put 文档化语义区分。

背景: REV36-M12 指出两个 /file/put URL 名字一样但语义不同:
      - /local/file/put → FileGet.save_file (上传文件到本地 data 目录)
      - /server/file/put → ServerScript.sh_script (下发脚本到远程主机)
      前端误调会写本地失败, 但错误信息不易识别。

修复:
  - 两个路由 description 字段都加 'REV38-M12' 标签 + 互引对方
  - description 明确语义差异 (本地 vs 远端)
  - 本测试验证: 两个 description 都被添加, 互引对方, 都标 REV38-M12

覆盖范围:
  1) /local/file/put description 含 REV38-M12 + 提及 /server/file/put
  2) /server/file/put description 含 REV38-M12 + 提及 /local/file/put
  3) 两个 URL 仍指向正确 view_class
  4) 两个 method name 仍正确
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) /local/file/put 文档化
# ============================================================
class TestLocalFilePutDoc:
    def test_01_local_file_put_in_routes(self):
        """/local/file/put 在 local_api.ROUTES 中"""
        import app.api.local_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/local/file/put']
        assert len(rules) == 1

    def test_02_local_file_put_description_has_rev38_m12(self):
        """/local/file/put description 含 REV38-M12 标签"""
        import app.api.local_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/local/file/put']
        desc = rules[0].description
        assert 'REV38-M12' in desc

    def test_03_local_file_put_description_mentions_server(self):
        """/local/file/put description 提及 /server/file/put"""
        import app.api.local_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/local/file/put']
        desc = rules[0].description
        assert '/server/file/put' in desc
        # 明确语义: 本地
        assert '本地' in desc or 'local' in desc.lower() or 'data' in desc.lower()

    def test_04_local_file_put_view_class(self):
        """/local/file/put view_class = FileGet, method = save_file"""
        import app.api.local_api as _api
        from app.files.file import FileGet
        rules = [r for r in _api.ROUTES if r.url == '/local/file/put']
        assert rules[0].view_class is FileGet
        assert rules[0].method == 'save_file'


# ============================================================
# 2) /server/file/put 文档化
# ============================================================
class TestServerFilePutDoc:
    def test_01_server_file_put_in_routes(self):
        """/server/file/put 在 server_api.ROUTES 中"""
        import app.api.server_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/server/file/put']
        assert len(rules) == 1

    def test_02_server_file_put_description_has_rev38_m12(self):
        """/server/file/put description 含 REV38-M12 标签"""
        import app.api.server_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/server/file/put']
        desc = rules[0].description
        assert 'REV38-M12' in desc

    def test_03_server_file_put_description_mentions_local(self):
        """/server/file/put description 提及 /local/file/put"""
        import app.api.server_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/server/file/put']
        desc = rules[0].description
        assert '/local/file/put' in desc
        # 明确语义: 远端
        assert '远端' in desc or '远程' in desc or 'remote' in desc.lower() or '脚本' in desc or 'script' in desc.lower()

    def test_04_server_file_put_view_class(self):
        """/server/file/put view_class = ServerScript, method = sh_script"""
        import app.api.server_api as _api
        # ServerScript 类在 server_api 内部定义, 不直接 import
        rules = [r for r in _api.ROUTES if r.url == '/server/file/put']
        assert rules[0].method == 'sh_script'
        # view_class 名应是 ServerScript
        assert rules[0].view_class.__name__ == 'ServerScript'


# ============================================================
# 3) 集成: 两个 URL 都在 Flask url_map 中
# ============================================================
class TestBothRoutesRegistered:
    def test_01_both_urls_distinct(self):
        """两个 URL 不同"""
        import app.api.local_api as _local
        import app.api.server_api as _server
        local_urls = {r.url for r in _local.ROUTES}
        server_urls = {r.url for r in _server.ROUTES}
        assert '/local/file/put' in local_urls
        assert '/server/file/put' in server_urls
        assert local_urls.isdisjoint(server_urls)

    def test_02_both_methods_distinct(self):
        """两个 method 不同 (save_file vs sh_script)"""
        import app.api.local_api as _local
        import app.api.server_api as _server
        local_method = next(r.method for r in _local.ROUTES if r.url == '/local/file/put')
        server_method = next(r.method for r in _server.ROUTES if r.url == '/server/file/put')
        assert local_method == 'save_file'
        assert server_method == 'sh_script'
        assert local_method != server_method

    def test_03_descriptions_reciprocally_cite(self):
        """两个 description 互相引用对方 URL"""
        import app.api.local_api as _local
        import app.api.server_api as _server
        local_desc = next(r.description for r in _local.ROUTES if r.url == '/local/file/put')
        server_desc = next(r.description for r in _server.ROUTES if r.url == '/server/file/put')
        # 双向引用
        assert '/server/file/put' in local_desc
        assert '/local/file/put' in server_desc


# ============================================================
# 4) M12 防止历史回归: description 不会被偷改
# ============================================================
class TestDescriptionRegression:
    def test_01_local_file_put_desc_not_empty(self):
        """description 非空 (避免后续被简化)"""
        import app.api.local_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/local/file/put']
        assert rules[0].description
        assert len(rules[0].description) > 10

    def test_02_server_file_put_desc_not_empty(self):
        """description 非空 (避免后续被简化)"""
        import app.api.server_api as _api
        rules = [r for r in _api.ROUTES if r.url == '/server/file/put']
        assert rules[0].description
        assert len(rules[0].description) > 10
