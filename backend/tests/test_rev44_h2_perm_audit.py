# -*- coding: utf-8 -*-
"""REV44-H2: auto_update 权限表变更加审计单测.

背景:
- host_group_auth / sys_user_auth / acc_group_auth 修改 t_auth_host_*_group
  / t_auth_host_sys_user 等权限关联表, 之前完全无审计
- 安全相关表变更无追溯 = 安全事故无证据
- 修复: commit 成功后调 _audit_permission_change() 写入 t_cz_log

测试策略:
- helper _audit_permission_change 直接单测 (mock get_current_user + CzToolsLog)
- 三个 auth 方法测试: 验证 commit 后 _audit_permission_change 被调
- 边界: all_auth=None / SqlOpError 时不调 audit
- 隔离: audit 异常不影响主业务 (silent pass, REV44-H4 一致)
"""
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# 1) _audit_permission_change helper 单测
# ============================================================
class TestAuditPermissionChange:
    """REV44-H2: 权限变更审计 helper."""

    def test_01_writes_cz_log_with_correct_fields(self):
        """成功路径: 调 CzToolsLog().host_log 写入 t_cz_log, 字段正确."""
        from app.tools import auto_update as _au

        # mock get_current_user 返回已登录 admin
        mock_ords = MagicMock()
        # mock CzToolsLog 类
        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        # 用 monkeypatch.setattr 替换 (而不是 module patch, 避免破坏其他测试)
        monkey_ords = MagicMock()

        with patch.object(_au, 'Log'):
            with patch('app.tools.at.get_current_user', return_value=(monkey_ords, 'admin_user')):
                with patch('app.tools.audlog.CzToolsLog', mock_log_class, create=True):
                    # 直接调 helper
                    _au._audit_permission_change('host_group', 5)

        # 验证 host_log 被调, 参数正确
        mock_log_instance.host_log.assert_called_once_with(
            'admin_user',
            '权限操作',
            '刷新所有权限',
            'host_group_count=5',
            '成功',
        )

    def test_02_no_audit_when_not_logged_in(self):
        """未登录态 (cz_name 为空) → 不审计 (避免污染 t_cz_log)."""
        from app.tools import auto_update as _au

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_au, 'Log'):
            with patch('app.tools.at.get_current_user', return_value=(MagicMock(), None)):
                with patch('app.tools.audlog.CzToolsLog', mock_log_class, create=True):
                    _au._audit_permission_change('sys_user', 10)

        # CzToolsLog().host_log 不应被调
        mock_log_class.assert_not_called()
        mock_log_instance.host_log.assert_not_called()

    def test_03_silent_on_cztoolslog_exception(self):
        """CzToolsLog 抛错 → silent pass (REV44-H4 一致)."""
        from app.tools import auto_update as _au

        mock_log_class = MagicMock(side_effect=RuntimeError('mock CzToolsLog 失败'))

        with patch.object(_au, 'Log'):
            with patch('app.tools.at.get_current_user', return_value=(MagicMock(), 'admin')):
                with patch('app.tools.audlog.CzToolsLog', mock_log_class, create=True):
                    # 不应抛错
                    _au._audit_permission_change('user_group', 3)

    def test_04_silent_on_get_current_user_exception(self):
        """get_current_user 抛错 → silent pass (Redis 故障不影响主业务)."""
        from app.tools import auto_update as _au

        with patch.object(_au, 'Log'):
            with patch('app.tools.at.get_current_user', side_effect=ConnectionError('Redis down')):
                # 不应抛错
                _au._audit_permission_change('host_group', 0)

    def test_05_count_is_int_in_details(self):
        """count 是 int, 拼成 '<op>_count=<n>' 格式."""
        from app.tools import auto_update as _au

        mock_log_instance = MagicMock()
        mock_log_class = MagicMock(return_value=mock_log_instance)

        with patch.object(_au, 'Log'):
            with patch('app.tools.at.get_current_user', return_value=(MagicMock(), 'admin')):
                with patch('app.tools.audlog.CzToolsLog', mock_log_class, create=True):
                    _au._audit_permission_change('sys_user', 42)

        # 验证 details 字段
        call_args = mock_log_instance.host_log.call_args
        details = call_args[0][3]  # 第 4 个位置参数
        assert details == 'sys_user_count=42', \
            'details 应为 sys_user_count=42, 实际: %r' % details


# ============================================================
# 2) host_group_auth 调审计
# ============================================================
class TestHostGroupAuthAudit:
    """REV44-H2: host_group_auth 成功 commit 后调 audit."""

    def test_01_calls_audit_after_commit(self):
        """host_group_auth commit 成功后调 _audit_permission_change('host_group', N)."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group') as _tg, \
             patch.object(_au, 't_sys_user'), \
             patch.object(_au, 't_acc_group'), \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, 'osql_de') as _od, \
             patch.object(_au, 'db') as _db, \
             patch.object(_au, '_ensure_all_auth_row') as _ear, \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tg.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['g1', 'g2', 'g3']
            mock_auth = MagicMock()
            mock_auth.id = 1
            _ear.return_value = mock_auth

            result = _au.AuthAutoUpdate.host_group_auth()

        assert result is True, '成功路径应返 True'
        # 验证 audit 被调, 参数正确
        _apc.assert_called_once_with('host_group', 3)

    def test_02_no_audit_on_sql_op_error(self):
        """SqlOpError (主业务失败) 时不调 audit."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group') as _tg, \
             patch.object(_au, 't_sys_user'), \
             patch.object(_au, 't_acc_group'), \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, 'osql_de', side_effect=_au.SqlOpError('mock DB 失败')), \
             patch.object(_au, '_ensure_all_auth_row') as _ear, \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tg.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['g1']
            mock_auth = MagicMock()
            mock_auth.id = 1
            _ear.return_value = mock_auth

            result = _au.AuthAutoUpdate.host_group_auth()

        assert result is False, 'SqlOpError 应返 False'
        # audit 不应被调
        _apc.assert_not_called()

    def test_03_no_audit_when_all_auth_none(self):
        """all_auth 为 None (首次部署失败) → 不调 audit (无 commit = 无变更)."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group') as _tg, \
             patch.object(_au, 't_sys_user'), \
             patch.object(_au, 't_acc_group'), \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, '_ensure_all_auth_row', return_value=None), \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tg.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['g1', 'g2']

            result = _au.AuthAutoUpdate.host_group_auth()

        assert result is True, '方法本身返 True (silent-fail)'
        # audit 不应被调
        _apc.assert_not_called()

    def test_04_empty_query_msg_still_audited(self):
        """query_msg 为空 (清空关联表) 仍调 audit (commit 成功了)."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group') as _tg, \
             patch.object(_au, 't_sys_user'), \
             patch.object(_au, 't_acc_group'), \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, 'osql_de'), \
             patch.object(_au, 'db'), \
             patch.object(_au, '_ensure_all_auth_row') as _ear, \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tg.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = []  # 空列表
            mock_auth = MagicMock()
            mock_auth.id = 1
            _ear.return_value = mock_auth

            result = _au.AuthAutoUpdate.host_group_auth()

        assert result is True
        # 即使 count=0 仍审计 (代表清空关联表是有意操作)
        _apc.assert_called_once_with('host_group', 0)

    def test_05_main_business_only_catches_sql_op_error(self):
        """主业务只 catch SqlOpError, 不 broad-catch Exception.

        _audit_permission_change helper 自身已 silent (try/except Exception: pass),
        所以主业务不应再 broad-catch. 此测试防御未来误改成 except Exception.
        """
        import inspect
        from app.tools import auto_update as _au

        for method_name in ('host_group_auth', 'sys_user_auth', 'acc_group_auth'):
            method = getattr(_au.AuthAutoUpdate, method_name)
            src = inspect.getsource(method)
            assert 'except SqlOpError' in src, \
                '%s 应 catch SqlOpError' % method_name
            assert 'except Exception' not in src, \
                '%s 不应 broad-catch Exception (helper 已 silent)' % method_name


# ============================================================
# 3) sys_user_auth 调审计
# ============================================================
class TestSysUserAuthAudit:
    """REV44-H2: sys_user_auth 成功 commit 后调 audit."""

    def test_01_calls_audit_after_commit(self):
        """sys_user_auth commit 成功后调 _audit_permission_change('sys_user', N)."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group'), \
             patch.object(_au, 't_sys_user') as _tsu, \
             patch.object(_au, 't_acc_group'), \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, 'osql_de'), \
             patch.object(_au, 'db'), \
             patch.object(_au, '_ensure_all_auth_row') as _ear, \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tsu.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['root', 'web', 'dev']  # sys_user aliases
            mock_auth = MagicMock()
            mock_auth.id = 1
            _ear.return_value = mock_auth

            result = _au.AuthAutoUpdate.sys_user_auth()

        assert result is True
        _apc.assert_called_once_with('sys_user', 3)

    def test_02_no_audit_on_sql_op_error(self):
        """SqlOpError 时不调 audit."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group'), \
             patch.object(_au, 't_sys_user') as _tsu, \
             patch.object(_au, 't_acc_group'), \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, 'osql_de', side_effect=_au.SqlOpError('mock DB 失败')), \
             patch.object(_au, '_ensure_all_auth_row') as _ear, \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tsu.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['root']
            mock_auth = MagicMock()
            mock_auth.id = 1
            _ear.return_value = mock_auth

            result = _au.AuthAutoUpdate.sys_user_auth()

        assert result is False
        _apc.assert_not_called()

    def test_03_no_audit_when_all_auth_none(self):
        """all_auth 为 None → 不调 audit."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group'), \
             patch.object(_au, 't_sys_user') as _tsu, \
             patch.object(_au, 't_acc_group'), \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, '_ensure_all_auth_row', return_value=None), \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tsu.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['root']

            result = _au.AuthAutoUpdate.sys_user_auth()

        assert result is True
        _apc.assert_not_called()


# ============================================================
# 4) acc_group_auth 调审计
# ============================================================
class TestAccGroupAuthAudit:
    """REV44-H2: acc_group_auth 成功 commit 后调 audit."""

    def test_01_calls_audit_after_commit(self):
        """acc_group_auth commit 成功后调 _audit_permission_change('user_group', N)."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group'), \
             patch.object(_au, 't_sys_user'), \
             patch.object(_au, 't_acc_group') as _tag, \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, 'osql_de'), \
             patch.object(_au, 'db'), \
             patch.object(_au, '_ensure_all_auth_row') as _ear, \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tag.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['admins', 'users', 'guests']
            mock_auth = MagicMock()
            mock_auth.id = 1
            _ear.return_value = mock_auth

            result = _au.AuthAutoUpdate.acc_group_auth()

        assert result is True
        _apc.assert_called_once_with('user_group', 3)

    def test_02_no_audit_on_sql_op_error(self):
        """SqlOpError 时不调 audit."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group'), \
             patch.object(_au, 't_sys_user'), \
             patch.object(_au, 't_acc_group') as _tag, \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, 'osql_de', side_effect=_au.SqlOpError('mock DB 失败')), \
             patch.object(_au, '_ensure_all_auth_row') as _ear, \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tag.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['admins']
            mock_auth = MagicMock()
            mock_auth.id = 1
            _ear.return_value = mock_auth

            result = _au.AuthAutoUpdate.acc_group_auth()

        assert result is False
        _apc.assert_not_called()

    def test_03_no_audit_when_all_auth_none(self):
        """all_auth 为 None → 不调 audit."""
        from app.tools import auto_update as _au

        with patch.object(_au, 't_group'), \
             patch.object(_au, 't_sys_user'), \
             patch.object(_au, 't_acc_group') as _tag, \
             patch.object(_au, 'ListTool') as _LT, \
             patch.object(_au, '_ensure_all_auth_row', return_value=None), \
             patch.object(_au, '_audit_permission_change') as _apc, \
             patch.object(_au, 'Log'):
            _tag.query.with_entities.return_value.all.return_value = []
            _LT.list_gather.return_value = ['admins']

            result = _au.AuthAutoUpdate.acc_group_auth()

        assert result is True
        _apc.assert_not_called()


# ============================================================
# 5) 静态分析: auto_update.py 必含审计逻辑
# ============================================================
class TestAuditStaticAnalysis:
    """REV44-H2: 静态分析 auto_update.py 含审计修复."""

    def _read_source(self):
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', 'app', 'tools', 'auto_update.py',
        )
        with open(src_path, encoding='utf-8') as f:
            return f.read()

    def test_01_audit_helper_exists(self):
        """auto_update.py 必含 _audit_permission_change helper."""
        src = self._read_source()
        assert 'def _audit_permission_change' in src, \
            'auto_update.py 应有 _audit_permission_change helper'

    def test_02_host_group_auth_calls_audit(self):
        """host_group_auth 必调 _audit_permission_change."""
        src = self._read_source()
        # 找 host_group_auth 函数体
        import re
        m = re.search(r'def\s+host_group_auth[^:]*:\s*([\s\S]*?)(?=\n    @|\nclass\s|\n\ndef\s|\Z)', src)
        assert m, 'host_group_auth 应存在'
        body = m.group(1)
        assert '_audit_permission_change(\'host_group\'' in body, \
            'host_group_auth 应调 _audit_permission_change(\'host_group\', ...)'

    def test_03_sys_user_auth_calls_audit(self):
        """sys_user_auth 必调 _audit_permission_change."""
        src = self._read_source()
        import re
        m = re.search(r'def\s+sys_user_auth[^:]*:\s*([\s\S]*?)(?=\n    @|\nclass\s|\n\ndef\s|\Z)', src)
        assert m
        body = m.group(1)
        assert '_audit_permission_change(\'sys_user\'' in body

    def test_04_acc_group_auth_calls_audit(self):
        """acc_group_auth 必调 _audit_permission_change."""
        src = self._read_source()
        import re
        m = re.search(r'def\s+acc_group_auth[^:]*:\s*([\s\S]*?)(?=\n    @|\nclass\s|\n\ndef\s|\Z)', src)
        assert m
        body = m.group(1)
        assert '_audit_permission_change(\'user_group\'' in body

    def test_05_rev44_h2_marker_exists(self):
        """auto_update.py 必含 REV44-H2 标记."""
        src = self._read_source()
        assert 'REV44-H2' in src

    def test_06_audit_uses_cztoolslog(self):
        """_audit_permission_change 必须用 CzToolsLog 写入 t_cz_log."""
        src = self._read_source()
        import re
        m = re.search(r'def\s+_audit_permission_change[^:]*:\s*([\s\S]*?)(?=\ndef\s|\nclass\s|\Z)', src)
        assert m
        body = m.group(1)
        assert 'CzToolsLog' in body, 'helper 应用 CzToolsLog'
        assert '权限操作' in body, 'helper 应写 log_type=权限操作'
        assert '刷新所有权限' in body, 'helper 应写 log_info=刷新所有权限'

    def test_07_audit_silent_on_exception(self):
        """_audit_permission_change 必须 try/except silent pass."""
        src = self._read_source()
        import re
        m = re.search(r'def\s+_audit_permission_change[^:]*:\s*([\s\S]*?)(?=\ndef\s|\nclass\s|\Z)', src)
        assert m
        body = m.group(1)
        assert 'except Exception' in body, 'helper 必须 except Exception'
        assert 'pass' in body, 'helper 必须 silent pass (不阻断主业务)'

    def test_08_audit_only_on_commit_success(self):
        """_audit_permission_change 必须在 commit 之后调用 (审计实际变更)."""
        src = self._read_source()
        # 验证三个 auth 方法中 _audit_permission_change 都在 db.session.commit() 之后
        for method_name in ('host_group_auth', 'sys_user_auth', 'acc_group_auth'):
            import re
            m = re.search(r'def\s+' + method_name + r'[^:]*:\s*([\s\S]*?)(?=\n    @|\nclass\s|\n\ndef\s|\Z)', src)
            assert m, '%s 应存在' % method_name
            body = m.group(1)
            commit_pos = body.find('db.session.commit()')
            audit_pos = body.find('_audit_permission_change')
            assert commit_pos > 0, '%s 应有 commit' % method_name
            assert audit_pos > 0, '%s 应有 audit' % method_name
            assert audit_pos > commit_pos, \
                '%s 的 audit 必须在 commit 之后 (确保审计实际发生的变更)' % method_name


# ============================================================
# 6) 集成: 真实三个 auth 方法走完整路径
# ============================================================
class TestAuditIntegration:
    """REV44-H2: 端到端验证三个 auth 方法都走 audit."""

    def test_01_all_three_methods_have_audit(self):
        """三个 auth 方法都包含 _audit_permission_change 调用."""
        import inspect
        from app.tools import auto_update as _au

        for method_name in ('host_group_auth', 'sys_user_auth', 'acc_group_auth'):
            method = getattr(_au.AuthAutoUpdate, method_name)
            src = inspect.getsource(method)
            assert '_audit_permission_change' in src, \
                '%s 应调 _audit_permission_change' % method_name