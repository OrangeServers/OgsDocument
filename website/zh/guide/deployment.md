# 部署方式

OrangeServer 提供三条经过验证的部署路径，全部经过部署审计并在真实环境
端到端验证过。

## Docker Compose（推荐）

一条命令启动四个容器（nginx、前端、后端、MySQL/Redis），
即[快速开始](/zh/guide/getting-started)描述的路径。

全新安装可直接运行稳定 GitHub Release 中固定版本的薄引导器：

```bash
curl -fsSL \
  https://github.com/OrangeServers/OrangeServer/releases/download/v1.0.0/bootstrap-compose.sh \
  | sudo bash -s -- --version v1.0.0
```

引导器会下载并校验同版本部署包，生成 MySQL 与 Redis 基础设施密码，
并启动已发布的
`ghcr.io/orangeservers/orangeserver-backend:v1.0.0` 镜像。
管理员、SMTP、AI 服务商等应用配置仍在浏览器 `/setup` 向导中完成。
如果环境不允许把下载内容直接交给 shell，请先下载并审阅引导器再执行。

源码检出或已有安装仍可使用仓库目标：

```bash
make docker-up        # bundled 模式：全容器
make docker-up-host   # host 模式：复用宿主机已有 MySQL/Redis
```

## 物理机

在主机上直接安装 MySQL、Redis、nginx 与 Python 后端。
首次启动前用预检脚本验证环境：

```bash
ops/preflight-physical-backend.sh
```

## systemd / supervisor

用与容器相同的 gunicorn 命令在 systemd 或 supervisor 下运行后端，
unit 文件与配置布局见部署手册。

## 参考

完整手册（环境变量、nginx 配置、健康检查、故障排查）见
[DEPLOY.md](https://github.com/OrangeServers/OrangeServer/blob/main/DEPLOY.md)。
升级请务必遵循
[统一升级流程](https://github.com/OrangeServers/OrangeServer/blob/main/docs/operations/UPGRADE.md)。
