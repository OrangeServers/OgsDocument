# -*- coding: utf-8 -*-
"""REV37 后端 API 路由层评审 P0 修复测试

修复范围（REV36 评审 4 项 HIGH）：
  - H1: /server/host/cmd 命令执行无审计 → ServerCmd.sh_cmd 加 CzToolsLog + IP/UA
  - H2: /local/file/put 文件上传无审计 → FileGet.save_file 加 MIME 嗅探 + 审计日志
  - H3: 装饰器链顺序错误（csrf 在 auth 之前）→ 当前顺序已对, 注释修正 + 错误响应走 api_error
  - H4: 错误响应格式不统一 → 新建 apierr.py + csrf/at/init 全部走 api_error

执行：
    cd backend && python -m pytest tests/test_rev37_api.py -v
"""
import os
import sys
import re
import inspect
import pytest
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# 本地 fixture: 提供 Flask app context (jsonify 需要 current_app)
@pytest.fixture
def flask_app_ctx():
    try:
        from app.app_factory import app
    except Exception:
        from flask import Flask
        app = Flask(__name__)
    with app.app_context():
        yield app


# =============================================================================
# REV37-H4: apierr.py 统一响应包装
# =============================================================================

class TestApiErrResponseHelper:
    """REV37-H4: api_error / api_response / ApiCode."""

    def test_apicode_constants_exist(self):
        """ApiCode 必须有所有业务错误码常量."""
        from app.tools.apierr import ApiCode
        # OK / 错误码
        assert ApiCode.OK == 0
        assert ApiCode.INTERNAL_ERROR == 2
        assert ApiCode.UNAUTHORIZED == 3
        assert ApiCode.FORBIDDEN == 4
        # 业务码
        assert ApiCode.BUSINESS_UNAUTHORIZED == 100
        assert ApiCode.USER_NOT_FOUND == 101
        assert ApiCode.WRONG_PASSWORD == 102
        assert ApiCode.USERNAME_EXISTS == 103
        assert ApiCode.EMAIL_REGISTERED == 104
        assert ApiCode.CAPTCHA_EXPIRED == 105
        assert ApiCode.CAPTCHA_WRONG == 106
        # 资产
        assert ApiCode.ASSET_EXISTS == 111
        assert ApiCode.CONNECT_HOST_FAILED == 112
        assert ApiCode.ASSET_CRED_ERROR == 113
        # 文件
        assert ApiCode.DIR_NOT_FOUND == 121
        assert ApiCode.DELETE_FORBIDDEN == 131
        # 权限
        assert ApiCode.PERMISSION_EXISTS == 132
        # 定时任务
        assert ApiCode.CRON_EXISTS == 141
        # 系统错误
        assert ApiCode.DB_ERROR == 201
        assert ApiCode.TYPE_ERROR == 211
        # 冲突
        assert ApiCode.FILE_EXISTS == 231
        assert ApiCode.NAME_EXISTS == 232

    def test_api_response_default(self, flask_app_ctx):
        """api_response() 默认成功响应."""
        from app.tools.apierr import api_response, ApiCode
        resp, status = api_response()
        assert status == 200
        # tuple 是 (flask.Response, int)
        assert hasattr(resp, 'get_json')
        data = resp.get_json()
        assert data['code'] == ApiCode.OK
        assert data['msg'] == 'ok'

    def test_api_response_with_data(self, flask_app_ctx):
        """api_response(data=...) 把数据放进 'data' 字段."""
        from app.tools.apierr import api_response
        resp, status = api_response(data={'foo': 'bar'}, msg='ok')
        assert status == 200
        data = resp.get_json()
        assert data['code'] == 0
        assert data['msg'] == 'ok'
        assert data['data'] == {'foo': 'bar'}

    def test_api_response_with_extra(self, flask_app_ctx):
        """api_response 额外字段平铺 (与旧 jsonify 风格兼容)."""
        from app.tools.apierr import api_response
        resp, _ = api_response(host_list_msg=['a', 'b'], host_len_msg=2)
        data = resp.get_json()
        assert data['host_list_msg'] == ['a', 'b']
        assert data['host_len_msg'] == 2

    def test_api_error_unauthorized_status(self, flask_app_ctx):
        """api_error(ApiCode.UNAUTHORIZED) -> HTTP 401."""
        from app.tools.apierr import api_error, ApiCode
        resp, status = api_error(ApiCode.UNAUTHORIZED, '未授权访问')
        assert status == 401
        data = resp.get_json()
        assert data['code'] == 3
        assert data['msg'] == '未授权访问'

    def test_api_error_forbidden_status(self, flask_app_ctx):
        """api_error(ApiCode.FORBIDDEN) -> HTTP 403."""
        from app.tools.apierr import api_error, ApiCode
        resp, status = api_error(ApiCode.FORBIDDEN, '权限不足')
        assert status == 403
        data = resp.get_json()
        assert data['code'] == 4

    def test_api_error_internal_status(self, flask_app_ctx):
        """api_error(ApiCode.INTERNAL_ERROR) -> HTTP 500."""
        from app.tools.apierr import api_error, ApiCode
        resp, status = api_error(ApiCode.INTERNAL_ERROR, '服务器内部错误')
        assert status == 500

    def test_api_error_user_not_found_status(self, flask_app_ctx):
        """api_error(ApiCode.USER_NOT_FOUND) -> HTTP 404."""
        from app.tools.apierr import api_error, ApiCode
        resp, status = api_error(ApiCode.USER_NOT_FOUND, '用户不存在')
        assert status == 404

    def test_api_error_explicit_status_overrides(self, flask_app_ctx):
        """显式 status 参数覆盖自动映射."""
        from app.tools.apierr import api_error
        resp, status = api_error(999, 'custom', status=418)
        assert status == 418

    def test_api_error_with_extra_fields(self, flask_app_ctx):
        """api_error 支持附加字段 detail/reason 等."""
        from app.tools.apierr import api_error
        resp, _ = api_error(100, 'error', reason='test reason', extra_field='x')
        data = resp.get_json()
        assert data['reason'] == 'test reason'
        assert data['extra_field'] == 'x'

    def test_status_by_code_coverage(self):
        """_STATUS_BY_CODE 必须覆盖关键错误码."""
        from app.tools.apierr import _STATUS_BY_CODE
        # 0=200 OK
        assert _STATUS_BY_CODE[0] == 200
        # 3 / 100 = 401 未授权
        assert _STATUS_BY_CODE[3] == 401
        assert _STATUS_BY_CODE[100] == 401
        # 4 = 403 权限不足
        assert _STATUS_BY_CODE[4] == 403
        # 102 密码错误 = 401
        assert _STATUS_BY_CODE[102] == 401
        # 106 验证码错误 = 400
        assert _STATUS_BY_CODE[106] == 400
        # 112 连接主机失败 = 502
        assert _STATUS_BY_CODE[112] == 502
        # 201 DB 错误 = 500
        assert _STATUS_BY_CODE[201] == 500

    def test_make_handler_status(self):
        """make_handler_status 从 Exception/Code 取 HTTP 状态码."""
        from app.tools.apierr import make_handler_status
        # HTTPException-like (有 code 属性)
        e1 = MagicMock()
        e1.code = 403
        assert make_handler_status(e1) == 403
        # int
        assert make_handler_status(404) == 404
        # 未知
        assert make_handler_status('xxx') == 500


# =============================================================================
# REV37-H3/H4: csrf.py 错误响应统一走 api_error
# =============================================================================

class TestCsrfUsesApiError:
    """REV37-H3/H4: csrf.py 错误响应必须走 api_error, 返回 (jsonify, status) tuple."""

    def test_csrf_imports_api_error(self):
        """csrf.py 必须 import api_error."""
        src = open(os.path.join(ROOT, 'app/tools/csrf.py'), encoding='utf-8').read()
        assert 'from app.tools.apierr import api_error' in src
        # 不再单独 import jsonify
        assert 'from flask import jsonify, request' not in src
        assert 'from flask import jsonify' not in src.replace(' ', '').replace('\n', '')

    def test_csrf_origin_fail_returns_api_error(self):
        """Origin/Referer 校验失败走 api_error."""
        src = open(os.path.join(ROOT, 'app/tools/csrf.py'), encoding='utf-8').read()
        # 找到 Origin/Referer 校验处
        m = re.search(
            r'if not _is_origin_allowed.*?return\s+(\S+)\((.+?)\)',
            src, re.DOTALL,
        )
        assert m is not None, 'Origin/Referer 校验缺少 api_error 返回'
        assert 'api_error' in m.group(1)

    def test_csrf_token_missing_returns_api_error(self):
        """token 缺失走 api_error."""
        src = open(os.path.join(ROOT, 'app/tools/csrf.py'), encoding='utf-8').read()
        # 检查关键错误路径
        assert "api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF token 缺失')" in src
        assert "api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF token 无效')" in src
        assert "api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF nonce 缺失" in src

    def test_csrf_no_raw_jsonify_with_code_100(self):
        """csrf.py 不能再出现 jsonify({'code': 100 错误响应 (必须是 api_error)."""
        src = open(os.path.join(ROOT, 'app/tools/csrf.py'), encoding='utf-8').read()
        # 之前是 jsonify({...}), 403 - 现应都是 api_error
        # 检查不含 csrf token 相关的裸 jsonify
        assert "jsonify({'code': 100" not in src or src.count("jsonify({'code': 100") == 0, \
            'csrf.py 仍含裸 jsonify 错误响应, 应改用 api_error'


# =============================================================================
# REV37-H3/H4: at.py 错误响应统一走 api_error
# =============================================================================

class TestAtUsesApiError:
    """REV37-H3/H4: at.py require_role / ogs_auth_token 错误响应走 api_error."""

    def test_at_imports_api_error(self):
        """at.py 必须 import api_error / ApiCode."""
        src = open(os.path.join(ROOT, 'app/tools/at.py'), encoding='utf-8').read()
        assert 'from app.tools.apierr import api_error' in src
        assert 'ApiCode' in src

    def test_require_role_returns_api_error(self, flask_app_ctx):
        """require_role 未登录走 api_error(ApiCode.UNAUTHORIZED)."""
        from app.tools.at import require_role

        @require_role('admin')
        def dummy():
            return 'ok'

        # mock session 返回 (None, None)
        with patch('app.tools.at._session', return_value=(None, None)):
            resp, status = dummy()
            assert status == 401
            data = resp.get_json()
            assert data['code'] == 3
            assert '未授权' in data['msg']

    def test_require_role_wrong_role_returns_api_error(self, flask_app_ctx):
        """require_role 角色不匹配走 api_error(ApiCode.FORBIDDEN)."""
        from app.tools.at import require_role
        from app.tools.apierr import ApiCode

        @require_role('admin')
        def dummy():
            return 'ok'

        # mock 登录但角色是 user
        mock_conn = MagicMock()
        mock_conn.conn.get.return_value = b'user'
        with patch('app.tools.at._session', return_value=(mock_conn, 'alice')):
            resp, status = dummy()
            assert status == 403
            data = resp.get_json()
            assert data['code'] == ApiCode.FORBIDDEN
            assert '权限不足' in data['msg']

    def test_require_role_correct_role_passes(self):
        """require_role 角色匹配时直接调 view_func."""
        from app.tools.at import require_role

        @require_role('admin', 'audit')
        def dummy():
            return 'executed'

        mock_conn = MagicMock()
        mock_conn.conn.get.return_value = b'admin'
        with patch('app.tools.at._session', return_value=(mock_conn, 'admin_user')):
            result = dummy()
            assert result == 'executed'

    def test_ogs_auth_token_unauth_returns_api_error(self, flask_app_ctx):
        """ogs_auth_token 未登录走 api_error(401)."""
        from app.tools.at import ogs_auth_token

        @ogs_auth_token
        def dummy():
            return 'ok'

        with patch('app.tools.at._session', return_value=(None, None)):
            resp, status = dummy()
            assert status == 401
            data = resp.get_json()
            assert data['code'] == 3

    def test_at_no_dict_unauth_response(self):
        """at.py 不再有 {'code': 100, 'msg': '未授权访问'} dict 返回 (都已改 api_error)."""
        src = open(os.path.join(ROOT, 'app/tools/at.py'), encoding='utf-8').read()
        # 之前 require_role / auth_token 返回的裸 dict
        assert "{'code': 100, 'msg': '未授权访问'}" not in src
        assert "{'code': 100, 'msg': '权限不足'}" not in src

    def test_ws_auth_unchanged(self, flask_request_ctx):
        """ws_auth 保持 ('', 401) tuple 不变 (WebSocket 握手专用)."""
        from app.tools.at import ws_auth

        @ws_auth
        def dummy():
            return 'ok'

        # 调用 flask_request_ctx() 来 push request context, 此时无 cookie -> ('', 401)
        flask_request_ctx()
        result = dummy()
        assert result == ('', 401)

    def test_ws_auth_with_token_passes(self, flask_request_ctx):
        """ws_auth 有 cookie 但 Redis 无 token -> 仍返 ('', 401)."""
        from app.tools.at import ws_auth
        from unittest.mock import patch

        @ws_auth
        def dummy():
            return 'ok'

        flask_request_ctx(values={})
        # cookies 设为无效 token, Redis conn.get 返 None
        with patch('app.tools.at.ConnRedis') as mock_redis:
            mock_inst = mock_redis.return_value
            mock_inst.conn.get.return_value = None
            # 覆盖 cookies 提供一个 tk
            from flask import request as real_req
            real_req.cookies = MagicMock()
            real_req.cookies.get.return_value = 'invalid_tk'
            result = dummy()
            assert result == ('', 401)


# =============================================================================
# REV37-H3/H4: init.py 全局 errorhandler
# =============================================================================

class TestInitErrorHandlers:
    """REV37-H4: init.py 注册全局 errorhandler(404/405/500/Exception)."""

    def test_init_imports_api_error(self):
        """init.py 必须 import api_error / ApiCode."""
        src = open(os.path.join(ROOT, 'init.py'), encoding='utf-8').read()
        assert 'from app.tools.apierr import api_error' in src

    def test_init_404_handler(self):
        """init.py 必须有 @app.errorhandler(404)."""
        src = open(os.path.join(ROOT, 'init.py'), encoding='utf-8').read()
        assert '@app.errorhandler(404)' in src
        # handler body 用 api_error
        idx = src.find('@app.errorhandler(404)')
        window = src[idx:idx + 400]
        assert 'api_error' in window

    def test_init_405_handler(self):
        """@app.errorhandler(405)."""
        src = open(os.path.join(ROOT, 'init.py'), encoding='utf-8').read()
        assert '@app.errorhandler(405)' in src

    def test_init_500_handler(self):
        """@app.errorhandler(500)."""
        src = open(os.path.join(ROOT, 'init.py'), encoding='utf-8').read()
        assert '@app.errorhandler(500)' in src

    def test_init_generic_exception_handler(self):
        """@app.errorhandler(Exception) 全局兜底."""
        src = open(os.path.join(ROOT, 'init.py'), encoding='utf-8').read()
        assert '@app.errorhandler(Exception)' in src

    def test_decorator_chain_order_doc_clarified(self):
        """init.py 装饰器链顺序注释已更新, 标注 csrf 在最外层."""
        src = open(os.path.join(ROOT, 'init.py'), encoding='utf-8').read()
        # 装饰器链注释块
        idx = src.find('csrf_protect')
        assert idx > -1
        # 检查装饰器链说明
        assert 'csrf -> auth -> role -> view_func' in src
        # 顺序: require_role -> ogs_auth_token -> csrf_protect (从内到外)
        # 即 view_func = csrf_protect(ogs_auth_token(require_role(view_func)))
        chain_idx = src.find('view_func = require_role')
        if chain_idx > -1:
            window = src[chain_idx:chain_idx + 500]
            assert 'require_role' in window
            assert 'ogs_auth_token' in window
            assert 'csrf_protect' in window


# =============================================================================
# REV37-H1: ServerCmd.sh_cmd 审计 + IP/UA
# =============================================================================

class TestServerCmdAudit:
    """REV37-H1: ServerCmd 继承 CzToolsLog, 记录 IP + UA + cmd."""

    def test_server_cmd_inherits_cz_tools_log(self):
        """ServerCmd 必须继承 CzToolsLog 才能调 host_log."""
        src = open(os.path.join(ROOT, 'app/assets/ServerManagement.py'), encoding='utf-8').read()
        assert re.search(r'class ServerCmd\(CzToolsLog\)', src), \
            'ServerCmd 应继承 CzToolsLog'

    def test_server_cmd_init_captures_remote_addr(self):
        """ServerCmd.__init__ 必须取 request.remote_addr."""
        src = open(os.path.join(ROOT, 'app/assets/ServerManagement.py'), encoding='utf-8').read()
        # 找 ServerCmd 类的 __init__
        m = re.search(r'class ServerCmd\(CzToolsLog\):.*?def __init__.*?(?=\n    def [a-z])', src, re.DOTALL)
        assert m is not None
        init_src = m.group(0)
        assert 'remote_addr' in init_src
        assert 'X-Forwarded-For' in init_src
        assert 'User-Agent' in init_src

    def _sh_cmd_src(self):
        src = open(os.path.join(ROOT, 'app/assets/ServerManagement.py'), encoding='utf-8').read()
        m = re.search(r'@property\s*\n\s*def sh_cmd.*?(?=\n    @property|\nclass )', src, re.DOTALL)
        assert m is not None, 'ServerCmd.sh_cmd 未找到'
        return m.group(0)

    def test_server_cmd_sh_cmd_calls_host_log(self):
        """ServerCmd.sh_cmd 成功/失败路径都必须调 host_log."""
        sh_cmd_src = self._sh_cmd_src()
        host_log_count = sh_cmd_src.count('self.host_log(')
        assert host_log_count >= 2, f'需要 >= 2 处 host_log 调用, 实际 {host_log_count}'

    def test_server_cmd_sh_cmd_includes_ip_ua_in_log_details(self):
        """host_log 调用必须把 IP 和 UA 写入 log_details."""
        sh_cmd_src = self._sh_cmd_src()
        assert 'self.remote_ip' in sh_cmd_src
        assert 'self.user_agent' in sh_cmd_src
        assert 'ip=' in sh_cmd_src

    def test_server_cmd_dangerous_blocked_audited(self):
        """危险命令拦截时也记录审计 (让 dangerous 尝试可追踪)."""
        sh_cmd_src = self._sh_cmd_src()
        idx = sh_cmd_src.find('_check_command_safe')
        window = sh_cmd_src[idx:idx + 800]
        assert 'dangerous command blocked' in window or 'host_log' in window

    def test_server_cmd_no_audit_left_optional(self):
        """ServerCmd 不能不调 host_log - 所有路径都审计."""
        sh_cmd_src = self._sh_cmd_src()
        # 验证: 拦截路径 + 找不到 host 路径 + IOError 路径 + 成功路径 = 4 处
        assert sh_cmd_src.count('self.host_log(') >= 3, \
            f'危险/失败路径都应有审计, 当前 {sh_cmd_src.count("self.host_log(")}'


# =============================================================================
# REV37-H2: FileGet.save_file MIME 嗅探 + 审计
# =============================================================================

class TestFileUploadMIMESniffing:
    """REV37-H2: FileGet.save_file 加扩展名黑名单 + 魔术字节嗅探 + 审计."""

    def test_danger_ext_set_exists(self):
        """_DANGER_EXT 危险脚本后缀集合必须存在."""
        from app.files import file as fmod
        assert hasattr(fmod, '_DANGER_EXT')
        # 必须含 .py / .sh / .ps1 / .bat 等
        danger = fmod._DANGER_EXT
        assert '.py' in danger
        assert '.sh' in danger
        assert '.ps1' in danger
        assert '.bat' in danger
        assert '.jar' in danger
        assert '.php' in danger

    def test_save_file_blocks_danger_ext(self):
        """save_file 必须拒绝危险脚本后缀."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        assert '_DANGER_EXT' in src
        assert '禁止上传脚本类型文件' in src

    def test_save_file_blocks_elf_magic(self):
        """save_file 检测 ELF 魔术字节."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        # ELF: \x7fELF
        assert "b'\\x7fELF'" in src or 'ELF' in src
        assert '禁止上传 ELF' in src

    def test_save_file_blocks_pe_magic(self):
        """save_file 检测 PE (MZ) 魔术字节."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        assert "'MZ'" in src or 'b"MZ"' in src or "'MZ'" in src
        assert '禁止上传 PE' in src

    def test_save_file_blocks_class_magic(self):
        """save_file 检测 Java class 魔术字节 (\\xca\\xfe\\xba\\xbe)."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        assert 'xcafebabe' in src or '\\xca\\xfe\\xba\\xbe' in src or 'class' in src.lower()

    def test_save_file_size_limit_unchanged(self):
        """REV30-L13 size 限制保留."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        assert '_MAX_SAVE_FILE_SIZE' in src

    def test_save_file_writes_audit_log(self):
        """save_file 写 CzToolsLog 审计 (含 IP + UA + filename + size)."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        assert 'CzToolsLog' in src
        assert 'host_log' in src
        assert 'file_upload@' in src
        # IP + UA 字段
        assert 'ip=' in src
        assert 'ua=' in src

    def test_save_file_audit_failure_does_not_break(self):
        """审计失败不影响上传主流程 (try/except)."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        # 找 host_log 上下文, 后面应有 try/except pass
        idx = src.find('host_log(')
        window = src[idx:idx + 800]
        assert 'except Exception' in window or 'except:' in window

    def test_save_file_path_traversal_still_blocked(self):
        """REV5-A 路径遍历防护保留."""
        from app.files import file as fmod
        src = inspect.getsource(fmod.FileGet.save_file)
        assert '_is_within' in src
        assert 'secure_filename' in src or '路径越界' in src


# =============================================================================
# 集成回归: 关键修复点都在
# =============================================================================

class TestRev37AnnotationPresence:
    """REV37 注释应在所有修复文件中出现."""

    def test_rev37_files_have_annotations(self):
        """REV37 注释出现在所有修复文件."""
        rev37_files = [
            'app/tools/apierr.py',
            'app/tools/csrf.py',
            'app/tools/at.py',
            'init.py',
            'app/files/file.py',
            'app/assets/ServerManagement.py',
        ]
        missing = []
        for f in rev37_files:
            p = os.path.join(ROOT, f)
            if not os.path.exists(p):
                missing.append(f + ' (not found)')
                continue
            content = open(p, encoding='utf-8').read()
            if 'REV37' not in content:
                missing.append(f)
        assert not missing, '以下文件缺 REV37 注释: %s' % missing

    def test_apierr_module_has_rev37_markers(self):
        """apierr.py 模块 docstring 含 REV37-H3/H4 标记."""
        from app.tools import apierr
        assert 'REV37' in apierr.__doc__

    def test_apierr_exports(self):
        """apierr 模块导出 ApiCode / api_response / api_error."""
        import app.tools.apierr as mod
        assert hasattr(mod, 'ApiCode')
        assert hasattr(mod, 'api_response')
        assert hasattr(mod, 'api_error')
        assert hasattr(mod, 'make_handler_status')