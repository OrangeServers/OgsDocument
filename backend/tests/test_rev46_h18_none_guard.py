# -*- coding: utf-8 -*-
"""REV46-H18: get_ssh_connection None 防护单测.

背景:
- 之前 get_ssh_connection 直接访问 sys_user_info.host_user 等属性
- sys_user_info = None 时 → AttributeError → 500 Internal Server Error
- 修复: 入口 None check + raise ValueError (业务异常)
"""
from unittest.mock import MagicMock

import pytest


class TestGetSshConnectionNoneGuard:
    """H18: get_ssh_connection 必须对不存在的 sys_user 抛 ValueError, 不 AttributeError."""

    def test_none_sys_user_raises_value_error(self):
        """sys_user alias 不存在时抛 ValueError (语义化业务异常)."""
        from app.tools import shellcmd as _sc
        # mock t_sys_user.query.filter_by(...).first() 返回 None
        mock_first = MagicMock(return_value=None)
        mock_filter_by = MagicMock(return_value=MagicMock(first=mock_first))
        mock_query = MagicMock(filter_by=mock_filter_by)

        # 用 monkeypatch 替换 t_sys_user.query
        # 由于 t_sys_user 是 from import, 需要直接 patch 其 query 属性
        original_query = _sc.t_sys_user.query
        try:
            _sc.t_sys_user.query = mock_query
            with pytest.raises(ValueError) as exc_info:
                _sc.get_ssh_connection('not_exist', '127.0.0.1', 22)
            # 错误信息应含 alias 名
            assert 'not_exist' in str(exc_info.value)
            # 必须 ValueError, 不是 AttributeError
            assert not isinstance(exc_info.value, AttributeError)
        finally:
            _sc.t_sys_user.query = original_query

    def test_existing_sys_user_calls_remote_connection(self, monkeypatch):
        """sys_user 存在时, 不抛异常, 走 RemoteConnectionAuto 路径."""
        from app.tools import shellcmd as _sc

        # mock 一行 sys_user
        mock_row = MagicMock()
        mock_row.host_user = 'alice'
        mock_row.host_key = None
        mock_row.host_password = 'secret'

        mock_first = MagicMock(return_value=mock_row)
        mock_filter_by = MagicMock(return_value=MagicMock(first=mock_first))
        mock_query = MagicMock(filter_by=mock_filter_by)
        original_query = _sc.t_sys_user.query

        # mock RemoteConnectionAuto 避免真实 paramiko 连接
        mock_remote = MagicMock()
        monkeypatch.setattr(_sc, 'RemoteConnectionAuto', mock_remote)

        # mock get_ssh_password (避免触发 Fernet 解密)
        monkeypatch.setattr(_sc, 'get_ssh_password', lambda r: 'plain_pwd')

        try:
            _sc.t_sys_user.query = mock_query
            result = _sc.get_ssh_connection('alice', '127.0.0.1', 22)
            assert result is not None
            # RemoteConnectionAuto 被调用 1 次
            assert mock_remote.called
            # 调用参数含 (host_ip, host_port, host_user, password, pkey)
            call_args = mock_remote.call_args
            assert '127.0.0.1' in call_args.args
            assert 22 == call_args.args[1]
        finally:
            _sc.t_sys_user.query = original_query


class TestGetSshPasswordNoneGuard:
    """旁路: get_ssh_password(s) 已防御 None 返回 None, 此处加固."""

    def test_get_ssh_password_none_row_returns_none(self):
        """sys_user_row=None 时返回 None, 不抛异常."""
        from app.tools.shellcmd import get_ssh_password
        assert get_ssh_password(None) is None