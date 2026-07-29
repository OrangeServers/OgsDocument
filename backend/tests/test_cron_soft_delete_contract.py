import inspect

from app.cron.cron import CronList, OgsCron


def test_cron_list_all_hides_soft_deleted_tasks():
    source = inspect.getsource(CronList.cron_list_all.fget)
    assert source.count("t_cron.query.filter_by(is_deleted=False)") == 2


def test_cron_add_reuses_soft_deleted_unique_name():
    source = inspect.getsource(OgsCron.add_job)
    assert "job_name_query.is_deleted" in source
    assert "new_cron.is_deleted = False" in source
    assert "t_cron_host.query.filter_by(cron_id=new_cron.id).delete()" in source
    assert "t_cron_group.query.filter_by(cron_id=new_cron.id).delete()" in source
