# -*- coding: utf-8 -*-
"""runtime.env 原子写入（0600，临时文件 + os.replace）。"""
from __future__ import annotations

import os
from typing import Dict

from setup import state


def _quote(value: str) -> str:
    """dotenv 双引号包裹：python-dotenv 解析 \\ 与 \" 转义；
    不用 shell 单引号拼接语法（dotenv 不支持）。"""
    escaped = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return '"%s"' % escaped


def write_runtime_env(values: Dict[str, str]) -> str:
    """把配置写入 runtime.env（原子替换），返回落盘路径。"""
    path = state.runtime_env_path()
    state.data_dir().mkdir(parents=True, exist_ok=True)
    lines = [
        '# OrangeServer 首次部署向导生成（setup wizard）',
        '# 优先级：非空进程环境变量 > 本文件 > backend/.env',
        '# 修改后重启后端生效；删除本文件即回退到纯 .env 配置。',
        '',
    ]
    for key in sorted(values):
        lines.append('%s=%s' % (key, _quote(values[key])))
    content = '\n'.join(lines) + '\n'

    tmp_path = str(path) + '.tmp'
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(path))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        pass
    return str(path)
