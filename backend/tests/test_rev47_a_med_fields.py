# -*- coding: utf-8 -*-
"""REV47-A 段: REV45 P1 MED 剩余 4 项数据库字段.

测试范围:
  - M1: t_line_chart.log_name 字段 (按用户维度统计)
  - M2: t_settings.name unique 约束 (1 行限制)
  - M5: t_sys_user.alias 30 -> 24 (与 t_acc_user.alias 统一)
  - M9: t_login_log.log_session_id / log_csrf_nonce 字段 (安全审计)

所有测试均为 ORM 模型 schema 校验, 不连真实 DB.
通过反射 t_line_chart.__table__.columns / t_settings.__table__ 等拿字段定义.
"""
import pytest
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.schema import UniqueConstraint


def test_m1_t_line_chart_log_name_field_exists():
    """M1: t_line_chart 加 log_name 字段 (String(24), nullable, FK -> t_acc_user.name)."""
    from app.core.db.database import t_line_chart, t_acc_user

    cols = t_line_chart.__table__.columns
    assert 'log_name' in cols, "t_line_chart 缺 log_name 字段 (M1)"

    col = cols['log_name']
    # 类型 String(24)
    assert isinstance(col.type, String), f"log_name 应该是 String, 实际 {type(col.type).__name__}"
    assert col.type.length == 24, f"log_name 长度应是 24, 实际 {col.type.length}"
    # nullable
    assert col.nullable is True, "log_name 应允许 NULL (aggregate 行无用户维度)"
    # FK -> t_acc_user.name
    fk_targets = [fk.column.table.name + '.' + fk.column.name for fk in col.foreign_keys]
    assert 't_acc_user.name' in fk_targets, (
        f"log_name 应有 FK -> t_acc_user.name, 实际 {fk_targets}"
    )
    # 有 index
    assert col.index is True, "log_name 应建 index (按用户维度查询)"


def test_m1_t_line_chart_log_name_fk_ondelete_set_null():
    """M1: log_name FK ondelete=SET NULL (删用户不级联清 line_chart)."""
    from app.core.db.database import t_line_chart

    col = t_line_chart.__table__.columns['log_name']
    fk_list = list(col.foreign_keys)
    assert len(fk_list) >= 1
    fk = fk_list[0]
    # ondelete 应是 SET NULL (删 user 时 line_chart.log_name 置 NULL, 不级联删)
    ondelete = fk.ondelete
    assert ondelete is not None and ondelete.upper() == 'SET NULL', (
        f"log_name FK ondelete 应是 SET NULL, 实际 {ondelete}"
    )


def test_m1_t_line_chart_existing_fields_unchanged():
    """M1: t_line_chart 既有字段不变 (chart_date / login_count / user_count / logerr_count)."""
    from app.core.db.database import t_line_chart

    cols = t_line_chart.__table__.columns
    assert 'id' in cols
    assert 'chart_date' in cols
    assert 'login_count' in cols
    assert 'user_count' in cols
    assert 'logerr_count' in cols


def test_m2_t_settings_name_unique_constraint():
    """M2: t_settings.name unique=True (1 行限制, 防业务方误传第二个 default 行)."""
    from app.core.db.database import t_settings

    col = t_settings.__table__.columns['name']
    assert col.unique is True, f"t_settings.name 应有 unique 约束, 实际 unique={col.unique}"
    # 长度 20
    assert col.type.length == 20


def test_m2_t_settings_name_server_default_unchanged():
    """M2: t_settings.name server_default='default' 保持 (与 unique 配合限制 1 行)."""
    from app.core.db.database import t_settings

    col = t_settings.__table__.columns['name']
    # server_default 是 ServerDefault 对象, 取其 arg
    sd = col.server_default
    assert sd is not None, "t_settings.name 缺 server_default"
    sd_arg = str(sd.arg) if hasattr(sd, 'arg') else str(sd)
    assert 'default' in sd_arg.lower(), f"server_default 应是 'default', 实际 {sd_arg}"


def test_m5_t_sys_user_alias_length_24():
    """M5: t_sys_user.alias 30 -> 24 (与 t_acc_user.alias 统一)."""
    from app.core.db.database import t_sys_user, t_acc_user

    sys_alias_len = t_sys_user.__table__.columns['alias'].type.length
    acc_alias_len = t_acc_user.__table__.columns['alias'].type.length
    assert sys_alias_len == 24, f"t_sys_user.alias 应是 24, 实际 {sys_alias_len}"
    assert acc_alias_len == 24, f"t_acc_user.alias 应是 24, 实际 {acc_alias_len}"
    assert sys_alias_len == acc_alias_len, (
        f"t_sys_user.alias={sys_alias_len} 与 t_acc_user.alias={acc_alias_len} 不一致"
    )


def test_m5_t_auth_host_sys_user_sys_user_alias_length_24():
    """M5: t_auth_host_sys_user.sys_user_alias 同步 30 -> 24."""
    from app.core.db.database import t_auth_host_sys_user, t_sys_user

    junction_len = t_auth_host_sys_user.__table__.columns['sys_user_alias'].type.length
    main_len = t_sys_user.__table__.columns['alias'].type.length
    assert junction_len == 24, f"t_auth_host_sys_user.sys_user_alias 应是 24, 实际 {junction_len}"
    assert junction_len == main_len, (
        f"关联表 sys_user_alias={junction_len} 与主表 alias={main_len} 不一致"
    )


def test_m9_t_login_log_log_session_id_field():
    """M9: t_login_log 加 log_session_id 字段 (String(64), nullable)."""
    from app.core.db.database import t_login_log

    cols = t_login_log.__table__.columns
    assert 'log_session_id' in cols, "t_login_log 缺 log_session_id 字段 (M9)"

    col = cols['log_session_id']
    assert isinstance(col.type, String)
    assert col.type.length == 64, f"log_session_id 长度应是 64, 实际 {col.type.length}"
    assert col.nullable is True, "log_session_id 应允许 NULL (历史数据不补)"


def test_m9_t_login_log_log_csrf_nonce_field():
    """M9: t_login_log 加 log_csrf_nonce 字段 (String(64), nullable)."""
    from app.core.db.database import t_login_log

    cols = t_login_log.__table__.columns
    assert 'log_csrf_nonce' in cols, "t_login_log 缺 log_csrf_nonce 字段 (M9)"

    col = cols['log_csrf_nonce']
    assert isinstance(col.type, String)
    assert col.type.length == 64
    assert col.nullable is True


def test_m9_t_login_log_existing_fields_unchanged():
    """M9: t_login_log 既有字段不被破坏."""
    from app.core.db.database import t_login_log

    cols = t_login_log.__table__.columns
    assert 'id' in cols
    assert 'log_name' in cols
    assert 'log_nw_ip' in cols
    assert 'log_agent' in cols
    assert 'log_status' in cols
    assert 'log_reason' in cols
    assert 'log_time' in cols


def test_m1_m2_m5_m9_no_breaking_changes_to_other_tables():
    """M1/M2/M5/M9 不应影响其他表 (除上面明确改动的)."""
    from app.core.db.database import (
        t_host, t_acc_user, t_acc_group, t_group,
        t_command_log, t_cz_log, t_cron, t_cron_host,
        t_auth_host, t_auth_host_user, t_auth_host_user_group,
        t_auth_host_host_group,
    )

    # t_command_log 字段长度 (R2-6-4/REV45-H10: 10 -> 32 与 audlog CzToolsLog._FIELDS 对齐)
    assert t_command_log.__table__.columns['log_status'].type.length == 32
    # t_host.alias 长度 25 不变
    assert t_host.__table__.columns['alias'].type.length == 25
    # t_cron.job_owner 长度 30 不变 (REV45-H7 既有)
    assert t_cron.__table__.columns['job_owner'].type.length == 30
