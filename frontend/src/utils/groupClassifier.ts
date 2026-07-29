// =====================================================================
// REV35-L5: group classifier — 5 色映射工具
// ti3-TS: 加类型注解
// =====================================================================

const _PROD_RE: RegExp = /admin|超管|管理员|ops|prod|prd|生产|线上|master|主库|formal/ // i18n-ignore 组名分类协议
const _STAGING_RE: RegExp = /audit|审计|log|日志|stag|stg|预发|灰度|gray/ // i18n-ignore
const _TEST_RE: RegExp = /dev|研发|开发|test|测试|qa|sandbox/ // i18n-ignore
const _CACHE_RE: RegExp = /cache|redis|mq|kafka|nginx|中间件|中间|db|数据库/ // i18n-ignore

/** 5 色分类 key */
export type GroupTagClass = 'is-prod' | 'is-staging' | 'is-test' | 'is-cache' | 'is-other'

/**
 * 资产组 / 用户组 → 5 色 CSS class
 * @param name 组名 (可空)
 * @returns 5 色 class
 */
export function groupTagClass(name: string | null | undefined): GroupTagClass {
  if (!name) return 'is-other'
  const g = String(name).toLowerCase()
  if (_PROD_RE.test(g))    return 'is-prod'
  if (_STAGING_RE.test(g)) return 'is-staging'
  if (_TEST_RE.test(g))    return 'is-test'
  if (_CACHE_RE.test(g))   return 'is-cache'
  return 'is-other'
}
