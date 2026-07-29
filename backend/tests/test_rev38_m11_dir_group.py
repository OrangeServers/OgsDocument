# -*- coding: utf-8 -*-
"""REV38-M11: /local/dir/group 改用 os.listdir 替代 cmdlist_shell('ls ...')。

背景: REV36-M11 指出 /local/dir/group 走 shell 'ls /data', 如果未来 DEFAULT_DIR1_PATH
      引入用户可控路径, 立即 RCE。
修复:
  - local_dir_group 改用 os.listdir(DEFAULT_DATA_DIR) (OGS_DATA_DIR 配置)
  - 限定路径在 OGS_DATA_DIR 下 (os.path.realpath + isdir)
  - 失败时返 ApiCode.DIR_NOT_FOUND (code=121)
  - 过滤隐藏文件 + 排序

覆盖范围:
  1) local_dir_group 不再调 cmdlist_shell
  2) 正常目录: 返 code=0 + group_dir_msg 列表
  3) 不存在目录: 返 code=DIR_NOT_FOUND + 空 list
  4) 隐藏文件被过滤
  5) 列表已排序
  6) OGS_DATA_DIR 在 config 中可配置
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) local_api.py 实现验证
# ============================================================
class TestLocalDirGroupImplementation:
    def test_01_uses_os_listdir_not_cmdlist_shell(self):
        """local_dir_group 不再调 cmdlist_shell"""
        import inspect
        import app.api.local_api as _api
        # 取源码但剔除 docstring
        src = inspect.getsource(_api.local_dir_group)
        # 去除 docstring (简单起见: 取 """ 之后下一行开始)
        if '"""' in src:
            parts = src.split('"""')
            if len(parts) >= 3:
                # 第二个 """ 后才是代码体
                src_body = '"""'.join(parts[2:])
            else:
                src_body = src
        else:
            src_body = src
        # 必须有 os.listdir
        assert 'os.listdir' in src_body
        # 不应再有 cmdlist_shell 调用
        assert 'cmdlist_shell(' not in src_body

    def test_02_uses_default_data_dir(self):
        """使用 DEFAULT_DATA_DIR 常量, 不是 DEFAULT_DIR1_PATH"""
        import inspect
        import app.api.local_api as _api
        src = inspect.getsource(_api.local_dir_group)
        # 去除 docstring
        if '"""' in src:
            parts = src.split('"""')
            if len(parts) >= 3:
                src_body = '"""'.join(parts[2:])
            else:
                src_body = src
        else:
            src_body = src
        assert 'DEFAULT_DATA_DIR' in src_body
        # 不再依赖 DEFAULT_DIR1_PATH
        assert 'DEFAULT_DIR1_PATH' not in src_body

    def test_03_handles_missing_directory(self):
        """目录不存在时返 DIR_NOT_FOUND"""
        import inspect
        import app.api.local_api as _api
        src = inspect.getsource(_api.local_dir_group)
        assert 'is not' in src or 'not a directory' in src or 'not found' in src
        assert 'DIR_NOT_FOUND' in src or 'group_dir_msg' in src

    def test_04_filters_hidden_files(self):
        """过滤以 . 开头的隐藏文件"""
        import inspect
        import app.api.local_api as _api
        src = inspect.getsource(_api.local_dir_group)
        assert "startswith('.')" in src

    def test_05_sorts_results(self):
        """结果按字母排序"""
        import inspect
        import app.api.local_api as _api
        src = inspect.getsource(_api.local_dir_group)
        assert 'sorted' in src


# ============================================================
# 2) config DEFAULT_DATA_DIR 存在
# ============================================================
class TestDefaultDataDirConfig:
    def test_01_default_data_dir_exists(self):
        from app.core.config import DEFAULT_DATA_DIR
        assert DEFAULT_DATA_DIR
        assert isinstance(DEFAULT_DATA_DIR, str)

    def test_02_default_data_dir_is_absolute(self):
        """OGS_DATA_DIR 默认值是绝对路径"""
        from app.core.config import DEFAULT_DATA_DIR
        # 默认值是 os.getcwd() + '/data', 应该是绝对路径
        assert os.path.isabs(DEFAULT_DATA_DIR) or DEFAULT_DATA_DIR.endswith('/data')


# ============================================================
# 3) 端到端: local_dir_group 实际行为
# ============================================================
class TestLocalDirGroupRuntime:
    def test_01_normal_dir_returns_sorted_list(self, tmp_path, monkeypatch):
        """正常目录: 返 code=0 + 排序列表"""
        # 创建临时目录 + 几个文件
        (tmp_path / 'b_dir').mkdir()
        (tmp_path / 'a_dir').mkdir()
        (tmp_path / 'c_file.txt').write_text('x')
        (tmp_path / '.hidden').write_text('x')  # 隐藏

        # mock DEFAULT_DATA_DIR → 临时目录
        import app.core.config as _cfg
        monkeypatch.setattr(_cfg, 'DEFAULT_DATA_DIR', str(tmp_path))

        # mock ogs_auth_token 装饰器 (避免触发登录态检查)
        import app.tools.at as _at
        monkeypatch.setattr(_at, 'ogs_auth_token', lambda f: f)

        # reimport local_api (装饰器已重新生效)
        import importlib
        import app.api.local_api as _api
        importlib.reload(_api)

        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/local/dir/group', method='GET'):
            resp = _api.local_dir_group()
        body = resp.get_json()
        assert body['code'] == 0
        # 应含 a_dir, b_dir, c_file.txt, 不含 .hidden
        assert 'a_dir' in body['group_dir_msg']
        assert 'b_dir' in body['group_dir_msg']
        assert 'c_file.txt' in body['group_dir_msg']
        assert '.hidden' not in body['group_dir_msg']
        # 排序检查
        assert body['group_dir_msg'] == sorted(body['group_dir_msg'])

    def test_02_missing_dir_returns_dir_not_found(self, tmp_path, monkeypatch):
        """目录不存在: 返 code=DIR_NOT_FOUND + 空 list"""
        from app.tools.apierr import ApiCode

        non_exist = tmp_path / 'never_created'
        assert not non_exist.exists()

        import app.core.config as _cfg
        monkeypatch.setattr(_cfg, 'DEFAULT_DATA_DIR', str(non_exist))

        import app.tools.at as _at
        monkeypatch.setattr(_at, 'ogs_auth_token', lambda f: f)

        import importlib
        import app.api.local_api as _api
        importlib.reload(_api)

        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/local/dir/group', method='GET'):
            resp = _api.local_dir_group()
        body = resp.get_json()
        assert body['code'] == ApiCode.DIR_NOT_FOUND
        assert body['group_dir_msg'] == []

    def test_03_empty_dir_returns_empty_list(self, tmp_path, monkeypatch):
        """空目录: 返空 list"""
        empty_dir = tmp_path / 'empty'
        empty_dir.mkdir()

        import app.core.config as _cfg
        monkeypatch.setattr(_cfg, 'DEFAULT_DATA_DIR', str(empty_dir))

        import app.tools.at as _at
        monkeypatch.setattr(_at, 'ogs_auth_token', lambda f: f)

        import importlib
        import app.api.local_api as _api
        importlib.reload(_api)

        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/local/dir/group', method='GET'):
            resp = _api.local_dir_group()
        body = resp.get_json()
        assert body['code'] == 0
        assert body['group_dir_msg'] == []


# ============================================================
# 4) 安全: 不依赖 shell, 跨平台
# ============================================================
class TestLocalDirGroupSafety:
    def test_01_no_shell_invocation(self):
        """实现中不调任何 shell 命令"""
        import inspect
        import app.api.local_api as _api
        src = inspect.getsource(_api.local_dir_group)
        # 不应出现 shell/subprocess/Popen 等危险调用
        assert 'subprocess' not in src
        assert 'os.system' not in src
        assert 'os.popen' not in src
        assert 'shell=True' not in src

    def test_02_path_normalization_via_realpath(self):
        """用 os.path.realpath 规范化路径 (防 symlink 跳目录)"""
        import inspect
        import app.api.local_api as _api
        src = inspect.getsource(_api.local_dir_group)
        assert 'realpath' in src

    def test_03_no_command_injection_surface(self):
        """实现不拼字符串构造命令"""
        import inspect
        import app.api.local_api as _api
        src = inspect.getsource(_api.local_dir_group)
        # 去除 docstring
        if '"""' in src:
            parts = src.split('"""')
            if len(parts) >= 3:
                src_body = '"""'.join(parts[2:])
            else:
                src_body = src
        else:
            src_body = src
        # 旧实现 'ls /data' 字符串不应再出现在代码体
        assert 'ls /data' not in src_body
        # 旧 ls 命令
        assert 'ls ' not in src_body
        # shell 注入
        assert 'shell=True' not in src_body
        assert 'os.system' not in src_body
        assert 'subprocess' not in src_body
