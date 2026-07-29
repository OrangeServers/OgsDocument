from app.auth.AuthHost import AuthHostList, AuthHostDel, AuthHostAdd, AuthHostUpdate
from app.api import route  # REV38-M1: 统一 ROUTES schema

ROUTES = [
    # ---- 权限规则（仅超级管理员）----
    route('/auth/host/list_all', AuthHostList, 'auth_host_list_all',
          roles=['admin'],
          description='权限规则完整列表（含关联的用户/组/主机/系统用户）'),
    route('/auth/host/uplist', AuthHostList, 'auth_group_role',
          roles=['admin'],
          description='用户/组/主机 三方组合的可授权项聚合'),
    route('/auth/host/list', AuthHostList, 'create_auth_list',
          roles=['admin'],
          description='创建权限规则表单所需的下拉数据'),
    route('/auth/host/add', AuthHostAdd, 'auth_host_add',
          roles=['admin'],
          description='新增权限规则'),
    route('/auth/host/update', AuthHostUpdate, 'auth_host_update',
          roles=['admin'],
          description='更新权限规则'),
    route('/auth/host/del', AuthHostDel, 'auth_host_del',
          roles=['admin'],
          description='删除权限规则'),
]
