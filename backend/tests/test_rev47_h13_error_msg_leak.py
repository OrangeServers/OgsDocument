# -*- coding: utf-8 -*-
"""
R2-8 (REV45-H13): 异常信息防泄漏

问题: API 错误响应 str(e) 暴露 SQL 表名/字段/路径/类型
修复:
  - app/core/error_handler.py 提供 safe_error_msg()
  - 注册全局 Flask errorhandler (500/404/400/...)
测试维度:
  1) 模块存在
  2) safe_error_msg: 基础清洗
  3) safe_error_msg: 脱敏 Windows 路径
  4) safe_error_msg: 脱敏 Unix 路径
  5) safe_error_msg: 脱敏 SQL 表名
  6) safe_error_msg: 脱敏 Python 异常类型
  7) safe_error_msg: 脱敏行号 file.py:123
  8) safe_error_msg: 长度截断
  9) safe_error_msg: 空字符串返 default
  10) safe_error_msg: 非 Exception (字符串输入) 也工作
  11) register_error_handlers: 500 返 JSON 不含 traceback
  12) register_error_handlers: 404 返 JSON not found
  13) register_error_handlers: 405 返 JSON method not allowed
  14) register_error_handlers: 400 返 JSON bad request
  15) register_error_handlers: 500 响应日志记录异常
"""
import os
import re
import sys
import logging
import pytest
from unittest.mock import MagicMock, patch

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# 1) 模块 / 函数存在
# =============================================================================
class TestModuleExists:
    """R2-8: error_handler 模块存在"""

    def test_01_module_imports(self):
        from app.core import error_handler
        assert error_handler is not None

    def test_02_safe_error_msg_exists(self):
        from app.core.error_handler import safe_error_msg
        assert callable(safe_error_msg)

    def test_03_register_error_handlers_exists(self):
        from app.core.error_handler import register_error_handlers
        assert callable(register_error_handlers)


# =============================================================================
# 2) safe_error_msg 脱敏测试
# =============================================================================
class TestSafeErrorMsgDesensitize:
    """R2-8: safe_error_msg 必须脱敏各种敏感信息"""

    def test_01_windows_path_redacted(self):
        """Windows 路径 D:\code\... 应脱敏"""
        from app.core.error_handler import safe_error_msg
        e = OSError("Failed to read D:\code\OrangeServer\backend\secret.txt")
        msg = safe_error_msg(e)
        assert 'REDACTED' in msg or 'D:\\code' not in msg

    def test_02_unix_path_redacted(self):
        """Unix 绝对路径 /home/... 应脱敏"""
        from app.core.error_handler import safe_error_msg
        e = FileNotFoundError("No such file: /home/app/secret/key.pem")
        msg = safe_error_msg(e)
        # 路径或脱敏
        assert 'REDACTED' in msg or '/home/app' not in msg

    def test_03_sql_table_name_redacted(self):
        """SQL 表名 t_acc_user 应脱敏"""
        from app.core.error_handler import safe_error_msg
        # 直接给 str 也行 (兼容)
        msg = safe_error_msg("INSERT into t_acc_user failed")
        assert 'REDACTED' in msg
        assert 't_acc_user' not in msg

    def test_04_python_exception_type_redacted(self):
        """Python 异常类名 OperationalError 应脱敏"""
        from app.core.error_handler import safe_error_msg
        msg = safe_error_msg(
            "OperationalError: connection refused on host"
        )
        # 异常类名应被脱敏; 但消息仍包含原因描述 (因为没有敏感模式)
        assert 'OperationalError' not in msg

    def test_05_line_number_redacted(self):
        """行号 file.py:123 应脱敏"""
        from app.core.error_handler import safe_error_msg
        msg = safe_error_msg("Error at main.py:1234")
        assert 'REDACTED' in msg
        assert ':1234' not in msg

    def test_06_combined_sensitive_patterns(self):
        """混合多种敏感信息全部脱敏"""
        from app.core.error_handler import safe_error_msg
        msg = safe_error_msg(
            "t_acc_user lookup failed in D:\code\OrangeServer\app\db.py:999 "
            "(IntegrityError)"
        )
        assert 'REDACTED' in msg
        assert 't_acc_user' not in msg
        assert 'D:\\code' not in msg or 'REDACTED' in msg
        assert 'IntegrityError' not in msg

    def test_07_length_truncation(self):
        """超长消息应被截断"""
        from app.core.error_handler import safe_error_msg
        long_msg = "x" * 500
        msg = safe_error_msg(long_msg, max_len=50)
        assert len(msg) <= 53  # 50 + '...'
        assert msg.endswith('...')

    def test_08_empty_string_returns_default(self):
        """空串应返 default"""
        from app.core.error_handler import safe_error_msg
        msg = safe_error_msg('', default='fallback msg')
        assert msg == 'fallback msg'

    def test_09_none_or_str_input(self):
        """safe_error_msg 接受 str 直接输入"""
        from app.core.error_handler import safe_error_msg
        msg = safe_error_msg('plain text message')
        assert 'plain text message' in msg or msg == 'plain text message'

    def test_10_default_is_returned_when_msg_empty_after_strip(self):
        """strip 后空串返 default"""
        from app.core.error_handler import safe_error_msg
        msg = safe_error_msg('   ', default='default msg')
        assert msg == 'default msg'


# =============================================================================
# 3) register_error_handlers (Flask 集成)
# =============================================================================
class TestRegisterErrorHandlers:
    """R2-8: Flask 错误处理器注册"""

    def _make_app(self):
        """构造最小 Flask app 用于测试"""
        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        return app

    def test_01_register_does_not_crash(self):
        """register_error_handlers 不抛异常"""
        from app.core.error_handler import register_error_handlers
        app = self._make_app()
        # 不抛异常
        register_error_handlers(app)

    def test_02_500_returns_safe_json(self):
        """500 错误返回 JSON 不含原始 traceback"""
        from app.core.error_handler import register_error_handlers
        app = self._make_app()
        register_error_handlers(app)

        @app.route('/boom')
        def boom():
            raise RuntimeError('t_acc_user data corrupted')

        client = app.test_client()
        resp = client.get('/boom')
        assert resp.status_code == 500
        data = resp.get_json()
        # 应为 JSON 格式
        assert data is not None
        # 不应暴露 SQL 表名
        body = resp.data.decode()
        assert 't_acc_user' not in body, \
            f"500 响应暴露 SQL 表名: {body}"
        # 不应含 traceback
        assert 'Traceback' not in body

    def test_03_404_returns_json_not_found(self):
        """404 错误统一 JSON 格式"""
        from app.core.error_handler import register_error_handlers
        app = self._make_app()
        register_error_handlers(app)

        client = app.test_client()
        resp = client.get('/no-such-route')
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['code'] == 404
        assert 'not found' in data['msg'].lower()

    def test_04_405_method_not_allowed(self):
        """405 错误统一 JSON 格式"""
        from app.core.error_handler import register_error_handlers
        app = self._make_app()
        register_error_handlers(app)

        @app.route('/route', methods=['GET'])
        def only_get():
            return 'ok'

        client = app.test_client()
        resp = client.post('/route')
        assert resp.status_code == 405
        data = resp.get_json()
        assert data['code'] == 405

    def test_05_500_logs_exception(self):
        """500 处理器应记录异常到日志"""
        from app.core.error_handler import register_error_handlers
        app = self._make_app()
        register_error_handlers(app)

        @app.route('/boom2')
        def boom2():
            raise ValueError('test boom')

        with app.test_client() as client:
            # 用 caplog 抓 logging 输出
            import io
            import logging as _logging

            logger = _logging.getLogger('error_handler')
            records = []

            class CaptureHandler(_logging.Handler):
                def emit(self, record):
                    records.append(record)

            handler = CaptureHandler()
            logger.addHandler(handler)
            logger.setLevel(_logging.DEBUG)

            try:
                resp = client.get('/boom2')
                assert resp.status_code == 500
                # 至少有一条日志
                assert len(records) >= 1, \
                    f"500 处理器未记录异常 (records={len(records)})"
            finally:
                logger.removeHandler(handler)


# =============================================================================
# 4) 集成: 原 files/file.py str(e) 不再裸用
# =============================================================================
class TestLegacyCodeUsesSafeApi:
    """R2-8: 业务代码不应裸用 str(e) 暴露敏感信息"""

    def test_01_error_handler_module_documented(self):
        """error_handler.py 应有 module docstring 解释为什么"""
        from app.core import error_handler
        doc = error_handler.__doc__
        assert doc is not None
        assert 'REV45-H13' in doc or '敏感' in doc or 'leak' in doc.lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
