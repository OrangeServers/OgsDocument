# -*- coding: utf-8 -*-
"""REV47-T1: 跨模块 SSH 私钥路径校验统一工具测试.

覆盖:
  1. app/tools/keypath.py:safe_key_path 纯函数 (空/绝对路径/..穿越/越界/不存在)
  2. app/tools/shellcmd.py:_safe_key_path 委托验证
  3. app/ssh/sftp.py:_safe_local_key_path 委托验证
  4. app/ssh/webssh.py: REV40 H2 漏洞修复 (不再字符串拼接 FILE_CONF['key_path']+pkey)
"""
import os
import inspect
import tempfile
from unittest.mock import patch

import pytest


# =============================================================================
# TestSafeKeyPathPure: 纯函数测试 (使用 tmp_path 隔离真实 key_path)
# =============================================================================
class TestSafeKeyPathPure:
    """safe_key_path 纯函数: 各种攻击路径全部拒绝."""

    def test_valid_relative_path_returns_realpath(self, tmp_path):
        """合法相对路径: 返回 realpath."""
        from app.tools.keypath import safe_key_path
        # 在 tmp_path 下建一个真实文件
        key_file = tmp_path / 'alice_rsa'
        key_file.write_text('fake-key')

        result = safe_key_path('alice_rsa', key_base=str(tmp_path))
        # realpath 应该解析到 tmp_path/alice_rsa
        assert os.path.isfile(result), f"返回的路径应是文件: {result}"
        assert os.path.realpath(result) == os.path.realpath(str(key_file))

    def test_absolute_path_inside_key_base_is_accepted_for_stored_sys_user(
            self, tmp_path):
        """t_sys_user 保存的是 key 根目录内绝对路径，必须可直接用于连接。"""
        from app.tools.keypath import safe_key_path
        key_file = tmp_path / 'uploaded_rsa'
        key_file.write_text('fake-key')

        result = safe_key_path(
            os.path.realpath(str(key_file)),
            key_base=str(tmp_path),
        )

        assert result == os.path.realpath(str(key_file))

    def test_empty_pkey_raises_value_error(self, tmp_path):
        """空字符串 → ValueError."""
        from app.tools.keypath import safe_key_path
        with pytest.raises(ValueError, match='pkey must be a non-empty string'):
            safe_key_path('', key_base=str(tmp_path))

    def test_non_string_pkey_raises_value_error(self, tmp_path):
        """非字符串 → ValueError."""
        from app.tools.keypath import safe_key_path
        with pytest.raises(ValueError, match='pkey must be a non-empty string'):
            safe_key_path(None, key_base=str(tmp_path))
        with pytest.raises(ValueError, match='pkey must be a non-empty string'):
            safe_key_path(123, key_base=str(tmp_path))

    def test_absolute_path_rejected(self, tmp_path):
        """绝对路径 → ValueError (REV47-T1 攻击面)."""
        import platform
        from app.tools.keypath import safe_key_path
        # Windows 上 /etc/passwd 不是绝对路径 (Python ntpath), 用平台相关的真绝对路径
        if platform.system() == 'Windows':
            abs_pkey = 'C:\\Windows\\System32\\drivers\\etc\\hosts'
        else:
            abs_pkey = '/etc/passwd'
        with pytest.raises(ValueError, match='absolute path forbidden'):
            safe_key_path(abs_pkey, key_base=str(tmp_path))

    def test_path_traversal_rejected(self, tmp_path):
        """.. 路径穿越 → ValueError."""
        from app.tools.keypath import safe_key_path
        with pytest.raises(ValueError, match='path traversal forbidden'):
            safe_key_path('../etc/passwd', key_base=str(tmp_path))
        with pytest.raises(ValueError, match='path traversal forbidden'):
            safe_key_path('a/../../etc/passwd', key_base=str(tmp_path))

    def test_symlink_escape_rejected(self, tmp_path):
        """symlink 指向 key_base 外 → ValueError."""
        from app.tools.keypath import safe_key_path
        # 创建一个 symlink 指向 /etc/passwd
        link_path = tmp_path / 'evil_link'
        try:
            os.symlink('/etc/passwd', str(link_path))
        except (OSError, NotImplementedError):
            pytest.skip('symlink not supported on this platform')

        with pytest.raises(ValueError, match='escapes key dir'):
            safe_key_path('evil_link', key_base=str(tmp_path))

    def test_file_not_found_raises(self, tmp_path):
        """文件不存在 → ValueError (默认 must_exist=True)."""
        from app.tools.keypath import safe_key_path
        with pytest.raises(ValueError, match='file not found'):
            safe_key_path('nonexistent_rsa', key_base=str(tmp_path))

    def test_must_exist_false_skips_file_check(self, tmp_path):
        """must_exist=False 时不检查文件存在性."""
        from app.tools.keypath import safe_key_path
        # 文件不存在但不报错
        result = safe_key_path('nonexistent_rsa', key_base=str(tmp_path), must_exist=False)
        assert result.endswith('nonexistent_rsa')

    def test_nested_path_within_key_base(self, tmp_path):
        """子目录下的合法路径 (如 sub/team_rsa) 应允许."""
        from app.tools.keypath import safe_key_path
        sub_dir = tmp_path / 'sub'
        sub_dir.mkdir()
        key_file = sub_dir / 'team_rsa'
        key_file.write_text('fake')

        result = safe_key_path('sub/team_rsa', key_base=str(tmp_path))
        assert os.path.isfile(result)


# =============================================================================
# TestSafeKeyPathDefaultKeyBase: 默认 key_base = FILE_CONF['key_path']
# =============================================================================
class TestSafeKeyPathDefaultKeyBase:
    """默认 key_base 来自 FILE_CONF['key_path'] (无需显式传参)."""

    def test_default_uses_file_conf_key_path(self, tmp_path, monkeypatch):
        from app.core import config as _cfg
        from app.tools.keypath import safe_key_path

        # 重定向 FILE_CONF['key_path'] 到 tmp_path
        new_conf = dict(_cfg.FILE_CONF)
        new_conf['key_path'] = str(tmp_path) + '/'
        monkeypatch.setattr(_cfg, 'FILE_CONF', new_conf)

        # 在 tmp_path 建文件
        key_file = tmp_path / 'bob_rsa'
        key_file.write_text('fake')

        # 不传 key_base, 应该用 FILE_CONF['key_path']
        result = safe_key_path('bob_rsa')
        assert os.path.isfile(result)


# =============================================================================
# TestShellcmdDelegation: shellcmd._safe_key_path 委托验证
# =============================================================================
class TestShellcmdDelegation:
    """REV47-T1: shellcmd._safe_key_path 委托给 keypath.safe_key_path."""

    def test_shellcmd_safe_key_path_delegates(self):
        """shellcmd._safe_key_path 通过 __wrapped__ 委托给 keypath.safe_key_path."""
        from app.tools import shellcmd
        from app.tools import keypath
        # REV47-T1: 委托验证
        assert getattr(shellcmd._safe_key_path, '__wrapped__', None) is keypath.safe_key_path, \
            "REV47-T1: shellcmd._safe_key_path 应委托给 keypath.safe_key_path"

    def test_shellcmd_safe_key_path_is_keypath(self):
        """shellcmd.safe_key_path === keypath.safe_key_path (顶层 import 直接引用)."""
        from app.tools import shellcmd
        from app.tools import keypath
        # 顶层 import 的 safe_key_path 是同一个引用
        assert shellcmd.safe_key_path is keypath.safe_key_path

    def test_shellcmd_safe_key_path_validation_inherited(self, tmp_path, monkeypatch):
        """shellcmd._safe_key_path 通过委托继承同样的安全约束."""
        from app.core import config as _cfg
        from app.tools import shellcmd
        new_conf = dict(_cfg.FILE_CONF)
        new_conf['key_path'] = str(tmp_path) + '/'
        monkeypatch.setattr(_cfg, 'FILE_CONF', new_conf)
        # .. 穿越应抛错
        with pytest.raises(ValueError, match='path traversal'):
            shellcmd._safe_key_path('../etc/passwd')

    def test_shellcmd_uses_safe_key_path_in_get_ssh_connection(self):
        """get_ssh_connection 中应使用 safe_key_path (而非裸拼接)."""
        from app.tools import shellcmd
        source = inspect.getsource(shellcmd)
        # 关键: 'self.pkey = _safe_key_path(pkey)' 存在
        assert '_safe_key_path(pkey)' in source, \
            "shellcmd.get_ssh_connection 必须用 _safe_key_path(pkey) 而非裸字符串拼接"


# =============================================================================
# TestSftpDelegation: sftp._safe_local_key_path 委托验证
# =============================================================================
class TestSftpDelegation:
    """REV47-T1: sftp._safe_local_key_path 委托给 keypath.safe_key_path."""

    def test_sftp_safe_local_key_path_delegates(self):
        """sftp._safe_local_key_path 通过 __wrapped__ 委托给 keypath.safe_key_path."""
        from app.ssh import sftp
        from app.tools import keypath
        assert getattr(sftp._safe_local_key_path, '__wrapped__', None) is keypath.safe_key_path, \
            "REV47-T1: sftp._safe_local_key_path 应委托给 keypath.safe_key_path"

    def test_sftp_safe_key_path_is_keypath(self):
        """sftp.safe_key_path === keypath.safe_key_path (顶层 import 直接引用)."""
        from app.ssh import sftp
        from app.tools import keypath
        assert sftp.safe_key_path is keypath.safe_key_path

    def test_sftp_safe_local_key_path_validation_inherited(self, tmp_path, monkeypatch):
        from app.core import config as _cfg
        from app.ssh import sftp
        new_conf = dict(_cfg.FILE_CONF)
        new_conf['key_path'] = str(tmp_path) + '/'
        monkeypatch.setattr(_cfg, 'FILE_CONF', new_conf)
        # Windows 兼容
        import platform
        abs_pkey = 'C:\\Windows\\System32\\drivers\\etc\\hosts' if platform.system() == 'Windows' else '/etc/passwd'
        with pytest.raises(ValueError, match='absolute path forbidden'):
            sftp._safe_local_key_path(abs_pkey)


# =============================================================================
# TestWebsshRev40H2Fix: webssh.py REV40 H2 修复验证
# =============================================================================
class TestWebsshRev40H2Fix:
    """REV40 H2 + REV47-T1: webssh 不再裸字符串拼接 FILE_CONF['key_path']+pkey."""

    def test_webssh_uses_safe_key_path_in_create_ssh_conn(self):
        """webssh._create_ssh_conn 必须用 safe_key_path, 而非裸字符串拼接."""
        from app.ssh import webssh
        # 整个 webssh.py 模块源码必须包含 safe_key_path 引用
        source = inspect.getsource(webssh)
        # 关键修复: 旧实现 'FILE_CONF[\'key_path\'] + pkey' 不应再出现
        assert 'FILE_CONF[\'key_path\'] + pkey' not in source, \
            "REV40 H2 + REV47-T1: webssh 不应再裸拼接 FILE_CONF['key_path']+pkey"
        # 新实现: 必须用 safe_key_path
        assert 'safe_key_path(pkey)' in source, \
            "REV47-T1: webssh 应使用 safe_key_path(pkey) 校验私钥路径"

    def test_webssh_path_traversal_blocked(self, tmp_path, monkeypatch):
        """构造一个真实场景: webssh 被传入 ../ 路径, 应被 safe_key_path 拦截."""
        from app.ssh import webssh
        from app.core import config as _cfg

        new_conf = dict(_cfg.FILE_CONF)
        new_conf['key_path'] = str(tmp_path) + '/'
        monkeypatch.setattr(_cfg, 'FILE_CONF', new_conf)

        # mock paramiko.Transport 避免真实连 SSH
        with patch('paramiko.Transport'):
            bridge = webssh.SshBridge(websocket=None)
            # _create_ssh_conn 应在 safe_key_path 阶段就抛错, 不进入 paramiko
            with pytest.raises(ValueError, match='path traversal'):
                bridge._create_ssh_conn(
                    host='example.com', port=22, user='alice',
                    pkey='../../../etc/passwd',  # 攻击 payload
                )

    def test_webssh_absolute_path_blocked(self, tmp_path, monkeypatch):
        import platform
        from app.ssh import webssh
        from app.core import config as _cfg

        new_conf = dict(_cfg.FILE_CONF)
        new_conf['key_path'] = str(tmp_path) + '/'
        monkeypatch.setattr(_cfg, 'FILE_CONF', new_conf)

        abs_pkey = 'C:\\Windows\\System32\\drivers\\etc\\hosts' if platform.system() == 'Windows' else '/etc/passwd'
        with patch('paramiko.Transport'):
            bridge = webssh.SshBridge(websocket=None)
            with pytest.raises(ValueError, match='absolute path forbidden'):
                bridge._create_ssh_conn(
                    host='example.com', port=22, user='alice',
                    pkey=abs_pkey,
                )


# =============================================================================
# TestRev47T1Marker: 注释/模块标记
# =============================================================================
class TestRev47T1Marker:
    """REV47-T1 修复必须显式 import keypath + 注释标记."""

    def test_shellcmd_imports_keypath(self):
        from app.tools import shellcmd
        from app.tools import keypath
        assert hasattr(shellcmd, 'safe_key_path'), \
            "REV47-T1: shellcmd 必须 import safe_key_path"
        # 引用的是同一个函数对象
        assert shellcmd.safe_key_path is keypath.safe_key_path

    def test_sftp_imports_keypath(self):
        from app.ssh import sftp
        from app.tools import keypath
        assert hasattr(sftp, 'safe_key_path'), \
            "REV47-T1: sftp 必须 import safe_key_path"
        assert sftp.safe_key_path is keypath.safe_key_path

    def test_webssh_imports_keypath(self):
        from app.ssh import webssh
        from app.tools import keypath
        assert hasattr(webssh, 'safe_key_path'), \
            "REV47-T1: webssh 必须 import safe_key_path (REV40 H2 修复关键)"
        assert webssh.safe_key_path is keypath.safe_key_path

    def test_keypath_module_has_rev47_t1_marker(self):
        import inspect
        from app.tools import keypath
        source = inspect.getsource(keypath)
        assert 'REV47-T1' in source, "keypath.py 必须有 REV47-T1 标记注释"
        assert 'REV40' in source, "keypath.py 应引用 REV40 (历史) + REV46 评审来源"
