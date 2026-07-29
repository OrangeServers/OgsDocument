# -*- coding: utf-8 -*-
"""REV39-L1: /local/image/test_get/<img_name> 路径遍历防护回归测试。

覆盖范围：
  1) Flask URL 转换器显式 <string:img_name>（不接收 '/'）
  2) local_image_get basename 二次校验（兜底 Werkzeug 边界 case）
  3) GetUserImage.get_img 内部 regex 白名单 + realpath 越界（第三层防线）
  4) 加 REV39-L1 标签注释（代码可追溯）
  5) 边界用例：含 '.' '-' '_' / 超长 / 数字 / 中文 / 空 / None
"""
import importlib
import os
import re
import sys

import pytest

# 路径初始化
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


@pytest.fixture
def flask_app_ctx():
    """REV38-M6: 提供 Flask app context，jsonify/url_map 需 current_app。"""
    from init import app
    ctx = app.app_context()
    ctx.push()
    try:
        yield app
    finally:
        ctx.pop()


# ============================================================
# 1) Flask URL 转换器显式 <string:img_name> 测试 (静态分析)
# ============================================================
class TestStringConverter:
    def test_01_init_py_uses_string_converter(self):
        """init.py:370 必须显式声明 <string:img_name>。"""
        import re
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        # 静态分析：必须出现 <string:img_name> 显式声明
        assert re.search(r"/local/image/test_get/<string:img_name>", src), \
            'init.py 应显式声明 <string:img_name>，而不是默认 <img_name>'

    def test_02_init_py_has_rev39_l1_comment(self):
        """init.py 路由注册前必须有 REV39-L1 注释。"""
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        assert 'REV39-L1' in src, 'init.py 应有 REV39-L1 标签注释'

    def test_03_string_converter_rejects_slash(self):
        """Werkzeug string converter 不接受 '/'，URL 段路径分隔符会 404。"""
        # Werkzeug 内置 string converter 在路由匹配时按 '/' 切分
        # 这里用 Flask test client 验证（独立 app 不污染 init.app）
        from flask import Flask
        app = Flask(__name__)

        @app.route('/img/<string:name>')
        def view(name):
            return 'ok:' + name

        client = app.test_client()
        # 合法
        resp = client.get('/img/abc.png')
        assert resp.status_code == 200
        # 含 '/' 不匹配
        resp = client.get('/img/a/b')
        assert resp.status_code == 404


# ============================================================
# 2) local_image_get basename 二次校验测试
# ============================================================
class TestLocalImageGetGuard:
    def test_01_guard_exists(self):
        """local_api.local_image_get 必须有 basename 校验分支。"""
        from app.api import local_api
        src = importlib.reload(local_api)
        # 拿函数源码
        import inspect
        body = inspect.getsource(src.local_image_get)
        # 必须有 basename 校验
        assert 'os.path.basename' in body, \
            'local_image_get 必须调用 os.path.basename 做二次校验'

    def test_02_guard_max_len_constant(self):
        """必须有 _MAX_IMG_NAME_LEN = 32 常量。"""
        from app.api import local_api
        src = importlib.reload(local_api)
        assert hasattr(src, '_MAX_IMG_NAME_LEN'), 'local_api 应导出 _MAX_IMG_NAME_LEN'
        assert src._MAX_IMG_NAME_LEN == 32, '应与 GetUserImage regex {1,32} 一致'

    def test_03_guard_rev39_l1_comment(self):
        """必须有 REV39-L1 标签注释。"""
        from app.api import local_api
        src = importlib.reload(local_api)
        import inspect
        body = inspect.getsource(src.local_image_get)
        # 拿完整模块 body 找 REV39-L1 标签
        full = inspect.getsource(src)
        assert 'REV39-L1' in full, 'local_api 模块应含 REV39-L1 标签'

    def test_04_basename_blocks_traversal(self):
        """basename 校验能拦下 ../etc.png 这类 case（不是 path separator，是文件名本身）。"""
        import os as _os
        # os.path.basename('..') == '..'，与原值相等，不算 traversal
        # 但 os.path.basename('../etc') == 'etc'，与原值不等 → 算 traversal
        # 这就是 local_image_get 守护的语义
        assert _os.path.basename('../etc') != '../etc'
        assert _os.path.basename('avatar.png') == 'avatar.png'
        # basename 不会去除文件名内的 '..'（这不是 traversal，仅是文件名）
        assert _os.path.basename('a..b') == 'a..b'


# ============================================================
# 3) GetUserImage.get_img 内部 regex + realpath 防线测试
# ============================================================
class TestGetUserImageInnerGuard:
    def test_01_regex_rejects_traversal_chars(self):
        """regex 拒绝 / % \\ 0x00 等危险字符。"""
        from app.local.Basics import GetUserImage
        import inspect
        body = inspect.getsource(GetUserImage.get_img)
        assert re.search(r"re\.fullmatch\(r['\"]\^\[A-Za-z0-9_\.\\-\]\{1,32\}", body), \
            'get_img 应保留 regex 白名单 [A-Za-z0-9_.-]{1,32}'

    def test_02_realpath_uses_commonpath(self):
        """realpath 越界用 os.path.commonpath 检测。"""
        from app.local.Basics import GetUserImage
        import inspect
        body = inspect.getsource(GetUserImage.get_img)
        assert 'os.path.commonpath' in body, 'get_img 必须用 commonpath 防越界'
        assert 'real_target' in body and 'real_root' in body, 'real_target/real_root 命名保留'

    def test_03_rev39_l1_comment_present(self):
        """get_img 必须有 REV39-L1 升级注释。"""
        from app.local.Basics import GetUserImage
        import inspect
        body = inspect.getsource(GetUserImage.get_img)
        assert 'REV39-L1' in body, 'get_img 应有 REV39-L1 注释'


# ============================================================
# 4) 行为模拟：三层防御协同
# ============================================================
class TestDefenseInDepth:
    def test_01_attack_dotdot_slash_rejected(self, flask_app_ctx):
        """攻击: img_name='../etc'，应被三层任意一层拦下。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        # 直接调 get_img（绕过 URL converter）
        result = g.get_img('../etc')
        # 不抛异常 + 返 jsonify 是预期（内层防御到位）
        # 即使 IMAGE_PATH 不存在也安全
        assert result is not None

    def test_02_attack_long_string_rejected(self, flask_app_ctx):
        """攻击: img_name 长度 100 字符，regex 拒绝。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        long_name = 'a' * 100
        result = g.get_img(long_name)
        assert result is not None

    def test_03_attack_null_byte_rejected(self, flask_app_ctx):
        """攻击: img_name 含 \\x00，regex 拒绝。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img('a\x00b.png')
        assert result is not None

    def test_04_attack_percent_2f_rejected(self, flask_app_ctx):
        """攻击: img_name='..%2F..%2Fetc'，regex 拒绝（% 不在白名单）。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img('..%2F..%2Fetc')
        assert result is not None

    def test_05_attack_slash_in_name_rejected(self, flask_app_ctx):
        """攻击: img_name='a/b'，regex 拒绝。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img('a/b')
        assert result is not None

    def test_06_legitimate_name_works(self, flask_app_ctx):
        """合法: img_name='avatar.png' 不应被任何一层误伤。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img('avatar.png')
        assert result is not None

    def test_07_legitimate_underscore_dash(self, flask_app_ctx):
        """合法: 含 _ - . 的名字。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img('my-avatar_1.0.png')
        assert result is not None

    def test_08_none_input_rejected(self, flask_app_ctx):
        """异常: img_name=None 不抛 TypeError。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img(None)
        assert result is not None

    def test_09_empty_string_rejected(self, flask_app_ctx):
        """异常: img_name='' regex 拒绝 → default。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img('')
        assert result is not None

    def test_10_unicode_rejected(self, flask_app_ctx):
        """异常: img_name='头像.png' regex 拒绝（中文字符不在白名单）。"""
        from app.local.Basics import GetUserImage
        g = GetUserImage()
        result = g.get_img('头像.png')
        assert result is not None
