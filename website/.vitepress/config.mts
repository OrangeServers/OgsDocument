import { defineConfig } from 'vitepress'

// 官网：GitHub Pages 托管于 https://orangeservers.github.io/OrangeServer/
// base 必须与仓库名一致；未来绑自定义域名时改为 '/' 并加 CNAME。
export default defineConfig({
  title: 'OrangeServer',
  base: '/OrangeServer/',
  head: [['link', { rel: 'icon', type: 'image/png', href: '/OrangeServer/logo.png' }]],
  lastUpdated: true,

  locales: {
    root: {
      label: 'English',
      lang: 'en-US',
      description:
        'Self-hosted operations platform: assets, SSH, batch jobs, audit trails, and approval-gated AI assistance.',
      themeConfig: {
        nav: [
          { text: 'Guide', link: '/guide/getting-started' },
          { text: 'AI Operations', link: '/guide/ai-ops' },
          {
            text: 'Resources',
            items: [
              { text: 'Documentation index', link: 'https://github.com/OrangeServers/OrangeServer/tree/main/docs' },
              { text: 'Changelog', link: 'https://github.com/OrangeServers/OrangeServer/blob/main/CHANGELOG.md' },
              { text: 'Security policy', link: 'https://github.com/OrangeServers/OrangeServer/blob/main/SECURITY.md' },
            ],
          },
        ],
        sidebar: [
          {
            text: 'Guide',
            items: [
              { text: 'Getting started', link: '/guide/getting-started' },
              { text: 'Deployment options', link: '/guide/deployment' },
              { text: 'AI operations', link: '/guide/ai-ops' },
            ],
          },
        ],
        editLink: {
          pattern: 'https://github.com/OrangeServers/OrangeServer/edit/main/website/:path',
          text: 'Edit this page on GitHub',
        },
        outline: { label: 'On this page' },
      },
    },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      description: '自托管运维平台：资产、SSH、批量任务、审计与需审批的 AI 运维。',
      themeConfig: {
        nav: [
          { text: '指南', link: '/zh/guide/getting-started' },
          { text: 'AI 运维', link: '/zh/guide/ai-ops' },
          {
            text: '资源',
            items: [
              { text: '文档索引', link: 'https://github.com/OrangeServers/OrangeServer/tree/main/docs' },
              { text: '变更日志', link: 'https://github.com/OrangeServers/OrangeServer/blob/main/CHANGELOG.md' },
              { text: '安全策略', link: 'https://github.com/OrangeServers/OrangeServer/blob/main/SECURITY.md' },
            ],
          },
        ],
        sidebar: [
          {
            text: '指南',
            items: [
              { text: '快速开始', link: '/zh/guide/getting-started' },
              { text: '部署方式', link: '/zh/guide/deployment' },
              { text: 'AI 运维', link: '/zh/guide/ai-ops' },
            ],
          },
        ],
        editLink: {
          pattern: 'https://github.com/OrangeServers/OrangeServer/edit/main/website/:path',
          text: '在 GitHub 上编辑此页',
        },
        outline: { label: '本页目录' },
        docFooter: { prev: '上一页', next: '下一页' },
        lastUpdatedText: '最近更新',
        darkModeSwitchLabel: '外观',
        sidebarMenuLabel: '菜单',
        returnToTopLabel: '返回顶部',
        langMenuLabel: '切换语言',
      },
    },
  },

  themeConfig: {
    logo: '/logo.png',
    socialLinks: [
      { icon: 'github', link: 'https://github.com/OrangeServers/OrangeServer' },
    ],
    search: { provider: 'local' },
    footer: {
      message: 'Released under the Apache-2.0 License.',
      copyright: 'Copyright © 2021-2026 Xuzhiwei',
    },
  },
})
