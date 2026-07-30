import datetime, os, re
from PIL import Image
from flask import request, jsonify, make_response
from app.core.db.database import t_host, db, t_group, t_acc_user, t_login_log, t_line_chart
from app.tools.SqlListTool import ListTool
from app.core.db.insert import osql_in, osql_up, SqlOpError
from app.core.config import FILE_CONF
from app.tools.at import auth_list_get, request_param


# REV30-L9: PutUserImage 上传限制常量
#   5MB 上限是头像类常见选择; _ALLOWED_IMG_FORMATS 限定位图格式 (防 SVG / TIFF 等攻击面)
_MAX_UPLOAD_IMG_SIZE = 5 * 1024 * 1024  # 5MB
_ALLOWED_IMG_FORMATS = frozenset({'PNG', 'JPEG', 'JPG', 'GIF', 'WEBP'})


# REV30-H2: SQL LIKE 通配符转义 (同 REV28-H4 模式)
#   - now_date 是 date 对象 (如 2026-06-26), 一般不含 %, 但用户可控字段同样需要转义
#   - 转义 % 和 _, 并使用 escape='\\' 让 SQLAlchemy 认识反斜杠为转义符
_LIKE_ESCAPE_CHARS = str.maketrans({'\\': '\\\\', '%': '\\%', '_': '\\_'})


def _escape_like(s):
    """REV30-H2: 转义 LIKE 特殊字符。"""
    if s is None:
        return ''
    return str(s).translate(_LIKE_ESCAPE_CHARS)


class CountUpdate:
    def __init__(self):
        self.ls_tool = ListTool
        self.now_date = datetime.date.today()
        # REV30-H2: 转义 LIKE 通配符, 避免匹配意外行为 (同 REV28-H4)
        self._safe_date = _escape_like(self.now_date)
        self.query_user_count = t_login_log.query.filter(
            t_login_log.log_time.like("%{}%".format(self._safe_date), escape='\\')).filter_by(log_status='成功').with_entities(
            t_login_log.log_name).distinct().count()
        self.query_login_count = t_login_log.query.filter(
            t_login_log.log_time.like("%{}%".format(self._safe_date), escape='\\')).filter_by(log_status='成功').count()
        self.query_logerr_count = t_login_log.query.filter(
            t_login_log.log_time.like("%{}%".format(self._safe_date), escape='\\')).filter_by(log_status='失败').count()
        self.query_msg = t_line_chart.query.filter_by(chart_date=self.now_date).first()

    def count_into_all(self):
        """插入今日图表记录（无返回值，供 count_update_all 调用）"""
        if self.query_msg is None:
            osql_in('t_line_chart', login_count=self.query_login_count, user_count=self.query_user_count,
                    logerr_count=self.query_logerr_count,
                    chart_date=self.now_date)

    @property
    def count_update_all(self):
        try:
            if self.query_msg is None:
                self.count_into_all()
            else:
                osql_up('t_line_chart', {'chart_date': self.now_date},
                        {'login_count': self.query_login_count, 'user_count': self.query_user_count,
                         'logerr_count': self.query_logerr_count,
                         'chart_date': self.now_date})
            return jsonify({'code': 0})
        except (SqlOpError, IOError, TypeError) as e:
            return jsonify({'code': 2, 'msg': f'服务器内部错误: {type(e).__name__}'})


class CountList:
    def __init__(self):
        self.lt = ListTool

    @property
    def server_count_all(self):
        try:
            host_len_msg = t_host.query.filter_by(is_deleted=False).count()
            user_len_msg = t_acc_user.query.filter_by(is_deleted=False).count()
            group_len_msg = t_group.query.filter_by(is_deleted=False).count()
            return jsonify({
                'code': 0,
                'host_len': host_len_msg,
                'user_len': user_len_msg,
                'group_len': group_len_msg
            })
        except IOError:
            return jsonify({'code': 100, 'msg': '服务器内部错误'})

    @property
    def server_chart_count_all(self):
        try:
            login_list = []
            logerr_list = []
            user_list = []
            date_list = []
            # REV30-L4: 删除反向变量名 new_date (days=-5 实际是未来), 改用正向 timedelta
            start_date = (datetime.date.today() - datetime.timedelta(days=15)).strftime("%Y-%m-%d")
            now_date = datetime.date.today()
            query_msg_all = t_line_chart.query.filter(t_line_chart.chart_date <= now_date).filter(
                t_line_chart.chart_date >= start_date).all()
            for i in query_msg_all:
                # REV30-L7: 用显式字段访问代替 i.__dict__, 避免暴露 _sa_instance_state 等内部字段
                date_list.append(str(i.chart_date))
                login_list.append(i.login_count)
                logerr_list.append(i.logerr_count)
                user_list.append(i.user_count)
            return jsonify({'code': 0, 'date_msg': date_list, 'login_msg': login_list, 'logerr_msg': logerr_list, 'user_msg': user_list})
        except IOError:
            jsonify({'code': 100, 'msg': '服务器内部错误'})


class DataList:
    def __init__(self):
        self.lt = ListTool

    def get_list(self):
        # que_group = Host.query.with_entities(Host.group).all()
        que_group = t_group.query.with_entities(t_group.name).all()
        host_group = self.lt.list_rep_gather(que_group)
        res_group = auth_list_get()
        msg_list = []
        # REV30-L6: 移除死代码注释 # host_count = 100
        # REV30-L5: 移除假主键 group_count = 1000, 改从数据库查真实 id
        # REV30-L5: 批量查所有组的 host (一次 SQL), 按 group 分组填回 (消除 N+1)
        #   原: for i in res_group: t_host.query.filter_by(group=i).all()  -> N 次 SQL
        #   修: t_host.query.filter(t_host.group.in_(res_group)).all()  -> 1 次 SQL
        if res_group:
            all_hosts = t_host.query.filter(t_host.group.in_(res_group)).with_entities(
                t_host.id, t_host.alias, t_host.group).all()
            hosts_by_group = {}
            for hid, halias, hgroup in all_hosts:
                hosts_by_group.setdefault(hgroup, []).append({'title': halias, 'id': hid})
            group_id_map = {g.id: g.name for g in t_group.query.with_entities(t_group.id, t_group.name).all()
                            if g.name in res_group}
            for i in res_group:
                body_list = hosts_by_group.get(i, [])
                dic = {'title': i, 'id': group_id_map.get(i, 0), 'children': body_list}
                msg_list.append(dic)
        return jsonify({"code": 0, "host": [{'title': '所有资产组', 'id': 0, 'spread': 'true', 'children': msg_list}]})


class DataSumAll:
    def __init__(self):
        self.lt = ListTool
        self.sum_name = request_param('sum_name')

    def get_sum(self):
        if self.sum_name == 'group':
            try:
                query_group = t_group.query.with_entities(t_group.name).all()
                # REV30-H1: 跟踪是否有 group 被更新, 循环结束后统一 return
                updated = False
                if query_group:
                    group_list = self.lt.list_rep_gather(query_group)
                    for i in group_list:
                        group_count = t_host.query.filter_by(group=i).count()
                        # REVIEW-10-P2-4: 走统一封装,自动 commit + SqlOpError
                        osql_up('t_group', {'name': i}, {'nums': group_count})
                        # REV30-H1: 不在 for 内部 return, 让所有 group 都更新
                        updated = True
                # REV30-H1: 循环结束后统一返回, 包含 updated 标记
                return jsonify({'update_table_sum': 'true' if updated else 'empty', 'updated': updated})
            except SqlOpError:
                return jsonify({'update_table_sum': 'fail'})


class GetUserImage:
    def __init__(self):
        # self.path = '/data/putfile/'
        self.path = FILE_CONF['image_path']
        self.default_img = 'juzi11.png'

    def get_img(self, img_name):
        # REV16 B9 HIGH-2: img_name 白名单 + realpath 越界检测
        #   原：self.path + img_name + '.png' 字符串拼接，img_name 来自 URL path 无校验
        #   攻击：img_name='../../etc' → /data/avatars/../../etc.png → 任意 .png 探测
        #   修复：白名单 [A-Za-z0-9_.\-]{1,32} + realpath 越界检测
        # REV39-L1: 注释升级 + 显式 32 长度常量复用
        #   - URL 段已用 <string:img_name> 显式声明（init.py:370）
        #   - local_image_get 已 basename 二次校验
        #   - 此处 regex 是最后一道防线 + realpath 越界是兜底
        if not isinstance(img_name, str) or not re.fullmatch(r'^[A-Za-z0-9_.\-]{1,32}$', img_name):
            img_name = 'default'
        real_target = os.path.realpath(self.path + img_name + '.png')
        real_root = os.path.realpath(self.path)
        if os.path.commonpath([real_target, real_root]) != real_root:
            return jsonify({'image': 'path traversal blocked'})
        # REV30-L8: 删除未使用的死变量 request_begin_time
        try:
            if os.path.isfile(real_target):
                # REV30-M10: 用 with open() 自动关闭文件句柄
                with open(real_target, 'rb') as f:
                    image_data = f.read()
            else:
                default_target = os.path.realpath(self.path + self.default_img)
                if os.path.commonpath([default_target, real_root]) != real_root:
                    return jsonify({'image': 'error not file'})
                # REV30-M10: 用 with open() 自动关闭文件句柄
                with open(default_target, 'rb') as f:
                    image_data = f.read()
            response = make_response(image_data)
            response.headers['Content-Type'] = 'image/png'
            return response
        except FileNotFoundError:
            return jsonify({'image': 'error not file'})


class PutUserImage:
    def __init__(self):
        # self.path = '/data/putfile/'
        self.path = FILE_CONF['image_path']
        self.img_file = request.files.get('file')
        self.img_user = request_param('user')

    def put_img(self):
        # REV16 B7 HIGH-3: img_user 白名单 + realpath 越界检测
        #   原：self.path + self.img_user + '.png' 任意文件覆盖
        #   攻击：img_user='../../etc' → /data/avatars/../../etc.png → 任意 .png 覆盖
        #   修复：白名单 [A-Za-z0-9_.\-]{1,32} + realpath 越界检测
        if not isinstance(self.img_user, str) or not re.fullmatch(r'^[A-Za-z0-9_.\-]{1,32}$', self.img_user):
            return jsonify({'status': 'fail', 'msg': 'invalid user name'})
        real_target = os.path.realpath(self.path + self.img_user + '.png')
        real_root = os.path.realpath(self.path)
        if os.path.commonpath([real_target, real_root]) != real_root:
            return jsonify({'status': 'fail', 'msg': 'path traversal blocked'})
        # REV30-L9: 加固上传 - 大小限制 + MIME 验证 + Image.verify
        #   原: Image.open 直接读, 可能接受 SVG/XML (注入风险) 或超大文件 (DoS)
        #   修复: 限制 5MB + Image.verify() + try/except UnidentifiedImageError
        if self.img_file is None:
            return jsonify({'status': 'fail', 'msg': 'no file uploaded'})
        # 检查 Content-Length (如果代理提供)
        try:
            self.img_file.seek(0, os.SEEK_END)
            size = self.img_file.tell()
            self.img_file.seek(0)
            if size > _MAX_UPLOAD_IMG_SIZE:
                return jsonify({'status': 'fail', 'msg': 'file too large (max %d bytes)' % _MAX_UPLOAD_IMG_SIZE})
        except Exception:
            pass
        try:
            im = Image.open(self.img_file)
            # REV30-L9: Image.verify() 快速校验是否为合法图片 + 阻止非图片格式
            im.verify()
            # 重新打开 (verify 会破坏文件指针, 需重开才能 save)
            self.img_file.seek(0)
            im = Image.open(self.img_file)
            # REV30-L9: 限定格式为常见位图 (PNG / JPEG / GIF / WEBP), 阻止 SVG / TIFF / PDF
            if im.format not in _ALLOWED_IMG_FORMATS:
                return jsonify({'status': 'fail', 'msg': 'unsupported image format: %s' % im.format})
            im.save(real_target)
            return jsonify({'status': 'true'})
        except Image.UnidentifiedImageError:
            return jsonify({'status': 'fail', 'msg': 'not a valid image'})
        except Exception:
            return jsonify({'status': 'fail', 'msg': 'save error'})
