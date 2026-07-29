# -*- coding: utf-8 -*-
"""REV47-T1: SSH 私钥路径校验统一工具.

背景 (REV46_review.md T1):
  - REV40 H2: webssh `private_key_path` 拼接 (漏修!)
  - REV40 H4: sftp `_handle_download` 私钥路径
  - REV46 H17: shellcmd `self.pkey` 拼接
  - 三处独立实现几乎相同 (realpath + startswith), 现在抽到统一工具.

安全约束:
  1. pkey 必须是非空字符串
  2. pkey 可为相对路径，或 key_base 内的绝对路径（数据库保存格式）
  3. pkey 禁止 '..' 路径分隔符
  4. realpath 后必须仍以 key_base + os.sep 开头 (防 symlink 逃逸)
  5. 默认 must_exist=True 要求文件存在 (避免下游传错路径)

调用方:
  - app/tools/shellcmd.py: get_ssh_connection 使用 safe_key_path
  - app/ssh/sftp.py: _handle_download 使用 safe_key_path
  - app/ssh/webssh.py: SshBridge._create_ssh_conn 使用 safe_key_path (REV40 H2 修复)
"""
import os.path

from app.core.config import FILE_CONF


def safe_key_path(pkey, key_base=None, must_exist=True):
    """REV47-T1: 校验 SSH 私钥路径, 防止任意文件读取.

    Args:
        pkey: 私钥名或 key_base 内的绝对路径 (不含 ../)
        key_base: 私钥基础目录, 默认 FILE_CONF['key_path'].
                 测试时可显式传 tmp 目录.
        must_exist: True=要求文件存在 (默认), False=只校验路径安全性

    Returns:
        规范化后的绝对路径 (realpath)

    Raises:
        ValueError: 路径不安全或文件不存在

    Examples:
        >>> safe_key_path('alice_rsa', key_base='/data/key')
        '/data/key/alice_rsa'

        >>> safe_key_path('../etc/passwd', key_base='/data/key')
        ValueError: pkey path traversal forbidden: '../etc/passwd'

        >>> safe_key_path('/etc/passwd', key_base='/data/key')
        ValueError: pkey absolute path forbidden: '/etc/passwd'
    """
    if key_base is None:
        # 调用时从 config 读最新值 (支持 monkeypatch FILE_CONF 用于测试)
        from app.core.config import FILE_CONF
        key_base = FILE_CONF['key_path']

    # 1. 类型/空检查
    if not isinstance(pkey, str) or not pkey:
        raise ValueError('pkey must be a non-empty string')
    # 2. 禁止显式 .. 路径穿越
    if '..' in pkey.replace('\\', '/').split('/'):
        raise ValueError('pkey path traversal forbidden: %r' % pkey)

    # 3. 统一解析相对路径和数据库中保存的绝对路径。绝对路径只有在
    # key_base 内才允许，兼容 SysUserAdd 保存的 key_path，同时不放宽
    # 任意文件读取边界。
    base = os.path.realpath(key_base)
    is_absolute = os.path.isabs(pkey)
    target = os.path.realpath(
        pkey if is_absolute else os.path.join(base, pkey))
    try:
        contained = os.path.commonpath([base, target]) == base
    except ValueError:
        contained = False
    if not contained:
        if is_absolute:
            raise ValueError('pkey absolute path forbidden: %r' % pkey)
        raise ValueError('pkey escapes key dir: %r -> %r' % (pkey, target))

    # 4. 文件存在性
    if must_exist and not os.path.isfile(target):
        raise ValueError('pkey file not found: %r' % target)
    return target
