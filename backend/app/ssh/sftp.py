import paramiko
import json
import stat
import os
import time

from flask import request
from app.app_factory import app
from app.core.db.database import t_host, t_sys_user, t_auth_host_user, t_auth_host_user_group, t_auth_host_host_group, t_acc_user
from app.tools.basesec import base64_auto  # noqa: F401  # 保留旧 base64 工具供外部模块使用
from app.tools.shellcmd import get_ssh_password  # Fernet 解密 + 透明迁移
from app.tools.keypath import safe_key_path  # REV47-T1: 跨模块 keypath 统一
from app.tools.pathsec import safe_join, safe_remote_path  # REV47-T2: 跨模块 pathsec 统一
from app.tools.audlog import CzToolsLog  # REV47-R2-M1: SFTP 文件操作审计
from app.core.config import FILE_CONF, SFTP_MAX_UPLOAD_SIZE, SSH_HOST_KEY_POLICY
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.server import WSGIServer
from geventwebsocket.websocket import WebSocket
from gevent import sleep, Timeout
from app.tools.ws_helper import setup_ws_logger, SafeSendMixin

logger = setup_ws_logger(__name__)


# REV47-R2-M1: SFTP 文件操作审计 helper
#   业务: 6 个 _handle_* 写操作 (mkdir/rm/rename/download/upload) 全部记录到 t_cz_log
#   字段: log_name=操作人, log_type='SFTP文件操作', log_info=具体动作, log_details=路径/参数, log_status=成功/失败
#   失败兜底: 审计写库异常走 audsec.safe_db_write, 不阻断 SFTP 主流程 (与 REV44-H4 一致)
def _audit_sftp_file_op(user_name, host_alias, action, path_or_details, status='成功', error_msg=None):
    """REV47-R2-M1: 写一条 SFTP 文件操作审计到 t_cz_log.

    Args:
        user_name: 操作用户名 (从 cookie session 来, 可能 None)
        host_alias: SFTP 目标主机 alias (用于溯源)
        action: 'mkdir' / 'rm' / 'rename' / 'download' / 'upload' 等
        path_or_details: 文件路径 或 "old -> new" 形式细节
        status: '成功' / '失败'
        error_msg: 失败原因 (None 表示成功)
    """
    try:
        log_name = user_name or 'anonymous'
        # log_info 限 255 字符, 留余量给 host_alias + path
        info = f'SFTP {action}@{host_alias}'
        details = f'{action} {path_or_details}'[:255]
        CzToolsLog().host_log(
            log_name=log_name[:30],  # log_name 限 30 字符
            log_type='SFTP文件操作',
            log_info=info[:255],
            log_details=details,
            log_status=status[:32],
            log_msg=(error_msg or '')[:255] if error_msg else None,
        )
    except Exception as e:
        # 审计本身失败不能阻断 SFTP, 静默 fallback 到 logger.error
        logger.error('SFTP audit write failed: %s', e)


# REV16 B3 HIGH-1: host_key 策略工厂 (sftp 复用 webssh 的实现逻辑)
def _make_host_key_policy():
    pol = (SSH_HOST_KEY_POLICY or 'reject').lower()
    if pol == 'warning':
        return paramiko.WarningPolicy()
    if pol == 'auto':
        return paramiko.AutoAddPolicy()
    return paramiko.RejectPolicy()


def _current_user_from_cookie():
    try:
        token = request.cookies.get('ogs_token')
        if not token:
            return None
        from app.tools.at import _session  # type: ignore
        _, name = _session()
        return name
    except Exception:
        return None


def _check_host_permitted(host_alias, current_user):
    """B3 HIGH-2: sftp 复用 webssh 的 host 权限逻辑."""
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
    auth_ids_for_host = set()
    if host_group:
        rows = t_auth_host_host_group.query.filter_by(group_name=host_group).all()
        auth_ids_for_host.update(r.auth_id for r in rows)
    direct_rows = t_auth_host_user.query.filter_by(user_name=current_user).all()
    user_auth_ids = set(r.auth_id for r in direct_rows)
    if user_auth_ids & auth_ids_for_host:
        return True
    if user_info and user_info.group:
        grp_rows = t_auth_host_user_group.query.filter_by(group_name=user_info.group).all()
        grp_auth_ids = set(r.auth_id for r in grp_rows)
        if grp_auth_ids & auth_ids_for_host:
            return True
    return False

# 文件传输分块大小
CHUNK_SIZE = 65536  # 64KB

# REVIEW-5-F-2: SFTP idle timeout (秒), 防止用户关闭浏览器后 SFTP channel 永久残留
SFTP_IDLE_TIMEOUT = 1800  # 30 分钟

# REVIEW-5-D-1: sftp 上传目标目录白名单
#   原代码接受前端传的 remote_path，覆盖 SSH authorized_keys、crontab、passwd 等敏感文件
#   修复后: 服务端硬编码到 SFTP_UPLOAD_DIR，filename 走 sanitize 过滤特殊字符
#   文件名 sanitize: 仅保留字母数字/下划线/点/连字符，其他替换为下划线
import re
_SAFE_FILENAME_RE = re.compile(r'[^A-Za-z0-9._-]')
SFTP_UPLOAD_DIR = '/tmp/ogs_uploads/'  # 服务端唯一可信目标目录


def _sanitize_filename(name):
    """只保留安全字符；防御路径穿越 (../) + 不可见字符"""
    if not name:
        return None
    # 取 basename 防传入 "a/b" 形式的伪路径
    base = os.path.basename(name)
    safe = _SAFE_FILENAME_RE.sub('_', base)
    # 防止 sanitize 后全空 (例如 ".." 变 "_")
    if not safe or safe in ('.', '..'):
        return None
    return safe


def _safe_join(base, name):
    """REV47-T2: 委托给 app.tools.pathsec.safe_join 统一实现.

    历史: 旧实现直接内联在 sftp.py, 现已抽到 pathsec.py 跨模块共用.
    保留本函数仅为向后兼容 (外部可能引用), 推荐直接 import safe_join.
    """
    return safe_join(base, name)


_safe_join.__wrapped__ = safe_join  # 保留真实函数引用 (供测试)


# REV40-H1: SFTP mkdir/rm/rename 路径白名单
#   业务: 用户经 WebSocket 控制台发出的 mkdir/rm/rename 命令, 路径必须经过沙箱
#   路径约束: 必须以白名单前缀开头 (防止覆盖 SSH crontab / authorized_keys / passwd 等)
_SFTP_PATH_ALLOWED_PREFIXES = (
    '/tmp/ogs_uploads/',      # SFTP_UPLOAD_DIR
    '/tmp/',
    '/home/',
    '/data/',
    '/opt/',
    '/var/upload/',
)


def _safe_sftp_path(path):
    """REV40-H1 + REV47-T2: 委托给 app.tools.pathsec.safe_remote_path 统一实现.

    历史: 旧实现与 shellcmd._safe_remote_path 几乎完全重复, 已抽到 pathsec.py 跨模块共用.
    保留本函数仅为向后兼容 (外部可能引用), 推荐直接 import safe_remote_path.
    """
    return safe_remote_path(path, _SFTP_PATH_ALLOWED_PREFIXES)


_safe_sftp_path.__wrapped__ = safe_remote_path  # 保留真实函数引用 (供测试)


def _safe_local_key_path(pkey):
    """REV40-H4 + REV47-T1: 委托给 app.tools.keypath.safe_key_path 统一实现.

    历史: 旧实现与 shellcmd._safe_key_path 几乎完全重复, 已抽到 keypath.py 跨模块共用.
    保留本函数仅为向后兼容 (外部可能引用), 推荐直接 import safe_key_path.
    """
    return safe_key_path(pkey)


_safe_local_key_path.__wrapped__ = safe_key_path  # 保留真实函数引用 (供测试)


class SftpBridge:
    """SFTP与WebSocket之间的桥接器，实现远程文件操作"""

    def __init__(self, websocket, host_alias=None, current_user=None):
        self.ws = websocket  # type: WebSocket
        self.transport = None
        self.sftp = None
        self._closed = False
        # REVIEW-5-F-2: 记录最近一次从 WS 收到数据的时间戳，用于 idle timeout 检查
        self._last_recv_ts = time.time()
        # REV47-R2-M1: 审计上下文, 6 个写操作 handler 共享
        self._audit_host = host_alias or 'unknown'
        self._audit_user = current_user  # 可能 None (cookie 无 token)

    def _audit(self, action, details, status='成功', error_msg=None):
        """REV47-R2-M1: 内部审计 shortcut, 6 个 handler 复用.
        REV44-H4 一致: 审计异常不阻断 SFTP 主流程.
        """
        try:
            _audit_sftp_file_op(
                user_name=self._audit_user,
                host_alias=self._audit_host,
                action=action,
                path_or_details=details,
                status=status,
                error_msg=error_msg,
            )
        except Exception as e:
            # 兜底: helper 内部已经有 try/except, 这里再包一层防 mock 替换或 import 失败
            logger.error('SFTP audit shortcut failed: %s', e)

    def _connect(self, host, port, user, password=None, pkey=None):
        """建立SSH连接并打开SFTP会话"""
        logger.info('Connecting SFTP %s:%s as %s (pkey=%s)', host, port, user, bool(pkey))
        # paramiko 3.x/4.x: 使用 SSHClient 统一处理 host key 策略
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
            connect_kwargs['key_filename'] = _safe_local_key_path(pkey)
        else:
            connect_kwargs['password'] = password
        self._ssh_client.connect(**connect_kwargs)
        self.transport = self._ssh_client.get_transport()

        self.sftp = paramiko.SFTPClient.from_transport(self.transport)
        if not self.sftp:
            raise paramiko.SSHException('Failed to open SFTP session')
        logger.info('SFTP session established: %s:%s', host, port)

    def _send_json(self, data):
        """发送JSON消息到WebSocket"""
        try:
            if self.ws and not self.ws.closed:
                self.ws.send(json.dumps(data))
        except Exception as e:
            logger.error('send_json error: %s', e)

    def _send_error(self, action, message):
        """发送错误响应"""
        self._send_json({'action': action, 'status': 'error', 'message': message})

    def _send_success(self, action, **kwargs):
        """发送成功响应"""
        msg = {'action': action, 'status': 'ok'}
        msg.update(kwargs)
        self._send_json(msg)

    def _handle_ls(self, msg):
        """处理列目录请求"""
        path = msg.get('path', '/')
        try:
            entries = []
            for attr in self.sftp.listdir_attr(path):
                entry = {
                    'name': attr.filename,
                    'size': attr.st_size,
                    'isDir': stat.S_ISDIR(attr.st_mode),
                    'mode': stat.S_IMODE(attr.st_mode),
                    'mtime': attr.st_mtime,
                }
                # 拼接完整路径
                if path == '/':
                    entry['path'] = '/' + attr.filename
                else:
                    entry['path'] = path + '/' + attr.filename
                entries.append(entry)
            # 排序：目录在前，再按名称
            entries.sort(key=lambda x: (not x['isDir'], x['name'].lower()))
            self._send_success('ls', path=path, entries=entries)
        except Exception as e:
            logger.error('ls error: %s', e)
            self._send_error('ls', str(e))

    def _handle_stat(self, msg):
        """处理获取文件信息请求"""
        path = msg.get('path', '/')
        try:
            attr = self.sftp.stat(path)
            info = {
                'name': os.path.basename(path),
                'path': path,
                'size': attr.st_size,
                'isDir': stat.S_ISDIR(attr.st_mode),
                'mode': stat.S_IMODE(attr.st_mode),
                'mtime': attr.st_mtime,
            }
            self._send_success('stat', info=info)
        except Exception as e:
            self._send_error('stat', str(e))

    def _handle_download(self, msg):
        """处理文件下载请求（分块流式传输，零落盘）
        REV47-R2-M1: 下载完成时记录审计, 失败也记录.
        """
        path = msg.get('path', '')
        if not path:
            return self._send_error('download', 'No path specified')
        try:
            attr = self.sftp.stat(path)
            if stat.S_ISDIR(attr.st_mode):
                self._safe_audit('download', path, status='失败', error_msg='Cannot download a directory')
                return self._send_error('download', 'Cannot download a directory')

            file_size = attr.st_size
            filename = os.path.basename(path)
            # 先发元数据
            self._send_json({
                'action': 'download_start',
                'status': 'ok',
                'path': path,
                'filename': filename,
                'size': file_size,
            })

            # 分块读取并传输
            with self.sftp.open(path, 'rb') as f:
                transferred = 0
                while transferred < file_size:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    # 以二进制帧发送
                    self.ws.send(chunk)
                    transferred += len(chunk)

            # 发送完成信号
            self._send_success('download_end', path=path, size=transferred)
            self._safe_audit('download', f'{path} ({transferred} bytes)', status='成功')
            logger.info('Download complete: %s (%d bytes)', path, transferred)

        except Exception as e:
            self._safe_audit('download', path, status='失败', error_msg=str(e))
            logger.error('download error: %s', e)
            self._send_error('download', str(e))

    def _handle_upload_start(self, msg):
        """处理上传开始请求，准备接收文件数据
        REVIEW-5-D-1: 拒绝前端传 remote_path，服务端硬编码到 SFTP_UPLOAD_DIR
        REVIEW-5-E-2: 上传 size 超过 SFTP_MAX_UPLOAD_SIZE 立即拒绝，防磁盘填充
        """
        self._upload_path = msg.get('path', '')
        self._upload_filename = msg.get('filename', '')

        # REVIEW-5-D-1: 服务端硬编码目标目录 + 文件名 sanitize
        #   忽略前端传的 remote_path，防覆盖系统文件
        safe_name = _sanitize_filename(self._upload_filename)
        if not safe_name:
            return self._send_error('upload', 'invalid filename')
        self._upload_remote_path = os.path.join(SFTP_UPLOAD_DIR, safe_name)

        if not self._upload_path or not self._upload_filename:
            return self._send_error('upload', 'Missing path or filename')

        # REVIEW-5-E-2: 上传大小前置检查（防止前端宣称 size=10GB 实际发到一半）
        self._upload_size = msg.get('size', 0)
        try:
            declared = int(self._upload_size)
        except (TypeError, ValueError):
            return self._send_error('upload', 'invalid size')
        if declared < 0:
            return self._send_error('upload', 'size must be non-negative')
        if declared > SFTP_MAX_UPLOAD_SIZE:
            return self._send_error('upload',
                f'upload size {declared} exceeds limit {SFTP_MAX_UPLOAD_SIZE}')

        try:
            # 确保远程目录存在
            remote_dir = os.path.dirname(self._upload_remote_path)
            try:
                self.sftp.stat(remote_dir)
            except IOError:
                # 目录不存在，尝试创建
                self._mkdir_p(remote_dir)

            # 打开远程文件用于写入
            self._upload_file = self.sftp.open(self._upload_remote_path, 'wb')
            self._upload_transferred = 0

            self._send_success('upload_start', path=self._upload_remote_path)
            logger.info('Upload started: %s -> %s', self._upload_filename, self._upload_remote_path)

        except Exception as e:
            logger.error('upload_start error: %s', e)
            self._send_error('upload', str(e))

    def _handle_upload_chunk(self, data):
        """处理上传数据块（二进制帧）
        REVIEW-5-E-2: 实时累计检查，防前端谎报 size 偷偷传超出大小限制的文件
        """
        if not hasattr(self, '_upload_file') or self._upload_file is None:
            return
        try:
            # 前置检查: 累计传输量加上本块不能超出限制
            incoming = len(data) if data else 0
            if self._upload_transferred + incoming > SFTP_MAX_UPLOAD_SIZE:
                logger.warning('upload_chunk: cumulative size %d + %d > limit %d, aborting',
                               self._upload_transferred, incoming, SFTP_MAX_UPLOAD_SIZE)
                self._finish_upload()
                return self._send_error('upload',
                    f'transfer exceeds limit {SFTP_MAX_UPLOAD_SIZE}')

            self._upload_file.write(data)
            self._upload_transferred += incoming
            # 每 1MB 报告一次进度
            if self._upload_transferred % (1024 * 1024) < CHUNK_SIZE:
                self._send_json({
                    'action': 'upload_progress',
                    'transferred': self._upload_transferred,
                    'total': self._upload_size,
                })
        except Exception as e:
            logger.error('upload_chunk error: %s', e)
            self._send_error('upload', str(e))
            self._finish_upload()

    def _handle_upload_end(self, msg):
        """处理上传结束请求"""
        self._finish_upload()

    def _finish_upload(self):
        """完成上传，关闭远程文件
        REV47-R2-M1: 上传完成时记录审计 (成功/失败).
        """
        if hasattr(self, '_upload_file') and self._upload_file:
            remote_path = getattr(self, '_upload_remote_path', '?')
            transferred = getattr(self, '_upload_transferred', 0)
            try:
                self._upload_file.close()
                logger.info('Upload complete: %s (%d bytes)',
                            remote_path, transferred)
                self._send_success('upload_end',
                                   path=remote_path,
                                   size=transferred)
                self._safe_audit('upload', f'{remote_path} ({transferred} bytes)', status='成功')
            except Exception as e:
                logger.error('finish_upload error: %s', e)
                self._send_error('upload', str(e))
                self._safe_audit('upload', remote_path, status='失败', error_msg=str(e))
            finally:
                self._upload_file = None

    def _handle_mkdir(self, msg):
        """处理创建目录请求. REV40-H1: path 必须经 _safe_sftp_path 沙箱校验.
        REV47-R2-M1: 写操作审计, 成功/失败都记录.
        REV44-H4 一致: 审计异常不阻断 SFTP.
        """
        path = msg.get('path', '')
        try:
            safe_path = _safe_sftp_path(path)
            self.sftp.mkdir(safe_path)
            self._safe_audit('mkdir', safe_path, status='成功')
            self._send_success('mkdir', path=safe_path)
        except ValueError as e:
            self._safe_audit('mkdir', path, status='失败', error_msg=str(e))
            self._send_error('mkdir', str(e))
        except Exception as e:
            self._safe_audit('mkdir', path, status='失败', error_msg=str(e))
            self._send_error('mkdir', str(e))

    def _handle_rm(self, msg):
        """处理删除请求. REV40-H1: path 必须经 _safe_sftp_path 沙箱校验.
        REV47-R2-M1: 写操作审计.
        """
        path = msg.get('path', '')
        is_dir = msg.get('isDir', False)
        try:
            safe_path = _safe_sftp_path(path)
            if is_dir:
                self.sftp.rmdir(safe_path)
            else:
                self.sftp.remove(safe_path)
            kind = 'rmdir' if is_dir else 'rm'
            self._safe_audit(kind, safe_path, status='成功')
            self._send_success('rm', path=safe_path)
        except ValueError as e:
            self._safe_audit('rm', path, status='失败', error_msg=str(e))
            self._send_error('rm', str(e))
        except Exception as e:
            self._safe_audit('rm', path, status='失败', error_msg=str(e))
            self._send_error('rm', str(e))

    def _handle_rename(self, msg):
        """处理重命名请求. REV40-H1: old_path / new_path 都必须经 _safe_sftp_path 沙箱校验.
        REV47-R2-M1: 写操作审计.
        """
        old_path = msg.get('old_path', '')
        new_path = msg.get('new_path', '')
        try:
            safe_old = _safe_sftp_path(old_path)
            safe_new = _safe_sftp_path(new_path)
            self.sftp.rename(safe_old, safe_new)
            self._safe_audit('rename', f'{safe_old} -> {safe_new}', status='成功')
            self._send_success('rename', old_path=safe_old, new_path=safe_new)
        except ValueError as e:
            self._safe_audit('rename', f'{old_path} -> {new_path}', status='失败', error_msg=str(e))
            self._send_error('rename', str(e))
        except Exception as e:
            self._safe_audit('rename', f'{old_path} -> {new_path}', status='失败', error_msg=str(e))
            self._send_error('rename', str(e))

    def _safe_audit(self, action, details, status='成功', error_msg=None):
        """REV47-R2-M1: handler 内部包了 try/except 的 audit, 永不抛错."""
        try:
            self._audit(action, details, status=status, error_msg=error_msg)
        except Exception as e:
            logger.error('SFTP _safe_audit failed: %s', e)

    def _mkdir_p(self, remote_path):
        """递归创建远程目录（类似 mkdir -p）"""
        dirs = remote_path.split('/')
        current = ''
        for d in dirs:
            if not d:
                current = '/'
                continue
            current = current + d + '/' if current.endswith('/') else current + '/' + d
            try:
                self.sftp.stat(current)
            except IOError:
                self.sftp.mkdir(current)

    def run(self):
        """主循环：接收并处理WebSocket消息
        REVIEW-5-F-2: 用 gevent.Timeout 包装 receive()，超时 (SFTP_IDLE_TIMEOUT) 视为 idle 主动断开
        """
        try:
            while True:
                # REVIEW-5-F-2: idle timeout 包裹，receive 超时即跳出
                try:
                    with Timeout(SFTP_IDLE_TIMEOUT):
                        msg = self.ws.receive()
                except Timeout:
                    logger.info('SFTP WebSocket idle timeout (%ds), closing',
                                SFTP_IDLE_TIMEOUT)
                    break
                if msg is None:
                    logger.info('WebSocket closed by client')
                    break
                # REVIEW-5-F-2: 收到任何数据 (文本帧或二进制帧) 都刷新时间戳
                self._last_recv_ts = time.time()

                # 二进制帧 = 上传数据块
                if isinstance(msg, bytes):
                    self._handle_upload_chunk(msg)
                    continue

                # 文本帧 = JSON 控制指令
                try:
                    data = json.loads(msg)
                except (json.JSONDecodeError, TypeError):
                    self._send_error('unknown', 'Invalid JSON')
                    continue

                action = data.get('action', '')
                if action == 'ls':
                    self._handle_ls(data)
                elif action == 'stat':
                    self._handle_stat(data)
                elif action == 'download':
                    self._handle_download(data)
                elif action == 'upload_start':
                    self._handle_upload_start(data)
                elif action == 'upload_end':
                    self._handle_upload_end(data)
                elif action == 'mkdir':
                    self._handle_mkdir(data)
                elif action == 'rm':
                    self._handle_rm(data)
                elif action == 'rename':
                    self._handle_rename(data)
                else:
                    self._send_error('unknown', 'Unknown action: ' + action)

        except Exception as e:
            logger.error('SftpBridge.run error: %s', e)
        finally:
            self._close()

    def _close(self):
        """清理SFTP连接资源"""
        if self._closed:
            return
        self._closed = True
        logger.info('SftpBridge._close() cleaning up')
        try:
            if hasattr(self, '_upload_file') and self._upload_file:
                self._upload_file.close()
        except Exception:
            pass
        try:
            if self.sftp:
                self.sftp.close()
        except Exception:
            pass
        try:
            if self.transport and self.transport.is_active():
                self.transport.close()
        except Exception:
            pass
        try:
            if self.ws and not self.ws.closed:
                self.ws.close(1000, 'normal closure')
        except Exception as e:
            logger.warning('ws.close() error: %s', e)


class OgsSftpWebSocket(SafeSendMixin):
    """SFTP WebSocket 入口，复用 webssh 的认证逻辑"""

    def __init__(self):
        self.client_socket = request.environ.get('wsgi.websocket')

    def sftp_connect(self):
        if not self.client_socket:
            logger.warning('SFTP: wsgi.websocket not found in environ')
            return '', 400

        logger.info('SFTP WebSocket connected, waiting for credentials...')

        # 接收认证信息
        msg_one = self.client_socket.receive()
        if msg_one is None:
            logger.warning('SFTP: client disconnected before sending credentials')
            return ''

        try:
            front_msg = json.loads(msg_one)
        except (json.JSONDecodeError, TypeError):
            self._safe_send_and_close(json.dumps({'action': 'auth', 'status': 'error', 'message': 'Invalid JSON'}))
            return ''

        hostname = front_msg.get('hostname')
        username = front_msg.get('username')
        logger.info('SFTP auth: hostname=%s, username=%s', hostname, username)

        # 查数据库
        query_host = t_host.query.filter_by(
            alias=hostname, is_deleted=False
        ).first()
        sys_user = t_sys_user.query.filter_by(
            alias=username, is_deleted=False
        ).first()

        if not query_host or not sys_user:
            self._safe_send_and_close(json.dumps({'action': 'auth', 'status': 'error', 'message': 'Host or user not found'}))
            return ''

        # REV16 B3 HIGH-2: host 权限校验
        current_user = _current_user_from_cookie()
        if not _check_host_permitted(hostname, current_user):
            logger.warning('SFTP host permission denied: user=%s try to access host=%s',
                           current_user, hostname)
            self._safe_send_and_close(json.dumps({'action': 'auth', 'status': 'error', 'message': 'Permission denied for host %s' % hostname}))
            return ''

        try:
            # REV47-R2-M1: 传 host_alias + current_user 给 SftpBridge 用于审计
            bridge = SftpBridge(
                self.client_socket,
                host_alias=hostname,
                current_user=current_user,
            )
            if sys_user.host_key:
                bridge._connect(
                    host=query_host.host_ip,
                    port=query_host.host_port,
                    user=sys_user.host_user,
                    pkey=sys_user.host_key
                )
            else:
                # 使用 get_ssh_password 解密密码（支持 base64→Fernet 透明迁移）
                ssh_pwd = get_ssh_password(sys_user)
                if not ssh_pwd:
                    self._safe_send_and_close(json.dumps({
                        'action': 'auth', 'status': 'error',
                        'message': '系统用户 "%s" 未配置密码或密钥' % sys_user.alias
                    }))
                    return ''
                bridge._connect(
                    host=query_host.host_ip,
                    port=query_host.host_port,
                    user=sys_user.host_user,
                    password=ssh_pwd
                )

            # 认证成功
            bridge._send_json({'action': 'auth', 'status': 'ok', 'hostname': hostname})

            # 进入主循环
            bridge.run()

        except paramiko.ssh_exception.AuthenticationException:
            self._safe_send_and_close(json.dumps({'action': 'auth', 'status': 'error', 'message': 'Authentication failed'}))
        except paramiko.ssh_exception.SSHException as e:
            self._safe_send_and_close(json.dumps({'action': 'auth', 'status': 'error', 'message': str(e)}))
        except Exception as e:
            logger.error('sftp_connect error: %s', e)
            self._safe_send_and_close(json.dumps({'action': 'auth', 'status': 'error', 'message': str(e)}))

        return ''
