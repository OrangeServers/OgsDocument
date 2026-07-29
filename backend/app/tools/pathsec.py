# -*- coding: utf-8 -*-
"""REV47-T2: 跨模块路径安全工具.

背景 (REV46_review.md T2):
  - REV40 H1: sftp mkdir/rm/rename 路径白名单
  - REV46 H16: shellcmd put_file 路径白名单
  - 两处独立实现几乎相同 (前缀白名单 + .. 检测 + NUL 检测), 现抽到统一工具.

提供:
  - safe_join(base, name): 通用安全路径拼接 (防 symlink 越狱, 越界返 None)
  - safe_remote_path(path, allowed_prefixes): 远程路径白名单校验
"""
import os.path


def safe_join(base, name):
    """REV47-T2: 通用安全路径拼接, 防御 symlink 越狱.

    背景: sftp._safe_join 独立实现, 现抽到 pathsec.py 跨模块共用.

    Args:
        base: 基础目录 (绝对路径)
        name: 待拼接的相对名称

    Returns:
        拼接后的 realpath, 如果越界 (e.g. name 含 ../) 返 None

    Examples:
        >>> safe_join('/data', 'file.txt')
        '/data/file.txt'

        >>> safe_join('/data', '../etc/passwd')  # 越界
        None
    """
    if not isinstance(base, str) or not isinstance(name, str):
        return None
    try:
        candidate = os.path.realpath(os.path.join(base, name))
        base_real = os.path.realpath(base)
        if os.path.commonpath([candidate, base_real]) != base_real:
            return None
    except (ValueError, OSError):
        # ValueError: paths don't have same drive (Windows)
        # OSError: realpath 失败
        return None
    return candidate


def safe_remote_path(path, allowed_prefixes):
    """REV47-T2: 远程路径白名单校验 (SFTP mkdir/rm/rename + put_file 通用).

    背景: sftp._safe_sftp_path + shellcmd._safe_remote_path 几乎完全重复,
          现抽到 pathsec.py 统一实现, 接受 allowed_prefixes 参数.

    拒绝条件:
      1) path 非字符串
      2) path 含 NUL 字符
      3) path 含 '..' 路径分隔符 (穿越)
      4) path 不在 allowed_prefixes 白名单下

    Args:
        path: 待校验的远程路径 (绝对路径)
        allowed_prefixes: tuple of str, 允许的前缀 (e.g. ('/home/', '/tmp/'))

    Returns:
        规范化后的绝对路径 (os.path.normpath)

    Raises:
        ValueError: 路径不安全

    Examples:
        >>> safe_remote_path('/home/alice/file.txt', ('/home/', '/tmp/'))
        '/home/alice/file.txt'

        >>> safe_remote_path('/etc/passwd', ('/home/', '/tmp/'))
        ValueError: path not in allowed prefixes: '/etc/passwd'

        >>> safe_remote_path('/home/../etc/passwd', ('/home/',))
        ValueError: path traversal forbidden: '/home/../etc/passwd'
    """
    if not isinstance(path, str):
        raise ValueError('path must be a string')
    if '\x00' in path:
        raise ValueError('path contains NUL char')
    if '..' in path.split('/'):
        raise ValueError('path traversal forbidden: %r' % path)
    if not any(path.startswith(p) for p in allowed_prefixes):
        raise ValueError('path not in allowed prefixes: %r' % path)
    return os.path.normpath(path)
