import time

from flask import request, jsonify

from app.core.db.database import t_group, t_auth_host, t_host, db, \
    t_auth_host_user, t_auth_host_host_group
from app.core.db.insert import osql_in
from app.tools.audlog import CzToolsLog
from app.tools.SqlListTool import ListTool
from app.tools.at import auth_list_get, get_current_user, Log, request_param
from app.tools.auto_update import AuthAutoUpdate
from app.tools.redisdb import ConnRedis


class ServerGroupList:
    def __init__(self):
        self.lt = ListTool
        self.ords = ConnRedis()

    @property
    def group_list(self):
        try:
            group_id = request_param("id")
            # REV47-M6: 业务查询过滤软删
            query_msg = t_group.query.filter_by(id=group_id, is_deleted=False).first()
            list_msg = self.lt.dict_reset_pop_auto(query_msg)
            list_msg.update({'code': 0})
            return jsonify(list_msg)
        except IOError:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    @property
    def group_name_list(self):
        user_token = request.cookies.get('ogs_token')
        # REV25-L2: user_token 判空, 避免 Redis TypeError + 日志污染
        name = self.ords.conn.get(user_token) if user_token else None
        if not name:
            return jsonify({'code': 100, 'msg': '未登录或会话已过期'})
        try:
            # 通过关联表查询用户有权限的 auth_host，再取 host_group
            auth_ids = [r.auth_id for r in t_auth_host_user.query.filter_by(user_name=name).all()]
            host_group_names = set()
            for aid in auth_ids:
                rows = t_auth_host_host_group.query.filter_by(auth_id=aid).all()
                for r in rows:
                    host_group_names.add(r.group_name)
            group_list = list(host_group_names)
            return jsonify({'code': 0, 'group_name_list_msg': group_list})
        except AttributeError:
            return jsonify({"code": 0,
                            "group_list_msg": '',
                            "msg": "",
                            "group_len_msg": 0})
        except IOError:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})

    @property
    def group_list_all(self):
        try:
            auth_list = auth_list_get()
            # REV47-M6: 业务查询过滤软删
            return ListTool.paginated_query(
                t_group.query.filter(t_group.name.in_(auth_list), t_group.is_deleted == False),
                'group_list_msg', 'group_len_msg')
        except AttributeError:
            return jsonify({"code": 0, "group_list_msg": '', "msg": "", "group_len_msg": 0})
        except IOError:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})


class ServerGroupDel(CzToolsLog):
    def __init__(self):
        super(ServerGroupDel, self).__init__()
        self.name = request_param('name')
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()
        self.new_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    @property
    def host_del(self):
        # REV25-L5: name 未校验非空, 可导致空查询或异常
        if not isinstance(self.name, str) or not self.name.strip():
            return jsonify({'code': 100, 'msg': 'invalid group name'})
        # REV47-M6: soft_delete - 标记 is_deleted=True 而非物理删除
        user_chk = t_group.query.filter_by(name=self.name, is_deleted=False).first()
        if user_chk:
            # REV25-M3: 级联删除主机前检查, 组内有主机时拒绝删除
            query_host = t_host.query.filter_by(group=user_chk.name, is_deleted=False).all()
            if query_host:
                self.host_log(self.cz_name, '资产组操作', '删除资产组', self.name, '失败',
                              '组内仍有 %d 台主机, 请先转移' % len(query_host))
                return jsonify({'code': 100, 'msg': '组内仍有主机, 请先转移后再删除'})
            user_chk.is_deleted = True
            db.session.commit()
            self.host_log(self.cz_name, '资产组操作', '删除资产组', self.name, '成功')
            AuthAutoUpdate.host_group_auth()
            return jsonify({'code': 0})
        else:
            self.host_log(self.cz_name, '资产组操作', '删除资产组', self.name, '失败', '系统内没有该资产组')
            return jsonify({'code': 100, 'msg': '操作权限不足'})


class ServerGroupAdd(CzToolsLog):
    def __init__(self):
        super(ServerGroupAdd, self).__init__()
        self.name = request_param('name')
        self.remarks = request_param('remarks', type=str, default=None)
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()

    @property
    def host_add(self):
        try:
            # REV47-M6: 业务查询过滤软删 (同名检查让软删 name 可复用)
            user_chk = t_group.query.filter_by(name=self.name, is_deleted=False).first()
            if user_chk is None:
                osql_in('t_group', name=self.name, remarks=self.remarks)
                self.host_log(self.cz_name, '资产组操作', '新增资产组', self.name, '成功')
                AuthAutoUpdate.host_group_auth()
                return jsonify({'code': 0})
            else:
                self.host_log(self.cz_name, '资产组操作', '新增资产组', self.name, '失败', '该资产组已存在')
                return jsonify({'code': 100, 'msg': '操作权限不足'})
        except IOError:
            self.host_log(self.cz_name, '资产组操作', '新增资产组', self.name, '失败', '连接数据库失败')
            return jsonify({'code': 100, 'msg': '服务器内部错误'})
        except Exception:
            self.host_log(self.cz_name, '资产组操作', '新增资产组', self.name, '失败', '未知错误')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class ServerGroupUpdate(ServerGroupAdd):
    def __init__(self):
        super(ServerGroupUpdate, self).__init__()
        self.id = request_param('id')
        self.nums = request_param('nums')

    @property
    def update(self):
        # REV25-L6: id/nums 未校验数字, 可导致异常
        try:
            int(self.id)
            int(self.nums)
        except (TypeError, ValueError):
            return jsonify({'code': 100, 'msg': 'invalid id/nums parameter'})
        # REV25-M4: 显式事务, 异常时 rollback (原单次 commit 但无 rollback 保护)
        try:
            old_group = t_group.query.filter_by(
                id=self.id, is_deleted=False).first()
            if old_group is None:
                return jsonify({'code': 100, 'msg': '资产组不存在'})
            # GROUP-RENAME: t_host.group 与 t_auth_host_host_group.group_name
            # 都使用 ON UPDATE CASCADE。只更新主表，避免先写入尚不存在的新组名
            # 触发外键错误，也让主机与授权关系在同一事务内原子跟随。
            t_group.query.filter_by(id=self.id).update({'name': self.name, 'nums': self.nums, 'remarks': self.remarks})
            db.session.commit()
            self.host_log(self.cz_name, '资产组操作', '修改资产组', self.name, '成功')
            AuthAutoUpdate.host_group_auth()
            return jsonify({'code': 0})
        except Exception as e:
            db.session.rollback()
            # P0-LOW-2: 生产代码禁用 print, 改为结构化 logger
            Log.logger.error('server_group update failed: %s' % e, exc_info=True)
            self.host_log(self.cz_name, '资产组操作', '修改资产组', self.name, '失败', '连接数据库错误')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})
