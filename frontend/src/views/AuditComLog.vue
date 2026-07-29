<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <span class="page-eyebrow">AUDIT · COMMAND</span>
        <h2>{{ $t('menu.auditComLog') }}</h2>
        <p>{{ $t('audit.com.desc') }} · <i18n-t keypath="audit.stats.total" tag="span" scope="global"><template #n><strong>{{ total }}</strong></template></i18n-t> · {{ $t('audit.stats.success') }} <strong class="num" style="color:var(--ogs-log-success)">{{ successCount }}</strong> · {{ $t('audit.stats.fail') }} <strong class="num" style="color:var(--ogs-log-fail)">{{ failCount }}</strong> · {{ $t('audit.stats.danger') }} <strong class="num" style="color:var(--ogs-critical)">{{ dangerCount }}</strong></p>
      </div>
      <div class="page-actions">
        <el-button @click="loadData">{{ $t('common.action.refresh') }}</el-button>
        <el-button type="primary" plain @click="exportLog('command-log', [$t('audit.csv.user'), $t('audit.csv.type'), $t('audit.csv.host'), $t('audit.csv.command'), $t('audit.csv.status'), $t('audit.csv.reason'), $t('audit.csv.time')], r => [
          r.log_name, r.log_type, r.log_host, r.log_info,
          statusLabel(r.log_status), r.log_reason, r.log_time
        ])"><el-icon :size="13"><Download /></el-icon>{{ $t('common.action.export') }}</el-button>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <span class="panel-icon"><el-icon :size="14"><Document /></el-icon></span>
        <span class="panel-title">{{ $t('menu.auditComLog') }}</span>
        <span class="panel-sub">Command Trail</span>
      </div>
      <div class="list-toolbar">
        <template v-if="auditRef">
          <el-tag type="warning" effect="plain">{{ $t('audit.com.aiRefLocated') }}</el-tag>
          <el-button @click="clearAuditRef">{{ $t('audit.com.viewAllLogs') }}</el-button>
        </template>
        <template v-else>
          <el-input v-model="keyword" :placeholder="$t('audit.com.searchPlaceholder')" clearable class="search-input" :prefix-icon="Search" style="max-width:280px" @keyup.enter="search" />
          <el-date-picker v-model="dateRange" type="datetimerange" :range-separator="$t('audit.dateRange.to')" :start-placeholder="$t('audit.dateRange.start')" :end-placeholder="$t('audit.dateRange.end')" @change="search" style="width:380px" />
          <el-button @click="reset">{{ $t('common.action.reset') }}</el-button>
        </template>
        <div class="stats">
          <i18n-t keypath="audit.stats.total" tag="span" class="num" scope="global"><template #n><strong>{{ total }}</strong></template></i18n-t>
          <span><span class="dot" style="background:var(--ogs-log-success)" />{{ $t('audit.stats.success') }} <strong class="num">{{ successCount }}</strong></span>
          <span v-if="failCount > 0"><span class="dot" style="background:var(--ogs-log-fail)" />{{ $t('audit.stats.fail') }} <strong class="num">{{ failCount }}</strong></span>
          <span v-if="dangerCount > 0"><span class="dot" style="background:var(--ogs-critical)" />{{ $t('audit.stats.danger') }} <strong class="num">{{ dangerCount }}</strong></span>
        </div>
      </div>
      <div class="panel-body" style="padding:0">
        <el-table :data="tableData" :class="['is-compact', 'is-critical-row']" stripe v-loading="loading" style="width:100%" :row-class-name="rowClassName">
        <el-table-column prop="log_name" :label="$t('audit.com.colUser')" min-width="110">
          <template #default="{ row }">
            <span style="font-weight:600;color:var(--ogs-text)">{{ row.log_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.com.colType')" width="120">
          <template #default="{ row }">
            <span v-if="row.log_type" :class="['group-tag', typeClass(row.log_type)]">{{ row.log_type }}</span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.com.colAsset')" min-width="200">
          <template #default="{ row }">
            <el-popover
              v-if="row.log_host"
              :width="480"
              placement="bottom-start"
              :show-arrow="false"
              trigger="click"
              :hide-after="0"
              popper-class="cmd-popover ip-popover"
              :offset="6"
            >
              <template #reference>
                <div class="ip-pill-wrap" :title="memoParseHostList(row.log_host).length > 1 ? $t('audit.com.clickViewAllHosts') : ''" @click.stop>
                  <span class="ip-pill">
                    <el-icon :size="10"><Monitor /></el-icon>
                    <span class="ip-pill-text">{{ memoParseHostList(row.log_host)[0] }}</span>
                  </span>
                  <span v-if="memoParseHostList(row.log_host).length > 1" class="ip-pill-more" :title="$t('audit.com.moreHosts', { n: memoParseHostList(row.log_host).length - 1 })">
                    +{{ memoParseHostList(row.log_host).length - 1 }}
                  </span>
                  <span class="ip-pill-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><Monitor /></el-icon>
                    <span>{{ $t('audit.com.colAsset') }}</span>
                    <span class="cmd-popover-badge cmd-popover-badge--ghost">{{ $t('audit.hostUnit', { n: memoParseHostList(row.log_host).length }) }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><User /></el-icon>{{ row.log_name || '—' }}
                    </span>
                    <span v-if="row.log_type" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.log_type }}
                    </span>
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><Clock /></el-icon>{{ formatTimeAbs(row.log_time) || row.log_time || '—' }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content">
                  <ul class="ip-popover-list">
                    <li v-for="(h, i) in memoParseHostList(row.log_host)" :key="i" class="ip-popover-item">
                      <span class="ip-popover-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                      <el-icon :size="11" class="ip-popover-ico"><Monitor /></el-icon>
                      <span class="ip-popover-name">{{ h }}</span>
                      <span class="ip-popover-copy" :title="$t('audit.com.copyHostTitle')" @click.stop="copyText(h, $t('audit.copiedHost', { name: h }))">
                        <el-icon :size="10"><CopyDocument /></el-icon>
                      </span>
                    </li>
                  </ul>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('audit.popoverCloseTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(row.log_host, $t('audit.copied', { text: row.log_host }))">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('audit.copyAll') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
            <span v-else-if="batchTargetLabel(row)" class="ip-pill">
              <el-icon :size="10"><Monitor /></el-icon>
              <span class="ip-pill-text">{{ batchTargetLabel(row) }}</span>
            </span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.com.colDetail')" min-width="220">
          <template #default="{ row }">
            <el-popover
              v-if="row.log_info"
              :width="520"
              placement="bottom-start"
              :show-arrow="false"
              trigger="click"
              :hide-after="0"
              popper-class="cmd-popover"
              :offset="6"
            >
              <template #reference>
                <div
                  :class="['cmd-expandable', { 'is-danger': isDangerCommand(row.log_info) }]"
                  :title="$t('audit.com.clickViewFullCmd')"
                  @click.stop
                >
                  <el-icon v-if="isDangerCommand(row.log_info)" :size="11" class="cmd-icon"><Warning /></el-icon>
                  <span class="cmd-text">{{ row.log_info }}</span>
                  <span class="cmd-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head" :class="{ 'is-danger': isDangerCommand(row.log_info) }">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><Memo /></el-icon>
                    <span>{{ $t('audit.com.cmdDetailTitle') }}</span>
                    <span v-if="isDangerCommand(row.log_info)" class="cmd-popover-badge">{{ $t('audit.com.dangerCmd') }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><User /></el-icon>{{ row.log_name || '—' }}
                    </span>
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><Monitor /></el-icon>{{ row.log_host || batchTargetLabel(row) || '—' }}
                    </span>
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><Clock /></el-icon>{{ formatTimeAbs(row.log_time) || row.log_time || '—' }}
                    </span>
                    <span v-if="row.log_type" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.log_type }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content" :class="{ 'is-danger': isDangerCommand(row.log_info) }">
                  <pre class="cmd-popover-pre">{{ row.log_info }}</pre>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('audit.popoverCloseTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(row.log_info, $t('audit.com.cmdCopied'))">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('audit.com.copyCmd') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.col.status')" width="90" align="center">
          <template #default="{ row }">
            <span :class="['log-status', statusClass(row.log_status)]">{{ statusLabel(row.log_status) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.col.reason')" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.log_reason" style="color:var(--ogs-text-secondary)">{{ row.log_reason }}</span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.com.colTime')" width="120" sortable>
          <template #default="{ row }">
            <span class="time-cell">
              <span class="time-rel">{{ formatTimeRel(row.log_time) }}</span>
              <span class="time-abs">{{ formatTimeAbs(row.log_time) }}</span>
            </span>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state">
            <el-icon :size="40" style="color:var(--ogs-text-muted)"><Document /></el-icon>
            <p>{{ auditRef ? $t('audit.com.emptyAiRef') : $t('audit.com.empty') }}</p>
            <span>{{ auditRef ? $t('audit.com.emptyAiRefHint') : $t('audit.com.emptyHint') }}</span>
          </div>
        </template>
        </el-table>
      </div>
      <div class="list-pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// REV33-M4: 抽取公共状态 / 时间格式化 / 数据加载 / 导出 / 复制 到 useLogTable composable
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { t } from '@/i18n'
import { Search, Download, Monitor, Warning, CopyDocument, ZoomIn, Memo, User, Clock, Document, InfoFilled } from '@element-plus/icons-vue'
import { parseHostList } from '@/utils/host'
import { useLogTable, type LogRow } from '@/composables/useLogTable'
// REV35-L4: 危险命令检测抽到 utils/danger
import { isDangerCommand } from '@/utils/danger'

const route = useRoute()
const router = useRouter()
const auditRef = computed<string>(() => (
  typeof route.query.audit_ref === 'string'
    ? route.query.audit_ref.trim().slice(0, 160)
    : ''
))

const {
  tableData, loading, keyword, dateRange, page, pageSize, total,
  successCount, failCount,
  statusClass, statusLabel,
  formatTimeRel, formatTimeAbs,
  loadData, search, reset, handleSizeChange, handlePageChange,
  exportLog, copyText,
} = useLogTable({
  logType: 'command',
  searchKeywordField: 'log_jg_date',
  searchDateField: 'log_jg_date',
  fixedParams: () => auditRef.value ? { audit_ref: auditRef.value } : {},
})

function clearAuditRef(): void {
  void router.replace({ path: '/log-exec' })
}

// REV33-M4: 此页面特有 - 危险命令统计 + 行标记
function typeClass(type: string): string {
  const t = (type || '').toLowerCase()
  if (/exec|run|cmd|bash|shell/.test(t)) return 'is-prod'
  if (/upload|put|write/.test(t)) return 'is-staging'
  if (/download|get|fetch/.test(t)) return 'is-test'
  if (/delete|rm|drop/.test(t)) return 'is-cache'
  return 'is-other'
}

// REV35-L7: parseHostList 多次调用 memoize（模板内调用 5+ 次/行，原始调用会重新 split + 去重）
//   Map<hostStr, string[]> - 同输入跳过重新计算
const _hostCache: Map<string, string[]> = new Map()
function memoParseHostList(s: string | string[] | null | undefined): string[] {
  if (s == null) return []
  const key: string = Array.isArray(s) ? s.join('|') : String(s)
  const cached = _hostCache.get(key)
  if (cached) return cached
  const out = parseHostList(s)
  // 简单 LRU: 超过 1000 项清空，防内存堆积
  if (_hostCache.size > 1000) _hostCache.clear()
  _hostCache.set(key, out)
  return out
}

function batchTargetLabel(row: LogRow): string {
  if (row.log_type !== 'AI 批量命令' && row.log_type !== '批量命令') return '' // i18n-ignore
  const matched = String(row.log_reason || '').match(/(?:^|;\s*)targets=(\d{1,3})(?:;|$)/)
  return matched ? t('audit.com.batchHosts', { n: matched[1] }) : t('audit.com.batchAssets')
}

const dangerCount = computed<number>(() => tableData.value.filter(r => isDangerCommand(typeof r.log_info === 'string' ? r.log_info : null)).length)

function rowClassName({ row }: { row: LogRow }): string {
  const classes: string[] = []
  if (statusClass(row.log_status) === 'is-fail') classes.push('is-critical')
  if (isDangerCommand(typeof row.log_info === 'string' ? row.log_info : null)) classes.push('is-warn')
  return classes.join(' ')
}

// 主机名解析：详见 @/utils/host（兼容字符串与数组两种后端字段）
// REV35-L7: 模板中使用 memoParseHostList 减少重复调用

watch(
  () => route.query.audit_ref,
  () => {
    page.value = 1
    void loadData()
  },
)
onMounted(loadData)
</script>
