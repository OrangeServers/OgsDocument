# -*- coding: utf-8 -*-
"""setup 模式判定与配置视图（不 import app.*，仅 stdlib + python-dotenv）。

三态模型：
- setup       必需配置不齐 且 哨兵不存在（或 OGS_SETUP_MODE=force）
- normal      必需配置齐全
- maintenance 配置不齐但哨兵存在（已配置系统被破坏时绝不重开向导）

必需项判定复刻 app/core/config.py 的 fail-fast 规则与
ops/preflight-physical-backend.sh 的 REQUIRED_KEYS，实现保持静态独立。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - dotenv 是 runtime 依赖
    def dotenv_values(_path):  # type: ignore
        return {}

# 与 config.py:_DEFAULT_MYSQL_INSECURE 保持一致（含空串 → MySQL 三项等于必填）
MYSQL_INSECURE = {'zkfc', 'zkfc123', '192.0.2.1', 'root', '', 'changeme', 'placeholder'}
# 与 config.py SECRET_KEY 校验一致（含 CHANGE_ME* 前缀，见 _is_template_placeholder 与下方判定）
SECRET_INSECURE_SUBSTR = ('dev-only', 'change-me', 'please-override', 'placeholder', 'changeme', 'change_me')
SECRET_MIN_LEN = 32

BACKEND_DIR = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    return Path(os.environ.get('OGS_DATA_DIR') or (Path(os.getcwd()) / 'data'))


def runtime_env_path() -> Path:
    override = os.environ.get('OGS_RUNTIME_ENV_FILE')
    if override:
        return Path(override)
    return data_dir() / 'runtime.env'


def sentinel_path() -> Path:
    return data_dir() / '.setup_completed'


def token_path() -> Path:
    return data_dir() / 'setup_token.txt'


def resolve_env() -> Dict[str, str]:
    """合成配置视图：非空进程 env > runtime.env > backend/.env。

    与 config.py 的最终加载语义一致（fill-empty：空串按未设置处理）。
    只读合成，不写 os.environ。
    """
    merged: Dict[str, str] = {}
    dotenv_file = BACKEND_DIR / '.env'
    if dotenv_file.exists():
        for k, v in (dotenv_values(dotenv_file) or {}).items():
            if v:
                merged[k] = v
    runtime_file = runtime_env_path()
    if runtime_file.exists():
        for k, v in (dotenv_values(runtime_file) or {}).items():
            if v:
                merged[k] = v
    for k, v in os.environ.items():
        if v:
            merged[k] = v
    return merged


def _is_template_placeholder(value: str) -> bool:
    """env.example 模板占位值（如 __REQUIRED_GENERATE_FERNET_KEY__）按未配置处理，
    防止占位符绕过判定导致向导不触发、服务带着占位密钥启动。"""
    return value.startswith('__') and value.endswith('__') and len(value) > 4


def missing_required(env: Dict[str, str] | None = None) -> List[str]:
    """返回缺失/不合格的必需配置项列表（空列表 = 配置齐全）。"""
    env = env if env is not None else resolve_env()
    missing: List[str] = []
    for key in ('OGS_MYSQL_USER', 'OGS_MYSQL_PASSWORD', 'OGS_MYSQL_HOST'):
        value = env.get(key, '')
        if (
            value in MYSQL_INSECURE
            or _is_template_placeholder(value)
            or value.upper().startswith('CHANGE_ME')  # 与 config.py 判定对齐
        ):
            missing.append(key)
    secret = env.get('OGS_FLASK_SECRET_KEY', '')
    if (
        len(secret) < SECRET_MIN_LEN
        or _is_template_placeholder(secret)
        or any(bad in secret.lower() for bad in SECRET_INSECURE_SUBSTR)
    ):
        missing.append('OGS_FLASK_SECRET_KEY')
    # Fernet：config.py 不校验但功能必需（凭据加密），向导补上这层
    fernet = env.get('OGS_FERNET_KEYS') or env.get('OGS_FERNET_KEY') or ''
    if not fernet or _is_template_placeholder(fernet):
        missing.append('OGS_FERNET_KEYS')
    return missing


def env_locked_keys() -> List[str]:
    """进程 env 中非空的启动级 key（由部署环境固定，向导中置灰只读）。"""
    keys = (
        'OGS_MYSQL_HOST', 'OGS_MYSQL_PORT', 'OGS_MYSQL_DBNAME',
        'OGS_MYSQL_USER', 'OGS_MYSQL_PASSWORD',
        'OGS_REDIS_HOST', 'OGS_REDIS_PORT', 'OGS_REDIS_PASSWORD', 'OGS_REDIS_DB',
        'OGS_FLASK_SECRET_KEY', 'OGS_FERNET_KEYS',
    )
    return [k for k in keys if os.environ.get(k)]


def sentinel_exists() -> bool:
    return sentinel_path().exists()


def mark_configured() -> None:
    """写入/刷新哨兵。normal 启动成功后也调用（自愈存量部署无哨兵的情况）。"""
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
        sentinel_path().write_text('configured\n', encoding='utf-8')
    except OSError:
        # 数据目录不可写不阻断业务启动；只是失去 maintenance 保护
        pass


def setup_mode_flag() -> str:
    return (os.environ.get('OGS_SETUP_MODE') or '').strip().lower()


def should_enter_setup() -> bool:
    flag = setup_mode_flag()
    if flag == 'off':
        return False
    if flag == 'force':
        return True
    if not missing_required():
        return False
    return not sentinel_exists()


def resolve_mode() -> str:
    """'setup' | 'normal' | 'maintenance'（wsgi 三态判定入口）。"""
    if should_enter_setup():
        return 'setup'
    if not missing_required():
        return 'normal'
    return 'maintenance'
