import datetime, functools, logging, os
from logging import handlers
from flask import request
# REV38-M2: 顶层导入 gevent 用于 spawn/greenlet 续期后台任务与 sleep
#   提到顶层方便测试 patch (函数内懒加载 patch 不到), gevent 是 ws 模式必装依赖
from gevent import spawn as g_spawn, sleep as g_sleep
from app.tools.redisdb import ConnRedis
from app.tools.SqlListTool import ListTool
from app.core.db.database import t_acc_user, t_auth_host, \
    t_auth_host_user, t_auth_host_user_group, t_auth_host_host_group, t_auth_host_sys_user
from app.core.config import FILE_CONF, SESSION_DEFAULT_EXP_SECONDS, SESSION_RENEW_THRESHOLD_RATIO
# REV37-H4: 统一错误响应
from app.tools.apierr import api_error, ApiCode

# REV38-M2: WebSocket session 续期配置
#   长连接期间(SSH/SFTP)定期续期 Redis token TTL, 防长连接中途 token 过期
#   默认 5 分钟; 设 0 可禁用后台续期
#   可通过 OGS_WS_SESSION_RENEW_INTERVAL 环境变量覆盖
WS_SESSION_RENEW_INTERVAL = int(os.environ.get('OGS_WS_SESSION_RENEW_INTERVAL', '300'))


# BUGFIX-REV50: 前端 pj() 发送 JSON body，但 Flask request.values 只读 form-encoded。
# 此函数兼容两种格式，可在任何路由处理中替代 request.values.get()。
def request_param(key: str, default=None, type=None):
    """从请求中取参数，兼容 form-encoded 和 JSON body 两种格式。

    优先读 request.values（form + query），再读 request.json（JSON body）。
    用法与 request.values.get(key, default) 完全兼容。
    """
    # 1. form-encoded + query string
    val = request.values.get(key)
    if val is not None:
        if type is not None:
            try:
                return type(val)
            except (ValueError, TypeError):
                return default
        return val
    # 2. JSON body
    json_data = request.get_json(silent=True)
    if json_data and isinstance(json_data, dict) and key in json_data:
        val = json_data[key]
        if val is None:
            return default
        if type is not None:
            try:
                return type(val)
            except (ValueError, TypeError):
                return default
        return val
    return default


def request_file(key: str):
    """从请求中取上传文件，兼容 multipart/form-data。"""
    return request.files.get(key)


def request_param_list(key: str):
    """从请求中取数组参数，兼容 form-encoded 和 JSON body。

    form-encoded 时用 request.values.getlist(key)，
    JSON body 时直接取 list 字段。
    """
    # 1. form-encoded: getlist
    vals = request.values.getlist(key)
    if vals:
        return vals
    # 2. JSON body
    json_data = request.get_json(silent=True)
    if json_data and isinstance(json_data, dict) and key in json_data:
        val = json_data[key]
        if isinstance(val, list):
            return val
        if val is not None:
            return [val]
    return []


# REVIEW-6-P2-3: 统一会话上下文函数, 避免重复 ConnRedis() + conn.get(tk) 调用
def _session():
    """统一取当前会话上下文。返回 (ords, name) 或 (None, None) 表示未登录。

    调用者负责后续处理：未登录需返回统一错误码；已登录则 name 是 str。
    """
    ords = ConnRedis()
    tk = request.cookies.get('ogs_token')
    if not tk:
        return None, None
    name = ords.conn.get(tk)
    if isinstance(name, bytes):
        name = name.decode('utf-8', errors='ignore')
    if not name:
        return None, None
    return ords, name


def auth_list_get():
    """获取当前用户有权访问的资产组名集合（基于关联表）。"""
    ords, name = _session()
    if not name:
        return []  # REVIEW-6-P2-2: 返回 list 以便可 JSON 序列化
    # 用户直接关联的 auth → host_group
    auth_ids = [r.auth_id for r in t_auth_host_user.query.filter_by(user_name=name).all()]
    # 用户所在用户组关联的 auth → host_group
    # REV47-M6: 业务查询过滤软删 (软删用户不应该有资产权限)
    grp_name = t_acc_user.query.filter_by(name=name, is_deleted=False).first()
    if grp_name and grp_name.group:
        group_auth_ids = [r.auth_id for r in
                          t_auth_host_user_group.query.filter_by(group_name=grp_name.group).all()]
        auth_ids = list(set(auth_ids + group_auth_ids))
    # 从关联表取出 host_group 集合
    host_groups = set()
    for aid in auth_ids:
        for r in t_auth_host_host_group.query.filter_by(auth_id=aid).all():
            host_groups.add(r.group_name)
    return host_groups


def get_current_user():
    """从请求 cookie 中获取当前登录用户名，返回 (redis_conn, username) 元组。"""
    return _session()  # REVIEW-6-P2-3: 复用 _session() 避免重复 ConnRedis()+get(tk)


def get_current_user_role():
    """获取当前登录用户的角色。"""
    ords, name = _session()
    if not name:
        return None
    role_key = name + '_role'
    user_role = ords.conn.get(role_key)
    if isinstance(user_role, bytes):
        user_role = user_role.decode('utf-8', errors='ignore')
    return user_role


def require_role(*roles):
    """角色鉴权装饰器：只允许指定角色访问。
    用法: @require_role('admin') 或 @require_role('admin', 'audit')

    REV37-H4: 错误响应统一走 api_error，返回 (jsonify, status_code) tuple，
              前端 axios 拦截器可走 res.status 统一判 401/403/500。
    REV39-L5: 错误码语义对齐（替代原 at.py:77/84 用 code=100 的重叠）
              - 未登录: ApiCode.UNAUTHORIZED (3) → HTTP 401
              - 权限不足: ApiCode.FORBIDDEN (4) → HTTP 403
              - init.py:70-96 docstring 与 apierr.py._STATUS_BY_CODE 保持一致
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # REVIEW-6-P2-3: 复用 _session() 避免与 get_current_user 重复查询
            ords, username = _session()
            if not username:
                return api_error(ApiCode.UNAUTHORIZED, '未授权访问')
            role_key = username + '_role'
            user_role = ords.conn.get(role_key)
            if isinstance(user_role, bytes):
                user_role = user_role.decode('utf-8', errors='ignore')
            # P1-11: str() 包裹防 user_role 是 None 时的 in 异常
            if str(user_role) not in [str(r) for r in roles]:
                return api_error(ApiCode.FORBIDDEN, '权限不足')
            return func(*args, **kwargs)
        return wrapper
    return decorator


# REVIEW-5-B + REV38-M2: WebSocket 鉴权装饰器 + sliding session 续期
#   区别于 ogs_auth_token: WebSocket 升级握手阶段必须用 HTTP 状态码拒绝
#   geventwebsocket 在 view_func 返回 ('', 4xx) 时会中断升级流程,
#   而 dict 响应会让握手进入异常态(无明确状态码), 不够干净.
#   不走 csrf_protect: 升级请求是 GET, csrf_protect 天然豁免 GET/HEAD/OPTIONS.
#
# REV38-M2 修复: 长连接期间(SSH/SFTP)定期续期 Redis token TTL
#   原 ws_auth 仅握手时校验一次, 长连接 1h 但 token TTL 30min → 中途过期, 前端不知情
#   修复: 握手通过后立即续期一次 (与 HTTP 行为一致) + 启动后台 greenlet
#         每 WS_SESSION_RENEW_INTERVAL 秒检查 token 有效性, 失效时主动关 WS
def _ws_session_check_and_renew(tk):
    """REV38-M2: WebSocket session 检查 + 续期。

    返回 (alive, renewed):
      alive   - True=token 仍有效, False=token 失效
      renewed - True=本调用触发了 TTL 续期, False=无需续期 (TTL 充足)
    """
    if not tk:
        return False, False
    try:
        ords = ConnRedis()
        if ords.conn.get(tk) is None:
            return False, False
        ttl = ords.conn.ttl(tk)
        threshold = int(SESSION_DEFAULT_EXP_SECONDS * SESSION_RENEW_THRESHOLD_RATIO)
        if ttl == -1 or (0 <= ttl < threshold):
            ords.conn.expire(tk, SESSION_DEFAULT_EXP_SECONDS)
            return True, True
        return True, False
    except Exception:
        # 续期异常时保守视为 alive, 避免误杀活跃会话
        return True, False


def _ws_session_renew_loop(tk, ws_ref):
    """REV38-M2: WebSocket 后台 session 续期 greenlet。

    每 WS_SESSION_RENEW_INTERVAL 秒:
      1. 检查 ws 是否还活着 (ws.closed) → 关闭则退出
      2. 检查 token 有效性 → 失效则主动 close WS (1008=policy violation) 并退出
      3. token 有效时按阈值续期 TTL
    """
    while True:
        g_sleep(WS_SESSION_RENEW_INTERVAL)
        try:
            # 1. WS 已关闭 → 退出后台循环
            if not ws_ref or getattr(ws_ref, 'closed', True):
                return
            # 2. token 失效 → 关 WS 并退出
            alive, _ = _ws_session_check_and_renew(tk)
            if not alive:
                try:
                    ws_ref.close(1008, 'session expired')
                except Exception:
                    pass
                return
        except Exception:
            # 续期异常不打断后台循环 (单次失败不应终止整个会话)
            continue


def ws_auth(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ords = ConnRedis()
        tk = request.cookies.get('ogs_token')
        # REVIEW-6-P2-4: 防止 cookie 丢失时 str(None) == 'None' 误查
        if not tk:
            # 让 geventwebsocket 拒绝握手，浏览器侧能明确看到 401
            return '', 401
        if ords.conn.get(tk) is None:
            return '', 401

        # REV38-M2: 握手通过后立即续期一次, 与 HTTP 行为一致
        try:
            _ws_session_check_and_renew(tk)
        except Exception:
            # 续期失败不影响握手
            pass

        # REV38-M2: 启动后台续期 greenlet (设 0 可禁用)
        if WS_SESSION_RENEW_INTERVAL > 0:
            ws_ref = request.environ.get('wsgi.websocket')
            if ws_ref is not None:
                try:
                    g_spawn(_ws_session_renew_loop, tk, ws_ref)
                except Exception:
                    # 启动失败不影响主流程 (后台非关键路径)
                    pass

        return func(*args, **kwargs)
    return wrapper


def ogs_auth_token(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # REVIEW-6-P2-3: 复用 _session() 避免重复 ConnRedis()+get(tk)
        ords, username = _session()
        if not username:
            # REV37-H4: 未登录返回 (jsonify, 401)
            return api_error(ApiCode.UNAUTHORIZED, '未授权访问')

        # REVIEW-6-P1-1: sliding session 续期
        #   活跃用户每发起一次受保护请求，TTL 自动续期到 SESSION_DEFAULT_EXP_SECONDS
        #   当 TTL 不足一半时触发，避免每个请求都写 Redis
        #   ttl 含义: -2=键不存在(已过滤), -1=无过期, >=0=剩余秒数
        #   要拿到原始 tk 以用 ttl/expire, 从 cookie 重新取一次 (开销 O(1))
        try:
            tk = request.cookies.get('ogs_token')
            ttl = ords.conn.ttl(tk)
            threshold = int(SESSION_DEFAULT_EXP_SECONDS * SESSION_RENEW_THRESHOLD_RATIO)
            if ttl == -1 or (0 <= ttl < threshold):
                ords.conn.expire(tk, SESSION_DEFAULT_EXP_SECONDS)
        except Exception:
            # 续期失败不影响鉴权主流程
            pass

        return func(*args, **kwargs)

    return wrapper


# REVIEW-6-P2-5: 改名为 FileLogger, 避开与 stdlib logging.Logger 命名冲突
class FileLogger(object):
    level_relations = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'crit': logging.CRITICAL
    }  # 日志级别关系映射

    def __init__(self, level='info', when='D', backCount=3,
                 fmt='%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s'):
        self.logger = logging.getLogger(FILE_CONF['log_path'] + 'ogsbackend.log')
        format_str = logging.Formatter(fmt)  # 设置日志格式
        self.logger.setLevel(self.level_relations.get(level))  # 设置日志级别
        self.sh = logging.StreamHandler()  # 往屏幕上输出
        self.sh.setFormatter(format_str)  # 设置屏幕上显示的格式
        self.th = handlers.TimedRotatingFileHandler(filename=FILE_CONF['log_path'] + 'ogsbackend.log', when=when,
                                                    backupCount=backCount,
                                                    encoding='utf-8')  # 往文件里写入#指定间隔时间自动生成文件的处理器
        # 实例化TimedRotatingFileHandler
        # interval是时间间隔，backupCount是备份文件的个数，如果超过这个个数，就会自动删除，when是间隔的时间单位，单位有以下几种：
        # S 秒
        # M 分
        # H 小时、
        # D 天、
        # W 每星期（interval==0时代表星期一）
        # midnight 每天凌晨
        self.th.setFormatter(format_str)  # 设置文件里写入的格式
        if not self.logger.handlers:  # 防止重复添加handler
            self.logger.addHandler(self.sh)  # 把对象加到logger里
            self.logger.addHandler(self.th)


# 向后兼容别名: 已有代码 4 个文件 (LocalInit/Settings/user/cron) 用 `from app.tools.at import Log`
# Log 实例名未变, 仅为 Logger 类改了名; 调用方无需修改
Log = FileLogger()
