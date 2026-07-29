import itertools
from flask import request, jsonify


class ListTool:
    # 列表集合整合成一个列表
    @staticmethod
    def list_gather(ls_str):
        msg = list(itertools.chain.from_iterable(ls_str))
        return msg

    # 去重整合
    @staticmethod
    def list_rep_gather(ls_str):
        msg = list(itertools.chain.from_iterable(set(ls_str)))
        return msg

    # 查询的dict传list（去掉_sa_instance_state）
    @staticmethod
    def dict_reset_pop_auto(one_dict, pop=None):
        msg = one_dict.__dict__
        msg.pop('_sa_instance_state')
        if pop:
            msg.pop(pop)
        return msg

    # 查询的dict组传list内dict组
    @staticmethod
    def dict_ls_reset_dict_auto(ls_dict, *args):
        msg = []
        for ds in ls_dict:
            ds_ls = ds.__dict__
            ds_ls.pop('_sa_instance_state')
            if args:
                for y in args:
                    ds_ls.pop(y)
            msg.append(ds_ls)
        return msg

    @staticmethod
    def time_ls_dict_que(ls_dict, pop=None, log_time=None):
        msg = []
        for ds in ls_dict:
            ds_ls = ds.__dict__
            ds_ls[log_time] = str(ds_ls[log_time])
            ds_ls.pop('_sa_instance_state')
            if pop:
                ds_ls.pop(pop)
            msg.append(ds_ls)
        return msg

    # ---- 分页查询公共方法 ----

    @staticmethod
    def paginated_query(query, list_key, len_key, pop_fields=None, per_page=10):
        """通用分页查询，返回标准的 jsonify 结果。

        :param query: SQLAlchemy query 对象（如 t_host.query）
        :param list_key: 列表数据的 JSON key（如 'host_list_msg'）
        :param len_key: 总数的 JSON key（如 'host_len_msg'）
        :param pop_fields: 需要从结果中剔除的字段名，如 ('password',)
        :param per_page: 每页条数，默认 10
        :return: jsonify 结果
        """
        from app.tools.at import request_param  # 延迟导入避免循环依赖
        table_page = request_param('page')
        table_limit = request_param('limit')
        if table_page and table_limit:
            offset = (int(table_page) - 1) * int(table_limit)
            items = query.offset(offset).limit(table_limit).all()
        else:
            items = query.all()
        list_msg = ListTool.dict_ls_reset_dict_auto(items, *pop_fields) if pop_fields else ListTool.dict_ls_reset_dict_auto(items)
        total = query.count()
        return jsonify({"code": 0, list_key: list_msg, "msg": "", len_key: total})
