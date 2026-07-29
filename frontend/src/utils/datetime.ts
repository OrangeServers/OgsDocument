// =====================================================================
// REV35-L1: datetime 工具 — 3 个 Audit 日志页 + Dashboard 等统一调用
// ti3-TS: 加类型注解
// =====================================================================

/**
 * 解析日志时间为 Date 对象
 * @param s 时间字符串/数字/null/undefined
 * @returns 解析失败返回 null
 */
export function parseLogTime(s: string | number | null | undefined): Date | null {
  if (!s) return null
  if (typeof s === 'number') return new Date(s * 1000)
  if (/^\d+$/.test(s)) return new Date(parseInt(s) * 1000)
  return new Date(String(s).replace(' ', 'T'))
}

/**
 * 相对时间格式化（中文）
 * - < 60s     → "刚刚"
 * - < 1h      → "X 分钟前"
 * - < 24h     → "X 小时前"
 * - < 7d      → "X 天前"
 * - 否则      → localeDate "MM-DD"
 * @param s 时间字符串或数字
 * @returns 相对时间字符串
 */
export function formatTimeRel(s: string | number): string {
  const d = parseLogTime(s)
  if (!d || isNaN(d.getTime())) return String(s || '—')
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 60) return t('common.time.justNow')
  if (diff < 3600) return t('common.time.minutesAgo', { n: Math.floor(diff / 60) })
  if (diff < 86400) return t('common.time.hoursAgo', { n: Math.floor(diff / 3600) })
  if (diff < 604800) return t('common.time.daysAgo', { n: Math.floor(diff / 86400) })
  return d.toLocaleDateString(currentLocale(), { month: '2-digit', day: '2-digit' })
}

/**
 * 短绝对时间格式化（中文 locale, 24h）
 * 输出格式: "MM-DD HH:MM:SS"
 * @param s 时间字符串或数字
 * @returns 解析失败返回空串
 */
export function formatTimeAbs(s: string | number): string {
  const d = parseLogTime(s)
  if (!d || isNaN(d.getTime())) return ''
  return d.toLocaleString(currentLocale(), { hour12: false }).slice(5)
}import { t, currentLocale } from '@/i18n'

