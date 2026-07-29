import ipaddress
import re
import socket
import logging

import paramiko.ssh_exception
from flask import request, jsonify
from werkzeug.utils import secure_filename
from app.tools.shellcmd import RemoteConnectionAuto, get_ssh_connection, _check_dangerous_command, DangerousCommandError  # REV46-M23

from app.core.db.settings import db
from app.core.db.database import t_host, t_group, t_acc_user
from app.core.db.insert import osql_in
from app.tools.audlog import CzToolsLog, ComToolsLog, log_ssh_audit  # REV46-M26
from app.tools.SqlListTool import ListTool
from app.tools.at import (
    auth_list_get,
    get_current_user,
    get_current_user_role,
    request_param,
    request_param_list,
)
from app.tools.auto_update import AuthAutoUpdate
from app.core.config import FILE_CONF
from app.assets.batch_service import (
    DANGEROUS_SCRIPT_PATTERNS,
    MAX_SCRIPT_SIZE,
)

logger = logging.getLogger(__name__)

# REV25-H1: 资产参数校验正则 (复用 SysUser._ALIAS_RE)
_HOST_ALIAS_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,25}$')
# REV25-M5/L7: 批量操作主机数上限
_MAX_BATCH_COUNT = 50

# 主机健康检查 Redis key 前缀和 TTL
_HOST_ONLINE_PREFIX = 'host:online:'
_HOST_ONLINE_TTL = 120  # 秒，检查结果缓存 2 分钟


def check_all_hosts_health():
    """APScheduler 定时调用：TCP 探测所有主机的 SSH 端口，结果写入 Redis。
    轻量级检测：仅尝试 TCP 连接（3s 超时），不需要 SSH 凭据。
    """
    from app.tools.redisdb import ConnRedis
    from app.app_factory import app as flask_app

    with flask_app.app_context():
        ords = ConnRedis()
        hosts = t_host.query.filter_by(is_deleted=False).all()
        online_count = 0

        for h in hosts:
            ip = h.host_ip
            port = int(h.host_port or 22)
            is_online = _tcp_check(ip, port, timeout=3)

            # 写入 Redis
            key = f'{_HOST_ONLINE_PREFIX}{h.id}'
            ords.conn.set(key, '1' if is_online else '0', ex=_HOST_ONLINE_TTL)

            if is_online:
                online_count += 1

        logger.info('Host health check: %d/%d online', online_count, len(hosts))


def _tcp_check(host: str, port: int, timeout: float = 3.0) -> bool:
    """TCP 连接探测：成功返回 True，失败返回 False。"""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, socket.error, OSError):
        return False


def get_host_online_status(host_id: int) -> bool:
    """从 Redis 读取主机在线状态。"""
    from app.tools.redisdb import ConnRedis
    try:
        ords = ConnRedis()
        val = ords.conn.get(f'{_HOST_ONLINE_PREFIX}{host_id}')
        return val == '1' if val else False
    except Exception:
        return False


def get_hosts_online_status(host_ids) -> dict:
    """批量从 Redis 读取主机在线状态，Redis 不可用时全部视为离线。"""
    normalized_ids = [int(host_id) for host_id in host_ids]
    statuses = {host_id: False for host_id in normalized_ids}
    if not normalized_ids:
        return statuses

    from app.tools.redisdb import ConnRedis
    try:
        keys = [f'{_HOST_ONLINE_PREFIX}{host_id}' for host_id in normalized_ids]
        values = ConnRedis().conn.mget(keys)
        return {
            host_id: value == '1'
            for host_id, value in zip(normalized_ids, values)
        }
    except Exception:
        return statuses


def _get_configured_groups() -> set:
    """查询已关联系统用户的主机组集合。

    逻辑：主机组通过权限规则(t_auth_host)关联系统用户(t_auth_host_sys_user)，
    有系统用户的主机组才能执行 SSH 连接，视为“已配置”。
    """
    from app.core.db.database import t_auth_host_host_group, t_auth_host_sys_user
    try:
        # 找出有系统用户的 auth_id
        auth_ids_with_sys_user = {r.auth_id for r in t_auth_host_sys_user.query.all()}
        if not auth_ids_with_sys_user:
            return set()
        # 找出这些 auth_id 对应的主机组
        rows = t_auth_host_host_group.query.filter(
            t_auth_host_host_group.auth_id.in_(auth_ids_with_sys_user)
        ).all()
        return {r.group_name for r in rows}
    except Exception:
        return set()


class ServerList:
    def __init__(self):
        self.lt = ListTool

    @property
    def server_list(self):
        try:
            host_type = request_param('type')
            if host_type == 'host_id':
                host_id = request_param("id")
                # REV25-L3: host_id 未校验数字, 可导致异常查询
                try:
                    int(host_id)
                except (TypeError, ValueError):
                    return jsonify({'code': 100, 'msg': 'invalid id parameter'})
                # REV47-M6: 业务查询过滤软删
                query_msg = t_host.query.filter_by(id=host_id, is_deleted=False).first()
                list_msg = self.lt.dict_reset_pop_auto(query_msg)
                list_msg.update({'code': 0})
                return jsonify(list_msg)
            elif host_type == 'host_alias':
                host_alias = request_param("alias")
                # REV25-L3: host_alias 未校验, 可注入非法字符
                if not isinstance(host_alias, str) or not _HOST_ALIAS_RE.fullmatch(host_alias):
                    return jsonify({'code': 100, 'msg': 'invalid alias parameter'})
                # REV47-M6: 业务查询过滤软删
                query_msg = t_host.query.filter_by(alias=host_alias, is_deleted=False).first()
                list_msg = self.lt.dict_reset_pop_auto(query_msg)
                list_msg.update({'code': 0})
                return jsonify(list_msg)
        except IOError:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    @property
    def server_list_page(self):
        table_page = request_param('page')
        table_limit = request_param('limit')
        # REV25-M1: 分页参数非数字 → ValueError 500, 需 try/except
        try:
            table_offset = (int(table_page) - 1) * 10
            int(table_limit)  # 校验 limit 可转为 int
        except (TypeError, ValueError):
            return jsonify({"code": 100, 'msg': 'invalid page/limit parameter'})
        group_name = request_param('group_name')
        try:
            if group_name == '所有资产':
                return self.server_list_all
            else:
                query_msg = t_host.query.filter_by(group=group_name).offset(table_offset).limit(table_limit).all()
                list_msg = self.lt.dict_ls_reset_dict_auto(query_msg)
                len_msg = t_host.query.filter_by(group=group_name).count()
                return jsonify({"code": 0,
                                "host_list_msg": list_msg,
                                "msg": "",
                                "host_len_msg": len_msg})
        except IOError:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    @property
    def server_list_all(self):
        try:
            auth_list = auth_list_get()
            resp = ListTool.paginated_query(
                t_host.query.filter(t_host.group.in_(auth_list)),
                'host_list_msg', 'host_len_msg')
            # 拼接在线状态 + 配置状态（是否关联系统用户）
            try:
                data = resp.get_json()
                if data and 'host_list_msg' in data:
                    configured_groups = _get_configured_groups()
                    for host in data['host_list_msg']:
                        host['is_online'] = get_host_online_status(host.get('id', 0))
                        host['configured'] = host.get('group', '') in configured_groups
                return jsonify(data)
            except Exception:
                return resp
        except AttributeError:
            return jsonify({"code": 0, "group_list_msg": '', "msg": "", "group_len_msg": 0})
        except IOError:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})


class GroupList:
    def __init__(self):
        self.group = request_param('group')
        self.lt = ListTool

    @property
    def server_list(self):
        try:
            # REV47-M6: 业务查询过滤软删行
            group_list = t_host.query.filter_by(group=self.group, is_deleted=False).all()
            len_msg = t_host.query.filter_by(group=self.group, is_deleted=False).count()
            group_select = self.lt.dict_ls_reset_list(group_list)
            return jsonify({"group_list_msg": group_select,
                            "group_len_msg": len_msg})

        except IOError:
            return jsonify({"group_list_msg": 'select group list msg error',
                            "group_len_msg": 0})


class ServerDel(CzToolsLog):
    def __init__(self):
        super(ServerDel, self).__init__()
        self.host_ip = request_param('host_ip')
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()

    @property
    def host_del(self):
        # REV25-L4: host_ip 未校验 IP 格式, 可注入非法字符串
        if not isinstance(self.host_ip, str) or not self.host_ip:
            return jsonify({'code': 100, 'msg': 'host_ip is required'})
        try:
            ipaddress.ip_address(self.host_ip)
        except ValueError:
            return jsonify({'code': 100, 'msg': 'invalid host_ip format'})
        # REV47-M6: soft_delete - 不再 db.session.delete(), 标记 is_deleted=True
        #   业务查询 .filter_by(is_deleted=False) 隐藏软删行; 可在 admin 后台恢复
        user_chk = t_host.query.filter_by(host_ip=self.host_ip, is_deleted=False).first()
        if user_chk:
            user_chk.is_deleted = True
            db.session.commit()
            self.host_log(self.cz_name, '资产操作', '删除资产', self.host_ip, '成功')
            AuthAutoUpdate.host_grp_count(user_chk.group)
            return jsonify({'code': 0})
        else:
            self.host_log(self.cz_name, '资产操作', '删除资产', self.host_ip, '失败', '系统内没有该资产')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class ServerAdd(CzToolsLog):
    def __init__(self):
        super(ServerAdd, self).__init__()
        self.alias = request_param('alias')
        self.host_ip = request_param('host_ip')
        self.host_port = request_param('host_port')
        self.group = request_param('group', type=str, default='default')
        # 新增记录日志相关
        self.ords, self.cz_name = get_current_user()

    def _validate_params(self):
        """REV25-H1: 资产参数校验。返回 (ok, error_msg)。"""
        # alias: 白名单正则
        if not isinstance(self.alias, str) or not _HOST_ALIAS_RE.fullmatch(self.alias):
            return False, 'invalid alias: must match [A-Za-z0-9_.-]{1,25}'
        # host_ip: IPv4/IPv6 格式校验
        if not isinstance(self.host_ip, str) or not self.host_ip:
            return False, 'host_ip is required'
        try:
            ipaddress.ip_address(self.host_ip)
        except ValueError:
            return False, 'invalid host_ip format'
        # host_port: 1-65535 校验
        try:
            port = int(self.host_port)
        except (TypeError, ValueError):
            return False, 'host_port must be a number'
        if not (1 <= port <= 65535):
            return False, 'host_port must be in range 1-65535'
        # group: 字符集校验 (允许字母数字下划线连字符, 1-32 字符)
        if not isinstance(self.group, str) or not re.fullmatch(r'[A-Za-z0-9_\-]{1,32}', self.group):
            return False, 'invalid group: must match [A-Za-z0-9_-]{1,32}'
        return True, None

    @property
    def host_add(self):
        # REV25-H1: 参数校验前置
        ok, err = self._validate_params()
        if not ok:
            self.host_log(self.cz_name, '资产操作', '新增资产', self.host_ip or '', '失败', err)
            return jsonify({'code': 100, 'msg': err})
        try:
            active_ip = t_host.query.filter_by(
                host_ip=self.host_ip, is_deleted=False).first()
            active_alias = t_host.query.filter_by(
                alias=self.alias, is_deleted=False).first()
            if active_ip is not None or active_alias is not None:
                self.host_log(self.cz_name, '资产操作', '新增资产', self.host_ip, '失败', '该资产已存在')
                return jsonify({'code': 100, 'msg': '操作权限不足'})

            # HOST-SOFT-DELETE-REUSE: alias 有数据库唯一约束，同 alias
            # 重加必须复用软删行。若只是 IP 相同而 alias 不同，则新增一行，
            # 保留历史命令日志等外键继续指向旧 alias。
            deleted_host = t_host.query.filter_by(
                alias=self.alias, is_deleted=True).first()
            if deleted_host is not None:
                deleted_host.alias = self.alias
                deleted_host.host_ip = self.host_ip
                deleted_host.host_port = self.host_port
                deleted_host.group = self.group
                deleted_host.is_deleted = False
                db.session.commit()
            else:
                osql_in(
                    't_host',
                    alias=self.alias,
                    host_ip=self.host_ip,
                    host_port=self.host_port,
                    group=self.group,
                )
            self.host_log(self.cz_name, '资产操作', '新增资产', self.host_ip, '成功')
            AuthAutoUpdate.host_grp_count(self.group)
            return jsonify({'code': 0})
        except IOError:
            self.host_log(self.cz_name, '资产操作', '新增资产', self.host_ip, '失败', '连接主机失败')
            return jsonify({'code': 100, 'msg': '服务器内部错误'})
        except Exception:
            self.host_log(self.cz_name, '资产操作', '新增资产', self.host_ip, '失败', '未知错误')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class ServerUpdate(ServerAdd):
    def __init__(self):
        super(ServerUpdate, self).__init__()
        self.id = request_param('id')

    @property
    def update(self):
        ok, err = self._validate_params()
        if not ok:
            return jsonify({'code': 100, 'msg': err})
        # REV25-M2: id 未校验数字
        try:
            int(self.id)
        except (TypeError, ValueError):
            return jsonify({'code': 100, 'msg': 'invalid id parameter'})
        try:
            # conn = RemoteConnection(self.host_ip, int(self.host_port), self.host_user, self.host_password)
            # conn.ssh_cmd('hostname')
            try:
                up_host = t_host.query.filter_by(id=self.id).first()
                t_host.query.filter_by(id=self.id).update(
                    {'alias': self.alias, 'host_ip': self.host_ip, 'host_port': self.host_port, 'group': self.group})
                db.session.commit()
                self.host_log(self.cz_name, '资产操作', '变更资产', self.alias, '成功')
                if up_host.group == self.group:
                    AuthAutoUpdate.host_grp_count(self.group)
                else:
                    AuthAutoUpdate.host_grp_count(up_host.group)
                    AuthAutoUpdate.host_grp_count(self.group)
                return jsonify({'code': 0})
            except Exception:
                self.host_log(self.cz_name, '资产操作', '变更资产', self.alias, '失败', '连接数据库错误')
                return jsonify({'code': 100, 'msg': '服务器内部错误'})
        except Exception:
            self.host_log(self.cz_name, '资产操作', '变更资产', self.alias, '失败', '未知错误')
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})


class ServerCmd(CzToolsLog):
    # REV37-H1: 继承 CzToolsLog 获取 host_log 能力, 记录单条命令审计
    def __init__(self):
        CzToolsLog.__init__(self)
        # self.host_ip = request_param('host_ip')
        self.host_id = request_param('host_id')
        self.command = request_param('command')
        # REV25-H2: 补 sys_user 参数 (原 ServerCmd 未传, 导致 host_dict['host_password'] KeyError)
        self.sys_user = request_param('sys_user', default=None)
        # REV37-H1: 取当前操作者上下文 (ip + ua), 用于审计 log_details
        from app.tools.at import _session
        self.ords, self.cz_name = _session()
        try:
            self.remote_ip = request.remote_addr or ''
            # 如有反代, 优先取 X-Forwarded-For 首个 IP (REV37-H1 补充)
            xff = request.headers.get('X-Forwarded-For', '')
            if xff:
                self.remote_ip = xff.split(',')[0].strip() or self.remote_ip
            self.user_agent = (request.headers.get('User-Agent') or '')[:200]
        except Exception:
            self.remote_ip = ''
            self.user_agent = ''

    def _check_command_safe(self):
        """REVIEW-11-P1-1: SSH 危险命令前置拦截。返回 (ok, response)。"""
        danger = _check_dangerous_command(self.command)
        if danger:
            return False, jsonify({
                'code': 100,
                'msg': 'dangerous command blocked: %s' % danger,
            })
        return True, None

    @property
    def sh_cmd(self):
        # P1-1: 危险命令拦截
        ok, err = self._check_command_safe()
        if not ok:
            # REV37-H1: 拦截时也记录审计, 让 dangerous 尝试可追踪
            self.host_log(
                self.cz_name or '', '主机操作',
                'ssh_cmd@%s' % (self.host_id or ''),
                'cmd=%s; ip=%s; ua=%s' % ((self.command or '')[:200], self.remote_ip, self.user_agent),
                '失败', 'dangerous command blocked',
            )
            return err
        try:
            host = t_host.query.filter_by(id=self.host_id).first()
            if not host:
                # REV37-H1: 找不到主机也记录
                self.host_log(
                    self.cz_name or '', '主机操作',
                    'ssh_cmd@%s' % (self.host_id or ''),
                    'cmd=%s; ip=%s; ua=%s' % ((self.command or '')[:200], self.remote_ip, self.user_agent),
                    '失败', 'host not found',
                )
                return jsonify({'code': 100, 'msg': '未找到目标资源'})
            # REV25-H2: 改用 get_ssh_connection, 通过 sys_user 关联 t_sys_user 获取凭据
            # 原 host_dict['host_password'] 访问 t_host 不存在的字段会 KeyError
            # t_host 表只有 id/alias/host_ip/host_port/group, 凭据在 t_sys_user 表
            # REV46-M20: ssh_cmd 不再自动 close, 调用方显式管理连接生命周期
            # REV46-M26: ssh_cmd 接受 audit_callback 写 t_command_log
            conn = get_ssh_connection(self.sys_user, host.host_ip, host.host_port)
            try:
                msg = conn.ssh_cmd(self.command, audit_callback=log_ssh_audit)
            finally:
                conn.close()
            # REV37-H1: 命令执行成功也记录审计 (含 IP + UA, 写入 log_details)
            self.host_log(
                self.cz_name or '', '主机操作',
                'ssh_cmd@%s/%s' % (host.host_ip, host.host_port),
                'cmd=%s; ip=%s; ua=%s' % ((self.command or '')[:200], self.remote_ip, self.user_agent),
                '成功', None,
            )
            return jsonify({'code': 0,
                            'command_msg': msg,
                            'hostname_list': self.host_id})
        except IOError:
            self.host_log(
                self.cz_name or '', '主机操作',
                'ssh_cmd@%s' % (self.host_id or ''),
                'cmd=%s; ip=%s; ua=%s' % ((self.command or '')[:200], self.remote_ip, self.user_agent),
                '失败', 'IOError',
            )
            return jsonify({'code': 100, 'msg': '未找到目标资源'})


class ServerListCmd(ComToolsLog, ServerCmd):
    def __init__(self):
        ComToolsLog.__init__(self)
        ServerCmd.__init__(self)
        self.host_name = request_param_list('host_name')
        self.ords, self.com_name = get_current_user()
        self.com_host = ','.join(self.host_name)

        # 新增选择执行的系统用户
        self.sys_user = request_param('sys_user', default=None)

    @property
    def sh_list_cmd(self):
        # P1-1: 危险命令拦截
        ok, err = self._check_command_safe()
        if not ok:
            return err
        # REV25-M5/L7: 批量操作主机数上限 (防 DoS)
        if len(self.host_name) > _MAX_BATCH_COUNT:
            return jsonify({'code': 100, 'msg': 'too many hosts (max %d)' % _MAX_BATCH_COUNT})
        from app.assets.batch_service import (
            BatchCommandValidationError,
            execute_batch_command,
        )

        hosts = t_host.query.filter(
            t_host.alias.in_(self.host_name),
            t_host.is_deleted.is_(False),
        ).all()
        by_alias = {host.alias: host for host in hosts}
        if any(alias not in by_alias for alias in self.host_name):
            return jsonify({'code': 100, 'msg': '未找到目标资源'})
        try:
            result = execute_batch_command(
                username=self.com_name,
                role=get_current_user_role(),
                host_ids=[by_alias[alias].id for alias in self.host_name],
                sys_user=self.sys_user,
                command=self.command,
                connection_factory=get_ssh_connection,
            )
        except BatchCommandValidationError as exc:
            return jsonify({'code': 100, 'msg': str(exc)})
        success_items = [
            item for item in result['items'] if item['status'] == 'success'
        ]
        msg_list = [item['output'] for item in success_items]
        alias_list = [item['alias'] for item in success_items]
        error_list = [
            item['alias'] for item in result['items']
            if item['status'] != 'success'
        ]
        public_items = [
            {
                'alias': item['alias'],
                'status': item['status'],
                'output': item.get('output', ''),
                'error': item.get('error', ''),
            }
            for item in result['items']
        ]
        has_error = len(error_list) > 0
        if has_error and len(msg_list) == 0:
            # 全部失败
            return jsonify({'code': 100, 'msg': '未找到目标资源',
                            'error_list': error_list,
                            'msg': 'host connect to timeout!',
                            'items': public_items})
        elif has_error:
            # 部分成功：返回成功结果 + 失败列表
            return jsonify({'code': 0,
                            'command_msg': msg_list,
                            'hostname_list': alias_list,
                            'error_list': error_list,
                            'items': public_items})
        else:
            return jsonify({'code': 0,
                            'command_msg': msg_list,
                            'hostname_list': alias_list,
                            'items': public_items})


class GroupCmd:
    # REV28-L3: 接受可选参数, 调用方可传入预先从 request.values 取出的 group/command/sys_user,
    # 支持调用方直接传入 group，避免同一请求参数被重复读取。
    #   默认参数保持与原逻辑一致: 仍从 request.values 取, 以保证独立调用场景不变.
    def __init__(self, group=None, command=None, sys_user=None):
        self.group = group if group is not None else request_param('group')
        self.command = command if command is not None else request_param('command')
        self.sys_user = sys_user if sys_user is not None else request_param('sys_user', default=None)

    def sh_cmd(self, cmd=None):
        if cmd:
            self.command = cmd
        # P1-1: 危险命令拦截
        danger = _check_dangerous_command(self.command)
        if danger:
            return jsonify({
                'code': 100,
                'msg': 'dangerous command blocked: %s' % danger,
            })
        msg_list = []
        error_list = []
        group_in_host_list = []
        group_list = t_host.query.filter_by(group=self.group).all()
        for groups in group_list:
            try:
                conn = get_ssh_connection(self.sys_user, groups.host_ip, groups.host_port)
                try:
                    # REV46-M26: audit_callback 写 t_command_log
                    msg = conn.ssh_cmd(self.command, audit_callback=log_ssh_audit)
                    msg_list.append(msg)
                    group_in_host_list.append(groups.host_ip)
                finally:
                    conn.close()  # REV46-M20
            except (IOError, paramiko.ssh_exception.AuthenticationException):
                error_list.append(groups.host_ip)
        has_error = len(error_list) > 0
        if has_error and len(msg_list) == 0:
            return jsonify({'code': 100, 'msg': '未找到目标资源',
                            'error_list': error_list,
                            'msg': 'host connect to timeout!'})
        elif has_error:
            return jsonify({'code': 0,
                            'command_msg': msg_list,
                            'group_list': self.group,
                            'hostname_list': group_in_host_list,
                            'error_list': error_list})
        else:
            return jsonify({'code': 0,
                            'command_msg': msg_list,
                            'group_list': self.group,
                            'hostname_list': group_in_host_list})


class GroupListCmd(GroupCmd):
    def __init__(self):
        super(GroupListCmd, self).__init__()
        self.group_ls = request_param_list('group_ls')

    @property
    def sh_list_cmd(self):
        # 批量执行组内主机，逐台容错
        gop_list_msg = []
        all_error_list = []
        for group in self.group_ls:
            msg_list = []
            error_list = []
            group_list = t_host.query.filter_by(group=group).all()
            for groups in group_list:
                try:
                    conn = get_ssh_connection(self.sys_user, groups.host_ip, groups.host_port)
                    try:
                        # REV46-M26: audit_callback 写 t_command_log
                        msg = conn.ssh_cmd(self.command, audit_callback=log_ssh_audit)
                        msg_list.append(msg)
                    finally:
                        conn.close()  # REV46-M20
                except (IOError, paramiko.ssh_exception.AuthenticationException):
                    error_list.append(groups.host_ip)
            msg_dict = {group: msg_list}
            gop_list_msg.append(msg_dict)
            all_error_list.extend(error_list)
        has_error = len(all_error_list) > 0
        if has_error and not any(msg_dict[grp] for msg_dict in gop_list_msg for grp in msg_dict):
            return jsonify({'code': 100, 'msg': '未找到目标资源',
                            'error_list': all_error_list,
                            'msg': 'host connect to timeout!'})
        elif has_error:
            return jsonify({'code': 0,
                            'command_msg': gop_list_msg,
                            'error_list': all_error_list})
        else:
            return jsonify({'code': 0,
                            'command_msg': gop_list_msg})


# 脚本上传接口
class ServerScript(ComToolsLog):
    # REV16 B5 HIGH-2: 脚本上传大小限制 (默认 1MB，防大文件拖库 / zip 炸弹)
    _MAX_SCRIPT_SIZE = MAX_SCRIPT_SIZE
    # REV16 B5 HIGH-2: 危险脚本关键字 (rm -rf / fork bomb 等仅限 admin)
    _DANGEROUS_SCRIPT_PATTERNS = DANGEROUS_SCRIPT_PATTERNS

    def __init__(self):
        super(ServerScript, self).__init__()
        self.file = request.files.get('file')
        self.name_list = request_param_list('name_list')
        self.original_filename = self.file.filename if self.file else ''
        self.filename = secure_filename(self.original_filename)
        self.ords, self.com_name = get_current_user()
        self.com_host = ','.join(self.name_list)

        # 新增选择执行的系统用户
        self.sys_user = request_param('sys_user', default=None)

    def sh_script(self):
        put_type = request_param('put_type')
        if self.file is None:
            return jsonify({'code': 100, 'msg': 'script file is required'})
        if put_type not in ('sh', 'send'):
            return jsonify({'code': 100, 'msg': 'unsupported script operation'})
        current_role = get_current_user_role()
        if current_role not in ('admin', 'user'):
            return jsonify({
                'code': 100,
                'msg': 'batch operation permission denied',
            })
        if put_type == 'sh' and current_role != 'admin':
            self.host_log(self.com_name, '批量脚本', self.filename or '',
                          self.com_host, '失败', 'sh 类型脚本需 admin 角色')
            return jsonify({'code': 100, 'msg': '脚本执行仅限 admin 角色'})

        # Read one byte beyond the limit so an incorrect/missing multipart
        # content_length cannot bypass the authoritative 1 MiB check.
        self.file.seek(0)
        script_bytes = self.file.read(self._MAX_SCRIPT_SIZE + 1)
        # The request-independent service performs UTF-8, extension and full
        # content checks and quotes its generated remote path before execution.
        from app.assets.batch_service import (
            BatchCommandValidationError,
            execute_batch_script,
            execute_batch_upload,
        )

        if not self.name_list:
            return jsonify({'code': 100, 'msg': 'target hosts are required'})
        if len(set(self.name_list)) != len(self.name_list):
            return jsonify({
                'code': 100,
                'msg': 'duplicate target hosts are not allowed',
            })
        if len(self.name_list) > _MAX_BATCH_COUNT:
            return jsonify({
                'code': 100,
                'msg': 'too many hosts (max %d)' % _MAX_BATCH_COUNT,
            })
        hosts = t_host.query.filter(
            t_host.alias.in_(self.name_list),
            t_host.is_deleted.is_(False),
        ).all()
        by_alias = {host.alias: host for host in hosts}
        if any(alias not in by_alias for alias in self.name_list):
            return jsonify({'code': 100, 'msg': '未找到目标资源'})
        try:
            common_args = {
                'username': self.com_name,
                'role': current_role,
                'host_ids': [by_alias[alias].id for alias in self.name_list],
                'sys_user': self.sys_user,
                'connection_factory': get_ssh_connection,
            }
            if put_type == 'send':
                result = execute_batch_upload(
                    filename=self.filename or 'upload.bin',
                    file_bytes=script_bytes,
                    **common_args,
                )
            else:
                result = execute_batch_script(
                    filename=self.original_filename,
                    script_bytes=script_bytes,
                    audit_callback=log_ssh_audit,
                    **common_args,
                )
        except DangerousCommandError as exc:
            return jsonify({
                'code': 100,
                'msg': 'dangerous command blocked: %s' % str(exc),
            })
        except BatchCommandValidationError as exc:
            return jsonify({'code': 100, 'msg': str(exc)})

        success_items = [
            item for item in result['items'] if item['status'] == 'success'
        ]
        msg_list = (
            ['上传成功']
            if put_type == 'send' and success_items
            else [item['output'] for item in success_items]
        )
        alias_list = [item['alias'] for item in success_items]
        error_list = [
            item['alias'] for item in result['items']
            if item['status'] != 'success'
        ]
        payload = {
            'code': 0 if success_items else 100,
            'command_msg': msg_list,
            'hostname_list': alias_list,
            'items': result['items'],
        }
        if error_list:
            payload['error_list'] = error_list
        if not success_items:
            payload['msg'] = 'host connect to timeout!'
        return jsonify(payload)
