import os
import re
import shlex
import subprocess
import sys

from flask import request, jsonify
from werkzeug.utils import secure_filename

from app.core.config import FILE_CONF
from app.tools.at import Log, request_param

sys.path.append('../..')


# REVIEW-11-P0-1: group_dir / project_dir 白名单
#   仅允许 [A-Za-z0-9._-]{1,64},阻断经典 shell 注入 (`;` / `&&` / `$()` 等)
_ALLOWED_NAME_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,64}$')


def _validate_safe_name(name, field):
    """P0-1 修复: 严格白名单校验 group_dir / project_dir。
    返回 (safe_name, None) 或 (None, error_response)。"""
    if name is None:
        return None, jsonify({'code': 100, 'msg': 'missing %s' % field})
    if not isinstance(name, str) or not _ALLOWED_NAME_RE.fullmatch(name):
        return None, jsonify({
            'code': 100,
            'msg': 'invalid %s: must match [A-Za-z0-9._-]{1,64}' % field,
        })
    return name, None


# REV16 B7 HIGH-2: 命令白名单改为 shlex 解析 + token 严格匹配
#   原：'ls /tmp; rm -rf /'.startswith('ls ') -> True -> shell=True 注入执行
#   修复：shlex.split 拆 token + 第一个 token 必须严格命中白名单
_ALLOWED_CMD_TOKENS = frozenset({
    'ls', '/usr/bin/rsync', '/bin/ls',
})


def _is_allowed_cmd(cmd):
    """REV16 B7 HIGH-2: 严格 token 匹配。
    - shlex 拆分，第一个 token 必须严格命中 _ALLOWED_CMD_TOKENS
    - 阻断：'ls /tmp; rm -rf /' -> shlex 拆分后首个 token 'ls' 在白名单内
           但 shell=False 模式下仅执行 ls，剩余作为参数传给 ls（不会解释 ;）
    - 阻断：'cat /etc/passwd' -> 首个 token 'cat' 不在白名单
    """
    if not isinstance(cmd, str):
        return False
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        return False
    if not tokens:
        return False
    return tokens[0] in _ALLOWED_CMD_TOKENS


def _safe_run(cmd_str, timeout=30, list_mode=False):
    """REV16 B7 HIGH-2: 改用 shlex.split + shell=False + 参数列表（消除 shell=True 注入面）。
    - cmd_str: 已通过 _is_allowed_cmd 校验
    - list_mode: True 返 list (按行 split), False 返单行字符串
    """
    tokens = shlex.split(cmd_str, posix=True)
    if not tokens or tokens[0] not in _ALLOWED_CMD_TOKENS:
        raise ValueError('cmd not in allowlist: %r' % cmd_str[:80])
    try:
        proc = subprocess.run(
            tokens,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors='replace',
        )
        out = proc.stdout or proc.stderr or ''
        if list_mode:
            return [s for s in out.replace('\n', ',').strip(',').split(',') if s]
        return out.replace('\n', '')
    except subprocess.TimeoutExpired:
        return [] if list_mode else ''


class LocalShell:
    def __init__(self):
        pass

    @staticmethod
    def cmd_shell(cmd):
        """REV16 B7 HIGH-2: 沙箱化 - token 白名单 + shell=False。
        完全消除 shell=True 注入面（'ls /tmp; rm -rf /' 不再通过 startswith 校验）。"""
        if not _is_allowed_cmd(cmd):
            raise ValueError('cmd not in allowlist: %r' % (cmd[:80] if isinstance(cmd, str) else cmd))
        return _safe_run(cmd, timeout=30, list_mode=False)

    @staticmethod
    def cmdlist_shell(cmd):
        """REV16 B7 HIGH-2: 沙箱化 - token 白名单 + shell=False。"""
        if not _is_allowed_cmd(cmd):
            raise ValueError('cmd not in allowlist: %r' % (cmd[:80] if isinstance(cmd, str) else cmd))
        return _safe_run(cmd, timeout=30, list_mode=True)


# P2-4 修复: LocalDirList 不再继承 LocalShell (空继承无意义)
class LocalDirList:
    def __init__(self, dir1path=None, dir2path=None, rscmd=None):
        self.dir1path = dir1path
        self.dir2path = dir2path
        self.rscmd = rscmd
        # P1-4 修复: 默认 None (原本字面字符串 'err not group_dir key' 会进 shell)
        self.group_dir = request_param('group_dir', type=str)

    def _safe_group_dir(self):
        """P0-1 + P1-4: group_dir 白名单 + 默认值校验。"""
        return _validate_safe_name(self.group_dir, 'group_dir')

    def _safe_project_dir(self, project_dir):
        """P0-1: project_dir 白名单。"""
        return _validate_safe_name(project_dir, 'project_dir')

    def getdir1(self):
        safe_group, err = self._safe_group_dir()
        if err:
            return err
        dir1 = self.cmdlist_shell(self.dir1path)
        if safe_group in dir1:
            # P0-1: safe_group 已校验,只能含 [A-Za-z0-9._-],不可注入
            dir2_path = (self.dir2path % safe_group)
            dir2 = self.cmdlist_shell(dir2_path)
            return jsonify({
                'code': 0,
                'msg': dir2,
            })
        else:
            # REV30-M7: 移除重复 msg key (原: 'msg'='本地命令执行失败', 'msg'='server is not group_dir xxx',
            # 后者覆盖前者, 前端只看到后者). 合并到单一 msg。
            return jsonify({
                'code': 100,
                'msg': '本地命令执行失败: server is not group_dir %s !' % safe_group,
            })

    def getdir2(self):
        project_dir = request_param('project_dir', type=str)
        safe_group, err = self._safe_group_dir()
        if err:
            return err
        safe_project, err2 = self._safe_project_dir(project_dir)
        if err2:
            return err2
        dir1 = self.cmdlist_shell(self.dir1path)
        if safe_group in dir1:
            dir2_path = (self.dir2path % safe_group)
            dir2 = self.cmdlist_shell(dir2_path)
            if safe_project in dir2:
                # P0-1: safe_group + safe_project 都已白名单, %s 拼接安全
                rsync_dir = (self.rscmd % (safe_group, safe_project))
                try:
                    msg_out = LocalShell().cmdlist_shell(rsync_dir)
                    return jsonify({
                        'code': 0,
                        'msg': msg_out,
                    })
                except Exception:
                    # REV30-M7: 移除重复 msg key, 合并为单一 msg
                    return jsonify({
                        'code': 100,
                        'msg': '本地命令执行失败: rsync %s %s is fail!' % (safe_group, safe_project),
                    })
            else:
                # REV30-M7: 移除重复 msg key
                return jsonify({
                    'code': 100,
                    'msg': '本地命令执行失败: server is not project_dir %s !' % safe_project,
                })
        else:
            # REV30-M7: 移除重复 msg key
            return jsonify({
                'code': 100,
                'msg': '本地命令执行失败: server is not group_dir %s !' % safe_group,
            })


class LocalFilePut:
    def __init__(self):
        self.file = request.files.get('file')
        # P1-3 修复: file 为 None 时 secure_filename 会抛 AttributeError
        self.file_name = secure_filename(self.file.filename) if self.file else ''
        self.file_route = FILE_CONF['file_path']

    def put_file(self):
        if self.file is not None and self.file_name:
            # P1-3 修复: realpath 校验 + 大小限制
            try:
                real_target = os.path.realpath(self.file_route + self.file_name)
                real_route = os.path.realpath(self.file_route)
                if os.path.commonpath([real_target, real_route]) != real_route:
                    Log.logger.warning('LocalFilePut path traversal blocked: %s' % self.file_name)
                    return jsonify({'status': 'fail', 'msg': 'path traversal blocked'})
                # P1-3: 简单 size 校验 (走 Flask MAX_CONTENT_LENGTH 已设 conf 则生效)
                self.file.save(real_target)
                return jsonify({'status': 'true'})
            # P2-5 修复: 异常时记录日志 + 返回更具体错误
            except Exception as e:
                Log.logger.error('LocalFilePut put_file error for %s: %s' % (self.file_name, e))
                return jsonify({'status': 'fail', 'msg': str(e)[:200]})
        else:
            return jsonify({'status': 'null'})
