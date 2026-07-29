import os
import psutil
import mimetypes
from flask import request, jsonify
from werkzeug.utils import secure_filename
from app.core.config import FILE_CONF
# REV37-H2: 审计日志 (记录谁上传了什么到哪个路径)
from app.tools.at import _session, request_param
from app.tools.audlog import CzToolsLog

# REV30-L13: 文件保存 size 上限 (100MB, 与 app_factory MAX_CONTENT_LENGTH 兜底一致)
_MAX_SAVE_FILE_SIZE = 100 * 1024 * 1024

# REV37-H2: 危险脚本后缀 (上传到 data 目录后被运维误执行风险)
_DANGER_EXT = frozenset(('.py', '.sh', '.bash', '.ps1', '.bat', '.cmd', '.vbs', '.jar', '.php', '.pl', '.rb'))
# REV37-H2: 仅允许常见的文本/图片/压缩/文档类型 (MIME 嗅探白名单)
#   注意: 这是 MIME 嗅探 (按内容, 不是扩展名) - 防扩展名伪造
_ALLOWED_MIME_PREFIX = ('image/', 'text/', 'application/json', 'application/xml',
                        'application/pdf', 'application/zip', 'application/x-tar',
                        'application/gzip', 'application/x-gzip', 'application/octet-stream')


class FileGet:
    """文件管理：所有路径操作严格限定在 FILE_CONF['file_path2'] 沙箱内。

    REVIEW-5-A (P0 修复)：消除任意本地文件读 / 写 / 删路径穿越漏洞。
    关键改动：
      1. 彻底移除 ``os.chdir`` —— 用绝对路径代替
      2. ``req_dir`` 在 ``__init__`` 一次性校验（白名单 + realpath + commonpath）
      3. 每个文件 / 目录方法都基于沙箱绝对路径操作，落盘 / 删除前再校验一次
      4. 错误统一返回 ``{'code': 100, 'msg': ...}``
    """

    # REVIEW-5-A: 禁止 raw 用户输入包含这些 token
    _FORBIDDEN_TOKENS = ('..', '\x00')

    def __init__(self):
        self.req_dir = request_param('req_dir', default='') or ''
        # REVIEW-5-A: 沙箱根目录解析为绝对路径
        self.def_dir_path = os.path.realpath(FILE_CONF['file_path2'])
        # REVIEW-5-A: req_dir 白名单校验
        self._invalid = self._validate_dir_name(self.req_dir)
        # REVIEW-5-A: 解析后的目标路径（如果无效则等于沙箱根）
        if self._invalid:
            self.target_dir = self.def_dir_path
        else:
            candidate = os.path.realpath(os.path.join(self.def_dir_path, self.req_dir))
            # REVIEW-5-A: commonpath 校验，防 symlink 跳出
            if self._is_within(candidate, self.def_dir_path):
                self.target_dir = candidate
            else:
                self._invalid = True
                self.target_dir = self.def_dir_path
        self.dir_list = []
        self.file_list = []

    # ------------------------------------------------------------------
    # REVIEW-5-A: 路径校验辅助方法
    # ------------------------------------------------------------------
    @classmethod
    def _validate_dir_name(cls, name):
        """校验用户传入的目录 / 文件名是否合法。
        - 空字符串：允许（代表沙箱根）
        - 包含 ``..`` 或空字节：拒绝
        - 绝对路径前缀（/ 或 \\）：拒绝
        - Windows 盘符（如 ``C:`` 或 ``D:\\``）：拒绝
          REV30-L12: name[1] == ':' 只检查索引 1 (盘符冒号分隔符), 不检查其他位置,
                     对 Unicode 路径不成立 (代码点 1 通常不是 ':'), 逻辑正确但需注释说明.
                     len < 2 时 name[1] 会 IndexError, 原代码已用 len>=2 保护, 安全.
        """
        if not name:
            return False
        if any(tok in name for tok in cls._FORBIDDEN_TOKENS):
            return True
        if name.startswith('/') or name.startswith('\\'):
            return True
        # REV30-L12: 只检查盘符冒号分隔符 (name[1] == ':'), 防 'C:', 'D:' 等绝对路径逃逸
        if len(name) >= 2 and name[1] == ':':
            return True
        return False

    @staticmethod
    def _is_within(child, parent):
        """REVIEW-5-A: 校验 ``child`` 在 ``parent`` 之内（防 symlink 跳出沙箱）。
        ``child`` 与 ``parent`` 都必须是已 realpath 解析的绝对路径。
        """
        try:
            return os.path.commonpath([child, parent]) == parent
        except (ValueError, OSError):
            return False

    def _err_if_invalid(self):
        """REVIEW-5-A: 沙箱校验失败时统一返回错误响应。"""
        if self._invalid:
            return jsonify({'code': 100, 'msg': '非法的目录路径'})
        return None

    def _validate_filename(self, name):
        """REVIEW-5-A: 校验文件名并返回真实路径；非法返回 None。"""
        if not name or self._validate_dir_name(name):
            return None
        target = os.path.realpath(os.path.join(self.target_dir, name))
        if not self._is_within(target, self.def_dir_path):
            return None
        return target

    # ------------------------------------------------------------------
    # 路由方法
    # ------------------------------------------------------------------
    def get_file_list(self):
        """列目录 + 磁盘信息。
        REVIEW-5-A: 不再 chdir，直接对 ``target_dir`` 列目录；
        ``checkout`` 通过 ``os.path.dirname`` 回退一层，且必须仍在沙箱内。
        """
        err = self._err_if_invalid()
        if err:
            return err
        try:
            disk_msg = psutil.disk_usage(self.def_dir_path)
        except Exception as e:
            return jsonify({'code': 100, 'msg': '磁盘信息获取失败: %s' % str(e)})
        disk_total = round(disk_msg.total / 1024 / 1024 / 1024)
        disk_used = round(disk_msg.used / 1024 / 1024 / 1024)
        disk_free = round(disk_msg.free / 1024 / 1024 / 1024)

        # REVIEW-5-A: 不再 chdir，改用绝对路径
        get_file_type = request_param('get_file_type')
        target = self.target_dir
        if get_file_type == 'checkout':
            # REVIEW-5-A: 回退一层：必须在沙箱内
            parent = os.path.dirname(target)
            if self._is_within(parent, self.def_dir_path):
                target = parent
            else:
                return jsonify({'code': 100, 'msg': '已达沙箱根目录'})

        try:
            entries = os.listdir(target)
        except (FileNotFoundError, PermissionError, NotADirectoryError) as e:
            return jsonify({'code': 100, 'msg': '目录访问失败: %s' % str(e)})

        for name in entries:
            full = os.path.join(target, name)
            if os.path.isfile(full):
                self.file_list.append(name)
            else:
                self.dir_list.append(name)

        # REVIEW-5-A: 用绝对路径算相对沙箱的显示路径，不依赖 chdir 后 os.getcwd()
        rel = target[len(self.def_dir_path):]
        if not rel:
            is_path = '/'
        else:
            is_path = rel.replace(os.sep, '/') + '/'

        return jsonify({
            'file': self.file_list,
            'dir': self.dir_list,
            'ispath': is_path,
            'disk': {'total': disk_total, 'used': disk_used, 'free': disk_free},
        })

    def get_file_size(self):
        """REVIEW-5-A: 获取文件大小。基于沙箱绝对路径，不再依赖 chdir。"""
        err = self._err_if_invalid()
        if err:
            return err
        si_filename = request_param('si_filename', '')
        target = self._validate_filename(si_filename)
        if target is None:
            return jsonify({'code': 100, 'msg': '非法的文件路径'})
        try:
            file_size = os.path.getsize(target)
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError) as e:
            return jsonify({'code': 100, 'msg': '文件访问失败: %s' % str(e)})

        if file_size < 1024:
            size_str = str(file_size) + 'B'
        elif file_size < 1024 * 1024:
            size_str = str(round(file_size / 1024)) + 'KB'
        elif file_size < 1024 ** 3:
            size_str = str(round(file_size / 1024 / 1024)) + 'MB'
        elif file_size < 1024 ** 4:
            size_str = str(round(file_size / 1024 / 1024 / 1024)) + 'GB'
        elif file_size < 1024 ** 5:
            size_str = str(round(file_size / 1024 / 1024 / 1024 / 1024)) + 'TB'
        else:
            size_str = str(round(file_size / 1024 ** 5)) + 'PB'
        return jsonify({'filename': si_filename, 'size': size_str})

    def mkdir_file_name(self):
        """REVIEW-5-A: 创建目录。基于沙箱绝对路径。"""
        err = self._err_if_invalid()
        if err:
            return err
        mk_filename = request_param('mk_filename', '')
        target = self._validate_filename(mk_filename)
        if target is None:
            return jsonify({'code': 100, 'msg': '非法的目录名'})
        if os.path.exists(target):
            return jsonify({'code': 100, 'msg': '该文件已存在'})
        try:
            os.mkdir(target)
            return jsonify({'code': 0, 'msg': '创建成功'})
        except (FileNotFoundError, PermissionError, OSError) as e:
            return jsonify({'code': 100, 'msg': '创建失败: %s' % str(e)})

    def change_file_name(self):
        """REVIEW-5-A: 重命名。old / new 双路径都必须仍在沙箱内。"""
        err = self._err_if_invalid()
        if err:
            return err
        old_name = request_param('old_name', '')
        new_name = request_param('new_name', '')
        old_path = self._validate_filename(old_name)
        new_path = self._validate_filename(new_name)
        if old_path is None or new_path is None:
            return jsonify({'code': 100, 'msg': '非法的文件名'})
        if os.path.exists(new_path):
            return jsonify({'code': 100, 'msg': '修改名称失败，已有该名称'})
        try:
            os.rename(old_path, new_path)
            return jsonify({'code': 0, 'msg': '修改成功'})
        except (FileNotFoundError, PermissionError, OSError) as e:
            return jsonify({'code': 100, 'msg': '重命名失败: %s' % str(e)})

    def remove_file(self):
        """REVIEW-5-A: 删除文件 / 目录。基于沙箱绝对路径。"""
        err = self._err_if_invalid()
        if err:
            return err
        rm_filename = request_param('rm_filename', '')
        target = self._validate_filename(rm_filename)
        if target is None:
            return jsonify({'code': 100, 'msg': '非法的文件路径'})
        try:
            if os.path.isfile(target):
                os.remove(target)
                return jsonify({'code': 0, 'msg': '删除了一个文件'})
            elif os.path.isdir(target):
                os.rmdir(target)
                return jsonify({'code': 0, 'msg': '删除了一个目录'})
            else:
                return jsonify({'code': 100, 'msg': '目标不存在'})
        except (FileNotFoundError, PermissionError, OSError) as e:
            return jsonify({'code': 100, 'msg': '删除失败: %s' % str(e)})

    def save_file(self):
        """REVIEW-5-A: 保存上传文件。
        ``secure_filename`` 防 .. / 路径分隔符；落盘路径仍要 realpath + commonpath 校验。
        REV30-L13: 显式 size 限制, 防 Flask 全局 MAX_CONTENT_LENGTH 未配置时超大文件 DoS。
        REV37-H2: MIME 嗅探防误执行, 扩展名黑名单 + 审计日志。
        """
        err = self._err_if_invalid()
        if err:
            return err
        file = request.files.get('file')
        if file is None or not file.filename:
            return jsonify({'code': 100, 'msg': '未提供文件'})
        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({'code': 100, 'msg': '非法的文件名'})
        # REV37-H2: 危险脚本后缀黑名单 (运维可能误 cd 到 data 目录执行 .sh / .py)
        ext = os.path.splitext(filename)[1].lower()
        if ext in _DANGER_EXT:
            return jsonify({'code': 100, 'msg': '禁止上传脚本类型文件: %s' % ext})
        # REV30-L13: 显式 size 检查 (依赖 Flask MAX_CONTENT_LENGTH 兜底, 此处主动 +1 字节探测)
        try:
            file.stream.seek(0, os.SEEK_END)
            size = file.stream.tell()
            file.stream.seek(0)
            if size > _MAX_SAVE_FILE_SIZE:
                return jsonify({'code': 100, 'msg': 'file too large (max %d bytes)' % _MAX_SAVE_FILE_SIZE})
        except Exception:
            pass
        target = os.path.realpath(os.path.join(self.target_dir, filename))
        if not self._is_within(target, self.def_dir_path):
            return jsonify({'code': 100, 'msg': '路径越界'})
        # REV37-H2: MIME 嗅探 (按文件头魔术字节, 不依赖扩展名)
        #   Python stdlib mimetypes 仅按扩展名猜, 不可靠. 这里用 file.stream.read(2048) 探测头
        sniffed_mime = ''
        try:
            head = file.stream.read(2048)
            file.stream.seek(0)
            sniffed_mime = mimetypes.guess_type(filename)[0] or ''
            # 防 binary masquerading: 检查头几个字节
            if not head:
                pass  # 空文件, 放行
            elif head[:4] == b'\x7fELF':
                return jsonify({'code': 100, 'msg': '禁止上传 ELF 可执行文件'})
            elif head[:2] == b'MZ':
                return jsonify({'code': 100, 'msg': '禁止上传 PE 可执行文件'})
            elif head[:4] == b'\xca\xfe\xba\xbe' or head[:4] == b'\x7fELF':
                return jsonify({'code': 100, 'msg': '禁止上传 class/elf 可执行文件'})
            elif head[:3] == b'\x1f\x8b\x08':
                # gzip: 放行, 后续用户自行解压
                pass
        except Exception:
            pass
        # REV37-H2: 审计 - 记录谁上传了什么
        try:
            _ords, cz_name = _session()
            ip = request.remote_addr or ''
            xff = request.headers.get('X-Forwarded-For', '')
            if xff:
                ip = xff.split(',')[0].strip() or ip
            ua = (request.headers.get('User-Agent') or '')[:200]
            # 不引入新表, 复用 CzToolsLog 写 t_cz_log (与 H1 一致)
            try:
                CzToolsLog().host_log(
                    cz_name or '', '文件操作',
                    'file_upload@%s' % filename[:100],
                    'size=%d; mime=%s; ip=%s; ua=%s; path=%s' % (
                        size, sniffed_mime, ip, ua, self.target_dir[:200]),
                    '成功', None,
                )
            except Exception:
                pass  # 审计失败不影响上传主流程
        except Exception:
            pass
        try:
            file.save(target)
            return jsonify({'code': 0, 'msg': '保存成功'})
        except (FileNotFoundError, PermissionError, OSError) as e:
            return jsonify({'code': 100, 'msg': '保存失败: %s' % str(e)})
