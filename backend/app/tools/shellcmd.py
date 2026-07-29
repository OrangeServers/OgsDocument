import os.path
import re
import select  # REV46-M22: ssh_cmd select 轮询超时
import socket  # REV46-M22: 捕获 socket.timeout
import paramiko
from app.core.config import (
    FILE_CONF,
    SSH_HOST_KEY_POLICY,
    SSH_CONNECT_TIMEOUT,
    SSH_KEEPALIVE_INTERVAL,
    SSH_CMD_MAX_OUTPUT_BYTES,
    SSH_CMD_TIMEOUT,  # REV46-M22
    SSH_DANGEROUS_COMMANDS,
)
from app.core.db.database import t_sys_user, db
from app.tools.basesec import base64_auto, decrypt_host_password
from app.tools.keypath import safe_key_path  # REV47-T1: 跨模块 keypath 统一
from app.tools.pathsec import safe_remote_path  # REV47-T2: 跨模块 pathsec 统一
from app.tools.audsec import safe_db_write  # REV47-T3: 跨模块降级写库统一


# REV46-H19 (R2-1): 危险命令 regex 编译缓存
#   旧实现: `if d in cmd_stripped` 子串匹配 → "rm -rf /home/xxx" 误拦截
#   新实现: 词边界 (前后是 \s ; & | 或字符串起止) 才算匹配
_DANGEROUS_REGEX_CACHE = None


def _get_dangerous_regex():
    """R2-1: 编译危险命令 regex 列表, 边界字符 = 空白 ; & | / = 字符串起止"""
    global _DANGEROUS_REGEX_CACHE
    if _DANGEROUS_REGEX_CACHE is not None:
        return _DANGEROUS_REGEX_CACHE
    compiled = []
    for d in SSH_DANGEROUS_COMMANDS or []:
        d = (d or '').strip()
        if not d:
            continue
        # 边界: 字符串起止 OR 空白 OR ; & | / =
        # 例如: "rm -rf /" 不匹配 "rm -rf /home/xxx" (因 / 紧跟 home, 非边界)
        # 又如: "dd if=" 匹配 "dd if=/dev/zero" (= / 都是边界)
        pattern = re.compile(
            r'(?:^|[\s;&|/=])' + re.escape(d) + r'(?:$|[\s;&|/=])'
        )
        compiled.append((pattern, d))
    _DANGEROUS_REGEX_CACHE = compiled
    return compiled


# REV46-H16: 远程 SFTP 路径白名单 (put_file / put_fileobj 的 to_path 必须在此前缀下)
_REMOTE_PATH_ALLOWED_PREFIXES = (
    '/home/',
    '/tmp/',
    '/var/upload/',
    '/opt/',
    '/data/',
)


def _safe_remote_path(to_path):
    """REV46-H16 + REV47-T2: 委托给 app.tools.pathsec.safe_remote_path 统一实现.

    历史: 旧实现直接内联在 shellcmd.py, 现已抽到 pathsec.py 跨模块共用.
    保留本函数仅为向后兼容 (外部可能引用), 推荐直接 import safe_remote_path.
    """
    return safe_remote_path(to_path, _REMOTE_PATH_ALLOWED_PREFIXES)


_safe_remote_path.__wrapped__ = safe_remote_path  # 保留真实函数引用 (供测试)


def _safe_key_path(pkey):
    """REV46-H17 + REV47-T1: 委托给 app.tools.keypath.safe_key_path 统一实现.

    历史: 旧实现直接内联在 shellcmd.py, 现已抽到 keypath.py 跨模块共用.
    保留本函数仅为向后兼容 (外部可能引用), 推荐直接 import safe_key_path.
    """
    return safe_key_path(pkey)


_safe_key_path.__wrapped__ = safe_key_path  # 保留真实函数引用 (供测试)


def _make_host_key_policy():
    """REVIEW-11-P0-2: SSH 主机 host key 策略工厂。
    生产环境默认 reject,严禁 AutoAddPolicy (MITM 风险)。
    """
    policy = (SSH_HOST_KEY_POLICY or 'reject').lower()
    if policy == 'reject':
        return paramiko.RejectPolicy()
    if policy == 'warning':
        return paramiko.WarningPolicy()
    if policy == 'auto':
        # 仅限本地测试环境使用
        return paramiko.AutoAddPolicy()
    raise ValueError(
        'OGS_SSH_HOST_KEY_POLICY 必须是 reject/warning/auto,当前: %r' % policy
    )


class DangerousCommandError(Exception):
    """REVIEW-11-P1-1: 危险命令拦截异常。"""
    pass


class SshCommandTimeout(Exception):
    """REV46-M22: ssh_cmd select 轮询超时异常.

    旧实现: stdout.read() 同步阻塞, 死循环/慢命令会让 worker 永久挂起.
    新实现: 超过 SSH_CMD_TIMEOUT 秒未收到 EOF/数据则中断, 抛 SshCommandTimeout.
    """
    pass


def _read_with_select(channel, max_bytes, timeout):
    """REV46-M22: 用 select 主动 poll channel 读取, 带超时.

    - 每次 select 等待 1s, 累计超过 timeout 秒仍未收到 EOF/数据 → 抛 SshCommandTimeout
    - 收到数据时一次性 read(max_bytes) (但 select 缓冲可能远小于 max_bytes, 实际由
      channel 内部缓冲, 不会真正读到 max_bytes; 截断判定仍走外层 recv_ready 检查)
    - 通道关闭 (recv_ready=False 且 status 有值) 时返回剩余数据
    """
    import time as _time
    deadline = _time.monotonic() + timeout
    collected = b''
    while len(collected) < max_bytes:
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            raise SshCommandTimeout(
                'ssh_cmd select timeout after %ds' % timeout
            )
        # 每次 select 等待 1s 或直到 channel 可读
        wait = min(1.0, remaining)
        try:
            r, _, _ = select.select([channel], [], [], wait)
        except (OSError, ValueError):
            # channel 已关闭/异常, 退出循环
            break
        if not r:
            # timeout 内无数据, 但尚未到总超时, 继续轮询
            if channel.status_event.is_set() or channel.exit_status_ready():
                # 命令已结束, 但可能还有 stdout 缓冲未读
                pass
            else:
                # 仍未到 deadline 也不可读, 继续下一次 select
                if _time.monotonic() < deadline:
                    continue
                else:
                    raise SshCommandTimeout(
                        'ssh_cmd select timeout after %ds' % timeout
                    )
        # 可读, 读一段
        try:
            chunk = channel.recv(max_bytes - len(collected))
        except socket.timeout:
            raise SshCommandTimeout(
                'ssh_cmd socket.timeout after %ds' % timeout
            )
        if not chunk:
            # EOF
            break
        collected += chunk
        # 读到非满 max_bytes 通常表示当前无可读, 检查是否已结束
        if len(chunk) < (max_bytes - len(collected)):
            if channel.exit_status_ready():
                # 命令已结束, 退出
                break
    return collected


def _check_dangerous_command(command):
    """REVIEW-11-P1-1: SSH 危险命令黑名单拦截。
    拦截 rm -rf / / mkfs / dd if= / shutdown / reboot / fork 炸弹 等。
    返回 None 表示命令安全,否则返回被拦截的危险模式字符串。

    R2-1 (REV46-H19): 改用 regex + 词边界避免误拦截.
    边界字符: \\s (空白) ; & | 或字符串起止.
    例: "rm -rf /" 不再误拦 "rm -rf /home/xxx" (因 / 紧跟 home, 非边界).
    """
    if not isinstance(command, str):
        return 'cmd not a string'
    cmd_stripped = command.strip()
    if not cmd_stripped:
        return None
    for pattern, label in _get_dangerous_regex():
        if pattern.search(cmd_stripped):
            return label
    return None


def get_ssh_password(sys_user_row):
    """从 t_sys_user 行提取明文 SSH 密码，自动处理 base64/Fernet 兼容 + 透明迁移。

    透明迁移语义：
        - 如果存储值是旧 base64 编码，解码出明文后会自动重新加密为 Fernet 并写回 DB
        - 如果存储值已经是 Fernet 密文，直接解密
        - 并发安全：rehash 是幂等 UPDATE，多个请求同时触发最终结果一致

    R2-2 (REV46-H20): 改走 osql_up + SqlOpError, 与 REV44-H4 同模式
    (写库失败 → 主业务 500 → 必须降级 + Log.warning, 不再绕过统一封装)
    """
    if sys_user_row is None:
        return None

    stored = sys_user_row.host_password
    sys_user_id = sys_user_row.id

    def _rehash(new_stored):
        # R2-2: 走 osql_up 而非直接 db.session.commit()
        # 失败时 SqlOpError 降级为 logger.warning, 不阻断主业务
        #
        # REV47-T3: 委托 audsec.safe_db_write 统一降级模式, 消除内联 try/except.
        # 与 REV44-H4 (audlog) 共用同一实现, 仅 logger/level 差异.
        from app.core.db.insert import osql_up
        safe_db_write(
            lambda: osql_up('t_sys_user', {'id': sys_user_id},
                            {'host_password': new_stored}),
            op_name='ssh_password_rehash',
            level='warning',
            logger_name='shellcmd',
            sys_user_id=sys_user_id,
        )

    return decrypt_host_password(stored, rehash_callback=_rehash)


def get_ssh_connection(alias, host_ip, host_port):
    """根据系统用户别名 + 主机信息创建 SSH 连接，自动判断 key/password 认证。
    返回 RemoteConnectionAuto 实例。

    REV46-H18: sys_user 不存在时抛 ValueError (而非 AttributeError 500).
    """
    # REV47-M6: 业务查询过滤软删 (不能拿软删 sys_user 去建 SSH 连接)
    sys_user_info = t_sys_user.query.filter_by(alias=alias, is_deleted=False).first()
    if sys_user_info is None:
        raise ValueError(f'system user alias not found: {alias!r}')
    return RemoteConnectionAuto(host_ip, host_port, sys_user_info.host_user,
                                get_ssh_password(sys_user_info), sys_user_info.host_key)


def get_ssh_connection_by_id(sys_user_id, host_ip, host_port):
    """Create an SSH connection from an immutable credential reference."""
    try:
        credential_id = int(sys_user_id)
    except (TypeError, ValueError):
        raise ValueError("invalid system user id") from None
    sys_user_info = t_sys_user.query.filter_by(
        id=credential_id,
        is_deleted=False,
    ).first()
    if sys_user_info is None:
        raise ValueError("system user does not exist or has been deleted")
    return RemoteConnectionAuto(
        host_ip,
        host_port,
        sys_user_info.host_user,
        get_ssh_password(sys_user_info),
        sys_user_info.host_key,
    )


# 远程操作linux服务器
class RemoteConnectionAuto:
    # REV47-M25: 入参类型校验常量
    #   防御: 业务层误传 int port = '28000' (字符串) 或 None username → paramiko
    #         在更深层抛 obscure exception, 调试困难
    _HOST_TYPES = (str,)
    _PORT_TYPES = (int,)
    _USERNAME_TYPES = (str,)

    def __init__(self, host, port, username, password=None, pkey=None):
        """
        host-->远程连接的主机ip,str类型
        port-->远程连接的主机ssh端口,int类型
        username-->远程连接的主机用户名,str类型
        key-->远程连接的主机用户秘钥,str类型

        REV47-M25: 入参类型校验, 业务层传错类型早 raise, 避免 paramiko 内层
        obscure exception. 校验失败信息含参数名+实际类型, 便于定位调用方.
        REV47-M28: 加载系统 known_hosts (host key cache) + 接受自定义 known_hosts 路径.
                   - load_system_host_keys() 读 ~/.ssh/known_hosts (生产运维习惯)
                   - 同时支持 OGS_SSH_KNOWN_HOSTS 环境变量指定额外文件
                   - 命中后 paramiko 用 reject 策略也合法 (不用 AutoAdd)
        """
        # REV47-M25: 类型校验
        if not isinstance(host, self._HOST_TYPES):
            raise TypeError(
                f'host 必须是 str, 实际 {type(host).__name__}: {host!r}'
            )
        if not isinstance(port, self._PORT_TYPES):
            raise TypeError(
                f'port 必须是 int, 实际 {type(port).__name__}: {port!r}'
            )
        if not isinstance(username, self._USERNAME_TYPES):
            raise TypeError(
                f'username 必须是 str, 实际 {type(username).__name__}: {username!r}'
            )
        if not (1 <= int(port) <= 65535):
            raise ValueError(
                f'port 越界 (须 1-65535): {port!r}'
            )

        # REV47-M28: host key cache - 加载 known_hosts
        #   流程: 系统 known_hosts → 自定义 known_hosts → 连接
        #   若 host 在 known_hosts 中有 fingerprint, RejectPolicy 仍合法 (命中即通过)
        #   若 host 不在 known_hosts 中, RejectPolicy 抛 SSHException (安全)
        from app.core.config import _env  # 局部 import 避免循环
        _known_hosts_extra = _env('OGS_SSH_KNOWN_HOSTS', '') or ''

        self.host = host
        self.port = int(port)  # 强制 int
        self.username = username
        self.password = password
        # Keep the legacy ``str | None`` return contract for existing callers,
        # while allowing batch execution to surface a useful remote diagnostic.
        self.last_command_error = None
        self.ssh = paramiko.SSHClient()
        # REV47-M28: 加载 host key cache (先系统, 再自定义)
        try:
            self.ssh.load_system_host_keys()
        except Exception as e:
            import logging as _logging
            _logging.getLogger('shellcmd').warning(
                'load_system_host_keys failed (continuing without cache): %s', e,
            )
        if _known_hosts_extra:
            try:
                self.ssh.load_host_keys(_known_hosts_extra)
            except Exception as e:
                import logging as _logging
                _logging.getLogger('shellcmd').warning(
                    'load_host_keys(%s) failed: %s', _known_hosts_extra, e,
                )
        # REVIEW-11-P0-2: 使用策略工厂 (默认 RejectPolicy),禁止 AutoAddPolicy
        self.ssh.set_missing_host_key_policy(_make_host_key_policy())
        if pkey:
            # REV46-H17: 私钥路径 realpath 校验 (防 ../ 任意读 + symlink 逃逸)
            self.pkey = _safe_key_path(pkey)
            self.key = paramiko.RSAKey.from_private_key_file(self.pkey)
            self.ssh.connect(self.host, port=self.port, username=self.username, pkey=self.key, timeout=SSH_CONNECT_TIMEOUT)
        else:
            # password 字段必须为明文（调用方负责解密：Fernet 密文走 get_ssh_password）
            self.ssh.connect(self.host, port=self.port, username=self.username,
                             password=self.password, timeout=SSH_CONNECT_TIMEOUT)
        # REVIEW-11-P2-2: keepalive (默认 60s),防中间设备切断长连接
        if SSH_KEEPALIVE_INTERVAL > 0:
            try:
                transport = self.ssh.get_transport()
                if transport is not None:
                    transport.set_keepalive(SSH_KEEPALIVE_INTERVAL)
            except Exception:
                pass

    def ssh_cmd(self, command, audit_callback=None, command_timeout=None):
        """
        command-->需要执行的shell命令,str类型
        audit_callback-->REV46-M26 审计回调, 签名 (log_name, log_type, log_info,
                        log_host, log_status, log_msg) 仿 ComToolsLog.host_log.
                        推荐传 app.tools.audlog.log_ssh_audit 写 t_command_log.
        command_timeout-->可选的单次命令超时秒数，不得超过全局 SSH_CMD_TIMEOUT。
        REVIEW-11-P1-1: 危险命令前置拦截 (黑名单)
        REVIEW-11-P1-2: stdout/stderr 输出长度上限 (防 DoS)
        REV46-M23: 危险命令检测命中时, 不再返回 'DANGEROUS_COMMAND_BLOCKED:' 字符串
                    (被调用方误当正常输出), 改为 raise DangerousCommandError.
                    外层调用方 (ServerManagement / cron / containers) 需 except.
        REV46-M22: stdout/stderr 读取改用 select 轮询 + SSH_CMD_TIMEOUT 超时.
                    旧实现 stdout.read() 同步阻塞, 死循环/慢命令会让 worker 永久挂起.
        """
        self.last_command_error = None
        # P1-1: 危险命令前置检查
        danger = _check_dangerous_command(command)
        if danger:
            # REV46-M23: 抛异常而非返回字符串
            err = DangerousCommandError('blocked: %s' % danger)
            err.danger_pattern = danger  # 让调用方能拿到具体危险模式
            # REV46-M26: 审计 (危险命令拦截事件)
            if audit_callback is not None:
                try:
                    audit_callback(
                        log_name='', log_type='ssh_cmd_dangerous',
                        log_info=(command or '')[:200], log_host=self.host,
                        log_status='blocked',
                        log_msg='danger_pattern=%s' % danger,
                    )
                except Exception:
                    # 审计失败不阻断主业务
                    pass
            raise err
        try:
            stdin, stdout, stderr = self.ssh.exec_command(command)
            # M22: 改用 select 轮询代替同步 read, 防永久阻塞
            max_bytes = SSH_CMD_MAX_OUTPUT_BYTES
            timeout = SSH_CMD_TIMEOUT
            if command_timeout is not None:
                try:
                    timeout = max(
                        1,
                        min(SSH_CMD_TIMEOUT, int(command_timeout)),
                    )
                except (TypeError, ValueError):
                    raise ValueError("command_timeout must be an integer")
            stdout_msg = _read_with_select(
                stdout.channel, max_bytes, timeout
            ).decode(errors='replace')
            stderr_msg = _read_with_select(
                stderr.channel, max_bytes, timeout
            ).decode(errors='replace')
            # 检测截断
            truncated = False
            try:
                if stdout.channel.recv_ready():
                    truncated = True
                if stderr.channel.recv_ready():
                    truncated = True
            except Exception:
                pass
            if truncated:
                suffix = '\n[OUTPUT TRUNCATED at %d bytes]' % max_bytes
                if stdout_msg:
                    stdout_msg = stdout_msg + suffix
                else:
                    stderr_msg = stderr_msg + suffix
            if stdout_msg:
                result = stdout_msg
            else:
                result = stderr_msg
            # Transport success is not command success. Paramiko returns stderr
            # normally for a non-zero remote exit, so checking only for raised
            # exceptions incorrectly marked commands such as `false` as success.
            exit_code = stdout.channel.recv_exit_status()
            if isinstance(exit_code, int) and exit_code != 0:
                diagnostic = (stderr_msg or stdout_msg or "").strip()
                self.last_command_error = "exit code %d%s" % (
                    exit_code,
                    (": " + diagnostic[:2000]) if diagnostic else "",
                )
                if audit_callback is not None:
                    try:
                        audit_callback(
                            log_name='', log_type='ssh_cmd',
                            log_info=(command or '')[:200], log_host=self.host,
                            log_status='failed',
                            log_msg='exit_code=%d; output_bytes=%d'
                                    % (exit_code, len(result or '')),
                        )
                    except Exception:
                        pass
                return None
            # REV46-M26: 审计 (成功执行)
            if audit_callback is not None:
                try:
                    audit_callback(
                        log_name='', log_type='ssh_cmd',
                        log_info=(command or '')[:200], log_host=self.host,
                        log_status='success',
                        log_msg='output_bytes=%d' % len(result or ''),
                    )
                except Exception:
                    pass
            return result
        except SshCommandTimeout as e:
            # REV46-M22: 超时明确抛 SshCommandTimeout (不再返回 None 误导调用方)
            # 调用方应能识别此异常 (例如记录到审计日志)
            # REV46-M26: 审计 (超时)
            if audit_callback is not None:
                try:
                    audit_callback(
                        log_name='', log_type='ssh_cmd_timeout',
                        log_info=(command or '')[:200], log_host=self.host,
                        log_status='timeout',
                        log_msg='%ds timeout' % timeout,
                    )
                except Exception:
                    pass
            raise
        except Exception as e:
            self.last_command_error = "SSH execution failed (%s)" % (
                e.__class__.__name__,
            )
            # REV46-M26: 审计 (失败)
            if audit_callback is not None:
                try:
                    audit_callback(
                        log_name='', log_type='ssh_cmd',
                        log_info=(command or '')[:200], log_host=self.host,
                        log_status='failed',
                        log_msg='err=%s' % (e.__class__.__name__),
                    )
                except Exception:
                    pass
            return None
        # REV46-M20: 移除 finally 自动 close, 改为调用方显式 close()
        # 旧实现: 每次 ssh_cmd 都 close 整个 SSH 连接 → 频繁命令低效
        # 新实现: 连接生命周期由调用方管理, 支持复用 + 显式 close + 上下文管理器

    def close(self):
        """REV46-M20: 显式关闭 SSH 连接 (调用方管理生命周期).

        推荐用法 (上下文管理器):
            with get_ssh_connection(...) as conn:
                conn.ssh_cmd('cmd1')  # 复用
                conn.ssh_cmd('cmd2')  # 复用

        或 try/finally:
            conn = get_ssh_connection(...)
            try:
                conn.ssh_cmd(cmd)
            finally:
                conn.close()
        """
        if getattr(self, '_closed', False):
            return
        try:
            self.ssh.close()
        except Exception:
            pass
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def put_file(self, form_path, to_path):
        """
        form_path-->从本地上传的文件路径;str类型
        to_path-->上传到对方服务器的文件路径;str类型
        REV46-H16: to_path 必须经 _safe_remote_path 校验 (白名单 + 防 ..)
        """
        # REV46-M21: 异常时也 close sftp_client (防 fd 泄漏)
        safe_to = _safe_remote_path(to_path)
        sftp_cilent = None
        try:
            sftp_cilent = paramiko.SFTPClient.from_transport(self.ssh.get_transport())
            sftp_cilent.put(form_path, safe_to)
        finally:
            if sftp_cilent is not None:
                try:
                    sftp_cilent.close()
                except Exception:
                    pass

    def put_fileobj(self, file_obj, to_path):
        """
        file_obj-->文件对象(file-like object)，如Flask上传的FileStorage
        to_path-->上传到对方服务器的文件路径;str类型
        REV46-H16: to_path 必须经 _safe_remote_path 校验
        """
        safe_to = _safe_remote_path(to_path)
        sftp_cilent = None
        try:
            sftp_cilent = paramiko.SFTPClient.from_transport(self.ssh.get_transport())
            sftp_cilent.putfo(file_obj, safe_to)
        finally:
            if sftp_cilent is not None:
                try:
                    sftp_cilent.close()
                except Exception:
                    pass
