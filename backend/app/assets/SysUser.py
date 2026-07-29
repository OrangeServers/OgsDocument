import os
import stat
import time
import re
from flask import request, jsonify
from app.core.db.database import t_sys_user, t_auth_host, t_acc_user, db, \
    t_auth_host_sys_user, t_auth_host_user, t_auth_host_user_group
from app.core.db.insert import osql_in
from app.tools.audlog import CzToolsLog
from app.tools.basesec import encrypt_host_password  # Fernet 对称加密（替代原 base64）
from app.tools.SqlListTool import ListTool
from app.tools.at import get_current_user, request_param
from app.tools.auto_update import AuthAutoUpdate
from app.tools.redisdb import ConnRedis
from app.core.config import FILE_CONF

# REV16 B6 HIGH-1: alias 路径越界 + chmod 白名单
#   原：self.alias + '_rsa' 字符串拼接,alias 来自 request 末任何校验
#   攻击：alias='../../../etc/cron.d/evil' → /data/key/../../../etc/cron.d/evil_rsa → 任意文件写
#   修复：白名单 + realpath 越界检测
# BUGFIX-REV50: 允许 Unicode 字符（中文/日文等），\w 含 Unicode 字母、数字、下划线
_ALIAS_RE = re.compile(r'^[\w.\-]{1,64}$')


class SysUserList:
    def __init__(self):
        self.ls_tool = ListTool
        self.ords = ConnRedis()

    @property
    def sys_user_name_list(self):
        try:
            user_token = request.cookies.get('ogs_token')
            # REV25-L1: user_token 判空, 避免 Redis TypeError + 日志污染
            name = self.ords.conn.get(user_token) if user_token else None
            if not name:
                return jsonify({'code': 100, 'msg': '未登录或会话已过期'})
            # 通过关联表查询用户直接授权的 auth_id
            auth_ids = [r.auth_id for r in t_auth_host_user.query.filter_by(user_name=name).all()]
            # 同时查找用户所在用户组的授权
            # REV47-M6: 业务查询过滤软删
            user_info = t_acc_user.query.filter_by(name=name, is_deleted=False).first()
            if user_info and user_info.group:
                group_auth_ids = [r.auth_id for r in
                                  t_auth_host_user_group.query.filter_by(group_name=user_info.group).all()]
                auth_ids = list(set(auth_ids + group_auth_ids))
            # 从关联表提取 sys_user
            sys_list = []
            for aid in auth_ids:
                rows = t_auth_host_sys_user.query.filter_by(auth_id=aid).all()
                for r in rows:
                    sys_list.append(r.sys_user_alias)
            name_list = list(set(sys_list))
            return jsonify({'code': 0, 'msg': name_list})
        except IOError:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    @property
    def sys_user_list(self):
        try:
            user_type = request_param('type')
            if user_type == 'user_id':
                sys_user_id = request_param("id")
                # REV47-M6: 业务查询过滤软删
                query_msg = t_sys_user.query.filter_by(id=sys_user_id, is_deleted=False).first()
                list_msg = self.ls_tool.dict_reset_pop_auto(query_msg)
                list_msg.update({'code': 0})
                return jsonify(list_msg)
            elif user_type == 'user_alias':
                sys_user_alias = request_param("alias")
                # REV47-M6: 业务查询过滤软删
                query_msg = t_sys_user.query.filter_by(alias=sys_user_alias, is_deleted=False).first()
                list_msg = self.ls_tool.dict_reset_pop_auto(query_msg)
                list_msg.update({'code': 0})
                return jsonify(list_msg)
        except IOError:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    @property
    def sys_user_list_all(self):
        try:
            table_page = request_param('page')
            table_limit = request_param('limit')
            # BUGFIX: 前端 list_all 不传 page/limit 时返回全部记录
            base_query = t_sys_user.query.filter_by(is_deleted=False)
            if table_page and table_limit:
                table_offset = (int(table_page) - 1) * int(table_limit)
                query_msg = base_query.offset(table_offset).limit(int(table_limit)).all()
            else:
                query_msg = base_query.all()
            list_msg = self.ls_tool.dict_ls_reset_dict_auto(query_msg)
            # key信息过滤掉具体路径，只返回名字
            for i in list_msg:
                if i.get('host_key'):
                    i['host_key'] = re.sub(FILE_CONF['key_path'], '', i['host_key'])
                if i.get('host_password'):
                    i['host_password'] = '********'
            len_msg = base_query.count()
            return jsonify({"code": 0,
                            "sys_user_list_msg": list_msg,
                            "msg": "",
                            "sys_user_len_msg": len_msg})
        except (IOError, TypeError, ValueError) as e:
            return jsonify({"code": 2, "msg": f"服务器内部错误: {type(e).__name__}"})


class SysUserDel(CzToolsLog):
    def __init__(self):
        super(SysUserDel, self).__init__()
        self.alias = request_param('alias')
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()
        self.new_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    @property
    def host_del(self):
        # REV16 B6 HIGH-1: alias 白名单
        if not isinstance(self.alias, str) or not _ALIAS_RE.fullmatch(self.alias):
            return jsonify({'code': 100, 'msg': 'invalid alias'})
        # REV47-M6: soft_delete - 标记 is_deleted=True 而非物理删除
        user_chk = t_sys_user.query.filter_by(alias=self.alias, is_deleted=False).first()
        if user_chk:
            if user_chk.host_key:
                key_path = FILE_CONF['key_path'] + user_chk.alias + '_rsa'
                real_key = os.path.realpath(key_path)
                real_root = os.path.realpath(FILE_CONF['key_path'])
                if os.path.commonpath([real_key, real_root]) == real_root and os.path.isfile(real_key):
                    os.remove(real_key)
            user_chk.is_deleted = True
            db.session.commit()
            self.host_log(self.cz_name, '资产用户操作', '删除资产用户', self.alias, '成功')
            AuthAutoUpdate.sys_user_auth()
            return jsonify({'code': 0})
        else:
            self.host_log(self.cz_name, '资产用户操作', '删除资产用户', self.alias, '失败', '系统内没有该用户')
            return jsonify({'code': 100, 'msg': '操作权限不足'})


class SysUserAdd(CzToolsLog):
    def __init__(self):
        super(SysUserAdd, self).__init__()
        self.alias = request_param('alias')
        self.host_user = request_param('host_user')
        self.host_password = request_param('host_password', default=None)
        # 新增获取传入的key文件
        self.host_key = request.files.get('host_key')

        self.agreement = request_param('agreement')
        self.remarks = request_param('remarks', default=None)
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()

    @property
    def host_add(self):
        # REV16 B6 HIGH-1: alias 白名单（防路径越界 + chmod 攻击）
        if not isinstance(self.alias, str) or not _ALIAS_RE.fullmatch(self.alias):
            self.host_log(self.cz_name, '资产用户操作', '新增资产用户',
                          getattr(self, 'alias', None), '失败', 'alias 不合法')
            return jsonify({'code': 100, 'msg': 'invalid alias: must match [A-Za-z0-9_.-]{1,32}'})
        try:
            # REV47-M6: 业务查询过滤软删 (同名检查让软删 alias 可复用)
            user_chk = t_sys_user.query.filter_by(alias=self.alias, is_deleted=False).first()
            if user_chk is None:
                # 保存key文件 判断文件是否存在，后续逻辑待优化
                if self.host_key:
                    key_path = FILE_CONF['key_path'] + self.alias + '_rsa'
                    real_key = os.path.realpath(key_path)
                    real_root = os.path.realpath(FILE_CONF['key_path'])
                    if os.path.commonpath([real_key, real_root]) != real_root:
                        return jsonify({'code': 100, 'msg': 'path traversal blocked'})
                    self.host_key.save(key_path)
                    os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
                else:
                    key_path = None
                if self.host_password:
                    # Fernet 对称加密（替代原 base64_auto；不能解密为明文的存储会带来
                    # 数据库泄露即密钥泄露的风险，Fernet 需 OGS_FERNET_KEY 才能解密）
                    password_en = encrypt_host_password(self.host_password)
                else:
                    password_en = None
                osql_in('t_sys_user', alias=self.alias, host_user=self.host_user, host_password=password_en, host_key=key_path,
                        agreement=self.agreement,
                        remarks=self.remarks)
                self.host_log(self.cz_name, '资产用户操作', '新增资产用户', self.alias, '成功')
                AuthAutoUpdate.sys_user_auth()
                return jsonify({'code': 0})
            else:
                self.host_log(self.cz_name, '资产用户操作', '新增资产用户', self.alias, '失败', '该资产用户已存在')
                return jsonify({'code': 100, 'msg': '操作权限不足'})
        except IOError:
            self.host_log(self.cz_name, '资产用户操作', '新增资产用户', self.alias, '失败', '连接数据库失败')
            return jsonify({'code': 100, 'msg': '服务器内部错误'})
        except Exception:
            self.host_log(self.cz_name, '资产用户操作', '新增资产用户', self.host_user, '失败', '未知错误')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class SysUserUpdate(SysUserAdd):
    def __init__(self):
        super(SysUserUpdate, self).__init__()
        self.id = request_param('id')
        self.nums = request_param('nums')

    @property
    def update(self):
        # REV16 B6 HIGH-1: alias 白名单（防路径越界）
        if not isinstance(self.alias, str) or not _ALIAS_RE.fullmatch(self.alias):
            self.host_log(self.cz_name, '资产用户操作', '修改资产用户',
                          getattr(self, 'alias', None), '失败', 'alias 不合法')
            return jsonify({'code': 100, 'msg': 'invalid alias: must match [A-Za-z0-9_.-]{1,32}'})
        query_msg = t_sys_user.query.filter_by(id=self.id).first()
        try:
            if self.host_password:
                password_en = encrypt_host_password(self.host_password)
            else:
                password_en = query_msg.host_password
            if self.host_key:
                key_path = FILE_CONF['key_path'] + self.alias + '_rsa'
                real_key = os.path.realpath(key_path)
                real_root = os.path.realpath(FILE_CONF['key_path'])
                if os.path.commonpath([real_key, real_root]) != real_root:
                    return jsonify({'code': 100, 'msg': 'path traversal blocked'})
                self.host_key.save(key_path)
                os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
            else:
                key_path = query_msg.host_key
            t_sys_user.query.filter_by(id=self.id).update({'alias': self.alias, 'host_user': self.host_user,
                                                           'host_password': password_en,
                                                           'agreement': self.agreement,
                                                           'host_key': key_path, 'remarks': self.remarks})
            db.session.commit()
            self.host_log(self.cz_name, '资产用户操作', '修改资产用户', self.host_user, '成功')
            AuthAutoUpdate.sys_user_auth()
            return jsonify({'code': 0})
        except Exception:
            self.host_log(self.cz_name, '资产用户操作', '修改资产用户', self.host_user, '失败', '连接数据失败')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})
