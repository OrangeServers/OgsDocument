// =====================================================================
// REV33-M4: useLogTable composable - 3 个 Audit 日志页共享
// ti3-TS: 加类型注解
// =====================================================================
// 抽离 AuditComLog / AuditCzLog / AuditUserLog 共用逻辑：
//   1. 响应式状态：keyword / dateRange / page / pageSize / total / loading / tableData
//   2. 计算属性：successCount / failCount
//   3. 工具方法：isSuccess / isFail / statusClass / statusLabel
//   4. 时间格式化：parseLogTime / formatTimeRel / formatTimeAbs
//   5. 数据加载：loadData / search / reset / handleSizeChange / handlePageChange
//   6. 导出：exportLog(filename, headers, rowMap)
//
// API 差异：
//   - getLogs({ log_type: 'command' | 'cz' | 'login', page, limit })
//   - searchLogs({ cz_jg_date | login_jg_date | log_jg_date, log_type, page, limit })
//   - getLogsByDate({ cz_jg_date | login_jg_date | log_jg_date, log_type, page, limit })
//   调用方通过 searchKeywordField / searchDateField 配置
// =====================================================================
import { t } from '@/i18n'
import { ref, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLogs, getLogsByDate, searchLogs } from '@/api'
// REV35: 时间格式化 / 状态判定 / 复制已抽离到 utils 与 composables
import { parseLogTime, formatTimeRel, formatTimeAbs } from '@/utils/datetime'
import { isSuccess, isFail, statusClass, statusLabel } from '@/utils/logStatus'
import { useClipboard } from '@/composables/useClipboard'

/** 日志类型 */
export type LogType = 'command' | 'cz' | 'login'

/** 日志后端搜索/筛选字段 */
export type LogDateField = 'log_jg_date' | 'cz_jg_date' | 'login_jg_date'

/** 日志行 (后端动态结构, 兼容 3 类日志) */
export interface LogRow {
  log_status: string | number
  [k: string]: unknown
}

/** 日志响应 (后端真实返回) */
export interface LogListResponse {
  log_list_msg?: LogRow[]
  log_len_msg?: number
  [k: string]: unknown
}

/** useLogTable 配置 */
export interface UseLogTableOpts {
  logType: LogType
  searchKeywordField?: LogDateField
  searchDateField?: LogDateField
  defaultPageSize?: number
  fixedParams?: Record<string, unknown> | (() => Record<string, unknown>)
}

/** useLogTable 返回值 */
export interface UseLogTableReturn {
  // 状态
  tableData: Ref<LogRow[]>
  loading: Ref<boolean>
  keyword: Ref<string>
  dateRange: Ref<[string, string] | [Date, Date] | null>
  page: Ref<number>
  pageSize: Ref<number>
  total: Ref<number>
  successCount: ComputedRef<number>
  failCount: ComputedRef<number>
  // 判定
  isSuccess: typeof isSuccess
  isFail: typeof isFail
  statusClass: typeof statusClass
  statusLabel: typeof statusLabel
  // 时间
  parseLogTime: typeof parseLogTime
  formatTimeRel: typeof formatTimeRel
  formatTimeAbs: typeof formatTimeAbs
  // 操作
  loadData: () => Promise<void>
  search: () => Promise<void>
  reset: () => void
  handleSizeChange: () => void
  handlePageChange: () => void
  exportLog: (filename: string, headers: string[], rowMap: (row: LogRow) => unknown[]) => void
  copyText: (text: string, msg?: string) => void
}

// Vue 3 computed Ref type
import type { ComputedRef } from 'vue'

/**
 * @param opts 配置项
 * @param opts.logType - 'command' | 'cz' | 'login'
 * @param opts.searchKeywordField - 'log_jg_date' | 'cz_jg_date' | 'login_jg_date'
 * @param opts.searchDateField - 'log_jg_date' | 'cz_jg_date' | 'login_jg_date'
 * @param opts.defaultPageSize - 默认 10
 */
export function useLogTable(opts: UseLogTableOpts): UseLogTableReturn {
  const {
    logType,
    searchKeywordField = 'log_jg_date',
    searchDateField = 'log_jg_date',
    defaultPageSize = 10,
    fixedParams,
  } = opts

  function getFixedParams(): Record<string, unknown> {
    return typeof fixedParams === 'function' ? fixedParams() : (fixedParams || {})
  }

  // ===== 响应式状态 =====
  const tableData: Ref<LogRow[]> = ref([])
  const loading: Ref<boolean> = ref(false)
  const keyword: Ref<string> = ref('')
  const dateRange: Ref<[string, string] | [Date, Date] | null> = ref(null)
  const page: Ref<number> = ref(1)
  const pageSize: Ref<number> = ref(defaultPageSize)
  const total: Ref<number> = ref(0)

  // ===== 状态判定（REV35-L3: 已抽离到 utils/logStatus.js，下面只是 re-import 引用） =====
  // isSuccess / isFail / statusClass / statusLabel 直接引用顶部 import

  // ===== 统计 =====
  const successCount: ComputedRef<number> = computed(() => tableData.value.filter((r) => isSuccess(r.log_status)).length)
  const failCount: ComputedRef<number> = computed(() => tableData.value.filter((r) => isFail(r.log_status)).length)

  // ===== 时间格式化（REV35-L1: 已抽离到 utils/datetime.js） =====
  // parseLogTime / formatTimeRel / formatTimeAbs 直接引用顶部 import

  // ===== 数据加载 =====
  async function loadData(): Promise<void> {
    loading.value = true
    try {
      const res = (await getLogs({
        ...getFixedParams(),
        log_type: logType,
        page: page.value,
        limit: pageSize.value,
      })) as unknown as LogListResponse
      if (res.log_list_msg) tableData.value = res.log_list_msg
      if (typeof res.log_len_msg === 'number') total.value = res.log_len_msg
    } finally { loading.value = false }
  }

  function _fmtDateTime(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
  }

  async function search(): Promise<void> {
    loading.value = true
    page.value = 1
    try {
      if (keyword.value) {
        const res = (await searchLogs({
          ...getFixedParams(),
          [searchKeywordField]: keyword.value,
          log_type: logType,
          page: page.value,
          limit: pageSize.value,
        })) as unknown as LogListResponse
        if (res.log_list_msg) tableData.value = res.log_list_msg
        if (typeof res.log_len_msg === 'number') total.value = res.log_len_msg
      } else if (dateRange.value && dateRange.value.length === 2) {
        const start = new Date(dateRange.value[0])
        const end = new Date(dateRange.value[1])
        const dateStr = _fmtDateTime(start) + ' - ' + _fmtDateTime(end)
        const res = (await getLogsByDate({
          ...getFixedParams(),
          [searchDateField]: dateStr,
          log_type: logType,
          page: page.value,
          limit: pageSize.value,
        })) as unknown as LogListResponse
        if (res.log_list_msg) tableData.value = res.log_list_msg
        if (typeof res.log_len_msg === 'number') total.value = res.log_len_msg
      } else { await loadData(); return }
    } finally { loading.value = false }
  }

  function reset(): void {
    keyword.value = ''
    dateRange.value = null
    page.value = 1
    loadData()
  }
  function handleSizeChange(): void { page.value = 1; loadData() }
  function handlePageChange(): void { loadData() }

  // ===== 导出 CSV =====
  /**
   * @param filename - 不含后缀，如 'command-log'
   * @param headers - CSV 表头
   * @param rowMap - 每行 CSV 字段映射
   */
  function exportLog(filename: string, headers: string[], rowMap: (row: LogRow) => unknown[]): void {
    if (!tableData.value.length) { ElMessage.warning(t('common.export.empty')); return }
    const rows: unknown[][] = tableData.value.map((r) => rowMap(r))
    const csv = '\ufeff' + [headers, ...rows].map((r) => r.map((c) => `"${(c == null ? '' : c).toString().replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(t('common.export.done', { n: rows.length }))
  }

  // ===== 复制（REV35-L2: 已抽离到 composables/useClipboard.js） =====
  const { copy: copyText } = useClipboard()

  return {
    // 状态
    tableData, loading, keyword, dateRange, page, pageSize, total,
    successCount, failCount,
    // 判定
    isSuccess, isFail, statusClass, statusLabel,
    // 时间
    parseLogTime, formatTimeRel, formatTimeAbs,
    // 操作
    loadData, search, reset, handleSizeChange, handlePageChange,
    exportLog, copyText,
  }
}
