import time, re
from flask import request, jsonify
from app.tools.SqlListTool import ListTool
from app.core.db.database import t_acc_group, t_acc_user, db
from app.core.db.insert import osql_in, osql_up, SqlOpError  # REV47-M6: 移除 osql_de (改用 osql_up is_deleted=True 软删)
from app.tools.audlog import CzToolsLog
from app.tools.at import get_current_user, get_current_user_role, Log, request_param
from app.tools.auto_update import AuthAutoUpdate
from app.users.user import _require_admin_or_raise  # REV41-H10: 类内 admin 鉴权共享 helper


def _replace_in_csv(csv_value, old, new):
    """REV41-H11-2: 在 CSV 字符串中精确替换 old → new, 避免 re.sub 子串误替换.

    背景: re.sub(r'dev', 'qa', 'dev,developer') 会得到 'qa,qaeloper', 误把 'developer'
    里的 'dev' 也替换了. 这里改用 split + 精确等值匹配, 避免此问题.

    Args:
        csv_value: 形如 "dev,ops,sre" 的字符串
        old: 要替换的精确值
        new: 替换为该值

    Returns:
        替换后的字符串; 输入为空/old 为空时原样返回.
    """
    if not csv_value or not old:
        return csv_value
    parts = csv_value.split(',')
    parts = [new if p == old else p for p in parts]
    return ','.join(parts)


class AccGroupList:
    def __init__(self):
        self.lt = ListTool

    @property
    def group_list(self):
        try:
            group_id = request_param("id")
            # REV47-M6: 业务查询过滤软删
            query_msg = t_acc_group.query.filter_by(id=group_id, is_deleted=False).first()
            list_msg = self.lt.dict_reset_pop_auto(query_msg)
            list_msg.update({'code': 0})
            return jsonify(list_msg)
        except IOError:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    @property
    def group_name_list(self):
        try:
            # REV47-M6: 业务查询过滤软删
            que_auth_group = t_acc_group.query.with_entities(t_acc_group.name).filter_by(is_deleted=False).all()
            group_list = self.lt.list_gather(que_auth_group)
            return jsonify({'code': 0, 'group_name_list_msg': group_list})
        except IOError:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})

    @property
    def group_list_all(self):
        try:
            # REV47-M6: 业务查询过滤软删
            return ListTool.paginated_query(t_acc_group.query.filter_by(is_deleted=False), 'group_list_msg', 'group_len_msg')
        except IOError:
            return jsonify({"host_list_msg": 'select list msg error', "host_len_msg": 0})


class AccGroupDel(CzToolsLog):
    def __init__(self):
        super(AccGroupDel, self).__init__()
        _require_admin_or_raise()  # REV41-H10
        self.name = request_param('name')
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()

    @property
    def host_del(self):
        # REV47-M6: soft_delete - 查 is_deleted=False 行, 标记 is_deleted=True
        user_chk = t_acc_group.query.filter_by(name=self.name, is_deleted=False).first()
        if user_chk:
            # REV41-H12: 不再级联删除属于该组的 user, 而是置 group=NULL
            # REV41-H13 (R2-11): 走 osql_up 统一封装, 失败 SqlOpError 兜底.
            #   背景: 旧实现走裸 commit, 无 rollback, 失败时污染 session;
            #         半途失败还会留下"users 已解绑但 group 还在"的不一致状态.
            #   修复: set group=NULL → osql_up; soft delete group → osql_up is_deleted=True;
            #         任何一步失败 → SqlOpError → rollback → 记录失败审计 + 错误日志.
            try:
                osql_up('t_acc_user', {'group': user_chk.name, 'is_deleted': False}, {'group': None})
                # REV47-M6: 不再 osql_de 物理删除, 改为 osql_up is_deleted=True (软删)
                osql_up('t_acc_group', {'name': self.name}, {'is_deleted': True})
            except SqlOpError as e:
                # R2-11: 与 AccGroupAdd 一致, 失败时走 Log.logger.error + 失败审计.
                Log.logger.error(
                    'R2-11 AccGroupDel host_del failed: name=%s err=%s',
                    self.name, e, exc_info=True)
                self.host_log(
                    self.cz_name, '用户组操作', '删除用户组', self.name,
                    '失败', f'数据库操作失败: {e}')
                return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})
            self.host_log(self.cz_name, '用户组操作', '删除用户组', self.name, '成功')
            AuthAutoUpdate.acc_group_auth()
            return jsonify({'code': 0})
        else:
            self.host_log(self.cz_name, '用户组操作', '删除用户组', self.name, '失败', '系统内没有该用户组')
            return jsonify({'code': 100, 'msg': '操作权限不足'})


class AccGroupAdd(CzToolsLog):
    def __init__(self):
        super(AccGroupAdd, self).__init__()
        _require_admin_or_raise()  # REV41-H10
        self.name = request_param('name')
        self.remarks = request_param('remarks', type=str, default=None)
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()

    @property
    def host_add(self):
        try:
            # REV47-M6: 业务查询过滤软删 (同名检查让软删 name 可复用)
            user_chk = t_acc_group.query.filter_by(name=self.name, is_deleted=False).first()
            if user_chk is None:
                osql_in('t_acc_group', name=self.name, remarks=self.remarks)
                self.host_log(self.cz_name, '用户组操作', '新增用户组', self.name, '成功')
                return jsonify({'code': 0})
            else:
                self.host_log(self.cz_name, '用户组操作', '新增用户组', self.name, '失败', '该用户组已存在')
                return jsonify({'code': 100, 'msg': '操作权限不足'})
        except IOError:
            self.host_log(self.cz_name, '用户组操作', '新增用户组', self.name, '失败', '连接数据库错误')
            return jsonify({'code': 100, 'msg': '服务器内部错误'})
        except Exception:
            self.host_log(self.cz_name, '用户组操作', '新增用户组', self.name, '失败', '未知错误')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class AccGroupUpdate(AccGroupAdd):
    def __init__(self):
        super(AccGroupUpdate, self).__init__()
        # AccGroupAdd.__init__ 已做 admin 校验, 无需重复
        self.id = request_param('id')

    @property
    def update(self):
        try:
            old_group = t_acc_group.query.filter_by(
                id=self.id, is_deleted=False).first()
            if old_group is None:
                return jsonify({'code': 100, 'msg': '用户组不存在'})
            if self.name != old_group.name:
                # AUTH-JUNCTION: 授权已迁移到 t_auth_host_user_group 关联表，
                # 不再读取已删除的 t_auth_host.user_group CSV 字段。关联表外键
                # 使用 ON UPDATE CASCADE，主表改名时由数据库原子更新授权关系。
                t_acc_user.query.filter_by(
                    group=old_group.name, is_deleted=False).update(
                    {'group': self.name}, synchronize_session=False)
            self.host_log(self.cz_name, '用户组操作', '修改用户组', self.name, '成功')
            t_acc_group.query.filter_by(id=self.id).update(
                {'name': self.name, 'remarks': self.remarks})
            db.session.commit()
            AuthAutoUpdate.acc_group_auth()
            return jsonify({'code': 0})
        except Exception as e:
            # P0-LOW-2: 生产代码禁用 print, 改为结构化 logger (带堆栈 + 级别控制)
            Log.logger.error('acc_group update failed: %s' % e, exc_info=True)
            self.host_log(self.cz_name, '用户组操作', '修改用户组', self.name, '失败', '连接数据库错误')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})
