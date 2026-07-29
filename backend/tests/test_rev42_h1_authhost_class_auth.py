# -*- coding: utf-8 -*-
"""REV42-H1: AuthHostDel/Add/Update 类内 admin 鉴权单测.

背景:
- AuthHostDel/Add 之前无类内鉴权, 无审计基类
- 一旦 init.py 路由装饰器被误改, 任何已登录用户能加/删/改授权规则 → 直接获得 admin 等价权限
- 修复: 3 个类继承 CzToolsLog + __init__ 调 _require_admin_or_raise()
- AuthHostUpdate extends AuthHostAdd → 父类 __init__ 已校验, 子类自动覆盖
"""
from unittest.mock import MagicMock, patch

import pytest


class TestAuthHostAdminEnforcement:
    """H1: AuthHostDel/Add/Update 类内 admin 校验."""

    def test_auth_host_del_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AuthHostDel → 抛 PermissionError."""
        from app.auth.AuthHost import AuthHostDel
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/del', method='POST', data={'name': 'rule1'}):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AuthHostDel()

    def test_auth_host_del_allows_admin(self, monkeypatch):
        """admin 角色构造 AuthHostDel → 不抛异常."""
        from app.auth.AuthHost import AuthHostDel
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/del', method='POST', data={'name': 'rule1'}):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            instance = AuthHostDel()
            assert instance.name == 'rule1'

    def test_auth_host_add_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AuthHostAdd → 抛 PermissionError."""
        from app.auth.AuthHost import AuthHostAdd
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/add', method='POST', data={
            'name': 'newrule', 'user': [], 'user_group': [], 'host_group': [],
            'sys_user': [], 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AuthHostAdd()

    def test_auth_host_add_allows_admin(self, monkeypatch):
        """admin 角色构造 AuthHostAdd → 不抛异常."""
        from app.auth.AuthHost import AuthHostAdd
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/add', method='POST', data={
            'name': 'newrule', 'user': ['alice'], 'user_group': [], 'host_group': [],
            'sys_user': [], 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            instance = AuthHostAdd()
            assert instance.name == 'newrule'
            assert 'alice' in instance.user

    def test_auth_host_update_rejects_non_admin(self, monkeypatch):
        """user 角色构造 AuthHostUpdate → 抛 PermissionError (继承自 AuthHostAdd.__init__)."""
        from app.auth.AuthHost import AuthHostUpdate
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/update', method='POST', data={
            'name': 'rule1', 'user': [], 'user_group': [], 'host_group': [],
            'sys_user': [], 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AuthHostUpdate()

    def test_auth_host_update_allows_admin(self, monkeypatch):
        """admin 角色构造 AuthHostUpdate → 不抛异常 (继承链覆盖)."""
        from app.auth.AuthHost import AuthHostUpdate
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/update', method='POST', data={
            'name': 'rule1', 'user': [], 'user_group': [], 'host_group': [],
            'sys_user': [], 'remarks': '',
        }):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            instance = AuthHostUpdate()
            assert instance.name == 'rule1'


class TestAuthHostInheritance:
    """验证 AuthHostDel/Add 已继承 CzToolsLog (为后续 H5 审计修复打基础)."""

    def test_auth_host_del_inherits_cztoolslog(self):
        from app.auth.AuthHost import AuthHostDel, CzToolsLog
        assert issubclass(AuthHostDel, CzToolsLog)

    def test_auth_host_add_inherits_cztoolslog(self):
        from app.auth.AuthHost import AuthHostAdd, CzToolsLog
        assert issubclass(AuthHostAdd, CzToolsLog)

    def test_auth_host_update_inherits_cztoolslog(self):
        from app.auth.AuthHost import AuthHostUpdate, CzToolsLog
        # AuthHostUpdate extends AuthHostAdd extends CzToolsLog
        assert issubclass(AuthHostUpdate, CzToolsLog)

    def test_host_log_method_available(self, monkeypatch):
        """CzToolsLog 提供的 host_log 方法可调用 (审计 API)."""
        from app.auth.AuthHost import AuthHostDel
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/del', method='POST', data={'name': 'rule1'}):
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'admin')
            instance = AuthHostDel()
            # 验证 host_log 方法存在 (H5 审计修复时调用)
            assert hasattr(instance, 'host_log')
            assert callable(instance.host_log)


class TestDefenseInDepthAuth:
    """防御深度: 即使 init.py 装饰器被误删, 类内仍能拦住."""

    def test_decorator_missing_simulation(self, monkeypatch):
        """模拟路由层装饰器被误删."""
        from app.auth.AuthHost import AuthHostDel
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context('/auth/host/del', method='POST', data={'name': 'rule1'}):
            # 假设装饰器被删, 角色校验完全由类内负责
            monkeypatch.setattr('app.users.user.get_current_user_role', lambda: 'user')
            with pytest.raises(PermissionError):
                AuthHostDel()
