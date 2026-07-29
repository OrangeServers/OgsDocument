# -*- coding: utf-8 -*-
"""OrangeServer 公共类型 (ti3-HINT).

用途:
  - 集中管理跨模块复用的类型 (TypedDict / Protocol / Union aliases)
  - 替代散落各处的 Dict[str, Any] / Optional[str] 等模糊类型
  - 让 mypy 能正确推断业务返回结构

使用规范:
  - 业务模块 (api/users/assets) 优先用这里的类型
  - 工具模块 (tools/local) 允许 Any, 不强制
  - 新增类型按业务域分类, 不要建过多

REV47-M12 续: basesec.py 标杆后, 业务层跟进的公共类型沉淀.
"""
from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

# =============================================================================
# 基础类型别名
# =============================================================================
# 通用 ID (DB 主键 / 用户名 / 主机名 / 资产名)
StrId = str
# 邮箱
Email = str
# IP / 域名
HostAddr = str
# 文件路径 (str 而非 pathlib.Path, 因为业务广泛用 str 路径, 改 Path 风险大)
FilePath = str
# 命令 / Shell 命令
ShellCmd = str
# 时间戳 ISO 字符串
IsoTimestamp = str
# 业务错误码 (int, 参考 app.tools.apierr.ApiCode)
ErrorCode = int

# Redis key
RedisKey = str

# 用户角色
UserRole = str  # 'admin' / 'user' / 'readonly' 等

# 业务返回的 code 字段
ApiResponseCode = int  # 0=成功, 1=通用错, 2=服务器错, 3=未登录, 4=权限不足, ...


# =============================================================================
# 通用返回结构
# =============================================================================
# 标准 API 返回 (REV37-H4 统一格式)
#   成功: {"code": 0, "data": {...}, "msg": "ok"}
#   失败: {"code": 3, "msg": "未登录", "data": null}
class ApiResponsePayload(Dict[str, Any]):
    """标准 API JSON 响应 (dict subclass, 仅为类型提示).

    字段:
      code: ApiResponseCode (0=成功)
      data: 业务数据 (成功时填, 失败时 None)
      msg:  可读消息 (str)
    """
    code: ApiResponseCode
    data: Optional[Any]
    msg: str


# 业务返回值 = JSON dict (Flask jsonify) 或 Flask Response 对象
JsonOrResponse = Union[Dict[str, Any], 'flask.Response', Any]

# ORM 单行 = dict-like (SQLAlchemy Row / NamedTuple / dict)
DbRow = Dict[str, Any]

# ORM 多行
DbRows = List[DbRow]

# 分页结果
PaginatedResult = Dict[str, Any]  # 包含 items + total + page + limit


# =============================================================================
# 用户/资产/SSH 业务类型
# =============================================================================
class UserInfo(Dict[str, Any]):
    """用户信息 (登录态 / 数据库行)."""
    id: int
    name: str
    email: Optional[str]
    role: UserRole
    is_active: bool


class HostInfo(Dict[str, Any]):
    """资产/主机信息."""
    id: int
    name: str
    host: HostAddr
    port: int
    user: str
    group_id: Optional[int]


class CronJobInfo(Dict[str, Any]):
    """定时任务."""
    id: int
    name: str
    cron_expr: str
    cmd: ShellCmd
    is_active: bool


# =============================================================================
# 通用类型变量 (用于泛型函数)
# =============================================================================
T = TypeVar('T')
TKey = TypeVar('TKey', bound=str)
TValue = TypeVar('TValue')


# =============================================================================
# Redis 客户端 (interface)
# =============================================================================
class RedisConnProtocol:
    """Redis 连接协议 (最小子集, 业务用的方法).

    用于 type hints 替代 redis.Redis 全类型, 简化 mock.
    """
    def get(self, key: RedisKey) -> Optional[bytes]:
        ...

    def set(self, key: RedisKey, value: Any, ex: Optional[int] = None) -> bool:
        ...

    def delete(self, key: RedisKey) -> int:
        ...

    def incr(self, key: RedisKey) -> int:
        ...

    def expire(self, key: RedisKey, seconds: int) -> bool:
        ...

    def ttl(self, key: RedisKey) -> int:
        ...


# =============================================================================
# 装饰器相关
# =============================================================================
# 视图函数 = callable 接受 **kwargs 返 JSON
ViewFunc = Callable[..., JsonOrResponse]

# 带 self 的类方法
MethodViewFunc = Callable[..., JsonOrResponse]


# =============================================================================
# 兼容旧代码 (无 typing.Any 时仍可 import)
# =============================================================================
__all__ = [
    # 基础
    'Any', 'Callable', 'Dict', 'Iterable', 'Iterator', 'List', 'Mapping',
    'Optional', 'Sequence', 'Set', 'Tuple', 'TypeVar', 'Union',
    # 别名
    'StrId', 'Email', 'HostAddr', 'FilePath', 'ShellCmd', 'IsoTimestamp',
    'ErrorCode', 'RedisKey', 'UserRole', 'ApiResponseCode',
    # 返回结构
    'ApiResponsePayload', 'JsonOrResponse', 'DbRow', 'DbRows', 'PaginatedResult',
    # 业务
    'UserInfo', 'HostInfo', 'CronJobInfo',
    # 泛型
    'T', 'TKey', 'TValue',
    # 协议
    'RedisConnProtocol',
    # 装饰器
    'ViewFunc', 'MethodViewFunc',
]
