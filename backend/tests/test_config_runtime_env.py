# -*- coding: utf-8 -*-
"""SETUP-WIZARD: config.py 的 runtime.env fill-empty 加载语义。

直接复现 config.py 顶部的加载循环（不 reload config 模块本身——它 import 期
有 fail-fast 副作用），保证语义锚定：空串按未设置填充、非空进程 env 最高优先。
"""
import os

import pytest

pytest.importorskip('dotenv')
from dotenv import dotenv_values  # noqa: E402


def _fill_empty(runtime_path):
    """与 app/core/config.py 的 SETUP-WIZARD 加载块逐行同义。"""
    if runtime_path.exists():
        for key, value in (dotenv_values(runtime_path) or {}).items():
            if value is not None and os.environ.get(key) in (None, ''):
                os.environ[key] = value


def test_missing_key_filled(tmp_path, monkeypatch):
    monkeypatch.delenv('OGS_TEST_FILL', raising=False)
    runtime = tmp_path / 'runtime.env'
    runtime.write_text("OGS_TEST_FILL='from-file'\n", encoding='utf-8')
    _fill_empty(runtime)
    assert os.environ['OGS_TEST_FILL'] == 'from-file'
    monkeypatch.delenv('OGS_TEST_FILL', raising=False)


def test_empty_string_env_filled(tmp_path, monkeypatch):
    """compose 把未设置的宿主变量注入为空串——必须被 runtime.env 填充。"""
    monkeypatch.setenv('OGS_TEST_FILL', '')
    runtime = tmp_path / 'runtime.env'
    runtime.write_text("OGS_TEST_FILL='from-file'\n", encoding='utf-8')
    _fill_empty(runtime)
    assert os.environ['OGS_TEST_FILL'] == 'from-file'


def test_nonempty_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv('OGS_TEST_FILL', 'operator-set')
    runtime = tmp_path / 'runtime.env'
    runtime.write_text("OGS_TEST_FILL='from-file'\n", encoding='utf-8')
    _fill_empty(runtime)
    assert os.environ['OGS_TEST_FILL'] == 'operator-set'


def test_absent_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv('OGS_TEST_FILL', '')
    _fill_empty(tmp_path / 'runtime.env')
    assert os.environ['OGS_TEST_FILL'] == ''


def test_config_source_contains_fill_empty_block():
    """守护：config.py 里的 fill-empty 块不被后续重构误删。"""
    from pathlib import Path
    source = (
        Path(__file__).resolve().parents[1] / 'app' / 'core' / 'config.py'
    ).read_text(encoding='utf-8')
    assert 'OGS_RUNTIME_ENV_FILE' in source
    assert "os.environ.get(_k) in (None, '')" in source


def test_envwrite_quotes_special_chars(tmp_path, monkeypatch):
    """envwrite 落盘的值经 dotenv 解析后与原值一致（含引号/空格/井号）。"""
    monkeypatch.setenv('OGS_DATA_DIR', str(tmp_path))
    import importlib
    from setup import state, envwrite
    importlib.reload(state)
    tricky = {"OGS_TEST_TRICKY": "pa'ss #word $x \"q\""}
    envwrite.write_runtime_env(tricky)
    parsed = dotenv_values(state.runtime_env_path())
    assert parsed['OGS_TEST_TRICKY'] == tricky['OGS_TEST_TRICKY']
