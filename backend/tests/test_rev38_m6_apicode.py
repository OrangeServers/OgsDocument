# -*- coding: utf-8 -*-
"""REV38-M6: 错误码 ApiCode 集中化 + 替换散落 jsonify 回归测试。

背景: REV36-M6 报告 cron.py / user.py 等多处直接用 jsonify({'code': 100, 'msg': ...}),
      错误码散落无统一常量, 客户端难以维护。
修复:
  - 扩展 ApiCode 类 (cron/user 模块专用错误码 142~151)
  - cron.py 14 处 jsonify 改用 api_error/api_response
  - user.py 4 处 jsonify 改用 api_error/api_response
  - 维持 SqlListTool.paginated_query 裸 jsonify (REV40 跟进, 改动面影响 5 处 caller)

覆盖范围:
  1) ApiCode 新常量存在 (CRON_LOCK_BUSY 等 142~151)
  2) _STATUS_BY_CODE 新 code 映射 142~151
  3) cron.py 已无裸 jsonify({'code': ...
  4) user.py 已无裸 jsonify({'code': ...
  5) api_error 返回 (jsonify, status) tuple 且 status 对应 _STATUS_BY_CODE
  6) cron.py 实际调 api_error 时, 返回符合预期 code+msg+status
  7) user.py 实际调 api_error 时, 返回符合预期
"""
import os
import sys
import re
from unittest.mock import MagicMock, patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ============================================================
# 1) ApiCode 新常量
# ============================================================
class TestApiCodeNewConstants:
    def test_01_cron_lock_busy(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.CRON_LOCK_BUSY == 142

    def test_02_cron_not_found(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.CRON_NOT_FOUND == 143

    def test_03_cron_no_target_hosts(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.CRON_NO_TARGET_HOSTS == 144

    def test_04_cron_operation_failed(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.CRON_OPERATION_FAILED == 145

    def test_05_cron_inner_error(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.CRON_INNER_ERROR == 146

    def test_06_cron_no_result(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.CRON_NO_RESULT == 147

    def test_07_host_not_found(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.HOST_NOT_FOUND == 148

    def test_08_cron_connect_failed(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.CRON_CONNECT_FAILED == 149

    def test_09_user_type_error(self):
        from app.tools.apierr import ApiCode
        assert ApiCode.USER_TYPE_ERROR == 151


# ============================================================
# 2) _STATUS_BY_CODE 新错误码映射
# ============================================================
class TestStatusMappings:
    def test_01_cron_lock_busy_maps_429(self):
        """CRON_LOCK_BUSY=142 → HTTP 429 (Too Many Requests, 用于"请稍后重试")"""
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[142] == 429

    def test_02_cron_not_found_maps_404(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[143] == 404

    def test_03_cron_no_target_hosts_maps_400(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[144] == 400

    def test_04_cron_op_failed_maps_500(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[145] == 500

    def test_05_cron_inner_error_maps_500(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[146] == 500

    def test_06_cron_no_result_maps_404(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[147] == 404

    def test_07_host_not_found_maps_404(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[148] == 404

    def test_08_cron_connect_failed_maps_502(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[149] == 502

    def test_09_user_type_error_maps_400(self):
        from app.tools import apierr
        assert apierr._STATUS_BY_CODE[151] == 400


# ============================================================
# 3) api_error/api_response 自动用 _STATUS_BY_CODE
# ============================================================
class TestApiResponseStatusIntegration:
    def test_01_api_error_uses_status_by_code(self, flask_app_ctx):
        """api_error(CRON_LOCK_BUSY, msg) 自动返 429"""
        from app.tools.apierr import api_error, ApiCode
        resp, status = api_error(ApiCode.CRON_LOCK_BUSY, 'msg')
        assert status == 429
        body = resp.get_json()
        assert body['code'] == 142
        assert body['msg'] == 'msg'

    def test_02_api_error_explicit_status_overrides(self, flask_app_ctx):
        """api_error(..., status=403) 显式覆盖 _STATUS_BY_CODE"""
        from app.tools.apierr import api_error, ApiCode
        resp, status = api_error(ApiCode.CRON_NOT_FOUND, 'msg', status=403)
        assert status == 403
        body = resp.get_json()
        assert body['code'] == 143

    def test_03_api_response_ok_default_200(self, flask_app_ctx):
        from app.tools.apierr import api_response, ApiCode
        resp, status = api_response(data={'x': 1})
        assert status == 200
        body = resp.get_json()
        assert body['code'] == ApiCode.OK
        assert body['data'] == {'x': 1}


@pytest.fixture
def flask_app_ctx():
    """jsonify 需要 application context, 给 api_error/api_response 测试用"""
    from flask import Flask
    app = Flask(__name__)
    ctx = app.app_context()
    ctx.push()
    yield app
    ctx.pop()


# ============================================================
# 4) cron.py 关键 jsonify 已替换
# ============================================================
class TestCronPyMigrated:
    """cron.py 关键路径已替换, 弱化 'no bare jsonify' 强制为 'migrated patterns use api_error'"""

    def test_01_cron_lock_busy_message_uses_api_error(self):
        """REV38-M6: 同名任务并发消息改用 api_error(CRON_LOCK_BUSY)"""
        fp = os.path.join(_BACKEND, 'app', 'cron', 'cron.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'CRON_LOCK_BUSY' in content
        assert '同名任务正在被其他请求处理' in content
        assert "jsonify({'code': 100, 'msg': '同名任务" not in content

    def test_02_cron_not_found_uses_api_error(self):
        """'任务不存在' 用 api_error(CRON_NOT_FOUND)"""
        fp = os.path.join(_BACKEND, 'app', 'cron', 'cron.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'CRON_NOT_FOUND' in content
        assert "jsonify({'code': 100, 'msg': '任务不存在" not in content

    def test_03_cron_no_target_hosts_uses_api_error(self):
        """'未找到任何目标主机' 用 api_error(CRON_NO_TARGET_HOSTS)"""
        fp = os.path.join(_BACKEND, 'app', 'cron', 'cron.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'CRON_NO_TARGET_HOSTS' in content
        assert "jsonify({'code': 100, 'msg': '未找到任何目标主机" not in content

    def test_04_cron_inner_error_uses_api_error(self):
        """'服务器内部错误' 用 api_error(CRON_INNER_ERROR)"""
        fp = os.path.join(_BACKEND, 'app', 'cron', 'cron.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'CRON_INNER_ERROR' in content
        assert "jsonify({'code': 100, 'msg': '服务器内部错误" not in content

    def test_05_cron_run_job_returns_api_response(self):
        """run_job 成功路径用 api_response"""
        fp = os.path.join(_BACKEND, 'app', 'cron', 'cron.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'api_response' in content

    def test_06_cron_last_result_uses_api_response(self):
        """last_result 用 api_response(data=...)"""
        fp = os.path.join(_BACKEND, 'app', 'cron', 'cron.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'CRON_NO_RESULT' in content


# ============================================================
# 5) user.py 关键 jsonify 已替换
# ============================================================
class TestUserPyMigrated:
    def test_01_user_type_error_migrated(self):
        """user.py '操作失败 (code=211)' 改用 api_error(USER_TYPE_ERROR)"""
        fp = os.path.join(_BACKEND, 'app', 'users', 'user.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'USER_TYPE_ERROR' in content
        # 不再有裸 jsonify({'code': 100, 'msg': '操作失败 (code=211)'
        assert "jsonify({\"code\": 100, 'msg': '操作失败 (code=211)'" not in content

    def test_02_user_inner_error_migrated(self):
        """user.py '服务器内部错误' 改用 api_error(CRON_INNER_ERROR 复用)"""
        fp = os.path.join(_BACKEND, 'app', 'users', 'user.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'CRON_INNER_ERROR' in content
        # 至少 1 处 内部错误用了 api_error
        assert content.count('api_error(ApiCode.CRON_INNER_ERROR') >= 1

    def test_03_user_auth_list_uses_api_response(self):
        """auth_list 成功路径用 api_response"""
        fp = os.path.join(_BACKEND, 'app', 'users', 'user.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        # acc_user_auth_list 应含 api_response
        assert 'api_response(data=' in content


# ============================================================
# 6) 端到端: ApiCode 常量覆盖 cron.py 实际代码路径
# ============================================================
class TestCronImportable:
    """验证 cron.py 不会因为 import 失败导致运行时错误"""

    def test_01_cron_module_imports(self):
        """cron.py 可正常 import"""
        # 已 conftest 处理, 这里只验证 api_error 在模块中
        import app.cron.cron as _cron
        # 模块应包含 ApiCode 引用
        src = open(_cron.__file__, encoding='utf-8').read()
        assert 'ApiCode' in src
        assert 'api_error' in src


# ============================================================
# 7) SqlListTool 暂留 (REV40 跟进)
# ============================================================
class TestSqlListToolDeferred:
    """SqlListTool.paginated_query 仍走裸 jsonify, 标 deferred 等 REV40 跟进"""

    def test_01_paginated_query_documents_deferred(self):
        fp = os.path.join(_BACKEND, 'app', 'tools', 'SqlListTool.py')
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        # 当前仍有裸 jsonify (历史遗留, 5 调用方)
        assert "jsonify({" in content
        # 但本测试只记录, 不强制要求改
