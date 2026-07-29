# -*- coding: utf-8 -*-
"""REV47-T3 测试: 跨模块"非关键写库失败降级"统一.

覆盖:
  1. app/tools/audsec.py:safe_db_write 核心行为
     (成功透传 / 失败降级 / reraise / logger 隔离 / context / 异常 logger)
  2. audlog._BaseToolsLog._write 委托 audsec.safe_db_write
  3. shellcmd.get_ssh_password 透明迁移委托 audsec.safe_db_write
  4. 静态结构 (import 验证 + 模块标记 REV47-T3 / REV44 / REV46)
"""
import inspect
import logging
import unittest.mock as mock
import pytest


# 辅助: 抛异常的 callable 工厂 (避免 yield 语法兼容问题)
def _raise(exc):
    """返回一个调用时抛 exc 的 callable."""
    def _f():
        raise exc
    return _f


# =============================================================================
# TestSafeDbWriteCore: audsec.safe_db_write 核心行为
# =============================================================================
class TestSafeDbWriteCore:
    """safe_db_write 核心: 成功透传 / 失败降级 / 日志 / reraise."""

    def test_success_returns_callable_result(self):
        """成功路径: callable 返回值原样透传."""
        from app.tools.audsec import safe_db_write
        assert safe_db_write(lambda: 42, 'op_test') == 42
        assert safe_db_write(lambda: 'foo', 'op_test') == 'foo'
        assert safe_db_write(lambda: None, 'op_test') is None

    def test_callable_exception_degrades_silently(self):
        """callable 抛任意 Exception -> 降级返回 None, 不抛."""
        from app.tools.audsec import safe_db_write
        # 不应 raise, 返回 None
        result = safe_db_write(_raise(RuntimeError('db connection lost')), 'op_boom')
        assert result is None

    def test_sqlop_error_is_caught(self):
        """SqlOpError (REV44 H4 触发) 同样被降级, 不阻断主业务."""
        from app.tools.audsec import safe_db_write
        # 模拟 SqlOpError, 不需要 import 真实类
        class FakeSqlOpError(Exception):
            pass
        # 不应 raise
        result = safe_db_write(
            _raise(FakeSqlOpError('table t_login_log write failed')),
            'audlog_insert', table='t_login_log',
        )
        assert result is None

    def test_reraise_true_propagates_exception(self):
        """reraise=True 时, callable 异常继续向上抛."""
        from app.tools.audsec import safe_db_write
        with pytest.raises(ValueError, match='force rethrow'):
            safe_db_write(_raise(ValueError('force rethrow')), 'op_reraise', reraise=True)

    def test_reraise_false_default_does_not_raise(self):
        """默认 reraise=False, 永远不抛."""
        from app.tools.audsec import safe_db_write
        # 默认 reraise=False, 不应 raise
        assert safe_db_write(_raise(ValueError('this should not propagate')), 'op_default') is None


# =============================================================================
# TestSafeDbWriteLogger: 日志行为
# =============================================================================
class TestSafeDbWriteLogger:
    """safe_db_write 日志: level / logger_name / context / 异常 logger 兜底."""

    def test_default_logger_is_audlog_fallback(self):
        """默认 logger_name = 'audlog_fallback' (与历史兼容)."""
        from app.tools.audsec import safe_db_write, _AUDSEC_DEFAULT_LOGGER
        assert _AUDSEC_DEFAULT_LOGGER == 'audlog_fallback'
        # mock 实际 logger 实例 (audsec 内部用 logging.getLogger 获取同一个)
        target = logging.getLogger('audlog_fallback')
        with mock.patch.object(target, 'log') as m_log:
            safe_db_write(_raise(RuntimeError('x')), 'op_test')
            assert m_log.called

    def test_level_error_uses_error_level(self):
        """level='error' -> logger.log(ERROR, ...)."""
        from app.tools.audsec import safe_db_write
        target = logging.getLogger('audlog_fallback')
        with mock.patch.object(target, 'log') as m_log:
            safe_db_write(
                _raise(RuntimeError('x')),
                'op_test', level='error',
            )
            assert m_log.called
            # 第一参数应为 ERROR level (整数 40)
            assert m_log.call_args[0][0] == logging.ERROR

    def test_level_warning_uses_warning_level(self):
        """level='warning' 走 WARNING (透明迁移场景)."""
        from app.tools.audsec import safe_db_write
        target = logging.getLogger('shellcmd')
        with mock.patch.object(target, 'log') as m_log:
            safe_db_write(
                _raise(RuntimeError('rehash fail')),
                'ssh_password_rehash',
                level='warning',
                logger_name='shellcmd',
                sys_user_id=42,
            )
            assert m_log.called
            assert m_log.call_args[0][0] == logging.WARNING

    def test_level_case_insensitive(self):
        """level 大小写不敏感."""
        from app.tools.audsec import safe_db_write
        target = logging.getLogger('audlog_fallback')
        with mock.patch.object(target, 'log') as m_log:
            safe_db_write(
                _raise(RuntimeError('x')),
                'op_test', level='ERROR',  # 大写
            )
            assert m_log.called
            assert m_log.call_args[0][0] == logging.ERROR

    def test_invalid_level_falls_back_to_error(self):
        """无效 level 名降级为 ERROR."""
        from app.tools.audsec import safe_db_write
        target = logging.getLogger('audlog_fallback')
        with mock.patch.object(target, 'log') as m_log:
            safe_db_write(
                _raise(RuntimeError('x')),
                'op_test', level='NOT_A_REAL_LEVEL',
            )
            assert m_log.called
            assert m_log.call_args[0][0] == logging.ERROR

    def test_custom_logger_name(self):
        """logger_name 显式传入, 走对应 logger (而非 audlog_fallback)."""
        from app.tools.audsec import safe_db_write
        custom = logging.getLogger('test_custom_logger_xyz_unique')
        with mock.patch.object(custom, 'log') as m_log:
            safe_db_write(
                _raise(RuntimeError('x')),
                'op_test',
                level='warning',
                logger_name='test_custom_logger_xyz_unique',
            )
            assert m_log.called

    def test_context_in_log_message(self):
        """**context kwargs 出现在日志消息中 (k=v 格式)."""
        from app.tools.audsec import safe_db_write
        target = logging.getLogger('audlog_fallback')
        with mock.patch.object(target, 'log') as m_log:
            safe_db_write(
                _raise(RuntimeError('boom')),
                'audlog_insert',
                level='error',
                table='t_login_log',
                sys_user_id=99,
            )
            assert m_log.called
            msg = m_log.call_args[0][1]  # 第二参数: 消息
            assert 'audlog_insert' in msg
            assert 't_login_log' in msg
            assert '99' in msg
            assert 'boom' in msg

    def test_empty_context_still_works(self):
        """无 context 时, 日志消息只含 op_name + err (不报错)."""
        from app.tools.audsec import safe_db_write
        target = logging.getLogger('audlog_fallback')
        with mock.patch.object(target, 'log') as m_log:
            safe_db_write(
                _raise(RuntimeError('x')),
                'op_no_ctx',
            )
            assert m_log.called
            msg = m_log.call_args[0][1]
            assert 'op_no_ctx' in msg

    def test_logger_itself_broken_does_not_propagate(self):
        """logger 自身抛异常 (e.g. handler 坏掉) 也不阻断主业务."""
        from app.tools.audsec import safe_db_write
        # 让 logger.log 自身抛异常, safe_db_write 必须吃掉
        target = logging.getLogger('audlog_fallback')
        with mock.patch.object(
            target, 'log', side_effect=TypeError('handler broken'),
        ):
            # 不应 raise
            result = safe_db_write(_raise(RuntimeError('db error')), 'op_logger_broken')
            assert result is None


# =============================================================================
# TestAudlogDelegatesToAudsec: audlog._write 委托验证
# =============================================================================
class TestAudlogDelegatesToAudsec:
    """REV47-T3: audlog._write 走 audsec.safe_db_write, 消除内联 try/except."""

    def test_audlog_imports_audsec(self):
        """audlog 模块顶层 import 了 audsec.safe_db_write."""
        from app.tools import audlog
        assert hasattr(audlog, 'safe_db_write'), \
            "REV47-T3: audlog 应 import audsec.safe_db_write"

    def test_audlog_write_calls_safe_db_write(self):
        """_BaseToolsLog._write 实际调用 safe_db_write (而非内联 try/except)."""
        # 关键: audlog 顶层是 `from app.tools.audsec import safe_db_write`,
        # 所以 audlog.safe_db_write 是 audsec.safe_db_write 的引用.
        # patch audlog.safe_db_write (模块级引用) 才能截获.
        from app.tools import audlog
        with mock.patch.object(audlog, 'safe_db_write') as spy:
            spy.return_value = None
            log = audlog.LoginToolsLog()
            log._write(log_name='alice', log_nw_ip='1.2.3.4', log_agent='UA')
            assert spy.called, "_write 必须调用 audsec.safe_db_write"
            # 验证 op_name 是 audlog_insert
            kwargs = spy.call_args.kwargs
            assert kwargs.get('op_name') == 'audlog_insert'
            assert kwargs.get('level') == 'error'
            assert kwargs.get('table') == 't_login_log'

    def test_audlog_no_inline_try_except(self):
        """audlog._write 源码中不应再有内联 try/except 模式."""
        from app.tools import audlog
        source = inspect.getsource(audlog._BaseToolsLog._write)
        # 不应有 'try:' (内联 try/except 已被 safe_db_write 替代)
        assert 'try:' not in source, \
            "REV47-T3: audlog._write 不应再有内联 try/except"
        # 应有 safe_db_write 调用
        assert 'safe_db_write' in source

    def test_audlog_logger_name_compat_preserved(self):
        """_audlog_fallback_logger 仍存在 (向后兼容)."""
        from app.tools import audlog
        assert hasattr(audlog, '_audlog_fallback_logger')
        assert audlog._audlog_fallback_logger.name == 'audlog_fallback'


# =============================================================================
# TestShellcmdRehashDelegatesToAudsec: shellcmd 透明迁移委托验证
# =============================================================================
class TestShellcmdRehashDelegatesToAudsec:
    """REV47-T3: shellcmd.get_ssh_password rehash 走 audsec.safe_db_write."""

    def test_shellcmd_imports_audsec(self):
        """shellcmd 模块顶层 import 了 audsec.safe_db_write."""
        from app.tools import shellcmd
        assert hasattr(shellcmd, 'safe_db_write'), \
            "REV47-T3: shellcmd 应 import audsec.safe_db_write"

    def test_rehash_calls_safe_db_write(self):
        """get_ssh_password._rehash 实际调用 safe_db_write (非内联 try/except)."""
        from app.tools import shellcmd
        from app.tools.audsec import safe_db_write

        fake_row = mock.MagicMock()
        fake_row.id = 7
        fake_row.host_password = 'any_value'

        # 关键: shellcmd 顶层 `from app.tools.audsec import safe_db_write`,
        # patch shellcmd.safe_db_write 截获 (不是 audsec.safe_db_write).
        def fake_decrypt(stored, rehash_callback=None):
            if rehash_callback is not None:
                rehash_callback('new_encrypted_stored')
            return 'plain_password'

        with mock.patch.object(shellcmd, 'safe_db_write') as spy:
            spy.return_value = None
            with mock.patch.object(shellcmd, 'decrypt_host_password', side_effect=fake_decrypt):
                with mock.patch('app.core.db.insert.osql_up', return_value=1):
                    result = shellcmd.get_ssh_password(fake_row)

        # decrypt 应返回明文
        assert result == 'plain_password'
        # _rehash 必须经过 safe_db_write
        assert spy.called, "_rehash 必须调用 audsec.safe_db_write"
        kwargs = spy.call_args.kwargs
        assert kwargs.get('op_name') == 'ssh_password_rehash'
        assert kwargs.get('level') == 'warning'
        assert kwargs.get('logger_name') == 'shellcmd'
        assert kwargs.get('sys_user_id') == 7

    def test_rehash_does_not_propagate_db_error(self):
        """osql_up 抛异常时, _rehash 不阻断 decrypt 返回明文 (与历史语义一致)."""
        from app.tools import shellcmd

        fake_row = mock.MagicMock()
        fake_row.id = 8
        fake_row.host_password = 'any_value'

        def fake_decrypt(stored, rehash_callback=None):
            if rehash_callback is not None:
                # rehash 自身不抛 (降级)
                rehash_callback('new_stored')
            return 'plain_pwd'

        class FakeSqlOpError(Exception):
            pass

        with mock.patch.object(shellcmd, 'decrypt_host_password', side_effect=fake_decrypt), \
             mock.patch('app.core.db.insert.osql_up',
                        side_effect=FakeSqlOpError('db unavailable')):
            # 不应 raise, 应返回明文
            result = shellcmd.get_ssh_password(fake_row)
            assert result == 'plain_pwd'

    def test_shellcmd_no_inline_try_in_rehash(self):
        """shellcmd.get_ssh_password 源码应含 safe_db_write 调用."""
        from app.tools import shellcmd
        source = inspect.getsource(shellcmd.get_ssh_password)
        # safe_db_write 必须在源码中
        assert 'safe_db_write' in source, \
            "REV47-T3: get_ssh_password 源码应含 safe_db_write 调用"


# =============================================================================
# TestAudsecModuleStructure: 模块结构与标记
# =============================================================================
class TestAudsecModuleStructure:
    """REV47-T3 静态结构: 模块存在 + 关键标记 + 历史溯源."""

    def test_audsec_module_exists(self):
        import app.tools.audsec as _mod
        assert hasattr(_mod, 'safe_db_write')
        assert hasattr(_mod, '_AUDSEC_DEFAULT_LOGGER')

    def test_audsec_has_rev47_t3_marker(self):
        """audsec.py 源码应含 REV47-T3 标记 + 历史溯源 REV44/REV46."""
        from app.tools import audsec
        source = inspect.getsource(audsec)
        assert 'REV47-T3' in source, "audsec.py 应含 REV47-T3 标记"
        assert 'REV44' in source, "audsec.py 应溯源 REV44 H4 (audlog 模式)"
        assert 'REV46' in source, "audsec.py 应溯源 REV46 H20 (rehash 模式)"

    def test_audsec_module_docstring(self):
        """模块 docstring 描述用途."""
        from app.tools import audsec
        assert audsec.__doc__ is not None
        assert 'REV47-T3' in audsec.__doc__
        # 应说明"不阻断主业务"语义
        assert '不阻断' in audsec.__doc__ or '降级' in audsec.__doc__

    def test_safe_db_write_signature(self):
        """safe_db_write 签名: callable_, op_name, *, level, logger_name, reraise, **context."""
        from app.tools.audsec import safe_db_write
        sig = inspect.signature(safe_db_write)
        params = list(sig.parameters.keys())
        # 前两个位置参数
        assert params[0] == 'callable_'
        assert params[1] == 'op_name'
        # keyword-only 参数
        assert 'level' in sig.parameters
        assert 'logger_name' in sig.parameters
        assert 'reraise' in sig.parameters
        # reraise 默认 False
        assert sig.parameters['reraise'].default is False
        # level 默认 'error'
        assert sig.parameters['level'].default == 'error'
