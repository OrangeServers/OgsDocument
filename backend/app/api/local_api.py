import os
from typing import Any
from flask import jsonify, Response
from app.local.Basics import DataList, DataSumAll, CountList, CountUpdate, GetUserImage, PutUserImage
from app.local.LocalShell import LocalDirList, LocalFilePut
from app.core.config import DEFAULT_DIR1_PATH, DEFAULT_DIR2_PATH, RSYNC_SHELL_CMD, DEFAULT_DATA_DIR
from app.local.LocalInit import AppInit, is_init_phase_open
from app.local.Captcha import CaptchaGet
from app.ssh.webssh import OgsWebSocket
from app.local.Settings import OgsSettings
from app.local.MailSettings import MailSettings
from app.local.download import DownloadFile
from app.files.file import FileGet
from app.users.user import CheckMail
from app.mail.MailApi import OrangeMailApi
from app.cron.cron import OgsCron, CronList
from app.audit.loginlogs import LoginIpTop
# REV38-M6: 统一 API 响应格式
from app.tools.apierr import api_error, api_response, ApiCode
from app.tools.at import Log
from app.tools.at import ogs_auth_token, ws_auth
from app.api import route  # REV38-M1: 统一 ROUTES schema
from app.core.types import JsonOrResponse  # ti3-HINT: 公共返回类型


# ---- 可自动注册的常规路由 ----
ROUTES = [
    # ---- 初始化状态 ----
    route('/local/app_auth_ck', AppInit, 'app_auth_status',
          need_auth=False, is_property=False,
          description='应用初始化状态检查', skip_csrf=True),

    # ---- 图形验证码（匿名、未鉴权）----
    # REV38-M10: captcha 接口加 IP rate limit（30次/分钟）
    route('/local/captcha/get', CaptchaGet, 'get',
          need_auth=False, is_property=False,
          description='获取图形验证码（IP 限流 30次/分钟）', skip_csrf=True),

    # ---- 统计图表 ----
    route('/server/count_list_all', CountList, 'server_count_all',
          description='各资源统计计数（主机/用户/cron 等）'),
    route('/local/chart/count', CountList, 'server_chart_count_all',
          description='图表聚合数据'),
    route('/local/chart/update', CountUpdate, 'count_update_all',
          is_property=True,
          description='刷新图表缓存'),

    # ---- 数据概览 ----
    route('/local/data', DataList, 'get_list',
          is_property=False,
          description='首页数据概览列表'),
    route('/local/sum', DataSumAll, 'get_sum',
          is_property=False,
          description='首页数据汇总'),

    # ---- 图片 ----
    # REV34-M10: 保留 /local/image/test_put 作为旧 alias，新增 /local/image/upload 正式 endpoint
    # REV38-M4: alias 路由显式标记 is_alias=True (抑制启动时重复注册 WARNING)
    route('/local/image/test_put', PutUserImage, 'put_img',
          is_property=False,
          is_alias=True,
          description='上传用户图片（旧 alias，保留兼容）'),
    route('/local/image/upload', PutUserImage, 'put_img',
          is_property=False,
          description='上传用户图片（正式 endpoint）'),

    # ---- 设置（admin 管理，开放注册状态所有用户可见）----
    route('/local/settings/open', OgsSettings, 'settings_open_info',
          need_auth=False, is_property=False,
          description='公开的系统设置（注册状态/系统名称/公告）', skip_csrf=True),
    route('/local/settings/get', OgsSettings, 'settings_info',
          is_property=False,
          description='完整系统设置'),
    route('/local/settings/update', OgsSettings, 'settings_change',
          is_property=False, roles=['admin'],
          description='更新系统设置'),
    route('/local/settings/mail/get', MailSettings, 'settings_get',
          is_property=False, roles=['admin'],
          description='读取 SMTP 设置（不返回授权码）'),
    route('/local/settings/mail/update', MailSettings, 'settings_update',
          is_property=False, roles=['admin'],
          description='保存 SMTP 设置（授权码加密）'),
    route('/local/settings/mail/test', MailSettings, 'settings_test',
          is_property=False, roles=['admin'],
          description='测试 SMTP 连接或发送测试邮件'),

    # ---- 文件管理 ----
    route('/local/file/download', DownloadFile, 'download',
          is_property=False,
          description='文件下载（按权限过滤）'),
    # REV38-M5: /local/file/def_get → /local/file/list 重命名
    # REV38-M4: alias 路由显式标记 is_alias=True (抑制启动时重复注册 WARNING)
    route('/local/file/def_get', FileGet, 'get_file_list',
          is_property=False,
          is_alias=True,
          description='文件列表（旧 alias，保留兼容，建议改用 /local/file/list）'),
    route('/local/file/list', FileGet, 'get_file_list',
          is_property=False,
          description='文件列表（正式 endpoint）'),
    route('/local/file/add', FileGet, 'mkdir_file_name',
          is_property=False,
          description='创建目录'),
    route('/local/file/del', FileGet, 'remove_file',
          is_property=False,
          description='删除文件/目录'),
    # REV37-H2: 文件上传路径校验 + MIME 嗅探
    route('/local/file/put', FileGet, 'save_file',
          is_property=False,
          description='上传文件到本地 data 目录（路径校验 + MIME 嗅探，与 /server/file/put 区分，REV38-M12）'),
    route('/local/file/rename', FileGet, 'change_file_name',
          is_property=False,
          description='重命名文件/目录'),
    route('/local/file/size', FileGet, 'get_file_size',
          is_property=False,
          description='获取文件/目录大小'),

    # ---- 邮件（注册验证码不需鉴权）----
    route('/mail/send_user_mail', CheckMail, 'send',
          need_auth=False, is_property=False,
          description='发送注册验证码邮件', skip_csrf=True),
    # REVIEW-13 P0-2: 邮件中继接口必须登录态 (前端不调用, 仅留作后端使用)
    #   原 csrf=False role=False → 任何匿名访客可任意发邮件 → SMTP 服务商封号
    route('/mail/send_mail', OrangeMailApi, 'send',
          is_property=False,
          description='邮件中继发送（必须登录态）'),

    # ---- 定时任务 ----
    route('/local/cron/list', CronList, 'cron_list',
          description='当前用户可见的 cron 列表'),
    # REVIEW-5-C: cron_auth_list 查的是当前用户权限，admin 才能下放 cron，
    #  普通用户暴露这个端点没意义（前端 cron 页面仅 admin 可进）
    route('/local/cron/auth_list', CronList, 'cron_auth_list',
          roles=['admin'],
          description='可授权的 cron 列表'),
    route('/local/cron/list_all', CronList, 'cron_list_all',
          description='全部 cron 列表（含禁用）'),
    route('/local/cron/add', OgsCron, 'add_job',
          is_property=False,
          description='新增定时任务'),
    route('/local/cron/pause', OgsCron, 'pause_job',
          is_property=False,
          description='暂停定时任务'),
    route('/local/cron/resume', OgsCron, 'resume_job',
          is_property=False,
          description='恢复定时任务'),
    route('/local/cron/del', OgsCron, 'remove_job',
          is_property=False,
          description='删除定时任务'),
    route('/local/cron/run', OgsCron, 'run_job',
          is_property=False,
          description='立即执行一次'),
    route('/local/cron/last_result', OgsCron, 'last_result',
          is_property=False,
          description='最近一次执行结果'),
    route('/local/cron/com_list', OgsCron, 'com_list_job',
          is_property=False,
          description='任务执行完成列表'),
    # REVIEW-5-C: close_job 关闭全站所有 cron，必须仅 admin
    route('/local/cron/close', OgsCron, 'close_job',
          is_property=False, roles=['admin'],
          description='关闭全站所有 cron'),

    # ---- 登录 IP 统计 ----
    # REV34-M12: 登录 IP Top N 聚合（Dashboard loginTop 专用）
    route('/local/log/login/ip_top', LoginIpTop, 'get_ip_top',
          is_property=False,
          description='登录 IP Top N 聚合'),
]


# ---- 特殊路由：需要传参 / WebSocket / 带URL参数，保留手动注册 ----

def local_app_init() -> None:
    """启动时初始化，非路由。
    REV38-M3: 启动完成后标记 init_phase 关闭, 关闭 /local/init alias 运行时访问。
    """
    orange = AppInit()
    orange.con_init()
    # 启动 helper 完成后, 标记启动阶段结束
    from app.local.LocalInit import end_init_phase
    end_init_phase()


def local_app_status() -> JsonOrResponse:
    """REV38-M3: 正式 endpoint /local/status 的视图函数。
    任何登录态可调用, 不受启动阶段限制。
    """
    orange = AppInit()
    return orange.app_status()


def local_app_status_alias() -> JsonOrResponse:
    """REV38-M3: /local/init alias 视图函数。
    启动阶段 (_INIT_PHASE_OPEN=True) 透传到 app_status;
    运行时 (_INIT_PHASE_OPEN=False) 返 410 Gone, 提示前端改用 /local/status。
    """
    if not is_init_phase_open():
        return jsonify({
            'status': 410,
            'msg': 'gone, use /local/status',
            'rev': 'REV38-M3',
        }), 410
    return local_app_status()


def local_chart_into() -> Any:
    """启动时初始化图表，非路由"""
    orange = CountUpdate()
    return orange.count_into_all


@ogs_auth_token
def local_dir_group() -> JsonOrResponse:
    """REV38-M11: 改用 os.listdir(OGS_DATA_DIR) 替代 cmdlist_shell('ls /data').

    收益:
      - 消除 shell 命令路径 (即使 DEFAULT_DIR1_PATH 被污染也不会 RCE)
      - 自动限定在 DEFAULT_DATA_DIR 下, 不依赖 shell 'ls' 行为
      - 跨平台 (Windows / Linux 都可读)
    """
    try:
        data_dir = os.path.realpath(DEFAULT_DATA_DIR)
        if not os.path.isdir(data_dir):
            return jsonify({
                'code': ApiCode.DIR_NOT_FOUND,
                'msg': 'data dir not found: %s' % DEFAULT_DATA_DIR,
                'group_dir_msg': [],
            })
        entries = os.listdir(data_dir)
        # 排序 + 过滤隐藏文件
        entries = sorted([e for e in entries if not e.startswith('.')])
        return jsonify({'code': 0, 'group_dir_msg': entries})
    except Exception as e:
        Log.logger.warning('local_dir_group failed: %s' % e)
        return jsonify({
            'code': ApiCode.DIR_NOT_FOUND,
            'msg': 'list dir failed: %s' % str(e),
            'group_dir_msg': [],
        })


@ogs_auth_token
def local_dir_project() -> JsonOrResponse:
    orange = LocalDirList(DEFAULT_DIR1_PATH, DEFAULT_DIR2_PATH)
    return orange.getdir1()


@ogs_auth_token
def local_rsync_code() -> JsonOrResponse:
    orange = LocalDirList(DEFAULT_DIR1_PATH, DEFAULT_DIR2_PATH, RSYNC_SHELL_CMD)
    return orange.getdir2()


@ogs_auth_token
def local_data_file_put() -> JsonOrResponse:
    orange = LocalFilePut()
    return orange.put_file()


# REV39-L1: img_name 路径遍历防护
#   - init.py 注册时显式 <string:img_name>，URL 段不含 '/'
#   - 这里做 basename 二次校验，兜底 Werkzeug 解析边界 case
#   - 真校验在 GetUserImage.get_img 内 (regex 白名单 + realpath 越界)
_MAX_IMG_NAME_LEN = 32  # 与 GetUserImage regex 保持一致


@ogs_auth_token
def local_image_get(img_name: str) -> JsonOrResponse:
    if not isinstance(img_name, str) or os.path.basename(img_name) != img_name \
            or len(img_name) > _MAX_IMG_NAME_LEN:
        img_name = 'default'
    orange = GetUserImage()
    return orange.get_img(img_name)


# REVIEW-5-B: WebSocket 路由必须先过 ws_auth（拒绝升级握手用 401）
#   不走 csrf_protect：升级请求是 GET，csrf 在 GET 天然豁免
@ws_auth
def local_web_ssh() -> JsonOrResponse:
    orange = OgsWebSocket()
    return orange.web_ssh()


# REV39-L8: SFTP WebSocket 同样走 ws_auth 装饰器，自动继承 session 续期
#   - REV38-M2 在 at.ws_auth 内部已实现：握手通过后立即续期一次 + 启动后台 greenlet 定期续期
#   - SFTP / SSH 共用同一个装饰器，不需重复实现续期逻辑
#   - 长连接期间 token TTL 续期由 _ws_session_renew_loop 负责
#   - token 失效时主动 close WS (1008=policy violation)
@ws_auth
def local_sftp_connect() -> JsonOrResponse:
    from app.ssh.sftp import OgsSftpWebSocket
    orange = OgsSftpWebSocket()
    return orange.sftp_connect()
