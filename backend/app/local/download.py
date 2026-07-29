import json
import os
import re
from urllib.parse import quote

from flask import request, Response
from werkzeug.utils import secure_filename
from app.core.config import FILE_CONF
from app.tools.at import Log, request_param

# REV16 B7 HIGH-1: filename 严格白名单 (路径越界防御)
#   原有：self.file_path + self.file_name 字符串拼接，filename 未校验
#   攻击：filename=../../../etc/passwd → 任意文件下载
#   修复：白名单 + secure_filename + realpath 越界检测
_FILENAME_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,128}$')


class DownloadFile:
    """
        文件下载接口
    :post传值下载文件
    """

    def __init__(self):
        self.file_path = FILE_CONF['file_path2']
        self.file_name = request_param('filename')

    @staticmethod
    def file_iterator(file_path, chunk_size=512):
        """
            文件读取迭代器
        :param file_path:文件路径
        :param chunk_size: 每次读取流大小
        :return:
        """
        with open(file_path, 'rb') as target_file:
            while True:
                chunk = target_file.read(chunk_size)
                if chunk:
                    yield chunk
                else:
                    break

    @staticmethod
    def to_json(obj):
        """
            放置
        :return:
        """
        return json.dumps(obj, ensure_ascii=False)

    def _err_json(self, msg, status=400):
        """REV30-H4: 错误统一返 Response(json, status=400) 而非裸 json.dumps,
        让前端可以用统一 response.blob()/response.json() 路径处理。"""
        payload = json.dumps({'status': 'fail', 'msg': msg}, ensure_ascii=False)
        return Response(payload, status=status, mimetype='application/json')

    def download(self):
        """
            文件下载
        :return:
        """
        # REV16 B7 HIGH-1: filename 白名单 + 越界检测
        if not self.file_name or not _FILENAME_RE.fullmatch(self.file_name):
            Log.logger.warning('DownloadFile invalid filename: %r' % self.file_name)
            return self._err_json('invalid filename')
        # REV30-H4: secure_filename 去除 \r\n / 路径分隔符, 防 Content-Disposition 注入
        safe_name = secure_filename(self.file_name) or 'download.bin'
        target = self.file_path + safe_name
        real_target = os.path.realpath(target)
        real_root = os.path.realpath(self.file_path)
        if os.path.commonpath([real_target, real_root]) != real_root:
            Log.logger.warning('DownloadFile path traversal blocked: %s -> %s' % (safe_name, real_target))
            return self._err_json('path traversal blocked')
        if not os.path.isfile(real_target):
            return self._err_json('文件路径不存在')
        # REV30-H4: 二次 secure_filename 确保 header 不含 \r\n / 特殊字符
        filename = secure_filename(os.path.basename(real_target)) or 'download.bin'
        # REV30-H4: RFC 6266 Content-Disposition: filename*=UTF-8''<percent-encoded>
        #   原: filename="{filename}" 直接拼, filename 含 \r\n 可注入 header
        #   修: 走 RFC 6266 标准的 filename* 格式 + percent-encode
        quoted = quote(filename, safe='')
        response = Response(self.file_iterator(real_target))
        response.headers['Content-Type'] = 'application/octet-stream'
        response.headers["Content-Disposition"] = "attachment; filename*=UTF-8''%s" % quoted
        return response
