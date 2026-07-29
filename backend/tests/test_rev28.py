# -*- coding: utf-8 -*-
"""
REV28 mail/audit 模块结构性优化回归测试
====================================================

覆盖 REV28_review.md 中 HIGH / MED 风险修复。

执行:
    cd backend && python -m pytest tests/test_rev28.py -v
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
    """过滤注释行"""
    return '\n'.join(l for l in body.split('\n') if not l.strip().startswith('#'))


class TestRev28H4LikeInjectionFix:
    """REV28-H4: get_select_logs 应转义 LIKE 通配符"""

    def test_get_select_logs_escapes_like(self):
        content = _read('app/audit/loginlogs.py')
        body = _extract_method(content, 'get_select_logs')
        assert body, "未找到 get_select_logs 方法"
        code = _strip_comments(body)
        assert 'safe_date' in code, \
            "get_select_logs 应有 safe_date 变量 (H4)"
        assert 'replace' in code, \
            "get_select_logs 应转义 LIKE 特殊字符 (H4)"
        assert "escape" in code or "\\\\" in code, \
            "get_select_logs 应使用 escape 参数 (H4)"


class TestRev28MEDBatchFixes:
    """REV28 MED 批量修复 (M1-M5)"""

    def test_m1_mail_api_no_typo(self):
        """M1: MailApi 不应有 to_amil 拼写错误"""
        content = _read('app/mail/MailApi.py')
        assert 'to_amil' not in content, \
            "MailApi 不应有 to_amil 拼写 (M1)"
        assert 'to_mail' in content, \
            "MailApi 应使用 to_mail (M1)"

    def test_m3_sendmail_except_cleanup(self):
        """M3: SendMail.send 异常时应 quit SMTP (含 L5 重构后的 _send_msg 拆分形态).
        REV28-L5 把 send 拆为 _build_msg + _send_msg, 异常清理逻辑移至 _send_msg.
        M3 语义不变 (异常时 quit smtp), 但检查范围扩大到整个 SendMail 类.
        """
        content = _read('app/tools/sendmail.py')
        # 抽取整个 SendMail 类体 (不仅 send 方法)
        cls_body = _extract_class(content, 'SendMail')
        assert cls_body, "未找到 SendMail 类"
        code = _strip_comments(cls_body)
        assert 'except Exception' in code, \
            "SendMail 应有 except Exception 分支 (M3)"
        assert 'smtp.quit' in code or 'self.smtp = None' in code, \
            "SendMail 异常时应 quit/close SMTP 连接 (M3)"
        # 不应再有 finally: pass
        assert 'finally' not in code or 'pass' not in code.split('finally')[1][:30], \
            "SendMail 不应再有 finally: pass (M3)"

    def test_m5_loginlogs_except_exception(self):
        """M5: loginlogs 应捕获 Exception 而非 IOError"""
        content = _read('app/audit/loginlogs.py')
        code = _strip_comments(content)
        assert 'except Exception' in code, \
            "loginlogs 应使用 except Exception (M5)"
        assert 'except IOError' not in code, \
            "loginlogs 不应再有 except IOError (M5)"
