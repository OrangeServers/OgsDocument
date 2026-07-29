"""CRIT-4 + HIGH-9：CSRF Token 签发与校验

设计：双 cookie 模式（Double Submit Cookie）
  - 登录成功后，Set-Cookie 写两个 cookie：
      1) ogs_token (HttpOnly) - 身份认证
      2) csrf_token (非 HttpOnly) - CSRF 防护
  - 前端从 cookie 读 csrf_token，请求时加到 X-CSRF-Token header
  - 后端装饰器 @csrf_protect 校验：header 与 cookie 一致

为什么用双 cookie 而不是 stateful token？
  - 简单，无需服务器 session 存储
  - 与 HttpOnly 主 token 隔离，即使 XSS 也只能读 csrf_token（不致命）
  - SameSite=Lax 已防大部分 CSRF，csrf_token 是纵深防御
"""
import hashlib
import hmac
import os
import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import request, make_response

# REVIEW-6-P1-2: 集中从 conf.py 读取密钥，避免与 conf.py 双重默认串发散
from app.core.config import FLASK_SECRET_KEY, _env, SESSION_DEFAULT_EXP_SECONDS
# REV37-H4: 统一错误响应包装
from app.tools.apierr import api_error, ApiCode


# CSRF 密钥 = Flask secret_key（P1-2：不再独立读 env，与 conf.py 同源）
# 保留 _get_csrf_secret 作为 backward-compat 别名（verify_high9.py / 外部脚本引用）
def _get_csrf_secret():
    return FLASK_SECRET_KEY


# REVIEW-6-P1-3: CSRF nonce Redis key 模板 + 默认 TTL
CSRF_NONCE_KEY_TPL = 'ogs:csrf_nonce:%s'  # %s = user_token
CSRF_NONCE_TTL = SESSION_DEFAULT_EXP_SECONDS  # 复用 session 过期时间


def _get_csrf_nonce(user_token):
    """从 Redis 读 per-session 随机 nonce；不存在返回 None"""
    from app.tools.redisdb import ConnRedis
    if not user_token:
        return None
    ords = ConnRedis()
    nonce = ords.conn.get(CSRF_NONCE_KEY_TPL % user_token)
    if isinstance(nonce, bytes):
        nonce = nonce.decode('utf-8', errors='ignore')
    return nonce or None


def set_csrf_nonce(user_token):
    """生成并写入 per-session 随机 nonce；返回 nonce 本身。
    REVIEW-6-P1-3: 登录成功后由 user.py 调用，TTL 复用 session。
    """
    from app.tools.redisdb import ConnRedis
    nonce = secrets.token_urlsafe(16)
    ords = ConnRedis()
    ords.conn.set(CSRF_NONCE_KEY_TPL % user_token, nonce, ex=CSRF_NONCE_TTL)
    return nonce


def clear_csrf_nonce(user_token):
    """登出 / 重置密码时清理 nonce。"""
    from app.tools.redisdb import ConnRedis
    if not user_token:
        return
    ords = ConnRedis()
    ords.conn.delete(CSRF_NONCE_KEY_TPL % user_token)


def make_csrf_token(user_token=None, nonce=None):
    """生成 csrf_token：HMAC(secret, nonce + user_token) -> hex
    REVIEW-6-P1-3：双因子，未传 nonce 时退化为原 (user_token) 输入以保 backward-compat
    """
    secret = FLASK_SECRET_KEY.encode('utf-8')
    # 即使无 user_token 也生成一个固定 token（防误用）
    payload = (user_token or 'anonymous').encode('utf-8')
    if nonce is not None:
        # REVIEW-6-P1-3：nonce 拼接在 user_token 前，HMAC 双因子
        payload = nonce.encode('utf-8') + b':' + payload
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


# REVIEW-6-P2-1: 豁免装饰器, 取代原硬编码路径列表
#   使用方式: @csrf_skip 在 view_func 上, csrf_protect 会自动跳过
#   适用于登录 / 登出 / 公开接口
def csrf_skip(func):
    """标记该 view_func 免受 csrf_protect 校验。"""
    func._csrf_skip = True
    return func


# REVIEW-6-P2-2: Origin/Referer 二次校验白名单
#   仅验证 scheme+netloc, 不验证 path (path 可由后端处理)
#   默认只允许同源, 可通过环境变量 OGS_CSRF_ALLOWED_ORIGINS 添加额外源 (逗号分隔)
#   例如 OGS_CSRF_ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
def _get_allowed_origins():
    raw = _env('OGS_CSRF_ALLOWED_ORIGINS', '')
    origins = set()
    for item in raw.split(','):
        item = item.strip()
        if item:
            origins.add(item.rstrip('/'))
    # 同源默认允许 (空 host 表示同源)
    return origins


def _is_origin_allowed(origin_header, referer_header):
    """检查 Origin / Referer 是否在白名单或与 request.host 同源。"""
    allowed = _get_allowed_origins()
    candidates = []
    if origin_header:
        candidates.append(origin_header.rstrip('/'))
    if referer_header:
        try:
            p = urlparse(referer_header)
            referer_origin = '%s://%s' % (p.scheme, p.netloc)
            candidates.append(referer_origin.rstrip('/'))
        except Exception:
            pass
    for c in candidates:
        if c in allowed:
            return True
        # 同源检测: scheme + netloc 都需与 request 匹配
        # REV20-P2-2-LOW-9: 原仅比 netloc, 允许 HTTP/HTTPS 互跨 (降级攻击)
        try:
            p = urlparse(c)
            if p.scheme == request.scheme and p.netloc == request.host:
                return True
        except Exception:
            continue
    return False


# 豁免路径集合（向后兼容: login/logout 接口走 csrf_skip 也走路径豁免）
# REV44-H7 (R2-5-2): 路径白名单改为可选 fallback, 推荐用 @csrf_skip 装饰器显式标记
#   背景: _EXEMPT_PATHS 硬编码在 csrf.py, 新增 login 接口要改源码
#   修法: 保留 _EXEMPT_PATHS 作为 fallback (向后兼容已上线 login_dl/login_dl2/login_out),
#         业务新加豁免请用 @csrf_skip 装饰 view_func, 不要扩这个集合
_EXEMPT_PATHS = frozenset(('/account/login_dl', '/account/login_dl2', '/account/login_out'))


def csrf_skip(func):
    """REV44-H7 (R2-5-2): 装饰器, 显式标记 view_func 走 CSRF 豁免.

    使用方式:
        @csrf_skip
        @csrf_protect
        def my_view(): ...

    注意: csrf_skip 必须在 csrf_protect 外层 (从内到外: csrf_skip -> csrf_protect),
          这样 csrf_protect 才能在 wrapper 内通过 func._csrf_skip 看到标记.
    """
    func._csrf_skip = True
    return func


def csrf_protect(func):
    """装饰器：校验请求 header X-CSRF-Token 与 cookie csrf_token 一致。

    豁免：
      - GET/HEAD/OPTIONS（不修改状态）
      - 登录/登出接口（路径白名单 - 向后兼容，新接口请用 @csrf_skip 装饰器）
      - @csrf_skip 装饰过的 view_func (REV44-H7 推荐方式)
      - Origin/Referer 同源或白名单

    REVIEW-6-P1-3：增加 per-session nonce 校验，防 user_token 泄露后离线重算。
    REV44-H8 (R2-5-3): user_token 为空时必须 raise, 不能 skip nonce 校验.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 只校验状态变更方法
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return func(*args, **kwargs)

        # REVIEW-6-P2-1: view_func 自声明豁免 (REV44-H7 推荐方式)
        if getattr(func, '_csrf_skip', False):
            return func(*args, **kwargs)

        # 向后兼容: 登录/登出接口豁免 (REV44-H7: 新增请用 @csrf_skip)
        if request.path in _EXEMPT_PATHS:
            return func(*args, **kwargs)

        # REVIEW-6-P2-2: Origin / Referer 二次校验
        #   在没有 CSRF token 的极端场景下 (Cookie 未写 / 跨域遗留) 也起防护作用
        origin = request.headers.get('Origin', '')
        referer = request.headers.get('Referer', '')
        if origin or referer:
            if not _is_origin_allowed(origin, referer):
                return api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF Origin/Referer 校验失败')

        # 从 header 读 csrf
        header_token = request.headers.get('X-CSRF-Token', '')
        # 从 cookie 读 csrf
        cookie_token = request.cookies.get('csrf_token', '')

        if not header_token or not cookie_token:
            return api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF token 缺失')
        if not hmac.compare_digest(header_token, cookie_token):
            return api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF token 无效')

        # REVIEW-6-P1-3: 强校验：cookie csrf_token 必须与 per-session nonce 重新计算的期望值一致
        #   这层校验防 user_token 泄露后离线重算 csrf_token
        # REV44-H8 (R2-5-3): user_token 为空时必须 fail-closed, 不能 skip nonce 校验
        #   原: if user_token: → 空 token 直接跳过 nonce 校验, 攻击者可拿 csrf_token 直接 POST
        #   修: if not user_token: raise → 未登录态不允许过 csrf 强校验
        user_token = request.cookies.get('ogs_token', '')
        if not user_token:
            return api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF user_token 缺失，请登录')
        nonce = _get_csrf_nonce(user_token)
        if nonce is None:
            # 未找到 nonce: 会话未走新流程 (P1-3 部署前的旧会话)，fail-closed
            return api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF nonce 缺失，请重新登录')
        expected = make_csrf_token(user_token, nonce)
        if not hmac.compare_digest(cookie_token, expected):
            return api_error(ApiCode.BUSINESS_UNAUTHORIZED, 'CSRF token 与 nonce 不匹配')

        return func(*args, **kwargs)
    return wrapper
