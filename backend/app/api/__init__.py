# =============================================================================
# OrangeServer 后端 API 路由统一模型（REV38-M1）
# =============================================================================
# 改造前: 4 个 api 文件的 ROUTES 表 schema 混用
#   - 5-tuple: (url, cls, method, need_auth, is_property)
#   - 6-tuple: (url, cls, method, need_auth, is_property, roles)
#   - init.py 用 route[:5] + route[5] if len(route)>5 兼容，字段含义靠位置记
# 改造后: 统一 RouteRule namedtuple（8 字段），字段含义自解释
#
# 字段说明:
#   url            URL 路径（必须以 / 开头）
#   view_class     视图类（必须含 method 字段指定的实例方法或属性）
#   method         实例方法名或属性名
#   need_auth      是否需登录鉴权（ogs_auth_token 装饰器）
#   is_property    True=属性调用, False=方法调用
#   roles          允许的角色列表（None=所有登录用户，[]=仅登录）
#   description    接口描述（用于 API 文档自动生成）
#   skip_csrf      是否跳过 CSRF 校验（公开接口如 /local/health）
# =============================================================================
from collections import namedtuple
from typing import Any, List, Optional, Type, Union

# REV38-M1: 统一 ROUTES schema 为 namedtuple，字段顺序固定，禁止位置错乱
# REV38-M4: 新增 is_alias 字段标记合法 alias (同一 class.method 注册到多个 URL)
#   默认 False 表示主路由, True 表示兼容期 alias
RouteRule = namedtuple('RouteRule', [
    'url',          # URL 路径
    'view_class',   # 视图类
    'method',       # 方法名/属性名
    'need_auth',    # 是否需鉴权
    'is_property',  # 属性调用 vs 方法调用
    'roles',        # 允许角色, None=所有登录用户
    'description',  # 接口描述（API 文档）
    'skip_csrf',    # 跳过 CSRF（默认 False）
    'is_alias',     # REV38-M4: 是否为 alias 路由（同一 view_class.method 重复注册到多 URL）
])


# REV38-M1: 便捷构造器，默认值覆盖常见场景
# REV38-M4: is_alias 默认 False, 调用方显式声明 alias 时为 True
ViewClassT = Type['object']
RolesT = Optional[List[str]]
MethodNameT = str


def route(url: str, view_class: ViewClassT, method: MethodNameT,
          need_auth: bool = True, is_property: bool = True, roles: RolesT = None,
          description: str = '', skip_csrf: bool = False, is_alias: bool = False) -> 'RouteRule':
    """构造 RouteRule，默认值匹配最常见路由配置。

    Args:
        url: URL 路径
        view_class: 视图类
        method: 方法名或属性名
        need_auth: 默认 True（绝大多数路由需登录）
        is_property: 默认 True（约定用 @property）
        roles: 默认 None（所有登录用户）
        description: 默认空字符串（TODO 阶段可暂留空）
        skip_csrf: 默认 False
        is_alias: REV38-M4 默认 False；同一 view_class.method 注册到多个 URL 时, 主路由 False, alias True

    Returns:
        RouteRule 实例
    """
    return RouteRule(
        url=url,
        view_class=view_class,
        method=method,
        need_auth=need_auth,
        is_property=is_property,
        roles=list(roles) if roles else None,
        description=description,
        skip_csrf=skip_csrf,
        is_alias=is_alias,
    )
