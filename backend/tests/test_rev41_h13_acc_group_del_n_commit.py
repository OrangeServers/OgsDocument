# -*- coding: utf-8 -*-
"""REV41-H13 (R2-11) 修复单测: AccGroupDel.host_del 走 osql_up + osql_de + SqlOpError 兜底.

H12 已修 (set group=NULL 替代级联删 user).
H13 新增: 走 osql_up / osql_de 统一封装, 失败 SqlOpError → rollback + 审计失败 + Log.error.

背景:
- 旧实现裸 db.session.commit(), 无 rollback, 失败时污染 session;
  半途失败还会留下"users 已解绑但 group 还在"的不一致状态.
- 新实现: set group=NULL → osql_up; delete group → osql_de;
          任何一步失败 → SqlOpError → 兜底失败审计 + Log.logger.error.
"""
from unittest.mock import MagicMock, patch

import importlib

import pytest


@pytest.fixture
def _reload_insert():
    """还原 conftest autouse cron_scheduler_skip 对 insert 模块的 lambda 干扰.

    背景: conftest.py line 287-294 用 monkeypatch.setattr 把 app.core.db.insert
    的 osql_in / osql_up 替换为 lambda, 导致 is 比较失败 + MagicMock 计数污染.
    修复: 在测试中显式 reload insert 模块, 还原真实函数.
    """
    import app.core.db.insert as _insert_mod
    importlib.reload(_insert_mod)
    yield _insert_mod
    # 测试结束恢复 (供后续测试 reload 不会被破坏)
    importlib.reload(_insert_mod)


# =============================================================================
# TestHostDelUsesOsql: 核心验证 - 走 osql_up + osql_de, 不走裸 commit
# =============================================================================
class TestHostDelUsesOsql:
    """R2-11 核心: host_del 必须走 osql_up + osql_de, 不调 db.session.commit/delete."""

    def test_host_del_calls_osql_up_with_group_none(self, monkeypatch):
        """验证: set group=NULL 走 osql_up, 不走裸 query.update."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            user_chk = MagicMock()
            user_chk.name = 'dev'

            osql_up_calls = []

            def fake_osql_up(types, filter_by, values):
                osql_up_calls.append((types, filter_by, values))
                return 1

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('name') == 'dev' and 'group' not in kwargs:
                    f.first.return_value = user_chk
                    f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)

            # REV47-M6: 只 mock osql_up, 不再 mock osql_de (group.py 已移除 osql_de 引用)
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del
            body = resp.get_json()

            assert body['code'] == 0, f"删除成功应 code=0, 实际 {body}"

            # R2-11 核心断言: 必须调用 osql_up('t_acc_user', {'group': 'dev', 'is_deleted': False}, {'group': None})
            # REV47-M6: filter_by 多加 is_deleted=False 参数, 用 .get() 兼容
            assert any(
                t == 't_acc_user' and fb.get('group') == 'dev' and v == {'group': None}
                for t, fb, v in osql_up_calls
            ), f"应调用 osql_up('t_acc_user', {{'group': 'dev'}}, {{'group': None}}), 实际: {osql_up_calls}"

    def test_host_del_soft_deletes_via_osql_up(self, monkeypatch):
        """REV47-M6: delete group 走 osql_up(is_deleted=True) 软删, 不走 osql_de / db.session.delete.

        R2-11 (REV41-H13) 旧实现用 osql_de 物理删除;  REV47-M6 软删改造后改用 osql_up.
        """
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'qa',
        }):
            user_chk = MagicMock()
            user_chk.name = 'qa'

            osql_up_calls = []

            def fake_osql_up(types, filter_by, values):
                osql_up_calls.append((types, filter_by, values))
                return 1

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('name') == 'qa':
                    f.first.return_value = user_chk
                    f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)

            # REV47-M6: 只 mock osql_up, 不再 mock osql_de
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del

            assert resp.get_json()['code'] == 0
            # REV47-M6 软删断言: 必须调用 osql_up('t_acc_group', {'name': 'qa'}, {'is_deleted': True})
            # 替代 R2-11 的 osql_de('t_acc_group', {'name': 'qa'}) 物理删除
            assert any(
                t == 't_acc_group' and fb == {'name': 'qa'} and v == {'is_deleted': True}
                for t, fb, v in osql_up_calls
            ), \
                f"REV47-M6: 应软删 osql_up('t_acc_group', {{'name': 'qa'}}, {{'is_deleted': True}}), 实际: {osql_up_calls}"

    def test_host_del_does_not_call_db_session_commit_directly(self, monkeypatch):
        """验证: host_del 源码不直接调用 db.session.commit / db.session.delete.

        理由: 真实 commit 必须在 osql_up/osql_de 内部, 这样失败时能 rollback.
        通过 inspect.getsource 检查 host_del 函数源码, 确保不出现裸 commit/delete.
        """
        import inspect
        from app.users.group import AccGroupDel
        source = inspect.getsource(AccGroupDel.host_del.fget)

        # R2-11 核心断言: host_del 源码不能直接调用 db.session.commit / db.session.delete
        assert 'db.session.commit' not in source, \
            "R2-11 修复: host_del 不应直接调用 db.session.commit (commit 应在 osql_up/osql_de 内部)"
        assert 'db.session.delete' not in source, \
            "R2-11 修复: host_del 不应直接调用 db.session.delete (delete 应走 osql_de)"

    def test_host_del_does_not_use_bare_query_update(self, monkeypatch):
        """验证: t_acc_user.query.filter_by().update() 不应被直接调用 (走 osql_up)."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            user_chk = MagicMock()
            user_chk.name = 'dev'

            # 记录裸 query.update 调用
            bare_update_calls = []

            def fake_osql_up(types, filter_by, values):
                return 1

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('name') == 'dev' and 'group' not in kwargs:
                    f.first.return_value = user_chk
                # 关键: 记录裸 update 调用
                if 'group' in kwargs:
                    def _capture_update(payload):
                        bare_update_calls.append(('t_acc_user_update', kwargs, payload))
                        return 1
                    f.update.side_effect = _capture_update
                else:
                    f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)

            # REV47-M6: 不再 mock osql_de
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del

            assert resp.get_json()['code'] == 0
            # R2-11 核心断言: t_acc_user.query.filter_by(group=...).update() 不应被直接调用
            t_acc_user_updates = [
                c for c in bare_update_calls if c[0] == 't_acc_user_update'
            ]
            assert t_acc_user_updates == [], \
                f"应走 osql_up 而非裸 t_acc_user.query.filter_by().update(), 实际: {t_acc_user_updates}"


# =============================================================================
# TestHostDelSqlOpErrorHandling: SqlOpError 兜底 - 失败审计 + Log.error
# =============================================================================
class TestHostDelSqlOpErrorHandling:
    """R2-11 失败兜底: SqlOpError → 失败审计 + Log.logger.error + code=100."""

    def test_osql_up_raises_sql_op_error_returns_100(self, monkeypatch):
        """osql_up 抛 SqlOpError → 返回 code=100 + 失败审计 + Log.error."""
        from app.users import group as _group_mod
        from app.core.db.insert import SqlOpError
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            user_chk = MagicMock()
            user_chk.name = 'dev'

            def fake_osql_up(types, filter_by, values):
                raise SqlOpError('数据冲突: FK violated')

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = user_chk
                f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            # 记录 host_log + Log.logger.error 调用
            host_log_calls = []
            monkeypatch.setattr(
                _group_mod.CzToolsLog, 'host_log',
                lambda self, *args: host_log_calls.append(args)
            )

            with patch.object(_group_mod.Log, 'logger') as mock_logger:
                del_op = _group_mod.AccGroupDel()
                resp = del_op.host_del
                body = resp.get_json()

                # R2-11 核心断言 1: 返回 code=100
                assert body['code'] == 100, f"应 code=100, 实际 {body}"

                # R2-11 核心断言 2: 调用 Log.logger.error
                mock_logger.error.assert_called()
                error_msg = str(mock_logger.error.call_args)
                assert 'R2-11' in error_msg or 'AccGroupDel' in error_msg, \
                    f"Log.error 应含 R2-11/AccGroupDel 标记, 实际: {error_msg}"

                # R2-11 核心断言 3: 记失败审计
                assert len(host_log_calls) >= 1, "应记失败审计"
                fail_call = host_log_calls[0]
                # 失败审计: 第 4 个位置参数为 '失败'
                assert '失败' in fail_call, \
                    f"应记失败审计, 实际: {fail_call}"

    def test_osql_up_soft_delete_raises_sql_op_error_returns_100(self, monkeypatch):
        """REV47-M6: 软删步骤 osql_up(is_deleted=True) 抛 SqlOpError → 返回 code=100 + 失败审计.

        R2-11 旧实现: osql_de 抛 SqlOpError; REV47-M6 后改 osql_up 抛 SqlOpError.
        注意: 此时 osql_up(set group=NULL) 已成功, 是软删失败, 仍按 R2-11 兜底处理.
        """
        from app.users import group as _group_mod
        from app.core.db.insert import SqlOpError
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            user_chk = MagicMock()
            user_chk.name = 'dev'

            def fake_osql_up(types, filter_by, values):
                # REV47-M6 软删步骤失败 (第 2 次 osql_up, is_deleted=True)
                if types == 't_acc_group':
                    raise SqlOpError('软删失败: integrity error')
                return 1  # 第 1 次 set group=NULL 成功

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = user_chk
                f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            host_log_calls = []
            monkeypatch.setattr(
                _group_mod.CzToolsLog, 'host_log',
                lambda self, *args: host_log_calls.append(args)
            )

            with patch.object(_group_mod.Log, 'logger') as mock_logger:
                del_op = _group_mod.AccGroupDel()
                resp = del_op.host_del
                body = resp.get_json()

                # R2-11 兜底断言 (不变): 返回 code=100
                assert body['code'] == 100, f"应 code=100, 实际 {body}"

                # Log.error 被调用
                mock_logger.error.assert_called()
                # 失败审计被记
                assert any('失败' in c for c in host_log_calls), \
                    f"应记失败审计, 实际: {host_log_calls}"


# =============================================================================
# TestHostDelSuccess: 成功路径 - 成功审计 + acc_group_auth 调用
# =============================================================================
class TestHostDelSuccess:
    """R2-11 成功路径: code=0 + 成功审计 + AuthAutoUpdate.acc_group_auth()."""

    def test_host_del_success_logs_success_audit(self, monkeypatch):
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            user_chk = MagicMock()
            user_chk.name = 'dev'

            def fake_osql_up(types, filter_by, values):
                return 5

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = user_chk
                f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            host_log_calls = []
            monkeypatch.setattr(
                _group_mod.CzToolsLog, 'host_log',
                lambda self, *args: host_log_calls.append(args)
            )

            mock_auto_update = MagicMock()
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', mock_auto_update)

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del
            body = resp.get_json()

            assert body['code'] == 0
            # 成功审计
            assert any('成功' in c for c in host_log_calls), \
                f"应记成功审计, 实际: {host_log_calls}"
            # AuthAutoUpdate.acc_group_auth 被调用
            mock_auto_update.acc_group_auth.assert_called_once()

    def test_host_del_does_not_log_failure_on_success(self, monkeypatch):
        """成功时不应记失败审计."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            user_chk = MagicMock()
            user_chk.name = 'dev'

            def fake_osql_up(types, filter_by, values):
                return 1

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = user_chk
                f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            host_log_calls = []
            monkeypatch.setattr(
                _group_mod.CzToolsLog, 'host_log',
                lambda self, *args: host_log_calls.append(args)
            )

            with patch.object(_group_mod.Log, 'logger') as mock_logger:
                del_op = _group_mod.AccGroupDel()
                resp = del_op.host_del
                assert resp.get_json()['code'] == 0
                # 成功时不应调 Log.logger.error
                mock_logger.error.assert_not_called()
                # 不应有失败审计
                fail_logs = [c for c in host_log_calls if '失败' in c]
                assert fail_logs == [], f"成功时不应记失败审计, 实际: {fail_logs}"


# =============================================================================
# TestImportsAndR2Marker: 模块导入 + 注释标记
# =============================================================================
class TestImportsAndR2Marker:
    """R2-11 修复必须显式 import osql_up/osql_de/SqlOpError + 注释标记."""

    def test_group_module_imports_osql_up(self, _reload_insert):
        """group.py 必须从 app.core.db.insert 导入 osql_up."""
        importlib.reload(_reload_insert)  # 还原真实函数 (避免 conftest lambda 干扰)
        import app.users.group as _group_mod
        importlib.reload(_group_mod)
        from app.core.db import insert as _insert_mod
        # group 模块应有 osql_up
        assert hasattr(_group_mod, 'osql_up'), \
            "R2-11 修复: group.py 必须 import osql_up (用于 set group=NULL)"
        # 是从 insert 模块导的 (用 __module__ 避免 is 比较失败)
        assert getattr(_group_mod.osql_up, '__module__', '') == 'app.core.db.insert', \
            f"R2-11: osql_up 应来自 app.core.db.insert, 实际来自 {getattr(_group_mod.osql_up, '__module__', 'unknown')!r}"

    def test_group_module_no_longer_imports_osql_de(self, _reload_insert):
        """REV47-M6: group.py 不应再 import osql_de (改用 osql_up 软删).

        R2-11 (REV41-H13) 旧实现用 osql_de 物理删除; REV47-M6 软删后改用 osql_up.
        这条断言确保软删改造被落实 (没有遗漏的 osql_de 引用).
        """
        importlib.reload(_reload_insert)
        import app.users.group as _group_mod
        importlib.reload(_group_mod)
        # REV47-M6 软删: group.py 不应再引用 osql_de
        # (用 hasattr 检查, 因为 importlib.reload 后模块属性可能仍残留)
        assert not hasattr(_group_mod, 'osql_de'), \
            "REV47-M6 软删改造: group.py 不应再 import osql_de (改用 osql_up is_deleted=True)"

    def test_group_module_imports_sql_op_error(self, _reload_insert):
        """group.py 必须从 app.core.db.insert 导入 SqlOpError."""
        importlib.reload(_reload_insert)
        import app.users.group as _group_mod
        importlib.reload(_group_mod)
        assert hasattr(_group_mod, 'SqlOpError'), \
            "R2-11 修复: group.py 必须 import SqlOpError (用于 except 兜底)"
        assert getattr(_group_mod.SqlOpError, '__module__', '') == 'app.core.db.insert', \
            f"R2-11: SqlOpError 应来自 app.core.db.insert, 实际来自 {getattr(_group_mod.SqlOpError, '__module__', 'unknown')!r}"

    def test_group_module_has_rev41_h13_marker(self):
        """group.py 必须有 R2-11 / REV41-H13 注释标记."""
        import inspect
        from app.users import group as _group_mod
        source = inspect.getsource(_group_mod)
        assert 'R2-11' in source, "group.py 必须有 R2-11 标记注释"
        assert 'REV41-H13' in source, "group.py 必须有 REV41-H13 标记注释"


# =============================================================================
# TestGroupNotFound: 边界 - 组不存在时返回 100
# =============================================================================
class TestGroupNotFound:
    """R2-11 边界: 组名不存在时返回 code=100, 不调 osql_up/osql_de."""

    def test_group_not_found_returns_100_without_osql_calls(self, monkeypatch):
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'nonexistent',
        }):
            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = None  # 组不存在
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)

            osql_up_called = []
            osql_de_called = []

            def fake_osql_up(*a, **kw):
                osql_up_called.append((a, kw))
                return 1

            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            host_log_calls = []
            monkeypatch.setattr(
                _group_mod.CzToolsLog, 'host_log',
                lambda self, *args: host_log_calls.append(args)
            )

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del
            body = resp.get_json()

            # 边界断言: 组不存在时 code=100, 不调 osql_up (REV47-M6 后无 osql_de)
            assert body['code'] == 100, f"组不存在应 code=100, 实际 {body}"
            assert osql_up_called == [], f"组不存在不应调 osql_up, 实际: {osql_up_called}"
            # 失败审计
            assert any('失败' in c for c in host_log_calls), \
                f"应记失败审计, 实际: {host_log_calls}"


# =============================================================================
# TestEndToEnd: 集成 - osql_up → osql_de 顺序
# =============================================================================
class TestEndToEnd:
    """集成验证: osql_up 必须先于 osql_de 调用 (否则 group 删了 user 还没解绑)."""

    def test_osql_up_set_null_called_before_soft_delete(self, monkeypatch):
        """REV47-M6 顺序: 先 osql_up(set group=NULL) → 再 osql_up(soft delete group).

        理由: 如果先软删 group, t_acc_user.group FK 仍指向旧 group 名,
        再 update 会因 FK violation 失败.
        """
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            user_chk = MagicMock()
            user_chk.name = 'dev'

            call_order = []

            def fake_osql_up(types, filter_by, values):
                call_order.append(('osql_up', types, filter_by, values))
                return 1

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = user_chk
                f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del

            assert resp.get_json()['code'] == 0
            # REV47-M6 顺序断言: 找到 t_acc_user set_null 和 t_acc_group soft_delete 两次调用
            up_indices = [
                i for i, c in enumerate(call_order)
                if c[0] == 'osql_up' and c[1] == 't_acc_user'
            ]
            del_indices = [
                i for i, c in enumerate(call_order)
                if c[0] == 'osql_up' and c[1] == 't_acc_group'
            ]
            assert up_indices, f"应至少调一次 osql_up('t_acc_user', ...), 实际: {call_order}"
            assert del_indices, f"应至少调一次 osql_up('t_acc_group', ...), 实际: {call_order}"
            # set_null 必须在 soft_delete 之前
            assert max(up_indices) < min(del_indices), \
                f"osql_up(set group=NULL) 必须在 osql_up(soft delete) 之前 (否则 FK violation), 实际顺序: {call_order}"