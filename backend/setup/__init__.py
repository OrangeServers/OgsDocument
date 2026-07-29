# -*- coding: utf-8 -*-
"""首次部署配置向导（setup wizard）。

本包在"必需配置不齐"时替代业务 app 启动一个最小 Flask，只提供
/setup/api/* 配置接口；配置写入 <DATA_DIR>/runtime.env 后 worker 自杀，
gunicorn master 重新 fork 的新 worker 会走 normal 分支加载业务 app。

铁律：本包顶层禁止 import app.*（app.core.config 在 import 期就会因
缺配置抛 RuntimeError）。仅 bootstrap_db 子进程在配置齐全后才 import 业务代码。
"""
