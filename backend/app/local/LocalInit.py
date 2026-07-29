import os
import sys

from flask import request, jsonify

from app.core.config import DEFAULT_DATA_DIR, FILE_CONF
from app.core.db.database import t_host, t_group, t_line_chart, t_acc_user, t_login_log, t_acc_group, t_command_log, \
    t_auth_host, t_sys_user, \
    t_cron_host, t_cron_group, \
    t_auth_host_user, t_auth_host_user_group, t_auth_host_host_group, t_auth_host_sys_user
from app.tools.at import Log, request_param
from app.tools.redisdb import ConnRedis


# REV38-M3: /local/init 启动阶段 flag
#   - 启动 helper `local_app_init()` 完成后调用 end_init_phase() 关闭
#   - /local/init alias 在 _INIT_PHASE_OPEN=True 时才接受请求, 运行时返 410 Gone
#   - 正式 endpoint /local/status 不受此限制, 任何登录态可查
_INIT_PHASE_OPEN = True


def is_init_phase_open():
    """REV38-M3: 当前是否处于启动初始化阶段 (允许 /local/init alias)"""
    return _INIT_PHASE_OPEN


def end_init_phase():
    """REV38-M3: 标记启动完成, 关闭 /local/init alias。运行时应只走 /local/status。"""
    global _INIT_PHASE_OPEN
    _INIT_PHASE_OPEN = False


def force_open_init_phase():
    """REV38-M3: 强制打开 (仅供测试或运维紧急维护)。"""
    global _INIT_PHASE_OPEN
    _INIT_PHASE_OPEN = True


class AppInit:
    def __init__(self):
        self.ords = ConnRedis()
        self.mysql_list = [t_host, t_group, t_line_chart, t_acc_user, t_login_log, t_acc_group, t_command_log,
                           t_auth_host, t_sys_user,
                           t_cron_host, t_cron_group,
                           t_auth_host_user, t_auth_host_user_group, t_auth_host_host_group, t_auth_host_sys_user]
        self.Log = Log

    def con_init(self):
        self.Log.logger.info('check connection redis............')
        self.Log.logger.info('check connection mysql............')
        if self.ords.conn.ping() is False:
            self.Log.logger.error('error! redis is not connection')
            sys.exit(1)
        for i in self.mysql_list:
            try:
                i.query.count()
            except IOError:
                self.Log.logger.error('error! mysql database table {} is not found'.format(str(i)))
                sys.exit(2)
        self.Log.logger.info('check connection redis mysql is ok!')
        if os.path.exists(DEFAULT_DATA_DIR):
            for i in FILE_CONF.values():
                if not os.path.exists(i):
                    os.mkdir(i)
                    self.Log.logger.info('mkdir is %s' % i)
        else:
            os.mkdir(DEFAULT_DATA_DIR)
            for i in FILE_CONF.values():
                if not os.path.exists(i):
                    os.mkdir(i)
            self.Log.logger.info('mkdir is data and subdirectory......')

    def app_status(self):
        sta = request_param('status')
        log_msg = 'req_body: [ status=%s ] /local/init' % sta
        if sta == 'ogsfront':
            return jsonify({'status': 200})
        else:
            self.Log.logger.error(log_msg + ' \"fail 403\"')
            return jsonify({'status': 403})

    @staticmethod
    def app_auth_status():
        """P0-4: 真正校验 token 是否在 Redis 中有效。
        原实现永远返回 {'code': 0}，导致前端 [router/index.js:69](file:///d:/code/ogs198/pycharm_ogsfront/src/router/index.js#L69) 路由守卫形同虚设。
        - 已登录(token 存在): {'code': 0}
        - 未登录/伪造/过期:   {'code': 3, 'msg': '...'}
        """
        user_token = request.cookies.get('ogs_token')
        if not user_token:
            return {'code': 3, 'msg': '未登录'}
        ords = ConnRedis()
        # og_token 是 OgsSession 写入 Redis 的键；可能为 None / b'' / ''
        username = ords.conn.get(user_token)
        if not username:
            return {'code': 3, 'msg': 'token 无效或已过期'}
        return {'code': 0}
