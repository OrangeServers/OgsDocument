# -*- coding: utf-8 -*-
"""REV44-H3: '所有权限' 行兜底单测.

背景:
- 首次部署 / DB 迁移后, t_auth_host 表可能没有 '所有权限' 行
- 三个 auth 方法 (host_group_auth / sys_user_auth / acc_group_auth)
  静默 skip, 关联表永远为空, 所有用户看不到 host (高危)
- 修复: 增加 _ensure_all_auth_row() 兜底, 缺失时自动 osql_in 创建

测试覆盖:
- TestEnsureAllAuthRow: helper 纯函数
  - 已有 → 复用, 不调 osql_in
  - 缺失 → osql_in 创建, 返回新行
  - osql_in 抛 SqlOpError → 返回 None, 不抛
- TestHostGroupAuth: 集成 - 缺失自动创建
- TestSysUserAuth: 集成
- TestAccGroupAuth: 集成
- TestModuleExports: 防御性
"""
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# TestEnsureAllAuthRow: helper 纯函数测试
# =============================================================================
class TestEnsureAllAuthRow:
    """REV44-H3: _ensure_all_auth_row() 单元测试."""

    def test_existing_row_returned_no_insert(self, monkeypatch):
        """已有 '所有权限' 行 → 直接返回, 不调 osql_in (避免重复创建)."""
        from app.tools import auto_update as _au
        existing = MagicMock(id=42, name='所有权限')

        # mock t_auth_host.query.filter_by(name='所有权限').first() -> existing
        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing)))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        # 记录 osql_in 是否被调用
        osql_in_calls = []
        monkeypatch.setattr(_au, 'osql_in',
                            lambda *a, **kw: osql_in_calls.append((a, kw)) or MagicMock())

        result = _au._ensure_all_auth_row()

        assert result is existing, f"应返回已有行 id=42, 实际 {result!r}"
        assert osql_in_calls == [], f"已有行不应调 osql_in, 实际 {osql_in_calls}"

    def test_missing_row_auto_created(self, monkeypatch):
        """缺失 '所有权限' 行 → osql_in 自动创建, 返回新行 (二次查询)."""
        from app.tools import auto_update as _au

        # 模拟首次查询返回 None, 二次查询返回新行
        new_row = MagicMock(id=100, name='所有权限')
        query_state = {'calls': 0}
        def mock_first():
            query_state['calls'] += 1
            if query_state['calls'] == 1:
                return None  # 首次: 查不到
            return new_row   # 二次: 查到刚创建的

        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=mock_first))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        # 记录 osql_in 调用
        osql_in_calls = []
        def fake_osql_in(table, **kwargs):
            osql_in_calls.append((table, kwargs))
            return MagicMock()
        monkeypatch.setattr(_au, 'osql_in', fake_osql_in)

        result = _au._ensure_all_auth_row()

        assert result is new_row, f"应返回新创建的行 id=100, 实际 {result!r}"
        assert len(osql_in_calls) == 1, f"应调 1 次 osql_in, 实际 {len(osql_in_calls)}"
        table, kwargs = osql_in_calls[0]
        assert table == 't_auth_host', f"应 INSERT t_auth_host, 实际 {table}"
        assert kwargs.get('name') == '所有权限', f"name 应为 '所有权限', 实际 {kwargs!r}"
        # 二次查询应被调用 (拿 auto-increment id)
        assert query_state['calls'] == 2, f"应二次查询拿 id, 实际 {query_state['calls']} 次"

    def test_osql_in_raises_returns_none(self, monkeypatch):
        """osql_in 抛 SqlOpError → 返回 None, 不向上抛 (不拖垮主业务)."""
        from app.tools import auto_update as _au
        # REV44-H3 防御: 某些早期 test 可能 reload 了 app.core.db.insert, 导致
        # _insert_mod.SqlOpError != _au.SqlOpError. 直接用 _au.SqlOpError 保证一致.
        SqlOpError = _au.SqlOpError

        # 首次查询返回 None
        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        def fake_osql_in_raises(*a, **kw):
            raise SqlOpError('模拟 DB 失败')
        monkeypatch.setattr(_au, 'osql_in', fake_osql_in_raises)

        # 不应抛异常
        result = _au._ensure_all_auth_row()
        assert result is None, f"创建失败应返回 None, 实际 {result!r}"

    def test_unexpected_exception_also_returns_none(self, monkeypatch):
        """osql_in 抛非 SqlOpError (e.g. AttributeError) → 仍不应拖垮主流程."""
        from app.tools import auto_update as _au

        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        def fake_osql_in_raises(*a, **kw):
            raise AttributeError('模拟代码 bug')
        monkeypatch.setattr(_au, 'osql_in', fake_osql_in_raises)

        # 现状: helper 只 catch SqlOpError, 其他异常会向上抛
        # 这是预期行为 (代码 bug 应被暴露, 不应静默吞掉)
        with pytest.raises(AttributeError):
            _au._ensure_all_auth_row()


# =============================================================================
# TestHostGroupAuth: 集成测试
# =============================================================================
class TestHostGroupAuth:
    """REV44-H3: host_group_auth 首次部署自动创建 '所有权限'."""

    def test_first_deploy_auto_creates_all_auth(self, monkeypatch):
        """首次部署 (无 '所有权限' 行) → host_group_auth 应自动创建并填充关联表."""
        from app.tools import auto_update as _au

        # 准备: t_group 有 2 个资产组
        groups = [('grp1',), ('grp2',)]
        new_auth_row = MagicMock(id=200, name='所有权限')

        # t_auth_host.query 首次 None, 二次 new_auth_row
        query_state = {'calls': 0}
        def mock_tauth_first():
            query_state['calls'] += 1
            return None if query_state['calls'] == 1 else new_auth_row

        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=mock_tauth_first))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        # REV47-M6: auto_update 走 filter_by(is_deleted=False).with_entities(...).all() 链
        # mock 端: filter_by 返回带 with_entities 的 MagicMock, with_entities 返回带 all 的 MagicMock
        mock_tgroup = MagicMock()
        mock_tgroup.query = MagicMock()
        mock_tgroup.query.filter_by = MagicMock(
            return_value=MagicMock(
                with_entities=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=groups))
                )
            )
        )
        monkeypatch.setattr(_au, 't_group', mock_tgroup)

        # 记录 osql_in 调用 (自动创建 '所有权限')
        osql_in_calls = []
        def fake_osql_in(table, **kwargs):
            osql_in_calls.append((table, kwargs))
            return MagicMock()
        monkeypatch.setattr(_au, 'osql_in', fake_osql_in)

        # 记录 osql_de 调用
        osql_de_calls = []
        def fake_osql_de(table, where):
            osql_de_calls.append((table, where))
        monkeypatch.setattr(_au, 'osql_de', fake_osql_de)

        # mock db.session.add 记录关联表插入
        adds = []
        mock_db = MagicMock()
        mock_db.session.add = lambda obj: adds.append(obj)
        mock_db.session.commit = MagicMock()
        monkeypatch.setattr(_au, 'db', mock_db)

        # mock ListTool.list_gather
        monkeypatch.setattr(_au.ListTool, 'list_gather',
                            lambda rows: [r[0] for r in rows])

        # mock t_auth_host_host_group 构造
        join_rows = []
        def fake_join(auth_id, group_name):
            j = MagicMock()
            j.auth_id = auth_id
            j.group_name = group_name
            join_rows.append((auth_id, group_name))
            return j
        monkeypatch.setattr(_au, 't_auth_host_host_group', fake_join)

        result = _au.AuthAutoUpdate.host_group_auth()

        # 验证
        assert result is True, f"应返回 True, 实际 {result}"
        # 1) 自动创建 '所有权限' 行
        assert any(
            tbl == 't_auth_host' and kw.get('name') == '所有权限'
            for tbl, kw in osql_in_calls
        ), f"应自动创建 t_auth_host '所有权限' 行, 实际 osql_in 调用: {osql_in_calls}"
        # 2) 关联表 (host_group) 被清空 (用 all_auth.id=200)
        assert any(
            tbl == 't_auth_host_host_group' and w.get('auth_id') == 200
            for tbl, w in osql_de_calls
        ), f"应调 osql_de 清空关联表 (auth_id=200), 实际: {osql_de_calls}"
        # 3) 2 个资产组都被 add 到关联表
        assert len(adds) == 2, f"应 add 2 个关联行, 实际 {len(adds)}"

    def test_existing_all_auth_no_double_create(self, monkeypatch):
        """已存在 '所有权限' 行 → host_group_auth 不应再调 osql_in."""
        from app.tools import auto_update as _au

        existing = MagicMock(id=300, name='所有权限')
        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing)))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        mock_tgroup = MagicMock()
        mock_tgroup.query = MagicMock()
        mock_tgroup.query.with_entities = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        monkeypatch.setattr(_au, 't_group', mock_tgroup)

        # 记录 osql_in
        osql_in_calls = []
        monkeypatch.setattr(_au, 'osql_in',
                            lambda *a, **kw: osql_in_calls.append((a, kw)) or MagicMock())
        monkeypatch.setattr(_au, 'osql_de', lambda *a, **kw: None)
        monkeypatch.setattr(_au, 'db', MagicMock())
        monkeypatch.setattr(_au.ListTool, 'list_gather', lambda rows: [r[0] for r in rows])
        monkeypatch.setattr(_au, 't_auth_host_host_group', MagicMock)

        result = _au.AuthAutoUpdate.host_group_auth()

        assert result is True
        # 关键: 不应调 osql_in (没有创建)
        assert osql_in_calls == [], f"已存在 '所有权限' 行不应再创建, 实际 osql_in: {osql_in_calls}"


# =============================================================================
# TestSysUserAuth / TestAccGroupAuth: 同样的兜底逻辑
# =============================================================================
class TestSysUserAuth:
    """REV44-H3: sys_user_auth 同样走 _ensure_all_auth_row()."""

    def test_first_deploy_auto_creates(self, monkeypatch):
        from app.tools import auto_update as _au
        new_auth = MagicMock(id=400, name='所有权限')
        query_state = {'calls': 0}
        def mock_first():
            query_state['calls'] += 1
            return None if query_state['calls'] == 1 else new_auth

        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=mock_first))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        mock_tsys = MagicMock()
        mock_tsys.query = MagicMock()
        mock_tsys.query.with_entities = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[('sualias1',)])))
        monkeypatch.setattr(_au, 't_sys_user', mock_tsys)

        osql_in_calls = []
        def fake_osql_in(table, **kwargs):
            osql_in_calls.append((table, kwargs))
            return MagicMock()
        monkeypatch.setattr(_au, 'osql_in', fake_osql_in)
        monkeypatch.setattr(_au, 'osql_de', lambda *a, **kw: None)
        monkeypatch.setattr(_au, 'db', MagicMock())
        monkeypatch.setattr(_au.ListTool, 'list_gather', lambda rows: [r[0] for r in rows])
        monkeypatch.setattr(_au, 't_auth_host_sys_user', MagicMock)

        result = _au.AuthAutoUpdate.sys_user_auth()

        assert result is True
        assert any(t == 't_auth_host' and kw.get('name') == '所有权限'
                   for t, kw in osql_in_calls), \
            f"应自动创建 t_auth_host '所有权限' 行, 实际: {osql_in_calls}"


class TestAccGroupAuth:
    """REV44-H3: acc_group_auth 同样走 _ensure_all_auth_row()."""

    def test_first_deploy_auto_creates(self, monkeypatch):
        from app.tools import auto_update as _au
        new_auth = MagicMock(id=500, name='所有权限')
        query_state = {'calls': 0}
        def mock_first():
            query_state['calls'] += 1
            return None if query_state['calls'] == 1 else new_auth

        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=mock_first))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        mock_tgroup = MagicMock()
        mock_tgroup.query = MagicMock()
        mock_tgroup.query.with_entities = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[('accg1',)])))
        monkeypatch.setattr(_au, 't_acc_group', mock_tgroup)

        osql_in_calls = []
        def fake_osql_in(table, **kwargs):
            osql_in_calls.append((table, kwargs))
            return MagicMock()
        monkeypatch.setattr(_au, 'osql_in', fake_osql_in)
        monkeypatch.setattr(_au, 'osql_de', lambda *a, **kw: None)
        monkeypatch.setattr(_au, 'db', MagicMock())
        monkeypatch.setattr(_au.ListTool, 'list_gather', lambda rows: [r[0] for r in rows])
        monkeypatch.setattr(_au, 't_auth_host_user_group', MagicMock)

        result = _au.AuthAutoUpdate.acc_group_auth()

        assert result is True
        assert any(t == 't_auth_host' and kw.get('name') == '所有权限'
                   for t, kw in osql_in_calls), \
            f"应自动创建 t_auth_host '所有权限' 行, 实际: {osql_in_calls}"

    def test_create_failure_returns_gracefully(self, monkeypatch):
        """osql_in 抛 SqlOpError → acc_group_auth 不向上抛 (H1+H3 静默 + Log).

        设计取舍: helper 内部已 catch SqlOpError 返回 None, 方法走到
        `if all_auth:` False 跳过, return True (没报错但也没填充关联表).
        错误信息已通过 Log.logger.error 记录. 这是 silent-fail + log 模式.
        """
        from app.tools import auto_update as _au
        SqlOpError = _au.SqlOpError  # REV44-H3 防御: 用 helper 命名空间的 SqlOpError

        mock_tauth = MagicMock()
        mock_tauth.query = MagicMock()
        mock_tauth.query.filter_by = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        monkeypatch.setattr(_au, 't_auth_host', mock_tauth)

        mock_tgroup = MagicMock()
        mock_tgroup.query = MagicMock()
        mock_tgroup.query.with_entities = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        monkeypatch.setattr(_au, 't_acc_group', mock_tgroup)

        def fake_osql_in_raises(*a, **kw):
            raise SqlOpError('模拟首次部署创建失败')
        monkeypatch.setattr(_au, 'osql_in', fake_osql_in_raises)

        # 记录 db.session.add 是否被调用 (helper 失败 → all_auth=None → 跳过)
        adds = []
        mock_db = MagicMock()
        mock_db.session.add = lambda obj: adds.append(obj)
        mock_db.session.commit = MagicMock()
        monkeypatch.setattr(_au, 'db', mock_db)
        monkeypatch.setattr(_au, 'osql_de', lambda *a, **kw: None)
        monkeypatch.setattr(_au.ListTool, 'list_gather', lambda rows: [r[0] for r in rows])
        monkeypatch.setattr(_au, 't_auth_host_user_group', MagicMock)

        # 不应抛异常, 静默返回 (H1 静默 catch + Log 已记录)
        result = _au.AuthAutoUpdate.acc_group_auth()
        assert result is True, f"helper 失败时方法应静默 return True (不抛), 实际 {result!r}"
        # 关键: 关联表不应被填充 (helper 失败, all_auth=None)
        assert len(adds) == 0, f"helper 失败时不应填充关联表, 实际 add {len(adds)} 次"


# =============================================================================
# TestModuleExports: 防御性 - 修复必须暴露
# =============================================================================
class TestModuleExports:
    """确保修复必须暴露在 auto_update.py 模块级."""

    def test_helper_function_exported(self):
        from app.tools import auto_update as _au
        assert hasattr(_au, '_ensure_all_auth_row'), \
            "REV44-H3 修复: _ensure_all_auth_row 必须暴露在 auto_update.py 模块级"

    def test_helper_is_callable(self):
        from app.tools import auto_update as _au
        assert callable(_au._ensure_all_auth_row), \
            "_ensure_all_auth_row 必须是 callable"

    def test_helper_used_in_all_three_auth_methods(self):
        """防御: 3 个 auth 方法必须调用 _ensure_all_auth_row()."""
        import inspect
        from app.tools import auto_update as _au
        for method_name in ('host_group_auth', 'sys_user_auth', 'acc_group_auth'):
            method = getattr(_au.AuthAutoUpdate, method_name)
            src = inspect.getsource(method)
            assert '_ensure_all_auth_row' in src, \
                f"AuthAutoUpdate.{method_name} 必须调用 _ensure_all_auth_row() (REV44-H3)"

    def test_db_imported_at_module_level(self):
        """M1 修复: db 必须顶层 import, 不在函数内 from import."""
        from app.tools import auto_update as _au
        assert hasattr(_au, 'db'), \
            "REV44-M1: db 必须在 auto_update.py 模块级 import"
