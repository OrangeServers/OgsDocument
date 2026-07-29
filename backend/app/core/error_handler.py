r"""
R2-8 (REV45-H13): 异常信息防泄漏工具

问题: API 错误响应直接 str(e), 暴露:
  - SQL 表名/字段名 (e.g. 't_acc_user')
  - 文件绝对路径 (e.g. 'D:\code\OrangeServer\...')
  - 内部异常类型 (e.g. 'psycopg2.errors.UniqueViolation')
  - 堆栈行号
攻击者通过这些信息定位内部结构, 减少攻击成本.

修复:
  - safe_error_msg(e, default='operation failed') -> 清洗过的安全消息
  - 保留面向用户的通用描述 (e.g. '磁盘信息获取失败'), 但清除异常细节
  - 详细信息走 logging.warning(..., exc_info=True) 供运维排查
  - Flask errorhandler: 500 返回统一 JSON, 不暴露 traceback
"""
import re
import logging
import traceback
from flask import jsonify


# REV45-H13: 危险模式 - 任何含这些模式的消息应被脱敏
_SENSITIVE_PATTERNS = [
    # Windows 路径 D:\... 或 D:/...
    re.compile(r'[A-Za-z]:[\\\\/][^\s\'"<>]+'),
    # Unix 路径 /home/, /tmp/, /var/... 含绝对路径
    re.compile(r'/(?:home|tmp|var|opt|etc|usr)/[^\s\'"<>]+'),
    # SQL 表名 t_xxx / T_xxx
    re.compile(r'\bt_[a-z_]+\b', re.IGNORECASE),
    # SQLAlchemy 类名 (e.g. 't_acc_user' 已匹配, 这里防 'Mapped[t_acc_user]')
    re.compile(r'Mapped\[[^\]]+\]'),
    # Python 异常类型 (e.g. 'OperationalError', 'IntegrityError')
    re.compile(r'\b(?:[A-Z][a-zA-Z]*Error|Exception)\b'),
    # 行号 file.py:123 等
    re.compile(r'\b[a-z_]+\.py:\d+'),
]


def _is_dev():
    """R2-8: 仅 dev 环境才暴露完整异常信息."""
    try:
        from app.core.config import _env
        return _env('OGS_ENV', 'dev') == 'dev'
    except Exception:
        # 配置加载失败 / 测试环境
        return True  # 测试时返详情


def safe_error_msg(e, default='operation failed', max_len=200):
    """R2-8: 把异常对象转为安全的用户可见消息.

    Args:
        e: 异常对象 (Exception / str)
        default: 默认友好消息 (清洗失败时返回)
        max_len: 最大长度, 防止过长消息 DoS

    Returns:
        str: 清洗过的安全消息

    Strategy:
        - dev 环境: 保留完整 str(e) (开发者本地调试)
        - prod 环境: 只返 generic default (运维查日志)
    """
    if _is_dev():
        # 开发环境: 返回受控的 str(e), 经脱敏
        msg = str(e) if not isinstance(e, str) else e
    else:
        # 生产环境: 永远返通用 message, 不暴露任何细节
        return default

    msg = msg.strip()
    if not msg:
        return default

    # 脱敏
    for pat in _SENSITIVE_PATTERNS:
        msg = pat.sub('[REDACTED]', msg)

    # 截断
    if len(msg) > max_len:
        msg = msg[:max_len] + '...'

    return msg if msg else default


def register_error_handlers(app):
    """R2-8: 注册 Flask 全局错误处理器.

    用途:
        from app.core.error_handler import register_error_handlers
        register_error_handlers(app)

    效果:
        - 500 Internal Server Error -> JSON 友好响应, 不暴露 traceback
        - Exception -> JSON 友好响应, 详细信息记日志
        - 404, 405, 400 也统一格式
    """
    logger = logging.getLogger('error_handler')

    @app.errorhandler(500)
    def _internal_error(e):
        logger.exception('500 Internal Server Error')
        # 不暴露原始 str(e) (e.g. 'ZeroDivisionError: ...')
        return jsonify({'code': 500, 'msg': 'internal server error'}), 500

    @app.errorhandler(Exception)
    def _all_exception(e):
        # HttpException 已经由 Flask 处理; 这里主要兜底
        logger.exception('Unhandled exception: %s', type(e).__name__)
        return jsonify({
            'code': 500,
            'msg': safe_error_msg(e, default='operation failed'),
        }), 500

    @app.errorhandler(404)
    def _not_found(e):
        return jsonify({'code': 404, 'msg': 'not found'}), 404

    @app.errorhandler(405)
    def _method_not_allowed(e):
        return jsonify({'code': 405, 'msg': 'method not allowed'}), 405

    @app.errorhandler(400)
    def _bad_request(e):
        return jsonify({'code': 400, 'msg': 'bad request'}), 400
