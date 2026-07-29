from datetime import datetime
import re
from typing import Any, Optional
from flask import Response, request, jsonify
from sqlalchemy import func
from sqlalchemy.orm import Query
from app.core.db.database import t_login_log, t_command_log, t_cz_log
from app.tools.SqlListTool import ListTool
from app.core.types import JsonOrResponse  # ti3-HINT: 公共返回类型
from app.tools.apierr import api_response
from app.tools.at import request_param
# REV28-L6: 日志查询接受的日期格式 (前端 laydate 默认).
#   限定 'YYYY-MM-DD' 与 'YYYY-MM-DD HH:MM:SS' 两种, 避免 SQL 比较传入任意字符串.
_DATE_FORMATS = ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S')


def _parse_jg_date(s: Optional[str]) -> Optional[datetime]:
    """REV28-L6: 解析日期/日期时间, 不合法返 None.
    支持 'YYYY-MM-DD' 与 'YYYY-MM-DD HH:MM:SS'.
    """
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


class LogsMeta:
    def __init__(self) -> None:
        self.lt = ListTool
        page_raw: Optional[str] = request_param('page')
        limit_raw: Optional[str] = request_param('limit')
        # REVIEW-7-P1-3: int(None) 防护, 默认 page=1 limit=10
        try:
            self.table_offset: int = (int(page_raw or 1) - 1) * 10
        except (TypeError, ValueError):
            self.table_offset = 0
        try:
            # REVIEW-7-P2-2: limit 上限 200, 防止 DoS
            self.table_limit: int = min(int(limit_raw or 10), 200)
        except (TypeError, ValueError):
            self.table_limit = 10
        self.log_type: Optional[str] = request_param("log_type", default=None)
        audit_ref_raw: Optional[str] = request_param("audit_ref", default=None)
        audit_ref = audit_ref_raw.strip() if audit_ref_raw else ""
        self.audit_ref: Optional[str] = None
        self.invalid_audit_ref = False
        if audit_ref:
            if (
                self.log_type == "command"
                and re.fullmatch(r"[0-9a-f]{32}/[0-9a-f]{32}", audit_ref)
            ):
                self.audit_ref = audit_ref
            else:
                self.invalid_audit_ref = True
        if self.log_type == "login":
            self.table = t_login_log
        elif self.log_type == "command":
            self.table = t_command_log
        elif self.log_type == "cz":
            self.table = t_cz_log
        else:
            # REVIEW-7-P0-2: 缺省 log_type=None 时, self.table 未设, 后续 .query 报 AttributeError → 审计页默认请求 500
            self.table = t_login_log  # 默认查登录日志 (最常用)


class LogList(LogsMeta):
    # REV28-L2: 三个查询方法都重复 .offset(self.table_offset).limit(self.table_limit),
    # 提取 _paginate 私有方法消除重复, 返回 query (调用方继续 .order_by 等操作).
    def _paginate(self, query: Query) -> Query:
        return query.offset(self.table_offset).limit(self.table_limit)

    def get_logs(self) -> JsonOrResponse:
        try:
            if self.invalid_audit_ref:
                response, _status = api_response(
                    log_list_msg=[],
                    log_len_msg=0,
                )
                return response
            base_q = self.table.query
            if self.table is t_command_log and self.audit_ref:
                base_q = base_q.filter(
                    t_command_log.log_type == "AI 批量命令",
                    t_command_log.log_reason.contains(
                        "ref={}".format(self.audit_ref),
                        autoescape=True,
                    ),
                )
            query_msg = self._paginate(
                base_q.order_by(self.table.log_time.desc())
            ).all()
            list_msg = self.lt.time_ls_dict_que(query_msg, 'id', 'log_time')
            len_msg = base_q.count()
            return jsonify({"code": 0,
                            "log_list_msg": list_msg,
                            "msg": "",
                            "log_len_msg": len_msg})
        except Exception:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})

    def get_select_logs(self) -> JsonOrResponse:
        log_jg_date = request_param('log_jg_date')
        # REV28-H4: 转义 LIKE 通配符 % 和 _, 防 SQL LIKE 注入
        safe_date = (log_jg_date or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        try:
            # REV28-L2: 提取 _paginate 复用 offset/limit
            base_q = self.table.query.filter(
                self.table.log_time.like("%{}%".format(safe_date), escape='\\')
            )
            query_msg = self._paginate(base_q).all()
            list_msg = self.lt.time_ls_dict_que(query_msg, 'id', 'log_time')
            len_msg = base_q.count()
            return jsonify({"code": 0,
                            "log_list_msg": list_msg,
                            "msg": "",
                            "log_len_msg": len_msg})
        except Exception:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    def get_date_logs(self) -> JsonOrResponse:
        log_jg_date = request_param('login_jg_date')
        # REVIEW-7-P1-4: split 长度校验, 无分隔符时 IndexError
        msg = log_jg_date.split(' - ') if log_jg_date else []
        if len(msg) != 2:
            return jsonify({"code": 100, "msg": "日期格式应为 'YYYY-MM-DD - YYYY-MM-DD'"})
        # REV28-L6: 显式校验两端均为合法日期格式 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS),
        # 防止任意外部字符串进入 SQL 比较 (如 '1=1' 或其他 SQL payload 干扰 ORM 行为).
        start_dt = _parse_jg_date(msg[0])
        end_dt = _parse_jg_date(msg[1])
        if start_dt is None or end_dt is None:
            return jsonify({"code": 100,
                            "msg": "日期格式错误, 应为 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS'"})
        if start_dt > end_dt:
            return jsonify({"code": 100, "msg": "起始日期不能晚于结束日期"})
        try:
            # REV28-L6: 使用校验后的 ISO 字符串, 保证入库格式统一.
            start_iso = start_dt.strftime('%Y-%m-%d %H:%M:%S')
            end_iso = end_dt.strftime('%Y-%m-%d %H:%M:%S')
            # REV28-L2: 提取 _paginate 复用 offset/limit, 复用 base_q 避免重复构造
            base_q = self.table.query.filter(self.table.log_time >= start_iso).filter(
                self.table.log_time <= end_iso).order_by(self.table.log_time.desc())
            query_msg = self._paginate(base_q).all()
            # REVIEW-7-P0-3: 'login_time' 改为 'log_time', 原字段名错位导致时间戳永远 None
            list_msg = self.lt.time_ls_dict_que(query_msg, 'id', 'log_time')
            len_msg = base_q.count()
            return jsonify({"code": 0,
                            "log_list_msg": list_msg,
                            "msg": "",
                            "log_len_msg": len_msg})
        except Exception:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})


class LoginIpTop:
    """REV34-M12: 登录 IP Top N 聚合接口.

    取代前端 Dashboard.loadLoginTop 的客户端拉 50 条日志 + JS 聚合样本估算：
    1. 后端一次 SQL group by 拿到全量分布
    2. 仅返 top N（默认 5），减少 payload
    3. 可选日期范围过滤
    """

    def __init__(self) -> None:
        # limit 上限 50，避免单次返回过多
        try:
            self.limit = min(int(request_param('limit') or 5), 50)
        except (TypeError, ValueError):
            self.limit = 5
        # 可选日期范围 (与 get_date_logs 保持一致的解析)
        self.start_dt = _parse_jg_date(request_param('start'))
        self.end_dt = _parse_jg_date(request_param('end'))
        if self.start_dt is not None and self.end_dt is not None and self.start_dt > self.end_dt:
            self.start_dt, self.end_dt = self.end_dt, self.start_dt  # 容忍顺序颠倒，自动交换

    def get_ip_top(self) -> JsonOrResponse:
        try:
            # 合并 nw + gw 视为同一 IP 源（用户场景是“登录来源 IP”）
            # 过滤 NULL / '-' / '' / 'unknown' 等无效值
            base = t_login_log.query.filter(
                t_login_log.log_nw_ip.isnot(None),
                t_login_log.log_nw_ip != '',
                t_login_log.log_nw_ip != '-',
                t_login_log.log_nw_ip != 'unknown',
            )
            if self.start_dt is not None:
                base = base.filter(t_login_log.log_time >= self.start_dt.strftime('%Y-%m-%d %H:%M:%S'))
            if self.end_dt is not None:
                base = base.filter(t_login_log.log_time <= self.end_dt.strftime('%Y-%m-%d %H:%M:%S'))
            rows = (
                base.with_entities(t_login_log.log_nw_ip, func.count(t_login_log.id).label('cnt'))
                .group_by(t_login_log.log_nw_ip)
                .order_by(func.count(t_login_log.id).desc())
                .limit(self.limit)
                .all()
            )
            ip_list = [r[0] for r in rows]
            cnt_list = [int(r[1]) for r in rows]
            return jsonify({'code': 0, 'ip_msg': ip_list, 'cnt_msg': cnt_list})
        except Exception:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})
