# -*- coding=utf8 -*-
"""REV37-H3/H4: 统一 API 响应包装与错误码常量。

设计目标：
  1. 统一错误响应格式（jsonify + 显式 HTTP 状态码）
  2. 集中错误码常量（替代 init.py:67-93 散落 docstring）
  3. 全局 Flask errorhandler 配合（init.py 注册）

调用约定：
  - api_response(data=None, code=ApiCode.OK, msg='ok', status=200)
      成功响应，data 为业务数据，code=0 表示 OK
  - api_error(code, msg, status=None, **extra)
      错误响应，status 自动按 code 映射（OK/未授权=401/权限不足=403/参数错=400/...）
      **extra 可附加 data/detail 字段

向后兼容：
  - 所有 view_func 现在常用 4 种返回：
      A) jsonify({'code': 0, 'msg': 'ok', ...data})
      B) jsonify({'code': 100, 'msg': '...'}), 4xx
      C) dict (无 jsonify, Flask 会自动序列化为 JSON 但无 Content-Type)
      D) tuple ('', 4xx) (WebSocket 拒绝握手专用)
  - 本模块重点统一 A 与 B，C/D 留给后续 REV 渐进迁移。
"""
from flask import jsonify

# REV37-H4: HTTP 状态码与业务错误码的映射（让前端 axios 拦截器可统一走 res.status）
_STATUS_BY_CODE = {
    0: 200,        # OK
    2: 500,        # 内部错误
    3: 401,        # 未授权访问
    4: 403,        # 权限不足
    100: 401,      # 通用业务未授权
    101: 404,      # 用户不存在
    102: 401,      # 密码错误
    103: 409,      # 用户名已存在
    104: 409,      # 邮箱已被注册
    105: 410,      # 验证码过期
    106: 400,      # 验证码错误
    111: 409,      # 资产已存在
    112: 502,      # 连接主机失败
    113: 502,      # 资产密码或其他错误
    121: 404,      # 目录不存在
    131: 403,      # 禁止删除
    132: 409,      # 权限已存在
    141: 409,      # 定时任务已存在
    # REV38-M6: cron/user 模块新错误码状态映射
    142: 429,      # CRON_LOCK_BUSY  - 同名并发加锁中 (用 429 表示"请稍后重试")
    143: 404,      # CRON_NOT_FOUND - 任务不存在
    144: 400,      # CRON_NO_TARGET_HOSTS - 关联主机为空
    145: 500,      # CRON_OPERATION_FAILED - 通用操作失败
    146: 500,      # CRON_INNER_ERROR - 服务器内部错误
    147: 404,      # CRON_NO_RESULT - 暂无执行记录
    148: 404,      # HOST_NOT_FOUND - 主机 ID 不存在
    149: 502,      # CRON_CONNECT_FAILED - SSH 连接失败
    151: 400,      # USER_TYPE_ERROR - 参数类型错误
    201: 500,      # 读取数据库错误
    211: 400,      # 传递类型错误
    231: 409,      # 文件已存在
    232: 409,      # 名称已存在
}


class ApiCode:
    """REV37-H4 / REV38-M6: 业务错误码常量集中定义。

    历史来源：init.py:67-93 散落 docstring 现统一为可 IDE 跳转的常量。
    客户端按需 from app.tools.apierr import ApiCode 引用。
    """
    OK = 0
    INTERNAL_ERROR = 2
    UNAUTHORIZED = 3
    FORBIDDEN = 4
    # 通用业务 (100~109)
    BUSINESS_UNAUTHORIZED = 100
    USER_NOT_FOUND = 101
    WRONG_PASSWORD = 102
    USERNAME_EXISTS = 103
    EMAIL_REGISTERED = 104
    CAPTCHA_EXPIRED = 105
    CAPTCHA_WRONG = 106
    # 资产 (110~119)
    ASSET_EXISTS = 111
    CONNECT_HOST_FAILED = 112
    ASSET_CRED_ERROR = 113
    # 文件 / 路径 (120~129)
    DIR_NOT_FOUND = 121
    # 权限 (130~139)
    DELETE_FORBIDDEN = 131
    PERMISSION_EXISTS = 132
    # 定时任务 (140~149)
    CRON_EXISTS = 141
    # REV38-M6: cron 模块更精细的错误码
    CRON_LOCK_BUSY = 142          # 同名任务并发加锁中
    CRON_NOT_FOUND = 143         # 任务不存在
    CRON_NO_TARGET_HOSTS = 144   # 关联主机为空
    CRON_OPERATION_FAILED = 145  # 通用操作失败
    CRON_INNER_ERROR = 146       # 服务器内部错误
    CRON_NO_RESULT = 147         # 暂无执行记录
    HOST_NOT_FOUND = 148         # 主机 ID 不存在
    CRON_CONNECT_FAILED = 149    # SSH 连接失败
    # REV38-M6: user 模块错误码
    USER_TYPE_ERROR = 151        # 参数类型错误
    # 系统错误 (200~219)
    DB_ERROR = 201
    TYPE_ERROR = 211
    # 文件 / 名称冲突 (230~239)
    FILE_EXISTS = 231
    NAME_EXISTS = 232


def _resolve_status(code, status=None):
    """根据业务错误码解析 HTTP 状态码；status 显式传入则优先。"""
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            return 200
    return _STATUS_BY_CODE.get(int(code), 400)


def api_response(data=None, code=ApiCode.OK, msg='ok', status=200, **extra):
    """REV37-H4: 统一成功响应。

    Args:
        data: 业务数据（dict / list / 标量），会放在 'data' 字段下
        code: 业务码，默认 OK=0
        msg: 提示文本
        status: HTTP 状态码，默认 200
        **extra: 附加字段（如 'count', 'total', 'host_list_msg' 等历史约定 key）
                 注：data 之外的字段会平铺到顶层，与旧 jsonify 风格兼容

    Returns:
        (flask.Response, status) tuple，Flask 会自动序列化 JSON
    """
    payload = {'code': int(code), 'msg': str(msg)}
    if data is not None:
        payload['data'] = data
    payload.update(extra)
    return jsonify(payload), _resolve_status(code, status)


def api_error(code, msg='error', status=None, **extra):
    """REV37-H4: 统一错误响应。

    Args:
        code: 业务错误码（ApiCode.*）
        msg: 错误描述
        status: HTTP 状态码，未传则按 _STATUS_BY_CODE 自动映射
        **extra: 附加字段（如 detail/reason/danger_type 等）

    Returns:
        (flask.Response, status) tuple
    """
    payload = {'code': int(code), 'msg': str(msg)}
    payload.update(extra)
    return jsonify(payload), _resolve_status(code, status)


def make_handler_status(exc_or_code):
    """便捷工具：从 Flask Exception 或已知 code 取 HTTP 状态码。

    REV37-H4: 给 errorhandler(404/500/Exception) 用。
    """
    if hasattr(exc_or_code, 'code'):
        try:
            return int(exc_or_code.code)
        except (TypeError, ValueError):
            return 500
    if isinstance(exc_or_code, int):
        return exc_or_code
    return 500
