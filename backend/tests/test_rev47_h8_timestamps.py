# -*- coding: utf-8 -*-
"""
R2-5 (REV45-H8): created_at / updated_at 时间戳自动管理

问题: 业务表无时间戳字段, 无法审计:
  - 何时添加的资产/账号/SSH 用户/cron
  - 何时被修改
修复:
  - TimestampMixin 自动管理 (default + onupdate)
  - 关键表加 mixin: t_host / t_sys_user / t_acc_user / t_auth_host / t_cron
  - ALTER 迁移脚本 rev47_h8_timestamps.sql
测试维度:
  1) Mixin 定义: created_at, updated_at 列属性存在
  2) created_at 字段有 default, 不可空
  3) updated_at 字段有 default + onupdate, 不可空
  4) 加 mixin 的 ORM 类继承时间戳列
  5) 没加 mixin 的 ORM 类不带时间戳列 (白名单正向验证)
  6) ALTER SQL: 含完整 stored procedure
  7) ALTER SQL: 5 张表名全
"""
import os
import re
import sys
import pytest
from datetime import datetime, timedelta

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# 1) TimestampMixin 自身
# =============================================================================
class TestTimestampMixin:
    """R2-5: TimestampMixin 必须含 created_at / updated_at"""

    def test_01_mixin_exists(self):
        """TimestampMixin 类定义存在"""
        from app.core.db.database import TimestampMixin
        assert TimestampMixin is not None

    def test_02_created_at_column(self):
        """created_at 是 db.Column (DateTime), 不可空"""
        from app.core.db.database import TimestampMixin
        col = TimestampMixin.created_at
        assert col is not None
        assert col.nullable is False
        assert hasattr(col.type, '__class__')
        from sqlalchemy import DateTime
        assert isinstance(col.type, DateTime)

    def test_03_created_at_has_default(self):
        """created_at 必须有 default 可调用对象"""
        from app.core.db.database import TimestampMixin
        col = TimestampMixin.created_at
        assert col.default is not None
        # default.arg 应是 callable
        assert callable(col.default.arg), \
            f"created_at.default.arg 应为 callable, 实际: {col.default.arg}"

    def test_04_updated_at_column(self):
        """updated_at 是 db.Column (DateTime), 不可空"""
        from app.core.db.database import TimestampMixin
        col = TimestampMixin.updated_at
        assert col.nullable is False
        from sqlalchemy import DateTime
        assert isinstance(col.type, DateTime)

    def test_05_updated_at_has_default_and_onupdate(self):
        """updated_at 既有 default 又有 onupdate (ON UPDATE 触发)"""
        from app.core.db.database import TimestampMixin
        col = TimestampMixin.updated_at
        assert col.default is not None
        assert col.onupdate is not None
        assert callable(col.onupdate.arg)

    def test_06_default_returns_utcnow(self):
        """default 函数返回 datetime.utcnow() 时间"""
        from app.core.db.database import TimestampMixin, _utcnow
        before = datetime.utcnow()
        ts = _utcnow()
        after = datetime.utcnow()
        # ts 必须落在 [before, after] 之内
        assert before <= ts <= after, \
            f"default utcnow ts={ts} 不在 [{before}, {after}]"


# =============================================================================
# 2) 5 张关键业务表继承 TimestampMixin
# =============================================================================
class TestKeyTablesHaveTimestamps:
    """R2-5: 关键表必须含 created_at / updated_at 列"""

    TABLES = ('t_host', 't_sys_user', 't_acc_user', 't_auth_host', 't_cron')

    @pytest.mark.parametrize('table_name', TABLES)
    def test_01_table_has_created_at_column(self, table_name):
        """每张关键表必须有 created_at 列"""
        from app.core.db import database as db_module
        Model = getattr(db_module, table_name)
        # 模型实例的 __table__.columns
        cols = list(Model.__table__.columns.keys())
        assert 'created_at' in cols, \
            f"{table_name} 缺 created_at (现有列: {cols})"

    @pytest.mark.parametrize('table_name', TABLES)
    def test_02_table_has_updated_at_column(self, table_name):
        """每张关键表必须有 updated_at 列"""
        from app.core.db import database as db_module
        Model = getattr(db_module, table_name)
        cols = list(Model.__table__.columns.keys())
        assert 'updated_at' in cols, \
            f"{table_name} 缺 updated_at (现有列: {cols})"

    @pytest.mark.parametrize('table_name', TABLES)
    def test_03_created_at_indexed(self, table_name):
        """created_at 应有 index (按时间范围查询)"""
        from app.core.db import database as db_module
        Model = getattr(db_module, table_name)
        col = Model.__table__.columns['created_at']
        assert col.index is True, f"{table_name}.created_at 没有 index"

    @pytest.mark.parametrize('table_name', TABLES)
    def test_04_updated_at_indexed(self, table_name):
        """updated_at 应有 index"""
        from app.core.db import database as db_module
        Model = getattr(db_module, table_name)
        col = Model.__table__.columns['updated_at']
        assert col.index is True, f"{table_name}.updated_at 没有 index"

    @pytest.mark.parametrize('table_name', TABLES)
    def test_05_timestamps_not_nullable(self, table_name):
        """created_at / updated_at 都应 NOT NULL"""
        from app.core.db import database as db_module
        Model = getattr(db_module, table_name)
        for col_name in ('created_at', 'updated_at'):
            col = Model.__table__.columns[col_name]
            assert col.nullable is False, \
                f"{table_name}.{col_name} nullable=True (应为 NOT NULL)"


# =============================================================================
# 3) ALTER 迁移脚本
# =============================================================================
class TestAlterMigration:
    """R2-5: rev47_h8_timestamps.sql 完整性检查"""

    MIGRATION = os.path.join(BACKEND, 'mysqldir', 'rev47_h8_timestamps.sql')

    def _read(self):
        with open(self.MIGRATION, encoding='utf-8') as f:
            return f.read()

    def test_01_file_exists(self):
        assert os.path.isfile(self.MIGRATION)

    def test_02_contains_stored_procedure(self):
        """ALTER 脚本必须含 stored procedure 防重复加"""
        sql = self._read()
        assert 'CREATE PROCEDURE' in sql, "缺 stored procedure"
        assert '_add_timestamps' in sql, "缺 _add_timestamps proc 名"

    def test_03_idempotent_via_information_schema(self):
        """stored proc 内必须用 information_schema 检查列存在"""
        sql = self._read()
        assert 'information_schema.COLUMNS' in sql, \
            "proc 内缺 information_schema 检查 (不幂等)"

    def test_04_adds_created_at_column(self):
        """proc 内含 ADD COLUMN created_at DATETIME"""
        sql = self._read()
        assert re.search(
            r"ADD\s+COLUMN\s+`?created_at`?\s+DATETIME",
            sql, re.IGNORECASE
        ), "proc 缺 ADD COLUMN created_at DATETIME"

    def test_05_adds_updated_at_with_on_update(self):
        """proc 内含 ADD COLUMN updated_at DATETIME ... ON UPDATE"""
        sql = self._read()
        assert re.search(
            r"ADD\s+COLUMN\s+`?updated_at`?\s+DATETIME.*?ON\s+UPDATE\s+CURRENT_TIMESTAMP",
            sql, re.IGNORECASE | re.DOTALL
        ), "proc 缺 updated_at + ON UPDATE CURRENT_TIMESTAMP"

    def test_06_covers_all_five_tables(self):
        """CALL _add_timestamps 必须覆盖 5 张表"""
        sql = self._read()
        for tbl in ('t_host', 't_sys_user', 't_acc_user', 't_auth_host', 't_cron'):
            assert re.search(
                r"CALL\s+_add_timestamps\s*\(\s*'" + re.escape(tbl) + r"'\s*\)",
                sql, re.IGNORECASE
            ), f"ALTER 缺对 {tbl} 表的 CALL"

    def test_07_adds_index_for_each_timestamp(self):
        """proc 内必须给两个时间戳都建索引"""
        sql = self._read()
        # 至少 2 个 ADD INDEX 语句
        add_index_count = len(re.findall(r"ADD\s+INDEX", sql, re.IGNORECASE))
        assert add_index_count >= 2, \
            f"proc 缺时间戳索引 (ADD INDEX 调用 {add_index_count} 次)"

    def test_08_verification_query(self):
        """ALTER 末尾必须含验证 SELECT"""
        sql = self._read()
        assert 'information_schema.COLUMNS' in sql
        # 必须查 created_at / updated_at
        assert "'created_at'" in sql or '"created_at"' in sql
        assert "'updated_at'" in sql or '"updated_at"' in sql

    def test_09_drops_procedure_after(self):
        """ALTER 末尾应 DROP PROCEDURE 清理临时对象"""
        sql = self._read()
        assert re.search(r"DROP\s+PROCEDURE\s+_add_timestamps", sql, re.IGNORECASE), \
            "ALTER 末尾未清理 stored procedure"


# =============================================================================
# 4) 系统表不带 created_at / updated_at (避免冗余)
# =============================================================================
class TestLogTablesDontHaveTimestamps:
    """R2-5: log_*_log 系列使用自己的 log_time, 不应再加 created_at"""

    def test_01_login_log_uses_log_time(self):
        """t_login_log 用 log_time, 不应混入 TimestampMixin"""
        from app.core.db.database import t_login_log
        cols = list(t_login_log.__table__.columns.keys())
        # 有 log_time
        assert 'log_time' in cols
        # 不应有 created_at / updated_at (避免冗余)
        assert 'created_at' not in cols, \
            f"t_login_log 已用 log_time, 不应再加 created_at (cols={cols})"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
