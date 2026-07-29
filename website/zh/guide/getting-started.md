# 快速开始

最快的方式是 Docker Compose。要求：Docker Engine、Docker Compose v2、Git 和 Make。

```bash
git clone https://github.com/OrangeServers/OrangeServer.git
cd OrangeServer
cp .env.example .env
cp backend/.env.example backend/.env
```

修改两个环境文件中的所有 `CHANGE_ME` 并设置生产密钥，然后启动：

```bash
make docker-up
```

浏览器打开 `http://<服务器地址>:8080`，初始账号和密码均为 `admin`，
首次登录后必须立即修改密码。

::: tip 首次部署向导
如果启动时缺少必需配置（MySQL、密钥、Fernet keys），后端不会崩溃退出，
而是在 `/setup` 提供网页引导：校验连通性、建库建表、创建管理员账号、
写入配置并自动重启。
:::

## 配置 AI 模型服务

以管理员登录，进入 **系统设置 → AI 模型服务**：选择厂商模板（OpenAI、
Anthropic、xAI、DeepSeek、MiniMax、Kimi、Qwen、GLM、SiliconFlow），填写模型 ID
与 API Key，完成 Tool Calling 测试后保存启用。密钥在后端 Fernet 加密，
不回传浏览器。

## 升级

升级已有实例时，不要只执行 `git pull`。先备份，再按
[统一升级流程](https://github.com/OrangeServers/OrangeServer/blob/main/docs/operations/UPGRADE.md)
顺序执行数据库迁移和验证。

## 下一步

- [部署方式](/zh/guide/deployment) — Compose、物理机、systemd
- [AI 运维](/zh/guide/ai-ops) — AI 助手能做什么、不能做什么
- [完整文档](https://github.com/OrangeServers/OrangeServer/tree/main/docs)
