# -*- coding: utf-8 -*-
"""REV45-H1/H2: t_acc_user.name unique 约束 ORM + DDL 同步测试.

背景:
- REV41 H2: AccUserUpdate 改名时可改成已存在的 name (业务校验绕过即可写入重复)
- 根因: ORM/DB 都缺 unique 约束 (mail 有, name 无)
- 修复: ORM 加 unique=True + index=True; 创建迁移 SQL 同步 DDL;
       更新 orange.sql 全新安装时也建 UNIQUE INDEX

测试覆盖:
  1) ORM t_acc_user.name 字段含 unique + index + nullable=False
  2) 迁移 SQL 文件存在且内容正确 (ADD UNIQUE INDEX uq_t_acc_user_name)
  3) orange.sql t_acc_user 表 DDL 含 UNIQUE KEY (name + mail)
  4) ORM/迁移 SQL/orange.sql 三方一致
  5) business 层与 DB 层双层防御 (REV41 H2 业务校验不变)
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_PROJECT = os.path.dirname(_BACKEND)


# ============================================================
# 1) ORM: t_acc_user.name 字段约束
# ============================================================
class TestRev45H1ORM:
    """REV45-H1: ORM t_acc_user.name 字段声明 unique + index."""

    def _get_name_col(self):
        from app.core.db.database import t_acc_user
        return t_acc_user.__table__.columns['name']

    def _get_mail_col(self):
        from app.core.db.database import t_acc_user
        return t_acc_user.__table__.columns['mail']

    def test_01_name_has_unique_constraint(self):
        """t_acc_user.name 必须有 unique=True (REV45-H1)."""
        col = self._get_name_col()
        assert col.unique is True, \
            't_acc_user.name 应有 unique=True, 实际: %s' % col.unique

    def test_02_name_has_index(self):
        """t_acc_user.name 必须有 index=True (查询加速)."""
        col = self._get_name_col()
        assert col.index is True, \
            't_acc_user.name 应有 index=True, 实际: %s' % col.index

    def test_03_name_not_nullable(self):
        """t_acc_user.name 必须 NOT NULL (登录名不能为空)."""
        col = self._get_name_col()
        assert col.nullable is False, \
            't_acc_user.name 应 nullable=False, 实际: %s' % col.nullable

    def test_04_name_max_length_24(self):
        """t_acc_user.name 长度仍是 24 (REV45 不动长度)."""
        col = self._get_name_col()
        assert col.type.length == 24, \
            't_acc_user.name 长度应为 24, 实际: %s' % col.type.length

    def test_05_mail_also_has_unique(self):
        """对比基准: t_acc_user.mail 也保持 unique=True (REV16 P2-4/MED-3)."""
        col = self._get_mail_col()
        assert col.unique is True, \
            't_acc_user.mail 应有 unique=True (REV16), 实际: %s' % col.unique

    def test_06_alias_not_unique(self):
        """alias 字段无 unique (允许别名重复, 但 name 唯一)."""
        from app.core.db.database import t_acc_user
        col = t_acc_user.__table__.columns['alias']
        # alias 不应有 unique (业务允许 alias 重复, name 唯一)
        assert col.unique in (None, False), \
            't_acc_user.alias 不应有 unique (只有 name 应唯一), 实际: %s' % col.unique

    def test_07_id_not_unique(self):
        """id 字段无 unique (主键自带唯一, 不需要再 unique=True)."""
        from app.core.db.database import t_acc_user
        col = t_acc_user.__table__.columns['id']
        # id 是 primary_key, 自带 unique, SQLAlchemy 不会再加 unique=True
        assert col.primary_key is True


# ============================================================
# 2) 迁移 SQL 文件存在且内容正确
# ============================================================
class TestRev45H1MigrationSQL:
    """REV45-H1: 迁移 SQL 同步 DDL."""

    MIGRATION_FILE = os.path.join(_BACKEND, 'mysqldir', 'rev45_h1_h2_acc_user_unique.sql')

    def _read_migration(self):
        assert os.path.exists(self.MIGRATION_FILE), \
            '迁移 SQL 不存在: %s' % self.MIGRATION_FILE
        with open(self.MIGRATION_FILE, encoding='utf-8') as f:
            return f.read()

    def test_01_migration_file_exists(self):
        """迁移 SQL 文件必须存在."""
        assert os.path.exists(self.MIGRATION_FILE), \
            '应创建 %s' % self.MIGRATION_FILE

    def test_02_contains_alter_table(self):
        """迁移 SQL 含 ALTER TABLE t_acc_user."""
        src = self._read_migration()
        assert re.search(r'ALTER\s+TABLE\s+`?t_acc_user`?', src, re.IGNORECASE), \
            '迁移 SQL 应含 ALTER TABLE t_acc_user'

    def test_03_contains_add_unique_index(self):
        """迁移 SQL 含 ADD UNIQUE INDEX."""
        src = self._read_migration()
        assert re.search(r'ADD\s+UNIQUE\s+INDEX', src, re.IGNORECASE), \
            '迁移 SQL 应含 ADD UNIQUE INDEX'

    def test_04_index_name_is_uq_t_acc_user_name(self):
        """迁移 SQL 索引名必须是 uq_t_acc_user_name (与 ORM 一致)."""
        src = self._read_migration()
        assert 'uq_t_acc_user_name' in src, \
            '迁移 SQL 索引名应为 uq_t_acc_user_name'

    def test_05_migration_targets_name_column(self):
        """迁移 SQL 必须作用在 name 列."""
        src = self._read_migration()
        # 找 `name` 或 (name) 或 `name`)
        assert re.search(r'\(?\s*`?name`?\s*\)?', src), \
            '迁移 SQL 应作用在 name 列'

    def test_06_has_rev45_marker(self):
        """迁移 SQL 含 REV45 标记."""
        src = self._read_migration()
        assert 'REV45' in src, '迁移 SQL 应含 REV45 标签'

    def test_07_has_h1_or_h2_marker(self):
        """迁移 SQL 含 REV45-H1 或 REV45-H2 标记 (注释合并写为 H1/H2 也算)."""
        src = self._read_migration()
        assert ('REV45-H1' in src or 'REV45-H2' in src
                or 'REV45-H1/H2' in src), \
            '迁移 SQL 应含 REV45-H1 或 REV45-H2 标签'

    def test_08_documents_duplicate_data_warning(self):
        """迁移 SQL 应说明已存在重复数据的处理 (避免执行时崩溃)."""
        src = self._read_migration()
        # 必须警告重复数据会导致 ALTER 失败
        assert 'Duplicate' in src or '重复' in src, \
            '迁移 SQL 应警告: 已存在重复数据时 ALTER 会失败'

    def test_09_documents_backup_requirement(self):
        """迁移 SQL 应要求备份."""
        src = self._read_migration()
        assert '备份' in src or 'backup' in src.lower(), \
            '迁移 SQL 应要求执行前备份'

    def test_10_documents_verification_command(self):
        """迁移 SQL 应给出验证命令 (SHOW CREATE TABLE)."""
        src = self._read_migration()
        assert 'SHOW CREATE TABLE' in src, \
            '迁移 SQL 应给出 SHOW CREATE TABLE 验证命令'


# ============================================================
# 3) orange.sql DDL 同步
# ============================================================
class TestRev45H1OrangeSqlDDL:
    """REV45-H1: orange.sql t_acc_user 表 DDL 同步 UNIQUE 索引."""

    ORANGE_SQL = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')

    def _read_acc_user_ddl(self):
        """读取 t_acc_user 表的完整 CREATE TABLE 块 (到 `) ENGINE=` 结束)."""
        assert os.path.exists(self.ORANGE_SQL)
        with open(self.ORANGE_SQL, encoding='utf-8') as f:
            content = f.read()
        # 用 `\) ENGINE=` 作为块结束边界 (避开字段长度里的 `)`)
        m = re.search(
            r'CREATE\s+TABLE\s+`?t_acc_user`?\s*\([\s\S]*?\)\s*ENGINE\s*=',
            content,
            re.IGNORECASE,
        )
        assert m, 'orange.sql 应有 CREATE TABLE t_acc_user 块'
        return m.group(0)

    def test_01_ddl_has_uq_t_acc_user_name(self):
        """orange.sql t_acc_user 表 DDL 含 UNIQUE KEY uq_t_acc_user_name."""
        ddl = self._read_acc_user_ddl()
        assert 'uq_t_acc_user_name' in ddl, \
            'orange.sql t_acc_user DDL 应含 UNIQUE KEY uq_t_acc_user_name'

    def test_02_ddl_has_uq_t_acc_user_mail(self):
        """orange.sql t_acc_user 表 DDL 含 UNIQUE KEY uq_t_acc_user_mail (REV16)."""
        ddl = self._read_acc_user_ddl()
        assert 'uq_t_acc_user_mail' in ddl, \
            'orange.sql t_acc_user DDL 应含 UNIQUE KEY uq_t_acc_user_mail (REV16)'

    def test_03_ddl_mail_length_is_128(self):
        """orange.sql mail 字段长度是 128 (REV16 P2-4/MED-3)."""
        ddl = self._read_acc_user_ddl()
        assert re.search(r'`?mail`?\s+varchar\s*\(\s*128\s*\)', ddl, re.IGNORECASE), \
            'orange.sql mail 字段长度应为 varchar(128) (REV16)'

    def test_04_ddl_name_length_is_24(self):
        """orange.sql name 字段长度是 24 (与 ORM 一致)."""
        ddl = self._read_acc_user_ddl()
        assert re.search(r'`?name`?\s+varchar\s*\(\s*24\s*\)', ddl, re.IGNORECASE), \
            'orange.sql name 字段长度应为 varchar(24)'

    def test_05_ddl_has_rev45_marker(self):
        """orange.sql DDL 含 REV45 注释."""
        ddl = self._read_acc_user_ddl()
        assert 'REV45' in ddl, \
            'orange.sql t_acc_user DDL 应含 REV45 标签注释'


# ============================================================
# 4) ORM / 迁移 SQL / orange.sql 三方一致
# ============================================================
class TestRev45H2Consistency:
    """REV45-H2: ORM / 迁移 SQL / orange.sql 三方一致 (无 drift)."""

    def test_01_orm_and_orange_sql_name_length_match(self):
        """ORM name 长度 (24) == orange.sql name 长度 (24) - 仅 t_acc_user 表."""
        from app.core.db.database import t_acc_user
        orm_len = t_acc_user.__table__.columns['name'].type.length

        orange_sql_path = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')
        with open(orange_sql_path, encoding='utf-8') as f:
            content = f.read()
        # 限定在 t_acc_user 表内查找
        m = re.search(
            r'CREATE\s+TABLE\s+`?t_acc_user`?\s*\([\s\S]*?\)\s*ENGINE\s*=',
            content,
            re.IGNORECASE,
        )
        assert m, 'orange.sql t_acc_user 表 DDL 未找到'
        ddl_block = m.group(0)
        m2 = re.search(r'`?name`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl_block)
        assert m2, 'orange.sql t_acc_user.name 字段长度未找到'
        ddl_len = int(m2.group(1))

        assert orm_len == ddl_len, \
            'ORM name 长度 %d != orange.sql name 长度 %d' % (orm_len, ddl_len)

    def test_02_orm_and_orange_sql_mail_length_match(self):
        """ORM mail 长度 (128) == orange.sql mail 长度 (128) - 仅 t_acc_user 表."""
        from app.core.db.database import t_acc_user
        orm_len = t_acc_user.__table__.columns['mail'].type.length

        orange_sql_path = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')
        with open(orange_sql_path, encoding='utf-8') as f:
            content = f.read()
        m = re.search(
            r'CREATE\s+TABLE\s+`?t_acc_user`?\s*\([\s\S]*?\)\s*ENGINE\s*=',
            content,
            re.IGNORECASE,
        )
        assert m
        ddl_block = m.group(0)
        m2 = re.search(r'`?mail`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl_block)
        assert m2
        ddl_len = int(m2.group(1))

        assert orm_len == ddl_len, \
            'ORM mail 长度 %d != orange.sql mail 长度 %d' % (orm_len, ddl_len)

    def test_03_orm_and_migration_index_name_match(self):
        """ORM unique 索引名 == 迁移 SQL 索引名."""
        migration_path = os.path.join(_BACKEND, 'mysqldir', 'rev45_h1_h2_acc_user_unique.sql')
        assert os.path.exists(migration_path), '迁移 SQL 不存在'
        with open(migration_path, encoding='utf-8') as f:
            migration_src = f.read()

        # ORM 字段 unique=True 会翻译成 uq_<table>_<column> 形式
        # 我们约定固定使用 uq_t_acc_user_name (在迁移 SQL 中显式指定)
        assert 'uq_t_acc_user_name' in migration_src

        # 同时 orange.sql 也应使用同一索引名
        orange_sql_path = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')
        with open(orange_sql_path, encoding='utf-8') as f:
            orange_src = f.read()
        assert 'uq_t_acc_user_name' in orange_src, \
            'orange.sql 应使用与迁移 SQL 一致的索引名 uq_t_acc_user_name'

    def test_04_name_and_mail_both_unique_in_orm(self):
        """ORM 层面 name 和 mail 都 unique (一致)."""
        from app.core.db.database import t_acc_user
        assert t_acc_user.__table__.columns['name'].unique is True
        assert t_acc_user.__table__.columns['mail'].unique is True

    def test_05_name_and_mail_both_unique_in_orange_sql(self):
        """orange.sql DDL 层面 name 和 mail 都 UNIQUE KEY (一致)."""
        orange_sql_path = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')
        with open(orange_sql_path, encoding='utf-8') as f:
            content = f.read()
        # 用 `\) ENGINE=` 作为块结束边界
        m = re.search(
            r'CREATE\s+TABLE\s+`?t_acc_user`?\s*\([\s\S]*?\)\s*ENGINE\s*=',
            content,
            re.IGNORECASE,
        )
        assert m
        ddl = m.group(0)
        assert 'uq_t_acc_user_name' in ddl
        assert 'uq_t_acc_user_mail' in ddl


# ============================================================
# 5) 业务集成: name unique 约束能拦截重复写入
# ============================================================
class TestRev45H1BusinessIntegration:
    """REV45-H1: DB 层 unique 约束拦截重复 name 写入."""

    def test_01_db_create_all_generates_unique_index(self):
        """SQLAlchemy db.create_all() 会根据 ORM unique=True 生成 UNIQUE INDEX DDL.

        验证方法: 检查 Column 的 unique=True 让 SQLAlchemy 在 create table 时
        生成 UNIQUE 约束 DDL.
        """
        from sqlalchemy import create_mock_engine
        from sqlalchemy.schema import CreateTable

        from app.core.db.database import t_acc_user

        # 用 mock engine 抓 DDL
        mock_engine = create_mock_engine('postgresql://', lambda sql, *a, **kw: None)
        ddl_str = str(CreateTable(t_acc_user.__table__).compile(mock_engine))

        # 应包含 UNIQUE 约束 (不同 dialect 关键字可能略有不同, 检查通用形式)
        # PostgreSQL/SQLite 用 "UNIQUE", MySQL 也用 "UNIQUE"
        # 由于 create_mock_engine 用的是 PostgreSQL dialect, 关键字是 "UNIQUE"
        assert 'UNIQUE' in ddl_str.upper(), \
            'db.create_all() 应生成含 UNIQUE 的 DDL, 实际: %s' % ddl_str

    def test_02_orm_declares_index_for_name(self):
        """ORM 层 t_acc_user.name 同时声明 unique=True + index=True.

        双重声明: unique=True 用于约束, index=True 用于查询加速.
        """
        from app.core.db.database import t_acc_user
        col = t_acc_user.__table__.columns['name']
        # unique + index 都要
        assert col.unique is True
        assert col.index is True

    def test_03_rev41_h2_business_validation_still_exists(self):
        """REV41-H2 业务校验 (AccUserUpdate 改名不与他人重复) 仍是第一道防线.

        DB 层 unique 是第二道防线. 业务校验不应被移除.
        """
        # 静态分析 user.py 应仍有 name 重复校验逻辑
        user_py_path = os.path.join(_BACKEND, 'app', 'users', 'user.py')
        with open(user_py_path, encoding='utf-8') as f:
            src = f.read()
        # 应有 name 重复校验 (查 t_acc_user.query.filter_by(name=name))
        assert 'filter_by(name=' in src or 'filter(t_acc_user.name' in src, \
            'user.py 应保留 name 重复校验 (REV41 H2 业务防线)'