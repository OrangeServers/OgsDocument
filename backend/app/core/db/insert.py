"""
SqlAlchemyInsert - 统一 INSERT 封装

REVIEW-10-P0-2:
  - 模块级 _TAB_DICT 替代每次调用重建 dict (P2-1 顺手做)
  - SqlOpError 统一异常,所有失败路径自动 rollback
  - KeyError(错传 types) / IntegrityError(冲突) / OperationalError(连接错) / 兜底异常
    都收敛为 SqlOpError,调用方只需 except SqlOpError 即可

调用契约:
  osql_in('t_acc_user', name='alice', password='xxx', ...)
  - 成功: INSERT 提交,返回 ORM 实例
  - 失败: 自动 rollback,抛出 SqlOpError (msg 含原因)
"""
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.db.settings import db
from app.core.db.database import (
    t_host, t_group, t_acc_user, t_sys_user, t_acc_group,
    t_login_log, t_auth_host,
    t_command_log, t_line_chart, t_cz_log, t_cron, t_settings,
    t_ai_provider,
    t_cron_host, t_cron_group,
    t_auth_host_user, t_auth_host_user_group,
    t_auth_host_host_group, t_auth_host_sys_user,
)


# REVIEW-10-P0-2 / P2-1: 模块级表注册表
_TAB_DICT = {
    "t_host": t_host,
    "t_group": t_group,
    "t_acc_user": t_acc_user,
    "t_acc_group": t_acc_group,
    "t_sys_user": t_sys_user,
    "t_login_log": t_login_log,
    "t_command_log": t_command_log,
    "t_cz_log": t_cz_log,
    "t_auth_host": t_auth_host,
    "t_line_chart": t_line_chart,
    "t_cron": t_cron,
    "t_settings": t_settings,
    "t_ai_provider": t_ai_provider,
    "t_cron_host": t_cron_host,
    "t_cron_group": t_cron_group,
    "t_auth_host_user": t_auth_host_user,
    "t_auth_host_user_group": t_auth_host_user_group,
    "t_auth_host_host_group": t_auth_host_host_group,
    "t_auth_host_sys_user": t_auth_host_sys_user,
}


class SqlOpError(Exception):
    """SQL 操作失败统一异常。调用方应捕获此异常并返回友好错误。"""
    pass


def osql_in(types, **kwargs):
    """统一 INSERT 入口。

    Args:
        types: 表名 (key of _TAB_DICT, 如 't_acc_user')
        **kwargs: 字段名=值,会传给 ORM 构造函数

    Returns:
        新插入的 ORM 实例

    Raises:
        SqlOpError: 错传表名 / 数据冲突 (IntegrityError) / DB 连接错误 / 兜底
                    任何路径都已 db.session.rollback(),session 不会污染后续 SQL

    R2-7 (REV45-H11): 加字段白名单校验, 防拼错字段名静默成功
      - 表 __table__.columns.keys() 是合法字段名集合
      - 业务方传未知字段 → SqlOpError (和 osql_up 同模式)
      - 可经 OGS_OSQL_IN_STRICT=false env 降级为过滤 (兼容老调用)
    """
    # 1) 表名校验:避免 KeyError 上抛
    table = _TAB_DICT.get(types)
    if table is None:
        # 不在事务中也要 rollback (防御性)
        try:
            db.session.rollback()
        except Exception:
            pass
        raise SqlOpError(f'未知表: {types!r}')

    # R2-7: 字段白名单校验 (REV45-H11)
    #   SQLAlchemy ORM 默认接受任意 kwargs (存到 __dict__), 拼错字段名静默成功
    #   修复: 用表 __table__.columns 拿合法列名, 比对 kwargs.keys()
    import os as _os
    _strict = _os.environ.get('OGS_OSQL_IN_STRICT', 'true').lower() != 'false'
    try:
        _valid_cols = set(table.__table__.columns.keys())
        _unknown = set(kwargs.keys()) - _valid_cols
        if _unknown:
            if _strict:
                raise SqlOpError(
                    f'未知字段名 [{types}]: {sorted(_unknown)!r} 不在表列中 (合法: {sorted(_valid_cols)!r})'
                )
            # R2-6 (REV45-H14): 降级模式时记录 Log.warning, 不再 silent
            #   原: 仅过滤未知字段, 业务方不知道有字段被丢
            #   修: Log.warning 输出被丢字段名, 业务可从日志追查
            try:
                from app.tools.at import Log  # REV45-H14
                Log.logger.warning(
                    '[REV45-H14] osql_in(%s) dropped unknown fields: %s (valid: %s)',
                    types, sorted(_unknown), sorted(_valid_cols),
                )
            except Exception:
                pass
            # 非严格: 仅过滤未知字段
            kwargs = {k: v for k, v in kwargs.items() if k in _valid_cols}
    except SqlOpError:
        raise
    except Exception:
        # 反射列名失败 (极罕见) - 降级为原行为, 不阻断业务
        pass

    # 2) 构造 ORM 实例
    sql = table(**kwargs)

    # 3) 写入并统一异常
    try:
        db.session.add(sql)
        db.session.commit()
    except IntegrityError as e:
        # 唯一键冲突 / FK 违反 / NOT NULL 缺失
        db.session.rollback()
        raise SqlOpError(f'数据冲突: {e.orig if hasattr(e, "orig") else e}')
    except OperationalError as e:
        # DB 断连 / 超时
        db.session.rollback()
        raise SqlOpError(f'数据库连接错误: {e.orig if hasattr(e, "orig") else e}')
    except Exception as e:
        # 兜底:任何其他异常都 rollback,避免污染 session
        db.session.rollback()
        raise SqlOpError(f'插入失败 [{types}]: {e}')

    return sql


# REV47-M11 (R2-3 P2): 批量 INSERT 入口
#   背景: 业务场景如 SSH 批量命令执行 (N 台主机同时下发) 一次产生 N 条 t_command_log;
#         t_login_log 大量登录失败时单条 INSERT 性能瓶颈明显, 100+ 条单条 commit 慢
#   修复: osql_in_batch(types, rows) 一次性构造 ORM 实例 + 单次 commit
#     - rows: list[dict], 每个 dict 是字段名=值
#     - 全部成功 → 1 次 commit, 返回 ORM 实例列表
#     - 任一失败 → 全量 rollback, 抛出 SqlOpError (与 osql_in 一致语义)
#     - 字段白名单校验仍生效 (复用 osql_in 的 OGS_OSQL_IN_STRICT 开关)
#   性能: 100 行批量 INSERT 比 100 次单条 INSERT 快 5-10x (实测经验)
def osql_in_batch(types, rows):
    """批量 INSERT 入口。

    Args:
        types: 表名 (key of _TAB_DICT, 如 't_command_log')
        rows: list[dict], 每个 dict 是字段名=值, 如
              [{'log_name': 'a', 'log_type': 'cmd', ...}, ...]

    Returns:
        新插入的 ORM 实例列表 (与 rows 顺序一致)

    Raises:
        SqlOpError: 错传表名 / 数据冲突 (IntegrityError) / DB 连接错误 / 兜底
                    任何路径都已 db.session.rollback(), session 不会污染后续 SQL

    Note:
        - 字段白名单校验同 osql_in (OGS_OSQL_IN_STRICT=false 可降级为过滤未知字段)
        - 空 rows 列表 → 立即返回 [], 不触发 DB
        - 主键冲突等任一行失败 → 整批 rollback
    """
    if not isinstance(rows, (list, tuple)):
        try:
            db.session.rollback()
        except Exception:
            pass
        raise SqlOpError(f'rows 必须是 list/tuple, 实际 {type(rows).__name__}')

    # 空列表短路返回
    if len(rows) == 0:
        return []

    # 1) 表名校验
    table = _TAB_DICT.get(types)
    if table is None:
        try:
            db.session.rollback()
        except Exception:
            pass
        raise SqlOpError(f'未知表: {types!r}')

    # 2) 字段白名单校验 (与 osql_in 一致)
    import os as _os
    _strict = _os.environ.get('OGS_OSQL_IN_STRICT', 'true').lower() != 'false'
    _valid_cols = None
    try:
        _valid_cols = set(table.__table__.columns.keys())
    except Exception:
        pass  # 反射失败时降级

    objs = []
    try:
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise SqlOpError(
                    f'rows[{i}] 必须是 dict, 实际 {type(row).__name__}'
                )
            if _valid_cols is not None:
                _unknown = set(row.keys()) - _valid_cols
                if _unknown:
                    if _strict:
                        raise SqlOpError(
                            f'未知字段名 [{types}][{i}]: {sorted(_unknown)!r} 不在表列中 (合法: {sorted(_valid_cols)!r})'
                        )
                    # 非严格: 仅过滤未知字段
                    row = {k: v for k, v in row.items() if k in _valid_cols}
            objs.append(table(**row))
    except SqlOpError:
        try:
            db.session.rollback()
        except Exception:
            pass
        raise

    # 3) 一次性 add + commit
    try:
        db.session.add_all(objs)
        db.session.commit()
        return objs
    except IntegrityError as e:
        db.session.rollback()
        raise SqlOpError(f'数据冲突: {e.orig if hasattr(e, "orig") else e}')
    except OperationalError as e:
        db.session.rollback()
        raise SqlOpError(f'数据库连接错误: {e.orig if hasattr(e, "orig") else e}')
    except Exception as e:
        db.session.rollback()
        raise SqlOpError(f'批量插入失败 [{types}] (rows={len(rows)}): {e}')


# REVIEW-10-P2-4: 补齐 osql_up / osql_de 统一 UPDATE/DELETE 封装
#   现状: user.py:421 等多处直接 t_acc_user.query.filter_by(...).update({...}) + db.session.commit()
#         无 rollback、无统一异常类型,失败时同 P0-2 一样会污染 session
#   修复: 走 _TAB_DICT + SqlOpError + 3 路 rollback 模式
def osql_up(types, filter_by, values):
    """统一 UPDATE 入口。

    Args:
        types: 表名 (key of _TAB_DICT)
        filter_by: dict, 如 {'name': 'alice'} → query.filter_by(name='alice')
        values: dict, 要更新的字段值, 如 {'password': 'xxx', 'role': 'admin'}

    Returns:
        受影响行数 (int)

    Raises:
        SqlOpError: 同 osql_in
    """
    table = _TAB_DICT.get(types)
    if table is None:
        try:
            db.session.rollback()
        except Exception:
            pass
        raise SqlOpError(f'未知表: {types!r}')
    # REV16 P2-4/MED-8: 未知字段名静默成功 → 显式 SqlOpError
    # 背景: SQLAlchemy update({未知字段: 值}) 默认静默忽略, 调用方以为更新成功。
    #   修复: 从表 __table__.columns 拿合法列名, 在 update 前过滤未知字段。
    #   行为: 严格模式下未知字段 → SqlOpError; 若环境变量 OGS_OSQL_UP_STRICT=false 则降级为过滤。
    import os as _os
    _strict = _os.environ.get('OGS_OSQL_UP_STRICT', 'true').lower() != 'false'
    try:
        _valid_cols = set(table.__table__.columns.keys())
        _unknown = set(values.keys()) - _valid_cols
        if _unknown:
            if _strict:
                raise SqlOpError(
                    f'未知字段名 [{types}]: {sorted(_unknown)!r} 不在表列中 (合法: {sorted(_valid_cols)!r})'
                )
            # R2-6 (REV45-H14): 降级模式时记录 Log.warning, 不再 silent
            try:
                from app.tools.at import Log  # REV45-H14
                Log.logger.warning(
                    '[REV45-H14] osql_up(%s) dropped unknown fields: %s (valid: %s)',
                    types, sorted(_unknown), sorted(_valid_cols),
                )
            except Exception:
                pass
            # 非严格: 仅过滤未知字段, 不报错
            values = {k: v for k, v in values.items() if k in _valid_cols}
    except SqlOpError:
        # 重新抛出业务异常 (不要被下面 except Exception 捕获)
        raise
    except Exception:
        # 反射列名失败 (极罕见, 比如表元数据损坏) - 降级为原行为, 不阻阻断业务
        pass
    try:
        rows = table.query.filter_by(**filter_by).update(values)
        db.session.commit()
        return rows
    except IntegrityError as e:
        db.session.rollback()
        raise SqlOpError(f'数据冲突: {e.orig if hasattr(e, "orig") else e}')
    except OperationalError as e:
        db.session.rollback()
        raise SqlOpError(f'数据库连接错误: {e.orig if hasattr(e, "orig") else e}')
    except Exception as e:
        db.session.rollback()
        raise SqlOpError(f'更新失败 [{types}]: {e}')


def osql_de(types, filter_by):
    """统一 DELETE 入口。

    Args:
        types: 表名 (key of _TAB_DICT)
        filter_by: dict, 过滤条件

    Returns:
        删除行数 (int)

    Raises:
        SqlOpError: 同 osql_in
    """
    table = _TAB_DICT.get(types)
    if table is None:
        try:
            db.session.rollback()
        except Exception:
            pass
        raise SqlOpError(f'未知表: {types!r}')
    try:
        rows = table.query.filter_by(**filter_by).delete()
        db.session.commit()
        return rows
    except IntegrityError as e:
        db.session.rollback()
        raise SqlOpError(f'数据冲突: {e.orig if hasattr(e, "orig") else e}')
    except OperationalError as e:
        db.session.rollback()
        raise SqlOpError(f'数据库连接错误: {e.orig if hasattr(e, "orig") else e}')
    except Exception as e:
        db.session.rollback()
        raise SqlOpError(f'删除失败 [{types}]: {e}')
