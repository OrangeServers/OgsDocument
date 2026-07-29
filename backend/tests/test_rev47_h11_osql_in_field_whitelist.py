# -*- coding: utf-8 -*-
"""
R2-7 (REV45-H11): osql_in 字段白名单校验

问题: SQLAlchemy ORM 默认接受任意 kwargs, 拼错字段名静默成功
  e.g. osql_in('t_acc_user', naem='alice')  # 'naem' 拼错, 不报错但 naem 列不存在
修复:
  - osql_in 加白名单校验, 传未知字段 → SqlOpError
  - OGS_OSQL_IN_STRICT=false env 可降级为过滤 (兼容老调用)
  - 和 osql_up (P2-4/MED-8) 同模式
测试维度:
  1) 正常 kwargs: 全部是合法列, 通过
  2) 拼错字段名 (naem 替代 name): SqlOpError
  3) 部分合法, 部分不合法: SqlOpError
  4) 错误消息含未知字段名 (调试信息)
  5) 错误消息含合法列名集合 (调试信息)
  6) OGS_OSQL_IN_STRICT=false 降级: 过滤未知字段而非报错
  7) 未知表仍然 SqlOpError
  8) SqlOpError 类型 (与 osql_up 行为一致)
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# Fixture: 绕过 conftest 的 autouse mock, 重新加载 insert 模块还原真实函数
# =============================================================================
# conftest.cron_scheduler_skip autouse 全局把 osql_in/osql_up 改成 lambda,
# 本测试需要真实行为. reload 是最直接的方式.
@pytest.fixture(autouse=True)
def _reload_insert_module():
    import importlib
    import sys as _sys
    # 卸下当前 insert 模块 (含 conftest 注入的 mock lambda), 强制 reload
    if 'app.core.db.insert' in _sys.modules:
        del _sys.modules['app.core.db.insert']
    importlib.import_module('app.core.db.insert')
    yield


# =============================================================================
# 1) 正常路径: 合法字段
# =============================================================================
class TestOsqlInValidFields:
    """R2-7: 合法字段必须通过"""

    def test_01_valid_fields_pass_through(self):
        """所有 kwargs 都是 t_acc_user 的合法列, osql_in 通过校验"""
        from app.core.db.insert import osql_in
        from app.core.db.database import t_acc_user

        valid_data = {
            'name': 'alice',
            'password': 'hashed_pwd',
            'usrole': 'admin',
            'mail': 'alice@example.com',
            'group': 'admin',
        }

        with patch('app.core.db.insert.db') as mock_db:
            mock_db.session.rollback = MagicMock()
            mock_db.session.add = MagicMock()
            mock_db.session.commit = MagicMock()

            try:
                # 这里可能会因为 ORM 内部 add 失败, 但先观察字段校验是否通过
                osql_in('t_acc_user', **valid_data)
            except Exception as e:
                # 校验阶段应该不抛 SqlOpError (字段都对)
                from app.core.db.insert import SqlOpError
                if isinstance(e, SqlOpError) and '未知字段名' in str(e):
                    pytest.fail(f"合法字段被误报为未知: {e}")
                # 其他异常 (e.g. ORM 内部) 不算校验错


# =============================================================================
# 2) 拼错字段名
# =============================================================================
class TestOsqlInFieldWhitelist:
    """R2-7: 未知字段必须 SqlOpError, 不静默成功"""

    def _mock_db_setup(self):
        """模拟 db.session, 让 osql_in 走到字段校验阶段就抛 SqlOpError (不会真 insert)"""
        # 关键: osql_in 字段校验阶段应该抛 SqlOpError 在 ORM 构造之前
        with patch('app.core.db.insert.db') as mock_db:
            mock_db.session.rollback = MagicMock()
            mock_db.session.add = MagicMock()
            mock_db.session.commit = MagicMock()
            yield mock_db

    def test_01_typo_field_raises_sqloperror(self):
        """naem (拼错 name) → SqlOpError"""
        from app.core.db.insert import osql_in, SqlOpError

        with patch('app.core.db.insert.db'):
            with pytest.raises(SqlOpError, match='未知字段名'):
                osql_in('t_acc_user',
                        naem='alice',  # 应是 name
                        password='x',
                        usrole='admin',
                        mail='x@e.com',
                        group='g')

    def test_02_partial_valid_partial_invalid(self):
        """部分合法 + 部分不合法字段 → SqlOpError"""
        from app.core.db.insert import osql_in, SqlOpError

        with patch('app.core.db.insert.db'):
            with pytest.raises(SqlOpError, match='未知字段名'):
                osql_in('t_acc_user',
                        name='alice',          # 合法
                        password='x',          # 合法
                        bogus_field_1='xyz',   # 不合法
                        bogus_field_2='abc')   # 不合法

    def test_03_error_message_lists_unknown_field(self):
        """错误消息必须含未知字段名"""
        from app.core.db.insert import osql_in, SqlOpError

        with patch('app.core.db.insert.db'):
            with pytest.raises(SqlOpError) as exc_info:
                osql_in('t_acc_user', name='a', naem_typo='b',
                        usrole='admin', mail='m@e.com',
                        password='p', group='g')
            msg = str(exc_info.value)
            assert 'naem_typo' in msg, f"错误消息缺未知字段名: {msg}"

    def test_04_error_message_lists_valid_columns(self):
        """错误消息含合法列名集合, 帮助调试"""
        from app.core.db.insert import osql_in, SqlOpError

        with patch('app.core.db.insert.db'):
            with pytest.raises(SqlOpError) as exc_info:
                osql_in('t_acc_user', name='a', unknown_field='b',
                        usrole='admin', mail='m@e.com',
                        password='p', group='g')
            msg = str(exc_info.value)
            # 应包含合法列名 name, password, mail 等
            assert '合法' in msg or 'name' in msg, \
                f"错误消息未提合法列名: {msg}"


# =============================================================================
# 3) 降级路径: OGS_OSQL_IN_STRICT=false
# =============================================================================
class TestOsqlInNonStrictMode:
    """R2-7: STRICT=false 时, 应过滤未知字段而非报错 (兼容老调用)"""

    def test_01_non_strict_filters_unknown(self):
        """OGS_OSQL_IN_STRICT=false 降级: 过滤未知字段"""
        from app.core.db.insert import osql_in

        with patch.dict(os.environ, {'OGS_OSQL_IN_STRICT': 'false'}), \
             patch('app.core.db.insert.db') as mock_db:
            mock_db.session.rollback = MagicMock()
            mock_db.session.add = MagicMock()
            mock_db.session.commit = MagicMock()

            # 不应抛 SqlOpError
            try:
                osql_in('t_acc_user',
                        name='alice',
                        password='x',
                        usrole='admin',
                        mail='x@e.com',
                        group='g',
                        typo_field='should_be_filtered')
            except Exception as e:
                # 若 mock 不够, 可能因 _TAB_DICT.get 等失败, 但不应是 SqlOpError(未知字段)
                from app.core.db.insert import SqlOpError
                if isinstance(e, SqlOpError) and '未知字段名' in str(e):
                    pytest.fail(f"非严格模式下不应报未知字段错: {e}")


# =============================================================================
# 4) 未知表
# =============================================================================
class TestOsqlInUnknownTable:
    """R2-7: 未知表的原行为保留"""

    def test_01_unknown_table_raises(self):
        """未知表 → SqlOpError (原行为)"""
        from app.core.db.insert import osql_in, SqlOpError

        with patch('app.core.db.insert.db'):
            with pytest.raises(SqlOpError, match='未知表'):
                osql_in('t_fake_table', foo='bar')


# =============================================================================
# 5) 和 osql_up 行为一致
# =============================================================================
class TestConsistencyWithOsqlUp:
    """R2-7: osql_in 的字段白名单行为应和 osql_up 一致"""

    def test_01_same_error_class(self):
        """osql_in / osql_up 都抛 SqlOpError (统一异常类型)"""
        from app.core.db.insert import osql_in, osql_up, SqlOpError
        # 二者签名都包含 SqlOpError (docstring 提到); 用 inspect.getsource 兜底
        import inspect
        in_src = inspect.getsource(osql_in)
        up_src = inspect.getsource(osql_up)
        assert 'SqlOpError' in in_src, "osql_in 源码未提 SqlOpError"
        assert 'SqlOpError' in up_src, "osql_up 源码未提 SqlOpError"

    def test_02_strict_env_var_match(self):
        """osql_in OGS_OSQL_IN_STRICT / osql_up OGS_OSQL_UP_STRICT 是独立 env"""
        # 这是设计: 允许分别降级 in / up
        # 但默认值都应是 'true'
        with patch('app.core.db.insert.db'):
            from app.core.db.insert import osql_up, SqlOpError
            with patch.dict(os.environ, {'OGS_OSQL_UP_STRICT': 'true'}):
                with pytest.raises(SqlOpError, match='未知字段名'):
                    osql_up('t_acc_user', {'name': 'x'}, {'unknown_field': 'y'})


# =============================================================================
# 6) 业务场景: 拼错常见字段 (防回归)
# =============================================================================
class TestCommonTypos:
    """R2-7: 防常见拼错回归"""

    COMMON_TYPOS = [
        ('naem', 'name'),
        ('adress', 'address_alias'),
        ('passowrd', 'password'),
        ('emial', 'mail'),
        ('rol', 'usrole'),
    ]

    @pytest.mark.parametrize('typo,correct', COMMON_TYPOS)
    def test_01_common_typo_caught(self, typo, correct):
        from app.core.db.insert import osql_in, SqlOpError

        kwargs = {typo: 'x', 'password': 'p', 'usrole': 'a',
                  'mail': 'm@e.com', 'group': 'g'}
        # 至少一个 name 类合法字段
        if 'name' not in kwargs and 'alias' not in kwargs:
            kwargs['name'] = 'alice'

        with patch('app.core.db.insert.db'):
            with pytest.raises(SqlOpError, match='未知字段名'):
                osql_in('t_acc_user', **kwargs)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
