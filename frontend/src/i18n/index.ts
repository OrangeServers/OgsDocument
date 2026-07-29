// =============================================================================
// I18N: 全站中英双语核心
// - locale 用 TS 模块（zh-CN 为 schema 源，en-US 以 satisfies 保证 key 全等）
// - 优先级链：localStorage('ogs:lang') → navigator.language → 'zh-CN'；
//   登录后由服务端 t_settings.language 覆盖（store.loadSettings 调 setLocale）
// - Element Plus 内建文案经 <el-config-provider :locale="epLocale"> 联动
// =============================================================================
import { computed } from 'vue'
import { createI18n } from 'vue-i18n'
import epZhCn from 'element-plus/es/locale/lang/zh-cn'
import epEn from 'element-plus/es/locale/lang/en'
import zhCN from '@/locales/zh-CN'
import enUS from '@/locales/en-US'

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]

export type MessageSchema = typeof zhCN

const STORAGE_KEY = 'ogs:lang'

function normalize(value: string | null | undefined): AppLocale | null {
  if (!value) return null
  if ((SUPPORTED_LOCALES as readonly string[]).includes(value)) return value as AppLocale
  const lower = value.toLowerCase()
  if (lower.startsWith('zh')) return 'zh-CN'
  if (lower.startsWith('en')) return 'en-US'
  return null
}

export function resolveInitialLocale(): AppLocale {
  try {
    const stored = normalize(localStorage.getItem(STORAGE_KEY))
    if (stored) return stored
  } catch { /* 隐私模式等 localStorage 不可用时忽略 */ }
  return normalize(navigator.language) || 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: resolveInitialLocale(),
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, 'en-US': enUS },
})

export function currentLocale(): AppLocale {
  return i18n.global.locale.value as AppLocale
}

/** 切换语言：i18n → localStorage 镜像 → <html lang> → 当前页标题。 */
export function setLocale(value: string): void {
  const locale = normalize(value)
  if (!locale || locale === i18n.global.locale.value) return
  i18n.global.locale.value = locale
  try { localStorage.setItem(STORAGE_KEY, locale) } catch { /* 同上 */ }
  document.documentElement.lang = locale
  refreshDocumentTitle()
}

/** meta.titleKey → document.title（路由守卫与语言切换共用）。 */
let currentTitleKey = ''
export function applyTitleKey(titleKey?: string): void {
  currentTitleKey = titleKey || ''
  refreshDocumentTitle()
}

function refreshDocumentTitle(): void {
  document.title = currentTitleKey
    ? `${i18n.global.t(currentTitleKey)} - OrangeServer`
    : 'OrangeServer'
}

/** Element Plus locale 随语言联动（App.vue 的 el-config-provider 消费）。 */
export const epLocale = computed(() => (
  i18n.global.locale.value === 'en-US' ? epEn : epZhCn
))

/** 非组件上下文（composable/util）直接取全局 t。 */
export const t = i18n.global.t
