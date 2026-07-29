from flask_sqlalchemy import SQLAlchemy
from app.app_factory import app
from app.core.config import MYSQL_URI

app.config['SQLALCHEMY_DATABASE_URI'] = MYSQL_URI
# R2-9 (REV45-H16): SQLALCHEMY_COMMIT_ON_TEARDOWN = False
#   旧值 True 的问题: app context 销毁时自动 session.commit(),
#   即业务层 ORM 对象 add 后没 commit, teardown 也提交了
#   - 副作用: 业务方以为失败的事务被静默提交
#   - 测试污染: conftest/teardown 自动 commit mock 数据
#   - 绕过统一封装: osql_in/osql_up 的 rollback 失效
#   修复: 设为 False, 强制业务层显式调用 osql_in / osql_up / db.session.commit()
#   (grep 显示业务代码 25+ 处显式 commit, 不依赖 teardown 兜底)
app.config["SQLALCHEMY_COMMIT_ON_TEARDOWN"] = False
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# REV45-H17: SQLALCHEMY_ENGINE_OPTIONS 连接池配置
#   - pool_pre_ping=True: 每次借连接前 SELECT 1, 防 MySQL wait_timeout 切断的死连接
#   - pool_recycle=3600: 强制 1h 回收, 配合 MySQL 默认 8h wait_timeout 留余量
#   - pool_size + max_overflow: 显式设值, 默认 5+10 在生产并发不足
#   - pool_timeout: 等待连接超时 30s, 防止请求 hang
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 3600,
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
}
db = SQLAlchemy(app)
