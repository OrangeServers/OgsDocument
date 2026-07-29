# -*- coding: utf-8 -*-
"""
R2-4 (REV45-H7): cron.job_owner FK 约束

问题: t_cron.job_owner 是 String(30), 无 FK 约束, 可写入任何垃圾字符串
修复:
  - ORM: t_cron.job_owner 加 db.ForeignKey('t_acc_user.name', ondelete='SET DEFAULT')
  - SQL: orange.sql 创建表时带 FK, 种子加 system 用户
  - ALTER: rev47_h7_cron_owner_fk.sql 给现有 DB 加 FK
测试维度:
  1) ORM 元数据: t_cron.job_owner 列有 ForeignKey 约束
  2) ORM 元数据: 引用 t_acc_user.name (不是 id)
  3) ORM 元数据: ondelete='SET DEFAULT'
  4) SQL 文件: orange.sql 包含 FK 约束定义
  5) SQL 文件: orange.sql 包含 system 内置用户 INSERT
  6) ALTER SQL: rev47_h7_cron_owner_fk.sql 含完整迁移步骤
  7) ALTER SQL: 含 FK 验证 status
"""
import os
import re
import sys
import pytest
import inspect

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# 1) ORM 元数据验证 (核心防御点)
# =============================================================================
class TestOrmMetadata:
    """R2-4: ORM 中 t_cron.job_owner 必须有 FK 约束"""

    def test_01_job_owner_has_foreign_key(self):
        """t_cron.job_owner 列必须有 ForeignKey 约束"""
        from app.core.db.database import t_cron
        from sqlalchemy import ForeignKey

        col = t_cron.job_owner
        fk_list = list(col.foreign_keys)
        assert len(fk_list) >= 1, \
            f"t_cron.job_owner 没有 ForeignKey 约束 (FK list={fk_list})"

    def test_02_foreign_key_targets_acc_user_name(self):
        """FK 必须指向 t_acc_user.name (不是 id 或其他表)"""
        from app.core.db.database import t_cron

        col = t_cron.job_owner
        # 取第一个 FK
        assert len(list(col.foreign_keys)) >= 1
        fk = list(col.foreign_keys)[0]
        target_table = fk.column.table.name
        target_col = fk.column.name

        assert target_table == 't_acc_user', \
            f"FK 指向表 {target_table}, 应指向 t_acc_user"
        assert target_col == 'name', \
            f"FK 指向列 {target_col}, 应指向 name"

    def test_03_ondelete_set_default(self):
        """FK ondelete 必须是 SET DEFAULT, 不是 NO ACTION / CASCADE"""
        from app.core.db.database import t_cron

        col = t_cron.job_owner
        fk = list(col.foreign_keys)[0]
        ondelete = (fk.ondelete or '').upper()

        assert ondelete == 'SET DEFAULT', \
            f"FK ondelete={ondelete!r}, 应为 SET DEFAULT"

    def test_04_string_length_30(self):
        """job_owner 长度 30, 与 t_acc_user.name(24) 兼容 (含中文/历史脏数据)"""
        from app.core.db.database import t_cron

        col = t_cron.job_owner
        assert col.type.length == 30, f"job_owner 长度 = {col.type.length}, 应为 30"

    def test_05_default_system_string(self):
        """默认值保留 'system' 字符串 (兼容历史脏数据)"""
        from app.core.db.database import t_cron

        col = t_cron.job_owner
        assert col.default.arg == 'system'
        assert col.server_default.arg == 'system'


# =============================================================================
# 2) SQL 初始化文件 (greenfield DB)
# =============================================================================
class TestOrangeSql:
    """R2-4: orange.sql 初始化脚本同步加 FK"""

    ORANGE_SQL = os.path.join(BACKEND, 'mysqldir', 'orange.sql')

    def _read(self):
        with open(self.ORANGE_SQL, encoding='utf-8') as f:
            return f.read()

    def test_01_contains_job_owner_column(self):
        """CREATE TABLE t_cron 必须含 job_owner 列"""
        sql = self._read()
        # 在 t_cron 表段中找到 job_owner 列定义
        match = re.search(
            r"CREATE TABLE\s+`?t_cron`?.*?\)\s*ENGINE",
            sql, re.DOTALL | re.IGNORECASE
        )
        assert match is not None, "未找到 CREATE TABLE t_cron 段"
        block = match.group(0)
        assert 'job_owner' in block, "t_cron 表缺 job_owner 列"

    def test_02_contains_fk_cron_owner_constraint(self):
        """CREATE TABLE t_cron 含 fk_cron_owner 外键约束"""
        sql = self._read()
        assert 'fk_cron_owner' in sql, \
            "orange.sql 缺 fk_cron_owner 外键约束"
        # 验证约束结构 (FK 引用的列正确)
        match = re.search(
            r"CONSTRAINT\s+`?fk_cron_owner`?\s+FOREIGN KEY\s*\([^)]+\)\s+REFERENCES\s+`?t_acc_user`?\s*\(`?name`?\)",
            sql, re.IGNORECASE
        )
        assert match is not None, \
            "fk_cron_owner 约束未正确指向 t_acc_user(name)"

    def test_03_ondelete_set_default_in_sql(self):
        """FK 定义含 ON DELETE SET DEFAULT"""
        sql = self._read()
        match = re.search(
            r"CONSTRAINT\s+`?fk_cron_owner`?.*?ON\s+DELETE\s+SET\s+DEFAULT",
            sql, re.DOTALL | re.IGNORECASE
        )
        assert match is not None, "FK 缺 ON DELETE SET DEFAULT"

    def test_04_contains_system_seed_user(self):
        """INSERT 'system' 内置用户 (FK 默认目标)"""
        sql = self._read()
        # 在 t_acc_user INSERT 段查找 'system' 行
        # 不能只检查 "system" 字符串 (太多误判)
        # DEPLOY-AUDIT P0-1 后种子 INSERT 带显式列清单, 正则同时兼容两种形式
        assert re.search(
            r"INSERT\s+INTO\s+`?t_acc_user`?\s*(\([^)]*\)\s*)?VALUES\s*\(99[^)]*'system'",
            sql, re.IGNORECASE
        ), "orange.sql 缺 system 用户种子"


# =============================================================================
# 3) ALTER 迁移脚本 (已有 DB 升级)
# =============================================================================
class TestAlterMigration:
    """R2-4: rev47_h7_cron_owner_fk.sql 给已有 DB 加 FK"""

    MIGRATION = os.path.join(BACKEND, 'mysqldir', 'rev47_h7_cron_owner_fk.sql')

    def _read(self):
        with open(self.MIGRATION, encoding='utf-8') as f:
            return f.read()

    def test_01_file_exists(self):
        """ALTER 脚本必须存在"""
        assert os.path.isfile(self.MIGRATION), \
            f"ALTER 脚本缺失: {self.MIGRATION}"

    def test_02_insert_system_user(self):
        """ALTER 第 1 步: 插入 system 用户 (INSERT IGNORE)"""
        sql = self._read()
        assert re.search(
            r"INSERT\s+IGNORE\s+INTO\s+`?t_acc_user`?",
            sql, re.IGNORECASE
        ), "ALTER 缺 INSERT IGNORE system 用户"
        # 检查 'system' 字符串
        assert "'system'" in sql, "ALTER 缺 system 用户记录"

    def test_03_fix_dangling_owner(self):
        """ALTER 第 2 步: 把指向已不存在用户的 job_owner 重置为 'admin'"""
        sql = self._read()
        assert re.search(
            r"UPDATE\s+`?t_cron`?.*?SET\s+`?job_owner`?\s*=\s*'admin'",
            sql, re.DOTALL | re.IGNORECASE
        ), "ALTER 缺 dangling owner 重置步骤"

    def test_04_add_foreign_key_constraint(self):
        """ALTER 第 3 步: ADD CONSTRAINT fk_cron_owner ... ON DELETE SET DEFAULT"""
        sql = self._read()
        assert re.search(
            r"ADD\s+CONSTRAINT\s+`?fk_cron_owner`?\s+FOREIGN KEY.*?"
            r"REFERENCES\s+`?t_acc_user`?\s*\(`?name`?\).*?ON\s+DELETE\s+SET\s+DEFAULT",
            sql, re.DOTALL | re.IGNORECASE
        ), "ALTER 缺 fk_cron_owner 外键约束语句"

    def test_05_idempotent_via_information_schema(self):
        """ALTER 用 information_schema 检查, 幂等 (可重跑)"""
        sql = self._read()
        assert 'information_schema' in sql, "ALTER 缺幂等性检查"
        assert 'IF(' in sql.upper() or 'IF @' in sql, \
            "ALTER 缺 IF(...) 条件判断"

    def test_06_verification_status(self):
        """ALTER 最后一步: 验证 status SELECT"""
        sql = self._read()
        assert 'migration_status' in sql, \
            "ALTER 缺迁移验证 SELECT"


# =============================================================================
# 4) 同步性: ORM + SQL + ALTER 三方一致
# =============================================================================
class TestThreeWayConsistency:
    """R2-4: ORM/SQL DDL/ALTER 三方必须一致"""

    def test_01_fk_target_match(self):
        """ORM FK 目标 和 orange.sql FK 引用 必须一致"""
        from app.core.db.database import t_cron

        col = t_cron.job_owner
        fk = list(col.foreign_keys)[0]
        orm_target = fk.column.table.name + '.' + fk.column.name

        with open(os.path.join(BACKEND, 'mysqldir', 'orange.sql'),
                  encoding='utf-8') as f:
            sql = f.read()

        # SQL FK 引用格式: t_acc_user (`name`)
        assert 't_acc_user' in sql and '`name`' in sql, \
            f"orange.sql 未引用 t_acc_user.name; ORM 目标 {orm_target}"
        # 三方 (ORM / 初始化 SQL / ALTER) 都应指向 t_acc_user.name
        assert orm_target == 't_acc_user.name'

    def test_02_default_match(self):
        """ORM default='system' 必须与 SQL DEFAULT 'system' 一致"""
        from app.core.db.database import t_cron

        col = t_cron.job_owner
        orm_default = col.default.arg

        with open(os.path.join(BACKEND, 'mysqldir', 'orange.sql'),
                  encoding='utf-8') as f:
            sql = f.read()

        # t_cron CREATE 段 DEFAULT 'system'
        t_cron_block = re.search(
            r"CREATE TABLE\s+`?t_cron`?.*?ENGINE",
            sql, re.DOTALL | re.IGNORECASE
        ).group(0)
        assert f"DEFAULT '{orm_default}'" in t_cron_block, \
            f"SQL DEFAULT '{orm_default}' 不在 CREATE TABLE t_cron 段"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
