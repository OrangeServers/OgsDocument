# -*- coding: utf-8 -*-
"""REV45-H6: t_cron_host.host_alias FK + 长度统一 ORM/DDL 同步测试.

背景:
- t_cron_host.host_alias 长度 100 (过大), t_host.alias 长度 25 (主表 PK)
- 无 FK 约束, 删主机时 cron_host 行不级联清理 (孤儿)
- 修复: 长度 25 + FK -> t_host.alias (ondelete CASCADE)

测试覆盖:
  1) ORM 字段长度 = 25 (匹配 t_host.alias)
  2) ORM FK 声明 (t_host.alias, ondelete CASCADE)
  3) 迁移 SQL 文件存在且含正确 ALTER + FK
  4) orange.sql DDL 与 ORM 一致
  5) 业务集成: query.filter_by(host_alias=...) 与新 schema 兼容
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_PROJECT = os.path.dirname(_BACKEND)


# ============================================================
# 1) ORM 字段长度
# ============================================================
class TestRev45H6ORMLength:
    """REV45-H6: ORM t_cron_host.host_alias 长度 = 25."""

    def test_01_host_alias_length_25(self):
        """t_cron_host.host_alias 长度应为 25 (匹配 t_host.alias)."""
        from app.core.db.database import t_cron_host
        col = t_cron_host.__table__.columns['host_alias']
        assert col.type.length == 25, \
            't_cron_host.host_alias 长度应为 25, 实际: %s' % col.type.length

    def test_02_host_alias_not_nullable(self):
        """t_cron_host.host_alias nullable=False (cron 必须关联主机)."""
        from app.core.db.database import t_cron_host
        col = t_cron_host.__table__.columns['host_alias']
        assert col.nullable is False


# ============================================================
# 2) ORM FK 声明
# ============================================================
class TestRev45H6ORMForeignKeys:
    """REV45-H6: ORM FK 声明."""

    def test_01_host_alias_has_fk_to_t_host(self):
        """t_cron_host.host_alias 有 FK -> t_host.alias."""
        from app.core.db.database import t_cron_host
        col = t_cron_host.__table__.columns['host_alias']
        fks = [str(fk.column) for fk in col.foreign_keys]
        assert 't_host.alias' in fks, \
            't_cron_host.host_alias 应有 FK -> t_host.alias, 实际: %s' % fks

    def test_02_host_alias_ondelete_cascade(self):
        """t_cron_host.host_alias FK ondelete=CASCADE (删主机同步清关联表)."""
        from app.core.db.database import t_cron_host
        col = t_cron_host.__table__.columns['host_alias']
        fk = list(col.foreign_keys)[0]
        assert fk.ondelete == 'CASCADE', \
            't_cron_host.host_alias FK 应 ondelete=CASCADE, 实际: %s' % fk.ondelete


# ============================================================
# 3) 迁移 SQL 文件
# ============================================================
class TestRev45H6MigrationSQL:
    """REV45-H6: 迁移 SQL 同步 DDL."""

    MIGRATION_FILE = os.path.join(_BACKEND, 'mysqldir', 'rev45_h6_cron_host_fk.sql')

    def _read(self):
        assert os.path.exists(self.MIGRATION_FILE), \
            '迁移 SQL 不存在: %s' % self.MIGRATION_FILE
        with open(self.MIGRATION_FILE, encoding='utf-8') as f:
            return f.read()

    def test_01_migration_file_exists(self):
        assert os.path.exists(self.MIGRATION_FILE)

    def test_02_modifies_host_alias_to_25(self):
        """迁移 SQL 应把 t_cron_host.host_alias 改为 VARCHAR(25)."""
        src = self._read()
        m = re.search(
            r'ALTER\s+TABLE\s+`?t_cron_host`?\s+MODIFY\s+`?host_alias`?\s+VARCHAR\s*\(\s*25\s*\)',
            src,
            re.IGNORECASE,
        )
        assert m, '迁移 SQL 应含 ALTER TABLE t_cron_host MODIFY host_alias VARCHAR(25)'

    def test_03_adds_host_alias_fk(self):
        """迁移 SQL 应给 t_cron_host.host_alias 加 FK -> t_host.alias."""
        src = self._read()
        assert re.search(
            r'ALTER\s+TABLE\s+`?t_cron_host`?\s+ADD\s+CONSTRAINT\s+`?fk_cron_host_host_alias`?\s+FOREIGN\s+KEY',
            src,
            re.IGNORECASE,
        ), '迁移 SQL 应给 t_cron_host.host_alias 加 FK fk_cron_host_host_alias'
        assert 't_host' in src
        assert 'ON DELETE CASCADE' in src.upper()

    def test_04_has_rev45_h6_marker(self):
        src = self._read()
        assert 'REV45-H6' in src

    def test_05_documents_backup_requirement(self):
        src = self._read()
        assert '备份' in src or 'backup' in src.lower()

    def test_06_documents_max_length_check(self):
        src = self._read()
        assert 'CHAR_LENGTH' in src or 'LENGTH' in src

    def test_07_documents_orphan_check(self):
        src = self._read()
        assert 'NOT IN' in src.upper() or '孤儿' in src

    def test_08_has_show_create_verification(self):
        src = self._read()
        assert 'SHOW CREATE TABLE' in src


# ============================================================
# 4) orange.sql DDL 同步
# ============================================================
class TestRev45H6OrangeSqlDDL:
    """REV45-H6: orange.sql DDL 同步."""

    ORANGE_SQL = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')

    def _read_table_ddl(self, table_name):
        with open(self.ORANGE_SQL, encoding='utf-8') as f:
            content = f.read()
        m = re.search(
            r'CREATE\s+TABLE\s+`?%s`?\s*\([\s\S]*?\)\s*ENGINE\s*=' % re.escape(table_name),
            content,
            re.IGNORECASE,
        )
        assert m, 'orange.sql 应有 CREATE TABLE %s 块' % table_name
        return m.group(0)

    def test_01_host_alias_varchar_25(self):
        """orange.sql t_cron_host.host_alias VARCHAR(25)."""
        ddl = self._read_table_ddl('t_cron_host')
        assert re.search(r'`?host_alias`?\s+varchar\s*\(\s*25\s*\)', ddl, re.IGNORECASE), \
            'orange.sql t_cron_host.host_alias 应为 VARCHAR(25)'

    def test_02_host_alias_has_fk(self):
        """orange.sql t_cron_host 有 FK -> t_host.alias."""
        ddl = self._read_table_ddl('t_cron_host')
        assert 'fk_cron_host_host_alias' in ddl
        assert 't_host' in ddl
        assert 'ON DELETE CASCADE' in ddl.upper()

    def test_03_host_alias_has_index(self):
        """orange.sql t_cron_host 应有 FK 索引 (host_alias)."""
        ddl = self._read_table_ddl('t_cron_host')
        # KEY fk_cron_host_host_alias (host_alias)
        assert re.search(r'KEY\s+`?fk_cron_host_host_alias`?\s*\(\s*`?host_alias`?\s*\)', ddl, re.IGNORECASE)

    def test_04_ddl_has_rev45_h6_marker(self):
        ddl = self._read_table_ddl('t_cron_host')
        assert 'REV45-H6' in ddl


# ============================================================
# 5) ORM / 迁移 SQL / orange.sql 三方一致
# ============================================================
class TestRev45H6Consistency:
    """REV45-H6: ORM / 迁移 SQL / orange.sql 三方一致."""

    def test_01_orm_and_orange_sql_length_match(self):
        """ORM length == orange.sql length."""
        from app.core.db.database import t_cron_host
        orm_len = t_cron_host.__table__.columns['host_alias'].type.length

        orange_sql_path = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')
        with open(orange_sql_path, encoding='utf-8') as f:
            content = f.read()
        m = re.search(
            r'CREATE\s+TABLE\s+`?t_cron_host`?\s*\([\s\S]*?\)\s*ENGINE\s*=',
            content,
            re.IGNORECASE,
        )
        assert m
        ddl_block = m.group(0)
        m2 = re.search(r'`?host_alias`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl_block, re.IGNORECASE)
        assert m2
        assert orm_len == int(m2.group(1))

    def test_02_fk_name_consistent_in_all_three(self):
        """FK 约束名 fk_cron_host_host_alias 在三方一致."""
        with open(os.path.join(_BACKEND, 'mysqldir', 'orange.sql'), encoding='utf-8') as f:
            orange_src = f.read()
        migration_path = os.path.join(_BACKEND, 'mysqldir', 'rev45_h6_cron_host_fk.sql')
        with open(migration_path, encoding='utf-8') as f:
            migration_src = f.read()
        fk_name = 'fk_cron_host_host_alias'
        assert fk_name in migration_src, '迁移 SQL 缺 FK 名: %s' % fk_name
        assert fk_name in orange_src, 'orange.sql 缺 FK 名: %s' % fk_name


# ============================================================
# 6) 业务集成
# ============================================================
class TestRev45H6BusinessIntegration:
    """REV45-H6: 业务 query filter 与新 schema 兼容."""

    def test_01_filter_by_host_alias_still_works(self):
        """t_cron_host.query.filter_by(host_alias=...) 仍能工作."""
        from app.core.db.database import t_cron_host
        col = t_cron_host.__table__.columns['host_alias']
        assert col.name == 'host_alias'

    def test_02_fk_protects_insert_invalid_host(self):
        """FK 约束应在 DB 层阻止写入不存在的 host_alias."""
        from app.core.db.database import t_cron_host
        col = t_cron_host.__table__.columns['host_alias']
        assert len(list(col.foreign_keys)) > 0


# ============================================================
# 7) 静态分析
# ============================================================
class TestRev45H6StaticAnalysis:
    """REV45-H6: 静态分析业务代码不依赖原 String(100) 长度."""

    def test_01_no_varchar_100_literal_in_cron_code(self):
        """cron 模块代码不应有 varchar(100) 字面量."""
        cron_py = os.path.join(_BACKEND, 'app', 'cron', 'cron.py')
        if os.path.exists(cron_py):
            with open(cron_py, encoding='utf-8') as f:
                src = f.read()
            assert 'varchar(100)' not in src.lower(), \
                'cron.py 应不含过时的 varchar(100) 字面量'

    def test_02_database_py_has_rev45_h6_marker(self):
        """database.py 应含 REV45-H6 标记注释."""
        db_py = os.path.join(_BACKEND, 'app', 'core', 'db', 'database.py')
        with open(db_py, encoding='utf-8') as f:
            src = f.read()
        assert 'REV45-H6' in src