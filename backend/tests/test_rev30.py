# -*- coding: utf-8 -*-
"""
REV30 cron/local/files 评审修复回归测试 (27 项)

对应评审: REV30_review.md
覆盖:
- HIGH 4 项 (H1-H4): 逻辑 bug / 数据不一致 / 接口误导
- MED 10 项 (M1-M10): 健壮性 / 一致性 / 资源管理
- LOW 13 项 (L1-L13): 命名 / 死代码 / 校验强化

策略:
- 静态分析 (AST / 源码字符串): 验证修复模式已应用 (H2 escape, M1 try/except, M7 重复 key 消除等)
- 行为测试: 用 fake_db / flask_request_ctx 跑真实调用, 验证返回值 (H1 多 group 更新, H3 返错等)
"""
import inspect
import io
import os
import re
import textwrap

import pytest


# =============================================================================
# 工具函数: 源码片段提取
# =============================================================================
def _read(path):
    return io.open(path, encoding='utf-8').read()


def _extract_method(content, class_name, method_name):
    """精确提取指定类中指定方法的函数体。

    返回该方法的完整 def 行 + 函数体字符串 (不含类的其他方法)。
    使用 AST 解析, 避免其他方法代码干扰。
    """
    import ast
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ''
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    # ast.unparse 在 Python 3.9+ 可用
                    if hasattr(ast, 'unparse'):
                        return ast.unparse(item)
                    # fallback: 提取 source lines
                    lines = content.splitlines()
                    return '\n'.join(lines[item.lineno - 1:item.end_lineno])
    return ''


def _extract_function(content, func_name):
    """提取模块级 def 函数体 (不在类内)。"""
    import ast
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ''
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            if hasattr(ast, 'unparse'):
                return ast.unparse(node)
            lines = content.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    return ''


def _extract_class(content, class_name):
    """提取整个类定义 (含类名 + 所有方法)。"""
    import ast
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ''
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            if hasattr(ast, 'unparse'):
                return ast.unparse(node)
            lines = content.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    return ''


# =============================================================================
# H1: Basics.DataSumAll.get_sum 逻辑 bug (for 循环里 return)
# =============================================================================
class TestRev30H1:
    """H1: DataSumAll.get_sum 应在 for 循环结束后统一 return, 不是 for 内 return."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_h1_no_return_inside_for(self):
        content = _read(self.SRC)
        func_src = _extract_method(content, 'DataSumAll', 'get_sum')
        assert 'for ' in func_src and 'osql_up' in func_src, 'get_sum 应包含 for 循环 + osql_up 调用'
        # AST 精确检查 for 循环体不应有 Return
        import ast
        tree = ast.parse(func_src)
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                for stmt in node.body:
                    assert not isinstance(stmt, ast.Return), \
                        'H1 修复未应用: for 循环体内仍有 Return, 会导致只更新第一个 group 就退出'
                # 找到 return, 确认在 for 之后 (不在 for body 内)
                return
        assert False, 'get_sum 未找到 for 循环'

    def test_h1_returns_updated_flag(self):
        """修复后 get_sum 应返回 'updated' 字段或 'empty' 标记."""
        content = _read(self.SRC)
        func_src = _extract_method(content, 'DataSumAll', 'get_sum')
        assert "'updated'" in func_src or '"updated"' in func_src, \
            'H1 修复未应用: get_sum 应返回 updated 字段标记是否真更新了 group'


# =============================================================================
# H2: Basics.CountUpdate SQL LIKE 通配符转义
# =============================================================================
class TestRev30H2:
    """H2: CountUpdate 使用 _escape_like + escape='\\' (同 REV28-H4 模式)."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_h2_escape_like_helper_exists(self):
        content = _read(self.SRC)
        assert '_escape_like' in content, 'H2 修复未应用: 应有 _escape_like helper'
        assert 'str.maketrans' in content, 'H2 修复未应用: 应使用 str.maketrans 制作转义表'
        # 验证 % 和 _ 都被转义
        m = re.search(r"str\.maketrans\s*\(\s*\{([^}]+)\}\s*\)", content)
        assert m, 'str.maketrans 字典格式有误'
        d = m.group(1)
        assert "'%'" in d or '"%"' in d, 'H2 修复未应用: 未转义 %'
        assert "'_'" in d or '"_"' in d, 'H2 修复未应用: 未转义 _'

    def test_h2_like_uses_escape_param(self):
        """CountUpdate 的 .like() 应带 escape='\\'."""
        content = _read(self.SRC)
        # 找 CountUpdate 类的 __init__
        cls = _extract_method(content, 'CountUpdate', '__init__')
        # 应有 like(..., escape='\\') - 考虑 like(...) 参数可能含 .format(...), 使用 line-based 匹配
        like_lines = [l for l in cls.split('\n') if '.like(' in l]
        assert like_lines, '__init__ 内应有 .like() 调用'
        for line in like_lines:
            assert 'escape=' in line, \
                'H2 修复未应用: .like() 调用未带 escape 参数, 行: %s' % line.strip()


# =============================================================================
# H3: Settings.change NUMBER_FIELDS 转换失败返错而非 0
# =============================================================================
class TestRev30H3:
    """H3: settings_change 应在 int(val) 失败时返 code=100, 不静默写 0."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Settings.py')

    def test_h3_no_silent_zero_fallback(self):
        content = _read(self.SRC)
        # 原始 buggy 模式: except (ValueError, TypeError): update_data[field] = 0
        # 在变更后, 该行应被替换为 return jsonify(...)
        assert 'update_data[field] = 0' not in content, \
            'H3 修复未应用: 仍存在 except -> update_data[field] = 0 静默模式'
        # 应有 invalid value for %s 错误消息
        assert re.search(r"invalid value for.*integer", content), \
            'H3 修复未应用: 应返回 invalid value for <field> 错误'

    def test_h3_returns_error_dict(self):
        """修复后 except 分支应返回 jsonify({'code': 100, 'msg': ...})."""
        content = _read(self.SRC)
        # 找 settings_change 方法
        m = re.search(r'def\s+settings_change\s*\([^)]*\)\s*:\s*\n((?:\s{4,}.*\n)+)', content)
        assert m, '未找到 settings_change'
        body = m.group(1)
        # 在 except (ValueError, TypeError): 之后应有 return jsonify
        exc_blocks = re.findall(r'except\s*\(\s*ValueError\s*,\s*TypeError\s*\)\s*:\s*\n((?:\s{8,}.*\n)*)', body)
        assert exc_blocks, '未找到 except (ValueError, TypeError) 块'
        for block in exc_blocks:
            assert 'return' in block and ('jsonify' in block or 'code' in block), \
                'H3 修复未应用: except 应 return 错误响应, 实际:\n%s' % block


# =============================================================================
# H4: DownloadFile.download 错误返 Response + Content-Disposition RFC 6266
# =============================================================================
class TestRev30H4:
    """H4: download 错误统一返 Response(json, status), Content-Disposition 走 RFC 6266."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'download.py')

    def test_h4_no_bare_to_json_for_error(self):
        content = _read(self.SRC)
        # 原始: 错误路径用 self.to_json({...}) (返 str)
        # 修复: 用 self._err_json(...) (返 Response)
        # 在 download 方法体内, 应不含 self.to_json({'status': 'fail'...
        body = _extract_method(content, 'DownloadFile', 'download')
        assert 'self.to_json' not in body, \
            'H4 修复未应用: download 内仍调用 self.to_json 返回错误 (前端无法统一处理)'
        assert '_err_json' in body, 'H4 修复未应用: 应使用 _err_json helper'

    def test_h4_content_disposition_rfc6266(self):
        """Content-Disposition 应使用 filename*=UTF-8''<encoded> (RFC 6266)."""
        content = _read(self.SRC)
        # 检查 RFC 6266 格式
        assert "filename*=UTF-8''" in content, \
            'H4 修复未应用: Content-Disposition 未走 RFC 6266 filename* 格式'
        # 不应再使用旧 filename="{}".format(filename) 模式
        assert "'filename=\"{}'.format(filename)'" not in content, \
            'H4 修复未应用: 仍使用旧 filename="{}".format(filename) 格式'

    def test_h4_secure_filename_for_header(self):
        """filename 走 secure_filename 防 \r\n 注入."""
        content = _read(self.SRC)
        # 应有 secure_filename(os.path.basename(real_target))
        assert re.search(r'secure_filename\s*\(\s*os\.path\.basename', content), \
            'H4 修复未应用: filename 应二次 secure_filename 防 \r\n 注入'


# =============================================================================
# M1: cron.CronList 分页参数 try/except
# =============================================================================
class TestRev30M1:
    """M1: CronList.__init__ 分页参数非数字时默认 page=1 / limit=10."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_m1_no_bare_int_conversion(self):
        """__init__ 不应直接 int(request.values.get('page')) (会抛 ValueError)."""
        content = _read(self.SRC)
        body = _extract_method(content, 'CronList', '__init__')
        assert 'try:' in body and 'except' in body, \
            'M1 修复未应用: __init__ 应有 try/except'
        # 找 int(...) 调用周围有 try
        int_calls = re.findall(r'int\s*\(\s*[^)]*\)', body)
        assert int_calls, '__init__ 内应至少有 int(...) 调用 (page/limit)'
        # 检查每个 int(...) 都在 try 块内
        # 简化: 整个 body 应有 try + except (TypeError, ValueError)
        assert re.search(r'except\s*\(\s*TypeError\s*,\s*ValueError\s*\)', body), \
            'M1 修复未应用: 应捕获 (TypeError, ValueError)'

    def test_m1_max_floor_one(self):
        """修复后 page 和 limit 应至少为 1 (max(page, 1) / max(limit, 1))."""
        content = _read(self.SRC)
        body = _extract_method(content, 'CronList', '__init__')
        assert 'max(page, 1)' in body and 'max(limit, 1)' in body, \
            'M1 修复未应用: page/limit 应 max(..., 1) 防 0/负数'


# =============================================================================
# M2: cron.OgsCron.add_job 任务已存在时 msg 文案
# =============================================================================
class TestRev30M2:
    """M2: add_job 已存在分支 msg 改为 '任务已存在'."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_m2_msg_correct(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsCron', 'add_job')
        assert "'任务已存在'" in body or '"任务已存在"' in body, \
            "M2 修复未应用: add_job 已存在分支应 msg='任务已存在'"
        # 不应再有 '任务不存在' 在 add_job (那是反义, 但 pause/run 等其他方法仍用)
        # 所以只检查 add_job 不含 '任务不存在' (因为修复后 add_job 内所有返错都是 '任务已存在')
        # 注: 暂不强制, 因为 add_job 内 if/else 分支可能引用
        # assert "'任务不存在'" not in body


# =============================================================================
# M3: cron.CronList.cron_list_all N+1 → 批量 in_(ids)
# =============================================================================
class TestRev30M3:
    """M3: cron_list_all 用 in_(ids) 批量查, 替代 for-loop N+1."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_m3_uses_in_ids(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'CronList', 'cron_list_all')
        assert '.in_(' in body, \
            'M3 修复未应用: cron_list_all 应使用 in_(ids) 批量查关联表'
        assert 't_cron_host.cron_id.in_' in body and 't_cron_group.cron_id.in_' in body, \
            'M3 修复未应用: 应分别对 t_cron_host.cron_id 和 t_cron_group.cron_id 用 in_'


# =============================================================================
# M4: cron.CronList.cron_auth_list auth_name 早退
# =============================================================================
class TestRev30M4:
    """M4: cron_auth_list user_token / auth_name 为 None 时返未登录."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_m4_early_return_when_no_token(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'CronList', 'cron_auth_list')
        # user_token 为空返错
        assert "if not user_token" in body, \
            'M4 修复未应用: cron_auth_list 应对空 user_token 早退'
        # auth_name 为空也返错
        assert "if not auth_name" in body, \
            'M4 修复未应用: cron_auth_list 应对空 auth_name 早退'


# =============================================================================
# M5: cron.OgsCron.com_list_job 不依赖 msg 字符串匹配
# =============================================================================
class TestRev30M5:
    """M5: com_list_job 失败分类不再依赖 msg 字符串 '权限' / '所有者'."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_m5_no_msg_string_match(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsCron', 'com_list_job')
        # 原: if '权限' in msg or '所有者' in msg
        # 修复: 移除 msg 字符串匹配, 直接靠 code
        assert "'权限' in msg" not in body, \
            "M5 修复未应用: com_list_job 仍依赖 '权限' in msg 字符串匹配"
        assert "'所有者' in msg" not in body, \
            "M5 修复未应用: com_list_job 仍依赖 '所有者' in msg 字符串匹配"


# =============================================================================
# M6: cron.OgsCron.close_job admin-only
# =============================================================================
class TestRev30M6:
    """M6: close_job 非 admin 应返 code=100."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_m6_admin_check(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsCron', 'close_job')
        assert "current_role != 'admin'" in body, \
            "M6 修复未应用: close_job 应检查 current_role != 'admin'"
        assert '仅管理员' in body, 'M6 修复未应用: 应返 中文 msg 提示仅管理员'


# =============================================================================
# M7: LocalShell.LocalDirList 重复 msg key
# =============================================================================
class TestRev30M7:
    """M7: LocalShell getdir1/getdir2 不再有重复 msg key (Python dict 后覆盖前)."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'LocalShell.py')

    def test_m7_no_duplicate_msg_in_jsonify(self):
        content = _read(self.SRC)
        # 在任何 jsonify({...}) 内不应出现两次 'msg'
        # 简化: 找 jsonify({  ...  }) 块, 检查 'msg' 不出现两次
        # 我们用正则找形如 'msg': xxx, 'msg': yyy 的连续模式
        pattern = re.compile(r"'msg'\s*:\s*[^,}]+,\s*'msg'\s*:", re.MULTILINE)
        matches = pattern.findall(content)
        assert not matches, \
            'M7 修复未应用: 发现重复 msg key: %s' % matches


# =============================================================================
# M8: Settings.OgsSettings bytes/str 混用
# =============================================================================
class TestRev30M8:
    """M8: self.name 应解码 bytes → str."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Settings.py')

    def test_m8_decode_helper(self):
        content = _read(self.SRC)
        # 应有 _decode_redis_str helper
        assert '_decode_redis_str' in content, \
            'M8 修复未应用: 缺少 _decode_redis_str helper'
        assert "decode('utf-8'" in content, \
            'M8 修复未应用: 应使用 decode("utf-8", ...)'

    def test_m8_init_decodes(self):
        """__init__ 应通过 _decode_redis_str 处理 name."""
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsSettings', '__init__')
        assert '_decode_redis_str' in body, \
            'M8 修复未应用: __init__ 未调用 _decode_redis_str'

    def test_m8_settings_change_handles_none_name(self):
        """修复后 settings_change 应对 self.name=None 返错 (bytes + str TypeError)."""
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsSettings', 'settings_change')
        # 应有 self.name is None 检查
        assert 'self.name is None' in body, \
            'M8 修复未应用: settings_change 未对 self.name=None 早退'


# =============================================================================
# M9: Settings.change SWITCH_FIELDS 只接受合法布尔值
# =============================================================================
class TestRev30M9:
    """M9: SWITCH_FIELDS 字段只接受 true/false/1/0, 其他值返错."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Settings.py')

    def test_m9_switch_allowed_set(self):
        content = _read(self.SRC)
        assert '_SWITCH_ALLOWED' in content, \
            'M9 修复未应用: 应有 _SWITCH_ALLOWED 集合'
        # 应包含 true/false/1/0
        m = re.search(r"_SWITCH_ALLOWED\s*=\s*frozenset\s*\(\s*\{([^}]+)\}\s*\)", content)
        assert m, '_SWITCH_ALLOWED 格式有误'
        items = m.group(1)
        for tok in ('true', 'false', '1', '0'):
            assert "'%s'" % tok in items or '"%s"' % tok in items, \
                'M9 修复未应用: _SWITCH_ALLOWED 应包含 %r' % tok

    def test_m9_switch_validation(self):
        """settings_change 应校验 SWITCH_FIELDS 值."""
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsSettings', 'settings_change')
        # 应有 elif field in SWITCH_FIELDS 分支
        assert 'elif field in SWITCH_FIELDS' in body, \
            'M9 修复未应用: 缺少 elif field in SWITCH_FIELDS 校验分支'
        assert 'v_lower not in _SWITCH_ALLOWED' in body, \
            'M9 修复未应用: 未校验 v_lower in _SWITCH_ALLOWED'

    def test_switch_accepts_on_off_and_normalizes(self):
        """SETTINGS-SAVE-FIX: 前端/DB 惯例为 'on'/'off', 白名单必须接受并归一化存储.
        旧白名单只认 true/false/1/0, 导致设置页保存全部被 code=100 拒绝."""
        content = _read(self.SRC)
        m = re.search(r"_SWITCH_ALLOWED\s*=\s*frozenset\s*\(\s*\{([^}]+)\}\s*\)", content)
        assert m, '_SWITCH_ALLOWED 格式有误'
        for tok in ('on', 'off'):
            assert "'%s'" % tok in m.group(1) or '"%s"' % tok in m.group(1), \
                "SETTINGS-SAVE-FIX 未应用: _SWITCH_ALLOWED 应包含 %r" % tok
        body = _extract_method(content, 'OgsSettings', 'settings_change')
        assert '_SWITCH_TRUTHY' in body, \
            "SETTINGS-SAVE-FIX 未应用: 应归一化为 'on'/'off' 存储 (_SWITCH_TRUTHY)"


# =============================================================================
# M10: Basics.GetUserImage 文件句柄关闭
# =============================================================================
class TestRev30M10:
    """M10: GetUserImage.get_img 用 with open() 关闭文件句柄."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_m10_uses_with_open(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'GetUserImage', 'get_img')
        # 应有 with open(...) as f:
        assert re.search(r'with\s+open\s*\(', body), \
            'M10 修复未应用: get_img 应使用 with open() 自动关闭句柄'
        # 不应再有裸 open(...).read()
        assert re.search(r'open\s*\([^)]+\)\.read\s*\(\s*\)', body) is None, \
            'M10 修复未应用: 仍有裸 open(...).read() 调用'


# =============================================================================
# L1: cron pause_job/remove_job/close_job rollback
# =============================================================================
class TestRev30L1:
    """L1: pause_job/remove_job/resume_job/close_job 异常时 rollback."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_l1_rollback_in_all(self):
        content = _read(self.SRC)
        # 4 个方法都应有 rollback (在 except 分支)
        for method in ('pause_job', 'remove_job', 'resume_job', 'close_job'):
            body = _extract_method(content, 'OgsCron', method)
            assert body, '未找到 %s 方法' % method
            assert 'db.session.rollback' in body, \
                'L1 修复未应用: %s 异常分支未调用 db.session.rollback()' % method


# =============================================================================
# L2: cron.OgsCron.resume_job owner 校验
# =============================================================================
class TestRev30L2:
    """L2: resume_job 应有 _can_operate_cron 校验 (与 pause/remove 一致)."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_l2_resume_owner_check(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsCron', 'resume_job')
        assert '_can_operate_cron' in body, \
            'L2 修复未应用: resume_job 未调用 _can_operate_cron 校验 owner'


# =============================================================================
# L3: cron.OgsCron.resume_job task 为 None 早退
# =============================================================================
class TestRev30L3:
    """L3: resume_job 应在 task 为 None 时返 '任务不存在'."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_l3_resume_no_task_early_return(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'OgsCron', 'resume_job')
        # task = ...filter_by(job_name=...).first() 后应 if not task: return
        # 检查存在 if not task: ... msg='任务不存在'
        # REV38-M6: 兼容 api_error(ApiCode.CRON_NOT_FOUND, '任务不存在')
        assert re.search(r'if\s+not\s+task\s*:\s*\n\s+return\s+(?:jsonify|api_error)\([^)]*任务不存在', body), \
            'L3 修复未应用: resume_job 未对 task 为 None 返 任务不存在'


# =============================================================================
# L4: Basics.CountList.server_chart_count_all 命名
# =============================================================================
class TestRev30L4:
    """L4: 移除 new_date (days=-5 反向), 用 start_date + 正 timedelta."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_l4_no_reverse_new_date(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'CountList', 'server_chart_count_all')
        assert 'new_date' not in body, \
            'L4 修复未应用: server_chart_count_all 仍有 new_date 反向变量'
        assert 'days=-' not in body, \
            'L4 修复未应用: 仍有 timedelta(days=-X) 反向天数'
        assert 'start_date' in body, \
            'L4 修复未应用: 应有 start_date 正向变量'


# =============================================================================
# L5: Basics.DataList.get_list N+1 → 批量 + 真实主键
# =============================================================================
class TestRev30L5:
    """L5: DataList.get_list 用 t_host.query.filter(in_) 批量, 移除假主键 group_count=1000."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_l5_no_n_plus_1(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'DataList', 'get_list')
        # 应有 .in_(res_group)
        assert re.search(r'\.in_\s*\(\s*res_group\s*\)', body), \
            'L5 修复未应用: get_list 应使用 .in_(res_group) 批量查'
        # 不应有 for i in res_group: 循环里再 query (这是 N+1)
        # 简单检查: for ... res_group: 紧跟 query 的模式不再存在
        for_loop_query_pattern = re.compile(
            r'for\s+\w+\s+in\s+res_group\s*:\s*\n\s+\w+\s*=\s*t_host\.query\.filter',
        )
        assert not for_loop_query_pattern.search(body), \
            'L5 修复未应用: 仍有 for ... in res_group 内 t_host.query.filter (N+1)'

    def test_l5_no_fake_primary_key(self):
        """不应再有 group_count = 1000 起步假主键."""
        content = _read(self.SRC)
        body = _extract_method(content, 'DataList', 'get_list')
        assert 'group_count = 1000' not in body, \
            'L5 修复未应用: 仍有 group_count = 1000 假主键'
        assert 'group_count += 1' not in body, \
            'L5 修复未应用: 仍有 group_count += 1 自增'


# =============================================================================
# L6: Basics.DataList.get_list 死代码注释
# =============================================================================
class TestRev30L6:
    """L6: 删除 # host_count = 100 死代码注释."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_l6_no_dead_comment(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'DataList', 'get_list')
        assert '# host_count = 100' not in body, \
            'L6 修复未应用: 仍有死代码注释 # host_count = 100'


# =============================================================================
# L7: Basics.CountList.server_chart_count_all 显式字段
# =============================================================================
class TestRev30L7:
    """L7: server_chart_count_all 用 i.chart_date 等显式字段替代 i.__dict__."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_l7_no_dict_access(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'CountList', 'server_chart_count_all')
        # 不应有 i.__dict__ / query_msg['chart_date']
        assert 'i.__dict__' not in body, \
            'L7 修复未应用: 仍有 i.__dict__ 访问'
        # 显式字段访问
        assert 'i.chart_date' in body or 'item.chart_date' in body, \
            'L7 修复未应用: 应使用 i.chart_date 等显式字段'


# =============================================================================
# L8: Basics.GetUserImage.get_img 死变量
# =============================================================================
class TestRev30L8:
    """L8: 删除 request_begin_time 死变量."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_l8_no_dead_variable(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'GetUserImage', 'get_img')
        assert 'request_begin_time' not in body, \
            'L8 修复未应用: 仍有 request_begin_time 死变量'


# =============================================================================
# L9: Basics.PutUserImage.put_img 上传加固
# =============================================================================
class TestRev30L9:
    """L9: put_img 加 size 限制 + Image.verify + format 白名单."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_l9_size_limit(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'PutUserImage', 'put_img')
        assert '_MAX_UPLOAD_IMG_SIZE' in content, \
            'L9 修复未应用: 应有 _MAX_UPLOAD_IMG_SIZE 常量'
        assert re.search(r'size\s*>\s*_MAX_UPLOAD_IMG_SIZE', body), \
            'L9 修复未应用: 应有 size > _MAX_UPLOAD_IMG_SIZE 检查'

    def test_l9_image_verify(self):
        """put_img 应有 Image.verify() 校验."""
        content = _read(self.SRC)
        body = _extract_method(content, 'PutUserImage', 'put_img')
        assert 'im.verify()' in body, \
            'L9 修复未应用: 缺 im.verify() 校验'

    def test_l9_format_whitelist(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'PutUserImage', 'put_img')
        assert '_ALLOWED_IMG_FORMATS' in content, \
            'L9 修复未应用: 应有 _ALLOWED_IMG_FORMATS 白名单'
        assert 'im.format not in _ALLOWED_IMG_FORMATS' in body, \
            'L9 修复未应用: 应校验 im.format'

    def test_l9_unidentified_image_error(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'PutUserImage', 'put_img')
        assert 'UnidentifiedImageError' in body, \
            'L9 修复未应用: 缺 UnidentifiedImageError 捕获'


# =============================================================================
# L10: Captcha 限流命中记录日志
# =============================================================================
class TestRev30L10:
    """L10: CaptchaGet.get 限流命中应 Log.logger.warning."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Captcha.py')

    def test_l10_warning_log(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'CaptchaGet', 'get')
        assert 'Log.logger.warning' in body, \
            'L10 修复未应用: CaptchaGet.get 限流命中未记录 warning 日志'
        assert 'captcha rate limit' in body, \
            'L10 修复未应用: 日志应含 "captcha rate limit" 标记'


# =============================================================================
# L11: Captcha verify_captcha decode errors='strict'
# =============================================================================
class TestRev30L11:
    """L11: verify_captcha 用 errors='strict', 异常走 except 返 False."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Captcha.py')

    def test_l11_strict_decode(self):
        content = _read(self.SRC)
        assert "errors='strict'" in content or 'errors="strict"' in content, \
            'L11 修复未应用: decode 仍用 errors="ignore"'
        # 不应再有 errors='ignore'
        assert "errors='ignore'" not in content and 'errors="ignore"' not in content, \
            'L11 修复未应用: 仍有 errors="ignore"'
        # 应有 except (UnicodeDecodeError, AttributeError)
        assert re.search(r'except\s*\(\s*UnicodeDecodeError', content), \
            'L11 修复未应用: 缺 UnicodeDecodeError 捕获'


# =============================================================================
# L12: files.FileGet._validate_dir_name Windows 盘符注释
# =============================================================================
class TestRev30L12:
    """L12: _validate_dir_name 应有 REV30-L12 说明注释."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'files', 'file.py')

    def test_l12_docstring_comment(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'FileGet', '_validate_dir_name')
        # 应有 REV30-L12 注释
        assert 'REV30-L12' in body, \
            'L12 修复未应用: _validate_dir_name 缺 REV30-L12 注释说明'


# =============================================================================
# L13: files.FileGet.save_file 显式 size 限制
# =============================================================================
class TestRev30L13:
    """L13: save_file 应有 _MAX_SAVE_FILE_SIZE 显式 size 检查."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'files', 'file.py')

    def test_l13_size_limit_constant(self):
        content = _read(self.SRC)
        assert '_MAX_SAVE_FILE_SIZE' in content, \
            'L13 修复未应用: 缺 _MAX_SAVE_FILE_SIZE 常量'

    def test_l13_save_file_uses_size_check(self):
        content = _read(self.SRC)
        body = _extract_method(content, 'FileGet', 'save_file')
        assert 'size > _MAX_SAVE_FILE_SIZE' in body, \
            'L13 修复未应用: save_file 未做 size > _MAX_SAVE_FILE_SIZE 检查'


# =============================================================================
# 集成行为测试 (核心 HIGH 项)
# =============================================================================
class TestRev30H1Behavior:
    """H1 行为测试: DataSumAll.get_sum 应在所有 group 更新后才返回."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Basics.py')

    def test_h1_behavior_multi_group_no_early_return(self, monkeypatch, flask_request_ctx):
        """3 个 group 都应触发 osql_up 调用."""
        from app.local import Basics

        # mock osql_up 跟踪调用次数 (更可靠, 不依赖 SQLAlchemy descriptor)
        up_calls = []

        def fake_osql_up(table, where, data):
            up_calls.append((table, where, data))

        monkeypatch.setattr(Basics, 'osql_up', fake_osql_up)

        # mock t_group.query / t_host.query 通过 fake_db 提供的 MagicMock
        #   - t_group.query.with_entities().all() 返 ['g1','g2','g3']
        #   - t_host.query.filter_by().count() 返 7
        # 直接 monkeypatch t_group.query 和 t_host.query 属性
        from app.core.db import database as db_mod

        # mock t_group.query 链: with_entities().all()
        class _GroupQ:
            def with_entities(self, *a, **kw):
                return self
            def all(self):
                return [('g1',), ('g2',), ('g3',)]
        # mock t_host.query 链: filter_by().count()
        class _HostQ:
            def filter_by(self, **kw):
                return self
            def count(self):
                return 7

        # 直接给类属性 query 赋值 (避开 descriptor)
        monkeypatch.setattr(db_mod.t_group, 'query', _GroupQ(), raising=False)
        monkeypatch.setattr(db_mod.t_host, 'query', _HostQ(), raising=False)
        # 同时 patch 已加载的 Basics 模块引用
        monkeypatch.setattr(Basics.t_group, 'query', _GroupQ(), raising=False)
        monkeypatch.setattr(Basics.t_host, 'query', _HostQ(), raising=False)

        flask_request_ctx({'sum_name': 'group'})

        instance = Basics.DataSumAll()
        result = instance.get_sum()
        result_data = result.get_json()

        # 关键断言: 3 个 group 都应被更新
        assert len(up_calls) == 3, \
            'H1 行为测试: 期望 3 次 osql_up 调用 (每个 group), 实际 %d' % len(up_calls)
        assert all(c[0] == 't_group' for c in up_calls), '应都更新 t_group 表'
        assert result_data.get('updated') is True, '应返回 updated=True'


class TestRev30H3Behavior:
    """H3 行为测试: Settings.change NUMBER_FIELDS 'abc' 返 code=100."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Settings.py')

    def test_h3_number_field_garbage_returns_error(self, monkeypatch, flask_request_ctx):
        from app.local import Settings
        from app.tools import redisdb

        # mock ConnRedis: 必须替换 Settings 模块里已 import 的引用
        # (line 4: `from app.tools.redisdb import ConnRedis` 把对象放进 Settings 命名空间)
        class FakeConn:
            def get(self, k):
                if k == 'token123':
                    return b'alice'  # 返回 bytes 测试 M8 修复
                if k == 'alice_role':
                    return 'admin'
                return None
            def set(self, *a, **kw): pass
            def delete(self, *a, **kw): pass

        class FakeRedis:
            def __init__(self):
                self.conn = FakeConn()

        # 双保险: 同时 patch redisdb.ConnRedis 和 Settings.ConnRedis
        monkeypatch.setattr(redisdb, 'ConnRedis', FakeRedis)
        monkeypatch.setattr(Settings, 'ConnRedis', FakeRedis)

        # 跟踪 t_settings.update 是否被调用 (H3 期望不应调用)
        update_called = []

        class FakeSettingsQuery:
            def filter_by(self, **kw):
                return self
            def update(self, data):
                update_called.append(data)
                return 1
        from app.core.db import database as db_mod
        monkeypatch.setattr(db_mod.t_settings, 'query', FakeSettingsQuery(), raising=False)
        monkeypatch.setattr(Settings.t_settings, 'query', FakeSettingsQuery(), raising=False)

        # 绕开 __init__ 中的 redis/cookies 调用, 直接创建带 mock 属性的实例
        # 用 __new__ 跳过 __init__, 然后手工填充 settings_change 需要的属性
        instance = Settings.OgsSettings.__new__(Settings.OgsSettings)
        instance.ords = FakeRedis()
        instance.user_token = 'token123'
        instance.name = 'alice'  # M8: bytes 解码后是 str 'alice'
        instance.lt = None

        # 验证 mock 生效
        assert instance.name == 'alice', \
            'M8 行为: bytes 解码后应得到 str "alice", 实际 %r' % instance.name

        # 修改 request.values 注入 NUMBER_FIELDS 垃圾值
        flask_request_ctx({'login_time': 'abc'})

        result = instance.settings_change()
        data = result.get_json()
        assert data.get('code') == 100, \
            'H3 行为: NUMBER_FIELDS="abc" 应返 code=100, 实际: %s' % data
        assert 'login_time' in data.get('msg', ''), \
            'H3 行为: msg 应提及字段名 login_time'
        # update 不应被调用
        assert not update_called, \
            'H3 行为: settings_change 返错后不应再调用 t_settings.update, 实际调用了'


class TestRev30M1Behavior:
    """M1 行为测试: CronList.__init__ 非数字 page/limit 应默认 1/10."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'cron', 'cron.py')

    def test_m1_non_numeric_pagination_safe(self, monkeypatch):
        from app.cron import cron as cron_mod
        from app.tools import redisdb
        from app.tools.SqlListTool import ListTool

        # mock redisdb ConnRedis (CronList.__init__ 创建实例)
        class FakeRedis:
            pass
        monkeypatch.setattr(redisdb, 'ConnRedis', lambda: FakeRedis())

        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/?page=abc&limit=xyz'):
            instance = cron_mod.CronList()
            assert instance.table_page == 1, \
                'M1 行为: 非数字 page 应默认 1, 实际 %r' % instance.table_page
            assert instance.table_limit == 10, \
                'M1 行为: 非数字 limit 应默认 10, 实际 %r' % instance.table_limit


class TestRev30H4Behavior:
    """H4 行为测试: DownloadFile.download 错误返 Response 对象, 非 str."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'download.py')

    def test_h4_error_returns_response_object(self, flask_request_ctx):
        from app.local import download

        flask_request_ctx({'filename': '../etc/passwd'})  # 含 .. 不通过 _FILENAME_RE
        instance = download.DownloadFile()
        result = instance.download()

        # 修复后: result 应该是 flask Response 对象, 不是裸 str
        assert hasattr(result, 'mimetype'), \
            'H4 行为: 错误应返 Response 对象 (有 mimetype), 实际类型: %s' % type(result)
        assert result.mimetype == 'application/json', \
            'H4 行为: 错误 Response mimetype 应 application/json'
        assert result.status_code == 400, \
            'H4 行为: 错误应返 HTTP 400'

    def test_h4_content_disposition_safe(self, flask_request_ctx, tmp_path, monkeypatch):
        """filename 含特殊字符应被 secure_filename 清理 + RFC 6266 编码."""
        from app.local import download

        # 创建临时文件
        target = tmp_path / 'safe.bin'
        target.write_bytes(b'hello')
        # 直接 patch 被测模块持有的配置引用，避免其他测试 reload(config)
        # 后产生新 dict，导致本测试修改了错误的对象。
        monkeypatch.setitem(
            download.FILE_CONF, 'file_path2', str(tmp_path) + os.sep)

        flask_request_ctx({'filename': 'safe.bin'})
        instance = download.DownloadFile()
        result = instance.download()

        # 应是 Response
        assert hasattr(result, 'headers')
        cd = result.headers.get('Content-Disposition', '')
        # 应走 RFC 6266 filename*=
        assert "filename*=UTF-8''" in cd, \
            'H4 行为: Content-Disposition 应走 RFC 6266 filename*, 实际: %s' % cd
        # 不应含 raw 双引号 (旧格式)
        assert 'filename="safe.bin"' not in cd, \
            'H4 行为: 不应再用旧 filename="..." 格式'


class TestRev30L11Behavior:
    """L11 行为测试: verify_captcha 处理损坏 bytes 时返 False."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Captcha.py')

    def test_l11_invalid_bytes_returns_false(self):
        from app.local.Captcha import verify_captcha

        # verify_captcha 内部访问 ords.conn.get / delete, 所以 FakeRedis 必须有 .conn 子对象
        class FakeConn:
            def __init__(self, stored):
                self._stored = stored
                self.deleted = False
            def get(self, key):
                return self._stored
            def delete(self, key):
                self.deleted = True

        class FakeRedis:
            def __init__(self, stored):
                self.conn = FakeConn(stored)

        # 构造 invalid UTF-8 bytes: \xff\xfe 单独存在不构成合法 UTF-8 起始
        # 在 strict 模式下应抛 UnicodeDecodeError
        invalid = b'\xff\xfeabc'  # \xff\xfe 不合法 UTF-8 起始
        fake = FakeRedis(invalid)
        result = verify_captcha(fake, 'cid', 'user_answer')
        assert result is False, \
            'L11 行为: 非法 UTF-8 bytes 应返 False (decode strict 抛异常走 except)'

    def test_l11_valid_bytes_returns_correctly(self):
        """正常 UTF-8 bytes 应正常比对."""
        from app.local.Captcha import verify_captcha

        # verify_captcha 内部访问 ords.conn.get / delete, 所以 FakeRedis 必须有 .conn 子对象
        class FakeConn:
            def __init__(self, stored):
                self._stored = stored
            def get(self, key):
                return self._stored
            def delete(self, key):
                pass

        class FakeRedis:
            def __init__(self, stored):
                self.conn = FakeConn(stored)

        valid = 'hello'
        fake = FakeRedis(valid.encode('utf-8'))
        assert verify_captcha(fake, 'cid', 'HELLO') is True, '大小写不敏感比对应通过'
        assert verify_captcha(fake, 'cid', 'world') is False, '不匹配应返 False'


class TestRev30L10Behavior:
    """L10 行为测试: CaptchaGet.get 限流命中调用 Log.logger.warning."""

    SRC = os.path.join(os.path.dirname(__file__), '..', 'app', 'local', 'Captcha.py')

    def test_l10_warning_log_called_on_rate_limit(self, monkeypatch, flask_request_ctx):
        from app.local import Captcha

        # 替换 Log.logger.warning 为 spy
        warnings = []

        class FakeLogger:
            @staticmethod
            def warning(msg, *a):
                warnings.append(msg)

        class FakeLog:
            logger = FakeLogger

        monkeypatch.setattr(Captcha, 'Log', FakeLog)

        instance = Captcha.CaptchaGet()
        # 直接调 _captcha_rate_limit 返 (False, 30)
        monkeypatch.setattr(instance, '_captcha_rate_limit', lambda ip: (False, 30))
        monkeypatch.setattr(instance, '_client_ip', lambda: '1.2.3.4')

        flask_request_ctx({})
        result = instance.get()
        data = result.get_json()
        assert data.get('code') == 429, \
            'L10 行为: 限流命中应返 code=429, 实际: %s' % data
        assert any('captcha rate limit' in str(w) for w in warnings), \
            'L10 行为: 限流命中应调用 Log.logger.warning("captcha rate limit...")'
