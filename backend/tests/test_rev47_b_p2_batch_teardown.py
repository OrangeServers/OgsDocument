# -*- coding: utf-8 -*-
"""REV47-B 段: REV45 P2 3 项.

测试范围:
  - M10: t_command_log 加 exit_code / duration_ms 字段
  - M11: osql_in_batch 批量 INSERT 入口
  - M16: gevent session 共享 - teardown_appcontext 调 session.remove()

所有测试均为 ORM 模型 schema 校验 / 函数源码 / Flask app 注册, 不连真实 DB.
"""
import inspect
import os
import re
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


# =============================================================================
# M10: t_command_log.exit_code / duration_ms
# =============================================================================
class TestM10CommandLogExitAndDuration:
    """M10: t_command_log 加 log_exit_code / log_duration_ms 字段."""

    def test_01_log_exit_code_field_exists(self):
        """M10: t_command_log.log_exit_code 字段 (INT, nullable)."""
        from app.core.db.database import t_command_log
        cols = t_command_log.__table__.columns
        assert 'log_exit_code' in cols, "t_command_log 缺 log_exit_code 字段 (M10)"

        col = cols['log_exit_code']
        # INT 类型 (SQLAlchemy 的 INT 在 .type 暴露)
        type_name = type(col.type).__name__
        assert type_name in ('INTEGER', 'INT', 'Integer'), (
            f"log_exit_code 应是 INT, 实际 {type_name}"
        )
        # nullable (历史数据不补)
        assert col.nullable is True, "log_exit_code 应允许 NULL (历史数据不补)"

    def test_02_log_duration_ms_field_exists(self):
        """M10: t_command_log.log_duration_ms 字段 (INT, nullable)."""
        from app.core.db.database import t_command_log
        cols = t_command_log.__table__.columns
        assert 'log_duration_ms' in cols, "t_command_log 缺 log_duration_ms 字段 (M10)"

        col = cols['log_duration_ms']
        type_name = type(col.type).__name__
        assert type_name in ('INTEGER', 'INT', 'Integer'), (
            f"log_duration_ms 应是 INT, 实际 {type_name}"
        )
        assert col.nullable is True, "log_duration_ms 应允许 NULL"

    def test_03_existing_fields_unchanged(self):
        """M10: t_command_log 既有字段不变 (log_name / log_type / log_info / log_host / log_status / log_reason / log_time)."""
        from app.core.db.database import t_command_log
        cols = t_command_log.__table__.columns
        for f in ('id', 'log_name', 'log_type', 'log_info', 'log_host',
                  'log_status', 'log_reason', 'log_time'):
            assert f in cols, f"t_command_log 丢失既有字段 {f!r}"


# =============================================================================
# M11: osql_in_batch 批量 INSERT
# =============================================================================
class TestM11OsqlInBatch:
    """M11: osql_in_batch 批量 INSERT 入口 (单次 commit)."""

    def test_01_function_exists(self):
        """M11: osql_in_batch 函数已注册."""
        from app.core.db.insert import osql_in_batch
        assert callable(osql_in_batch), "osql_in_batch 不可调用"

    def test_02_uses_add_all_single_commit(self):
        """M11: osql_in_batch 用 add_all + 单次 commit (批量性能)."""
        from app.core.db.insert import osql_in_batch
        src = inspect.getsource(osql_in_batch)
        assert 'add_all' in src, "osql_in_batch 应使用 db.session.add_all"
        # 应有 1 次 commit (批量提交)
        commit_count = src.count('db.session.commit()')
        assert commit_count == 1, (
            f"osql_in_batch 应有 1 次 commit (单次提交批量), 实际 {commit_count}"
        )

    def test_03_rollback_on_failure(self):
        """M11: 失败路径调 db.session.rollback() (与 osql_in 一致)."""
        from app.core.db.insert import osql_in_batch
        src = inspect.getsource(osql_in_batch)
        rollback_count = src.count('db.session.rollback()')
        assert rollback_count >= 3, (
            f"osql_in_batch rollback 调用过少 ({rollback_count} 处), 失败路径未回滚"
        )

    def test_04_field_whitelist_validation(self):
        """M11: 字段白名单校验 (与 osql_in 一致, OGS_OSQL_IN_STRICT)."""
        from app.core.db.insert import osql_in_batch
        src = inspect.getsource(osql_in_batch)
        assert 'OGS_OSQL_IN_STRICT' in src, (
            "osql_in_batch 应复用 OGS_OSQL_IN_STRICT 字段白名单开关"
        )

    def test_05_raises_sqloperror_on_invalid_table(self):
        """M11: 未知表名 → SqlOpError (与 osql_in 一致)."""
        from app.core.db.insert import osql_in_batch, SqlOpError
        with pytest.raises(SqlOpError):
            osql_in_batch('t_nonexistent', [{'foo': 'bar'}])

    def test_06_raises_on_non_list_rows(self):
        """M11: rows 非 list/tuple → SqlOpError."""
        from app.core.db.insert import osql_in_batch, SqlOpError
        with pytest.raises(SqlOpError):
            osql_in_batch('t_command_log', 'not a list')

    def test_07_empty_rows_returns_empty_list(self):
        """M11: 空 rows → 立即返回 [], 不触发 DB."""
        from app.core.db.insert import osql_in_batch
        result = osql_in_batch('t_command_log', [])
        assert result == [], f"空 rows 应返回 [], 实际 {result!r}"

    def test_08_raises_on_non_dict_row(self):
        """M11: rows[i] 非 dict → SqlOpError (带索引)."""
        from app.core.db.insert import osql_in_batch, SqlOpError
        # 用合法字段 log_type 避免先撞字段白名单, 中间放一个非 dict
        with pytest.raises(SqlOpError) as exc_info:
            osql_in_batch('t_command_log', [
                {'log_type': 'cmd', 'log_info': 'x', 'log_status': 'ok'},
                'not a dict',
                {'log_type': 'cmd', 'log_info': 'y', 'log_status': 'ok'},
            ])
        # 错误信息应包含索引 1
        assert '[1]' in str(exc_info.value) or 'rows[1]' in str(exc_info.value), (
            f"错误信息应含非 dict 行索引 1, 实际 {exc_info.value}"
        )


# =============================================================================
# M16: gevent session 共享 - teardown_appcontext session.remove()
# =============================================================================
class TestM16GeventSessionTeardown:
    """M16: gevent 协程间 session 隔离, teardown_appcontext 调 session.remove()."""

    def test_01_teardown_appcontext_registered(self):
        """M16: init.py 注册了 teardown_appcontext handler."""
        init_path = os.path.join(BACKEND, 'init.py')
        with open(init_path, encoding='utf-8') as f:
            src = f.read()
        assert '@app.teardown_appcontext' in src, (
            "init.py 未注册 @app.teardown_appcontext (M16 缺失)"
        )

    def test_02_calls_session_remove(self):
        """M16: teardown handler 调 db.session.remove()."""
        init_path = os.path.join(BACKEND, 'init.py')
        with open(init_path, encoding='utf-8') as f:
            src = f.read()
        # 找到 teardown_appcontext 函数体
        match = re.search(
            r'@app\.teardown_appcontext\s*\n\s*def\s+(_?\w+)\s*\([^)]*\)\s*:\s*\n((?:\s{4,}\S.*\n)+)',
            src,
        )
        assert match, "未找到 teardown_appcontext 函数体"
        body = match.group(2)
        assert 'db.session.remove()' in body, (
            f"teardown_appcontext handler 未调 db.session.remove(), body={body!r}"
        )

    def test_03_no_commit_in_teardown(self):
        """M16: teardown handler 不应 commit (R2-9 / REV45-H16 一致)."""
        init_path = os.path.join(BACKEND, 'init.py')
        with open(init_path, encoding='utf-8') as f:
            src = f.read()
        match = re.search(
            r'@app\.teardown_appcontext\s*\n\s*def\s+(_?\w+)\s*\([^)]*\)\s*:\s*\n((?:\s{4,}\S.*\n)+)',
            src,
        )
        assert match, "未找到 teardown_appcontext 函数体"
        body = match.group(2)
        # body 中不应有 commit (除了注释)
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            assert 'db.session.commit()' not in stripped, (
                f"teardown_appcontext 不应 commit (R2-9 / REV45-H16): {stripped!r}"
            )

    def test_04_has_rev47_m16_marker(self):
        """M16: init.py 含 REV47-M16 标记 / 说明."""
        init_path = os.path.join(BACKEND, 'init.py')
        with open(init_path, encoding='utf-8') as f:
            src = f.read()
        assert 'REV47-M16' in src, "init.py 缺 REV47-M16 注释"

    def test_05_explanation_keywords_present(self):
        """M16: 应解释为什么需要 teardown session.remove (gevent 协程)."""
        init_path = os.path.join(BACKEND, 'init.py')
        with open(init_path, encoding='utf-8') as f:
            src = f.read()
        # 关键词任一命中
        keywords = ['gevent', '协程', 'session', 'remove', '连接池']
        # 找到 REV47-M16 注释块
        m_idx = src.find('REV47-M16')
        assert m_idx >= 0
        nearby = src[m_idx:m_idx + 2000]
        assert any(kw in nearby for kw in keywords), (
            "REV47-M16 注释块缺关键词 (gevent/协程/session/remove/连接池)"
        )
