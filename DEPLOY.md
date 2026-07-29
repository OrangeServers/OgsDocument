# OrangeServer 部署手册

> **运维堡垒机 · MISSION CONTROL**
> 统一入口管理服务器资产、批量执行命令与脚本，所有操作可审计、可回溯、可告警。

---

## 一键安装

> 将下列 `vX.Y.Z` 替换为同一个已发布的稳定版本号。

```bash
curl -fsSL \
  https://github.com/OrangeServers/OrangeServer/releases/download/vX.Y.Z/bootstrap-compose.sh \
  | sudo bash -s -- --version vX.Y.Z
```

该命令中的脚本只是薄引导器：下载并校验对应 Release 的部署包、自动生成 MySQL /
Redis 基础设施密码，然后调用仓库内的预检与 `make docker-up-image`。应用管理员、
系统名称、SMTP、AI 等仍在浏览器 `/setup` 向导配置。

更保守的做法是先从同一 Release 下载 `bootstrap-compose.sh`，人工审阅后再执行；
引导器、部署包和校验文件都属于同一个固定版本，不会下载默认分支 HEAD。
同一主机并行验收多个实例时，可追加唯一的
`--project-name orangeserver_test --install-dir /opt/orangeserver-test --port 18082`；
项目名决定 Compose 容器、网络和数据卷前缀。

## 手动 Docker Compose 快速开始

```bash
# 1. 获取源码 & 配置
git clone <repo-url> orangeserver && cd orangeserver
# 无法访问 GitHub 时，也可以在联网机器下载正式 Release/source tarball，
# 上传到部署机并解压为 orangeserver/ 后进入该目录。
cp .env.example .env && cp backend/.env.example backend/.env
chmod 600 .env backend/.env

# 2. bundled 模式先填写 MySQL/Redis 容器初始化配置：
#    OGS_MYSQL_{DBNAME,USER,PASSWORD} 和 OGS_REDIS_PASSWORD 必须在根 .env
#    与 backend/.env 中保持一致；MYSQL_ROOT_PASSWORD 只填写在根 .env。
#    backend/.env 的 SECRET_KEY/FERNET_KEYS 可以留空，由 /setup 安全生成。
make docker-up

# 3. 访问
#    浏览器打开 http://<IP>:<OGS_HTTP_PORT>（默认 8080）
#    - 后端必需配置齐全时：直接进入登录页
#    - 后端应用配置未完成时：自动进入 /setup 首次部署配置向导（见下节）
#      向导中的 SMTP 步骤可跳过；也可在登录后的通知设置中再配置和测试。
```

### 首次部署配置向导（/setup）

后端启动时若必需配置不齐（MySQL 三项 / `OGS_FLASK_SECRET_KEY` / `OGS_FERNET_KEYS`
缺失、为空或仍为模板占位符），会进入**网页配置向导**而不是启动失败：

1. 打开 `http://<IP>:<OGS_HTTP_PORT>`（默认 `8080`），前端自动跳转 `/setup`
2. 第一步需要 **Setup Token**（防未授权配置）：在后端启动日志中查找 `[setup]` 行
   （`docker logs <后端容器>` / `journalctl -u orangeserver-backend`），或读取
   `<数据目录>/setup_token.txt`
3. 按步骤填写 MySQL、Redis（每步可"测试连接"）、管理员账号与可选设置；
   安全密钥由服务端自动生成、只落盘不回传浏览器
4. 提交后：初始化数据库（建表 + 种子，内置 admin/admin 弱口令账号会被向导
   管理员替代）→ 配置写入 `<数据目录>/runtime.env`（0600）→ 后端自动重启生效

要点：

- **优先级**：非空进程环境变量 > `runtime.env`（向导写入）> `backend/.env`。
  手工配置永远优先；删除 `runtime.env` 即回退纯 .env 配置
- **一次性**：配置完成后向导接口即不存在；已配置系统即使配置损坏也只会进入
  只读维护页（`/setup/api/status` 显示错误摘要），不会重新开放向导。
  救援通道：设 `OGS_SETUP_MODE=force` 后重启（需要宿主机权限）
- `OGS_SETUP_MODE=off` 可完全禁用向导，恢复旧版 fail-fast 行为
- compose **bundled 模式**下 MySQL/Redis 服务名等由部署环境固定的项，在向导中
  显示为只读；MySQL root/应用密码仍需在宿主 `.env` 配置（mysql 容器初始化需要）
- 向导要求 gunicorn 形态（三种部署方式均满足）；`python init.py` 裸跑 dev 模式
  不支持，请手工配置 `backend/.env`

> 前端 `frontend/dist/` 是 pre-build 产物，部署机不需要 node/npm。正式源码包或
> Release 必须包含该目录；只有开发者修改前端后才需要运行 `make build-frontend`。

> 国内拉镜像超时？配 registry mirror：`sudo cp deploy/daemon.json.example /etc/docker/daemon.json && sudo systemctl restart docker`

> 当前 Compose 会直接拉取官方 Nginx、Redis、MySQL 镜像，并从本仓库源码构建
> OrangeServer 后端镜像。测试机首次冷构建约需 3–5 分钟，具体取决于网络和磁盘；
> 依赖与源码未变化时 Docker 缓存重建通常只需数秒。可用
> `docker compose ... build --progress=plain backend` 查看详细进度。
> 使用预构建后端镜像时，可在根 `.env` 设置 `OGS_BACKEND_IMAGE` 与固定的
> `OGS_BACKEND_TAG`，再执行 `make docker-up-image` 跳过本地构建。目标版本尚未
> 发布镜像时不要启用该入口。

---

## 前置条件

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Docker | 24+ | Compose v2 插件 |
| Docker Compose | v2.20+ | `depends_on` + `required: false` 语法 |
| 磁盘 | ≥ 20 GB | MySQL 数据卷 |

---

## 环境变量配置

手动 Compose 部署需要两份 `.env` 文件。一键安装会自动生成并设为 `0600`，普通用户
不需要手工编辑；以下内容保留给高级部署、外部数据库和故障排查。

### 顶层 `.env`（Docker Compose 变量替换）

```bash
COMPOSE_PROJECT_NAME=orangeserver
OGS_HTTP_PORT=8080                    # 宿主机端口（默认 8080，避免与已有服务冲突）

MYSQL_ROOT_PASSWORD=<容器root强密码>    # MySQL root 密码（仅容器内使用）
OGS_MYSQL_HOST=mysql                  # bundled 模式用 compose 服务名
OGS_MYSQL_PORT=3306
OGS_MYSQL_DBNAME=orange
OGS_MYSQL_USER=app_user
OGS_MYSQL_PASSWORD=<业务账号密码>       # 与 backend/.env 保持一致
OGS_REDIS_HOST=redis
OGS_REDIS_PORT=6379
OGS_REDIS_PASSWORD=<Redis密码>
OGS_HTTPS=false                       # 试运行设 false，生产 TLS 终止后改 true
```

### `backend/.env`（后端进程加载）

```bash
OGS_ENV=prod
OGS_FLASK_SECRET_KEY=<48字节随机>      # python -c "import secrets; print(secrets.token_urlsafe(48))"
OGS_FERNET_KEYS=<Fernet密钥>           # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
OGS_MYSQL_HOST=mysql                   # compose 服务名
OGS_MYSQL_PORT=3306
OGS_MYSQL_PASSWORD=<与顶层一致>
OGS_REDIS_HOST=redis
OGS_REDIS_PORT=6379
OGS_REDIS_PASSWORD=<与顶层一致>
OGS_HTTPS=false
OGS_CSRF_ALLOWED_ORIGINS=http://<你的域名或IP>:8080
```

> **两个密码的区别**：
> - `MYSQL_ROOT_PASSWORD`：MySQL 容器 root 密码，仅顶层 `.env`
> - `OGS_MYSQL_PASSWORD`：业务账号 `app_user` 密码，两份 `.env` **保持一致**

> **公开地址必须一致**：修改 `OGS_HTTP_PORT` 后，浏览器访问地址、健康检查地址和
> `backend/.env` 中的 `OGS_CSRF_ALLOWED_ORIGINS` 必须使用同一个端口。例如
> `OGS_HTTP_PORT=18081` 时，应设置
> `OGS_CSRF_ALLOWED_ORIGINS=http://<你的域名或IP>:18081`，否则登录或向导提交
> 可能返回 CSRF 403。

> **密码透明升级**：首次成功登录后，密码自动从 base64 升级为 bcrypt hash。升级后密码不变，但忘记密码需直接操作数据库重置。

---

## Docker Compose 部署（推荐）

### 启动

```bash
# 预检 + 构建 + 启动（bundled 模式，4 容器全起）
make docker-up

# 查看日志（MySQL 初始化约 30-60s）
make docker-logs

# 查看状态
make docker-ps
```

### 验证

```bash
# 健康检查
make docker-health
# 初始化向导阶段: {"status":"setup","setup_required":true}
# 初始化完成后:   {"status":"ok", ...}
# 两者 HTTP 状态码均为 200

# 浏览器访问
# http://<IP>:<OGS_HTTP_PORT>  →  登录页（默认 8080）
# 使用 /setup 时，以向导中创建的管理员账号登录。
# 只有跳过向导并保留基线种子数据时才存在 admin/admin，登录后必须立即改密。

# 进容器排查
docker compose --env-file .env -f deploy/docker-compose.yml exec backend bash
```

### 两种模式

| 模式 | 命令 | 启动服务 | 镜像来源 | 场景 |
|------|------|----------|----------|------|
| **bundled** | `make docker-up` | 4 个 | 后端本地构建；其余 3 个拉取 | 全新部署 |
| **host** | `make docker-up-host` | 2 个 | 后端本地构建；Nginx 拉取 | 已有 MySQL/Redis |

> host 模式需将 `backend/.env` 中 `OGS_MYSQL_HOST` / `OGS_REDIS_HOST` 改为外部地址
> （容器访问宿主机服务用 `host.docker.internal`）。`make docker-up-host` 会自动叠加
> `deploy/docker-compose.host.yml`（提供 `host.docker.internal` 的解析）并先跑预检；
> 不要手敲缺少该 overlay 文件的裸 compose 命令。

### 开发模式

```bash
make docker-dev-up    # 挂载源码，改动即时生效
```

> 前置条件：dev 覆盖把 MySQL/Redis 指向 `host.docker.internal` 且不带
> `--profile bundled`——宿主机需已自行运行 MySQL 与 Redis。

### 升级 & 回滚

已有实例不能只执行 `git pull`。数据库备份、按顺序迁移、验证和回滚统一按照
[升级流程](docs/operations/UPGRADE.md) 操作。本节不重复维护迁移命令。

### 数据持久化

| 数据 | 位置 | 备份 |
|------|------|------|
| MySQL | `<COMPOSE_PROJECT_NAME>_mysql-data` volume | `docker compose --env-file .env -f deploy/docker-compose.yml exec -T mysql sh -c "MYSQL_PWD=\$MYSQL_ROOT_PASSWORD mysqldump -u root --single-transaction orange"` |
| 后端运行数据 | `<COMPOSE_PROJECT_NAME>_backend-data` volume | SSH 密钥 / 头像 / 上传文件 / 日志 |

---

## 物理机部署（高级）

> 适用于不能跑 Docker 的环境。需要 Python 3.11+（推荐 3.12，与容器一致；预检脚本
> 硬性要求 3.11/3.12）/ MySQL 8.0 / Redis 5+ / Nginx 1.16+。

### 文件布局

```
/opt/orangeserver/app/backend/        代码（只读）
/opt/orangeserver/venv/               Python 3.12 运行时（只读）
/data/orangeserver/                   运行数据（orange:orange 0700）
/etc/orangeserver/backend.env         环境变量（root:root 0600）
```

### 步骤

```bash
# 0. 代码与运行时（unit 文件按此布局锚定，路径不可省略）
useradd --system --home-dir /nonexistent --shell /sbin/nologin orange
mkdir -p /opt/orangeserver
git clone <repo-url> /opt/orangeserver/app        # 代码 → /opt/orangeserver/app/backend
python3.12 -m venv /opt/orangeserver/venv
/opt/orangeserver/venv/bin/pip install -r /opt/orangeserver/app/backend/requirements.txt

# 1. 数据目录
install -d -o orange -g orange -m 0700 /data/orangeserver/{avatars,file,key,log,containers/temp}

# 2. MySQL / Redis / 建库
#    需要已可用的 MySQL 8.0 与 Redis 5+。建库 + 导 schema + 建业务账号可用安装脚本：
#    bash /opt/orangeserver/app/ops/install.sh   （RHEL 系；Debian 用 install-debian.sh）
#    或手动: 建 orange 库 → 导入 backend/mysqldir/orange.sql → 创建 app_user 并授权 orange.*

# 3. 环境文件（必填项也可留空——首次启动会进入 /setup 网页向导）
install -o root -g root -m 0600 deploy/systemd/backend.env.example /etc/orangeserver/backend.env
vim /etc/orangeserver/backend.env

# 4. 安装 & 启动
install -o root -g root -m 0644 deploy/systemd/orangeserver-backend.service /etc/systemd/system/
systemctl daemon-reload
bash ops/preflight-physical-backend.sh       # 预检（必填项缺失仅 WARN，--strict 恢复硬校验）
systemctl start orangeserver-backend
systemctl status orangeserver-backend

# 5. 前端与反向代理（物理机必须由 nginx serve 静态资源，后端不托管 dist）
install -o root -g root -m 0644 deploy/nginx/orange_server.conf /etc/nginx/conf.d/
#    并把仓库 frontend/dist/ 同步到 conf 中 root 指向的目录后 reload nginx

# 6. 验证
curl -s http://127.0.0.1:28000/local/health
```

> **关键约束**：必须 `--workers 1`（APScheduler 模块导入时启动，多 worker 会重复执行定时任务）；入口必须是 `wsgi:app`（不是 `init:app`）。

### Supervisor 方式（传统）

```bash
# conf 必须平铺到 conf.d/ 根（supervisord 的 include 不递归子目录）
sudo cp deploy/supervisor/orange_server.conf /etc/supervisor/conf.d/
sudo cp deploy/supervisor/orange_server.env.example /etc/supervisor/orange_server.env
sudo vim /etc/supervisor/orange_server.env

# conf 中的 %(ENV_OGS_*)s 变量必须注入到 supervisord 守护进程本身：
sudo systemctl edit supervisor      # 加入:
#   [Service]
#   EnvironmentFile=/etc/supervisor/orange_server.env
sudo systemctl restart supervisor

sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl start orange:*
```

> Supervisor 不读 `env-file`；`source` 到当前 shell 也注入不进已运行的 daemon——
> 必须用上面的 `systemctl edit` 方式（或在 supervisord.conf 的 `[supervisord]`
> 段写 `environment=` 指令）。

---

## Kubernetes 部署（参考）

> 项目未内置 `k8s/` 目录，以下为参考示例。建议使用云厂商托管 MySQL/Redis。

关键资源：Namespace → ConfigMap（OGS_* 非敏感配置）→ Secret（密钥）→ Backend Deployment（`replicas: 1`，`--workers 1` 限制）→ Service → Ingress。

```bash
# 构建 & 推送镜像
docker build -t registry.example.com/orangeserver-backend:v1.0 backend/
docker push registry.example.com/orangeserver-backend:v1.0
```

自行编写清单（仓库未内置 `k8s/` 目录）后再 `kubectl apply`。

> WebSocket 长连接场景下，HPA 滚动升级可能导致 WebSSH 断连，建议固定 `replicas: 1` + 手动滚动。

---

## 升级与维护

### 数据库迁移

全新安装由初始化 schema 建库。已有实例必须从
[统一升级流程](docs/operations/UPGRADE.md) 进入，先确认起始版本并备份，再按版本
顺序执行迁移。不要从旧文档或聊天记录复制单条 SQL。

### 备份

| 数据 | 方式 | 频率 |
|------|------|------|
| MySQL | `mysqldump` 整库 | 每天 |
| Redis | `BGSAVE` | 视数据重要性 |
| 上传文件 | `tar/rsync` 到对象存储 | 每周 |

### 日志

| 部署方式 | 路径 |
|---------|------|
| Docker | `make docker-logs` |
| 物理机 | `$OGS_DATA_DIR/log/ogsbackend.log`（如 `/data/orangeserver/log/`，10MB 轮转） |
| Nginx | `/var/log/nginx/orange_server.{access,error}.log` |

### 健康检查

```bash
# Docker Compose（后端端口不对宿主发布，经前端 OGS_HTTP_PORT 反代）
make docker-health
# 物理机（gunicorn 直连）
curl http://127.0.0.1:28000/local/health
# HTTP 200 = 健康
```

---

## 常见问题

| 问题 | 排查 |
|------|------|
| `OGS_FLASK_SECRET_KEY is required` | `backend/.env` 未设置 `OGS_FLASK_SECRET_KEY`，且 `OGS_ENV=prod` |
| MySQL 连接失败 | 确认 HOST/PORT/USER/PASSWORD 正确；`mysql -u<user> -p<pwd> -h<host>` 手动验证 |
| Redis 连接失败 | `redis-cli -h <host> -p <port> ping` 应返回 PONG |
| 登录后立即"未登录" | `OGS_HTTPS` 设为 `false`（无 TLS 时 Secure cookie 不被浏览器写入） |
| 登录 CSRF 403 | `OGS_CSRF_ALLOWED_ORIGINS` 设为你的域名（精确到 scheme+netloc） |
| WebSSH 断连 | nginx `proxy_read_timeout` 需 ≥ 3600s |
| WebSSH “Incompatible ssh peer” | 目标服务器 OpenSSH 过旧（<6.5），只支持 ssh-rsa。需升级目标服务器 OpenSSH，或降级 paramiko `<5.0` |
| WebSSH 认证失败 | 系统用户未配置密码/密钥，请在“系统用户”页面设置凭据 |
| Host key 拒绝 | 代码默认 `OGS_SSH_HOST_KEY_POLICY=reject`（需预置 known_hosts）；接受新主机可改 `auto` |
| 上传 413 | nginx `client_max_body_size` 需 ≥ 200m |
| MySQL 健康检查失败 | 首次启动等 30-60s（MySQL 初始化） |

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [CONFIG.md](CONFIG.md) | 全部 OGS_* 环境变量清单 |
| [docs/operations/UPGRADE.md](docs/operations/UPGRADE.md) | 唯一数据库升级、验证与回滚流程 |
| [docs/operations/BACKEND_IMAGE_RELEASE.md](docs/operations/BACKEND_IMAGE_RELEASE.md) | 维护者发布 GHCR 后端镜像 |
| [deploy/docker-compose.yml](deploy/docker-compose.yml) | Docker Compose 编排 |
| [deploy/nginx/](deploy/nginx/) | Nginx 反代配置 |
| [deploy/systemd/](deploy/systemd/) | systemd unit + 环境模板 |
| [deploy/supervisor/](deploy/supervisor/) | Supervisor 进程管理 |
| [ops/preflight-physical-backend.sh](ops/preflight-physical-backend.sh) | 物理机预检脚本 |
| [backend/README.md](backend/README.md) | 后端模块说明 |
