# -*- coding: utf-8 -*-
"""REV45-H3/H4/H5: FK + 长度统一 ORM/DDL 同步测试.

背景:
- H3: t_host.group 长度 20 + 无 FK, t_group.name 长度 25
- H4: t_auth_host_*_group 关联表 group_name 长度 100 + 无 FK, 主表 PK 长度 25
- H5: 关联表字段 > 主表 PK, 攻击者可构造超长字符串写入

修复:
- t_host.group 长度 25 + FK -> t_group.name (SET NULL)
- t_auth_host_user.user_name 长度 24 (匹配 t_acc_user.name)
- t_auth_host_user_group.group_name 长度 25 + FK -> t_acc_group.name (CASCADE)
- t_auth_host_host_group.group_name 长度 25 + FK -> t_group.name (CASCADE)
- t_auth_host_sys_user.sys_user_alias 长度 30 (匹配 t_sys_user.alias)

测试覆盖:
  1) ORM 字段长度与主表 PK 长度一致
  2) ORM 字段 FK 声明 (t_host.group / t_auth_host_*_group.group_name)
  3) 迁移 SQL 文件存在且含正确 ALTER + FK
  4) orange.sql DDL 与 ORM 一致
  5) FK ondelete 行为符合预期 (SET NULL / CASCADE)
  6) 业务集成 (query filter 与新 schema 兼容)
"""
import os
import re

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)


# ============================================================
# 1) ORM 字段长度 (5 个字段)
# ============================================================
class TestRev45H3H4H5ORMLength:
    """REV45-H3/H4/H5: ORM 字段长度与主表 PK 一致."""

    def _get_length(self, table_cls, col_name):
        from app.core.db.database import (
            t_host, t_auth_host_user, t_auth_host_user_group,
            t_auth_host_host_group, t_auth_host_sys_user,
        )
        table_map = {
            't_host': t_host,
            't_auth_host_user': t_auth_host_user,
            't_auth_host_user_group': t_auth_host_user_group,
            't_auth_host_host_group': t_auth_host_host_group,
            't_auth_host_sys_user': t_auth_host_sys_user,
        }
        return table_map[table_cls].__table__.columns[col_name].type.length

    def test_01_host_group_length_25(self):
        """H3: t_host.group 长度 25 (匹配 t_group.name)."""
        assert self._get_length('t_host', 'group') == 25

    def test_02_auth_user_name_length_24(self):
        """H5: t_auth_host_user.user_name 长度 24 (匹配 t_acc_user.name)."""
        assert self._get_length('t_auth_host_user', 'user_name') == 24

    def test_03_auth_user_group_name_length_25(self):
        """H4/H5: t_auth_host_user_group.group_name 长度 25 (匹配 t_acc_group.name)."""
        assert self._get_length('t_auth_host_user_group', 'group_name') == 25

    def test_04_auth_host_group_name_length_25(self):
        """H4/H5: t_auth_host_host_group.group_name 长度 25 (匹配 t_group.name)."""
        assert self._get_length('t_auth_host_host_group', 'group_name') == 25

    def test_05_auth_sys_user_alias_length_30(self):
        """H5/M5: t_auth_host_sys_user.sys_user_alias 长度 24 (REV45-H5: 30; REV47-M5: 30->24, 匹配 t_acc_user.alias)."""
        assert self._get_length('t_auth_host_sys_user', 'sys_user_alias') == 24


# ============================================================
# 2) ORM FK 声明
# ============================================================
class TestRev45H3H4ORMForeignKeys:
    """REV45-H3/H4: ORM FK 声明 (3 个外键)."""

    def _get_col(self, table_cls_name, col_name):
        from app.core.db.database import (
            t_host, t_auth_host_user_group, t_auth_host_host_group,
        )
        table_map = {
            't_host': t_host,
            't_auth_host_user_group': t_auth_host_user_group,
            't_auth_host_host_group': t_auth_host_host_group,
        }
        return table_map[table_cls_name].__table__.columns[col_name]

    def test_01_host_group_has_fk_to_t_group(self):
        """H3: t_host.group 有 FK -> t_group.name."""
        col = self._get_col('t_host', 'group')
        fks = [str(fk.column) for fk in col.foreign_keys]
        assert 't_group.name' in fks, \
            't_host.group 应有 FK -> t_group.name, 实际: %s' % fks

    def test_02_host_group_ondelete_set_null(self):
        """H3: t_host.group FK ondelete=SET NULL (删组时 host.group 置空)."""
        col = self._get_col('t_host', 'group')
        fk = list(col.foreign_keys)[0]
        assert fk.ondelete == 'SET NULL', \
            't_host.group FK 应 ondelete=SET NULL, 实际: %s' % fk.ondelete

    def test_03_user_group_name_has_fk_to_t_acc_group(self):
        """H4: t_auth_host_user_group.group_name 有 FK -> t_acc_group.name."""
        col = self._get_col('t_auth_host_user_group', 'group_name')
        fks = [str(fk.column) for fk in col.foreign_keys]
        assert 't_acc_group.name' in fks, \
            't_auth_host_user_group.group_name 应有 FK -> t_acc_group.name, 实际: %s' % fks

    def test_04_user_group_name_ondelete_cascade(self):
        """H4: t_auth_host_user_group.group_name FK ondelete=CASCADE (删组时关联表行清空)."""
        col = self._get_col('t_auth_host_user_group', 'group_name')
        fk = list(col.foreign_keys)[0]
        assert fk.ondelete == 'CASCADE', \
            't_auth_host_user_group.group_name FK 应 ondelete=CASCADE, 实际: %s' % fk.ondelete

    def test_05_host_group_name_has_fk_to_t_group(self):
        """H4: t_auth_host_host_group.group_name 有 FK -> t_group.name."""
        col = self._get_col('t_auth_host_host_group', 'group_name')
        fks = [str(fk.column) for fk in col.foreign_keys]
        assert 't_group.name' in fks, \
            't_auth_host_host_group.group_name 应有 FK -> t_group.name, 实际: %s' % fks

    def test_06_host_group_name_ondelete_cascade(self):
        """H4: t_auth_host_host_group.group_name FK ondelete=CASCADE."""
        col = self._get_col('t_auth_host_host_group', 'group_name')
        fk = list(col.foreign_keys)[0]
        assert fk.ondelete == 'CASCADE', \
            't_auth_host_host_group.group_name FK 应 ondelete=CASCADE, 实际: %s' % fk.ondelete

    def test_07_host_group_nullable(self):
        """H3: t_host.group nullable=True (host 可以不属于任何组)."""
        col = self._get_col('t_host', 'group')
        assert col.nullable is True


# ============================================================
# 3) 迁移 SQL 文件
# ============================================================
class TestRev45H3H4H5MigrationSQL:
    """REV45-H3/H4/H5: 迁移 SQL 同步 DDL."""

    MIGRATION_FILE = os.path.join(_BACKEND, 'mysqldir', 'rev45_h3_h4_h5_fk_length.sql')

    def _read(self):
        assert os.path.exists(self.MIGRATION_FILE), \
            '迁移 SQL 不存在: %s' % self.MIGRATION_FILE
        with open(self.MIGRATION_FILE, encoding='utf-8') as f:
            return f.read()

    def test_01_migration_file_exists(self):
        assert os.path.exists(self.MIGRATION_FILE)

    def test_02_modifies_host_group_to_25(self):
        """迁移 SQL 应把 t_host.group 改为 VARCHAR(25)."""
        src = self._read()
        m = re.search(
            r'ALTER\s+TABLE\s+`?t_host`?\s+MODIFY\s+`?group`?\s+VARCHAR\s*\(\s*25\s*\)',
            src,
            re.IGNORECASE,
        )
        assert m, '迁移 SQL 应含 ALTER TABLE t_host MODIFY group VARCHAR(25)'

    def test_03_adds_host_group_fk(self):
        """迁移 SQL 应给 t_host.group 加 FK -> t_group.name."""
        src = self._read()
        assert re.search(
            r'ALTER\s+TABLE\s+`?t_host`?\s+ADD\s+CONSTRAINT\s+`?fk_host_group`?\s+FOREIGN\s+KEY',
            src,
            re.IGNORECASE,
        ), '迁移 SQL 应给 t_host.group 加 FK fk_host_group'
        assert 't_group' in src
        assert 'ON DELETE SET NULL' in src.upper()

    def test_04_modifies_user_name_to_24(self):
        """迁移 SQL 应把 t_auth_host_user.user_name 改为 VARCHAR(24)."""
        src = self._read()
        m = re.search(
            r'ALTER\s+TABLE\s+`?t_auth_host_user`?\s+MODIFY\s+`?user_name`?\s+VARCHAR\s*\(\s*24\s*\)',
            src,
            re.IGNORECASE,
        )
        assert m, '迁移 SQL 应含 ALTER TABLE t_auth_host_user MODIFY user_name VARCHAR(24)'

    def test_05_modifies_user_group_name_to_25(self):
        """迁移 SQL 应把 t_auth_host_user_group.group_name 改为 VARCHAR(25) + FK."""
        src = self._read()
        assert re.search(
            r'ALTER\s+TABLE\s+`?t_auth_host_user_group`?\s+MODIFY\s+`?group_name`?\s+VARCHAR\s*\(\s*25\s*\)',
            src,
            re.IGNORECASE,
        ), '迁移 SQL 应含 ALTER TABLE t_auth_host_user_group MODIFY group_name VARCHAR(25)'
        assert 'fk_ahug_group_name' in src
        assert 't_acc_group' in src

    def test_06_modifies_host_group_name_to_25(self):
        """迁移 SQL 应把 t_auth_host_host_group.group_name 改为 VARCHAR(25) + FK."""
        src = self._read()
        assert re.search(
            r'ALTER\s+TABLE\s+`?t_auth_host_host_group`?\s+MODIFY\s+`?group_name`?\s+VARCHAR\s*\(\s*25\s*\)',
            src,
            re.IGNORECASE,
        ), '迁移 SQL 应含 ALTER TABLE t_auth_host_host_group MODIFY group_name VARCHAR(25)'
        assert 'fk_ahhg_group_name' in src
        assert 't_group' in src

    def test_07_modifies_sys_user_alias_to_30(self):
        """迁移 SQL 应把 t_auth_host_sys_user.sys_user_alias 改为 VARCHAR(24). REV47-M5: 30->24, 匹配 t_acc_user.alias."""
        src = self._read()
        m = re.search(
            r'ALTER\s+TABLE\s+`?t_auth_host_sys_user`?\s+MODIFY\s+`?sys_user_alias`?\s+VARCHAR\s*\(\s*24\s*\)',
            src,
            re.IGNORECASE,
        )
        assert m, '迁移 SQL 应含 ALTER TABLE t_auth_host_sys_user MODIFY sys_user_alias VARCHAR(24)'

    def test_08_has_rev45_marker(self):
        src = self._read()
        assert 'REV45-H3' in src or 'REV45-H4' in src or 'REV45-H5' in src

    def test_09_documents_backup_requirement(self):
        src = self._read()
        assert '备份' in src or 'backup' in src.lower(), \
            '迁移 SQL 应要求执行前备份'

    def test_10_documents_max_length_check(self):
        """迁移 SQL 应警告字段长度变窄的检查方法 (CHAR_LENGTH)."""
        src = self._read()
        assert 'CHAR_LENGTH' in src or 'LENGTH' in src, \
            '迁移 SQL 应提供 CHAR_LENGTH 检查超长数据的方法'

    def test_11_documents_orphan_check(self):
        """迁移 SQL 应警告加 FK 前清理孤儿数据."""
        src = self._read()
        assert 'NOT IN' in src.upper() or '孤儿' in src or 'orphan' in src.lower(), \
            '迁移 SQL 应警告加 FK 前清理孤儿数据'


# ============================================================
# 4) orange.sql DDL 同步
# ============================================================
class TestRev45H3H4H5OrangeSqlDDL:
    """REV45-H3/H4/H5: orange.sql DDL 同步."""

    ORANGE_SQL = os.path.join(_BACKEND, 'mysqldir', 'orange.sql')

    def _read_table_ddl(self, table_name):
        """读取指定表的完整 CREATE TABLE 块 (到 `) ENGINE=` 结束)."""
        assert os.path.exists(self.ORANGE_SQL)
        with open(self.ORANGE_SQL, encoding='utf-8') as f:
            content = f.read()
        m = re.search(
            r'CREATE\s+TABLE\s+`?%s`?\s*\([\s\S]*?\)\s*ENGINE\s*=' % re.escape(table_name),
            content,
            re.IGNORECASE,
        )
        assert m, 'orange.sql 应有 CREATE TABLE %s 块' % table_name
        return m.group(0)

    def test_01_host_group_varchar_25(self):
        """orange.sql t_host.group VARCHAR(25)."""
        ddl = self._read_table_ddl('t_host')
        assert re.search(r'`?group`?\s+varchar\s*\(\s*25\s*\)', ddl, re.IGNORECASE), \
            'orange.sql t_host.group 应为 VARCHAR(25)'

    def test_02_host_group_has_fk(self):
        """orange.sql t_host 有 FK -> t_group.name."""
        ddl = self._read_table_ddl('t_host')
        assert 'fk_host_group' in ddl
        assert 't_group' in ddl
        assert 'ON DELETE SET NULL' in ddl.upper()

    def test_03_auth_user_user_name_varchar_24(self):
        """orange.sql t_auth_host_user.user_name VARCHAR(24)."""
        ddl = self._read_table_ddl('t_auth_host_user')
        assert re.search(r'`?user_name`?\s+varchar\s*\(\s*24\s*\)', ddl, re.IGNORECASE), \
            'orange.sql t_auth_host_user.user_name 应为 VARCHAR(24)'

    def test_04_auth_user_group_group_name_varchar_25(self):
        """orange.sql t_auth_host_user_group.group_name VARCHAR(25)."""
        ddl = self._read_table_ddl('t_auth_host_user_group')
        assert re.search(r'`?group_name`?\s+varchar\s*\(\s*25\s*\)', ddl, re.IGNORECASE), \
            'orange.sql t_auth_host_user_group.group_name 应为 VARCHAR(25)'

    def test_05_auth_user_group_has_fk_to_t_acc_group(self):
        """orange.sql t_auth_host_user_group 有 FK -> t_acc_group.name."""
        ddl = self._read_table_ddl('t_auth_host_user_group')
        assert 'fk_ahug_group_name' in ddl
        assert 't_acc_group' in ddl
        assert 'ON DELETE CASCADE' in ddl.upper()

    def test_06_auth_host_group_group_name_varchar_25(self):
        """orange.sql t_auth_host_host_group.group_name VARCHAR(25)."""
        ddl = self._read_table_ddl('t_auth_host_host_group')
        assert re.search(r'`?group_name`?\s+varchar\s*\(\s*25\s*\)', ddl, re.IGNORECASE), \
            'orange.sql t_auth_host_host_group.group_name 应为 VARCHAR(25)'

    def test_07_auth_host_group_has_fk_to_t_group(self):
        """orange.sql t_auth_host_host_group 有 FK -> t_group.name."""
        ddl = self._read_table_ddl('t_auth_host_host_group')
        assert 'fk_ahhg_group_name' in ddl
        assert 't_group' in ddl
        assert 'ON DELETE CASCADE' in ddl.upper()

    def test_08_auth_sys_user_alias_varchar_30(self):
        """orange.sql t_auth_host_sys_user.sys_user_alias VARCHAR(24). REV47-M5: 30->24, 匹配 t_acc_user.alias."""
        ddl = self._read_table_ddl('t_auth_host_sys_user')
        assert re.search(r'`?sys_user_alias`?\s+varchar\s*\(\s*24\s*\)', ddl, re.IGNORECASE), \
            'orange.sql t_auth_host_sys_user.sys_user_alias 应为 VARCHAR(24)'

    def test_09_host_ddl_has_rev45_h3_marker(self):
        ddl = self._read_table_ddl('t_host')
        assert 'REV45-H3' in ddl, \
            'orange.sql t_host DDL 应含 REV45-H3 标签'

    def test_10_auth_user_group_ddl_has_rev45_h4_marker(self):
        ddl = self._read_table_ddl('t_auth_host_user_group')
        assert 'REV45-H4' in ddl, \
            'orange.sql t_auth_host_user_group DDL 应含 REV45-H4 标签'

    def test_11_auth_user_ddl_has_rev45_h5_marker(self):
        ddl = self._read_table_ddl('t_auth_host_user')
        assert 'REV45-H5' in ddl, \
            'orange.sql t_auth_host_user DDL 应含 REV45-H5 标签'


# ============================================================
# 5) ORM / 迁移 SQL / orange.sql 三方一致
# ============================================================
class TestRev45H3H4H5Consistency:
    """REV45-H3/H4/H5: ORM / 迁移 SQL / orange.sql 三方一致."""

    def _read_orange_sql(self):
        with open(os.path.join(_BACKEND, 'mysqldir', 'orange.sql'), encoding='utf-8') as f:
            return f.read()

    def _read_migration(self):
        path = os.path.join(_BACKEND, 'mysqldir', 'rev45_h3_h4_h5_fk_length.sql')
        with open(path, encoding='utf-8') as f:
            return f.read()

    def _table_ddl(self, content, table_name):
        m = re.search(
            r'CREATE\s+TABLE\s+`?%s`?\s*\([\s\S]*?\)\s*ENGINE\s*=' % re.escape(table_name),
            content,
            re.IGNORECASE,
        )
        assert m
        return m.group(0)

    def test_01_host_group_length_consistent(self):
        """ORM t_host.group length == orange.sql t_host.group length."""
        from app.core.db.database import t_host
        orm_len = t_host.__table__.columns['group'].type.length
        ddl = self._table_ddl(self._read_orange_sql(), 't_host')
        m = re.search(r'`?group`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl, re.IGNORECASE)
        assert m
        assert orm_len == int(m.group(1))

    def test_02_user_name_length_consistent(self):
        """ORM t_auth_host_user.user_name length == orange.sql length."""
        from app.core.db.database import t_auth_host_user
        orm_len = t_auth_host_user.__table__.columns['user_name'].type.length
        ddl = self._table_ddl(self._read_orange_sql(), 't_auth_host_user')
        m = re.search(r'`?user_name`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl, re.IGNORECASE)
        assert m
        assert orm_len == int(m.group(1))

    def test_03_user_group_name_length_consistent(self):
        from app.core.db.database import t_auth_host_user_group
        orm_len = t_auth_host_user_group.__table__.columns['group_name'].type.length
        ddl = self._table_ddl(self._read_orange_sql(), 't_auth_host_user_group')
        m = re.search(r'`?group_name`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl, re.IGNORECASE)
        assert m
        assert orm_len == int(m.group(1))

    def test_04_host_group_name_length_consistent(self):
        from app.core.db.database import t_auth_host_host_group
        orm_len = t_auth_host_host_group.__table__.columns['group_name'].type.length
        ddl = self._table_ddl(self._read_orange_sql(), 't_auth_host_host_group')
        m = re.search(r'`?group_name`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl, re.IGNORECASE)
        assert m
        assert orm_len == int(m.group(1))

    def test_05_sys_user_alias_length_consistent(self):
        from app.core.db.database import t_auth_host_sys_user
        orm_len = t_auth_host_sys_user.__table__.columns['sys_user_alias'].type.length
        ddl = self._table_ddl(self._read_orange_sql(), 't_auth_host_sys_user')
        m = re.search(r'`?sys_user_alias`?\s+varchar\s*\(\s*(\d+)\s*\)', ddl, re.IGNORECASE)
        assert m
        assert orm_len == int(m.group(1))

    def test_06_fk_name_consistent_in_all_three(self):
        """FK 约束名在 ORM / 迁移 SQL / orange.sql 三方一致."""
        # ORM 用 auto-generated FK name, 我们约定用 fk_host_group 等显式名
        # 检查迁移 SQL 和 orange.sql 使用相同的 FK 名
        migration_src = self._read_migration()
        orange_src = self._read_orange_sql()

        for fk_name in ['fk_host_group', 'fk_ahug_group_name', 'fk_ahhg_group_name']:
            assert fk_name in migration_src, '迁移 SQL 缺 FK 名: %s' % fk_name
            assert fk_name in orange_src, 'orange.sql 缺 FK 名: %s' % fk_name


# ============================================================
# 6) 业务集成: query filter 与新 schema 兼容
# ============================================================
class TestRev45H3H4H5BusinessIntegration:
    """REV45-H3/H4/H5: 业务 query filter 与新 schema 兼容."""

    def test_01_filter_by_group_still_works(self):
        """t_host.query.filter_by(group=...) 仍能工作 (FK 不影响 filter)."""
        from app.core.db.database import t_host
        col = t_host.__table__.columns['group']
        # column 名仍是 'group', 与现有 query 调用兼容
        assert col.name == 'group'

    def test_02_filter_by_user_name_still_works(self):
        """t_auth_host_user.query.filter_by(user_name=...) 仍工作."""
        from app.core.db.database import t_auth_host_user
        col = t_auth_host_user.__table__.columns['user_name']
        assert col.name == 'user_name'

    def test_03_filter_by_group_name_still_works(self):
        """关联表 query.filter_by(group_name=...) 仍工作."""
        from app.core.db.database import (
            t_auth_host_user_group, t_auth_host_host_group,
        )
        assert t_auth_host_user_group.__table__.columns['group_name'].name == 'group_name'
        assert t_auth_host_host_group.__table__.columns['group_name'].name == 'group_name'

    def test_04_filter_by_sys_user_alias_still_works(self):
        from app.core.db.database import t_auth_host_sys_user
        assert t_auth_host_sys_user.__table__.columns['sys_user_alias'].name == 'sys_user_alias'

    def test_05_fk_protects_insert_invalid_group(self):
        """FK 约束应在 DB 层阻止写入不存在的 group_name.

        测试 ORM 列 FK 声明存在 (DB 层执行由 SQLAlchemy 在 commit 时触发).
        """
        from app.core.db.database import (
            t_auth_host_user_group, t_auth_host_host_group,
        )
        # FK 约束存在即足以在 commit 时触发 IntegrityError
        for tbl in (t_auth_host_user_group, t_auth_host_host_group):
            col = tbl.__table__.columns['group_name']
            assert len(list(col.foreign_keys)) > 0, \
                '%s.group_name 应有 FK 约束' % tbl.__tablename__


# ============================================================
# 7) 静态分析: 业务代码不依赖原 String(100) 长度
# ============================================================
class TestRev45H3H4H5StaticAnalysis:
    """REV45-H3/H4/H5: 静态分析业务代码仍能兼容新 schema."""

    def test_01_no_string_literal_100_in_filter_calls(self):
        """业务代码不应在 filter 调用中硬编码 VARCHAR(100)."""
        # 业务代码通常使用 query.filter_by(name=var), 不写 100
        # 但若有人写了 user_name[0:100] 这种 magic number, 也应被审视
        # 此处只检查不出现'varchar(100)'字面量
        for path in [
            'app/users/user.py',
            'app/users/group.py',
            'app/tools/at.py',
            'app/tools/auto_update.py',
        ]:
            full = os.path.join(_BACKEND, path)
            if os.path.exists(full):
                with open(full, encoding='utf-8') as f:
                    src = f.read()
                # 不应该有 varchar(100) 字面量 (已过时)
                assert 'varchar(100)' not in src.lower(), \
                    '%s 应不含过时的 varchar(100) 字面量' % path

    def test_02_at_py_uses_group_name_filter(self):
        """at.py 应用层用 filter_by(group_name=...) 校验权限组存在."""
        at_py = os.path.join(_BACKEND, 'app', 'tools', 'at.py')
        with open(at_py, encoding='utf-8') as f:
            src = f.read()
        # at.py 仍使用 query.filter_by(group_name=...) 查权限组
        assert 'filter_by(group_name=' in src, \
            'at.py 应保留 filter_by(group_name=...) 业务校验'