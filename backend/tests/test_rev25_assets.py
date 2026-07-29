# -*- coding: utf-8 -*-
"""
REV25 assets 模块回归测试
========================

覆盖 REV25_assets_review.md 中 HIGH / MED / LOW 风险修复。

执行:
    cd backend && python -m pytest tests/test_rev25_assets.py -v
"""

import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TestRev25H1ServerAddValidation:
    """REV25-H1: ServerAdd 资产参数校验 (alias/host_ip/host_port/group)"""

    def test_server_add_has_validate_params(self):
        """ServerAdd 类必须有 _validate_params 方法"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取 ServerAdd 类体
        m = re.search(
            r'class\s+ServerAdd\s*\([^)]*\)\s*:(.*?)(?=\nclass\s|\Z)',
            content, re.DOTALL,
        )
        assert m, "未找到 ServerAdd 类"
        body = m.group(1)
        assert '_validate_params' in body, \
            "ServerAdd 应有 _validate_params 方法 (REV25-H1)"
        assert 'ipaddress.ip_address' in body, \
            "_validate_params 应用 ipaddress.ip_address 校验 host_ip"
        assert '_HOST_ALIAS_RE' in body, \
            "_validate_params 应用 _HOST_ALIAS_RE 校验 alias"

    def test_host_add_calls_validate_first(self):
        """host_add 方法应先调用 _validate_params 再执行业务逻辑"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        m = re.search(
            r'def\s+host_add\s*\(\s*self\s*\)\s*:(.*?)(?=\n    def\s|\n    @|\nclass\s|\Z)',
            content, re.DOTALL,
        )
        assert m, "未找到 host_add 方法"
        body = m.group(1)
        # _validate_params 应在 osql_in 之前调用
        validate_pos = body.find('_validate_params')
        osql_pos = body.find('osql_in')
        assert validate_pos != -1, "host_add 应调用 _validate_params"
        assert osql_pos != -1, "host_add 应调用 osql_in"
        assert validate_pos < osql_pos, \
            "_validate_params 必须在 osql_in 之前调用"

    def test_alias_regex_defined(self):
        """_HOST_ALIAS_RE 正则应在模块级定义"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        assert '_HOST_ALIAS_RE' in content, "应定义 _HOST_ALIAS_RE 常量"
        # 应在 class 之前定义
        class_pos = content.find('class ServerList')
        regex_pos = content.find('_HOST_ALIAS_RE')
        assert regex_pos < class_pos, "_HOST_ALIAS_RE 应在 class 之前定义"

    def test_port_range_check(self):
        """_validate_params 应校验 port 范围 1-65535"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        m = re.search(
            r'class\s+ServerAdd\s*\([^)]*\)\s*:(.*?)(?=\nclass\s|\Z)',
            content, re.DOTALL,
        )
        body = m.group(1)
        assert '65535' in body, "port 校验应包含 65535 上限"
        assert '1 <= port' in body or '1 <= int' in body, \
            "port 校验应包含 1 <= port"

    def test_ip_validation_uses_ipaddress(self):
        """host_ip 校验应使用 ipaddress 模块"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import ipaddress' in content, "应 import ipaddress"
        assert 'ipaddress.ip_address' in content, \
            "应用 ipaddress.ip_address 校验 host_ip"


class TestRev25H2ServerCmdNoPlaintextPassword:
    """REV25-H2: ServerCmd.sh_cmd 不应访问 t_host 不存在的 host_password 字段"""

    def test_sh_cmd_uses_get_ssh_connection(self):
        """sh_cmd 应用 get_ssh_connection, 不用 RemoteConnectionAuto 直接传凭据"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取 sh_cmd 方法
        m = re.search(
            r'def\s+sh_cmd\s*\(\s*self\s*\)\s*:(.*?)(?=\n    def\s|\n    @|\nclass\s|\Z)',
            content, re.DOTALL,
        )
        assert m, "未找到 sh_cmd 方法"
        body = m.group(1)
        assert 'get_ssh_connection' in body, \
            "sh_cmd 应使用 get_ssh_connection (通过 sys_user 关联 t_sys_user)"
        assert 'RemoteConnectionAuto' not in body, \
            "sh_cmd 不应再使用 RemoteConnectionAuto (访问 t_host 不存在的字段)"

    def test_sh_cmd_no_host_dict_password_access(self):
        """sh_cmd 不应访问 host_dict['host_password']"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        m = re.search(
            r'def\s+sh_cmd\s*\(\s*self\s*\)\s*:(.*?)(?=\n    def\s|\n    @|\nclass\s|\Z)',
            content, re.DOTALL,
        )
        body = m.group(1)
        # 过滤注释行, 避免修复说明中的 host_dict 字样误判
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        assert "host_dict['host_password']" not in code_body, \
            "sh_cmd 不应访问 host_dict['host_password'] (t_host 表无此字段)"
        assert "host_dict['host_user']" not in code_body, \
            "sh_cmd 不应访问 host_dict['host_user'] (t_host 表无此字段)"

    def test_server_cmd_has_sys_user(self):
        """ServerCmd.__init__ 应获取 sys_user 参数"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取 ServerCmd 类体 (到下一个 class 为止) - 兼容继承写法 ServerCmd(CzToolsLog)
        m = re.search(
            r'class\s+ServerCmd\s*(?:\([^)]*\))?\s*:(.*?)(?=\nclass\s|\Z)',
            content, re.DOTALL,
        )
        assert m, "未找到 ServerCmd 类"
        body = m.group(1)
        # 在类体中找 __init__ 方法
        init_m = re.search(r'def\s+__init__\s*\([^)]*\)\s*:(.*?)(?=\n    def\s|\n    @|\Z)', body, re.DOTALL)
        assert init_m, "未找到 ServerCmd.__init__"
        init_body = init_m.group(1)
        assert 'sys_user' in init_body, \
            "ServerCmd.__init__ 应获取 sys_user 参数 (用于 get_ssh_connection)"


class TestRev25H3ScriptAuditFullRead:
    """REV25-H3: ServerScript 内容审计应全文读取 (原只读 8192 字节可绕过)"""

    def test_script_audit_reads_full_file(self):
        """sh_script 内容审计不应只读 8192 字节"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取 sh_script 方法
        m = re.search(
            r'def\s+sh_script\s*\(\s*self\s*\)\s*:(.*?)(?=\n    def\s|\n    @|\nclass\s|\Z)',
            content, re.DOTALL,
        )
        assert m, "未找到 sh_script 方法"
        body = m.group(1)
        # 过滤注释行, 避免修复说明中 'read(8192)' 字样误判
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        # 不应再有 read(8192) 限制
        assert 'read(8192)' not in code_body, \
            "sh_script 审计不应只读 8192 字节 (8193 后可绕过)"
        # 应改为全文读取 (read() 或 read(self._MAX_SCRIPT_SIZE))
        assert 'read()' in code_body or 'read(self._MAX_SCRIPT_SIZE' in code_body, \
            "sh_script 审计应全文读取 (read() 或 read(self._MAX_SCRIPT_SIZE))"


class TestRev25H4ScriptPathShlexQuote:
    """REV25-H4: batch service 对生成的远端路径应用 shlex.quote"""

    def test_sh_script_uses_shlex_quote(self):
        """执行服务中的解释器和清理命令都复用经过 quote 的路径。"""
        with open(os.path.join(ROOT, 'app', 'assets', 'batch_service.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'import shlex' in content, "应 import shlex"
        assert 'shlex.quote' in content, \
            "批量脚本服务应使用 shlex.quote 包装生成的远端路径"


class TestRev25MEDBatchFixes:
    """REV25 MED 批量修复 (M1-M5)"""

    def _extract_class_body(self, content, class_name):
        """提取类体到下一个 class"""
        m = re.search(r'class\s+' + class_name + r'\s*\(', content)
        if not m:
            return None
        start = m.start()
        end_match = re.search(r'\nclass\s', content[start:])
        return content[start:start + end_match.start()] if end_match else content[start:]

    def _extract_method_body(self, content, method_name):
        """提取方法体到下一个 def/@/class"""
        m = re.search(r'def\s+' + method_name + r'\s*\(\s*self\s*\)\s*:', content)
        if not m:
            return None
        start = m.end()
        end_match = re.search(r'\n    def\s|\n    @|\nclass\s', content[start:])
        return content[start:start + end_match.start()] if end_match else content[start:]

    def test_m1_server_list_page_validates_int(self):
        """M1: server_list_page 应校验 page/limit 为数字"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_method_body(content, 'server_list_page')
        assert body, "未找到 server_list_page"
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        assert 'TypeError' in code_body or 'ValueError' in code_body, \
            "server_list_page 应捕获 TypeError/ValueError (M1)"

    def test_m2_server_update_validates_id(self):
        """M2: ServerUpdate.update 应校验 id 为数字"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_class_body(content, 'ServerUpdate')
        assert body, "未找到 ServerUpdate 类"
        assert 'int(self.id)' in body, \
            "ServerUpdate 应校验 int(self.id) (M2)"

    def test_m3_server_group_del_checks_hosts(self):
        """M3: ServerGroupDel 应检查组内主机, 有主机时拒绝删除"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerGroup.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_class_body(content, 'ServerGroupDel')
        assert body, "未找到 ServerGroupDel 类"
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        assert 'if query_host:' in code_body, \
            "ServerGroupDel 应检查 query_host 是否为空 (M3)"
        assert '请先转移' in body, \
            "ServerGroupDel 应提示 '请先转移' (M3)"

    def test_m4_server_group_update_rollback(self):
        """M4: ServerGroupUpdate 应有 rollback 保护"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerGroup.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_class_body(content, 'ServerGroupUpdate')
        assert body, "未找到 ServerGroupUpdate 类"
        assert 'db.session.rollback()' in body, \
            "ServerGroupUpdate 应有 db.session.rollback() (M4)"

    def test_m5_server_list_cmd_batch_limit(self):
        """M5: ServerListCmd 应限制批量主机数"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        assert '_MAX_BATCH_COUNT' in content, \
            "应定义 _MAX_BATCH_COUNT 常量 (M5/L7)"
        body = self._extract_class_body(content, 'ServerListCmd')
        assert body, "未找到 ServerListCmd 类"
        assert '_MAX_BATCH_COUNT' in body, \
            "ServerListCmd 应检查 _MAX_BATCH_COUNT (M5)"


class TestRev25LOWBatchFixes:
    """REV25 LOW 批量修复 (L1-L6)"""

    def _extract_class_body(self, content, class_name):
        """提取类体到下一个 class"""
        m = re.search(r'class\s+' + class_name + r'\s*\(', content)
        if not m:
            return None
        start = m.start()
        end_match = re.search(r'\nclass\s', content[start:])
        return content[start:start + end_match.start()] if end_match else content[start:]

    def _extract_method_body(self, content, method_name):
        """提取方法体到下一个 def/@/class"""
        m = re.search(r'def\s+' + method_name + r'\s*\(\s*self\s*\)\s*:', content)
        if not m:
            return None
        start = m.end()
        end_match = re.search(r'\n    def\s|\n    @|\nclass\s', content[start:])
        return content[start:start + end_match.start()] if end_match else content[start:]

    def test_l1_sys_user_name_list_token_check(self):
        """L1: SysUserList.sys_user_name_list 应判空 user_token"""
        with open(os.path.join(ROOT, 'app', 'assets', 'SysUser.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_method_body(content, 'sys_user_name_list')
        assert body, "未找到 sys_user_name_list 方法"
        assert 'if user_token' in body or 'if not user_token' in body, \
            "sys_user_name_list 应判空 user_token (L1)"
        assert 'if not name' in body, \
            "sys_user_name_list 应判空 name 返回错误 (L1)"

    def test_l2_group_name_list_token_check(self):
        """L2: ServerGroupList.group_name_list 应判空 user_token"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerGroup.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_method_body(content, 'group_name_list')
        assert body, "未找到 group_name_list 方法"
        assert 'if user_token' in body or 'if not user_token' in body, \
            "group_name_list 应判空 user_token (L2)"
        assert 'if not name' in body, \
            "group_name_list 应判空 name 返回错误 (L2)"

    def test_l3_server_list_id_validation(self):
        """L3: ServerList.server_list 应校验 host_id 为数字"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_method_body(content, 'server_list')
        assert body, "未找到 server_list 方法"
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        assert 'int(host_id)' in code_body, \
            "server_list 应校验 int(host_id) (L3)"
        assert 'invalid id parameter' in code_body, \
            "server_list 应返回 invalid id parameter 错误 (L3)"

    def test_l3_server_list_alias_validation(self):
        """L3: ServerList.server_list 应校验 host_alias 格式"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_method_body(content, 'server_list')
        assert body, "未找到 server_list 方法"
        assert '_HOST_ALIAS_RE' in body, \
            "server_list 应用 _HOST_ALIAS_RE 校验 host_alias (L3)"

    def test_l4_server_del_ip_validation(self):
        """L4: ServerDel.host_del 应校验 host_ip IP 格式"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerManagement.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_class_body(content, 'ServerDel')
        assert body, "未找到 ServerDel 类"
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        assert 'ipaddress.ip_address' in code_body, \
            "ServerDel.host_del 应用 ipaddress.ip_address 校验 host_ip (L4)"

    def test_l5_group_del_name_check(self):
        """L5: ServerGroupDel.host_del 应校验 name 非空"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerGroup.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_class_body(content, 'ServerGroupDel')
        assert body, "未找到 ServerGroupDel 类"
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        assert 'not isinstance' in code_body or 'not self.name' in code_body, \
            "ServerGroupDel.host_del 应校验 name 类型/非空 (L5)"
        assert 'invalid group name' in code_body, \
            "ServerGroupDel.host_del 应返回 invalid group name 错误 (L5)"

    def test_l6_group_update_id_nums_check(self):
        """L6: ServerGroupUpdate.update 应校验 id/nums 为数字"""
        with open(os.path.join(ROOT, 'app', 'assets', 'ServerGroup.py'), 'r', encoding='utf-8') as f:
            content = f.read()
        body = self._extract_class_body(content, 'ServerGroupUpdate')
        assert body, "未找到 ServerGroupUpdate 类"
        code_lines = [l for l in body.split('\n') if not l.strip().startswith('#')]
        code_body = '\n'.join(code_lines)
        assert 'int(self.id)' in code_body, \
            "ServerGroupUpdate.update 应校验 int(self.id) (L6)"
        assert 'int(self.nums)' in code_body, \
            "ServerGroupUpdate.update 应校验 int(self.nums) (L6)"
