# -*- coding: utf-8 -*-
"""REV47-T2: 跨模块路径安全工具测试.

覆盖:
  1. app/tools/pathsec.py:safe_join 纯函数 (合法/越界/..穿越/symlink)
  2. app/tools/pathsec.py:safe_remote_path 纯函数 (合法/越界/../NUL)
  3. app/ssh/sftp.py:_safe_join + _safe_sftp_path 委托验证
  4. app/tools/shellcmd.py:_safe_remote_path 委托验证
"""
import os
import inspect
from unittest.mock import patch

import pytest


# =============================================================================
# TestSafeJoinPure: 通用路径拼接 (防 symlink 越狱)
# =============================================================================
class TestSafeJoinPure:
    """pathsec.safe_join 纯函数测试."""

    def test_valid_join_returns_realpath(self, tmp_path):
        from app.tools.pathsec import safe_join
        result = safe_join(str(tmp_path), 'file.txt')
        assert result is not None
        assert result == os.path.realpath(str(tmp_path / 'file.txt'))

    def test_nested_path_join(self, tmp_path):
        from app.tools.pathsec import safe_join
        sub = tmp_path / 'sub'
        sub.mkdir()
        result = safe_join(str(tmp_path), 'sub/team.txt')
        assert result is not None
        assert result == os.path.realpath(str(tmp_path / 'sub' / 'team.txt'))

    def test_path_traversal_returns_none(self, tmp_path):
        from app.tools.pathsec import safe_join
        # ../ 越界
        assert safe_join(str(tmp_path), '../etc/passwd') is None
        assert safe_join(str(tmp_path), 'a/../../etc/passwd') is None

    def test_absolute_path_returns_none(self, tmp_path):
        """绝对路径越界 → None (因为不在 base 下)."""
        import platform
        from app.tools.pathsec import safe_join
        if platform.system() == 'Windows':
            abs_path = 'C:\\Windows\\System32\\drivers\\etc\\hosts'
        else:
            abs_path = '/etc/passwd'
        # 绝对路径与 tmp_path 是不同盘 (Windows) 或绝对 (Unix), commonpath 不一致 → None
        assert safe_join(str(tmp_path), abs_path) is None

    def test_non_string_input_returns_none(self, tmp_path):
        from app.tools.pathsec import safe_join
        assert safe_join(None, 'file') is None
        assert safe_join(str(tmp_path), None) is None
        assert safe_join(123, 'file') is None

    def test_symlink_outside_base_returns_none(self, tmp_path):
        """symlink 指向 base 外 → None (关键安全测试)."""
        from app.tools.pathsec import safe_join
        link = tmp_path / 'evil'
        try:
            # 在 tmp_path 外创建一个目标, symlink 指向它
            outside = tmp_path.parent / 'outside_target'
            outside.touch()
            os.symlink(str(outside), str(link))
        except (OSError, NotImplementedError):
            pytest.skip('symlink not supported')

        result = safe_join(str(tmp_path), 'evil')
        # symlink realpath 指向 base 外 → None
        assert result is None


# =============================================================================
# TestSafeRemotePathPure: 远程路径白名单
# =============================================================================
class TestSafeRemotePathPure:
    """pathsec.safe_remote_path 纯函数测试."""

    @pytest.fixture
    def prefixes(self):
        return ('/home/', '/tmp/', '/var/upload/')

    def test_valid_path_returns_normpath(self, prefixes):
        from app.tools.pathsec import safe_remote_path
        result = safe_remote_path('/home/alice/file.txt', prefixes)
        assert result == os.path.normpath('/home/alice/file.txt')

    def test_path_not_in_prefixes_raises(self, prefixes):
        from app.tools.pathsec import safe_remote_path
        with pytest.raises(ValueError, match='not in allowed prefixes'):
            safe_remote_path('/etc/passwd', prefixes)

    def test_path_traversal_raises(self, prefixes):
        from app.tools.pathsec import safe_remote_path
        with pytest.raises(ValueError, match='path traversal forbidden'):
            safe_remote_path('/home/../etc/passwd', prefixes)
        with pytest.raises(ValueError, match='path traversal forbidden'):
            safe_remote_path('/home/alice/../../etc/passwd', prefixes)

    def test_nul_char_raises(self, prefixes):
        from app.tools.pathsec import safe_remote_path
        with pytest.raises(ValueError, match='NUL char'):
            safe_remote_path('/home/alice/\x00evil', prefixes)

    def test_non_string_raises(self, prefixes):
        from app.tools.pathsec import safe_remote_path
        with pytest.raises(ValueError, match='path must be a string'):
            safe_remote_path(None, prefixes)
        with pytest.raises(ValueError, match='path must be a string'):
            safe_remote_path(123, prefixes)

    def test_prefix_match_is_startswith(self, prefixes):
        """'/home2/' 不应匹配 '/home/' 前缀 (startswith 严格)."""
        from app.tools.pathsec import safe_remote_path
        with pytest.raises(ValueError, match='not in allowed prefixes'):
            safe_remote_path('/home2/alice/file.txt', prefixes)


# =============================================================================
# TestSftpDelegation: sftp._safe_join + _safe_sftp_path 委托
# =============================================================================
class TestSftpDelegation:
    """REV47-T2: sftp 委托给 pathsec 统一实现."""

    def test_sftp_safe_join_delegates(self):
        from app.ssh import sftp
        from app.tools import pathsec
        assert getattr(sftp._safe_join, '__wrapped__', None) is pathsec.safe_join, \
            "REV47-T2: sftp._safe_join 应委托给 pathsec.safe_join"

    def test_sftp_safe_join_top_level_import(self):
        from app.ssh import sftp
        from app.tools import pathsec
        assert sftp.safe_join is pathsec.safe_join, \
            "REV47-T2: sftp 模块顶层 import safe_join 应该是 pathsec.safe_join"

    def test_sftp_safe_sftp_path_delegates(self):
        from app.ssh import sftp
        from app.tools import pathsec
        assert getattr(sftp._safe_sftp_path, '__wrapped__', None) is pathsec.safe_remote_path, \
            "REV47-T2: sftp._safe_sftp_path 应委托给 pathsec.safe_remote_path"

    def test_sftp_safe_sftp_path_validation_inherited(self):
        """_safe_sftp_path 继承 pathsec.safe_remote_path 的所有安全约束."""
        from app.ssh import sftp
        # 非字符串
        with pytest.raises(ValueError, match='path must be a string'):
            sftp._safe_sftp_path(None)
        # 越界
        with pytest.raises(ValueError, match='not in allowed prefixes'):
            sftp._safe_sftp_path('/etc/passwd')
        # 穿越
        with pytest.raises(ValueError, match='path traversal forbidden'):
            sftp._safe_sftp_path('/home/../etc/passwd')


# =============================================================================
# TestShellcmdDelegation: shellcmd._safe_remote_path 委托
# =============================================================================
class TestShellcmdDelegation:
    """REV47-T2: shellcmd._safe_remote_path 委托给 pathsec.safe_remote_path."""

    def test_shellcmd_safe_remote_path_delegates(self):
        from app.tools import shellcmd
        from app.tools import pathsec
        assert getattr(shellcmd._safe_remote_path, '__wrapped__', None) is pathsec.safe_remote_path, \
            "REV47-T2: shellcmd._safe_remote_path 应委托给 pathsec.safe_remote_path"

    def test_shellcmd_safe_remote_path_top_level_import(self):
        from app.tools import shellcmd
        from app.tools import pathsec
        assert shellcmd.safe_remote_path is pathsec.safe_remote_path, \
            "REV47-T2: shellcmd 模块顶层 import safe_remote_path 应该是 pathsec.safe_remote_path"

    def test_shellcmd_safe_remote_path_validation_inherited(self):
        """_safe_remote_path 继承同样的安全约束 (使用 shellcmd 自己的 _REMOTE_PATH_ALLOWED_PREFIXES)."""
        from app.tools import shellcmd
        # 越界 (不在 shellcmd 白名单的 /home 等) - /etc 不在 shellcmd 白名单
        with pytest.raises(ValueError, match='not in allowed prefixes'):
            shellcmd._safe_remote_path('/etc/passwd')
        # 穿越
        with pytest.raises(ValueError, match='path traversal forbidden'):
            shellcmd._safe_remote_path('/home/../etc/passwd')

    def test_shellcmd_safe_remote_path_accepts_home(self):
        """shellcmd 的白名单包含 /home/, /tmp/ 等 — 应接受这些前缀."""
        from app.tools import shellcmd
        # shellcmd 白名单包含 /home/
        result = shellcmd._safe_remote_path('/home/alice/file.txt')
        assert result == os.path.normpath('/home/alice/file.txt')


# =============================================================================
# TestRev47T2Marker: 注释/import 标记
# =============================================================================
class TestRev47T2Marker:
    """REV47-T2 修复必须显式 import pathsec + 注释标记."""

    def test_pathsec_module_exists(self):
        import app.tools.pathsec as _mod
        assert hasattr(_mod, 'safe_join'), "pathsec.safe_join 必须存在"
        assert hasattr(_mod, 'safe_remote_path'), "pathsec.safe_remote_path 必须存在"

    def test_pathsec_has_rev47_t2_marker(self):
        import inspect
        from app.tools import pathsec
        source = inspect.getsource(pathsec)
        assert 'REV47-T2' in source, "pathsec.py 必须有 REV47-T2 标记注释"
        assert 'REV40' in source, "pathsec.py 应引用 REV40 (历史来源)"
        assert 'REV46' in source, "pathsec.py 应引用 REV46 (历史来源)"

    def test_sftp_imports_pathsec(self):
        from app.ssh import sftp
        from app.tools import pathsec
        assert sftp.safe_join is pathsec.safe_join
        assert sftp.safe_remote_path is pathsec.safe_remote_path

    def test_shellcmd_imports_pathsec(self):
        from app.tools import shellcmd
        from app.tools import pathsec
        assert shellcmd.safe_remote_path is pathsec.safe_remote_path
