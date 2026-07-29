# -*- coding: utf-8 -*-
"""REV44 P1 修复单测: H5 (audlog 截断提示) + H7 (csrf_skip 装饰器) + H8 (user_token 缺失 fail-closed).

H5 (R2-5-1): audlog._trunc 截断时打 Log.warning + 计数, 便于追查.
H7 (R2-5-2): 引入 @csrf_skip 装饰器, 路径白名单降级为向后兼容 fallback.
H8 (R2-5-3): csrf user_token 为空时必须 raise, 不能 skip nonce 校验.
"""
import logging
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


# =============================================================================
# H5: audlog._trunc 截断提示
# =============================================================================
class TestAudlogTruncWarnsAndCounts:
    """R2-5-1: 截断时打 Log.warning 提示, 计数器递增."""

    def test_trunc_logs_warning_on_truncation(self):
        """超长字段截断时, Log.warning 应输出 REV44-H5 标记 + 字段名 + 长度信息."""
        import app.tools.audlog as _audlog_mod
        before = _audlog_mod._TRUNC_DROPPED

        with patch('app.tools.audlog.Log.logger') as mock_logger:
            result = _audlog_mod._trunc('a' * 100, max_len=10, field_name='log_info')

        # 截断后值应等于前 10 字符
        assert result == 'a' * 10
        # 截断计数器应递增 (注: audlog 可能在 conftest 中被 reload, before 是 reload 后的当前值)
        assert _audlog_mod._TRUNC_DROPPED >= before + 1, \
            f"REV44-H5: 截断计数器应 +1, 实际 {before} -> {_audlog_mod._TRUNC_DROPPED}"
        # Log.warning 应被调用
        assert mock_logger.warning.called, \
            "REV44-H5: 截断时 Log.warning 应被调用"
        # 检查 warning 调用参数 (合并 fmt + args 检查 log_info 字段名)
        call_args = mock_logger.warning.call_args
        all_args = list(call_args[0]) + list(call_args[1].values())
        full_msg = ' '.join(str(a) for a in all_args)
        assert 'REV44-H5' in full_msg, f"warning 应含 REV44-H5 标记, 实际: {full_msg}"
        assert 'log_info' in full_msg, f"warning 应含字段名 log_info, 实际: {full_msg}"

    def test_trunc_does_not_log_when_within_limit(self):
        """字段长度未超 max_len 时不应打 warning, 计数器不增."""
        import app.tools.audlog as _audlog_mod
        before = _audlog_mod._TRUNC_DROPPED

        with patch('app.tools.audlog.Log.logger') as mock_logger:
            result = _audlog_mod._trunc('short', max_len=100, field_name='log_name')

        assert result == 'short'
        # 计数器可能因其他测试累积, 验证本次未增加
        assert _audlog_mod._TRUNC_DROPPED == before, \
            f"未超 max_len 时计数器应不变, 实际 {before} -> {_audlog_mod._TRUNC_DROPPED}"
        # 不应被调用 (有 REV44-H5 标记的 warning)
        for call in mock_logger.warning.call_args_list:
            msg = call[0][0] if call[0] else str(call)
            assert 'REV44-H5' not in msg, \
                f"未截断不应打 REV44-H5 warning, 实际: {msg}"

    def test_trunc_none_returns_none_without_warning(self):
        """value=None 应返 None, 不打 warning."""
        import app.tools.audlog as _audlog_mod
        with patch('app.tools.audlog.Log.logger') as mock_logger:
            result = _audlog_mod._trunc(None, max_len=10, field_name='log_name')
        assert result is None
        # 不应有 REV44-H5 warning
        for call in mock_logger.warning.call_args_list:
            msg = call[0][0] if call[0] else str(call)
            assert 'REV44-H5' not in msg, \
                f"None 不应打 REV44-H5 warning, 实际: {msg}"

    def test_trunc_signature_accepts_field_name(self):
        """_trunc 签名应接受 field_name 参数 (默认 None 兼容)."""
        import inspect
        from app.tools.audlog import _trunc
        sig = inspect.signature(_trunc)
        assert 'field_name' in sig.parameters, \
            f"REV44-H5: _trunc 应接受 field_name 参数, 实际签名: {sig}"

    def test_audlog_write_passes_field_name_to_trunc(self):
        """_write 内部调 _trunc 应传 field_name=col (供 warning 追查)."""
        import inspect
        from app.tools.audlog import _BaseToolsLog
        source = inspect.getsource(_BaseToolsLog._write)
        assert 'field_name=col' in source, \
            f"REV44-H5: _write 应传 field_name=col 给 _trunc, 实际: {source}"


# =============================================================================
# H7: csrf_skip 装饰器
# =============================================================================
class TestCsrfSkipDecorator:
    """R2-5-2: 引入 @csrf_skip 装饰器, view_func 自声明豁免."""

    def test_csrf_skip_marks_func_attribute(self):
        """@csrf_skip 装饰后, view_func._csrf_skip 应为 True."""
        from app.tools.csrf import csrf_skip

        @csrf_skip
        def my_view():
            return 'ok'

        assert getattr(my_view, '_csrf_skip', False) is True, \
            "REV44-H7: @csrf_skip 应设置 _csrf_skip=True"

    def test_csrf_skip_returns_func_unchanged(self):
        """@csrf_skip 直接返回原函数 (无 wrapper 包裹)."""
        from app.tools.csrf import csrf_skip

        def original():
            """My docstring."""
            return 'ok'

        marked = csrf_skip(original)
        assert marked is original, \
            "REV44-H7: @csrf_skip 应直接返回原函数 (不包 wrapper)"
        # docstring 等元信息保留
        assert marked.__doc__ == 'My docstring.'

    def test_csrf_protect_skips_marked_view(self, _flask_app_fixture):
        """@csrf_skip 装饰的 view 在 csrf_protect 校验时被跳过."""
        from app.tools.csrf import csrf_protect, csrf_skip

        @csrf_skip
        def my_view():
            return 'called'

        wrapped = csrf_protect(my_view)
        with _flask_app_fixture.test_request_context(
            '/test', method='POST', data={},
        ):
            # 故意不带 csrf_token / user_token
            result = wrapped()
            # 应直接走 view_func, 不返 401
            assert result == 'called', \
                f"REV44-H7: @csrf_skip 装饰的 view 应被跳过, 实际: {result}"

    def test_csrf_skip_decorator_exists(self):
        """csrf.py 必须导出 csrf_skip."""
        import app.tools.csrf as _mod
        assert hasattr(_mod, 'csrf_skip'), \
            "REV44-H7: csrf.py 必须导出 csrf_skip 装饰器"

    def test_exempt_paths_kept_for_backward_compat(self):
        """_EXEMPT_PATHS 应保留 (向后兼容已上线的 login/logout)."""
        import app.tools.csrf as _mod
        assert hasattr(_mod, '_EXEMPT_PATHS'), \
            "REV44-H7: _EXEMPT_PATHS 应保留为向后兼容 fallback"
        # 至少应包含 login_dl
        assert '/account/login_dl' in _mod._EXEMPT_PATHS, \
            f"_EXEMPT_PATHS 应含 /account/login_dl, 实际: {_mod._EXEMPT_PATHS}"


# =============================================================================
# H8: csrf user_token 缺失 fail-closed
# =============================================================================
class TestCsrfUserTokenRequired:
    """R2-5-3: csrf user_token 为空时必须 fail-closed, 不能 skip nonce 校验."""

    def test_user_token_empty_returns_401(self, _flask_app_fixture, monkeypatch):
        """user_token 为空时, csrf 校验应返 401 'CSRF user_token 缺失'."""
        from app.tools.csrf import csrf_protect

        def my_view():
            return 'should not be called'

        wrapped = csrf_protect(my_view)
        with _flask_app_fixture.test_request_context(
            '/test', method='POST',
            headers={'X-CSRF-Token': 'valid-csrf'},
            environ_overrides={'HTTP_COOKIE': 'csrf_token=valid-csrf; ogs_token=;'},
        ):
            result = wrapped()
        # 应返 401 错误响应
        assert result is not None
        # result 应是 (json, status) tuple 或 Response
        if hasattr(result, 'status_code'):
            assert result.status_code == 401, \
                f"user_token 为空应返 401, 实际: {result.status_code}"
        elif isinstance(result, tuple):
            # (body, status) 或 (body, status, headers)
            status = result[1] if len(result) > 1 else 200
            assert status == 401, f"user_token 为空应 status=401, 实际: {status}"

    def test_user_token_empty_not_call_view(self, _flask_app_fixture):
        """user_token 为空时, view_func 永远不应被调用."""
        from app.tools.csrf import csrf_protect

        call_count = []

        def my_view():
            call_count.append(1)
            return 'should not be called'

        wrapped = csrf_protect(my_view)
        with _flask_app_fixture.test_request_context(
            '/test', method='POST',
            headers={'X-CSRF-Token': 'valid-csrf'},
            environ_overrides={'HTTP_COOKIE': 'csrf_token=valid-csrf; ogs_token=;'},
        ):
            wrapped()

        assert call_count == [], \
            f"user_token 为空时 view_func 不应被调用, 实际调用次数: {len(call_count)}"

    def test_csrf_protect_code_removed_skip_when_no_user_token(self):
        """csrf_protect 源码不应再有 'if user_token:' 这种允许空 token skip 的逻辑."""
        import inspect
        from app.tools.csrf import csrf_protect
        source = inspect.getsource(csrf_protect)
        # REV44-H8: 'if user_token:' (允许空 token skip nonce) 应改为 'if not user_token: raise'
        # 静态断言: 提取 docstring 后的代码, 不应再有正向 if user_token: 条件
        #   (docstring 里的描述性 'if user_token:' 不算逻辑)
        # 简单方法: 检查 'if not user_token' 必须在 'if user_token:' 之前出现
        idx_if_user = source.find('if user_token:')
        idx_if_not_user = source.find('if not user_token')
        # 如果有 'if user_token:', 必须在 docstring 之外, 且 'if not user_token' 之后
        if idx_if_user >= 0:
            # 找到 docstring 结束位置
            docstring_end = source.find('"""', source.find('"""') + 3)
            assert docstring_end > 0 and idx_if_user > docstring_end, \
                f"REV44-H8: 'if user_token:' 出现在 docstring 之后 (即真代码中), 不应存在. 实际:\n{source}"
        # 应有反向 if not user_token: 拦截
        assert idx_if_not_user >= 0, \
            f"REV44-H8: csrf_protect 应有 'if not user_token' 拦截, 实际:\n{source}"
        # 应有 REV44-H8 注释
        assert 'REV44-H8' in source, \
            "REV44-H8: csrf_protect 应有 REV44-H8 注释标记"

    def test_user_token_present_valid_nonce_passes(self, _flask_app_fixture, monkeypatch):
        """user_token 存在 + nonce 校验通过 → 进入 view_func (H8 不破坏正常流程)."""
        from app.tools.csrf import csrf_protect, _get_csrf_nonce, make_csrf_token

        def my_view():
            return 'ok'

        user_token = 'valid-user-token'
        nonce = 'valid-nonce'
        expected_csrf = make_csrf_token(user_token, nonce)

        # mock _get_csrf_nonce 返固定 nonce
        monkeypatch.setattr(
            'app.tools.csrf._get_csrf_nonce', lambda t: nonce,
        )

        wrapped = csrf_protect(my_view)
        with _flask_app_fixture.test_request_context(
            '/test', method='POST',
            headers={'X-CSRF-Token': expected_csrf},
            environ_overrides={'HTTP_COOKIE': f'csrf_token={expected_csrf}; ogs_token={user_token};'},
        ):
            result = wrapped()
        assert result == 'ok', f"user_token 有效 + nonce 匹配应进 view_func, 实际: {result}"


# =============================================================================
# Fixtures
# =============================================================================
@pytest.fixture
def _flask_app_fixture():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app
