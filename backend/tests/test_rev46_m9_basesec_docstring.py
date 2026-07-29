# -*- coding: utf-8 -*-
"""REV46-M9: basesec.py dummy_verify_pwd docstring 路径错引用修复测试.

背景:
- basesec.py:130 原引用 `d:/code/ogs198/pycharm_ogsbackend/app/foo/user/user.py`
  是历史 IDE 路径, 不在 OrangeServer 当前仓库, 文档可读性/可点击性失效.
- 修复: 改为 OrangeServer 当前正确路径 `d:/code/OrangeServer/backend/app/users/user.py`.
- 评审优先级: P0 (文档正确性 + 新人 onboarding 阻塞).

测试覆盖:
  1) basesec.py 不再含旧错路径 (ogs198/pycharm_ogsbackend)
  2) basesec.py 含新正确路径 (OrangeServer/backend/app/users/user.py)
  3) docstring 中 dummy_verify_pwd 描述一致
  4) REV46-M9 标记注释存在
  5) dummy_verify_pwd 函数行为未变 (调用仍正常)
  6) 调用方 user.py 仍在 login_dl 方法中调用 dummy_verify_pwd (确认引用未失效)
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_BASESEC = os.path.join(_BACKEND, 'app', 'tools', 'basesec.py')
_USER_PY = os.path.join(_BACKEND, 'app', 'users', 'user.py')

# 旧错路径 (历史 IDE 路径, 应被清除)
_OLD_WRONG_PATH = 'd:/code/ogs198/pycharm_ogsbackend'
# 新正确路径
_NEW_RIGHT_PATH = 'd:/code/OrangeServer/backend/app/users/user.py'


def _read_basesec():
    with open(_BASESEC, encoding='utf-8') as f:
        return f.read()


def _read_user_py():
    with open(_USER_PY, encoding='utf-8') as f:
        return f.read()


# ============================================================
# 1) 旧错路径已清除
# ============================================================
class TestRev46M9OldPathRemoved:
    """REV46-M9: basesec.py 不再含旧错路径."""

    def test_01_no_old_ogs198_path(self):
        """basesec.py 不再含 d:/code/ogs198/... 旧路径 (修复标记行除外)."""
        src = _read_basesec()
        # 把所有 docstring 内容提取出来 (用 triple-quote 匹配)
        docstrings = re.findall(r'"""([\s\S]*?)"""', src)
        for ds in docstrings:
            # REV46-M9 修复标记行 (说明原因) 应允许提及旧路径
            ds_without_marker = re.sub(r'REV46-M9[^\n]*\n?', '', ds)
            assert 'ogs198' not in ds_without_marker, \
                'docstring 中 (修复标记外) 不应含旧 IDE 路径 (ogs198)'
            assert 'pycharm_ogsbackend' not in ds_without_marker, \
                'docstring 中 (修复标记外) 不应含 pycharm_ogsbackend 旧 IDE 路径'

    def test_02_no_foo_user_user_py(self):
        """basesec.py 不再含 foo/user/user.py (旧项目结构)."""
        src = _read_basesec()
        docstrings = re.findall(r'"""([\s\S]*?)"""', src)
        for ds in docstrings:
            ds_without_marker = re.sub(r'REV46-M9[^\n]*\n?', '', ds)
            assert 'foo/user/user.py' not in ds_without_marker, \
                'docstring 中 (修复标记外) 不应含 foo/user/user.py 旧项目结构路径'

    def test_03_dummy_verify_pwd_docstring_clean(self):
        """dummy_verify_pwd 的 docstring (修复标记外) 不含旧路径."""
        src = _read_basesec()
        # 找 dummy_verify_pwd 函数的 docstring
        m = re.search(
            r'def\s+dummy_verify_pwd\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*"""([\s\S]*?)"""',
            src,
        )
        assert m, '应找到 dummy_verify_pwd docstring'
        docstring = m.group(1)
        # 修复标记行允许提及旧路径
        docstring_clean = re.sub(r'REV46-M9[^\n]*\n?', '', docstring)
        assert _OLD_WRONG_PATH not in docstring_clean
        assert 'pycharm_ogsbackend' not in docstring_clean


# ============================================================
# 2) 新正确路径已添加
# ============================================================
class TestRev46M9NewPathAdded:
    """REV46-M9: basesec.py 含新正确路径."""

    def test_01_has_orange_server_path(self):
        """basesec.py 应含 d:/code/OrangeServer/backend/app/users/user.py."""
        src = _read_basesec()
        assert 'OrangeServer' in src, \
            'basesec.py 应含 OrangeServer 路径'
        assert 'app/users/user.py' in src, \
            'basesec.py 应含 app/users/user.py 路径'

    def test_02_dummy_verify_pwd_docstring_has_new_path(self):
        """dummy_verify_pwd 的 docstring 应含新正确路径."""
        src = _read_basesec()
        # 兼容 type hint 签名 `def f(args) -> ReturnType:`
        m = re.search(
            r'def\s+dummy_verify_pwd\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*"""([\s\S]*?)"""',
            src,
        )
        assert m
        docstring = m.group(1)
        assert _NEW_RIGHT_PATH in docstring, \
            'dummy_verify_pwd docstring 应含新正确路径: %s' % _NEW_RIGHT_PATH
        # 也应是 markdown link 格式
        assert re.search(r'\[user\.py:[^]]+\]\(file:///' + re.escape(_NEW_RIGHT_PATH) + r'\)', docstring), \
            'dummy_verify_pwd docstring 应是 Markdown link 格式'

    def test_03_uses_file_protocol(self):
        """Markdown link 应使用 file:// 协议 (Qoder IDE 可点击)."""
        src = _read_basesec()
        m = re.search(
            r'def\s+dummy_verify_pwd\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*"""([\s\S]*?)"""',
            src,
        )
        docstring = m.group(1)
        assert 'file:///' in docstring, \
            'dummy_verify_pwd docstring 应使用 file:/// 协议'

    def test_04_callsite_ref_user_py_login_dl(self):
        """引用文本应是 user.py:login_dl (定位具体方法)."""
        src = _read_basesec()
        m = re.search(
            r'def\s+dummy_verify_pwd\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*"""([\s\S]*?)"""',
            src,
        )
        docstring = m.group(1)
        assert 'user.py:login_dl' in docstring, \
            'dummy_verify_pwd docstring 应引用 user.py:login_dl 方法'


# ============================================================
# 3) REV46-M9 标记注释
# ============================================================
class TestRev46M9Marker:
    """REV46-M9: 修复标记."""

    def test_01_has_rev46_m9_marker(self):
        """basesec.py 应含 REV46-M9 标记."""
        src = _read_basesec()
        assert 'REV46-M9' in src, \
            'basesec.py 应含 REV46-M9 修复标记'

    def test_02_marker_near_dummy_verify_pwd(self):
        """REV46-M9 标记应靠近 dummy_verify_pwd 函数 (便于追溯)."""
        src = _read_basesec()
        idx_func = src.find('def dummy_verify_pwd')
        idx_marker = src.find('REV46-M9')
        assert idx_func >= 0 and idx_marker >= 0
        # 标记应在函数 docstring 内或函数定义前 200 字符内
        assert abs(idx_marker - idx_func) < 500, \
            'REV46-M9 标记应在 dummy_verify_pwd 函数附近 (实际距离 %d)' % abs(idx_marker - idx_func)

    def test_03_marker_documents_old_path_change(self):
        """REV46-M9 标记应说明路径变更 (ogs198 → OrangeServer)."""
        src = _read_basesec()
        m = re.search(r'REV46-M9[^\n]*', src)
        assert m
        marker_text = m.group(0)
        # 应说明旧路径是错的
        assert 'ogs198' in marker_text or 'pycharm_ogsbackend' in marker_text or '错' in marker_text or '旧' in marker_text, \
            'REV46-M9 标记应说明路径变更原因'


# ============================================================
# 4) dummy_verify_pwd 函数行为未变
# ============================================================
class TestRev46M9FunctionBehavior:
    """REV46-M9: dummy_verify_pwd 函数行为不变 (仅修注释)."""

    def test_01_dummy_verify_pwd_with_none(self):
        """dummy_verify_pwd(None) 不抛异常."""
        from app.tools.basesec import dummy_verify_pwd
        # 不应抛异常
        dummy_verify_pwd(None)

    def test_02_dummy_verify_pwd_with_empty(self):
        """dummy_verify_pwd('') 不抛异常."""
        from app.tools.basesec import dummy_verify_pwd
        dummy_verify_pwd('')

    def test_03_dummy_verify_pwd_with_normal_password(self):
        """dummy_verify_pwd('password') 不抛异常."""
        from app.tools.basesec import dummy_verify_pwd
        dummy_verify_pwd('test_password')

    def test_04_dummy_verify_pwd_with_bytes(self):
        """dummy_verify_pwd(b'bytes') 不抛异常."""
        from app.tools.basesec import dummy_verify_pwd
        dummy_verify_pwd(b'test_bytes')

    def test_05_dummy_verify_pwd_no_return(self):
        """dummy_verify_pwd 无返回值 (None)."""
        from app.tools.basesec import dummy_verify_pwd
        result = dummy_verify_pwd('password')
        assert result is None

    def test_06_docstring_still_describes_behavior(self):
        """docstring 仍描述 dummy_verify_pwd 的行为 (耗时对齐/不接受 None)."""
        src = _read_basesec()
        m = re.search(
            r'def\s+dummy_verify_pwd\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*"""([\s\S]*?)"""',
            src,
        )
        docstring = m.group(1)
        # 行为描述保留
        assert '不返回结果' in docstring or '无返回值' in docstring, \
            'docstring 应说明 dummy_verify_pwd 不返回结果'
        assert 'None' in docstring or '空串' in docstring, \
            'docstring 应说明 dummy_verify_pwd 接受 None/空串'
        assert '耗时' in docstring or '对齐' in docstring, \
            'docstring 应说明 dummy_verify_pwd 是耗时对齐'

    def test_07_callable_exists(self):
        """dummy_verify_pwd 函数可调用."""
        from app.tools import basesec
        assert callable(basesec.dummy_verify_pwd)


# ============================================================
# 5) 调用方 user.py 验证 (引用未失效)
# ============================================================
class TestRev46M9CallsiteValid:
    """REV46-M9: docstring 引用 user.py:login_dl 应真实存在."""

    def test_01_user_py_exists(self):
        """user.py 文件存在."""
        assert os.path.exists(_USER_PY)

    def test_02_user_py_has_login_dl_method(self):
        """user.py 应有 login_dl 方法 (docstring 引用目标)."""
        src = _read_user_py()
        # 找 def login_dl(self):
        m = re.search(r'def\s+login_dl\s*\(\s*self\s*\)', src)
        assert m, 'user.py 应有 login_dl 方法'

    def test_03_user_py_calls_dummy_verify_pwd(self):
        """user.py login_dl 应调用 dummy_verify_pwd (引用目标真实)."""
        src = _read_user_py()
        # 在 login_dl 函数体内找 dummy_verify_pwd 调用
        m = re.search(r'def\s+login_dl\s*\(\s*self\s*\)([\s\S]*?)(?=\n    def\s|\Z)', src)
        assert m
        body = m.group(1)
        assert 'dummy_verify_pwd' in body, \
            'user.py login_dl 应调用 dummy_verify_pwd'

    def test_04_user_py_has_user_info_is_none_branch(self):
        """user.py login_dl 应有用户名不存在分支 (docstring 描述场景).

        实际代码用 `else:` 分支 (user_info 为 None 时走 else),
        注释明确说 '用户名不存在'.
        """
        src = _read_user_py()
        m = re.search(r'def\s+login_dl\s*\(\s*self\s*\)([\s\S]*?)(?=\n    def\s|\Z)', src)
        body = m.group(1)
        # 业务上有 '用户名不存在' 注释
        assert '用户名不存在' in body, \
            'user.py login_dl 应有 "用户名不存在" 分支注释'
        # 或显式 is None 检查
        assert 'is None' in body or 'else' in body, \
            'user.py login_dl 应有 is None/else 分支'

    def test_05_dummy_verify_pwd_in_user_not_found_branch(self):
        """dummy_verify_pwd 应在用户名不存在分支内调用 (防枚举).

        实际结构: if user_info is not None: (用户存在走密码校验) else: (用户不存在走 dummy_verify_pwd)
        """
        src = _read_user_py()
        # 找 if user_info is not None: 块
        m_if = re.search(
            r'(if\s+user_info\s+is\s+not\s+None\s*:[\s\S]{0,300})',
            src,
        )
        assert m_if, 'user.py 应有 if user_info is not None: 分支'
        # dummy_verify_pwd 应在 else 分支 (即 if user_info is not None 块结束之后)
        m_else = re.search(
            r'else\s*:[\s\S]{0,500}dummy_verify_pwd',
            src,
        )
        assert m_else, \
            'dummy_verify_pwd 应在 else 分支内 (用户名不存在场景, 防枚举)'


# ============================================================
# 6) 路径修复扫描 (确保其他文件没有重复的 REV46-M9 模式 bug)
# ============================================================
class TestRev46M9PathSanityCheck:
    """REV46-M9: 检查 basesec.py 是否还有其他错路径."""

    def test_01_no_old_ogsbackend_path(self):
        """basesec.py 不再含 ogscbackend/pycharm_ogsbackend 旧路径 (修复标记外)."""
        src = _read_basesec()
        # 检查所有 docstring 不含旧路径 (修复标记除外)
        for match in re.finditer(r'"""([\s\S]*?)"""', src):
            docstring = match.group(1)
            docstring_clean = re.sub(r'REV46-M9[^\n]*\n?', '', docstring)
            assert 'ogs198' not in docstring_clean, \
                'docstring 中 (修复标记外) 不应含旧 IDE 路径'
            assert 'pycharm_ogsbackend' not in docstring_clean

    def test_02_path_format_consistent(self):
        """新路径格式一致 (d:/code/OrangeServer/...)."""
        src = _read_basesec()
        # 找所有 file:/// 引用
        for match in re.finditer(r'file:///([^)\s]+)', src):
            path = match.group(1)
            # 应是绝对路径
            assert path.startswith('d:/') or path.startswith('/') or path.startswith('C:/'), \
                'file:/// 路径应是绝对路径, 实际: %s' % path

    def test_03_dummy_verify_pwd_docstring_complete(self):
        """dummy_verify_pwd docstring 应完整保留原信息 + 新路径."""
        src = _read_basesec()
        m = re.search(
            r'def\s+dummy_verify_pwd\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*"""([\s\S]*?)"""',
            src,
        )
        docstring = m.group(1)
        # 完整保留: 不返回结果 + 接受 None/空串 + 恒定时长
        assert '不返回结果' in docstring
        assert 'None/空串' in docstring or 'None' in docstring
        assert '恒定时长' in docstring or '时延' in docstring
        # 新增: 正确路径
        assert _NEW_RIGHT_PATH in docstring