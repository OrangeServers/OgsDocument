# -*- coding: utf-8 -*-
"""REV47-D 段: REV46 P3 basesec/redisdb/shellcmd polish.

测试范围:
  - basesec M10 (regex cost) / M12 (type hints) / M13 (模块 docstring) / M14 (命名统一)
  - redisdb M17 (pipeline) / M19 (共享池注释)
  - shellcmd M25 (类型校验) / M28 (host key cache)

所有测试为静态 / 单元级 (不连真实 DB / Redis / SSH).
"""
import inspect
import os
import re
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# M10: basesec bcrypt cost 用 regex 解析
# =============================================================================
class TestM10BcryptCostRegex:
    """M10: needs_rehash 用 regex 解析 cost, 替代 stored[4:6] 切片."""

    def test_01_extract_bcrypt_cost_function_exists(self):
        """M10: _extract_bcrypt_cost 函数已注册."""
        from app.tools.basesec import _extract_bcrypt_cost
        assert callable(_extract_bcrypt_cost)

    def test_02_parses_2a_12(self):
        """M10: $2a$12$ 解析为 12."""
        from app.tools.basesec import _extract_bcrypt_cost
        assert _extract_bcrypt_cost('$2a$12$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ') == 12

    def test_03_parses_2b_10(self):
        """M10: $2b$10$ 解析为 10."""
        from app.tools.basesec import _extract_bcrypt_cost
        assert _extract_bcrypt_cost('$2b$10$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ') == 10

    def test_04_parses_2y(self):
        """M10: $2y$ 也支持 (bcrypt 变种)."""
        from app.tools.basesec import _extract_bcrypt_cost
        assert _extract_bcrypt_cost('$2y$14$abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ') == 14

    def test_05_invalid_returns_none(self):
        """M10: 非 bcrypt 格式 → None (不抛异常)."""
        from app.tools.basesec import _extract_bcrypt_cost
        assert _extract_bcrypt_cost('not_a_bcrypt_hash') is None
        assert _extract_bcrypt_cost('') is None
        assert _extract_bcrypt_cost(None) is None
        # 缺 $ 闭合
        assert _extract_bcrypt_cost('$2a$12abc') is None

    def test_06_needs_rehash_uses_regex(self):
        """M10: needs_rehash 走 _extract_bcrypt_cost, 不再 stored[4:6] 切片."""
        from app.tools import basesec
        src = inspect.getsource(basesec.needs_rehash)
        assert '_extract_bcrypt_cost' in src, (
            "needs_rehash 应调 _extract_bcrypt_cost"
        )
        # 老的 stored[4:6] 切片应删除 (用 'int(stored[4:6]' 这种完整表达式校验, 避免误伤函数签名里的 stored 参数)
        assert 'int(stored[4:6])' not in src, (
            "needs_rehash 不应再用 int(stored[4:6]) 切片"
        )


# =============================================================================
# M12: basesec 全函数 type hints
# =============================================================================
class TestM12BasesecTypeHints:
    """M12: basesec 全函数入参/出参 type hints."""

    @pytest.mark.parametrize("fn_name,expected_keys", [
        ('hash_pwd', {'plain', 'return'}),
        ('verify_pwd', {'plain', 'stored', 'return'}),
        ('needs_rehash', {'stored', 'return'}),
        ('dummy_verify_pwd', {'plain', 'return'}),
        ('encrypt_host_password', {'plain', 'return'}),
        ('decrypt_host_password', {'stored', 'return'}),
        ('_is_bcrypt_hash', {'stored', 'return'}),
        ('_is_fernet_ciphertext', {'stored', 'return'}),
        ('_extract_bcrypt_cost', {'stored', 'return'}),
    ])
    def test_01_function_has_annotations(self, fn_name, expected_keys):
        """M12: 关键函数都有 type hints."""
        from app.tools import basesec
        fn = getattr(basesec, fn_name)
        ann = getattr(fn, '__annotations__', {})
        missing = expected_keys - set(ann.keys())
        assert not missing, (
            f"{fn_name} 缺 type hints: {missing}, 实际 annotations={ann}"
        )


# =============================================================================
# M13: basesec 模块 docstring
# =============================================================================
class TestM13BasesecModuleDocstring:
    """M13: basesec 模块顶部 docstring."""

    def test_01_module_has_docstring(self):
        """M13: basesec 模块 docstring 存在且非空."""
        from app.tools import basesec
        assert basesec.__doc__ is not None, "basesec 缺模块 docstring (M13)"
        assert len(basesec.__doc__.strip()) > 100, (
            f"basesec docstring 长度太短 ({len(basesec.__doc__)}), 应有详细说明"
        )

    def test_02_docstring_covers_core_capabilities(self):
        """M13: docstring 应涵盖核心能力 (bcrypt / Fernet / 审计)."""
        from app.tools import basesec
        doc = basesec.__doc__
        for kw in ('bcrypt', 'Fernet', 'hash_pwd', 'verify_pwd',
                   'encrypt_host_password', 'decrypt_host_password'):
            assert kw in doc, f"basesec docstring 缺关键词 {kw!r}"

    def test_03_docstring_has_rev47_m13_marker(self):
        """M13: docstring 含 REV47-M13 标记."""
        from app.tools import basesec
        assert 'REV47-M13' in basesec.__doc__


# =============================================================================
# M14: basesec 命名统一 (plain / stored)
# =============================================================================
class TestM14BasesecNamingConsistency:
    """M14: 命名统一 - 入参用 plain (明文) / stored (已存储值)."""

    def test_01_hash_pwd_uses_plain(self):
        """M14: hash_pwd 入参名是 plain (非 password)."""
        from app.tools.basesec import hash_pwd
        sig = inspect.signature(hash_pwd)
        assert 'plain' in sig.parameters, (
            f"hash_pwd 入参名应是 'plain', 实际 {list(sig.parameters)!r}"
        )

    def test_02_verify_pwd_uses_plain_and_stored(self):
        """M14: verify_pwd 入参是 plain + stored."""
        from app.tools.basesec import verify_pwd
        sig = inspect.signature(verify_pwd)
        params = list(sig.parameters.keys())
        assert 'plain' in sig.parameters, f"verify_pwd 应有 'plain' 入参, 实际 {params}"
        assert 'stored' in sig.parameters, f"verify_pwd 应有 'stored' 入参, 实际 {params}"

    def test_03_encrypt_host_password_uses_plain(self):
        """M14: encrypt_host_password 入参名是 plain (与 hash_pwd 一致)."""
        from app.tools.basesec import encrypt_host_password
        sig = inspect.signature(encrypt_host_password)
        assert 'plain' in sig.parameters

    def test_04_decrypt_host_password_uses_stored(self):
        """M14: decrypt_host_password 入参名是 stored (与 verify_pwd 一致)."""
        from app.tools.basesec import decrypt_host_password
        sig = inspect.signature(decrypt_host_password)
        assert 'stored' in sig.parameters


# =============================================================================
# M17: redisdb pipeline 支持
# =============================================================================
class TestM17RedisPipeline:
    """M17: ConnRedis.pipeline() contextmanager."""

    def test_01_pipeline_method_exists(self):
        """M17: ConnRedis.pipeline() 方法已注册."""
        from app.tools.redisdb import ConnRedis
        assert hasattr(ConnRedis, 'pipeline'), "ConnRedis 缺 pipeline() (M17)"
        assert callable(ConnRedis.pipeline)

    def test_02_pipeline_is_contextmanager(self):
        """M17: pipeline 是 @contextmanager 装饰 (with 语句可用)."""
        from app.tools.redisdb import ConnRedis
        from contextlib import _GeneratorContextManager
        # @contextmanager 装饰后, 函数返回 _GeneratorContextManager 实例
        # (装饰后调用得到 contextmanager, 而非原函数)
        # 用 source 字符串校验有 yield 关键字 (contextmanager 必须有 yield)
        src = inspect.getsource(ConnRedis.pipeline)
        assert 'yield pipe' in src, (
            "ConnRedis.pipeline 应是 @contextmanager (含 yield pipe)"
        )

    def test_03_pipeline_accepts_transaction_flag(self):
        """M17: pipeline(transaction=True/False) 可控制是否事务."""
        from app.tools.redisdb import ConnRedis
        sig = inspect.signature(ConnRedis.pipeline)
        assert 'transaction' in sig.parameters
        # 默认 True (MULTI/EXEC 原子事务)
        assert sig.parameters['transaction'].default is True


# =============================================================================
# M19: redisdb 共享池注释
# =============================================================================
class TestM19RedisSharedPoolComment:
    """M19: redisdb _shared_pool 注释解释共享连接池机制."""

    def test_01_shared_pool_module_global(self):
        """M19: _shared_pool 是模块级全局 (所有 ConnRedis 实例共享)."""
        from app.tools import redisdb
        assert hasattr(redisdb, '_shared_pool')
        import redis
        assert isinstance(redisdb._shared_pool, redis.ConnectionPool)

    def test_02_pool_has_necessary_options(self):
        """M19: pool 配置项齐 (password / socket_keepalive / decode_responses)."""
        from app.tools import redisdb
        # pool 构造时已经传了 password/socket_keepalive 等, 通过源代码校验
        src_path = os.path.join(BACKEND, 'app', 'tools', 'redisdb.py')
        with open(src_path, encoding='utf-8') as f:
            src = f.read()
        # 共享池定义含必要选项
        for opt in ('password', 'socket_keepalive', 'socket_timeout',
                    'socket_connect_timeout', 'max_connections', 'decode_responses'):
            assert opt in src, f"_shared_pool 缺配置项 {opt!r}"

    def test_03_shared_pool_comment_present(self):
        """M19: _shared_pool 上方有解释注释 (REV47-M19)."""
        src_path = os.path.join(BACKEND, 'app', 'tools', 'redisdb.py')
        with open(src_path, encoding='utf-8') as f:
            src = f.read()
        assert 'REV47-M19' in src, "redisdb.py 缺 REV47-M19 标记"


# =============================================================================
# M25: shellcmd 类型校验
# =============================================================================
class TestM25ShellcmdTypeValidation:
    """M25: RemoteConnectionAuto.__init__ 入参类型校验."""

    def test_01_validate_host_type(self):
        """M25: host 非 str → TypeError."""
        from app.tools.shellcmd import RemoteConnectionAuto
        with pytest.raises(TypeError) as exc_info:
            RemoteConnectionAuto(host=12345, port=22, username='root')
        assert 'host' in str(exc_info.value)

    def test_02_validate_port_type(self):
        """M25: port 非 int → TypeError."""
        from app.tools.shellcmd import RemoteConnectionAuto
        with pytest.raises(TypeError) as exc_info:
            RemoteConnectionAuto(host='1.2.3.4', port='22', username='root')
        assert 'port' in str(exc_info.value)

    def test_03_validate_username_type(self):
        """M25: username 非 str → TypeError."""
        from app.tools.shellcmd import RemoteConnectionAuto
        with pytest.raises(TypeError) as exc_info:
            RemoteConnectionAuto(host='1.2.3.4', port=22, username=None)
        assert 'username' in str(exc_info.value)

    def test_04_validate_port_range(self):
        """M25: port 越界 (0 / 65536) → ValueError."""
        from app.tools.shellcmd import RemoteConnectionAuto
        with pytest.raises(ValueError):
            RemoteConnectionAuto(host='1.2.3.4', port=0, username='root')
        with pytest.raises(ValueError):
            RemoteConnectionAuto(host='1.2.3.4', port=70000, username='root')

    def test_05_m25_marker_present(self):
        """M25: shellcmd 含 REV47-M25 标记."""
        src_path = os.path.join(BACKEND, 'app', 'tools', 'shellcmd.py')
        with open(src_path, encoding='utf-8') as f:
            src = f.read()
        assert 'REV47-M25' in src


# =============================================================================
# M28: shellcmd host key cache
# =============================================================================
class TestM28ShellcmdHostKeyCache:
    """M28: RemoteConnectionAuto 加载 known_hosts (host key cache)."""

    def test_01_load_system_host_keys_called(self):
        """M28: __init__ 调 load_system_host_keys()."""
        from app.tools.shellcmd import RemoteConnectionAuto
        src = inspect.getsource(RemoteConnectionAuto.__init__)
        assert 'load_system_host_keys' in src, (
            "RemoteConnectionAuto.__init__ 应调 ssh.load_system_host_keys() (M28)"
        )

    def test_02_custom_known_hosts_env_support(self):
        """M28: 接受 OGS_SSH_KNOWN_HOSTS 环境变量额外加载."""
        from app.tools.shellcmd import RemoteConnectionAuto
        src = inspect.getsource(RemoteConnectionAuto.__init__)
        assert 'OGS_SSH_KNOWN_HOSTS' in src, (
            "RemoteConnectionAuto 应支持 OGS_SSH_KNOWN_HOSTS env (M28)"
        )
        assert 'load_host_keys' in src, (
            "应调 load_host_keys() 加载自定义 known_hosts"
        )

    def test_03_m28_marker_present(self):
        """M28: shellcmd 含 REV47-M28 标记."""
        src_path = os.path.join(BACKEND, 'app', 'tools', 'shellcmd.py')
        with open(src_path, encoding='utf-8') as f:
            src = f.read()
        assert 'REV47-M28' in src
