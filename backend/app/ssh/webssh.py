import paramiko
import json
import traceback
import time

from flask import request
from app.app_factory import app
from app.core.db.database import t_host, t_sys_user, t_auth_host_user, t_auth_host_user_group, t_auth_host_host_group, t_acc_user, t_auth_host
from app.tools.basesec import base64_auto  # noqa: F401
from app.tools.shellcmd import get_ssh_password  # Fernet 解密 + base64 透明迁移
from app.tools.keypath import safe_key_path  # REV47-T1: 修复 REV40 H2 漏修的私钥路径拼接
from app.core.config import FILE_CONF, SSH_HOST_KEY_POLICY
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.server import WSGIServer
from geventwebsocket.websocket import WebSocket
from gevent import sleep, spawn, Timeout
from app.tools.ws_helper import setup_ws_logger, SafeSendMixin

logger = setup_ws_logger(__name__)


# REV16 B3 HIGH-1: host_key 策略工厂
#   原: Transport 未 set_missing_host_key_policy → paramiko 默认 AutoAddPolicy
#   攻击: MITM 中间人首次可伪装主机密钥,后续客户端接受并被跟踪
#   修复: 复用 config.SSH_HOST_KEY_POLICY (prod=reject 默认)
def _make_host_key_policy():
    pol = (SSH_HOST_KEY_POLICY or 'reject').lower()
    if pol == 'warning':
        return paramiko.WarningPolicy()
    if pol == 'auto':
        return paramiko.AutoAddPolicy()
    return paramiko.RejectPolicy()


# REV16 B3 HIGH-2: WebSocket host 权限校验 (参考 t_auth_host_user / t_auth_host_user_group)
#   原: 仅查 t_host / t_sys_user 存在性, 未校验当前用户是否有该主机权限
#   攻击: 低权限用户拿到任意主机 alias 即可连
#   修复: 从 cookie 中取当前用户, 查 host_alias 是否在授权表内
def _current_user_from_cookie():
    """从 WS 握手中的 cookie 里拿当前用户名 (可能为空)。"""
    try:
        token = request.cookies.get('ogs_token')
        if not token:
            return None
        # 避免循环 import; redis 连接从 at._session 复用
        from app.tools.at import _session  # type: ignore
        _, name = _session()
        return name
    except Exception:
        return None


def _check_host_permitted(host_alias, current_user):
    """B3 HIGH-2: 检查 current_user 是否被授权访问 host_alias。
    数据模型路径:
      t_host (alias/group)  →  t_auth_host_host_group (auth_id / group_name)
      t_auth_host_user (user_name / auth_id)  →  t_auth_host (id / name)
    规则:
      1. admin 角色 → 总是通过
      2. 当前用户在 t_auth_host_user 中关联的 auth_id, 且该 auth_id 通过 t_auth_host_host_group 覆盖该主机所在组 → 通过
      3. 当前用户所在用户组在 t_auth_host_user_group 中关联的 auth_id, 且该 auth_id 覆盖该主机所在组 → 通过
      4. 其他情况 → 拒绝
    """
    if not current_user:
        return False
    user_info = t_acc_user.query.filter_by(name=current_user).first()
    user_role = getattr(user_info, 'usrole', None) if user_info else None
    if user_role == 'admin':
        return True
    host_row = t_host.query.filter_by(alias=host_alias, is_deleted=False).first()
    if not host_row:
        return False
    host_group = getattr(host_row, 'group', None)
    # 收集该主机所在组的 auth_id 列表 (host_group 可能为空, 则退到只按 host 检查)
    auth_ids_for_host = set()
    if host_group:
        rows = t_auth_host_host_group.query.filter_by(group_name=host_group).all()
        auth_ids_for_host.update(r.auth_id for r in rows)
    # 直接授权: 用户的 auth_id 覆盖该主机组
    direct_rows = t_auth_host_user.query.filter_by(user_name=current_user).all()
    user_auth_ids = set(r.auth_id for r in direct_rows)
    if user_auth_ids & auth_ids_for_host:
        return True
    # 用户组授权: 当前用户所在用户组的 auth_id 覆盖该主机组
    if user_info and user_info.group:
        grp_rows = t_auth_host_user_group.query.filter_by(group_name=user_info.group).all()
        grp_auth_ids = set(r.auth_id for r in grp_rows)
        if grp_auth_ids & auth_ids_for_host:
            return True
    return False

# 默认终端尺寸
DEFAULT_TERM_WIDTH = 80
DEFAULT_TERM_HEIGHT = 24
DEFAULT_TERM_TYPE = 'xterm'

# REVIEW-5-F-1: resize_pty cols/rows 边界，防前端传 999999 触发服务端 OOM
MIN_TERM_WIDTH, MAX_TERM_WIDTH = 20, 500
MIN_TERM_HEIGHT, MAX_TERM_HEIGHT = 5, 200

# REVIEW-5-F-2: webssh/sftp idle timeout (秒), 防止用户关闭浏览器后 SSH/SFTP channel 永久残留
WEBSH_IDLE_TIMEOUT = 1800   # 30 分钟
SFTP_IDLE_TIMEOUT = 1800    # 30 分钟


class SshBridge:
    """SSH与WebSocket之间的桥接器，实现双向数据转发"""

    def __init__(self, websocket):
        self.ws = websocket  # type: WebSocket
        self.channel = None
        self.trans = None
        self.ssh_greenlet = None
        self._closed = False  # 防止重复关闭
        # REVIEW-5-F-2: 记录最近一次从 WS 收到数据的时间戳，配合 _ssh_to_ws 检测空闲
        self._last_recv_ts = time.time()

    def _create_ssh_conn(self, host, port, user, password=None, pkey=None):
        """建立SSH连接，打开交互式shell"""
        logger.info('Connecting SSH %s:%s as %s (pkey=%s)', host, port, user, bool(pkey))
        # paramiko 3.x: 使用 SSHClient 统一处理 host key 策略
        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.set_missing_host_key_policy(_make_host_key_policy())
        connect_kwargs = {
            'hostname': host,
            'port': int(port),
            'username': user,
            'timeout': 15,
            'allow_agent': False,
            'look_for_keys': False,
        }
        if pkey:
            connect_kwargs['key_filename'] = safe_key_path(pkey)
        else:
            connect_kwargs['password'] = password
        self._ssh_client.connect(**connect_kwargs)
        self.trans = self._ssh_client.get_transport()
        self.channel = self.trans.open_session()
        # 不设timeout，保持长连接
        self.channel.settimeout(0)
        # 获取pty并激活shell
        self.channel.get_pty(term=DEFAULT_TERM_TYPE,
                             width=DEFAULT_TERM_WIDTH,
                             height=DEFAULT_TERM_HEIGHT)
        self.channel.invoke_shell()
        logger.info('SSH connection established: %s:%s', host, port)
        return self.channel

    def _ssh_to_ws(self):
        """从SSH channel读取数据，转发到WebSocket客户端（输出方向）"""
        try:
            while True:
                if self.channel is None or self.channel.closed:
                    logger.info('SSH channel closed, exiting ssh_to_ws')
                    break
                # REVIEW-5-F-2: 在轮询间隙检查空闲超时，超时主动断开
                if time.time() - self._last_recv_ts > WEBSH_IDLE_TIMEOUT:
                    logger.info('WebSocket idle timeout (%ds), closing ssh_to_ws',
                                WEBSH_IDLE_TIMEOUT)
                    break
                # 非阻塞读取：recv_ready()检查是否有数据可读
                if self.channel.recv_ready():
                    try:
                        data = self.channel.recv(4096)
                        if not data:
                            logger.info('SSH recv empty, remote closed')
                            break
                        self.ws.send(data.decode('utf-8', errors='ignore'))
                    except Exception as e:
                        logger.error('SSH recv error: %s', e)
                        break
                else:
                    # 没有数据时短暂让出协程，避免空转
                    sleep(0.01)
        except Exception as e:
            logger.error('ssh_to_ws error: %s', e)
        finally:
            self._close()

    def _ws_to_ssh(self):
        """从WebSocket客户端读取数据，转发到SSH channel（输入方向）"""
        try:
            while True:
                # REVIEW-5-F-2: 用 gevent.Timeout 包装 receive，超时视为 idle 主动断开
                try:
                    with Timeout(WEBSH_IDLE_TIMEOUT):
                        msg = self.ws.receive()
                except Timeout:
                    logger.info('WebSocket idle timeout (%ds) in ws_to_ssh',
                                WEBSH_IDLE_TIMEOUT)
                    break
                # 客户端主动断开时receive返回None
                if msg is None:
                    logger.info('WebSocket receive None, client disconnected')
                    break
                # REVIEW-5-F-2: 收到任何数据都刷新时间戳
                self._last_recv_ts = time.time()
                # 支持JSON控制消息（如终端resize）
                if msg.startswith('{'):
                    try:
                        ctrl_msg = json.loads(msg)
                        msg_type = ctrl_msg.get('type')
                        if msg_type == 'resize':
                            # 终端尺寸变更
                            # REVIEW-5-F-1: cols/rows 边界裁剪，防前端传巨型值触发服务端 OOM
                            try:
                                raw_cols = int(ctrl_msg.get('cols', DEFAULT_TERM_WIDTH))
                                raw_rows = int(ctrl_msg.get('rows', DEFAULT_TERM_HEIGHT))
                            except (TypeError, ValueError):
                                raw_cols, raw_rows = DEFAULT_TERM_WIDTH, DEFAULT_TERM_HEIGHT
                            cols = max(MIN_TERM_WIDTH, min(raw_cols, MAX_TERM_WIDTH))
                            rows = max(MIN_TERM_HEIGHT, min(raw_rows, MAX_TERM_HEIGHT))
                            if self.channel:
                                self.channel.resize_pty(width=cols, height=rows)
                            continue
                    except (json.JSONDecodeError, ValueError):
                        pass  # 非JSON控制消息，当作普通输入处理
                # 普通输入，直接发送到SSH channel
                if self.channel and not self.channel.closed:
                    self.channel.send(msg)
        except Exception as e:
            logger.error('ws_to_ssh error: %s', e)
        finally:
            self._close()

    def start(self, host, port, user, password=None, pkey=None):
        """启动SSH连接和双向转发"""
        self._create_ssh_conn(host, port, user, password, pkey)
        # 启动SSH→WS方向的greenlet（并发读取）
        self.ssh_greenlet = spawn(self._ssh_to_ws)
        # 当前greenlet处理WS→SSH方向（阻塞读取WebSocket）
        self._ws_to_ssh()
        # 等待SSH读取协程结束
        if self.ssh_greenlet:
            self.ssh_greenlet.join(timeout=5)

    def _close(self):
        """清理SSH连接资源（防重复调用）"""
        if self._closed:
            return
        self._closed = True
        logger.info('SshBridge._close() cleaning up')
        try:
            if self.channel and not self.channel.closed:
                self.channel.close()
        except Exception:
            pass
        try:
            if self.trans and self.trans.is_active():
                self.trans.close()
        except Exception:
            pass
        try:
            if not self.ws.closed:
                # 发送标准关闭帧（code=1000, reason=normal），
                # 避免 geventwebsocket 直接断 TCP 导致浏览器收到 1005
                self.ws.close(1000, 'normal closure')
        except Exception as e:
            logger.warning('ws.close() error: %s', e)


# @app.route('/websocket')
class OgsWebSocket(SafeSendMixin):
    def __init__(self):
        self.client_socket = request.environ.get('wsgi.websocket')  # type: WebSocket

    def web_ssh(self):
        if not self.client_socket:
            logger.warning('WebSocket handshake failed: wsgi.websocket not found in environ. '
                           'Make sure the proxy (Vite/Nginx) forwards Upgrade header correctly.')
            return '', 400

        logger.info('WebSocket connected, waiting for credentials...')

        # 第一次接收数据：建立SSH连接
        msg_one_cli = self.client_socket.receive()
        if msg_one_cli is None:
            logger.warning('WebSocket client disconnected before sending credentials')
            return ''

        logger.info('Received first message: %s', msg_one_cli[:200])

        try:
            front_msg = json.loads(msg_one_cli)
        except (json.JSONDecodeError, TypeError):
            logger.warning('Invalid JSON from client: %s', msg_one_cli[:100])
            self._safe_send_and_close('Invalid connection data', 1002, 'invalid data')
            return ''

        hostname = front_msg.get('hostname')
        username = front_msg.get('username')
        logger.info('Connecting: hostname=%s, username=%s', hostname, username)

        query_host_msg = t_host.query.filter_by(
            alias=hostname, is_deleted=False
        ).first()
        sys_user_info = t_sys_user.query.filter_by(
            alias=username, is_deleted=False
        ).first()

        if not query_host_msg or not sys_user_info:
            logger.warning('Host or user not found: hostname=%s (found=%s), username=%s (found=%s)',
                           hostname, bool(query_host_msg), username, bool(sys_user_info))
            self._safe_send_and_close('Host or user not found', 1002, 'not found')
            return ''

        # REV16 B3 HIGH-2: host 权限校验 (防低权限用户连未授权主机)
        current_user = _current_user_from_cookie()
        if not _check_host_permitted(hostname, current_user):
            logger.warning('Host permission denied: user=%s try to access host=%s',
                           current_user, hostname)
            self._safe_send_and_close('Permission denied for host %s' % hostname, 1003, 'forbidden')
            return ''

        logger.info('Found host=%s:%s, sys_user=%s (key=%s)',
                    query_host_msg.host_ip, query_host_msg.host_port,
                    sys_user_info.host_user, bool(sys_user_info.host_key))

        try:
            # 优先用key连接，否则用密码
            bridge = SshBridge(self.client_socket)
            if sys_user_info.host_key:
                bridge.start(
                    host=query_host_msg.host_ip,
                    port=query_host_msg.host_port,
                    user=sys_user_info.host_user,
                    pkey=sys_user_info.host_key
                )
            else:
                # 使用 get_ssh_password 解密密码（支持 base64→Fernet 透明迁移）
                ssh_pwd = get_ssh_password(sys_user_info)
                if not ssh_pwd:
                    logger.warning('No credentials configured for sys_user: %s', sys_user_info.alias)
                    self._safe_send_and_close(
                        '系统用户 "%s" 未配置密码或密钥，请先在系统用户管理中设置凭据' % sys_user_info.alias,
                        1002, 'no credentials')
                    return ''
                bridge.start(
                    host=query_host_msg.host_ip,
                    port=query_host_msg.host_port,
                    user=sys_user_info.host_user,
                    password=ssh_pwd
                )
        except paramiko.ssh_exception.AuthenticationException:
            logger.warning('SSH auth failed: %s@%s', sys_user_info.host_user, query_host_msg.host_ip)
            self._safe_send_and_close('Authentication failed, please check username/password', 1002, 'auth failed')
            return ''
        except paramiko.ssh_exception.SSHException as e:
            logger.warning('SSH connection failed: %s:%s - %s', query_host_msg.host_ip, query_host_msg.host_port, e)
            self._safe_send_and_close(
                'Unable to connect to {}: {}'.format(query_host_msg.host_ip, str(e)), 1002, 'ssh error')
            return ''
        except Exception as e:
            logger.error('web_ssh unexpected error: %s\n%s', e, traceback.format_exc())
            self._safe_send_and_close('Connection error: {}'.format(str(e)), 1011, 'internal error')
            return ''

        logger.info('WebSocket session ended normally')
        return ''
