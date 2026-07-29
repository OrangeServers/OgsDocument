# -*- coding=utf8 -*-
"""Flask application factory（来自原 Flask_App_Settings.py）

原文件名为 PascalCase 不符合 PEP 8，重构后统一 snake_case。
gunicorn 仍可通过 init:app 启动（init.py 的 app 变量从此模块导入）。
"""
import os  # REV43-H2 (R2-4-1): 静态目录锚定, 避免相对 cwd
from flask import Flask

# REV43-H2: 静态目录用 __file__ 锚定绝对路径, 避免在不同 cwd 启动时找不到 static/
#   原: static_folder='./static' → 相对 cwd, 若 `cd /tmp && python /path/to/init.py` 会找不到
#   修: 基于本文件绝对路径推算 app/static 目录
_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR = os.path.join(_HERE, 'static')

app = Flask(__name__,
            static_folder=_STATIC_DIR,
            template_folder='')

# ti2-API: 初始化 Flasgger (Swagger UI), 给 init.py 提供 swag 全局对象
#   - 仅在 flasgger 已装时启用, 缺包不阻断 init (开发体验)
#   - /apidocs (Swagger UI) 和 /apispec_1.json 在 init.py 的 orange_init_api() 末尾注册
#   - template 注入项目元信息 (title / version / tag description 等)
_Swagger = None  # 闭包引用, 让 init.py 可 import 此模块时拿到 swag
try:
    from flasgger import Swagger as _SwaggerCls
    _SWAGGER_TEMPLATE = {
        'swagger': '2.0',
        'info': {
            'title': 'OrangeServer API',
            'description': (
                'OrangeServer 后端 REST API 自动文档。\n\n'
                '由 [Flasgger](https://github.com/flasgger/flasgger) 从路由注册时注入的 '
                'view_func docstring 提取。业务描述来自各 api 模块 ROUTES 表的 description 字段。'
            ),
            'version': '1.0.0',
            'contact': {
                'name': 'OrangeServers',
                'url': 'https://github.com/OrangeServers/OrangeServer',
            },
        },
        'basePath': '/',
        'schemes': ['http', 'https'],
        'consumes': ['application/json'],
        'produces': ['application/json'],
        'tags': [
            {'name': 'account', 'description': '账号/用户/组 (登录注册、改密)'},
            {'name': 'auth', 'description': '资产授权 (主机/组授权)'},
            {'name': 'local', 'description': '本地服务 (文件/目录/上传)'},
            {'name': 'server', 'description': '资产管理 (主机/分组)'},
            {'name': 'mail', 'description': '邮件发送'},
            {'name': 'cron', 'description': '定时任务'},
        ],
    }
    _Swagger = _SwaggerCls(template=_SWAGGER_TEMPLATE)
except ImportError:
    # flasgger 未装: 跳过 Swagger 初始化, /apidocs 路由也会自动跳过
    pass
