# -*- coding: utf-8 -*-
"""REV42 P1 修复单测: H2 (auth_group_role None 防护) + H4 (AuthHostUpdate 支持改 name).

H2 (R2-3-1): auth_group_role 入口 req_type 为 None 时早返, 避免 fall through 返回 None.
H4 (R2-3-2): AuthHostUpdate 用 old_name 查 row, 用 self.name (新名) update, 实现改名.
"""
from unittest.mock import MagicMock

import pytest
from flask import Flask


@pytest.fixture
def _flask_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


# =============================================================================
# H2: auth_group_role None 防护
# =============================================================================
class TestAuthGroupRoleNoneProtect:
    """R2-3-1: auth_group_role 入口 req_type=None 时早返 code=100."""

    def test_req_type_none_returns_100_with_msg(self, _flask_app, monkeypatch):
        """req_type 缺失 → 返回 code=100, 不返回 None (避免前端拿空响应)."""
        from app.auth import AuthHost as _mod

        with _flask_app.test_request_context(
            '/auth/host/uplist', method='POST', data={'name': 'dev'},
        ):
            instance = _mod.AuthHostList()
            resp = instance.auth_group_role

        # 必须返回 jsonify 对象, 不能是 None
        assert resp is not None, "H2 修复: req_type=None 必须早返, 不能返回 None"
        body = resp.get_json()
        assert body['code'] == 100, f"应 code=100, 实际 {body}"
        assert 'req_type' in body.get('msg', ''), \
            f"msg 应提示 req_type, 实际: {body.get('msg')}"

    def test_req_type_none_does_not_query_database(self, _flask_app, monkeypatch):
        """req_type=None 时不应触发数据库查询 (早返)."""
        from app.auth import AuthHost as _mod

        # mock t_auth_host 等所有 query, 验证 H2 防护下不会被调用
        auth_query = MagicMock()
        monkeypatch.setattr(_mod, 't_auth_host', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_acc_user', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_acc_group', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_group', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_sys_user', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_auth_host_user', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_auth_host_user_group', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_auth_host_host_group', MagicMock(query=auth_query))
        monkeypatch.setattr(_mod, 't_auth_host_sys_user', MagicMock(query=auth_query))

        with _flask_app.test_request_context(
            '/auth/host/uplist', method='POST', data={'name': 'dev'},
        ):
            instance = _mod.AuthHostList()
            resp = instance.auth_group_role

        # H2 早返: 不应触发任何 query
        assert resp.get_json()['code'] == 100
        # .query.filter_by 都不应被调用
        for mod in [_mod.t_auth_host, _mod.t_acc_user, _mod.t_acc_group, _mod.t_group, _mod.t_sys_user,
                    _mod.t_auth_host_user, _mod.t_auth_host_user_group,
                    _mod.t_auth_host_host_group, _mod.t_auth_host_sys_user]:
            mod.query.filter_by.assert_not_called()

    def test_req_type_empty_string_returns_100(self, _flask_app, monkeypatch):
        """req_type='' (空字符串) 也应早返."""
        from app.auth import AuthHost as _mod

        with _flask_app.test_request_context(
            '/auth/host/uplist', method='POST', data={'name': 'dev', 'req_type': ''},
        ):
            instance = _mod.AuthHostList()
            resp = instance.auth_group_role

        body = resp.get_json()
        assert body['code'] == 100, f"空字符串也应早返, 实际 {body}"

    def test_valid_req_type_still_works(self, _flask_app, monkeypatch):
        """req_type='all' 等合法值时, 走原有逻辑 (不破坏 H2 早返)."""
        from app.auth import AuthHost as _mod

        with _flask_app.test_request_context(
            '/auth/host/uplist', method='POST', data={'name': 'dev', 'req_type': 'all'},
        ):
            instance = _mod.AuthHostList()
            # mock t_auth_host.query.filter_by(name=...).first() 返非空
            row = MagicMock()
            row.name = 'dev'
            row.remarks = 'test'
            _mod.t_auth_host.query.filter_by.return_value.first.return_value = row
            resp = instance.auth_group_role

        body = resp.get_json()
        assert body['code'] == 0, f"合法 req_type 应 code=0, 实际 {body}"


# =============================================================================
# H4: AuthHostUpdate 支持改 name
# =============================================================================
class TestAuthHostUpdateRename:
    """R2-3-2: AuthHostUpdate 用 old_name 查 row, update 用 self.name (新名)."""

    def _setup(self, monkeypatch, old_name='dev', new_name='qa'):
        """构造一个 admin 请求 + mock 数据库.

        Returns:
            _mod_module (导入的 AuthHost 模块)
        """
        from app.auth import AuthHost as _mod

        # admin 角色 (REV42-H1: _require_admin_or_raise)
        monkeypatch.setattr(
            'app.users.user.get_current_user_role', lambda: 'admin',
        )
        return _mod

    def test_update_with_old_name_and_new_name(self, _flask_app, monkeypatch):
        """传 old_name + new_name 改名, 成功 code=0."""
        _mod = self._setup(monkeypatch, old_name='dev', new_name='qa')

        with _flask_app.test_request_context(
            '/auth/host/update', method='POST', data={
                'name': 'qa',         # 新名
                'old_name': 'dev',   # 旧名
                'user': 'alice', 'user_group': '', 'host_group': '', 'sys_user': '',
                'remarks': 'renamed',
            },
        ):
            # 模拟查 row: filter_by(name='dev').first() 返 row; filter_by(name='qa').first() 返 None
            auth_row = MagicMock(id=1)

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('name') == 'dev':
                    f.first.return_value = auth_row
                elif kwargs.get('name') == 'qa':
                    f.first.return_value = None  # 新名不冲突
                f.update.return_value = 1
                f.delete.return_value = 1
                return f

            monkeypatch.setattr(_mod.t_auth_host, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_host_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_sys_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))

            instance = _mod.AuthHostUpdate()
            resp = instance.auth_host_update

        body = resp.get_json()
        assert body['code'] == 0, f"改名应 code=0, 实际 {body}"

    def test_update_old_name_not_found_returns_100(self, _flask_app, monkeypatch):
        """old_name 查不到 row → code=100 (兼容前端不传 old_name 但 self.name 错的场景)."""
        _mod = self._setup(monkeypatch, old_name='nonexistent', new_name='qa')

        with _flask_app.test_request_context(
            '/auth/host/update', method='POST', data={
                'name': 'qa', 'old_name': 'nonexistent',
                'user': '', 'user_group': '', 'host_group': '', 'sys_user': '',
                'remarks': '',
            },
        ):
            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                f.first.return_value = None
                f.update.return_value = 0
                f.delete.return_value = 0
                return f

            monkeypatch.setattr(_mod.t_auth_host, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_host_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_sys_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))

            instance = _mod.AuthHostUpdate()
            resp = instance.auth_host_update

        body = resp.get_json()
        assert body['code'] == 100, f"old_name 不存在应 code=100, 实际 {body}"

    def test_update_new_name_clash_returns_100(self, _flask_app, monkeypatch):
        """new_name 与现有活跃 name 冲突 → code=100 '新名称已被使用'."""
        _mod = self._setup(monkeypatch, old_name='dev', new_name='qa')

        with _flask_app.test_request_context(
            '/auth/host/update', method='POST', data={
                'name': 'qa', 'old_name': 'dev',
                'user': '', 'user_group': '', 'host_group': '', 'sys_user': '',
                'remarks': '',
            },
        ):
            auth_row = MagicMock(id=1)
            clash_row = MagicMock(id=2)  # qa 已被占用

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('name') == 'dev':
                    f.first.return_value = auth_row
                elif kwargs.get('name') == 'qa':
                    f.first.return_value = clash_row
                f.update.return_value = 0
                f.delete.return_value = 0
                return f

            monkeypatch.setattr(_mod.t_auth_host, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_host_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_sys_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))

            instance = _mod.AuthHostUpdate()
            resp = instance.auth_host_update

        body = resp.get_json()
        assert body['code'] == 100, f"new_name 冲突应 code=100, 实际 {body}"
        assert '已被使用' in body.get('msg', ''), \
            f"msg 应提示已被使用, 实际: {body.get('msg')}"

    def test_update_without_old_name_defaults_to_self_name(self, _flask_app, monkeypatch):
        """前端不传 old_name → 默认 self.name 查 row, 等于不改名 (向后兼容)."""
        _mod = self._setup(monkeypatch)

        with _flask_app.test_request_context(
            '/auth/host/update', method='POST', data={
                'name': 'dev',  # 不传 old_name, self.name = 'dev'
                'user': 'alice', 'user_group': '', 'host_group': '', 'sys_user': '',
                'remarks': 'unchanged',
            },
        ):
            auth_row = MagicMock(id=1)

            def filter_by_side_effect(**kwargs):
                f = MagicMock()
                if kwargs.get('name') == 'dev':
                    f.first.return_value = auth_row
                f.update.return_value = 1
                f.delete.return_value = 1
                return f

            monkeypatch.setattr(_mod.t_auth_host, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_user_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_host_group, 'query',
                                MagicMock(filter_by=filter_by_side_effect))
            monkeypatch.setattr(_mod.t_auth_host_sys_user, 'query',
                                MagicMock(filter_by=filter_by_side_effect))

            instance = _mod.AuthHostUpdate()
            # 验证 self.old_name 默认 = self.name
            assert instance.old_name == 'dev', \
                f"H4 兼容: 不传 old_name 应默认 self.name, 实际 old_name={instance.old_name!r}"
            resp = instance.auth_host_update

        body = resp.get_json()
        assert body['code'] == 0, f"不传 old_name 应正常 code=0, 实际 {body}"

    def test_update_system_auth_blocked(self, _flask_app, monkeypatch):
        """所有权限 改名 → code=100 '系统权限不可修改'."""
        _mod = self._setup(monkeypatch)

        with _flask_app.test_request_context(
            '/auth/host/update', method='POST', data={
                'name': '所有权限',  # self.name = '所有权限' 触发拦截
                'old_name': '所有权限',  # 默认值
                'user': '', 'user_group': '', 'host_group': '', 'sys_user': '',
                'remarks': '',
            },
        ):
            instance = _mod.AuthHostUpdate()
            resp = instance.auth_host_update

        body = resp.get_json()
        assert body['code'] == 100, f"系统权限改名应 code=100, 实际 {body}"
        assert '系统权限' in body.get('msg', ''), \
            f"msg 应提示系统权限, 实际: {body.get('msg')}"

    def test_update_init_stores_old_name(self, _flask_app, monkeypatch):
        """__init__ 应正确设置 self.old_name."""
        _mod = self._setup(monkeypatch)

        with _flask_app.test_request_context(
            '/auth/host/update', method='POST', data={
                'name': 'qa', 'old_name': 'dev',
                'user': '', 'user_group': '', 'host_group': '', 'sys_user': '',
                'remarks': '',
            },
        ):
            instance = _mod.AuthHostUpdate()
            # self.name 是 new_name (前端 form.value.name)
            assert instance.name == 'qa', f"self.name 应为 new_name='qa', 实际 {instance.name!r}"
            # self.old_name 是 old_name
            assert instance.old_name == 'dev', \
                f"self.old_name 应为 'dev', 实际 {instance.old_name!r}"
