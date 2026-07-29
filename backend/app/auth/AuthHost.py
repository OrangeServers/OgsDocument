from typing import Any, Dict, List, Optional
from flask import request, jsonify
from app.tools.SqlListTool import ListTool
from app.tools.audlog import CzToolsLog
from app.users.user import _require_admin_or_raise  # REV42-H1: 类内 admin 鉴权
from app.core.db.database import t_auth_host, t_group, t_acc_user, t_sys_user, t_acc_group, db, \
    t_auth_host_user, t_auth_host_user_group, t_auth_host_host_group, t_auth_host_sys_user
from app.core.db.insert import osql_in
from app.tools.at import request_param, request_param_list
from app.core.types import JsonOrResponse  # ti3-HINT: 公共返回类型


class AuthHostList:
    def __init__(self) -> None:
        self.lt = ListTool

    @property
    def create_auth_list(self) -> Optional[JsonOrResponse]:  # type: ignore[return]
        req_type = request_param("req_type")
        auth_list = []
        if req_type == 'user':
            query_user_name = t_acc_user.query.with_entities(t_acc_user.name).all()
            user_name = self.lt.list_gather(query_user_name)
            for i in user_name:
                auth_list.append({'name': i, 'value': i})
            return jsonify({'msg': auth_list})

        elif req_type == 'user_group':
            query_group_name = t_acc_group.query.with_entities(t_acc_group.name).all()
            group_name = self.lt.list_gather(query_group_name)
            for i in group_name:
                auth_list.append({'name': i, 'value': i})
            return jsonify({'msg': auth_list})

        elif req_type == 'host_group':
            query_group_name = t_group.query.with_entities(t_group.name).all()
            group_name = self.lt.list_gather(query_group_name)
            for i in group_name:
                auth_list.append({'name': i, 'value': i})
            return jsonify({'msg': auth_list})

        elif req_type == 'sys_user':
            query_user_name = t_sys_user.query.with_entities(t_sys_user.alias).all()
            user_name = self.lt.list_gather(query_user_name)
            for i in user_name:
                auth_list.append({'name': i, 'value': i})
            return jsonify({'msg': auth_list})

    @property
    def auth_group_role(self) -> Optional[JsonOrResponse]:  # type: ignore[return]
        auth_name = request_param('name')
        req_type = request_param("req_type")
        # REV42-H2 (R2-3-1): req_type 为 None 或空字符串时早返, 避免 fall through 返回 None 让前端拿到空响应
        if not req_type:
            return jsonify({'code': 100, 'msg': 'req_type is required'})
        auth_list = []
        if req_type == 'all':
            try:
                query_auth_msg = t_auth_host.query.filter_by(name=auth_name).first()
                return jsonify({'code': 0, 'msg': [{'name': query_auth_msg.name, 'remarks': query_auth_msg.remarks}]})
            except IOError:
                return jsonify({'code': 100, 'msg': 'fail'})

        elif req_type == 'user':
            try:
                query_user_name = t_acc_user.query.with_entities(t_acc_user.name).all()
                user_name = self.lt.list_gather(query_user_name)
                query_auth_msg = t_auth_host.query.filter_by(name=auth_name).first()
                selected_users = [r.user_name for r in t_auth_host_user.query.filter_by(auth_id=query_auth_msg.id).all()]
                for i in user_name:
                    if i in selected_users:
                        auth_list.append({'name': i, 'value': i, 'selected': 'selected'})
                    else:
                        auth_list.append({'name': i, 'value': i})
                return jsonify({'msg': auth_list})
            except IOError:
                return jsonify({'msg': 'fail'})

        elif req_type == 'user_group':
            try:
                query_group_name = t_acc_group.query.with_entities(t_acc_group.name).all()
                group_name = self.lt.list_gather(query_group_name)
                query_auth_msg = t_auth_host.query.filter_by(name=auth_name).first()
                selected_groups = [r.group_name for r in t_auth_host_user_group.query.filter_by(auth_id=query_auth_msg.id).all()]
                for i in group_name:
                    if i in selected_groups:
                        auth_list.append({'name': i, 'value': i, 'selected': 'selected'})
                    else:
                        auth_list.append({'name': i, 'value': i})
                return jsonify({'msg': auth_list})
            except IOError:
                return jsonify({'msg': 'fail'})

        elif req_type == 'host_group':
            try:
                query_group_name = t_group.query.with_entities(t_group.name).all()
                group_name = self.lt.list_gather(query_group_name)
                query_auth_msg = t_auth_host.query.filter_by(name=auth_name).first()
                selected_groups = [r.group_name for r in t_auth_host_host_group.query.filter_by(auth_id=query_auth_msg.id).all()]
                for i in group_name:
                    if i in selected_groups:
                        auth_list.append({'name': i, 'value': i, 'selected': 'selected'})
                    else:
                        auth_list.append({'name': i, 'value': i})
                return jsonify({'msg': auth_list})
            except IOError:
                return jsonify({'msg': 'fail'})

        elif req_type == 'sys_user':
            try:
                query_user_name = t_sys_user.query.with_entities(t_sys_user.alias).all()
                user_name = self.lt.list_gather(query_user_name)
                query_auth_msg = t_auth_host.query.filter_by(name=auth_name).first()
                selected_users = [r.sys_user_alias for r in t_auth_host_sys_user.query.filter_by(auth_id=query_auth_msg.id).all()]
                for i in user_name:
                    if i in selected_users:
                        auth_list.append({'name': i, 'value': i, 'selected': 'selected'})
                    else:
                        auth_list.append({'name': i, 'value': i})
                return jsonify({'msg': auth_list})
            except IOError:
                return jsonify({'msg': 'fail'})

    @property
    def auth_host_list(self) -> JsonOrResponse:
        try:
            acc_user_id = request_param("id")
            query_msg = t_auth_host.query.filter_by(id=acc_user_id).first()
            # P1-1: id 非法或不存在时 query_msg 是 None, 原代码 query_msg.id AttributeError 500
            if query_msg is None:
                return jsonify({"code": 100, "msg": "授权规则不存在"})
            list_msg = self.lt.dict_reset_pop_auto(query_msg)
            # 补充关联表数据为数组
            auth_id = query_msg.id
            list_msg['user'] = [r.user_name for r in t_auth_host_user.query.filter_by(auth_id=auth_id).all()]
            list_msg['user_group'] = [r.group_name for r in t_auth_host_user_group.query.filter_by(auth_id=auth_id).all()]
            list_msg['host_group'] = [r.group_name for r in t_auth_host_host_group.query.filter_by(auth_id=auth_id).all()]
            list_msg['sys_user'] = [r.sys_user_alias for r in t_auth_host_sys_user.query.filter_by(auth_id=auth_id).all()]
            return jsonify(list_msg)
        except IOError:
            return jsonify({"auth_host_list_msg": 'select list msg error'})

    @property
    def auth_host_list_all(self) -> JsonOrResponse:
        try:
            result = ListTool.paginated_query(t_auth_host.query, 'auth_host_list_msg', 'auth_host_len_msg')
            result_data = result.get_json()
            if result_data and 'auth_host_list_msg' in result_data:
                # 批量收集所有 auth_id
                all_ids = [item.get('id') for item in result_data['auth_host_list_msg'] if item.get('id')]
                # 一次查询拿回所有关联数据
                user_map: Dict[int, List[str]] = {}
                ug_map: Dict[int, List[str]] = {}
                hg_map: Dict[int, List[str]] = {}
                su_map: Dict[int, List[str]] = {}
                if all_ids:
                    for r in t_auth_host_user.query.filter(t_auth_host_user.auth_id.in_(all_ids)).all():
                        user_map.setdefault(r.auth_id, []).append(r.user_name)
                    for r in t_auth_host_user_group.query.filter(t_auth_host_user_group.auth_id.in_(all_ids)).all():
                        ug_map.setdefault(r.auth_id, []).append(r.group_name)
                    for r in t_auth_host_host_group.query.filter(t_auth_host_host_group.auth_id.in_(all_ids)).all():
                        hg_map.setdefault(r.auth_id, []).append(r.group_name)
                    for r in t_auth_host_sys_user.query.filter(t_auth_host_sys_user.auth_id.in_(all_ids)).all():
                        su_map.setdefault(r.auth_id, []).append(r.sys_user_alias)
                for item in result_data['auth_host_list_msg']:
                    aid = item.get('id')
                    if aid:
                        item['user'] = user_map.get(aid, [])
                        item['user_group'] = ug_map.get(aid, [])
                        item['host_group'] = hg_map.get(aid, [])
                        item['sys_user'] = su_map.get(aid, [])
                return jsonify(result_data)
            return result
        except IOError:
            return jsonify({"auth_host_list_msg": 'select list msg error', "auth_host_len_msg": 0})


class AuthHostDel(CzToolsLog):  # REV42-H1 + H5: 加类内鉴权 + 审计基类
    def __init__(self) -> None:
        super(AuthHostDel, self).__init__()
        _require_admin_or_raise()  # REV42-H1: 类内 admin 兜底
        # self.host_ip = request_param('host_ip')
        self.name = request_param('name')

    @property
    def auth_host_del(self) -> Optional[JsonOrResponse]:  # type: ignore[return]
        # REV47-M6: soft_delete - 标记 is_deleted=True 而非物理删除
        #   系统权限"所有权限"永不可删 (与物理删除一致保护)
        auth_chk = t_auth_host.query.filter_by(name=self.name, is_deleted=False).first()
        if auth_chk:
            if self.name != '所有权限':
                auth_chk.is_deleted = True
                db.session.commit()
                return jsonify({'code': 0})
            elif self.name == '所有权限':
                # P0-9: 修正文案（原"授权规则不存在"误导）— 系统权限"不可删除"不是"不存在"
                return jsonify({'code': 100, 'msg': '系统权限不可删除'})
        else:
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class AuthHostAdd(CzToolsLog):  # REV42-H1 + H5: 加类内鉴权 + 审计基类
    def __init__(self) -> None:
        super(AuthHostAdd, self).__init__()
        _require_admin_or_raise()  # REV42-H1: 类内 admin 兜底
        self.name = request_param('name')
        self.user = request_param_list('user')
        self.user_group = request_param_list('user_group')
        self.host_group = request_param_list('host_group')
        self.sys_user = request_param_list('sys_user')
        self.remarks = request_param('remarks', type=str, default=None)

    @property
    def auth_host_add(self) -> JsonOrResponse:
        try:
            # P0-9: 拦截"所有权限"系统规则的新增（防同名覆盖 / 防误增重名）
            if self.name == '所有权限':
                return jsonify({'code': 100, 'msg': '系统权限不可新增'})
            # REV47-M6: 业务查询过滤软删 (同名检查让软删 name 可复用)
            auth_chk = t_auth_host.query.filter_by(name=self.name, is_deleted=False).first()
            if auth_chk is None:
                new_auth = t_auth_host(name=self.name, remarks=self.remarks)
                db.session.add(new_auth)
                db.session.flush()
                try:
                    for u in self.user:
                        if u:
                            db.session.add(t_auth_host_user(auth_id=new_auth.id, user_name=u))
                    for g in self.user_group:
                        if g:
                            db.session.add(t_auth_host_user_group(auth_id=new_auth.id, group_name=g))
                    for g in self.host_group:
                        if g:
                            db.session.add(t_auth_host_host_group(auth_id=new_auth.id, group_name=g))
                    for u in self.sys_user:
                        if u:
                            db.session.add(t_auth_host_sys_user(auth_id=new_auth.id, sys_user_alias=u))
                    db.session.commit()
                    return jsonify({'code': 0})
                except Exception:
                    db.session.rollback()
                    raise
            else:
                return jsonify({'code': 100, 'msg': '授权规则已被使用'})
        except IOError:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})
        except Exception:
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class AuthHostUpdate(AuthHostAdd):
    def __init__(self) -> None:
        super(AuthHostUpdate, self).__init__()
        # REV42-H4 (R2-3-2): 支持改 name 字段.
        # 背景: 旧实现 filter_by(name=self.name) + update({'name': self.name}) 等于没改,
        #       一旦前端 form.value.name 是新名, 旧名 row 查不到 → 永远报"操作失败".
        # 修法: 用 old_name 查 row, 用 self.name (前端传的新名) update; 同时校验 new_name 唯一.
        # 兼容: 前端不传 old_name 时, 走 self.name 查 + update, name 不变.
        self.old_name = request_param('old_name', self.name)

    @property
    def auth_host_update(self) -> JsonOrResponse:
        try:
            # P0-9: 拦截"所有权限"系统规则的修改
            # 原实现未保护 → admin 误改 / 恶意修改都会影响所有用户资产可见性
            if self.name == '所有权限':
                return jsonify({'code': 100, 'msg': '系统权限不可修改'})
            # REV42-H4: 用 old_name 查 row, 支持前端 form.value.name 传新名
            auth_row = t_auth_host.query.filter_by(name=self.old_name).first()
            if not auth_row:
                return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})
            auth_id = auth_row.id
            # REV42-H4: 改名时校验 new_name 不与现有活跃 name 冲突
            if self.name != self.old_name:
                clash = t_auth_host.query.filter_by(name=self.name, is_deleted=False).first()
                if clash is not None:
                    return jsonify({'code': 100, 'msg': '新名称已被使用'})
            # 删除旧关联
            t_auth_host_user.query.filter_by(auth_id=auth_id).delete()
            t_auth_host_user_group.query.filter_by(auth_id=auth_id).delete()
            t_auth_host_host_group.query.filter_by(auth_id=auth_id).delete()
            t_auth_host_sys_user.query.filter_by(auth_id=auth_id).delete()
            try:
                # 写入新关联
                for u in self.user:
                    if u:
                        db.session.add(t_auth_host_user(auth_id=auth_id, user_name=u))
                for g in self.user_group:
                    if g:
                        db.session.add(t_auth_host_user_group(auth_id=auth_id, group_name=g))
                for g in self.host_group:
                    if g:
                        db.session.add(t_auth_host_host_group(auth_id=auth_id, group_name=g))
                for u in self.sys_user:
                    if u:
                        db.session.add(t_auth_host_sys_user(auth_id=auth_id, sys_user_alias=u))
                # REV42-H4: 用 old_name 查 row, update 用 self.name (new_name), 实现改名
                t_auth_host.query.filter_by(name=self.old_name).update(
                    {'name': self.name, 'remarks': self.remarks})
                db.session.commit()
                return jsonify({'code': 0})
            except Exception:
                db.session.rollback()
                raise
        except Exception:
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})
