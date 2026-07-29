# -*- coding: utf-8 -*-
"""REV47-T3: 跨模块"非关键写库失败降级"统一工具.

背景 (REV46_review.md T3):
  - REV44 H4: audlog 写库失败 -> fallback logger, 不阻断主业务
  - REV46 H20: shellcmd get_ssh_password rehash 写库失败 -> logging.warning 降级
  - 两处都是相同的内联 try/except 模式, 抽到 audsec.py 共用.

设计原则:
  1. 失败永远不阻断主业务 (reraise=False 强制默认)
     - 即便 fallback logger 自身异常, 也被内层 try/except 吃掉
  2. 操作命名空间: op_name + context kwargs 让日志可聚合检索
  3. 双 logger 区分:
     - level='error' + logger='audlog_fallback' (审计, 默认)
     - level='warning' + logger=业务 logger (透明迁移)
  4. callable_ 模式而非直接传 osql_in: 避免在 audsec 内 import core.db,
     也让单元测试可直接传 lambda, 无需 mock 数据库.

与 keypath / pathsec 的关系:
  - keypath 防御"路径不安全"
  - pathsec 防御"路径越界"
  - audsec 防御"非关键写库副作用拖垮主业务"
  三者都是 REV47 跨模块统一工具, 共同目标是消除重复内联模式.
"""
import logging


# REV44-H4: 审计 fallback logger 默认命名空间
# 与历史 audlog._audlog_fallback_logger 一致, 保留日志输出兼容性
_AUDSEC_DEFAULT_LOGGER = 'audlog_fallback'


def safe_db_write(callable_, op_name, *, level='error', logger_name=None,
                  reraise=False, **context):
    """REV47-T3: 安全包裹一次非关键 DB 写, 失败降级到 logger.

    Args:
        callable_: 0-arg callable, 实际执行 DB 写 (e.g. lambda: osql_in(...))
                   接受 callable 而非直接传函数引用, 是为了:
                   (a) 让 audsec 不 import core.db (避免循环依赖);
                   (b) 测试可直接传 lambda, 无需 mock 数据库.
        op_name: 操作名 (e.g. 'audlog_insert', 'ssh_password_rehash'),
                 用于日志聚合检索.
        level: 'error' (审计) / 'warning' (透明迁移) / 'info' / 'debug'.
               大小写不敏感, 无效值降级为 'error'.
        logger_name: logger 命名空间, 默认 'audlog_fallback' (与历史兼容).
                     透明迁移场景可传业务 logger name (e.g. 'shellcmd').
        reraise: True 时失败仍向上抛, 默认 False (降级, 不阻断).
                 审计场景**永远**不 raise (主业务 100% 不能因审计挂).
        **context: 附加到日志的字段 (e.g. table='t_login_log', sys_user_id=42).
                   自动以 'k=v' 格式拼接到日志消息.

    Returns:
        callable_() 的返回值 (成功时), 或 None (失败时, reraise=False).

    Raises:
        永不抛 (reraise=False). 内部异常仅记录到 logger.
        reraise=True 时, 重抛 callable_ 抛出的原始异常.

    Examples:
        # 审计 (REV44-H4 模式)
        safe_db_write(
            lambda: osql_in('t_login_log', **kwargs),
            'audlog_insert',
            table='t_login_log',
        )

        # 透明迁移 (REV46-H20 模式)
        safe_db_write(
            lambda: osql_up('t_sys_user', {'id': uid}, {'host_password': p}),
            'ssh_password_rehash',
            level='warning',
            logger_name='shellcmd',
            sys_user_id=uid,
        )
    """
    # 选择 logger
    log_name = logger_name or _AUDSEC_DEFAULT_LOGGER
    log = logging.getLogger(log_name)

    # 解析 level (大小写不敏感, 无效值降级 ERROR)
    log_level = getattr(logging, level.upper(), logging.ERROR)

    try:
        return callable_()
    except Exception as e:
        # 拼接 context (k=v, ...)
        if context:
            ctx_str = ', '.join('%s=%r' % (k, v) for k, v in context.items())
            msg = 'audsec write failed: op=%s, %s, err=%s' % (op_name, ctx_str, e)
        else:
            msg = 'audsec write failed: op=%s, err=%s' % (op_name, e)

        # 双层 try/except: 即便 logger 自身异常也不阻断主业务
        try:
            log.log(log_level, msg)
        except Exception:
            pass

        if reraise:
            raise
        return None
