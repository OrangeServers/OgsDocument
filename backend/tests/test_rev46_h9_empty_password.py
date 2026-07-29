# -*- coding: utf-8 -*-
"""REV46-H9: hash_pwd 拒绝空字符串密码测试.

背景:
- 业务问题: password='' -> bcrypt.hashpw(b'', salt) -> 仍合法 hash -> 用户可注册空密码账号
- 修复: hash_pwd 拒绝空字符串密码 (str '' 和 bytes b'')
- 保留语义: None 仍返回 None (字段 NULL 语义)

测试覆盖:
  1) None 行为 (保留: 返回 None)
  2) 空 str 行为 (新增: raise ValueError)
  3) 空 bytes 行为 (新增: raise ValueError)
  4) 正常 str 密码 (保留: 60 字符 hash)
  5) 正常 bytes 密码 (保留: 60 字符 hash)
  6) verify_pwd 正常匹配 (round-trip)
  7) 调用方 user.py 应有完整防御 (业务层 if self.password: 防御)
"""
import os
import re

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)


# ============================================================
# 1) None 行为保留
# ============================================================
class TestRev46H9NoneBehavior:
    """REV46-H9: None 输入仍返回 None (字段 NULL 语义)."""

    def test_01_none_returns_none(self):
        """hash_pwd(None) 返回 None (不是 raise)."""
        from app.tools.basesec import hash_pwd
        assert hash_pwd(None) is None


# ============================================================
# 2) 空字符串 raise (新增防御)
# ============================================================
class TestRev46H9EmptyStringRejected:
    """REV46-H9: 空字符串密码拒绝 (raise ValueError)."""

    def test_01_empty_str_raises_value_error(self):
        """hash_pwd('') 应 raise ValueError."""
        from app.tools.basesec import hash_pwd
        with pytest.raises(ValueError) as exc_info:
            hash_pwd('')
        assert 'empty' in str(exc_info.value).lower() or 'cannot' in str(exc_info.value).lower()

    def test_02_empty_bytes_raises_value_error(self):
        """hash_pwd(b'') 应 raise ValueError."""
        from app.tools.basesec import hash_pwd
        with pytest.raises(ValueError):
            hash_pwd(b'')

    def test_03_empty_str_does_not_call_bcrypt(self):
        """空字符串不应进入 bcrypt.hashpw (防御目的)."""
        # 通过 mock 验证空字符串路径不会调用 bcrypt
        from unittest.mock import patch
        with patch('bcrypt.hashpw') as mock_hash:
            with patch('bcrypt.gensalt', return_value=b'$2b$10$dummy'):
                from app.tools.basesec import hash_pwd
                try:
                    hash_pwd('')
                except ValueError:
                    pass
                # 不应调用 hashpw
                assert mock_hash.call_count == 0, \
                    '空字符串应在调用 bcrypt 前就 raise'


# ============================================================
# 3) 正常密码保留
# ============================================================
class TestRev46H9NormalPasswords:
    """REV46-H9: 正常密码仍可哈希 (业务不破坏)."""

    def test_01_normal_str_returns_60_chars(self):
        """正常 str 密码 -> 60 字符 hash."""
        from app.tools.basesec import hash_pwd
        r = hash_pwd('MySecurePassword123!')
        assert len(r) == 60

    def test_02_normal_bytes_returns_60_chars(self):
        """正常 bytes 密码 -> 60 字符 hash."""
        from app.tools.basesec import hash_pwd
        r = hash_pwd(b'MySecurePassword123!')
        assert len(r) == 60

    def test_03_unicode_password_works(self):
        """Unicode 密码 -> 60 字符 hash."""
        from app.tools.basesec import hash_pwd
        r = hash_pwd('中文密码测试')
        assert len(r) == 60


# ============================================================
# 4) verify_pwd round-trip
# ============================================================
class TestRev46H9VerifyCycle:
    """REV46-H9: hash_pwd 生成的 hash 能被 verify_pwd 验证."""

    def test_01_hash_and_verify_normal_str(self):
        from app.tools.basesec import hash_pwd, verify_pwd
        h = hash_pwd('MyPwd123!')
        matched, _ = verify_pwd('MyPwd123!', h)
        assert matched is True

    def test_02_hash_and_verify_normal_bytes(self):
        from app.tools.basesec import hash_pwd, verify_pwd
        h = hash_pwd(b'MyPwd123!')
        matched, _ = verify_pwd(b'MyPwd123!', h)
        assert matched is True

    def test_03_wrong_password_does_not_match(self):
        from app.tools.basesec import hash_pwd, verify_pwd
        h = hash_pwd('correct_pwd')
        matched, _ = verify_pwd('wrong_pwd', h)
        assert matched is False


# ============================================================
# 5) basesec.py 静态分析
# ============================================================
class TestRev46H9StaticAnalysis:
    """REV46-H9: basesec.py 应含防御逻辑和 REV46-H9 标记."""

    BASECEC_PY = os.path.join(_BACKEND, 'app', 'tools', 'basesec.py')

    def _read_hash_pwd_body(self):
        """读取 hash_pwd 函数体 (跳过 docstring)."""
        with open(self.BASECEC_PY, encoding='utf-8') as f:
            src = f.read()
        # 匹配 def hash_pwd(...): """docstring...""" body (直到下一个 def 或 class 或 EOF)
        # 注意: 兼容 type hint 签名 `def f(args) -> ReturnType:`
        m = re.search(
            r'def\s+hash_pwd\s*\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*"""[\s\S]*?"""\s*([\s\S]*?)(?=\ndef\s|\nclass\s|\Z)',
            src,
        )
        assert m, 'hash_pwd 函数体缺失 (含 docstring)'
        return m.group(1)

    def test_01_hash_pwd_docstring_mentions_rev46_h9(self):
        """hash_pwd docstring 应提及 REV46-H9."""
        with open(self.BASECEC_PY, encoding='utf-8') as f:
            src = f.read()
        m = re.search(
            r'def\s+hash_pwd\s*\([^)]*\)\s*(?:->\s*[^:]+)?\s*:\s*\n\s*"""([\s\S]*?)"""',
            src,
        )
        assert m, 'hash_pwd 函数定义缺失'
        docstring = m.group(1)
        assert 'REV46-H9' in docstring

    def test_02_hash_pwd_rejects_empty(self):
        """hash_pwd 函数体应含空校验逻辑."""
        body = self._read_hash_pwd_body()
        # 检查有 if not password: 或 password == '' 防御 (REV47-M14 后参数名可能为 plain)
        assert re.search(r'if\s+not\s+(password|plain)\s*:|(password|plain)\s*==\s*[\'"]\s*[\'"]', body), \
            'hash_pwd 应有空密码防御, body=%s' % body[:200]

    def test_03_hash_pwd_raises_value_error(self):
        """hash_pwd 应有 raise ValueError."""
        body = self._read_hash_pwd_body()
        assert 'raise ValueError' in body, 'hash_pwd body 应有 raise ValueError, body=%s' % body[:200]

    def test_04_hash_pwd_error_message_mentions_empty(self):
        """ValueError 消息应含 'empty' 提示."""
        body = self._read_hash_pwd_body()
        m2 = re.search(r"raise\s+ValueError\s*\(\s*['\"]([^'\"]*)['\"]", body)
        assert m2, 'hash_pwd body 应有 raise ValueError(\'...\') 形式'
        msg = m2.group(1).lower()
        assert 'empty' in msg or 'cannot' in msg


# ============================================================
# 6) 业务调用方防御
# ============================================================
class TestRev46H9BusinessCallerDefense:
    """REV46-H9: 业务层 user.py 应有完整防御 (多层防御)."""

    USER_PY = os.path.join(_BACKEND, 'app', 'users', 'user.py')

    def test_01_update_path_has_if_password_defense(self):
        """user.py 改密码路径 (line ~550) 应有 `if self.password:` 防御."""
        with open(self.USER_PY, encoding='utf-8') as f:
            src = f.read()
        # 寻找: if self.password:\n    update_kwargs['password'] = hash_pwd(self.password)
        # 模式: 防御后调用 hash_pwd
        pattern = re.compile(
            r'if\s+self\.password\s*:[\s\S]{0,200}hash_pwd\s*\(\s*self\.password\s*\)',
        )
        assert pattern.search(src), \
            'user.py 应有 `if self.password:` 防御后调用 hash_pwd'

    def test_02_update_kwargs_skips_password_when_empty(self):
        """改密码路径: 空密码时不更新 password 字段."""
        with open(self.USER_PY, encoding='utf-8') as f:
            src = f.read()
        # 检查防御: if self.password: ... else 跳过 password
        m = re.search(
            r'if\s+self\.password\s*:\s*\n\s*update_kwargs\[[\'"]password[\'"]\]\s*=\s*hash_pwd',
            src,
        )
        assert m, 'user.py 应有 if self.password: update_kwargs[\'password\'] = hash_pwd 模式'

    def test_03_register_and_create_user_have_password(self):
        """注册/创建用户路径: hash_pwd(self.password) 调用."""
        with open(self.USER_PY, encoding='utf-8') as f:
            src = f.read()
        # 至少有 1 处注册路径: osql_in(..., password=hash_pwd(self.password), ...)
        assert re.search(
            r"password\s*=\s*hash_pwd\s*\(\s*self\.password\s*\)",
            src,
        ), 'user.py 应有 password=hash_pwd(self.password) 注册模式'


# ============================================================
# 7) error_message 含 'empty'
# ============================================================
class TestRev46H9ErrorMessage:
    """REV46-H9: ValueError 消息清晰."""

    def test_01_value_error_msg_is_clear(self):
        """ValueError 消息含 'empty' 让调用方能识别."""
        from app.tools.basesec import hash_pwd
        try:
            hash_pwd('')
        except ValueError as e:
            msg = str(e).lower()
            assert 'empty' in msg or '空' in msg


# ============================================================
# 8) 集成：业务调用栈仍兼容
# ============================================================
class TestRev46H9Integration:
    """REV46-H9: hash_pwd 与 user.py 业务调用栈兼容."""

    def test_01_hash_pwd_callable(self):
        """hash_pwd 是可调用."""
        from app.tools.basesec import hash_pwd
        assert callable(hash_pwd)

    def test_02_hash_pwd_normal_flow_unchanged(self):
        """正常密码 hash 流程不变 (业务不破坏)."""
        from app.tools.basesec import hash_pwd, verify_pwd
        for pwd in ['a', 'long_password_123', '中文密码', b'bytes_pwd']:
            h = hash_pwd(pwd)
            assert len(h) == 60, '密码 %r hash 长度应为 60' % pwd
            matched, _ = verify_pwd(pwd, h)
            assert matched, '密码 %r 应能 verify 匹配' % pwd

    def test_03_empty_str_blocks_registration_simulation(self):
        """模拟注册: 空密码被 basesec 拦截."""
        from app.tools.basesec import hash_pwd
        # 模拟前端漏校验, 业务层仍走到 hash_pwd
        with pytest.raises(ValueError):
            hash_pwd('')