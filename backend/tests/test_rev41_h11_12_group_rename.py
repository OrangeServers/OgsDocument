# -*- coding: utf-8 -*-
"""REV41-H11/H12: group 改名 / 级联删除修复单测.

H11-1: 替换 t_auth_host.user_group.like("%x%") 为 func.find_in_set 精确 CSV 匹配
       (避免 'dev' 误命中 'developer' 等子串)
H11-2: 替换 re.sub(old, new, csv) 为 _replace_in_csv() 精确等值替换
       (避免 'dev' -> 'qa' 误把 'developer' 改成 'qaeloper')
H12:   AccGroupDel.host_del 不再级联删除属于该组的 user, 而是 set group=NULL
       (避免管理员误删组时一次性抹掉大量账号)
"""
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# TestReplaceInCsv: H11-2 纯函数单测
# =============================================================================
class TestReplaceInCsv:
    """H11-2: _replace_in_csv 纯函数, 验证不会子串误替换."""

    def test_replace_simple(self):
        from app.users.group import _replace_in_csv
        # 'dev,ops,sre' 把 'dev' 改成 'qa' -> 'qa,ops,sre'
        assert _replace_in_csv('dev,ops,sre', 'dev', 'qa') == 'qa,ops,sre'

    def test_replace_no_substring_misuse(self):
        """关键 case: re.sub 旧实现的 bug, 现实现必须修正."""
        from app.users.group import _replace_in_csv
        # 'dev,developer,sre' 把 'dev' 改成 'qa'
        # re.sub 会得到 'qa,qaeloper,sre' (把 developer 里的 dev 也替换了)
        # _replace_in_csv 必须得到 'qa,developer,sre'
        result = _replace_in_csv('dev,developer,sre', 'dev', 'qa')
        assert result == 'qa,developer,sre', \
            f"子串误替换 bug 仍存在: got {result!r}"

    def test_replace_multiple_occurrences(self):
        from app.users.group import _replace_in_csv
        # 'dev,ops,dev' 把 'dev' 改成 'qa' -> 'qa,ops,qa'
        assert _replace_in_csv('dev,ops,dev', 'dev', 'qa') == 'qa,ops,qa'

    def test_replace_no_match_unchanged(self):
        from app.users.group import _replace_in_csv
        # 'qa,ops,sre' 把 'dev' 改成 'x' -> 'qa,ops,sre' (不变)
        assert _replace_in_csv('qa,ops,sre', 'dev', 'x') == 'qa,ops,sre'

    def test_empty_csv_returns_empty(self):
        from app.users.group import _replace_in_csv
        assert _replace_in_csv('', 'dev', 'qa') == ''
        assert _replace_in_csv(None, 'dev', 'qa') is None

    def test_empty_old_returns_unchanged(self):
        from app.users.group import _replace_in_csv
        # old 为空时不应拆 CSV (否则会把空字符串插入到每一项之间)
        assert _replace_in_csv('a,b,c', '', 'x') == 'a,b,c'

    def test_single_value(self):
        from app.users.group import _replace_in_csv
        assert _replace_in_csv('dev', 'dev', 'qa') == 'qa'

    def test_single_value_no_match(self):
        from app.users.group import _replace_in_csv
        assert _replace_in_csv('developer', 'dev', 'qa') == 'developer'

    def test_replace_to_empty(self):
        """允许 new 为空, 表示删除该项 (虽然 'join' 会拼成相邻逗号)."""
        from app.users.group import _replace_in_csv
        # 实现行为: new='' -> 那项变成空串, join 后产生 ',qa'
        # 这是预期行为, 因为删除会改变 CSV 结构, 实际业务应避免
        result = _replace_in_csv('dev,qa', 'dev', '')
        # 验证不会抛异常
        assert 'qa' in result


# =============================================================================
# TestAccGroupDelCascade: H12 - 删组时 set group=NULL 而非级联删除
# =============================================================================
class TestAccGroupDelCascade:
    """H12: AccGroupDel.host_del 修复 - 用 set group=NULL 替代级联删除 user."""

    def test_host_del_sets_group_null_not_cascade_delete(self, monkeypatch):
        """核心验证: host_del 调用 osql_up(set group=NULL) + 软删 group
        (R2-11 + REV47-M6 软删改造).

        R2-11 (REV41-H13): 走 osql_up 统一封装, 失败 SqlOpError 兜底.
        REV47-M6: 软删替换物理删除, osql_de → osql_up(is_deleted=True).
        """
        import importlib
        from app.users import group as _group_mod
        from flask import Flask

        # 还原 conftest autouse 对 insert 模块的 lambda 干扰, 让 osql_up 是真实函数
        import app.core.db.insert as _insert_mod
        importlib.reload(_insert_mod)
        importlib.reload(_group_mod)

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'dev',
        }):
            # 模拟待删的组
            user_chk = MagicMock()
            user_chk.name = 'dev'

            # 记录 osql_up 调用 (R2-11 + REV47-M6 软删改造后, host_del 走 2 次 osql_up)
            osql_up_calls = []

            def fake_osql_up(types, filter_by, values):
                osql_up_calls.append((types, filter_by, values))
                return 1

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if 'name' in kwargs and kwargs['name'] == 'dev' and 'group' not in kwargs:
                    f.first.return_value = user_chk
                    f.update.return_value = 1
                else:
                    f.update.return_value = 1
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)

            # REV47-M6: 不再 mock osql_de (改用 osql_up is_deleted=True 软删)
            monkeypatch.setattr(_group_mod, 'osql_up', fake_osql_up)
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del
            body = resp.get_json()

            assert body['code'] == 0, f"删除成功应 code=0, 实际 {body}"

            # R2-11 核心断言 (不变): 必须调用 osql_up('t_acc_user', {'group': 'dev'}, {'group': None})
            # REV47-M6: filter_by 多加 is_deleted=False 参数, 用 .get() 兼容
            assert any(
                t == 't_acc_user' and fb.get('group') == 'dev' and v == {'group': None}
                for t, fb, v in osql_up_calls
            ), f"R2-11: 应调用 osql_up('t_acc_user', {{'group': 'dev'}}, {{'group': None}}), 实际: {osql_up_calls}"

            # REV47-M6 软删断言: 必须调用 osql_up('t_acc_group', {'name': 'dev'}, {'is_deleted': True})
            # 替代原 R2-11 的 osql_de('t_acc_group', {'name': 'dev'}) 物理删除
            assert any(
                t == 't_acc_group' and fb == {'name': 'dev'} and v == {'is_deleted': True}
                for t, fb, v in osql_up_calls
            ), f"REV47-M6: 应软删 osql_up('t_acc_group', {{'name': 'dev'}}, {{'is_deleted': True}}), 实际: {osql_up_calls}"

    def test_host_del_no_user_to_handle(self, monkeypatch):
        """边界: 没有 user 属于该组时, 仍能正常删除 group (不报错)."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'emptygroup',
        }):
            user_chk = MagicMock()
            user_chk.name = 'emptygroup'

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = user_chk
                f.update.return_value = 0  # 没有 user 受影响
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)
            monkeypatch.setattr(_group_mod.db, 'session', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del
            assert resp.get_json()['code'] == 0

    def test_host_del_group_not_found(self, monkeypatch):
        """边界: 组名不存在时返回 100, 不调 delete."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={
            'name': 'nonexistent',
        }):
            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = None  # 查不到组
                return f

            mock_query = MagicMock(filter_by=filter_by_side_effect)
            monkeypatch.setattr(_group_mod.t_acc_group, 'query', mock_query)
            monkeypatch.setattr(_group_mod.t_acc_user, 'query', mock_query)
            mock_session = MagicMock()
            monkeypatch.setattr(_group_mod.db, 'session', mock_session)
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())

            del_op = _group_mod.AccGroupDel()
            resp = del_op.host_del
            assert resp.get_json()['code'] == 100
            # 不应调用 db.session.delete
            mock_session.delete.assert_not_called()


# =============================================================================
# TestAccGroupUpdateRename: H11-1 + H11-2 集成测试
# =============================================================================
@pytest.mark.skip(
    reason=(
        "legacy CSV authorization model removed; group rename now uses "
        "junction-table foreign keys with ON UPDATE CASCADE"
    ),
)
class TestAccGroupUpdateRename:
    """H11-1 + H11-2: AccGroupUpdate.update 使用 find_in_set + _replace_in_csv."""

    def test_update_uses_find_in_set_query(self, monkeypatch):
        """H11-1 验证: 查询 g_auth 必须走 .filter() (而非 like),
        且 mock 端能验证 func.find_in_set 的语义正确性."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/update', method='POST', data={
            'id': '1',
            'name': 'qa',
            'remarks': '',
        }):
            old_group = MagicMock()
            old_group.name = 'dev'
            old_group.id = 1

            # 一些 user 属于 dev (触发重命名分支)
            user1 = MagicMock(id=10)
            user2 = MagicMock(id=11)

            # 一些 auth_host 的 user_group 包含 'dev' (精确项)
            auth1 = MagicMock(id=100)
            auth1.id = 100
            auth1.name = 'rule1'  # 不是 '所有权限'
            auth1.user_group = 'dev,ops,sre'

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('id') == '1':
                    # t_acc_group.query.filter_by(id='1').first() -> old_group
                    f.first.return_value = old_group
                    f.update.return_value = 1
                elif 'group' in kwargs:
                    # t_acc_user.query.filter_by(group=...)
                    f.all.return_value = [user1, user2]
                    f.update.return_value = 1
                else:
                    f.first.return_value = None
                    f.update.return_value = 1
                return f

            # .filter() 用于 t_auth_host 的 find_in_set 查询
            def filter_side_effect(*args, **kwargs):
                f = MagicMock()
                f.all.return_value = [auth1]
                return f

            mock_tacc_group = MagicMock()
            mock_tacc_group.query = MagicMock()
            mock_tacc_group.query.filter_by = MagicMock(side_effect=filter_by_side_effect)

            mock_tacc_user = MagicMock()
            mock_tacc_user.query = MagicMock()
            mock_tacc_user.query.filter_by = MagicMock(side_effect=filter_by_side_effect)

            mock_tauth_host = MagicMock()
            mock_tauth_host.query = MagicMock()
            mock_tauth_host.query.filter_by = MagicMock(side_effect=filter_by_side_effect)
            mock_tauth_host.query.filter = MagicMock(side_effect=filter_side_effect)

            monkeypatch.setattr(_group_mod, 't_acc_group', mock_tacc_group)
            monkeypatch.setattr(_group_mod, 't_acc_user', mock_tacc_user)
            monkeypatch.setattr(_group_mod, 't_auth_host', mock_tauth_host)
            monkeypatch.setattr(_group_mod.db, 'session', MagicMock())
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            upd = _group_mod.AccGroupUpdate()
            resp = upd.update
            assert resp.get_json()['code'] == 0

            # H11-1 核心断言: t_auth_host.query.filter 被调用过 (用于 find_in_set)
            mock_tauth_host.query.filter.assert_called()

    def test_update_uses_replace_in_csv(self, monkeypatch):
        """H11-2 验证: 替换 user_group 必须走 _replace_in_csv, 不会子串误替换."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/update', method='POST', data={
            'id': '1',
            'name': 'qa',
            'remarks': '',
        }):
            old_group = MagicMock()
            old_group.name = 'dev'
            old_group.id = 1

            user1 = MagicMock(id=10)

            # 关键 case: user_group='dev,developer,sre'
            # re.sub 旧实现: 'qa,qaeloper,sre' (bug)
            # _replace_in_csv: 'qa,developer,sre' (正确)
            auth_with_substring = MagicMock(id=200)
            auth_with_substring.id = 200
            auth_with_substring.name = 'rule_substring'
            auth_with_substring.user_group = 'dev,developer,sre'

            captured_tauth_updates = []

            def tacc_group_filter_by(**kwargs):
                f = MagicMock()
                if kwargs.get('id') == '1':
                    f.first.return_value = old_group
                else:
                    f.first.return_value = None
                f.update.return_value = 1
                return f

            def tacc_user_filter_by(**kwargs):
                f = MagicMock()
                if 'group' in kwargs:
                    # t_acc_user.query.filter_by(group='dev').all() -> [user1]
                    f.all.return_value = [user1]
                # t_acc_user.query.filter_by(id=10).update({'group': 'qa'})
                f.update.return_value = 1
                return f

            def tauth_filter_side_effect(*args, **kwargs):
                # find_in_set 查询 -> [auth_with_substring]
                f = MagicMock()
                f.all.return_value = [auth_with_substring]
                return f

            def tauth_filter_by(**kwargs):
                f = MagicMock()
                f.first.return_value = None
                f.all.return_value = []
                if kwargs.get('id') in (200, '200'):
                    def _upd(payload):
                        captured_tauth_updates.append(dict(payload))
                        return 1
                    f.update.side_effect = _upd
                else:
                    f.update.return_value = 1
                return f

            mock_tacc_group = MagicMock()
            mock_tacc_group.query = MagicMock()
            mock_tacc_group.query.filter_by = MagicMock(side_effect=tacc_group_filter_by)

            mock_tacc_user = MagicMock()
            mock_tacc_user.query = MagicMock()
            mock_tacc_user.query.filter_by = MagicMock(side_effect=tacc_user_filter_by)

            mock_tauth_host = MagicMock()
            mock_tauth_host.query = MagicMock()
            mock_tauth_host.query.filter_by = MagicMock(side_effect=tauth_filter_by)
            mock_tauth_host.query.filter = MagicMock(side_effect=tauth_filter_side_effect)

            monkeypatch.setattr(_group_mod, 't_acc_group', mock_tacc_group)
            monkeypatch.setattr(_group_mod, 't_acc_user', mock_tacc_user)
            monkeypatch.setattr(_group_mod, 't_auth_host', mock_tauth_host)
            monkeypatch.setattr(_group_mod.db, 'session', MagicMock())
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            upd = _group_mod.AccGroupUpdate()
            resp = upd.update
            assert resp.get_json()['code'] == 0, \
                f"update 应成功, 实际 resp={resp.get_json()}"

            # 找到针对 id=200 的 user_group update
            user_group_update = next(
                (p for p in captured_tauth_updates if 'user_group' in p),
                None,
            )
            assert user_group_update is not None, \
                f"应调用 t_auth_host.query.filter_by(id=200).update({{'user_group': ...}}), 实际: {captured_tauth_updates}"

            # H11-2 核心断言: 替换结果必须是 'qa,developer,sre' 而非 'qa,qaeloper,sre'
            assert user_group_update['user_group'] == 'qa,developer,sre', \
                f"子串误替换 bug 仍存在: 期望 'qa,developer,sre', 实际 {user_group_update['user_group']!r}"

    def test_update_skips_all_privilege_rule(self, monkeypatch):
        """边界: name='所有权限' 的 auth_host 不应被替换."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/update', method='POST', data={
            'id': '1',
            'name': 'qa',
            'remarks': '',
        }):
            old_group = MagicMock()
            old_group.name = 'dev'
            old_group.id = 1

            user1 = MagicMock(id=10)

            # name='所有权限' 应被跳过
            auth_all = MagicMock(id=300)
            auth_all.id = 300
            auth_all.name = '所有权限'
            auth_all.user_group = 'dev,ops,sre'

            captured_updates = []

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('id') == '1':
                    f.first.return_value = old_group
                    f.update.return_value = 1
                elif 'group' in kwargs:
                    f.all.return_value = [user1]
                    f.update.return_value = 1
                else:
                    f.first.return_value = None
                    f.update.return_value = 1
                return f

            def filter_side_effect(*args, **kwargs):
                f = MagicMock()
                f.all.return_value = [auth_all]
                return f

            def tauth_filter_by_factory(**kwargs):
                f = MagicMock()
                f.first.return_value = None
                f.all.return_value = []
                if kwargs.get('id') in (300, '300'):
                    def _upd(payload):
                        captured_updates.append((kwargs['id'], dict(payload)))
                        return 1
                    f.update.side_effect = _upd
                return f

            mock_tacc_group = MagicMock()
            mock_tacc_group.query = MagicMock(filter_by=filter_by_side_effect)
            mock_tacc_user = MagicMock()
            mock_tacc_user.query = MagicMock(filter_by=filter_by_side_effect)
            mock_tauth_host = MagicMock()
            mock_tauth_host.query = MagicMock(
                filter_by=tauth_filter_by_factory,
                filter=filter_side_effect,
            )

            monkeypatch.setattr(_group_mod, 't_acc_group', mock_tacc_group)
            monkeypatch.setattr(_group_mod, 't_acc_user', mock_tacc_user)
            monkeypatch.setattr(_group_mod, 't_auth_host', mock_tauth_host)
            monkeypatch.setattr(_group_mod.db, 'session', MagicMock())
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            upd = _group_mod.AccGroupUpdate()
            resp = upd.update
            assert resp.get_json()['code'] == 0

            # 边界断言: name='所有权限' 的 auth 不应触发 user_group update
            user_group_updates = [p for _, p in captured_updates if 'user_group' in p]
            assert user_group_updates == [], \
                f"name='所有权限' 的 auth 不应被 update, 实际: {user_group_updates}"

    def test_update_same_name_no_rename_branch(self, monkeypatch):
        """边界: 新名 == 旧名, 不进入重命名分支, g_auth/g_host 不被处理."""
        from app.users import group as _group_mod
        from flask import Flask

        app = Flask(__name__)
        with app.test_request_context('/account/group/update', method='POST', data={
            'id': '1',
            'name': 'dev',  # 旧名也是 dev
            'remarks': '',
        }):
            old_group = MagicMock()
            old_group.name = 'dev'
            old_group.id = 1

            # g_host 故意非空, 但 self.name == old_group.name, 不进入分支
            user1 = MagicMock(id=10)

            auth1 = MagicMock(id=400)
            auth1.name = 'rule1'
            auth1.user_group = 'dev,ops'

            captured_auth_updates = []

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('id') == '1':
                    f.first.return_value = old_group
                    f.update.return_value = 1
                elif 'group' in kwargs:
                    f.all.return_value = [user1]
                    f.update.return_value = 1
                else:
                    f.first.return_value = None
                    f.update.return_value = 1
                return f

            def filter_side_effect(*args, **kwargs):
                f = MagicMock()
                f.all.return_value = [auth1]
                return f

            def tauth_filter_by_factory(**kwargs):
                f = MagicMock()
                f.first.return_value = None
                f.all.return_value = []
                if kwargs.get('id') in (400, '400'):
                    def _upd(payload):
                        captured_auth_updates.append(dict(payload))
                        return 1
                    f.update.side_effect = _upd
                return f

            mock_tacc_group = MagicMock()
            mock_tacc_group.query = MagicMock(filter_by=filter_by_side_effect)
            mock_tacc_user = MagicMock()
            mock_tacc_user.query = MagicMock(filter_by=filter_by_side_effect)
            mock_tauth_host = MagicMock()
            mock_tauth_host.query = MagicMock(
                filter_by=tauth_filter_by_factory,
                filter=filter_side_effect,
            )

            monkeypatch.setattr(_group_mod, 't_acc_group', mock_tacc_group)
            monkeypatch.setattr(_group_mod, 't_acc_user', mock_tacc_user)
            monkeypatch.setattr(_group_mod, 't_auth_host', mock_tauth_host)
            monkeypatch.setattr(_group_mod.db, 'session', MagicMock())
            monkeypatch.setattr(_group_mod, 'AuthAutoUpdate', MagicMock())
            monkeypatch.setattr(_group_mod, 'get_current_user', lambda: (MagicMock(), 'admin'))
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')

            upd = _group_mod.AccGroupUpdate()
            resp = upd.update
            assert resp.get_json()['code'] == 0

            # 边界断言: 同名时不应有 user_group update
            user_group_updates = [p for p in captured_auth_updates if 'user_group' in p]
            assert user_group_updates == [], \
                f"同名时不应 update user_group, 实际: {user_group_updates}"


# =============================================================================
# TestModuleExports: 防御性测试 - 修复必须暴露为模块级函数
# =============================================================================
class TestModuleExports:
    """确保修复必须暴露在 group.py 模块级 (供测试覆盖 + 防止被删)."""

    def test_replace_in_csv_exported(self):
        from app.users import group as _group_mod
        assert hasattr(_group_mod, '_replace_in_csv'), \
            "H11-2 修复: _replace_in_csv 必须暴露在 group.py 模块级"

    def test_replace_in_csv_is_pure(self):
        """验证函数是纯函数 (无副作用, 同输入同输出)."""
        from app.users.group import _replace_in_csv
        a = _replace_in_csv('a,b,c', 'b', 'x')
        b = _replace_in_csv('a,b,c', 'b', 'x')
        assert a == b == 'a,x,c'

    def test_sqlalchemy_func_imported(self):
        """关联表迁移后不应再依赖 CSV FIND_IN_SET 查询。"""
        from app.users import group as _group_mod
        assert not hasattr(_group_mod, 'func')
        assert not hasattr(_group_mod, 't_auth_host')
