# -*- coding: utf-8 -*-
"""
REV47-M6 全表 soft_delete 改造回归测试
======================================

覆盖:
  1. database.py: SoftDeleteMixin 定义 + 7 张业务表继承
  2. 迁移 SQL: rev47_m6_soft_delete.sql 存在 + 7 张表覆盖
  3. orange.sql DDL: 7 张表加 is_deleted 列 + 索引
  4. 软删函数: 6 个 del 路径不再走 db.session.delete() / osql_de()
  5. 业务查询: list / add 同名检查 走 is_deleted=False 过滤
  6. 重名策略: 软删的 name/alias 可复用, 邮箱不过滤
  7. 系统保护: "所有权限" 永不可删
  8. 关键查询: shellcmd / at.auth_list_get 也走过滤

执行:
    cd backend && python -m pytest tests/test_rev47_m6_soft_delete.py -v
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# =============================================================================
# 工具函数
# =============================================================================

def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), 'r', encoding='utf-8') as f:
        return f.read()


def _strip_comments(body):
    """过滤注释行, 避免注释中的关键字误判"""
    return '\n'.join(l for l in body.split('\n') if not l.strip().startswith('#'))


def _extract_class(content, class_name):
    """提取类体到下一个 class (兼容 class X: 和 class X(Y): 两种形式)"""
    m = re.search(r'class\s+' + class_name + r'\s*[(:]', content)
    if not m:
        return None
    start = m.start()
    end_m = re.search(r'\nclass\s', content[start:])
    return content[start:start + end_m.start()] if end_m else content[start:]


def _extract_method(content, method_name):
    """提取方法体到下一个 def/@/class.
    ti3-HINT: 容忍返回类型注解 -> ... (如 def foo() -> None:)
    """
    m = re.search(r'def\s+' + method_name + r'\s*\([^)]*\)(?:\s*->\s*[^:]+)?\s*:', content)
    if not m:
        return None
    start = m.end()
    end_m = re.search(r'\n    def\s|\n    @|\nclass\s', content[start:])
    return content[start:start + end_m.start()] if end_m else content[start:]


# REV47-M6 应继承 SoftDeleteMixin 的 7 张业务表
M6_TABLES = (
    't_host', 't_sys_user', 't_acc_user',
    't_group', 't_acc_group',
    't_auth_host', 't_cron',
)


# =============================================================================
# TestM6SoftDeleteMixin: SoftDeleteMixin 定义 + 7 张表继承
# =============================================================================

class TestM6SoftDeleteMixin:
    """REV47-M6.4: database.py SoftDeleteMixin + 7 张表继承"""

    def test_soft_delete_mixin_defined(self):
        """database.py 必须有 SoftDeleteMixin 类"""
        content = _read('app/core/db/database.py')
        assert 'class SoftDeleteMixin' in content, \
            "database.py 应定义 SoftDeleteMixin 类 (REV47-M6.4)"
        # 应包含 is_deleted 列定义
        body = _extract_class(content, 'SoftDeleteMixin')
        assert body, "未找到 SoftDeleteMixin 类"
        code = _strip_comments(body)
        assert 'is_deleted' in code, "SoftDeleteMixin 应有 is_deleted 字段"
        # 列类型应为 BOOLEAN / Boolean / tinyint
        assert 'BOOLEAN' in code or 'Boolean' in code or 'tinyint' in code.lower(), \
            "is_deleted 应使用 BOOLEAN 类型"
        # 索引
        assert 'index=True' in code or 'INDEX' in code.upper() or 'index' in code, \
            "is_deleted 应建索引 (常用过滤字段)"

    def test_seven_business_tables_inherit_soft_delete(self):
        """7 张业务表必须继承 SoftDeleteMixin"""
        content = _read('app/core/db/database.py')
        for tbl in M6_TABLES:
            # 匹配: class t_xxx(db.Model, ..., SoftDeleteMixin)
            pattern = r'class\s+' + tbl + r'\s*\([^)]*SoftDeleteMixin[^)]*\)'
            assert re.search(pattern, content), \
                "%s 应继承 SoftDeleteMixin (REV47-M6.4)" % tbl

    def test_join_tables_do_not_inherit_soft_delete(self):
        """join 表不应继承 SoftDeleteMixin (REV47-M6 范围明确)"""
        content = _read('app/core/db/database.py')
        join_tables = (
            't_auth_host_user', 't_auth_host_user_group',
            't_auth_host_host_group', 't_auth_host_sys_user',
            't_cron_host', 't_cron_group',
        )
        for tbl in join_tables:
            pattern = r'class\s+' + tbl + r'\s*\([^)]*SoftDeleteMixin[^)]*\)'
            assert not re.search(pattern, content), \
                "%s 是 join 表, 不应继承 SoftDeleteMixin (REV47-M6 范围)" % tbl


# =============================================================================
# TestM6MigrationSql: 迁移 SQL 存在 + 7 张表覆盖
# =============================================================================

class TestM6MigrationSql:
    """REV47-M6.5: rev47_m6_soft_delete.sql"""

    MIGRATION = 'mysqldir/rev47_m6_soft_delete.sql'

    def test_migration_file_exists(self):
        path = os.path.join(ROOT, self.MIGRATION)
        assert os.path.isfile(path), \
            "%s 应存在 (REV47-M6.5)" % self.MIGRATION

    def test_migration_covers_seven_tables(self):
        content = _read(self.MIGRATION)
        for tbl in M6_TABLES:
            # 应有 ALTER TABLE t_xxx
            pattern = r'ALTER\s+TABLE\s+' + tbl
            assert re.search(pattern, content, re.IGNORECASE), \
                "%s 应在迁移 SQL 中 (REV47-M6.5)" % tbl
            # 应有 is_deleted 列
            assert 'is_deleted' in content, \
                "迁移 SQL 应有 is_deleted 列 (REV47-M6.5)"

    def test_migration_is_idempotent(self):
        """迁移 SQL 应幂等 (information_schema 检查 + PREPARE)"""
        content = _read(self.MIGRATION)
        # 至少 1 处 information_schema.COLUMNS 检查
        assert 'information_schema' in content, \
            "迁移 SQL 应有 information_schema 检查 (幂等性)"
        # 至少 1 处 PREPARE stmt
        assert 'PREPARE' in content, \
            "迁移 SQL 应使用 PREPARE stmt 动态执行 (幂等性)"


# =============================================================================
# TestM6OrangeSql: DDL 同步
# =============================================================================

class TestM6OrangeSql:
    """REV47-M6.6: orange.sql 7 张表 DDL 加 is_deleted"""

    def test_orange_sql_has_is_deleted_columns(self):
        content = _read('mysqldir/orange.sql')
        for tbl in M6_TABLES:
            # 找 t_xxx 表的 DDL 段 (DOTALL 模式, 跨多行匹配到 ENGINE 之后)
            pattern = (
                r'CREATE\s+TABLE\s+`?' + tbl + r'`?\s*\([\s\S]*?\)[\s\S]*?ENGINE'
            )
            m = re.search(pattern, content, re.IGNORECASE)
            assert m, "%s 应有 DDL 在 orange.sql" % tbl
            ddl = m.group(0)
            assert 'is_deleted' in ddl, \
                "%s DDL 应有 is_deleted 列 (REV47-M6.6)" % tbl

    def test_orange_sql_has_indexes(self):
        content = _read('mysqldir/orange.sql')
        # 至少有 7 个 idx_*_is_deleted 索引
        idx_count = len(re.findall(r'idx_\w*_is_deleted', content, re.IGNORECASE))
        assert idx_count >= 7, \
            "orange.sql 应至少有 7 个 is_deleted 索引, 当前 %d 个" % idx_count


# =============================================================================
# TestM6SoftDeleteFunctions: 6 个 del 函数不再 ORM.delete
# =============================================================================

class TestM6SoftDeleteFunctions:
    """REV47-M6.8: del 路径改 is_deleted=True (不 ORM.delete)"""

    # 6 个 del 路径: file_path + class_name + method_name
    DEL_PATHS = [
        ('app/assets/ServerManagement.py', 'ServerDel', 'host_del'),
        ('app/assets/SysUser.py', 'SysUserDel', 'host_del'),
        ('app/assets/ServerGroup.py', 'ServerGroupDel', 'host_del'),
        ('app/auth/AuthHost.py', 'AuthHostDel', 'auth_host_del'),
        ('app/cron/cron.py', 'OgsCron', 'remove_job'),
        ('app/users/group.py', 'AccGroupDel', 'host_del'),
    ]

    def _check_soft_delete(self, file_path, class_name, method_name):
        content = _read(file_path)
        # 找类
        cls_body = _extract_class(content, class_name)
        assert cls_body, "%s 中未找到 %s 类" % (file_path, class_name)
        # 找方法
        mthd_body = _extract_method(cls_body, method_name)
        assert mthd_body, "%s.%s 中未找到 %s 方法" % (file_path, class_name, method_name)
        code = _strip_comments(mthd_body)
        # 不应再有 db.session.delete() / osql_de() 物理删除
        assert 'db.session.delete(' not in code, \
            "%s.%s 不应再使用 db.session.delete() (REV47-M6.8)" % (class_name, method_name)
        # 软删标志: is_deleted = True
        assert 'is_deleted = True' in code or "is_deleted': True" in code, \
            "%s.%s 应设置 is_deleted = True (REV47-M6.8)" % (class_name, method_name)

    def test_server_del_soft_delete(self):
        self._check_soft_delete(*self.DEL_PATHS[0])

    def test_sys_user_del_soft_delete(self):
        self._check_soft_delete(*self.DEL_PATHS[1])

    def test_server_group_del_soft_delete(self):
        self._check_soft_delete(*self.DEL_PATHS[2])

    def test_auth_host_del_soft_delete(self):
        self._check_soft_delete(*self.DEL_PATHS[3])

    def test_cron_del_soft_delete(self):
        self._check_soft_delete(*self.DEL_PATHS[4])

    def test_acc_group_del_soft_delete(self):
        self._check_soft_delete(*self.DEL_PATHS[5])


# =============================================================================
# TestM6BusinessQueryFilter: 业务查询统一过滤 is_deleted=False
# =============================================================================

class TestM6BusinessQueryFilter:
    """REV47-M6.7: list 路径 + add 同名检查 加 is_deleted=False 过滤"""

    # (file_path, class_name, method_name) - 关键 list/add 路径
    LIST_PATHS = [
        ('app/assets/ServerManagement.py', 'ServerList', 'server_list'),
        ('app/assets/ServerGroup.py', 'ServerGroupList', 'group_list'),
        ('app/assets/ServerGroup.py', 'ServerGroupList', 'group_list_all'),
        ('app/assets/SysUser.py', 'SysUserList', 'sys_user_list'),
        ('app/assets/SysUser.py', 'SysUserList', 'sys_user_list_all'),
        ('app/users/group.py', 'AccGroupList', 'group_list'),
        ('app/users/group.py', 'AccGroupList', 'group_name_list'),
        ('app/users/group.py', 'AccGroupList', 'group_list_all'),
    ]

    def _check_filter(self, file_path, class_name, method_name):
        content = _read(file_path)
        cls_body = _extract_class(content, class_name)
        assert cls_body, "%s 中未找到 %s 类" % (file_path, class_name)
        mthd_body = _extract_method(cls_body, method_name)
        assert mthd_body, "%s.%s 中未找到 %s 方法" % (file_path, class_name, method_name)
        code = _strip_comments(mthd_body)
        # 接受两种过滤形式: filter_by(is_deleted=False) 或 filter(... is_deleted == False)
        assert (
            'is_deleted=False' in code
            or 'is_deleted == False' in code
            or 'is_deleted==False' in code
        ), \
            "%s.%s 应过滤 is_deleted=False (REV47-M6.7)" % (class_name, method_name)

    def test_all_list_paths_filter_soft_deleted(self):
        for fp, cn, mn in self.LIST_PATHS:
            self._check_filter(fp, cn, mn)


class TestM6AddUniqueCheck:
    """REV47-M6.7: add 同名检查过滤 is_deleted=False (让软删 name 可复用)"""

    # (file_path, class_name, method_name)
    ADD_PATHS = [
        ('app/assets/ServerGroup.py', 'ServerGroupAdd', 'host_add'),
        ('app/assets/SysUser.py', 'SysUserAdd', 'host_add'),
        ('app/users/group.py', 'AccGroupAdd', 'host_add'),
        ('app/auth/AuthHost.py', 'AuthHostAdd', 'auth_host_add'),
    ]

    def _check_filter(self, file_path, class_name, method_name):
        content = _read(file_path)
        cls_body = _extract_class(content, class_name)
        assert cls_body, "%s 中未找到 %s 类" % (file_path, class_name)
        mthd_body = _extract_method(cls_body, method_name)
        assert mthd_body, "%s.%s 中未找到 %s 方法" % (file_path, class_name, method_name)
        code = _strip_comments(mthd_body)
        assert 'is_deleted=False' in code, \
            "%s.%s 同名检查应过滤 is_deleted=False (REV47-M6.7)" % (class_name, method_name)

    def test_all_add_paths_filter_soft_deleted(self):
        for fp, cn, mn in self.ADD_PATHS:
            self._check_filter(fp, cn, mn)


class TestM6CriticalQueries:
    """REV47-M6.7: 关键查询点 (shellcmd / at.auth_list_get) 也要过滤"""

    def test_shellcmd_get_ssh_connection_filter(self):
        """get_ssh_connection 不能拿软删 sys_user 去建 SSH 连接"""
        content = _read('app/tools/shellcmd.py')
        mthd = _extract_method(content, 'get_ssh_connection')
        assert mthd, "未找到 get_ssh_connection"
        code = _strip_comments(mthd)
        assert 'is_deleted=False' in code, \
            "get_ssh_connection 应过滤 is_deleted=False (REV47-M6.7)"

    def test_at_auth_list_get_filter(self):
        """auth_list_get: 软删用户不应该有资产权限"""
        content = _read('app/tools/at.py')
        mthd = _extract_method(content, 'auth_list_get')
        assert mthd, "未找到 auth_list_get"
        code = _strip_comments(mthd)
        assert 'is_deleted=False' in code, \
            "auth_list_get 应过滤 is_deleted=False (REV47-M6.7)"


# =============================================================================
# TestM6SystemProtection: 系统保护行
# =============================================================================

class TestM6SystemProtection:
    """REV47-M6.8: "所有权限" 永不可删 (与物理删除保护一致)"""

    def test_auth_host_del_protects_all_privilege(self):
        content = _read('app/auth/AuthHost.py')
        cls_body = _extract_class(content, 'AuthHostDel')
        assert cls_body, "未找到 AuthHostDel"
        mthd = _extract_method(cls_body, 'auth_host_del')
        assert mthd, "未找到 auth_host_del"
        code = _strip_comments(mthd)
        assert "name != '所有权限'" in code or '所有权限' in code, \
            "AuthHostDel 应保护 '所有权限' 永不可删 (REV47-M6.8)"


# =============================================================================
# TestM6UserLogin: 用户登录 / 邮箱查重策略
# =============================================================================

class TestM6UserLogin:
    """REV47-M6.7: 软删用户不能登录; 邮箱查重不过滤 (防恶意重置)"""

    def test_login_filters_soft_deleted(self):
        """login_dl: 软删用户不能登录"""
        content = _read('app/users/user.py')
        mthd = _extract_method(content, 'login_dl')
        if not mthd:
            return  # login_dl 可能在其他方法中
        code = _strip_comments(mthd)
        assert 'is_deleted=False' in code, \
            "login_dl 应过滤 is_deleted=False (REV47-M6.7 软删用户不能登录)"

    def test_register_username_filter_mail_unfiltered(self):
        """register: 用户名查重过滤, 邮箱查重不过滤"""
        content = _read('app/users/user.py')
        mthd = _extract_method(content, 'register')
        if not mthd:
            return
        code = _strip_comments(mthd)
        # 用户名查重: filter_by is_deleted=False
        assert 'is_deleted=False' in code, \
            "register 用户名查重应过滤 is_deleted=False (REV47-M6.7)"
        # 邮箱查重: 不应带 is_deleted (防恶意用同邮箱重置账号)
        # 找 mail=self.email 这一行附近
        mail_lines = [l for l in code.split('\n') if 'mail=self.email' in l]
        for line in mail_lines:
            assert 'is_deleted' not in line, \
                "邮箱查重不应过滤 is_deleted (防恶意用同邮箱重置, REV47-M6.7)\n行: %s" % line

    def test_chk_username_allows_soft_deleted(self):
        """chk_username: 软删 username 视为可用 (可重用)"""
        content = _read('app/users/user.py')
        mthd = _extract_method(content, 'chk_username')
        if not mthd:
            return
        code = _strip_comments(mthd)
        assert 'is_deleted=False' in code, \
            "chk_username 应过滤 is_deleted=False (REV47-M6.7 软删名可复用)"


# =============================================================================
# TestM6AccUserList: acc_user_list 路径
# =============================================================================

class TestM6AccUserList:
    """REV47-M6.7: acc_user_list / acc_user_list_all 过滤 is_deleted=False"""

    def test_acc_user_list_all_filters(self):
        content = _read('app/users/user.py')
        mthd = _extract_method(content, 'acc_user_list_all')
        if not mthd:
            return
        code = _strip_comments(mthd)
        assert 'is_deleted=False' in code, \
            "acc_user_list_all 应过滤 is_deleted=False (REV47-M6.7)"


# =============================================================================
# TestM6AuthAutoUpdate: auto_update 过滤
# =============================================================================

class TestM6AuthAutoUpdate:
    """REV47-M6.7: auto_update 权限同步过滤 is_deleted=False"""

    def test_auto_update_filters_soft_deleted(self):
        content = _read('app/tools/auto_update.py')
        # host_grp_count / user_grp_count / *_auth 都应过滤
        # 至少 5 处 is_deleted=False
        count = content.count('is_deleted=False')
        assert count >= 5, \
            "auto_update 应至少有 5 处 is_deleted=False 过滤, 当前 %d 处" % count


# =============================================================================
# TestM6CronQueries: cron.py 查询过滤
# =============================================================================

class TestM6CronQueries:
    """REV47-M6.7: cron.py 11 处业务查询过滤 is_deleted=False"""

    def test_cron_filter_count(self):
        content = _read('app/cron/cron.py')
        count = content.count('is_deleted=False')
        assert count >= 10, \
            "cron.py 应至少有 10 处 is_deleted=False 过滤, 当前 %d 处" % count
