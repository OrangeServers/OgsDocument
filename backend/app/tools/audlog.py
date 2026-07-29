import time
import logging
from app.core.db.insert import osql_in
from app.tools.audsec import safe_db_write  # REV47-T3: 跨模块降级写库统一
from app.tools.at import Log  # REV44-H5: 截断时记录 warning 提示信息丢失


# REV44-H4: 审计日志写库失败的 fallback logger
# 审计是辅助功能, 不能因 osql_in 抛异常而拖垮主业务 (登录/重置密码等)
# REV47-T3: 仅保留向后兼容引用, 实际写库走 audsec.safe_db_write
_audlog_fallback_logger = logging.getLogger('audlog_fallback')


# REVIEW-7-P1-1: 类名 LogsDate -> LogTimestamp, 类内改 now() 方法, 在 host_log 内部调取最新时间戳
#   原 new_date 是在 __init__ 时生成, 一次创建多次调 host_log 后续时间不变
class LogTimestamp:
    def now(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


# REVIEW-7-P0-5: host_log 入口裁剪所有字段, 避免 IPv6 长 IP / 超长 UA 写库报错
# REV44-H5 (R2-5-1): 截断时打 Log.warning 提示信息丢失, 业务方可追查原值
#   原: 字段超长直接 s[:max_len] 截断, 不留任何提示, 出问题难追查
#   修: 截断时 Log.warning 输出原值长度 + 截断后长度, 业务可从日志还原
_TRUNC_DROPPED = 0  # 截断事件计数器 (供监控 / 测试观察)


def _trunc(value, max_len, default='', field_name=None):
    """REV44-H5: 截断超长字段, 并在发生截断时打 Log.warning 提示."""
    if value is None:
        return None
    s = str(value)
    if len(s) > max_len:
        global _TRUNC_DROPPED
        _TRUNC_DROPPED += 1
        # REV44-H5: 截断时记录, 但不阻断主业务 (与 REV44-H4 一致语义)
        Log.logger.warning(
            '[REV44-H5] audlog field %s truncated: orig_len=%d max_len=%d (dropped %d chars)',
            field_name or '?', len(s), max_len, len(s) - max_len,
        )
        return s[:max_len]
    return s


# REV28-L1: 三个日志类 (LoginToolsLog / CzToolsLog / ComToolsLog) 结构几乎相同,
#   提取 _BaseToolsLog 基类, 公共逻辑: 字段截断 + 缺省空串 + 写库时间戳 + osql_in.
#   子类只声明 _TABLE 和 _FIELDS, host_log 入口改为统一 _write(**values).
#
#   _FIELDS 项格式: (column_name, max_len, fallback_empty_bool)
#     - fallback_empty=True 时, _trunc 返回 None 会替换为 '' (兼容历史行为, 避免 DB NOT NULL 报错)
#     - fallback_empty=False 时保留 None (允许空字段入库)
#
#   注意: LoginToolsLog / CzToolsLog / ComToolsLog 的现存子类 (e.g. UserLogin2, ServerListCmd)
#   在 __init__ 中显式调用 XxxToolsLog.__init__(self). 基类不重写 __init__, 继承自 object,
#   所以这种调用方式依然合法, 无需修改调用方.
class _BaseToolsLog(LogTimestamp):
    _TABLE = None  # 子类覆盖: 目标表名
    _FIELDS = ()   # 子类覆盖: [(col, max_len, fallback_empty), ...]

    def _write(self, **values):
        """REV28-L1: 子类 host_log 准备 values 字典后调用 _write.
        自动按 _FIELDS 截断 + 缺省替换 + 附加 log_time + osql_in.

        REV44-H4 + REV47-T3: 写库异常不阻断主业务, 委托 audsec.safe_db_write
        统一降级到 'audlog_fallback' logger. 业务行为不变, 仅消除重复内联.

        REV44-H5: _trunc 传 field_name 便于日志追查.
        """
        kwargs = {}
        for col, max_len, fallback_empty in self._FIELDS:
            v = _trunc(values.get(col), max_len, field_name=col)
            if fallback_empty and not v:
                v = ''
            kwargs[col] = v
        kwargs['log_time'] = self.now()
        # REV47-T3: 委托 audsec, 默认 error level + audlog_fallback logger,
        # reraise=False 保证审计永不阻断主业务 (与历史语义一致)
        safe_db_write(
            lambda: osql_in(self._TABLE, **kwargs),
            op_name='audlog_insert',
            level='error',
            table=self._TABLE,
        )


class LoginToolsLog(_BaseToolsLog):
    _TABLE = 't_login_log'
    _FIELDS = [
        ('log_name', 30, False),
        ('log_nw_ip', 45, True),
        ('log_gw_ip', 45, False),
        ('log_gw_cs', 45, False),
        ('log_agent', 255, True),
        ('log_status', 255, True),
        ('log_reason', 30, False),
    ]

    def host_log(self, log_name, log_nw_ip, log_gw_ip, log_gw_cs, log_agent, log_status, log_msg=None):
        self._write(
            log_name=log_name, log_nw_ip=log_nw_ip, log_gw_ip=log_gw_ip,
            log_gw_cs=log_gw_cs, log_agent=log_agent, log_status=log_status,
            log_reason=log_msg,
        )


class CzToolsLog(_BaseToolsLog):
    _TABLE = 't_cz_log'
    _FIELDS = [
        ('log_name', 30, True),
        ('log_type', 30, True),
        ('log_info', 255, True),
        ('log_details', 255, True),
        ('log_status', 32, True),
        ('log_reason', 255, False),
    ]

    def host_log(self, log_name, log_type, log_info, log_details, log_status, log_msg=None):
        self._write(
            log_name=log_name, log_type=log_type, log_info=log_info,
            log_details=log_details, log_status=log_status, log_reason=log_msg,
        )


class ComToolsLog(_BaseToolsLog):
    _TABLE = 't_command_log'
    _FIELDS = [
        ('log_name', 30, True),
        ('log_type', 30, True),
        ('log_info', 255, True),
        # Nullable asset FK. A multi-host aggregate must remain NULL instead
        # of becoming '' (an invalid FK) or being attributed to one host.
        ('log_host', 30, False),
        ('log_status', 32, True),
        ('log_reason', 255, False),
    ]

    def host_log(self, log_name, log_type, log_info, log_host, log_status, log_msg=None):
        self._write(
            log_name=log_name, log_type=log_type, log_info=log_info,
            log_host=log_host, log_status=log_status, log_reason=log_msg,
        )


# REV46-M26: 模块级 SSH 命令审计 helper (供 shellcmd.ssh_cmd 等工具方法使用)
#   旧实现: ssh_cmd 缺审计, 命令执行无 t_command_log 记录
#   新实现: 提供 log_ssh_audit 工具, 写 t_command_log (ComToolsLog._TABLE).
#   调用方 (ServerCmd / GroupCmd / cron) 传 audit_callback
#   到 ssh_cmd, ssh_cmd 内部在 success/failed/dangerous/timeout 时调用.
def log_ssh_audit(log_name, log_type, log_info, log_host, log_status, log_msg=None):
    """REV46-M26: 直接写 t_command_log (仿 ComToolsLog.host_log 但无需继承).

    与 ComToolsLog.host_log 行为一致: 字段截断 + 缺省替换 + log_time.
    适合工具方法层 (shellcmd.ssh_cmd) 注入, 不需要构造 ComToolsLog 实例.
    """
    com = ComToolsLog.__new__(ComToolsLog)
    com.host_log(
        log_name=log_name, log_type=log_type, log_info=log_info,
        log_host=log_host, log_status=log_status, log_msg=log_msg,
    )
