# -*- coding: utf-8 -*-
#

from app.core.db.database import t_host, t_sys_user
from runner import AdHocRunner, CommandRunner
from inventory import BaseInventory


class TestAdHocRunner:

    def __init__(self):
        self.host_data = []
        self.host_query = t_host.query.all()
        self.user_query = t_sys_user.query.filter_by(alias='通用web用户').first()
        for i in self.host_query:
            self.host_data.append({
                "hostname": i.alias,
                "ip": i.host_ip,
                "port": i.host_port,
                "username": self.user_query.host_user,
                "password": self.user_query.host_password,
                'private_key': self.user_query.host_key,
                "groups": [i.group]
            })
        self.inventory = BaseInventory(self.host_data)
        print(self.inventory.get_hosts(), self.inventory.get_groups_dict())
        self.runner = AdHocRunner(self.inventory)

    def test_run(self):
        tasks = [
            {"action": {"module": "shell", "args": "ls"}, "name": "run_cmd"},
            {"action": {"module": "shell", "args": "whoami"}, "name": "run_whoami"},
        ]
        ret = self.runner.run(tasks, "yw199")
        # print(ret.results_summary)
        print(ret.results_raw)


if __name__ == "__main__":
    asb_run = TestAdHocRunner()
    asb_run.test_run()
