// useCronNext.ts — REV34-M7
// ti3-TS: 加类型注解
// 计算 cron 表达式下一次执行时间
// 支持标准 cron 五字段：分 时 日 月 周
// 字段语法：
//   *         任意
//   a         固定值 a
//   a-b       范围 [a, b]
//   * / n     步长（任意值范围内按 n 步进）
//   a-b / n   步长
//   a, b, c   多值
// 注：日和周遵循 Vixie cron 规则：同时指定时取并集
//   （即 day 命中 OR week 命中即匹配）
import { t, currentLocale } from '@/i18n'
import { ref, watchEffect, toValue, type Ref, type MaybeRefOrGetter } from 'vue'

interface CronRange {
  min: number
  max: number
}

const RANGES: Record<string, CronRange> = {
  minute: { min: 0, max: 59 },
  hour:   { min: 0, max: 23 },
  day:    { min: 1, max: 31 },
  month:  { min: 1, max: 12 },
  week:   { min: 0, max: 6 },
}

/** cron 行 (后端 t_cron 字段) */
export interface CronRow {
  job_name: string
  job_minute: string
  job_hour: string
  job_day: string
  job_month: string
  job_week: string
  [k: string]: unknown
}

/**
 * 解析单个 cron 字段为匹配值集合
 * @returns 解析失败返回 null
 */
function _parseField(field: unknown, min: number, max: number): Set<number> | null {
  if (typeof field !== 'string' || !field.trim()) return null
  const result = new Set<number>()
  for (const partRaw of field.split(',')) {
    const part = partRaw.trim()
    if (!part) return null
    let range: string
    let step: number
    if (part.includes('/')) {
      const idx = part.indexOf('/')
      range = part.slice(0, idx)
      step = parseInt(part.slice(idx + 1), 10)
    } else {
      range = part
      step = 1
    }
    if (!Number.isFinite(step) || step <= 0) return null
    let start: number
    let end: number
    if (range === '*' || range === '') {
      start = min; end = max
    } else if (range.includes('-')) {
      const [a, b] = range.split('-').map(s => parseInt(s, 10))
      if (!Number.isFinite(a) || !Number.isFinite(b)) return null
      start = a; end = b
    } else {
      const v = parseInt(range, 10)
      if (!Number.isFinite(v)) return null
      start = v; end = v
    }
    if (start < min || end > max || start > end) return null
    for (let i = start; i <= end; i += step) result.add(i)
  }
  return result
}

/**
 * 计算 cron 表达式下一次执行时间
 * @param row - { job_minute, job_hour, job_day, job_month, job_week }
 * @returns 解析失败返回 null
 */
export function computeNextRun(row: CronRow | null | undefined): Date | null {
  if (!row) return null
  const { job_minute: m, job_hour: h, job_day: d, job_month: mo, job_week: w } = row
  if (!m || !h || !d || !mo || !w) return null
  const minutes = _parseField(m, RANGES.minute.min, RANGES.minute.max)
  const hours   = _parseField(h, RANGES.hour.min,   RANGES.hour.max)
  const days    = _parseField(d, RANGES.day.min,    RANGES.day.max)
  const months  = _parseField(mo, RANGES.month.min, RANGES.month.max)
  const weeks   = _parseField(w, RANGES.week.min,   RANGES.week.max)
  if (!minutes || !hours || !days || !months || !weeks) return null
  // 候选时间从下一分钟开始
  const now = new Date()
  const cand = new Date(now)
  cand.setSeconds(0, 0)
  cand.setMinutes(cand.getMinutes() + 1)
  // 限制迭代次数：5 年（足够覆盖 366*5 = 1830 天）
  // 防止异常 cron 表达式导致死循环
  const MAX_ITER = 366 * 5
  for (let i = 0; i < MAX_ITER; i++) {
    const month = cand.getMonth() + 1
    if (!months.has(month)) {
      // 跳到下个月第一天
      cand.setMonth(cand.getMonth() + 1, 1)
      cand.setHours(0, 0, 0, 0)
      continue
    }
    const day = cand.getDate()
    const week = cand.getDay()
    const dayMatch  = days.has(day)
    const weekMatch = weeks.has(week)
    // 日 / 周 匹配规则（Vixie cron 语义）：
    //   d === '*' && w === '*'    -> 都通配，任何日期都算匹配
    //   d !== '*' && w !== '*'    -> dayMatch OR weekMatch（并集）
    //   d !== '*' && w === '*'    -> 仅 dayMatch
    //   d === '*' && w !== '*'    -> 仅 weekMatch
    let dateMatch: boolean
    if (d === '*' && w === '*') {
      dateMatch = true
    } else if (d !== '*' && w !== '*') {
      dateMatch = dayMatch || weekMatch
    } else if (d !== '*') {
      dateMatch = dayMatch
    } else {
      dateMatch = weekMatch
    }
    if (!dateMatch) {
      cand.setDate(cand.getDate() + 1)
      cand.setHours(0, 0, 0, 0)
      continue
    }
    if (!hours.has(cand.getHours())) {
      cand.setHours(cand.getHours() + 1, 0, 0, 0)
      continue
    }
    if (!minutes.has(cand.getMinutes())) {
      cand.setMinutes(cand.getMinutes() + 1)
      continue
    }
    return cand
  }
  return null
}

/**
 * 距离下次执行的相对时间（中文）
 */
export function formatNextRunRel(d: Date | null | undefined): string {
  if (!d) return ''
  const diff = Math.max(0, (d.getTime() - new Date().getTime()) / 1000)
  if (diff < 60) return t('common.time.imminent')
  if (diff < 3600) return t('common.time.inMinutes', { n: Math.floor(diff / 60) })
  if (diff < 86400) return t('common.time.inHours', { n: Math.floor(diff / 3600) })
  return t('common.time.inDays', { n: Math.floor(diff / 86400) })
}

/**
 * 格式化绝对时间为 MM-DD HH:mm
 */
export function formatNextRunAbs(d: Date | null | undefined): string {
  if (!d) return ''
  return d.toLocaleString(currentLocale(), {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** useCronNext 返回值 */
export interface UseCronNextReturn {
  nextRun: (row: CronRow | null | undefined) => Date | null
  nextRunRel: (row: CronRow | null | undefined) => string
  nextRunAbs: (row: CronRow | null | undefined) => string
  computeNextRun: (row: CronRow | null | undefined) => Date | null
}

/**
 *  composable：批量构造 nextRun/nextRunRel/nextRunAbs 方法
 *  保留原 Cron.vue 中 nextRun/nextRunRel/nextRunAbs 的同名接口
 *  性能优化：所有派生数据基于单个 Map<jobName, Date> 缓存，
 *  避免同一任务在表格中渲染多次时重复计算。
 */
export function useCronNext(getRows: MaybeRefOrGetter<CronRow[]>): UseCronNextReturn {
  // 缓存：key=jobName, value=Date|null
  const cache: Ref<Map<string, Date | null>> = ref(new Map())
  watchEffect(() => {
    const rows: CronRow[] = toValue(getRows) || []
    const next = new Map<string, Date | null>()
    for (const r of rows) {
      if (!r || !r.job_name) continue
      next.set(r.job_name, computeNextRun(r))
    }
    cache.value = next
  })
  function nextRun(row: CronRow | null | undefined): Date | null {
    if (!row || !row.job_name) return null
    return cache.value.get(row.job_name) ?? null
  }
  function nextRunRel(row: CronRow | null | undefined): string {
    return formatNextRunRel(nextRun(row))
  }
  function nextRunAbs(row: CronRow | null | undefined): string {
    return formatNextRunAbs(nextRun(row))
  }
  return { nextRun, nextRunRel, nextRunAbs, computeNextRun }
}
