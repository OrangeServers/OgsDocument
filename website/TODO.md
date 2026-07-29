# 官网后续待办

> 随 `feat/website` 分支走，不并入主仓库 docs/。2026-07-28 首页重构（commit `aa4f7da`）后梳理。

## 上线前（一次性）

- [ ] 合并 `feat/website` → `main`（`.github/workflows/deploy-site.yml` 仅在 main 分支触发）
- [ ] 仓库 Settings → Pages → Source 设为 **GitHub Actions**（首次发布前必须，否则 workflow 发布失败）

## 项目公开后（仓库当前为 private）

- [ ] 恢复 stars 动态 badge：`website/.vitepress/theme/components/HeroExtras.vue` 现用静态 badge 占位（private 期间 shields 接口返回 "repo not found"），公开后换回 `img.shields.io/github/stars/OrangeServers/OrangeServer`
- [ ] 全站检查指向 GitHub 仓库的外链（private 期间对外部访客全部 404）

## 内容优化

- [ ] **英文站截图替换**：`website/public/screens/` 6 张均为中文界面截图。产品切英文后重截一套（dashboard / ai-agent / assets / batch-ops / web-terminal / settings-ai），并核对 `ScreensGallery.vue` 与 `guide/ai-ops.md` 的英文 caption
- [ ] 指南页扩充：安全架构、FAQ、功能详情页（现仅 3 篇，深度内容靠外链回仓库 docs/）
- [ ] SEO 收尾：sitemap、og meta、自定义 404 页

## 产品 UI（另起分支，勿在 feat/website 做）

- [ ] **Web 终端页面重设计**：参考官网 hero 的终端窗口风格（TermMock.vue），用户已明确表示有兴趣，下次单独开分支实施
