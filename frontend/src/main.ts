// =============================================================================
// OrangeServer Frontend 入口
// ti3-TS: 从 main.js 迁移, 加类型注解
// =============================================================================
import { createApp, type App as VueApp } from 'vue'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import '@/styles/index.css'
import App from './App.vue'
import router from './router'
import { i18n, resolveInitialLocale } from '@/i18n'

const app: VueApp = createApp(App)
app.use(ElementPlus, { size: 'default' })
// I18N: 语言实例（EP locale 由 App.vue 的 el-config-provider 动态提供）
app.use(i18n)
document.documentElement.lang = resolveInitialLocale()

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// ============================================================
// REVIEW-14 P0-3: Dev 登录态 mock 已迁移到独立模块
//   路径: src/utils/dev-auth-mock.ts
//   防护: Vite 静态常量 + NODE_ENV + 浏览器环境 + hostname 白名单 + 一次性标志 + 原型 freeze
//   注意: 整个 import() 在 prod 构建时被 Vite tree-shake 剔除, 绝不进入生产
// ============================================================
async function bootstrap(): Promise<void> {
  // Dev mock 必须先于 router 安装，否则首个导航守卫已发出鉴权请求，
  // ?dev_login=... 会在 mock 生效前被重定向到登录页。
  let devTarget: string | null = null
  if (import.meta.env.DEV) {
    try {
      const devAuth = await import('@/utils/dev-auth-mock')
      devTarget = await devAuth.installDevAuthMock()
    } catch {
      /* 模块加载失败时静默 */
    }
  }
  app.use(router)
  if (devTarget) await router.replace(devTarget)
  await router.isReady()
  app.mount('#app')
}

void bootstrap()
