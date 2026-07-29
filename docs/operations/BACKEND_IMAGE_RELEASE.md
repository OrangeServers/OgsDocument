# 后端容器镜像发布

正式版本的后端镜像由 `.github/workflows/publish-backend-image.yml` 从稳定标签
构建。`publish` job 仅在公开的规范仓库中运行；私有归档或 Fork 即使手动触发也
不会发布镜像。

## 首次公开发布

1. 确认仓库已经公开，并完成发布前的全量验收。
2. 创建并推送稳定 SemVer 标签，再为同一标签创建 **Draft Release**，例如
   `v1.0.0`，暂时不要发布。工作流会在构建镜像前验证 Draft Release 已存在。
3. 手动运行 `Publish backend image`，输入该 tag。工作流从 tag 重新构建前端、
   构建 `linux/amd64` 后端镜像，并推送
   `ghcr.io/orangeservers/orangeserver-backend:v1.0.0`。项目不发布 `latest`；
   如果 GHCR 已存在同名版本标签，工作流会在构建前拒绝覆盖。
4. 工作流把独立的 `bootstrap-compose.sh` 和带 SHA256 的 Compose 部署包附加到
   Draft Release。已存在的同名资产不会被覆盖；SHA256 用于发现下载损坏，发布者
   真实性仍依赖固定 tag、GitHub 仓库权限和 Release 管理权限。
5. 首次推送后，在 GitHub Packages 中把 package 设为 **Public**，从未登录 GHCR
   的机器验证镜像匿名拉取，并下载部署包复核 SHA256。
6. 上述验证全部完成后才把 Draft Release 发布，避免用户看到尚未就绪的下载入口。
7. 将部署 `.env` 中的 `OGS_BACKEND_IMAGE` 和 `OGS_BACKEND_TAG` 指向已验证的
   版本，然后执行 `make docker-up-image`。

不要在仓库仍私有时手工公开镜像：Python 镜像包含应用源码，公开镜像基本等同于
提前公开后端代码。

## 发布失败

工作流会 checkout 输入的稳定标签，而不是用默认分支内容冒充版本。如果失败发生在
上传资产之前，可以排除故障后重试；一旦 Draft Release 已包含任何同名资产，不要
覆盖或移动该标签，修复后改用新的补丁版本。已经发布的 Release 会被工作流拒绝。
