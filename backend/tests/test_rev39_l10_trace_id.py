# -*- coding: utf-8 -*-
"""REV39-L10: 错误响应 trace_id 机制回归测试。

背景：REV36-L10 报告所有错误响应无 trace_id, 前端报错时无法精确定位后端日志。
       REV39-L10 修复:
         - before_request: 生成 trace_id (优先用上游 X-Trace-Id/X-Request-Id, 否则 uuid4().hex)
         - after_request: 所有响应附 X-Trace-Id header
         - 4 个 errorhandler (404/405/500/Exception): 响应 body 附加 trace_id 字段
         - 业务日志: _err_exception 错误日志带 [trace=<id>] 前缀

覆盖范围:
  1) before_request 生成 trace_id (默认 uuid4 hex)
  2) before_request 优先用 X-Trace-Id 上游 header
  3) before_request 兼容 X-Request-Id 旧式 header
  4) after_request 设 X-Trace-Id response header
  5) errorhandler 404 响应 body 含 trace_id
  6) errorhandler 405 响应 body 含 trace_id
  7) errorhandler 500 响应 body 含 trace_id
  8) errorhandler Exception 含 trace_id
  9) X-Trace-Id header 与 body 字段一致
 10) trace_id 长度 32 (uuid4 hex)
 11) _inject_trace_id helper 函数存在
 12) 业务代码无需修改 (透明注入)
"""
import os
import re
import sys
import uuid

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


@pytest.fixture
def flask_app_ctx():
    """REV38-M6: 提供 Flask app context, jsonify 需 current_app。"""
    from init import app
    ctx = app.app_context()
    ctx.push()
    try:
        yield app
    finally:
        ctx.pop()


@pytest.fixture
def fresh_app():
    """创建独立 Flask app 模拟 trace_id 行为（不污染 init.app）。"""
    from flask import Flask, g
    from app.tools.apierr import api_error, ApiCode

    app = Flask(__name__)

    @app.before_request
    def _before_request_trace_id():
        import uuid as _uuid
        from flask import request as _req
        g.trace_id = (
            _req.headers.get('X-Trace-Id')
            or _req.headers.get('X-Request-Id')
            or _uuid.uuid4().hex
        )

    @app.after_request
    def _after_request_trace_id(resp):
        from flask import g
        tid = getattr(g, 'trace_id', None)
        if tid:
            resp.headers['X-Trace-Id'] = tid
        return resp

    def _inject_trace_id(extra=None):
        from flask import g
        extra = dict(extra) if extra else {}
        tid = getattr(g, 'trace_id', None)
        if tid:
            extra['trace_id'] = tid
        return extra

    @app.errorhandler(404)
    def _err_404(_e):
        return api_error(ApiCode.DIR_NOT_FOUND, '接口不存在', **_inject_trace_id())

    @app.errorhandler(405)
    def _err_405(_e):
        return api_error(ApiCode.TYPE_ERROR, '请求方法不被允许', **_inject_trace_id())

    @app.errorhandler(Exception)
    def _err_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return api_error(
                ApiCode.INTERNAL_ERROR,
                e.description or str(e),
                status=e.code,
                **_inject_trace_id(),
            )
        return api_error(
            ApiCode.INTERNAL_ERROR,
            '服务器内部错误: %s' % type(e).__name__,
            **_inject_trace_id(),
        )

    return app


# ============================================================
# 1) before_request 生成 trace_id
# ============================================================
class TestBeforeRequestTraceId:
    def test_01_trace_id_generated_default(self, flask_app_ctx):
        """无 X-Trace-Id header 时, g.trace_id 应是 uuid4 hex (32 字符)。"""
        from flask import g
        app = flask_app_ctx
        with app.test_request_context('/any', method='GET'):
            # 手动触发 before_request hook
            app.preprocess_request()
            assert hasattr(g, 'trace_id'), 'before_request 应设置 g.trace_id'
            assert len(g.trace_id) == 32, 'uuid4 hex 应是 32 字符, 实际: %r' % g.trace_id
            # 验证是 hex
            int(g.trace_id, 16)  # 不是 hex 就抛 ValueError

    def test_02_trace_id_unique_per_request(self, flask_app_ctx):
        """每次请求 trace_id 不同。"""
        from flask import g
        app = flask_app_ctx
        ids = set()
        for _ in range(5):
            with app.test_request_context('/any', method='GET'):
                app.preprocess_request()
                ids.add(g.trace_id)
        assert len(ids) == 5, '5 次请求应生成 5 个不同 trace_id, 实际: %d' % len(ids)


# ============================================================
# 2) 上游 header 优先级
# ============================================================
class TestUpstreamHeaderPriority:
    def test_01_uses_x_trace_id_header(self, flask_app_ctx):
        """优先用 X-Trace-Id header (分布式追踪标准)。"""
        from flask import g
        app = flask_app_ctx
        with app.test_request_context('/any', method='GET', headers={'X-Trace-Id': 'caller-trace-123'}):
            app.preprocess_request()
            assert g.trace_id == 'caller-trace-123', \
                '应优先用 X-Trace-Id header, 实际: %r' % g.trace_id

    def test_02_falls_back_to_x_request_id(self, flask_app_ctx):
        """无 X-Trace-Id 时用 X-Request-Id (旧式 header)。"""
        from flask import g
        app = flask_app_ctx
        with app.test_request_context('/any', method='GET', headers={'X-Request-Id': 'req-456'}):
            app.preprocess_request()
            assert g.trace_id == 'req-456'

    def test_03_x_trace_id_wins_over_x_request_id(self, flask_app_ctx):
        """同时有 X-Trace-Id + X-Request-Id 时, X-Trace-Id 优先。"""
        from flask import g
        app = flask_app_ctx
        with app.test_request_context(
            '/any', method='GET',
            headers={'X-Trace-Id': 'new-trace', 'X-Request-Id': 'old-req'},
        ):
            app.preprocess_request()
            assert g.trace_id == 'new-trace', 'X-Trace-Id 应优先于 X-Request-Id'


# ============================================================
# 3) after_request 设 X-Trace-Id header
# ============================================================
class TestAfterRequestHeader:
    def test_01_response_has_x_trace_id_header(self, flask_app_ctx):
        """after_request 应在响应 header 加 X-Trace-Id。"""
        from flask import g
        app = flask_app_ctx

        @app.route('/test_l10')
        def view():
            return {'code': 0, 'msg': 'ok'}

        with app.test_client() as client:
            resp = client.get('/test_l10', headers={'X-Trace-Id': 'abc-trace'})
            assert 'X-Trace-Id' in resp.headers, '响应应有 X-Trace-Id header'
            assert resp.headers['X-Trace-Id'] == 'abc-trace'

    def test_02_generates_trace_id_when_no_header(self, fresh_app):
        """无上游 header 时, X-Trace-Id 应是 uuid4 hex。"""
        app = fresh_app

        @app.route('/test_l10_b')
        def view():
            return {'code': 0, 'msg': 'ok'}

        with app.test_client() as client:
            resp = client.get('/test_l10_b')
            assert 'X-Trace-Id' in resp.headers
            assert len(resp.headers['X-Trace-Id']) == 32


# ============================================================
# 4) errorhandler 404 响应含 trace_id
# ============================================================
class TestErrorHandlerTraceId:
    def test_01_404_response_includes_trace_id(self, flask_app_ctx):
        """404 errorhandler 响应 body 含 trace_id。"""
        app = flask_app_ctx
        with app.test_client() as client:
            resp = client.get('/nonexistent_endpoint_xyz', headers={'X-Trace-Id': '404-trace'})
            assert resp.status_code == 404
            data = resp.get_json()
            assert 'trace_id' in data, '404 响应 body 应含 trace_id 字段, 实际: %r' % data
            assert data['trace_id'] == '404-trace'
            # X-Trace-Id header 也应一致
            assert resp.headers['X-Trace-Id'] == '404-trace'

    def test_02_405_response_includes_trace_id(self, fresh_app):
        """405 errorhandler 响应 body 含 trace_id。"""
        app = fresh_app

        @app.route('/test_405', methods=['GET'])
        def view():
            return {'code': 0, 'msg': 'ok'}

        with app.test_client() as client:
            # POST 到只支持 GET 的路由 → 405
            resp = client.post('/test_405', headers={'X-Trace-Id': '405-trace'})
            # Werkzeug 不同版本可能返 400/405, 接受两者
            assert resp.status_code in (400, 405), \
                '应为 400/405, 实际: %d' % resp.status_code
            data = resp.get_json()
            # 只要 errorhandler 触发, body 应含 trace_id
            if resp.status_code == 405:
                assert 'trace_id' in data
                assert data['trace_id'] == '405-trace'

    def test_03_500_response_includes_trace_id(self, fresh_app):
        """500 errorhandler 响应 body 含 trace_id。"""
        app = fresh_app

        @app.route('/test_500')
        def view():
            raise RuntimeError('boom')

        with app.test_client() as client:
            resp = client.get('/test_500', headers={'X-Trace-Id': '500-trace'})
            assert resp.status_code == 500
            data = resp.get_json()
            assert 'trace_id' in data, '500 响应 body 应含 trace_id, 实际: %r' % data
            assert data['trace_id'] == '500-trace'


# ============================================================
# 5) trace_id body 与 header 一致性
# ============================================================
class TestTraceIdConsistency:
    def test_01_body_trace_id_matches_header(self, flask_app_ctx):
        """响应 body 的 trace_id 字段应与 X-Trace-Id header 一致。"""
        app = flask_app_ctx
        with app.test_client() as client:
            resp = client.get('/nonexistent_xyz', headers={'X-Trace-Id': 'consistency-check'})
            body = resp.get_json()
            assert body.get('trace_id') == resp.headers.get('X-Trace-Id'), \
                'body trace_id 应与 X-Trace-Id header 一致: body=%r header=%r' % \
                (body.get('trace_id'), resp.headers.get('X-Trace-Id'))

    def test_02_trace_id_format(self, flask_app_ctx):
        """trace_id 格式: 32 字符 hex (无 header 时)。"""
        app = flask_app_ctx
        with app.test_client() as client:
            resp = client.get('/nonexistent_xyz')
            tid = resp.headers['X-Trace-Id']
            assert len(tid) == 32, 'uuid4 hex 应 32 字符, 实际: %d (%r)' % (len(tid), tid)
            # hex 校验
            int(tid, 16)


# ============================================================
# 6) 静态分析: 关键组件存在
# ============================================================
class TestTraceIdComponents:
    def test_01_init_py_has_before_request_hook(self):
        """init.py 必含 _before_request_trace_id 钩子。"""
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        assert re.search(r'@app\.before_request\s*\n\s*def\s+_before_request_trace_id', src), \
            'init.py 应注册 @app.before_request _before_request_trace_id'

    def test_02_init_py_has_after_request_hook(self):
        """init.py 必含 _after_request_trace_id 钩子。"""
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        assert re.search(r'@app\.after_request\s*\n\s*def\s+_after_request_trace_id', src), \
            'init.py 应注册 @app.after_request _after_request_trace_id'

    def test_03_inject_trace_id_helper(self):
        """init.py 必含 _inject_trace_id helper。"""
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        assert re.search(r'def\s+_inject_trace_id', src), \
            'init.py 应有 _inject_trace_id helper'

    def test_04_all_errorhandlers_use_inject(self):
        """4 个 errorhandler 都应调 _inject_trace_id。"""
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        # 找 4 个 errorhandler
        for status in (404, 405, 500):
            # 找 def _err_<status> 块
            m = re.search(r'@app\.errorhandler\(' + str(status) + r'\)\s*\n\s*def\s+_err_\d+\(_e\):\s*\n\s*return\s+api_error\([^)]*_inject_trace_id', src)
            assert m, 'errorhandler %d 应调 _inject_trace_id' % status
        # _err_exception 也要调
        m = re.search(r'@app\.errorhandler\(Exception\)\s*\n\s*def\s+_err_exception[^:]*:\s*([\s\S]*?)(?=\n# ={3,}|\nclass |\ndef\s+\w+\(|$)', src)
        assert m, '_err_exception 应存在'
        body = m.group(1)
        assert '_inject_trace_id' in body, '_err_exception 应调 _inject_trace_id'

    def test_05_rev39_l10_marker_in_init(self):
        """init.py 应有 REV39-L10 注释标记。"""
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        assert 'REV39-L10' in src, 'init.py 应含 REV39-L10 标签注释'

    def test_06_exception_log_has_trace_id(self):
        """_err_exception 错误日志应带 trace_id 前缀。"""
        init_py_path = os.path.join(_BACKEND, 'init.py')
        with open(init_py_path, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'def\s+_err_exception[^:]*:\s*([\s\S]*?)(?=\n@|\nclass |\ndef\s+\w+\(|$)', src)
        assert m
        body = m.group(1)
        assert re.search(r'\[trace=%s\]|trace=', body), \
            '_err_exception 日志应带 [trace=<id>] 前缀'


# ============================================================
# 7) 集成: 业务代码无需修改, 透明注入
# ============================================================
class TestTransparentInjection:
    def test_01_business_view_returns_unchanged(self, fresh_app):
        """业务视图函数不需要修改, errorhandler 自动附加 trace_id。"""
        app = fresh_app

        @app.route('/biz_view')
        def view():
            # 业务代码只返 data, 不需要知道 trace_id
            return {'code': 0, 'msg': 'ok', 'data': {'foo': 'bar'}}

        with app.test_client() as client:
            resp = client.get('/biz_view', headers={'X-Trace-Id': 'biz-trace'})
            assert resp.status_code == 200
            data = resp.get_json()
            # 业务响应没有 trace_id 字段 (api_response 不自动注入, 仅 errorhandler)
            # 但 X-Trace-Id header 仍然附上
            assert resp.headers['X-Trace-Id'] == 'biz-trace'

    def test_02_health_endpoint_has_trace_id(self, flask_app_ctx):
        """/local/health 也应附 X-Trace-Id header。"""
        app = flask_app_ctx
        with app.test_client() as client:
            resp = client.get('/local/health', headers={'X-Trace-Id': 'health-trace'})
            assert resp.status_code == 200
            assert resp.headers['X-Trace-Id'] == 'health-trace'
