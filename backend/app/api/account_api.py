from app.users.user import CheckUser, UserRegister, UserLogin2, UserLogout, AccUserList, AccUserAdd, AccUserUpdate, AccUserDel, AccUserResetPwd, ForgotPwdSend, ForgotPwdReset
from app.users.group import AccGroupList, AccGroupAdd, AccGroupUpdate, AccGroupDel
from app.audit.loginlogs import LogList
from app.api import route  # REV38-M1: 统一 ROUTES schema

ROUTES = [
    # ---- 登录注册（无需鉴权）----
    route('/account/login_dl2', UserLogin2, 'login_dl',
          need_auth=False, is_property=False,
          description='用户登录（账号密码 + 图形验证码）', skip_csrf=True),
    route('/account/chk_username', CheckUser, 'check',
          need_auth=False, is_property=False,
          description='检查用户名是否存在（注册前置校验）', skip_csrf=True),
    route('/account/com_register', UserRegister, 'register',
          need_auth=False, is_property=False,
          description='用户注册（需邮箱验证码）', skip_csrf=True),
    route('/account/login_out', UserLogout, 'logout',
          need_auth=False, is_property=False,
          description='用户登出（清除 session）', skip_csrf=True),

    # ---- 用户组（仅超级管理员）----
    route('/account/group/list', AccGroupList, 'group_list',
          roles=['admin'],
          description='用户组分页列表'),
    route('/account/group/name_list', AccGroupList, 'group_name_list',
          roles=['admin'],
          description='用户组名称列表（下拉框用）'),
    route('/account/group/list_all', AccGroupList, 'group_list_all',
          roles=['admin'],
          description='用户组完整列表（含备注）'),
    route('/account/group/add', AccGroupAdd, 'host_add',
          roles=['admin'],
          description='新增用户组'),
    route('/account/group/update', AccGroupUpdate, 'update',
          roles=['admin'],
          description='更新用户组'),
    route('/account/group/del', AccGroupDel, 'host_del',
          roles=['admin'],
          description='删除用户组'),

    # ---- 页面用户（管理仅 admin；alias/auth_list 所有用户可用）----
    route('/account/user/list', AccUserList, 'acc_user_list',
          roles=['admin'],
          description='用户分页列表'),
    route('/account/user/auth_list', AccUserList, 'acc_user_auth_list',
          description='当前用户可授权的用户列表（权限分配用）'),
    route('/account/user/list_all', AccUserList, 'acc_user_list_all',
          roles=['admin'],
          description='用户完整列表'),
    route('/account/user/add', AccUserAdd, 'host_add',
          roles=['admin'],
          description='新增平台用户'),
    route('/account/user/update', AccUserUpdate, 'update',
          roles=['admin'],
          description='更新平台用户'),
    route('/account/user/del', AccUserDel, 'host_del',
          roles=['admin'],
          description='删除平台用户'),
    route('/account/user/reset_pwd', AccUserResetPwd, 'reset_pwd',
          roles=['admin'],
          description='管理员重置用户密码'),
    route('/account/user/alias', AccUserList, 'acc_user_alias',
          description='用户 alias 列表（按权限过滤）'),

    # ---- 审计日志（admin + 日志管理员）----
    route('/account/logs/log', LogList, 'get_logs',
          is_property=False, roles=['admin', 'audit'],
          description='操作日志分页查询'),
    route('/account/logs/date', LogList, 'get_date_logs',
          is_property=False, roles=['admin', 'audit'],
          description='按日期分组查询日志'),
    route('/account/logs/select', LogList, 'get_select_logs',
          is_property=False, roles=['admin', 'audit'],
          description='按条件筛选日志'),

    # ---- 忘记密码（无需鉴权）----
    route('/account/forgot_pwd_send', ForgotPwdSend, 'send',
          need_auth=False, is_property=False,
          description='发送忘记密码验证码邮件', skip_csrf=True),
    route('/account/forgot_pwd_reset', ForgotPwdReset, 'reset',
          need_auth=False, is_property=False,
          description='通过验证码重置密码', skip_csrf=True),
]
