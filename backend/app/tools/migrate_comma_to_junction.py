"""数据迁移脚本：将 t_cron 和 t_auth_host 的逗号分隔字段拆分写入关联表

使用方式：
  cd pycharm_ogsbackend
  python -m app.tools.migrate_comma_to_junction
"""
from app.core.db.settings import db
from app.core.db.database import (
    t_cron, t_cron_host, t_cron_group,
    t_auth_host, t_auth_host_user, t_auth_host_user_group,
    t_auth_host_host_group, t_auth_host_sys_user,
)


def migrate():
    # ---- t_cron → t_cron_host / t_cron_group ----
    cron_count = 0
    for task in t_cron.query.all():
        # 迁移 job_hosts（旧列可能已被删除，用 try 兼容）
        try:
            hosts_str = task.job_hosts
            if hosts_str:
                for alias in hosts_str.split(','):
                    alias = alias.strip()
                    if alias:
                        exists = t_cron_host.query.filter_by(cron_id=task.id, host_alias=alias).first()
                        if not exists:
                            db.session.add(t_cron_host(cron_id=task.id, host_alias=alias))
                            cron_count += 1
        except AttributeError:
            pass

        # 迁移 job_groups
        try:
            groups_str = task.job_groups
            if groups_str:
                for gname in groups_str.split(','):
                    gname = gname.strip()
                    if gname:
                        exists = t_cron_group.query.filter_by(cron_id=task.id, group_name=gname).first()
                        if not exists:
                            db.session.add(t_cron_group(cron_id=task.id, group_name=gname))
                            cron_count += 1
        except AttributeError:
            pass

    # ---- t_auth_host → 4 张关联表 ----
    auth_count = 0
    for auth in t_auth_host.query.all():
        # 迁移 user
        try:
            user_str = auth.user
            if user_str:
                for name in user_str.split(','):
                    name = name.strip()
                    if name:
                        exists = t_auth_host_user.query.filter_by(auth_id=auth.id, user_name=name).first()
                        if not exists:
                            db.session.add(t_auth_host_user(auth_id=auth.id, user_name=name))
                            auth_count += 1
        except AttributeError:
            pass

        # 迁移 user_group
        try:
            ug_str = auth.user_group
            if ug_str:
                for gname in ug_str.split(','):
                    gname = gname.strip()
                    if gname:
                        exists = t_auth_host_user_group.query.filter_by(auth_id=auth.id, group_name=gname).first()
                        if not exists:
                            db.session.add(t_auth_host_user_group(auth_id=auth.id, group_name=gname))
                            auth_count += 1
        except AttributeError:
            pass

        # 迁移 host_group
        try:
            hg_str = auth.host_group
            if hg_str:
                for gname in hg_str.split(','):
                    gname = gname.strip()
                    if gname:
                        exists = t_auth_host_host_group.query.filter_by(auth_id=auth.id, group_name=gname).first()
                        if not exists:
                            db.session.add(t_auth_host_host_group(auth_id=auth.id, group_name=gname))
                            auth_count += 1
        except AttributeError:
            pass

        # 迁移 sys_user
        try:
            su_str = auth.sys_user
            if su_str:
                for alias in su_str.split(','):
                    alias = alias.strip()
                    if alias:
                        exists = t_auth_host_sys_user.query.filter_by(auth_id=auth.id, sys_user_alias=alias).first()
                        if not exists:
                            db.session.add(t_auth_host_sys_user(auth_id=auth.id, sys_user_alias=alias))
                            auth_count += 1
        except AttributeError:
            pass

    db.session.commit()
    print('Migration done: %d cron rows, %d auth rows migrated.' % (cron_count, auth_count))


if __name__ == '__main__':
    migrate()
