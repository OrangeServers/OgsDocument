from flask import request, jsonify
from app.core.db.database import t_settings, db
from app.tools.SqlListTool import ListTool
from app.tools.redisdb import ConnRedis
from app.tools.at import Log, request_param

# 设置项字段定义：开关型字段列表和数值型字段列表
SWITCH_FIELDS = [
    'register_status', 'mfa_enabled', 'password_complexity',
    'session_record', 'command_audit', 'allow_upload', 'allow_download',
    'mail_notify',
]
NUMBER_FIELDS = [
    'login_time', 'login_fail_limit', 'lock_duration', 'password_expire_days',
    'ssh_timeout', 'terminal_scrollback', 'max_concurrent_sessions',
    'log_retention_days', 'upload_size_limit',
]
TEXT_FIELDS = [
    'color_matching', 'alert_email', 'system_name', 'login_notice',
    'language',  # I18N (rev51)
]
ALL_FIELDS = SWITCH_FIELDS + NUMBER_FIELDS + TEXT_FIELDS


# REV30-M9: SWITCH_FIELDS 仅接受合法布尔值
# SETTINGS-SAVE-FIX: 前端与 DB 的开关惯例是 'on'/'off'（列默认值、register_status==='on'
#   等所有消费方），旧白名单只认 true/false/1/0 导致设置页保存自 REV30 起全部被拒。
#   现接受两套输入并统一归一化存 'on'/'off'。
_SWITCH_ALLOWED = frozenset({'true', 'false', '1', '0', 'on', 'off'})
_SWITCH_TRUTHY = frozenset({'true', '1', 'on'})
# I18N: language 仅接受受支持的 locale, 防任意串入库
_LANGUAGE_ALLOWED = frozenset({'zh-CN', 'en-US'})


def _decode_redis_str(v):
    """REV30-M8: bytes -> str 统一转换。
    Redis conn.get 返回 bytes (Python 3), 原代码直接 bytes + '_role' 会 TypeError。"""
    if v is None:
        return None
    if isinstance(v, bytes):
        return v.decode('utf-8', errors='replace')
    return str(v)


class OgsSettings:
    def __init__(self):
        self.ords = ConnRedis()
        self.user_token = request.cookies.get('ogs_token', default=None)
        # REV30-M8: Redis 返回 bytes, decode 为 str 后才能拼接 '_role'
        raw_name = self.ords.conn.get(self.user_token) if self.user_token else None
        self.name = _decode_redis_str(raw_name)
        self.lt = ListTool

    @staticmethod
    def settings_open_info():
        default_msg = t_settings.query.filter_by(name='default').first()
        # I18N: language 随开放接口下发, 让登录页在未登录时也能应用服务端语言
        return {'name': default_msg.name, 'login_time': default_msg.login_time,
                'register_status': default_msg.register_status,
                'language': getattr(default_msg, 'language', None) or 'zh-CN'}

    def settings_info(self):
        default_msg = t_settings.query.filter_by(name='default').first()
        st_msg = self.lt.dict_reset_pop_auto(default_msg)
        # SMTP 授权码密文也属于秘密，专用接口只返回 configured 状态。
        st_msg.pop('mail_password_encrypted', None)
        return jsonify(st_msg)

    def settings_change(self):
        log_msg = 'req_body: [ name=%s ] /local/settings/update (fail)' % self.name
        try:
            # REV30-M8: self.name 已是 str, 直接拼接无 TypeError
            if self.name is None or self.ords.conn.get(self.name + '_role') != 'admin':
                return jsonify({'code': 100, 'msg': '操作失败 (code=4)'})

            update_data = {}
            for field in ALL_FIELDS:
                val = request_param(field)
                if val is not None:
                    if field in NUMBER_FIELDS:
                        # REV30-H3: 转换失败返错, 不静默写 0 (避免 login_time=0 等危险配置)
                        try:
                            update_data[field] = int(val)
                        except (ValueError, TypeError):
                            return jsonify({
                                'code': 100,
                                'msg': 'invalid value for %s: %r (must be integer)' % (field, val),
                            })
                    elif field in SWITCH_FIELDS:
                        # REV30-M9: SWITCH_FIELDS 只接受合法布尔值
                        v_lower = str(val).strip().lower()
                        if v_lower not in _SWITCH_ALLOWED:
                            return jsonify({
                                'code': 100,
                                'msg': 'invalid value for %s: %r (must be one of %s)' % (
                                    field, val, sorted(_SWITCH_ALLOWED)),
                            })
                        # SETTINGS-SAVE-FIX: 归一化为 DB/业务侧统一的 'on'/'off'
                        update_data[field] = 'on' if v_lower in _SWITCH_TRUTHY else 'off'
                    elif field == 'language':
                        # I18N: 枚举白名单, 防任意串入库
                        if val not in _LANGUAGE_ALLOWED:
                            return jsonify({
                                'code': 100,
                                'msg': 'invalid value for language: %r (must be one of %s)' % (
                                    val, sorted(_LANGUAGE_ALLOWED)),
                            })
                        update_data[field] = val
                    else:
                        update_data[field] = val

            if update_data:
                t_settings.query.filter_by(name='default').update(update_data)
                db.session.commit()
            return jsonify({'code': 0})
        except IOError:
            Log.logger.info(log_msg + ' "fail"')
            return jsonify({'code': 100, 'msg': '服务器内部错误'})
