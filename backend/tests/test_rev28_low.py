# -*- coding: utf-8 -*-
"""
REV28 LOW 6 项结构性优化回归测试
====================================

覆盖 REV28_review.md 中 LOW 风险修复:
- L1: audlog.py 三个日志类提取 _BaseToolsLog 基类
- L2: loginlogs 提取 offset/limit 私有方法消除重复
- L5: SendMail.send 拆分为 _build_msg + _send_msg
- L6: loginlogs.get_date_logs 用 datetime.strptime 校验日期格式

执行:
    cd backend && python -m pytest tests/test_rev28_low.py -v
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), 'r', encoding='utf-8') as f:
        return f.read()


def _extract_method(content, method_name):
    """提取方法体到下一个 def/@/class.
    ti3-HINT: 容忍返回类型注解 -> ... (如 def foo() -> None:)
    """
    m = re.search(r'def\s+' + method_name + r'\s*\([^)]*\)(?:\s*->\s*[^:]+)?\s*:', content)
    if not m:
        return None
    start = m.end()
    end_m = re.search(r'\n    def\s|\n    @|\nclass\s', content[start:])
    return content[start:start + end_m.start()] if end_m else content[start:]


def _extract_class(content, class_name):
    """提取类体到下一个 class"""
    m = re.search(r'class\s+' + class_name + r'\s*[(:]', content)
    if not m:
        return None
    start = m.start()
    end_m = re.search(r'\nclass\s', content[start:])
    return content[start:start + end_m.start()] if end_m else content[start:]


def _strip_comments(body):
    return '\n'.join(l for l in body.split('\n') if not l.strip().startswith('#'))


class TestRev28L1AudlogBaseClass:
    """REV28-L1: audlog.py 三个日志类应继承 _BaseToolsLog 基类"""

    def test_base_class_exists(self):
        content = _read('app/tools/audlog.py')
        assert '_BaseToolsLog' in content, \
            "应提取 _BaseToolsLog 基类 (L1)"
        # 基类继承 LogTimestamp
        assert re.search(r'class\s+_BaseToolsLog\s*\(\s*LogTimestamp\s*\)', content), \
            "_BaseToolsLog 应继承 LogTimestamp (L1)"
        # 基类应有 _write 方法
        body = _extract_method(content, '_write')
        assert body, "_BaseToolsLog 应有 _write 方法 (L1)"

    def test_login_tools_log_inherits_base(self):
        """LoginToolsLog 应继承 _BaseToolsLog, 声明 _TABLE='t_login_log'"""
        content = _read('app/tools/audlog.py')
        body = _extract_class(content, 'LoginToolsLog')
        assert body, "未找到 LoginToolsLog 类"
        assert '_BaseToolsLog' in body, \
            "LoginToolsLog 应继承 _BaseToolsLog (L1)"
        assert "'t_login_log'" in body or '"t_login_log"' in body, \
            "LoginToolsLog 应声明 _TABLE='t_login_log' (L1)"

    def test_cz_tools_log_inherits_base(self):
        """CzToolsLog 应继承 _BaseToolsLog, 声明 _TABLE='t_cz_log'"""
        content = _read('app/tools/audlog.py')
        body = _extract_class(content, 'CzToolsLog')
        assert body, "未找到 CzToolsLog 类"
        assert '_BaseToolsLog' in body, \
            "CzToolsLog 应继承 _BaseToolsLog (L1)"
        assert "'t_cz_log'" in body or '"t_cz_log"' in body, \
            "CzToolsLog 应声明 _TABLE='t_cz_log' (L1)"

    def test_com_tools_log_inherits_base(self):
        """ComToolsLog 应继承 _BaseToolsLog, 声明 _TABLE='t_command_log'"""
        content = _read('app/tools/audlog.py')
        body = _extract_class(content, 'ComToolsLog')
        assert body, "未找到 ComToolsLog 类"
        assert '_BaseToolsLog' in body, \
            "ComToolsLog 应继承 _BaseToolsLog (L1)"
        assert "'t_command_log'" in body or '"t_command_log"' in body, \
            "ComToolsLog 应声明 _TABLE='t_command_log' (L1)"

    def test_subclass_host_log_uses_write(self):
        """子类的 host_log 应简化为调用 _write"""
        content = _read('app/tools/audlog.py')
        for cls in ('LoginToolsLog', 'CzToolsLog', 'ComToolsLog'):
            body = _extract_class(content, cls)
            assert body, "未找到 %s 类" % cls
            host_log_body = _extract_method(body, 'host_log')
            assert host_log_body, "%s 应有 host_log 方法" % cls
            assert 'self._write' in host_log_body, \
                "%s.host_log 应调用 self._write (L1)" % cls


class TestRev28L2LoginlogsPaginateExtract:
    """REV28-L2: loginlogs 应有 _paginate 私有方法复用 offset/limit"""

    def test_paginate_method_exists(self):
        content = _read('app/audit/loginlogs.py')
        body = _extract_method(content, '_paginate')
        assert body, "应提取 _paginate 私有方法 (L2)"
        assert 'offset' in body and 'limit' in body, \
            "_paginate 应包含 offset + limit (L2)"
        assert 'self.table_offset' in body and 'self.table_limit' in body, \
            "_paginate 应使用 self.table_offset/limit (L2)"

    def test_get_logs_uses_paginate(self):
        content = _read('app/audit/loginlogs.py')
        body = _extract_method(content, 'get_logs')
        assert body, "未找到 get_logs 方法"
        code = _strip_comments(body)
        assert 'self._paginate' in code, \
            "get_logs 应使用 self._paginate (L2)"
        # 直接调用 .offset / .limit 不应再重复
        assert '.offset(self.table_offset)' not in code, \
            "get_logs 不应再直接调用 .offset(self.table_offset) (L2)"

    def test_get_select_logs_uses_paginate(self):
        content = _read('app/audit/loginlogs.py')
        body = _extract_method(content, 'get_select_logs')
        assert body, "未找到 get_select_logs 方法"
        code = _strip_comments(body)
        assert 'self._paginate' in code, \
            "get_select_logs 应使用 self._paginate (L2)"
        assert '.offset(self.table_offset)' not in code, \
            "get_select_logs 不应再直接调用 .offset(self.table_offset) (L2)"

    def test_get_date_logs_uses_paginate(self):
        content = _read('app/audit/loginlogs.py')
        body = _extract_method(content, 'get_date_logs')
        assert body, "未找到 get_date_logs 方法"
        code = _strip_comments(body)
        assert 'self._paginate' in code, \
            "get_date_logs 应使用 self._paginate (L2)"
        assert '.offset(self.table_offset)' not in code, \
            "get_date_logs 不应再直接调用 .offset(self.table_offset) (L2)"




class TestRev28L5SendmailSplit:
    """REV28-L5: SendMail.send 应拆分为 _build_msg + _send_msg"""

    def test_build_msg_method_exists(self):
        content = _read('app/tools/sendmail.py')
        body = _extract_method(content, '_build_msg')
        assert body, "应提取 _build_msg 私有方法 (L5)"
        # 应包含 MIME 构造
        assert 'MIMEText' in body, \
            "_build_msg 应构造 MIMEText (L5)"
        # 应包含 header 校验
        assert '_validate_email' in body or '_HEADER_FORBIDDEN' in body, \
            "_build_msg 应包含校验 (L5)"

    def test_send_msg_method_exists(self):
        content = _read('app/tools/sendmail.py')
        body = _extract_method(content, '_send_msg')
        assert body, "应提取 _send_msg 私有方法 (L5)"
        assert 'sendmail' in body, \
            "_send_msg 应调用 sendmail (L5)"
        # REV28-M3: 异常时应 quit
        assert 'except Exception' in body, \
            "_send_msg 应有 except Exception 清理 (L5+M3)"
        assert 'smtp.quit' in body or 'self.smtp = None' in body, \
            "_send_msg 异常时应 quit smtp (L5+M3)"

    def test_send_method_thin_dispatcher(self):
        content = _read('app/tools/sendmail.py')
        body = _extract_method(content, 'send')
        assert body, "未找到 send 方法"
        code = _strip_comments(body)
        # send 应是薄调度层, 调用 _build_msg + _send_msg
        assert '_build_msg' in code and '_send_msg' in code, \
            "send 应委托给 _build_msg + _send_msg (L5)"


class TestRev28L6DateFormatValidation:
    """REV28-L6: loginlogs.get_date_logs 应使用 datetime 校验日期"""

    def test_parse_jg_date_helper_exists(self):
        """loginlogs 应有 _parse_jg_date 校验辅助"""
        content = _read('app/audit/loginlogs.py')
        assert '_parse_jg_date' in content, \
            "应有 _parse_jg_date 校验辅助 (L6)"
        body = _extract_method(content, '_parse_jg_date')
        assert body, "未找到 _parse_jg_date 方法"
        code = _strip_comments(body)
        assert 'datetime' in code, \
            "_parse_jg_date 应使用 datetime (L6)"
        assert 'strptime' in code, \
            "_parse_jg_date 应使用 datetime.strptime (L6)"

    def test_get_date_logs_validates_format(self):
        content = _read('app/audit/loginlogs.py')
        body = _extract_method(content, 'get_date_logs')
        assert body, "未找到 get_date_logs 方法"
        code = _strip_comments(body)
        assert '_parse_jg_date' in code, \
            "get_date_logs 应调用 _parse_jg_date (L6)"
        # 校验失败应返 code=100
        assert '日期格式错误' in code or '日期格式错误'.encode().decode() in code, \
            "get_date_logs 校验失败应返友好错误 (L6)"
