import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from flask import request, jsonify
from app.cron.CronSettings import scheduler, app
from app.core.db.database import t_host, t_auth_host, t_sys_user, t_acc_user, t_cron, t_cron_host, t_cron_group, \
    t_auth_host_user, t_auth_host_user_group, t_auth_host_host_group, db
# REV38-M6: 统一 API 响应格式, 替换散落 jsonify({'code': ...})
from app.tools.apierr import api_error, api_response, ApiCode
from app.core.db.insert import osql_in
from app.tools.shellcmd import get_ssh_connection
from app.tools.SqlListTool import ListTool
from app.tools.redisdb import ConnRedis
from app.tools.audlog import log_ssh_audit  # REV46-M26: 写 t_command_log 审计
from app.tools.at import Log, get_current_user, get_current_user_role, request_param, request_param_list
from app.core.config import CRON_RESULT_RETENTION


# 每条主机输出的最大字符数，超出截断并追加提示
_MAX_OUTPUT_LEN = 4096
_TRUNCATED_SUFFIX = '\n... (输出过长，已截断)'

# REVIEW-5-F-5: 去除控制字符 (XSS 防御), 保留 \t \n \r (分别为 \x09 \x0a \x0d)
_ANSI_CTRL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')

# REVIEW-5-F-3: cron add_job Redis 分布式锁 TTL
ADD_JOB_LOCK_TTL = 5  # 秒


def _save_cron_result(job_name, result_list):
    """将定时任务最新执行结果存入 Redis（只保留最新一次），output 超长截断。
    REVIEW-5-E-1: 加 TTL 防止永久膨胀 + 敏感命令输出残留。
    REVIEW-5-F-5: 去控制字符 (XSS 防御)，防前端 v-html 渲染。
    """
    try:
        rds = ConnRedis()
        key = 'cron_last_result:%s' % job_name
        truncated = []
        for r in result_list:
            item = dict(r)
            out = item.get('output', '')
            # REVIEW-5-F-5: 去控制字符 (\x00-\x08, \x0b-\x1f, \x7f)，保留 \t\n\r
            if isinstance(out, str):
                out = _ANSI_CTRL_RE.sub('', out)
            item['output'] = out
            if len(out) > _MAX_OUTPUT_LEN:
                item['output'] = out[:_MAX_OUTPUT_LEN] + _TRUNCATED_SUFFIX
            truncated.append(item)
        data = {'results': truncated, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        # 7 天后自动过期，活跃 cron 每次执行都会重写
        rds.conn.set(key, json.dumps(data, ensure_ascii=False), ex=CRON_RESULT_RETENTION)
    except Exception as e:
        Log.logger.warning('_save_cron_result: failed for %s: %s' % (job_name, e))


def _get_cron_result(job_name: str) -> Optional[Any]:
    """从 Redis 读取定时任务最新执行结果"""
    try:
        rds = ConnRedis()
        key = 'cron_last_result:%s' % job_name
        raw: Any = rds.conn.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        Log.logger.warning('_get_cron_result: failed for %s: %s' % (job_name, e))
    return None


# REVIEW-5-D-2: cron owner 校验辅助函数
#   规则:
#     - admin 角色 -> 可操作任何 cron (包括旧 job_owner='system' 的遗袇据)
#     - 非 admin -> 仅可操作 job_owner == current_user 的 cron
#   旧数据 job_owner='system' 代表“创建于未加 owner 字段时”，无真实 owner，
#   严格遵守 “仅 admin 可碰”以避免遗留越权
def _current_user_info():
    """获取当前登录用户 (username, role)，未登录返 (None, None)"""
    ords, name = get_current_user()
    if not name:
        return None, None
    role = get_current_user_role()
    return name, role


def _can_operate_cron(task, current_user, current_role):
    """检查 current_user 是否有权操作 task.
    返回 (True, None) 或 (False, error_msg)."""
    if not current_user:
        return False, '未登录'
    if current_role == 'admin':
        return True, None
    if not task:
        return False, '任务不存在'
    if getattr(task, 'job_owner', None) == current_user:
        return True, None
    # 旧任务 (owner='system') 或其他用户的任务 -> 拒绝
    return False, '权限不足: 仅任务所有者或管理员可操作'

scheduler.start()

# 主机健康检查定时任务：每 60 秒 TCP 探测所有主机的 SSH 端口
from app.assets.ServerManagement import check_all_hosts_health
scheduler.add_job(
    check_all_hosts_health,
    'interval',
    seconds=60,
    id='host_health_check',
    name='主机在线状态检测',
    replace_existing=True,
    max_instances=1,
)
# 启动时立即执行一次
check_all_hosts_health()


def _resolve_host_ids(cron_id):
    """根据 cron_id 关联的资产组和指定资产，解析出最终去重的主机 ID 列表"""
    lt = ListTool
    id_list = []
    id_list2 = []
    # 按资产组解析主机 ID
    group_rows = t_cron_group.query.filter_by(cron_id=cron_id).all()
    for gr in group_rows:
        host_list = lt.list_gather(
            t_host.query.filter_by(group=gr.group_name, is_deleted=False).with_entities(t_host.id).all())
        id_list.append(host_list)
    # 按指定资产补充主机 ID
    host_rows = t_cron_host.query.filter_by(cron_id=cron_id).all()
    for hr in host_rows:
        host_row = t_host.query.filter_by(alias=hr.host_alias, is_deleted=False).with_entities(t_host.id).first()
        if host_row:
            id_list2.append(host_row)
    return list(set(lt.list_gather(id_list) + lt.list_gather(id_list2)))


def cron_list_cmd(job_name, job_sys_user, host_id: list, command: str):
    """APScheduler 回调：在应用上下文中对目标主机执行命令"""
    with app.app_context():
        result_list = []
        for hid in host_id:
            host = t_host.query.filter_by(id=hid, is_deleted=False).first()
            if not host:
                result_list.append({'host': 'id=%s' % hid, 'output': '', 'error': True, 'msg': '主机不存在'})
                continue
            conn = None
            try:
                conn = get_ssh_connection(job_sys_user, host.host_ip, host.host_port)
                try:  # REV46-M20: 显式管理连接生命周期
                    # REV46-M26: audit_callback 写 t_command_log
                    msg = conn.ssh_cmd(command, audit_callback=log_ssh_audit)
                    result_list.append({'host': host.alias or host.host_ip, 'output': msg or '', 'error': False})
                finally:
                    conn.close()
            except Exception as e:
                result_list.append({'host': host.alias or host.host_ip, 'output': str(e), 'error': True, 'msg': '连接失败'})
                Log.logger.warning('job %s host %s exec failed: %s' % (job_name, host.alias, e))
        # 存最新执行结果到 Redis
        _save_cron_result(job_name, result_list)
        error_list = [r['host'] for r in result_list if r['error']]
        alias_list = [r['host'] for r in result_list if not r['error']]
        if len(error_list) == 0:
            Log.logger.info('job %s cron run.... [ ok_ip=%s ]' % (job_name, alias_list))
        else:
            Log.logger.info('job %s cron run.... [ err_ip=%s ok_ip=%s ]' % (job_name, error_list, alias_list))


def load_cron_from_db():
    """应用启动时从 t_cron 表恢复所有 '启动' 状态的任务"""
    with app.app_context():
        tasks = t_cron.query.filter_by(job_status='启动', is_deleted=False).all()
        for task in tasks:
            all_ids = _resolve_host_ids(task.id)
            if not all_ids:
                Log.logger.warning('load_cron_from_db: task %s has no valid hosts, skipped' % task.job_name)
                continue
            try:
                scheduler.add_job(cron_list_cmd, 'cron',
                                  week=task.job_week, month=task.job_month, day=task.job_day,
                                  hour=task.job_hour, minute=task.job_minute,
                                  args=[task.job_name, task.job_sys_user, all_ids, task.job_command],
                                  id=task.job_name)
                Log.logger.info('load_cron_from_db: restored task %s' % task.job_name)
            except Exception as e:
                Log.logger.warning('load_cron_from_db: failed to restore task %s: %s' % (task.job_name, e))

# 启动时自动创建新增的关联表（已存在的表不会被修改）
with app.app_context():
    db.create_all()

load_cron_from_db()


class OgsCron:
    def __init__(self):
        self.job_name = request_param('job_name', default=None)
        self.lt = ListTool

    # 动态添加定时任务
    def add_job(self):
        job_minute = request_param('job_minute', default="*")
        job_hour = request_param('job_hour', default="*")
        job_day = request_param('job_day', default="*")
        job_month = request_param('job_month', default="*")
        job_week = request_param('job_week', default="*")
        job_hosts = request_param_list('job_hosts')  # 数组：['yw199', 'yw200']
        job_groups = request_param_list('job_groups')  # 数组：['group1', 'group2']
        job_sys_user = request_param('job_sys_user')
        job_command = request_param('job_command')
        job_remarks = request_param('job_remarks', default=None)
        # REVIEW-5-D-2: 记录当前用户为 owner
        current_user, _ = _current_user_info()
        # REVIEW-5-F-3: 同名并发 add_job 用 Redis 分布式锁串行化
        rds = None
        lock_key = 'lock:job_name:%s' % self.job_name
        try:
            rds = ConnRedis()
            # SET key value EX ttl NX 原子操作，nx=True 仅在 key 不存在时设成功
            acquired = rds.conn.set(lock_key, '1', ex=ADD_JOB_LOCK_TTL, nx=True)
            if not acquired:
                Log.logger.warning('add_job lock busy: job_name=%s user=%s', self.job_name, current_user)
                # REV38-M6: 改用 api_error (http 429 = 请稍后重试)
                return api_error(ApiCode.CRON_LOCK_BUSY, '同名任务正在被其他请求处理，请稍后重试')
        except Exception as e:
            # 锁获取失败不阻止业务，仅退化到无锁 (会可能重现 race 但优于完全不可用)
            Log.logger.warning('add_job lock acquire failed (degraded): %s', e)
        try:
            job_name_query = t_cron.query.filter_by(
                job_name=self.job_name).first()
            if job_name_query is not None and not job_name_query.is_deleted:
                # REV30-M2: 原 msg='任务不存在' 反义, 实际是任务已存在
                return api_error(ApiCode.CRON_EXISTS, '任务已存在')

            if job_name_query is None:
                new_cron = t_cron(
                    job_name=self.job_name, job_minute=job_minute, job_hour=job_hour,
                    job_day=job_day, job_month=job_month, job_week=job_week,
                    job_sys_user=job_sys_user, job_command=job_command,
                    job_status='启动', job_remarks=job_remarks,
                    job_owner=current_user or 'system')
                db.session.add(new_cron)
                db.session.flush()  # 拿到 new_cron.id
            else:
                # CRON-SOFT-DELETE-REUSE: job_name 有唯一索引。删除后同名
                # 新建必须复用软删行，并清掉上一次遗留的目标关联。
                new_cron = job_name_query
                new_cron.job_minute = job_minute
                new_cron.job_hour = job_hour
                new_cron.job_day = job_day
                new_cron.job_month = job_month
                new_cron.job_week = job_week
                new_cron.job_sys_user = job_sys_user
                new_cron.job_command = job_command
                new_cron.job_status = '启动'
                new_cron.job_remarks = job_remarks
                new_cron.job_owner = current_user or 'system'
                new_cron.is_deleted = False
                t_cron_host.query.filter_by(cron_id=new_cron.id).delete()
                t_cron_group.query.filter_by(cron_id=new_cron.id).delete()

            for alias in job_hosts:
                if alias:
                    db.session.add(
                        t_cron_host(cron_id=new_cron.id, host_alias=alias))
            for gname in job_groups:
                if gname:
                    db.session.add(
                        t_cron_group(cron_id=new_cron.id, group_name=gname))
            db.session.commit()
            all_ids = _resolve_host_ids(new_cron.id)
            if not all_ids:
                return api_error(
                    ApiCode.CRON_NO_TARGET_HOSTS, '未找到任何目标主机')
            scheduler.add_job(
                cron_list_cmd, 'cron',
                week=job_week, month=job_month, day=job_day,
                hour=job_hour, minute=job_minute,
                args=[
                    self.job_name, job_sys_user, all_ids, job_command,
                ],
                id=self.job_name,
            )
            return api_response(data=None, code=ApiCode.OK, msg='ok')
        except IOError:
            # REV38-M6
            return api_error(ApiCode.CRON_INNER_ERROR, '服务器内部错误')
        except Exception:
            # REV38-M6
            return api_error(ApiCode.CRON_OPERATION_FAILED, '操作失败 (code=2)')
        finally:
            # REVIEW-5-F-3: 释放分布式锁 (仅当锁是我们加的；锁 TTL 5s 也会自动过期)
            if rds is not None:
                try:
                    rds.conn.delete(lock_key)
                except Exception:
                    pass

    # 手动执行定时任务（立即运行，返回执行结果）
    def run_job(self, job_name=None):
        if job_name is None:
            job_name = self.job_name
        try:
            task = t_cron.query.filter_by(job_name=job_name, is_deleted=False).first()
            if not task:
                # REV38-M6
                return api_error(ApiCode.CRON_NOT_FOUND, '任务不存在')
            # REVIEW-5-D-2: owner 校验（非 admin 仅能跑自己的）
            current_user, current_role = _current_user_info()
            allowed, err = _can_operate_cron(task, current_user, current_role)
            if not allowed:
                Log.logger.warning('run_job denied: user=%s role=%s try to run %s (owner=%s)',
                                   current_user, current_role, job_name, getattr(task, 'job_owner', None))
                # REV38-M6
                return api_error(ApiCode.BUSINESS_UNAUTHORIZED, err)
            all_ids = _resolve_host_ids(task.id)
            if not all_ids:
                # REV38-M6
                return api_error(ApiCode.CRON_NO_TARGET_HOSTS, '未找到任何目标主机')
            result_list = []
            for hid in all_ids:
                host = t_host.query.filter_by(id=hid, is_deleted=False).first()
                if not host:
                    # REV38-M6
                    result_list.append({'host': 'id=%s' % hid, 'output': '', 'error': True, 'msg': '主机不存在', 'code': ApiCode.HOST_NOT_FOUND})
                    continue
                conn = None
                try:
                    conn = get_ssh_connection(task.job_sys_user, host.host_ip, host.host_port)
                    try:  # REV46-M20: 显式管理连接生命周期
                        # REV46-M26: audit_callback 写 t_command_log
                        output = conn.ssh_cmd(task.job_command, audit_callback=log_ssh_audit)
                        result_list.append({'host': host.alias or host.host_ip, 'output': output or '', 'error': False})
                    finally:
                        conn.close()
                except Exception as e:
                    # REV38-M6
                    result_list.append({'host': host.alias or host.host_ip, 'output': str(e), 'error': True, 'msg': '连接失败', 'code': ApiCode.CRON_CONNECT_FAILED})
            # 存最新执行结果到 Redis
            _save_cron_result(job_name, result_list)
            # REV38-M6
            return api_response(data={'job_name': job_name, 'results': result_list},
                                code=ApiCode.OK, msg='ok')
        except Exception as e:
            # REV38-M6
            return api_error(ApiCode.CRON_OPERATION_FAILED, str(e))

    # 获取最新执行结果
    def last_result(self, job_name=None):
        if job_name is None:
            job_name = self.job_name
        data = _get_cron_result(job_name)
        if data:
            # REV38-M6
            return api_response(data={'job_name': job_name, 'results': data['results'], 'time': data['time']},
                                code=ApiCode.OK, msg='ok')
        # REV38-M6
        return api_error(ApiCode.CRON_NO_RESULT, '暂无执行记录')

    # 动态暂停定时任务
    def pause_job(self, job_name=None):
        try:
            if job_name is None:
                job_name = self.job_name
            # REVIEW-5-D-2: owner 校验
            task = t_cron.query.filter_by(job_name=job_name, is_deleted=False).first()
            if not task:
                # REV38-M6
                return api_error(ApiCode.CRON_NOT_FOUND, '任务不存在')
            current_user, current_role = _current_user_info()
            allowed, err = _can_operate_cron(task, current_user, current_role)
            if not allowed:
                Log.logger.warning('pause_job denied: user=%s role=%s try to pause %s (owner=%s)',
                                   current_user, current_role, job_name, getattr(task, 'job_owner', None))
                # REV38-M6
                return api_error(ApiCode.BUSINESS_UNAUTHORIZED, err)
            # 调度器中可能不存在该 job（已移除/未恢复），忽略异常继续更新数据库
            try:
                scheduler.pause_job(job_name)
            except Exception:
                Log.logger.warning('pause_job: job %s not in scheduler, skip scheduler pause' % job_name)
            t_cron.query.filter_by(job_name=job_name, is_deleted=False).update({'job_status': '暂停'})
            db.session.commit()
            return jsonify({'code': 0})
        except Exception:
            # REV30-L1: commit/操作失败 rollback, 避免脏 session 阻断后续操作
            try:
                db.session.rollback()
            except Exception:
                pass
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})

    # 动态恢复定时任务
    def resume_job(self, job_name=None):
        try:
            if job_name is None:
                job_name = self.job_name
            # REV30-L2: owner 校验 (与 pause/remove 一致)
            task = t_cron.query.filter_by(job_name=job_name, is_deleted=False).first()
            if not task:
                # REV30-L3: task 为 None 时直接返错, 不进入 scheduler 操作
                # REV38-M6
                return api_error(ApiCode.CRON_NOT_FOUND, '任务不存在')
            current_user, current_role = _current_user_info()
            allowed, err = _can_operate_cron(task, current_user, current_role)
            if not allowed:
                Log.logger.warning('resume_job denied: user=%s role=%s try to resume %s (owner=%s)',
                                   current_user, current_role, job_name, getattr(task, 'job_owner', None))
                # REV38-M6
                return api_error(ApiCode.BUSINESS_UNAUTHORIZED, err)
            # 检查调度器中是否存在该 job，不存在则重新注册
            existing = scheduler.get_job(job_name)
            if existing:
                scheduler.resume_job(job_name)
            else:
                # job 不在调度器中（可能因暂停后服务重启），需要重新注册
                all_ids = _resolve_host_ids(task.id)
                if all_ids:
                    scheduler.add_job(cron_list_cmd, 'cron',
                                      week=task.job_week, month=task.job_month, day=task.job_day,
                                      hour=task.job_hour, minute=task.job_minute,
                                      args=[task.job_name, task.job_sys_user, all_ids, task.job_command],
                                      id=task.job_name)
            t_cron.query.filter_by(job_name=job_name, is_deleted=False).update({'job_status': '启动'})
            db.session.commit()
            return jsonify({'code': 0})
        except Exception:
            # REV30-L1: commit/操作失败 rollback, 避免脏 session
            try:
                db.session.rollback()
            except Exception:
                pass
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})

    # 动态删除定时任务
    def remove_job(self, job_name=None):
        try:
            if job_name is None:
                job_name = self.job_name
            # REVIEW-5-D-2: owner 校验
            task = t_cron.query.filter_by(job_name=job_name, is_deleted=False).first()
            if not task:
                # REV38-M6
                return api_error(ApiCode.CRON_NOT_FOUND, '任务不存在')
            current_user, current_role = _current_user_info()
            allowed, err = _can_operate_cron(task, current_user, current_role)
            if not allowed:
                Log.logger.warning('remove_job denied: user=%s role=%s try to remove %s (owner=%s)',
                                   current_user, current_role, job_name, getattr(task, 'job_owner', None))
                # REV38-M6
                return api_error(ApiCode.BUSINESS_UNAUTHORIZED, err)
            # 调度器中可能不存在该 job（未启动/已移除），忽略异常继续删库
            try:
                scheduler.remove_job(job_name)
            except Exception:
                pass
            # REV47-M6: soft_delete - 标记 is_deleted=True 而非物理删除
            #   关联表 t_cron_host / t_cron_group 仍走 FK CASCADE 物理清理
            task.is_deleted = True
            db.session.commit()
            return jsonify({'code': 0})
        except Exception:
            # REV30-L1: commit/操作失败 rollback, 避免脏 session
            try:
                db.session.rollback()
            except Exception:
                pass
            return jsonify({'code': 100, 'msg': '操作失败 (code=2)'})

    def com_list_job(self):
        # REVIEW-5-D-2: 批量操作前先取当前用户, 逐个 cron 单独校验 owner
        current_user, current_role = _current_user_info()
        if not current_user:
            return jsonify({'code': 100, 'msg': '未登录'})
        job_name_list = request_param_list('job_name_list')
        job_type = request_param('job_type')
        if job_type not in ('del', 'pause', 'resume'):
            return jsonify({'code': 100, 'msg': '无效的操作类型'})
        success_list = []
        fail_list = []
        no_perm_list = []  # REVIEW-5-D-2: 区分“权限不足”与“其他错误”，前端可提示原因
        action_map = {'del': self.remove_job, 'pause': self.pause_job, 'resume': self.resume_job}
        action_fn = action_map[job_type]
        for name in job_name_list:
            # REVIEW-5-D-2: 先查 task 本身, 防止子函数 (remove/pause) 出错导致 no_perm 归类错误
            try:
                task = t_cron.query.filter_by(job_name=name, is_deleted=False).first()
                allowed, _ = _can_operate_cron(task, current_user, current_role)
                if not allowed:
                    no_perm_list.append(name)
                    continue
            except Exception:
                pass
            try:
                result = action_fn(name)
                result_data = result.get_json() if hasattr(result, 'get_json') else result
                # REV30-M5: 仅靠前置 _can_operate_cron 判定权限, action_fn 内部失败归 fail_list
                #   原: msg='权限不足' 归类为 no_perm_list, 但依赖 msg 字符串匹配, 文案变化即失效
                #   修: 只看 code, no_perm 完全由前置 _can_operate_cron 决定, action_fn 内部失败统一归 fail_list
                if isinstance(result_data, dict) and result_data.get('code') == 0:
                    success_list.append(name)
                else:
                    fail_list.append(name)
            except Exception:
                fail_list.append(name)
        if no_perm_list or fail_list:
            return jsonify({'code': 100, 'msg': '部分操作失败',
                            'success': success_list, 'fail': fail_list,
                            'no_perm': no_perm_list})
        return jsonify({'code': 0, 'success': success_list})

    # 关闭所有定时任务（保留调度器，仅暂停所有 job）
    @property
    def close_job(self):
        # REV30-M6: admin-only 操作 (避免任何登录用户暂停所有 cron)
        current_user, current_role = _current_user_info()
        if current_role != 'admin':
            Log.logger.warning('close_job denied: user=%s role=%s try to close all cron',
                               current_user, current_role)
            return jsonify({'code': 100, 'msg': '仅管理员可关闭所有定时任务'})
        try:
            for job in scheduler.get_jobs():
                job.pause()
            t_cron.query.update({'job_status': '暂停'})
            db.session.commit()
            return jsonify({'cron_shutdown_status': 'true'})
        except Exception:
            # REV30-L1: commit 失败 rollback, 避免脏 session
            try:
                db.session.rollback()
            except Exception:
                pass
            return jsonify({'cron_shutdown_status': 'fail'})


class CronList:
    def __init__(self):
        self.lt = ListTool
        self.ords = ConnRedis()
        # REV30-M1: 分页参数 try/except (同 REV25-M1 模式), 防 'abc' → ValueError → 500
        try:
            page = int(request_param('page', default=1))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = int(request_param('limit', default=10))
        except (TypeError, ValueError):
            limit = 10
        self.table_page = max(page, 1)
        self.table_limit = max(limit, 1)
        self.table_offset = (self.table_page - 1) * self.table_limit

    @property
    def cron_list(self):
        try:
            # REV16 B5 HIGH-1: owner 过滤——非 admin 只能查自己的 cron
            current_user, current_role = _current_user_info()
            if not current_user:
                # REV38-M6: cron_list 列表查询未登录
                return api_error(ApiCode.BUSINESS_UNAUTHORIZED, '未登录', cron_list_msg=[])
            # REVIEW-5-F-4: id 强转 int，防传非数字时 SQLAlchemy 抛 StatementError
            cron_id_raw = request_param("id")
            if cron_id_raw is None or cron_id_raw == '':
                # REV38-M6
                return api_error(ApiCode.TYPE_ERROR, 'missing id', cron_list_msg=[])
            try:
                cron_id = int(cron_id_raw)
            except (TypeError, ValueError):
                # REV38-M6
                return api_error(ApiCode.TYPE_ERROR, 'invalid id (not integer)', cron_list_msg=[])
            query_msg = t_cron.query.filter_by(id=cron_id, is_deleted=False).first()
            if query_msg is None:
                # REV38-M6: 任务不存在
                return api_error(ApiCode.CRON_NOT_FOUND, '任务不存在', cron_list_msg=[])
            # B5 HIGH-1: 非 admin 不能看别人的
            if current_role != 'admin' and getattr(query_msg, 'job_owner', None) != current_user:
                Log.logger.warning('cron_list denied: user=%s role=%s try to read cron id=%s owner=%s',
                                   current_user, current_role, cron_id, getattr(query_msg, 'job_owner', None))
                # REV38-M6
                return api_error(ApiCode.FORBIDDEN, '权限不足', cron_list_msg=[])
            list_msg = self.lt.dict_reset_pop_auto(query_msg)
            # 补充关联表数据为数组
            list_msg['job_hosts'] = [r.host_alias for r in t_cron_host.query.filter_by(cron_id=cron_id).all()]
            list_msg['job_groups'] = [r.group_name for r in t_cron_group.query.filter_by(cron_id=cron_id).all()]
            return jsonify(list_msg)
        except IOError:
            return jsonify({"cron_list_msg": 'select list msg error'})

    @property
    def cron_list_all(self):
        try:
            # REV16 B5 HIGH-1: owner 过滤——非 admin 只能看自己的
            current_user, current_role = _current_user_info()
            if not current_user:
                return jsonify({'code': 100, 'msg': '未登录'})
            q = t_cron.query.filter_by(is_deleted=False)
            if current_role != 'admin':
                q = q.filter_by(job_owner=current_user)
            query_msg = q.order_by(t_cron.id.desc()).offset(self.table_offset).limit(self.table_limit).all()
            list_msg = self.lt.dict_ls_reset_dict_auto(query_msg)
            # REV30-M3: 批量查关联表 (1+2 次 SQL), 替换原来的 N+1 (2N 次 SQL)
            #   原: 每页 N 条记录 -> 2N 次关联表查询
            #   修: 一次 in_(ids) 查 host, 一次 in_(ids) 查 group, dict 化后填回
            if list_msg:
                ids = [item['id'] for item in list_msg]
                hosts_rows = t_cron_host.query.filter(t_cron_host.cron_id.in_(ids)).all()
                groups_rows = t_cron_group.query.filter(t_cron_group.cron_id.in_(ids)).all()
                hosts_by_cid: Dict[int, List[str]] = {}
                for r in hosts_rows:
                    hosts_by_cid.setdefault(r.cron_id, []).append(r.host_alias)
                groups_by_cid: Dict[int, List[str]] = {}
                for r in groups_rows:
                    groups_by_cid.setdefault(r.cron_id, []).append(r.group_name)
                for item in list_msg:
                    cid = item['id']
                    item['job_hosts'] = hosts_by_cid.get(cid, [])
                    item['job_groups'] = groups_by_cid.get(cid, [])
            else:
                for item in list_msg:
                    item['job_hosts'] = []
                    item['job_groups'] = []
            # B5 H1: 总数应与过滤后一致（分页合理）
            len_q = t_cron.query.filter_by(is_deleted=False)
            if current_role != 'admin':
                len_q = len_q.filter_by(job_owner=current_user)
            len_msg = len_q.count()
            return jsonify({"code": 0,
                            "cron_list_msg": list_msg,
                            "msg": "",
                            "cron_len_msg": len_msg})
        except Exception:
            return jsonify({"code": 100, 'msg': '服务器内部错误'})

    @property
    def cron_auth_list(self):
        user_token = request.cookies.get('ogs_token')
        # REV30-M4: user_token 为 None 时 早退, 防 Redis get(None) 拋 TypeError
        if not user_token:
            return jsonify({'code': 100, 'msg': '未登录'})
        auth_name = self.ords.conn.get(user_token)
        # REV30-M4: auth_name 也可能为 None (token 过期 / 被迫下线), 同样返未登录
        if not auth_name:
            return jsonify({'code': 100, 'msg': '未登录'})
        req_type = request_param("req_type")
        auth_list = []
        try:
            # 通过关联表查询用户有权限的 auth_host
            auth_ids = [r.auth_id for r in t_auth_host_user.query.filter_by(user_name=auth_name).all()]
            # 同时查找用户所在用户组的权限
            user_info = t_acc_user.query.filter_by(name=auth_name).first()
            if user_info and user_info.group:
                group_auth_ids = [r.auth_id for r in
                                  t_auth_host_user_group.query.filter_by(group_name=user_info.group).all()]
                auth_ids = list(set(auth_ids + group_auth_ids))
            # 获取 host_group 列表
            host_group_names = []
            for aid in auth_ids:
                rows = t_auth_host_host_group.query.filter_by(auth_id=aid).all()
                for r in rows:
                    host_group_names.append(r.group_name)
            user_role = set(host_group_names)
            if req_type == 'cron_hosts':
                for i in user_role:
                    query_msg = self.lt.list_gather(t_host.query.filter_by(group=i).with_entities(t_host.alias).all())
                    for y in query_msg:
                        auth_list.append({'name': y, 'value': y})
                return jsonify({'msg': auth_list})
            elif req_type == 'cron_groups':
                for i in user_role:
                    auth_list.append({'name': i, 'value': i})
                return jsonify({'msg': auth_list})
        except Exception:
            return jsonify({'msg': 'fail'})
