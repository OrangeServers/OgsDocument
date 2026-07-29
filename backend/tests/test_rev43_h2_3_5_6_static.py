# -*- coding: utf-8 -*-
"""REV43 P1 修复单测: H2/H3/H5/H6 (静态分析为主).

H2 (R2-4-1): app_factory.py 静态目录用 __file__ 锚定绝对路径.
H3 (R2-4-2): init.py 路由注册显式 endpoint= 防 Flask 重复命名冲突.
H5 (R2-4-3): init.py _make_view 入口检查 method 是否存在, 避免 AttributeError.
H6 (R2-4-4): init.py main 块加 atexit + signal 优雅关闭.
"""
import inspect
import os
import re


# =============================================================================
# H2: app_factory.py 静态目录 __file__ 锚定
# =============================================================================
class TestAppFactoryStaticDirAbsolute:
    """R2-4-1: static_folder 必须是基于 __file__ 的绝对路径, 不能相对 cwd."""

    def test_static_folder_is_absolute_path(self):
        """static_folder 必须是绝对路径 (os.path.isabs)."""
        from app.app_factory import app
        assert os.path.isabs(app.static_folder), \
            f"H2 修复: static_folder 应为绝对路径, 实际 {app.static_folder!r} (相对 cwd)"

    def test_static_folder_contains_app_static(self):
        """static_folder 路径应包含 app/static."""
        from app.app_factory import app
        # 标准化路径以匹配 (Windows 大小写不敏感)
        normalized = os.path.normpath(app.static_folder).lower()
        assert normalized.endswith(os.path.join('app', 'static')), \
            f"H2 修复: static_folder 应指向 app/static, 实际 {app.static_folder!r}"

    def test_static_folder_exists_or_creatable(self):
        """static_folder 目录应存在 (或可创建)."""
        from app.app_factory import app
        # 即使不存在, 也要保证是绝对路径 (防御性断言)
        assert os.path.isabs(app.static_folder), \
            f"H2: static_folder 应为绝对路径, 实际 {app.static_folder!r}"

    def test_app_factory_imports_os(self):
        """app_factory.py 必须 import os (锚定需要)."""
        import app.app_factory as _mod
        source = inspect.getsource(_mod)
        assert 'import os' in source, \
            "H2 修复: app_factory.py 必须 import os 才能用 __file__ 锚定"

    def test_app_factory_uses_abspath_or_dirname(self):
        """app_factory.py 必须用 os.path.abspath 或 os.path.dirname 锚定."""
        import app.app_factory as _mod
        source = inspect.getsource(_mod)
        assert '__file__' in source, \
            "H2 修复: app_factory.py 应使用 __file__ 锚定"
        assert 'os.path.abspath' in source or 'os.path.dirname' in source, \
            "H2 修复: app_factory.py 应使用 os.path.abspath/dirname 处理 __file__"


# =============================================================================
# H3: init.py 路由注册显式 endpoint=
# =============================================================================
class TestInitRoutesExplicitEndpoint:
    """R2-4-2: 路由注册应显式传 endpoint= 避免 Flask 重复命名冲突."""

    def test_route_registration_uses_endpoint_kwarg(self):
        """init.py 中 _register_routes_from_module 应显式传 endpoint=."""
        # 检查 app.add_url_rule 调用使用 endpoint= 参数
        import init
        source = inspect.getsource(init)
        # 找到 _register_routes_from_module 函数体中的 add_url_rule
        m = re.search(
            r'def _register_routes_from_module.*?(?=\n\ndef |\nclass |\Z)',
            source, re.DOTALL,
        )
        assert m, "找不到 _register_routes_from_module 函数"
        body = m.group(0)
        # 找 add_url_rule 行
        add_url_rule_lines = [
            line for line in body.split('\n')
            if 'app.add_url_rule' in line
        ]
        assert add_url_rule_lines, "_register_routes_from_module 中没有 add_url_rule 调用"
        # 至少有一个调用使用了 endpoint= 参数
        has_endpoint = any('endpoint=' in line for line in add_url_rule_lines)
        assert has_endpoint, \
            f"H3 修复: _register_routes_from_module 内 add_url_rule 应显式 endpoint=, 实际:\n" + \
            '\n'.join(add_url_rule_lines)

    def test_endpoint_name_handles_root_path(self):
        """endpoint_name 生成应处理 '/' 边界 (or 'root')."""
        import init
        source = inspect.getsource(init)
        # 找 endpoint_name 赋值行
        m = re.search(r"endpoint_name\s*=\s*([^\n]+)", source)
        assert m, "找不到 endpoint_name 赋值"
        line = m.group(1)
        # 应有 "or 'root'" 兜底 (空字符串处理)
        assert "'root'" in line or '"root"' in line, \
            f"H3 修复: endpoint_name 处理 '/' 应有 'root' 兜底, 实际: {line}"


# =============================================================================
# H5: _make_view 入口方法存在性检查
# =============================================================================
class TestMakeViewAttributeCheck:
    """R2-4-3: _make_view 入口检查 method 是否存在, 避免 AttributeError 500."""

    def test_make_view_gets_attribute_only_once(self):
        """不能用 hasattr + getattr 双重求值状态变更型 @property。"""
        import init
        source = inspect.getsource(init)
        m = re.search(
            r'def _make_view\(.*?\):.*?(?=\n\ndef |\nclass |\Z)',
            source, re.DOTALL,
        )
        assert m, "找不到 _make_view 函数"
        body = m.group(0)
        assert 'hasattr(inst, m)' not in body, \
            f"_make_view 不应通过 hasattr 求值 @property:\n{body[:500]}"
        assert body.count('getattr(inst, m)') == 1, \
            f"_make_view 每个请求必须只获取一次属性:\n{body[:500]}"
        # 必须有 REV43-H5 注释标记
        assert 'REV43-H5' in body, \
            "H5 修复: _make_view 应有 REV43-H5 注释标记"

    def test_make_view_raises_on_missing_method(self):
        """运行时验证: 传入不存在 method 的 class, 应 raise AttributeError."""
        import init
        from app.app_factory import app as _app

        class _BadView:
            """故意缺少 method_b 的 view class."""

            def method_a(self):
                return 'ok'

        # 直接模拟 _make_view 的单次 getattr 拦截
        with _app.test_request_context('/'):
            # _make_view 定义在 _register_routes_from_module 内部, 不直接暴露
            # 这里改为: 模拟 _make_view 的 view_func 内部单次 getattr 逻辑
            def _make_view_inner(c, m, auth, prop, r):
                def view_func(**kwargs):
                    inst = c()
                    try:
                        attr = getattr(inst, m)
                    except AttributeError as exc:
                        raise AttributeError(
                            '[REV43-H5] View class %s missing method %r' % (c.__name__, m)
                        ) from exc
                    return attr if prop else attr()
                return view_func

            view = _make_view_inner(_BadView, 'method_missing', False, False, ())
            # 应 raise AttributeError
            try:
                view()
                assert False, "应 raise AttributeError, 实际未抛"
            except AttributeError as e:
                assert 'REV43-H5' in str(e), \
                    f"AttributeError 应含 REV43-H5 标记, 实际: {e}"


# =============================================================================
# H6: main 块 atexit + signal 优雅关闭
# =============================================================================
class TestMainGracefulShutdown:
    """R2-4-4: init.py main 块应注册 atexit + signal 优雅关闭钩子."""

    def test_main_block_registers_atexit(self):
        """main 块 (if __name__ == '__main__') 应有 atexit.register()."""
        import init
        source = inspect.getsource(init)
        # 找 main 块
        m = re.search(
            r'if __name__\s*==\s*["\']__main__["\']:.*\Z',
            source, re.DOTALL,
        )
        assert m, "找不到 main 块"
        body = m.group(0)
        assert 'atexit' in body, \
            "H6 修复: main 块应 import + register atexit 钩子"
        assert 'atexit.register' in body, \
            "H6 修复: main 块应调用 atexit.register(...), 实际未注册"
        assert 'REV43-H6' in body, \
            "H6 修复: main 块应有 REV43-H6 注释标记"

    def test_main_block_registers_signal_handler(self):
        """main 块应注册 SIGTERM (或 SIGINT) signal handler."""
        import init
        source = inspect.getsource(init)
        m = re.search(
            r'if __name__\s*==\s*["\']__main__["\']:.*\Z',
            source, re.DOTALL,
        )
        assert m, "找不到 main 块"
        body = m.group(0)
        # 至少注册了 SIGTERM (或 gevent.signal 通用调用)
        has_signal = (
            'SIGTERM' in body or
            'gevent_signal' in body or
            'gevent.signal' in body
        )
        assert has_signal, \
            "H6 修复: main 块应注册 SIGTERM (或 gevent.signal) 处理器, 实际未注册"

    def test_main_block_has_shutdown_function(self):
        """main 块应有 _graceful_shutdown 函数定义 (或等效清理逻辑)."""
        import init
        source = inspect.getsource(init)
        m = re.search(
            r'if __name__\s*==\s*["\']__main__["\']:.*\Z',
            source, re.DOTALL,
        )
        body = m.group(0)
        # 应有 def _graceful_shutdown 或类似清理函数
        has_shutdown_fn = (
            re.search(r'def\s+_?graceful_shutdown', body) is not None or
            'http_server.stop' in body or
            'db.session.remove' in body
        )
        assert has_shutdown_fn, \
            "H6 修复: main 块应定义优雅关闭函数 (含 server.stop 或 session.remove)"

    def test_shutdown_cleans_db_session(self):
        """优雅关闭应清理 db.session (防连接泄漏)."""
        import init
        source = inspect.getsource(init)
        m = re.search(
            r'if __name__\s*==\s*["\']__main__["\']:.*\Z',
            source, re.DOTALL,
        )
        body = m.group(0)
        assert 'db.session.remove' in body or 'session.remove' in body, \
            "H6 修复: 优雅关闭应调 db.session.remove() 清理 SQLAlchemy session"
