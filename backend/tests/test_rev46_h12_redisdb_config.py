# -*- coding: utf-8 -*-
"""REV46-H12/H13/H14/H15: redisdb 配置与连接池单元测试

背景:
- H12: 之前 REDIS_CONF 缺 password, 生产 Redis 无法认证
- H13: 之前硬编码 db=10, 测试/生产冲突
- H14: 之前无 socket_timeout / socket_connect_timeout / socket_keepalive,
       单次操作可能 hang 或长连接被中间设备切断
- H15: ConnRedis 之前无 ping() 健康检查方法

修复:
- REDIS_CONF 扩展 7 个新字段
- _shared_pool 用完整字段构造
- ConnRedis 加 ping() 方法
"""
import os
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# 测试 1: REDIS_CONF 包含全部 9 个字段
# =============================================================================
class TestRedisConfKeys:
    """H12/H13/H14: REDIS_CONF 必须包含 password/db/max_connections/timeout/keepalive."""

    def test_redis_conf_has_password(self):
        """H12: password 字段必须存在 (即使默认空)."""
        from app.core.config import REDIS_CONF
        assert 'password' in REDIS_CONF
        assert isinstance(REDIS_CONF['password'], str)

    def test_redis_conf_has_db(self):
        """H13: db 字段必须存在且为 int."""
        from app.core.config import REDIS_CONF
        assert 'db' in REDIS_CONF
        assert isinstance(REDIS_CONF['db'], int)
        assert 0 <= REDIS_CONF['db'] <= 15  # Redis 默认 16 个 db

    def test_redis_conf_has_max_connections(self):
        """H14: max_connections 字段必须存在."""
        from app.core.config import REDIS_CONF
        assert 'max_connections' in REDIS_CONF
        assert isinstance(REDIS_CONF['max_connections'], int)
        assert REDIS_CONF['max_connections'] >= 1

    def test_redis_conf_has_socket_timeout(self):
        """H14: socket_timeout 必须存在 (防单次操作 hang)."""
        from app.core.config import REDIS_CONF
        assert 'socket_timeout' in REDIS_CONF
        assert isinstance(REDIS_CONF['socket_timeout'], (int, float))
        assert REDIS_CONF['socket_timeout'] > 0

    def test_redis_conf_has_socket_connect_timeout(self):
        """H14: socket_connect_timeout 必须存在 (防 TCP 连接 hang)."""
        from app.core.config import REDIS_CONF
        assert 'socket_connect_timeout' in REDIS_CONF
        assert isinstance(REDIS_CONF['socket_connect_timeout'], (int, float))

    def test_redis_conf_has_socket_keepalive(self):
        """H14: socket_keepalive 必须存在 (防长连接被切断)."""
        from app.core.config import REDIS_CONF
        assert 'socket_keepalive' in REDIS_CONF
        assert isinstance(REDIS_CONF['socket_keepalive'], bool)


# =============================================================================
# 测试 2: REDIS_CONF env 变量生效
# =============================================================================
class TestRedisConfEnvOverride:
    """环境变量可覆盖 REDIS_CONF 字段."""

    def test_ogs_redis_password_env(self, monkeypatch):
        """OGS_REDIS_PASSWORD 环境变量生效."""
        monkeypatch.setenv('OGS_REDIS_PASSWORD', 'my_secret_pwd')
        # 重新加载模块
        import importlib
        import app.core.config
        importlib.reload(app.core.config)
        from app.core.config import REDIS_CONF as FRESH
        assert FRESH['password'] == 'my_secret_pwd'

    def test_ogs_redis_db_env(self, monkeypatch):
        """OGS_REDIS_DB 环境变量生效."""
        monkeypatch.setenv('OGS_REDIS_DB', '5')
        import importlib
        import app.core.config
        importlib.reload(app.core.config)
        from app.core.config import REDIS_CONF as FRESH
        assert FRESH['db'] == 5

    def test_ogs_redis_socket_keepalive_false(self, monkeypatch):
        """OGS_REDIS_SOCKET_KEEPALIVE=false 时 socket_keepalive=False."""
        monkeypatch.setenv('OGS_REDIS_SOCKET_KEEPALIVE', 'false')
        import importlib
        import app.core.config
        importlib.reload(app.core.config)
        from app.core.config import REDIS_CONF as FRESH
        assert FRESH['socket_keepalive'] is False

    def test_ogs_redis_socket_keepalive_variants(self, monkeypatch):
        """OGS_REDIS_SOCKET_KEEPALIVE 接受多种 True 写法."""
        for truthy in ('1', 'true', 'yes', 'on', 'TRUE'):
            monkeypatch.setenv('OGS_REDIS_SOCKET_KEEPALIVE', truthy)
            import importlib
            import app.core.config
            importlib.reload(app.core.config)
            from app.core.config import REDIS_CONF as FRESH
            assert FRESH['socket_keepalive'] is True, f'failed for {truthy}'


# =============================================================================
# 测试 3: _shared_pool 使用 REDIS_CONF 完整字段
# =============================================================================
class TestSharedPoolUsesRedisConf:
    """_shared_pool 构造时必须把 REDIS_CONF 所有字段传进去."""

    def test_pool_has_all_redis_conf_keys(self):
        """redis.ConnectionPool 的 connection_kwargs 必须包含 password/db/timeouts."""
        from app.tools import redisdb as _r
        kwargs = _r._shared_pool.connection_kwargs
        # 至少包含 password / db / socket_timeout / socket_connect_timeout / socket_keepalive
        for required in ('password', 'db', 'socket_timeout',
                         'socket_connect_timeout', 'socket_keepalive'):
            assert required in kwargs, f'missing {required} in pool connection_kwargs'

    def test_pool_decode_responses_true(self):
        """decode_responses=True 必须保留 (业务依赖 str 返回)."""
        from app.tools import redisdb as _r
        assert _r._shared_pool.connection_kwargs.get('decode_responses') is True


# =============================================================================
# 测试 4: ConnRedis.ping() 方法 (REV46-H15)
# =============================================================================
class TestConnRedisPing:
    """H15: ConnRedis 必须有 ping() 健康检查方法."""

    def test_ping_method_exists(self):
        """ConnRedis.ping 方法存在."""
        from app.tools.redisdb import ConnRedis
        assert hasattr(ConnRedis, 'ping')
        assert callable(ConnRedis.ping)

    def test_ping_returns_true_on_success(self):
        """连通时 ping() 返回 True."""
        from app.tools.redisdb import ConnRedis
        with patch.object(ConnRedis, '__init__', lambda self: None):
            instance = ConnRedis.__new__(ConnRedis)
            instance.conn = MagicMock()
            instance.conn.ping = MagicMock(return_value=True)
            assert instance.ping() is True

    def test_ping_raises_on_failure(self):
        """Redis 不可达时 ping() 抛 redis.ConnectionError (由调用方处理)."""
        from app.tools.redisdb import ConnRedis
        import redis as _redis
        with patch.object(ConnRedis, '__init__', lambda self: None):
            instance = ConnRedis.__new__(ConnRedis)
            instance.conn = MagicMock()
            instance.conn.ping = MagicMock(side_effect=_redis.ConnectionError('down'))
            with pytest.raises(_redis.ConnectionError):
                instance.ping()


# =============================================================================
# 测试 5: ConnRedis 向后兼容 (REV46-M16)
# =============================================================================
class TestConnRedisBackwardCompat:
    """ConnRedis(host=None, port=None, max_connections=10) 签名保留以兼容老调用."""

    def test_init_signature_unchanged(self):
        """__init__ 接受 host, port, max_connections (at.py / 8 个测试 mock 依赖)."""
        from app.tools.redisdb import ConnRedis
        import inspect
        sig = inspect.signature(ConnRedis.__init__)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'host' in params
        assert 'port' in params
        assert 'max_connections' in params

    def test_init_uses_shared_pool(self):
        """实例化后 self.conn 来自 _shared_pool."""
        from app.tools.redisdb import ConnRedis, _shared_pool
        instance = ConnRedis(host='ignored', port=12345)
        # self.conn.connection_pool 应等于 _shared_pool
        assert instance.conn.connection_pool is _shared_pool

    def test_host_port_args_ignored(self):
        """host/port 参数被忽略 (REV46-M16), 由 REDIS_CONF 决定."""
        from app.tools.redisdb import ConnRedis
        # 即使传任意 host/port, 实例的 connection_kwargs 仍来自 REDIS_CONF
        instance1 = ConnRedis(host='10.0.0.1', port=9999)
        instance2 = ConnRedis(host='20.0.0.2', port=1111)
        # 两个实例 connection_kwargs 一致 (来自 _shared_pool)
        assert (instance1.conn.connection_pool.connection_kwargs
                == instance2.conn.connection_pool.connection_kwargs)


# =============================================================================
# 测试 6: password 空字符串转 None (redis-py 不接受空字符串)
# =============================================================================
class TestPasswordEmptyHandling:
    """OGS_REDIS_PASSWORD 未设时 password='' 经 redisdb 转 None."""

    def test_empty_password_becomes_none(self):
        """password='' → redis-py 传 None (不认证)."""
        from app.tools import redisdb as _r
        kwargs = _r._shared_pool.connection_kwargs
        # 当 password='' 时 redisdb 转为 None
        password_val = kwargs.get('password')
        if REDIS_CONF_PASSWORD_EMPTY:
            assert password_val is None
        # 或者环境变量设了, 则为字符串
        else:
            assert password_val is not None

    def test_password_is_none_or_str(self):
        """password 字段必须是 None 或 str, 不是空字符串."""
        from app.tools import redisdb as _r
        password_val = _r._shared_pool.connection_kwargs.get('password')
        assert password_val is None or isinstance(password_val, str)
        # 不能是空字符串 (redis-py 行为不一致)
        assert password_val != ''


# 辅助: 检查当前 REDIS_CONF 是否 password 空
def REDIS_CONF_PASSWORD_EMPTY():
    from app.core.config import REDIS_CONF
    return REDIS_CONF['password'] == ''