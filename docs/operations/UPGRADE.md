# OrangeServer 统一升级流程

这是项目内数据库升级、验证和回滚的唯一操作入口。README、配置说明和组件
README 只链接本文，不重复维护迁移命令。

> 不同历史版本可能需要更早的迁移。先阅读当前版本的 `CHANGELOG.md`，确认起始
> 版本，不要跳过未执行的 `backend/mysqldir/rev*.sql`。

## 1. 升级前

1. 安排维护窗口，通知用户 WebSSH 和批量任务可能中断。
2. 记录当前代码版本、镜像标签和运行中的容器。
3. 确认 `.env`、Fernet keys 和外部数据库配置已安全备份。
4. 备份 MySQL、Redis 持久化数据和 `OGS_DATA_DIR`。
5. 在副本或测试环境验证迁移。

MySQL 备份示例：

```bash
mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  -h <mysql-host> -u <mysql-user> -p \
  <database> > orangeserver-before-upgrade.sql
```

确认备份非空并可读取：

```bash
test -s orangeserver-before-upgrade.sql
```

备份文件包含凭据和业务数据，应加密保存且禁止提交 Git。

## 2. 获取并构建目标版本

```bash
git fetch --tags origin
git pull --ff-only
```

Docker Compose：

```bash
make build-backend
```

不要先删除旧镜像。保留一个已验证的应用镜像作为回滚点；具体标签和环境路径只
记录在部署方私有运维系统中。

## 3. 按顺序执行迁移

对尚未启用 AI Provider 和受控诊断的旧实例，依次执行：

```bash
mysql -h <mysql-host> -u <mysql-user> -p <database> \
  < backend/mysqldir/rev48_ai_provider.sql

mysql -h <mysql-host> -u <mysql-user> -p <database> \
  < backend/mysqldir/rev49_ai_context_window.sql

mysql -h <mysql-host> -u <mysql-user> -p <database> \
  < backend/mysqldir/rev50_ai_diagnostics.sql

mysql -h <mysql-host> -u <mysql-user> -p <database> \
  < backend/mysqldir/rev51_settings_language.sql

mysql -h <mysql-host> -u <mysql-user> -p <database> \
  < backend/mysqldir/rev52_smtp_settings.sql
```

顺序不可颠倒：rev49 修改 rev48 创建的 `t_ai_provider`，rev50 增加受控诊断的
Run、事件、加密证据和报告表，rev51 为 `t_settings` 增加界面语言字段（默认
zh-CN，存量行为不变），rev52 增加由管理界面维护的 SMTP 配置字段，授权码仅
保存 Fernet 密文。各脚本针对其自身变更设计了重复执行保护，但重复运行前仍应
确认输出和目标数据库正确。

如果你的起始版本尚未完成旧授权关系迁移，还需要在对应发布说明指导下运行：

```bash
cd backend
python -m app.tools.migrate_comma_to_junction
```

不要在不了解起始 schema 的情况下批量运行全部历史 SQL。

## 4. 验证数据库

```sql
SHOW TABLES LIKE 't_ai_provider';
SHOW COLUMNS FROM t_ai_provider LIKE 'context_window_tokens';
SHOW TABLES LIKE 't_ai_diagnostic_run';
SHOW TABLES LIKE 't_ai_diagnostic_event';
SHOW COLUMNS FROM t_settings LIKE 'mail_smtp_host';
SHOW COLUMNS FROM t_settings LIKE 'mail_password_encrypted';
SHOW TABLES LIKE 't_ai_diagnostic_evidence';
SHOW TABLES LIKE 't_ai_diagnostic_report';

SELECT
    provider_code,
    model,
    enabled,
    is_default,
    context_window_tokens
FROM t_ai_provider
ORDER BY provider_code;
```

预期：

- 存在 `t_ai_provider`；
- 存在 `context_window_tokens`；
- 旧 Provider 默认回填 `262144`；
- 只有管理员明确确认模型支持时才改为 `1048576`；
- 存在 4 张 `t_ai_diagnostic_*` 表及其外键；
- 查询结果中不应出现明文 API Key。

## 5. 启动和冒烟验证

Docker Compose：

```bash
make docker-up
docker compose --env-file .env -f deploy/docker-compose.yml ps
```

基础检查：

```bash
curl --fail http://127.0.0.1:28000/local/health
```

浏览器验证：

1. 管理员登录和退出正常；
2. 资产列表、授权、批量命令和审计页面可打开；
3. WebSSH 能建立和关闭会话；
4. “系统设置 → AI 模型服务”显示 256K/1M 能力；
5. 已配置 API Key 显示掩码状态而非明文或空配置；
6. Provider Tool Calling 测试成功；
7. 新建 256K 会话，执行一次只读资产查询；
8. 对测试资产运行一个固定只读诊断，检查进度、证据引用和报告；
9. 创建批量命令计划，检查预览后取消，不在升级冒烟中执行破坏性命令。

## 6. 回滚

应用回滚和数据库回滚是两件事：

- 应用启动失败但 schema 向后兼容时，可先恢复上一镜像。
- 如果旧应用不能识别新 schema，停止写入后恢复升级前 MySQL 备份。
- rev48/rev49/rev50 不提供自动 down migration；不要在生产手工删除列或表。
- 恢复数据库前先保留失败现场的日志和当前数据库快照。

MySQL 恢复示例：

```bash
mysql -h <mysql-host> -u <mysql-user> -p <database> \
  < orangeserver-before-upgrade.sql
```

恢复后重新运行健康检查和关键浏览器流程。

## 7. 升级后

- 将实际版本、迁移结果、验证结果和回滚点写入私有变更记录。
- 删除包含秘密的临时命令历史和未加密备份副本。
- 观察后端错误、Redis、MySQL、SSH 和 Provider 请求。
- 不要把测试机地址、部署目录、Cookie、密钥或真实资产截图添加到 Issue 或 Git。
