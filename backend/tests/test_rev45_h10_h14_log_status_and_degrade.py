# -*- coding: utf-8 -*-
"""REV45 P1 修复单测: H10 (log_status 列宽统一) + H14 (osql_up/in 降级 Log.warning).

H10 (R2-6-4): t_cz_log.log_status 列宽 10 -> 32, 与 audlog CzToolsLog._FIELDS 一致.
H14 (R2-6-6): osql_up/in 降级模式 (OGS_*_STRICT=false) 过滤未知字段时打 Log.warning.
"""
import os
from unittest.mock import patch

import pytest


# =============================================================================
# H10: t_cz_log.log_status 列宽
# =============================================================================
class TestCzLogLogStatusColumnWidth:
    """R2-6-4: t_cz_log.log_status 列宽应 ≥ audlog CzToolsLog._FIELDS 中的 max_len (32)."""

    def test_cz_log_log_status_column_width(self):
        """t_cz_log.log_status 列宽应 >= 32."""
        from app.core.db.database import t_cz_log
        col = t_cz_log.__table__.columns['log_status']
        # Column type length
        col_len = col.type.length
        assert col_len is not None and col_len >= 32, \
            f"REV45-H10: t_cz_log.log_status 列宽应 >= 32, 实际 {col_len}"

    def test_cz_log_log_status_consistent_with_audlog(self):
        """t_cz_log.log_status 列宽应 >= audlog CzToolsLog._FIELDS 中 log_status 的 max_len."""
        from app.core.db.database import t_cz_log
        from app.tools.audlog import CzToolsLog

        # 找到 CzToolsLog._FIELDS 中 log_status 的 max_len
        audlog_max_len = None
        for col_name, max_len, _ in CzToolsLog._FIELDS:
            if col_name == 'log_status':
                audlog_max_len = max_len
                break
        assert audlog_max_len is not None, \
            "CzToolsLog._FIELDS 应有 log_status 字段"

        col_len = t_cz_log.__table__.columns['log_status'].type.length
        assert col_len >= audlog_max_len, \
            f"REV45-H10: t_cz_log.log_status 列宽 {col_len} 应 >= audlog 写库 max_len {audlog_max_len}"

    def test_command_log_log_status_column_width(self):
        """t_command_log.log_status 列宽应足够 (sanity check)."""
        from app.core.db.database import t_command_log
        from app.tools.audlog import ComToolsLog

        audlog_max_len = None
        for col_name, max_len, _ in ComToolsLog._FIELDS:
            if col_name == 'log_status':
                audlog_max_len = max_len
                break
        if audlog_max_len is None:
            pytest.skip("ComToolsLog._FIELDS 无 log_status 字段")

        col_len = t_command_log.__table__.columns['log_status'].type.length
        assert col_len >= audlog_max_len, \
            f"t_command_log.log_status 列宽 {col_len} 应 >= audlog 写库 max_len {audlog_max_len}"


# =============================================================================
# H14: osql_up/in 降级 Log.warning
# =============================================================================
class TestOsqlDegradeModeLogsWarning:
    """R2-6-6: osql_up/in 降级模式 (OGS_*_STRICT=false) 过滤未知字段时打 Log.warning."""

    def test_osql_up_degrade_mode_logs_warning(self, monkeypatch):
        """osql_up 在 OGS_OSQL_UP_STRICT=false 降级时, 应打 Log.warning 含被丢字段名."""
        # 设置降级模式
        monkeypatch.setenv('OGS_OSQL_UP_STRICT', 'false')

        import importlib
        import app.core.db.insert as _insert_mod
        importlib.reload(_insert_mod)
        from app.core.db.insert import osql_up

        with patch('app.tools.at.Log.logger') as mock_logger:
            # 故意传未知字段, 应触发降级
            try:
                osql_up('t_acc_user', {'name': 'nonexistent_user'}, {
                    'name': 'new_name',
                    'unknown_field_xyz': 'should_be_dropped',  # 未知字段
                })
            except Exception:
                # 业务异常 (user 不存在) 不重要, 我们只关心 Log.warning
                pass

        # Log.warning 应被调用
        assert mock_logger.warning.called, \
            "REV45-H14: osql_up 降级模式应打 Log.warning"
        # 检查 warning 含 REV45-H14 标记 + 字段名
        all_msgs = []
        for call in mock_logger.warning.call_args_list:
            args = list(call[0]) + list(call[1].values())
            all_msgs.append(' '.join(str(a) for a in args))
        full = ' '.join(all_msgs)
        assert 'REV45-H14' in full, \
            f"warning 应含 REV45-H14 标记, 实际: {full}"
        assert 'unknown_field_xyz' in full, \
            f"warning 应含被丢字段名 unknown_field_xyz, 实际: {full}"

    def test_osql_in_degrade_mode_logs_warning(self, monkeypatch):
        """osql_in 在 OGS_OSQL_IN_STRICT=false 降级时, 应打 Log.warning."""
        monkeypatch.setenv('OGS_OSQL_IN_STRICT', 'false')

        import importlib
        import app.core.db.insert as _insert_mod
        importlib.reload(_insert_mod)
        from app.core.db.insert import osql_in

        with patch('app.tools.at.Log.logger') as mock_logger:
            try:
                osql_in('t_acc_user', name='test_user', unknown_field_abc='drop_me')
            except Exception:
                pass

        assert mock_logger.warning.called, \
            "REV45-H14: osql_in 降级模式应打 Log.warning"
        all_msgs = []
        for call in mock_logger.warning.call_args_list:
            args = list(call[0]) + list(call[1].values())
            all_msgs.append(' '.join(str(a) for a in args))
        full = ' '.join(all_msgs)
        assert 'REV45-H14' in full, \
            f"warning 应含 REV45-H14 标记, 实际: {full}"
        assert 'unknown_field_abc' in full, \
            f"warning 应含被丢字段名 unknown_field_abc, 实际: {full}"

    def test_osql_up_strict_mode_does_not_log_warning(self, monkeypatch):
        """osql_up 在 OGS_OSQL_UP_STRICT=true 严格模式, 未知字段抛 SqlOpError, 不打降级 warning."""
        # 严格模式 (默认)
        monkeypatch.setenv('OGS_OSQL_UP_STRICT', 'true')

        import importlib
        import app.core.db.insert as _insert_mod
        importlib.reload(_insert_mod)
        from app.core.db.insert import osql_up, SqlOpError

        with patch('app.tools.at.Log.logger') as mock_logger:
            try:
                osql_up('t_acc_user', {'name': 'nonexistent'}, {
                    'name': 'new',
                    'unknown_xyz': 'drop',
                })
            except SqlOpError:
                pass  # 预期抛 SqlOpError
            except Exception:
                pass

        # 严格模式不应有 REV45-H14 warning (因直接 raise 不进降级分支)
        for call in mock_logger.warning.call_args_list:
            args = list(call[0]) + list(call[1].values())
            full = ' '.join(str(a) for a in args)
            assert 'REV45-H14' not in full or 'unknown_xyz' not in full, \
                f"严格模式不应打 REV45-H14 降级 warning, 实际: {full}"

    def test_insert_py_has_h14_marker(self):
        """insert.py 源码中应有 REV45-H14 标记."""
        import inspect
        import app.core.db.insert as _mod
        source = inspect.getsource(_mod)
        # 至少有 2 处 REV45-H14 标记 (osql_in + osql_up)
        count = source.count('REV45-H14')
        assert count >= 2, \
            f"insert.py 应有 ≥ 2 处 REV45-H14 标记, 实际 {count}"


# =============================================================================
# H7-H11-H9 状态确认: 已有对应测试文件, 这里 sanity check 关键 ORM 状态
# =============================================================================
class TestRev45OtherP1Status:
    """H7/H8/H9/H11 已有独立测试, 这里做 ORM sanity check."""

    def test_t_cron_has_job_owner_fk(self):
        """R2-6-1 (REV45-H7): t_cron.job_owner 应有 FK -> t_acc_user.name."""
        from app.core.db.database import t_cron, t_acc_user
        cron_cols = t_cron.__table__.columns
        assert 'job_owner' in cron_cols, \
            "REV45-H7: t_cron.job_owner 字段必须存在"
        fk_targets = [fk.target_fullname for fk in t_cron.__table__.foreign_keys]
        # 至少有一个 FK 指向 t_acc_user.name
        assert any('t_acc_user' in t for t in fk_targets), \
            f"REV45-H7: t_cron 应有 FK -> t_acc_user, 实际 FK: {fk_targets}"

    def test_t_acc_user_has_password_version(self):
        """R2-6-3 (REV45-H9): t_acc_user.password_version 字段应存在."""
        from app.core.db.database import t_acc_user
        cols = t_acc_user.__table__.columns
        assert 'password_version' in cols, \
            "REV45-H9: t_acc_user.password_version 字段必须存在"

    def test_osql_in_signature_accepts_kwargs(self):
        """R2-6-5 (REV45-H11): osql_in 应通过 **kwargs 接收字段 (从 table.__table__.columns 取白名单)."""
        import inspect
        from app.core.db.insert import osql_in
        sig = inspect.signature(osql_in)
        # 应有 **kwargs
        assert any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()), \
            f"REV45-H11: osql_in 应有 **kwargs, 实际: {sig}"
