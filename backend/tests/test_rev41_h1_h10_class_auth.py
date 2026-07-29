# -*- coding: utf-8 -*-
"""REV41-H1/H10: AccUser/AccGroup 类内 admin 鉴权单测.

背景:
- 路由层已挂 roles=['admin'] 装饰器 (account_api.py)
- 但评审指出: 如果路由层误改, 任何已登录用户都能调危险操作
- 修复: 在每个高危 class __init__ 加 _require_admin_or_raise() 兜底
- 测试: 用 mock patch get_current_user_role 验证各 class 行为
"""
from unittest.mock import MagicMock, patch

import pytest


class TestRequireAdminHelper:
    """Helper 函数 _require_admin_or_raise 单元测试."""

    def test_admin_role_passes(self, monkeypatch):
        """admin 角色 → 不抛异常."""
        from app.users.user import _require_admin_or_raise
        monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
        # 应当无异常
        _require_admin_or_raise()

    def test_user_role_raises(self, monkeypatch):
        """非 admin (user) → 抛 PermissionError."""
        from app.users.user import _require_admin_or_raise
        monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
        with pytest.raises(PermissionError) as exc_info:
            _require_admin_or_raise()
        assert 'admin' in str(exc_info.value)

    def test_audit_role_raises(self, monkeypatch):
        """audit 角色 (虽然有日志权限) → 也被拒绝 (H1/H10 严格要求 admin)."""
        from app.users.user import _require_admin_or_raise
        monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'audit')
        with pytest.raises(PermissionError):
            _require_admin_or_raise()

    def test_none_role_raises(self, monkeypatch):
        """未登录 (role=None) → 抛 PermissionError."""
        from app.users.user import _require_admin_or_raise
        monkeypatch.setattr('app.users.user.get_current_user_role', lambda: None)
        with pytest.raises(PermissionError):
            _require_admin_or_raise()

    def test_empty_string_role_raises(self, monkeypatch):
        """role='' → 抛 PermissionError."""
        from app.users.user import _require_admin_or_raise
        monkeypatch.setattr('app.users.user.get_current_user_role', lambda: '')
        with pytest.raises(PermissionError):
            _require_admin_or_raise()


class TestAccUserAdminEnforcement:
    """H1: AccUserAdd/Del/Update/ResetPwd 类内 admin 校验."""

    def test_acc_user_add_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AccUserAdd → 抛 PermissionError."""
        from app.users.user import AccUserAdd
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/user/add', method='POST', data={
            'alias': 'x', 'name': 'y', 'password': 'pwd', 'usrole': 'user',
            'mail': 'm@e.com', 'group': 'g1', 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AccUserAdd()

    def test_acc_user_add_allows_admin(self, monkeypatch):
        """admin 角色构造 AccUserAdd → 不抛异常."""
        from app.users.user import AccUserAdd
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/user/add', method='POST', data={
            'alias': 'x', 'name': 'y', 'password': 'pwd', 'usrole': 'user',
            'mail': 'm@e.com', 'group': 'g1', 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            monkeypatch.setattr('app.users.user.get_current_user', lambda: (MagicMock(), 'admin'))
            instance = AccUserAdd()
            assert instance.name == 'y'

    def test_acc_user_del_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AccUserDel → 抛 PermissionError."""
        from app.users.user import AccUserDel
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/user/del', method='POST', data={'name': 'y'}):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AccUserDel()

    def test_acc_user_update_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AccUserUpdate → 抛 PermissionError (继承自 AccUserAdd.__init__)."""
        from app.users.user import AccUserUpdate
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/user/update', method='POST', data={
            'id': '1', 'alias': 'x', 'name': 'y', 'password': '', 'usrole': 'user',
            'mail': 'm@e.com', 'group': 'g1', 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AccUserUpdate()

    def test_acc_user_reset_pwd_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AccUserResetPwd → 抛 PermissionError."""
        from app.users.user import AccUserResetPwd
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/user/reset_pwd', method='POST', data={
            'name': 'y', 'new_password': 'newpass123',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AccUserResetPwd()


class TestAccGroupAdminEnforcement:
    """H10: AccGroupAdd/Del/Update 类内 admin 校验."""

    def test_acc_group_add_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AccGroupAdd → 抛 PermissionError."""
        from app.users.group import AccGroupAdd
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/group/add', method='POST', data={
            'name': 'g1', 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AccGroupAdd()

    def test_acc_group_del_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AccGroupDel → 抛 PermissionError."""
        from app.users.group import AccGroupDel
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/group/del', method='POST', data={'name': 'g1'}):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AccGroupDel()

    def test_acc_group_update_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AccGroupUpdate → 抛 PermissionError (继承自 AccGroupAdd.__init__)."""
        from app.users.group import AccGroupUpdate
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/group/update', method='POST', data={
            'id': '1', 'name': 'g1', 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AccGroupUpdate()

    def test_acc_group_add_allows_admin(self, monkeypatch):
        """admin 角色构造 AccGroupAdd → 不抛异常."""
        from app.users.group import AccGroupAdd
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/account/group/add', method='POST', data={
            'name': 'g1', 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            monkeypatch.setattr('app.users.user.get_current_user', lambda: (MagicMock(), 'admin'))
            instance = AccGroupAdd()
            assert instance.name == 'g1'


class TestDefenseInDepth:
    """防御深度: 即使路由层被误改, 类内仍能拦住."""

    def test_init_decorator_missing_simulation(self, monkeypatch):
        """模拟路由层装饰器被误删, 类内仍拦截."""
        # 现实: 假设 account_api.py 某个路由的 roles=['admin'] 被误删为 roles=[]
        # 类内 _require_admin_or_raise 应作为最后一道防线
        from app.users.user import _require_admin_or_raise
        # role=user 表示非 admin
        monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
        # 必须抛 PermissionError
        with pytest.raises(PermissionError):
            _require_admin_or_raise()
