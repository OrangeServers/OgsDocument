# -*- coding: utf-8 -*-
"""
R2-6 (REV45-H9): t_acc_user.password_version 显式版本号

问题: 密码算法版本只用 hash 形态推断, 无显式版本号:
  - 无法审计/统计各算法版本的账号占比
  - 升级到 scrypt/argon2 时无平滑迁移路径
修复:
  - ORM 加 t_acc_user.password_version INT NOT NULL DEFAULT 2
  - basesec.py 加版本常量 PWD_VERSION_LEGACY_BASE64=1 / PWD_VERSION_BCRYPT_1=2
  - ALTER 脚本 rev47_h9_password_version.sql
测试维度:
  1) basesec.py: 版本常量定义
  2) basesec.py: 当前版本是 BCRYPT_1
  3) ORM: t_acc_user.password_version 列存在
  4) ORM: 列类型 INT, NOT NULL, default=2
  5) ORM: password_version 不在 UNIQUE 索引 (允许重复)
  6) ALTER SQL: 加列 + DEFAULT 2
  7) ALTER SQL: 加索引
  8) ALTER SQL: 把 base64 行重置为 version=1
"""
import os
import re
import sys
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# 1) basesec.py 版本常量
# =============================================================================
class TestBasesecVersionConstants:
    """R2-6: basesec.py 定义密码算法版本号常量"""

    def test_01_legacy_base64_constant(self):
        """PWD_VERSION_LEGACY_BASE64 = 1 (旧 base64 格式)"""
        from app.tools.basesec import PWD_VERSION_LEGACY_BASE64
        assert PWD_VERSION_LEGACY_BASE64 == 1

    def test_02_bcrypt_1_constant(self):
        """PWD_VERSION_BCRYPT_1 = 2 (当前 bcrypt, rounds ≥ 10)"""
        from app.tools.basesec import PWD_VERSION_BCRYPT_1
        assert PWD_VERSION_BCRYPT_1 == 2

    def test_03_current_version_is_bcrypt(self):
        """PWD_VERSION_CURRENT 当前指向 BCRYPT_1"""
        from app.tools.basesec import (
            PWD_VERSION_CURRENT, PWD_VERSION_BCRYPT_1,
        )
        assert PWD_VERSION_CURRENT == PWD_VERSION_BCRYPT_1

    def test_04_versions_distinct(self):
        """所有版本号互相不同 (防重定义)"""
        from app.tools import basesec as bs
        versions = [bs.PWD_VERSION_CURRENT]
        if hasattr(bs, 'PWD_VERSION_SCRYPT_1'):
            versions.append(bs.PWD_VERSION_SCRYPT_1)
        if hasattr(bs, 'PWD_VERSION_ARGON2_1'):
            versions.append(bs.PWD_VERSION_ARGON2_1)
        assert len(set(versions)) == len(versions)


# =============================================================================
# 2) ORM 列
# =============================================================================
class TestOrmPasswordVersion:
    """R2-6: t_acc_user ORM 必须含 password_version 列"""

    def test_01_column_exists(self):
        from app.core.db.database import t_acc_user
        cols = list(t_acc_user.__table__.columns.keys())
        assert 'password_version' in cols, \
            f"t_acc_user 缺 password_version (现有: {cols})"

    def test_02_column_type_is_int(self):
        """password_version 是 INT"""
        from app.core.db.database import t_acc_user
        from sqlalchemy import Integer
        col = t_acc_user.__table__.columns['password_version']
        assert isinstance(col.type, Integer), \
            f"password_version type={col.type!r}, 应为 Integer"

    def test_03_column_not_nullable(self):
        """password_version NOT NULL"""
        from app.core.db.database import t_acc_user
        col = t_acc_user.__table__.columns['password_version']
        assert col.nullable is False

    def test_04_column_default_is_2(self):
        """password_version 默认值 2 (BCRYPT_1)"""
        from app.core.db.database import t_acc_user
        col = t_acc_user.__table__.columns['password_version']
        # ORM 层 default.arg = 2
        assert col.default.arg == 2, \
            f"password_version default={col.default.arg}, 应为 2"

    def test_05_column_has_server_default_2(self):
        """password_version server_default='2'"""
        from app.core.db.database import t_acc_user
        col = t_acc_user.__table__.columns['password_version']
        assert col.server_default.arg == '2', \
            f"password_version server_default={col.server_default.arg!r}"


# =============================================================================
# 3) ALTER 迁移脚本
# =============================================================================
class TestAlterMigration:
    """R2-6: rev47_h9_password_version.sql"""

    MIGRATION = os.path.join(BACKEND, 'mysqldir', 'rev47_h9_password_version.sql')

    def _read(self):
        with open(self.MIGRATION, encoding='utf-8') as f:
            return f.read()

    def test_01_file_exists(self):
        assert os.path.isfile(self.MIGRATION)

    def test_02_adds_password_version_column(self):
        """ALTER 加 password_version INT NOT NULL DEFAULT 2"""
        sql = self._read()
        assert re.search(
            r"ADD\s+COLUMN\s+`?password_version`?\s+INT\s+NOT\s+NULL\s+DEFAULT\s+2",
            sql, re.IGNORECASE
        ), "ALTER 缺 ADD COLUMN password_version INT NOT NULL DEFAULT 2"

    def test_03_adds_index(self):
        """ALTER 加 password_version 索引 (用于按版本统计)"""
        sql = self._read()
        assert re.search(
            r"ADD\s+INDEX\s+`?idx_acc_user_password_version`?",
            sql, re.IGNORECASE
        ), "ALTER 缺 idx_acc_user_password_version 索引"

    def test_04_idempotent_via_information_schema(self):
        """ALTER 必须幂等 (用 information_schema 检查)"""
        sql = self._read()
        assert sql.count('information_schema') >= 2, \
            "ALTER 缺 information_schema 幂等性检查"

    def test_05_resets_base64_users_to_version_1(self):
        """ALTER 把 base64 旧 hash 标记为 version=1"""
        sql = self._read()
        assert re.search(
            r"UPDATE\s+`?t_acc_user`?\s+SET\s+`?password_version`?\s*=\s*1",
            sql, re.IGNORECASE | re.DOTALL
        ), "ALTER 缺 UPDATE 重置 base64 账号"

    def test_06_excludes_bcrypt_hashes_from_reset(self):
        """UPDATE 必须排除 bcrypt 行 (REGEXP $2[aby]$)"""
        sql = self._read()
        # 不区分大小写搜 REGEXP
        assert re.search(
            r"REGEXP\s+['\"][^'\"]*\\\$2\[aby\]",
            sql, re.IGNORECASE
        ), "UPDATE WHERE 缺 bcrypt 排除 REGEXP"

    def test_07_verification_groupby(self):
        """ALTER 末尾必须含 GROUP BY 验证"""
        sql = self._read()
        assert re.search(
            r"GROUP\s+BY\s+`?password_version`?",
            sql, re.IGNORECASE
        ), "ALTER 缺 GROUP BY password_version 验证"


# =============================================================================
# 4) 一致性: ORM default = basesec.PWD_VERSION_BCRYPT_1
# =============================================================================
class TestConsistency:
    """R2-6: ORM default 必须等于 basesec 当前版本"""

    def test_01_orm_default_matches_current_version(self):
        """ORM password_version default = basesec.PWD_VERSION_BCRYPT_1 (= 2)"""
        from app.tools.basesec import PWD_VERSION_BCRYPT_1
        from app.core.db.database import t_acc_user

        col = t_acc_user.__table__.columns['password_version']
        assert col.default.arg == PWD_VERSION_BCRYPT_1, (
            f"ORM default={col.default.arg} != "
            f"basesec.PWD_VERSION_BCRYPT_1={PWD_VERSION_BCRYPT_1}"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
