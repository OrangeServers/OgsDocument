# -*- coding: utf-8 -*-
"""gunicorn 生产入口（REV48 修复 P0-1 + SETUP-WIZARD 三态启动）。

三态判定（setup/state.py）：
- setup       必需配置不齐且无哨兵 → 最小配置向导 app（不 import 业务代码）
- normal      配置齐全 → 现有 init.py 业务 app，成功后写哨兵
- maintenance 配置不齐但有哨兵 / normal 启动抛异常 → 只读错误页
  （把旧行为"worker boot 连续失败 → 容器 crash-loop"变成可诊断状态）

向导 apply 成功后 worker 对自身发 SIGTERM，gunicorn master 重新 fork 的
新 worker 会重新执行本模块，携带 runtime.env 走 normal 分支。

注意：gevent monkey-patch 由 gunicorn 的 gevent/geventwebsocket worker
在加载本模块之前完成，这里不要重复 patch。
"""
from setup import state

_mode = state.resolve_mode()

if _mode == 'setup':
    from setup.app import create_setup_app
    app = create_setup_app()
elif _mode == 'maintenance':
    from setup.app import create_maintenance_app
    app = create_maintenance_app()
else:
    try:
        from init import app, orange_init_api
        orange_init_api()
        state.mark_configured()
    except BaseException as exc:  # SystemExit(LocalInit) / RuntimeError(config)
        from setup.app import create_maintenance_app
        app = create_maintenance_app(error=exc)
