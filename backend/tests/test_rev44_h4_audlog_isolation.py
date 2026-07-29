# -*- coding: utf-8 -*-
"""REV44-H4: 审计日志写库失败 → 不阻断主业务.

背景:
- 审计日志 (t_login_log / t_cz_log / t_command_log) 写库失败会抛 SqlOpError
- 调用方 (user.py host_log) 没有 try/except → 主业务 500
- 修复: _BaseToolsLog._write 内部包 try/except, 失败 fallback 到 _audlog_fallback_logger

测试覆盖:
- TestBaseToolsLogIsolation: _write 写库失败 → 不抛, 走 fallback logger
- TestSubclassHostLog: 三个 Log 子类 host_log 异常隔离
- TestFallbackLogger: 防御性 - _audlog_fallback_logger 必须暴露
"""
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# TestBaseToolsLogIsolation: _write 写库失败隔离
# =============================================================================
class TestBaseToolsLogIsolation:
    """REV44-H4: _BaseToolsLog._write 写库异常不向上抛."""

    def test_normal_write_no_exception(self, monkeypatch):
        """正常路径: osql_in 成功 → _write 不抛."""
        from app.tools.audlog import _BaseToolsLog

        captured = []
        monkeypatch.setattr('app.tools.audlog.osql_in',
                            lambda table, **kw: captured.append((table, kw)) or MagicMock())

        # 直接构造一个最小子类用于测试
        class _TestLog(_BaseToolsLog):
            _TABLE = 't_test_log'
            _FIELDS = [('log_name', 30, True), ('log_details', 255, True)]

        log = _TestLog()
        log._write(log_name='hello', log_details='world')

        assert len(captured) == 1
        tbl, kwargs = captured[0]
        assert tbl == 't_test_log'
        assert kwargs['log_name'] == 'hello'
        assert kwargs['log_details'] == 'world'
        assert 'log_time' in kwargs, "log_time 应自动附加"

    def test_sqlop_error_does_not_propagate(self, monkeypatch, caplog):
        """REV44-H4 核心: osql_in 抛 SqlOpError → _write 不向上抛.

        REV47-T3: _write 改走 audsec.safe_db_write, 日志由 audsec 内部
        logging.getLogger('audlog_fallback') 发出. 这里用 caplog 捕获,
        验证: (1) 不抛, (2) logger 收到 ERROR 级别, (3) 消息含 op_name + table.
        """
        import logging
        from app.tools import audlog as _audlog_mod
        from app.tools.audlog import _BaseToolsLog
        from app.core.db.insert import SqlOpError as _RealSqlOpError

        def fake_osql_in_raises(*a, **kw):
            raise _RealSqlOpError('模拟 DB 失败')
        monkeypatch.setattr(_audlog_mod, 'osql_in', fake_osql_in_raises)

        class _TestLog(_BaseToolsLog):
            _TABLE = 't_test_log'
            _FIELDS = [('log_name', 30, True)]

        log = _TestLog()
        with caplog.at_level(logging.ERROR, logger='audlog_fallback'):
            # 不应抛异常
            log._write(log_name='hello')

        # audlog_fallback logger 应收到 ERROR 级别日志
        errors = [r for r in caplog.records
                  if r.name == 'audlog_fallback' and r.levelno >= logging.ERROR]
        assert len(errors) >= 1, \
            f"audlog_fallback logger 应收到 ERROR 日志, 实际 {len(errors)} 条"
        log_msg = errors[0].message
        assert 't_test_log' in log_msg, f"log_msg 应包含表名, 实际: {log_msg}"
        assert '模拟 DB 失败' in log_msg, f"log_msg 应包含原异常信息, 实际: {log_msg}"

    def test_generic_exception_also_caught(self, monkeypatch, caplog):
        """REV44-H4: 任何 Exception (不只 SqlOpError) 都被 catch.

        REV47-T3: 同上, 改用 caplog 验证 audsec 内部 logger 收到消息.
        """
        import logging
        from app.tools import audlog as _audlog_mod
        from app.tools.audlog import _BaseToolsLog

        def fake_osql_in_raises(*a, **kw):
            raise RuntimeError('任何异常')
        monkeypatch.setattr(_audlog_mod, 'osql_in', fake_osql_in_raises)

        class _TestLog(_BaseToolsLog):
            _TABLE = 't_test_log'
            _FIELDS = []

        log = _TestLog()
        with caplog.at_level(logging.ERROR, logger='audlog_fallback'):
            # RuntimeError 也不应向上抛
            log._write()
        errors = [r for r in caplog.records
                  if r.name == 'audlog_fallback' and r.levelno >= logging.ERROR]
        assert len(errors) >= 1, "audlog_fallback logger 应收到 ERROR 日志"

    def test_fallback_logger_itself_fails_silently(self, monkeypatch):
        """REV44-H4 兜底: 即便 fallback logger 自身失败, 也不向上抛."""
        from app.tools import audlog as _audlog_mod
        from app.tools.audlog import _BaseToolsLog

        def fake_osql_in_raises(*a, **kw):
            raise RuntimeError('DB 失败')
        monkeypatch.setattr(_audlog_mod, 'osql_in', fake_osql_in_raises)

        # fallback logger 自身也抛异常
        def broken_log(*a, **kw):
            raise OSError('disk full')
        monkeypatch.setattr(
            _audlog_mod, '_audlog_fallback_logger',
            MagicMock(error=broken_log)
        )

        class _TestLog(_BaseToolsLog):
            _TABLE = 't_test_log'
            _FIELDS = []

        log = _TestLog()
        # 不应抛 OSError, 也不应抛 RuntimeError
        # (silent-fail: 审计是辅助, 任何路径都不能影响主业务)
        log._write()


# =============================================================================
# TestSubclassHostLog: 三个 Log 子类异常隔离
# =============================================================================
class TestSubclassHostLog:
    """REV44-H4: LoginToolsLog / CzToolsLog / ComToolsLog 的 host_log 异常隔离."""

    def _setup_osql_raises(self, monkeypatch):
        from app.tools import audlog as _audlog_mod
        def fake_osql_in_raises(*a, **kw):
            raise RuntimeError('t_log 表写失败')
        monkeypatch.setattr(_audlog_mod, 'osql_in', fake_osql_in_raises)
        monkeypatch.setattr(
            _audlog_mod, '_audlog_fallback_logger',
            MagicMock(error=lambda msg: None)
        )

    def test_login_tools_log_host_log_no_propagate(self, monkeypatch):
        """LoginToolsLog.host_log 写库失败不抛."""
        from app.tools.audlog import LoginToolsLog
        self._setup_osql_raises(monkeypatch)

        log = LoginToolsLog()
        # 7 个参数, 任一调用都应不抛
        log.host_log(
            log_name='alice', log_nw_ip='10.0.0.1', log_gw_ip='gw',
            log_gw_cs='cs', log_agent='UA', log_status='200',
        )

    def test_cz_tools_log_host_log_no_propagate(self, monkeypatch):
        """CzToolsLog.host_log 写库失败不抛."""
        from app.tools.audlog import CzToolsLog
        self._setup_osql_raises(monkeypatch)

        log = CzToolsLog()
        log.host_log(
            log_name='bob', log_type='用户组操作',
            log_info='删除', log_details='qa', log_status='成功',
        )

    def test_com_tools_log_host_log_no_propagate(self, monkeypatch):
        """ComToolsLog.host_log 写库失败不抛."""
        from app.tools.audlog import ComToolsLog
        self._setup_osql_raises(monkeypatch)

        log = ComToolsLog()
        log.host_log(
            log_name='cmd', log_type='shell',
            log_info='ls', log_host='web1', log_status='ok',
        )

    def test_cz_tools_log_realistic_scenario(self, monkeypatch):
        """真实场景模拟: user.py AccUserAdd.__init__ 调 self.host_log,
        数据库挂时, 用户添加流程不应 500."""
        from app.tools.audlog import CzToolsLog
        self._setup_osql_raises(monkeypatch)

        log = CzToolsLog()
        # user.py:117 host_log 调用形式
        log.host_log(
            log_name='admin', log_type='用户操作',
            log_info='新增用户', log_details='alice', log_status='成功',
            log_msg='req_body: [...]',
        )


# =============================================================================
# TestFallbackLogger: 防御性 - 修复必须暴露
# =============================================================================
class TestFallbackLogger:
    """REV44-H4: 防御性测试."""

    def test_fallback_logger_exported(self):
        from app.tools import audlog as _audlog_mod
        assert hasattr(_audlog_mod, '_audlog_fallback_logger'), \
            "REV44-H4 修复: _audlog_fallback_logger 必须暴露在 audlog.py 模块级"

    def test_fallback_logger_name(self):
        from app.tools import audlog as _audlog_mod
        # 验证 logger name 是 'audlog_fallback' (与评审建议一致)
        assert _audlog_mod._audlog_fallback_logger.name == 'audlog_fallback', \
            f"logger 名称应为 'audlog_fallback', 实际 {_audlog_mod._audlog_fallback_logger.name}"

    def test_fallback_logger_has_error_method(self):
        """fallback logger 必须有 .error() 方法."""
        from app.tools import audlog as _audlog_mod
        assert hasattr(_audlog_mod._audlog_fallback_logger, 'error'), \
            "_audlog_fallback_logger 必须有 .error() 方法"
