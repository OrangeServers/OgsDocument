# -*- coding: utf-8 -*-
"""
REV47-M18: redisdb 读操作 retry 包装 (3次 + 指数 backoff).

背景:
- redis 操作偶发网络抖动 / 暂时性 ConnectionError
- 原实现: 一次失败就抛, 业务侧需要自己重试
- 修复: _with_retry(callable_, max_retries=3, base_delay=0.1) helper
        ping() 自动走 retry, 偶发故障自动恢复

测试覆盖:
  1) _with_retry 成功一次 → 直接返回
  2) _with_retry 第一次失败第二次成功 → 返回结果, 不抛
  3) _with_retry 三次都失败 → 抛最后一次异常
  4) _with_retry 指数 backoff (0.1, 0.2, 0.4 ...)
  5) _with_retry max_delay 上限
  6) _with_retry 只对 retriable 异常重试 (非 retriable 直接抛)
  7) _with_retry retry 过程写 WARNING 日志
  8) _with_retry 全部失败后写 ERROR 日志
  9) ping() 走 retry (失败 2 次后成功)
  10) ping() 走 retry (全失败抛 ConnectionError)
  11) ping() 走 retry 写 WARNING 日志
  12) logger 异常不阻断主业务
"""
import os
import time
import logging
from unittest.mock import patch, MagicMock

import pytest
import redis.exceptions


_HERE = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# 1) _with_retry 行为
# ============================================================
class TestRev47M18RetryHelper:
    """REV47-M18: _with_retry 基本行为."""

    def test_01_first_attempt_success(self):
        from app.tools.redisdb import ConnRedis
        calls = [0]

        def _fn():
            calls[0] += 1
            return 'ok'

        result = ConnRedis._with_retry(_fn, op_name='test')
        assert result == 'ok'
        assert calls[0] == 1

    def test_02_second_attempt_success(self):
        from app.tools.redisdb import ConnRedis
        calls = [0]

        def _fn():
            calls[0] += 1
            if calls[0] < 2:
                raise redis.exceptions.ConnectionError('mock transient')
            return 'recovered'

        with patch('app.tools.redisdb.time.sleep') as mock_sleep:
            result = ConnRedis._with_retry(_fn, op_name='test')

        assert result == 'recovered'
        assert calls[0] == 2
        # 第一次失败后 sleep backoff
        assert mock_sleep.call_count == 1
        # delay = base_delay * 2^0 = 0.1
        assert mock_sleep.call_args[0][0] == 0.1

    def test_03_third_attempt_success(self):
        from app.tools.redisdb import ConnRedis
        calls = [0]

        def _fn():
            calls[0] += 1
            if calls[0] < 3:
                raise redis.exceptions.ConnectionError('mock transient')
            return 'recovered_late'

        with patch('app.tools.redisdb.time.sleep'):
            result = ConnRedis._with_retry(_fn, op_name='test')

        assert result == 'recovered_late'
        assert calls[0] == 3

    def test_04_all_attempts_fail_raises(self):
        from app.tools.redisdb import ConnRedis
        calls = [0]

        def _fn():
            calls[0] += 1
            raise redis.exceptions.ConnectionError('mock persistent')

        with patch('app.tools.redisdb.time.sleep'):
            with pytest.raises(redis.exceptions.ConnectionError) as exc_info:
                ConnRedis._with_retry(_fn, op_name='test', max_retries=3)

        # 3 次都尝试了
        assert calls[0] == 3
        # sleep 2 次 (前两次失败后)
        assert 'mock persistent' in str(exc_info.value)

    def test_05_exponential_backoff(self):
        from app.tools.redisdb import ConnRedis

        def _fn():
            raise redis.exceptions.ConnectionError('fail')

        with patch('app.tools.redisdb.time.sleep') as mock_sleep:
            with pytest.raises(redis.exceptions.ConnectionError):
                ConnRedis._with_retry(
                    _fn, op_name='test', max_retries=4,
                    base_delay=0.1, max_delay=10.0,
                )

        # delays: 0.1, 0.2, 0.4 (3 次 sleep, 第 4 次 raise)
        delays = [c[0][0] for c in mock_sleep.call_args_list]
        assert delays == [0.1, 0.2, 0.4]

    def test_06_max_delay_cap(self):
        from app.tools.redisdb import ConnRedis

        def _fn():
            raise redis.exceptions.ConnectionError('fail')

        with patch('app.tools.redisdb.time.sleep') as mock_sleep:
            with pytest.raises(redis.exceptions.ConnectionError):
                ConnRedis._with_retry(
                    _fn, op_name='test', max_retries=5,
                    base_delay=0.1, max_delay=0.2,
                )

        delays = [c[0][0] for c in mock_sleep.call_args_list]
        # 0.1, 0.2, 0.2 (capped), 0.2 (capped)
        for d in delays:
            assert d <= 0.2, f"delay {d} 超过 max_delay=0.2"
        assert delays[0] == 0.1
        assert delays[1] == 0.2
        # 后续都被 cap 在 0.2

    def test_07_non_retriable_exception_not_retried(self):
        from app.tools.redisdb import ConnRedis
        calls = [0]

        def _fn():
            calls[0] += 1
            raise ValueError('not retriable')

        with pytest.raises(ValueError):
            ConnRedis._with_retry(_fn, op_name='test', max_retries=3)

        # ValueError 不在 retriable 列表, 只尝试 1 次
        assert calls[0] == 1

    def test_08_custom_retriable_exceptions(self):
        from app.tools.redisdb import ConnRedis
        calls = [0]

        def _fn():
            calls[0] += 1
            if calls[0] < 2:
                raise OSError('custom retriable')
            return 'ok'

        with patch('app.tools.redisdb.time.sleep'):
            result = ConnRedis._with_retry(
                _fn, op_name='test', retriable_exceptions=(OSError,),
            )

        assert result == 'ok'
        assert calls[0] == 2

    def test_09_retry_logs_warning(self, caplog):
        from app.tools.redisdb import ConnRedis

        def _fn():
            raise redis.exceptions.ConnectionError('fail')

        with patch('app.tools.redisdb.time.sleep'):
            with caplog.at_level(logging.WARNING, logger='redis_retry'):
                with pytest.raises(redis.exceptions.ConnectionError):
                    ConnRedis._with_retry(_fn, op_name='custom_op', max_retries=2)

        warnings = [r for r in caplog.records
                    if r.name == 'redis_retry' and r.levelno == logging.WARNING]
        # 2 次尝试, 1 次 sleep (前 1 次失败)
        assert len(warnings) >= 1
        assert any('custom_op' in r.message for r in warnings)

    def test_10_retry_exhausted_logs_error(self, caplog):
        from app.tools.redisdb import ConnRedis

        def _fn():
            raise redis.exceptions.ConnectionError('persistent')

        with patch('app.tools.redisdb.time.sleep'):
            with caplog.at_level(logging.ERROR, logger='redis_retry'):
                with pytest.raises(redis.exceptions.ConnectionError):
                    ConnRedis._with_retry(_fn, op_name='exhaust_op', max_retries=2)

        errors = [r for r in caplog.records
                  if r.name == 'redis_retry' and r.levelno == logging.ERROR]
        assert any('exhausted' in r.message for r in errors)
        assert any('exhaust_op' in r.message for r in errors)

    def test_11_logger_failure_does_not_break(self, caplog):
        """logger 自身异常 → 主业务仍正常."""
        from app.tools.redisdb import ConnRedis

        def _fn():
            raise redis.exceptions.ConnectionError('fail')

        with patch('app.tools.redisdb.time.sleep'):
            with patch('app.tools.redisdb.logging.getLogger') as mock_get:
                mock_log = mock_get.return_value
                mock_log.warning.side_effect = RuntimeError('logger dead')
                mock_log.error.side_effect = RuntimeError('logger dead')
                with pytest.raises(redis.exceptions.ConnectionError):
                    ConnRedis._with_retry(_fn, op_name='test', max_retries=2)


# ============================================================
# 2) ping() 走 retry
# ============================================================
class TestRev47M18PingWithRetry:
    """REV47-M18: ping() 自动 retry."""

    def test_01_ping_first_success(self):
        from app.tools.redisdb import ConnRedis
        r = ConnRedis()
        with patch.object(r.conn, 'ping', return_value=True):
            assert r.ping() is True

    def test_02_ping_recovers_after_two_failures(self):
        from app.tools.redisdb import ConnRedis
        r = ConnRedis()
        ping_mock = MagicMock(side_effect=[
            redis.exceptions.ConnectionError('1st'),
            redis.exceptions.ConnectionError('2nd'),
            True,  # 3rd success
        ])
        with patch.object(r.conn, 'ping', ping_mock):
            with patch('app.tools.redisdb.time.sleep'):
                assert r.ping() is True
        assert ping_mock.call_count == 3

    def test_03_ping_all_fail_raises(self):
        from app.tools.redisdb import ConnRedis
        r = ConnRedis()
        ping_mock = MagicMock(side_effect=redis.exceptions.ConnectionError('persistent'))
        with patch.object(r.conn, 'ping', ping_mock):
            with patch('app.tools.redisdb.time.sleep'):
                with pytest.raises(redis.exceptions.ConnectionError):
                    r.ping()
        assert ping_mock.call_count == 3  # default max_retries=3

    def test_04_ping_non_retriable_raises_immediately(self):
        from app.tools.redisdb import ConnRedis
        r = ConnRedis()
        ping_mock = MagicMock(side_effect=ValueError('not retriable'))
        with patch.object(r.conn, 'ping', ping_mock):
            with pytest.raises(ValueError):
                r.ping()
        # ValueError 不重试, 只 1 次
        assert ping_mock.call_count == 1

    def test_05_ping_retry_logs_warning(self, caplog):
        from app.tools.redisdb import ConnRedis
        r = ConnRedis()
        ping_mock = MagicMock(side_effect=[
            redis.exceptions.ConnectionError('fail'),
            True,
        ])
        with patch.object(r.conn, 'ping', ping_mock):
            with patch('app.tools.redisdb.time.sleep'):
                with caplog.at_level(logging.WARNING, logger='redis_retry'):
                    r.ping()
        warnings = [r for r in caplog.records
                    if r.name == 'redis_retry' and r.levelno == logging.WARNING]
        assert any('ping' in r.message for r in warnings)


# ============================================================
# 3) 源码检查
# ============================================================
class TestRev47M18SourceCode:
    """REV47-M18: 源码中含 retry helper."""

    def test_01_with_retry_method_exists(self):
        from app.tools.redisdb import ConnRedis
        assert hasattr(ConnRedis, '_with_retry')
        assert callable(ConnRedis._with_retry)

    def test_02_with_retry_signature(self):
        import inspect
        from app.tools.redisdb import ConnRedis
        sig = inspect.signature(ConnRedis._with_retry)
        params = list(sig.parameters.keys())
        assert 'callable_' in params
        assert 'max_retries' in params
        assert 'base_delay' in params
        assert 'max_delay' in params
        assert 'retriable_exceptions' in params
        assert 'op_name' in params

    def test_03_ping_uses_with_retry(self):
        import inspect
        from app.tools.redisdb import ConnRedis
        source = inspect.getsource(ConnRedis.ping)
        assert '_with_retry' in source

    def test_04_logger_name(self):
        from app.tools import redisdb
        assert redisdb._REDIS_RETRY_LOGGER == 'redis_retry'

    def test_05_imports(self):
        from app.tools import redisdb
        assert hasattr(redisdb, 'logging')
        assert hasattr(redisdb, 'time')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
