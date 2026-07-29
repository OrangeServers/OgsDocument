<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <span class="page-eyebrow">AUDIT · LOGIN</span>
        <h2>{{ $t('menu.auditUserLog') }}</h2>
        <p>{{ $t('audit.login.desc') }} · <i18n-t keypath="audit.stats.total" tag="span" scope="global"><template #n><strong>{{ total }}</strong></template></i18n-t> · {{ $t('audit.stats.success') }} <strong class="num" style="color:var(--ogs-log-success)">{{ successCount }}</strong> · {{ $t('audit.stats.fail') }} <strong class="num" style="color:var(--ogs-log-fail)">{{ failCount }}</strong></p>
      </div>
      <div class="page-actions">
        <el-button @click="loadData">{{ $t('common.action.refresh') }}</el-button>
        <el-button type="primary" plain @click="exportLog('login-log', [$t('audit.csv.user'), $t('audit.csv.nwIp'), $t('audit.csv.gwIp'), $t('audit.csv.addr'), $t('audit.csv.device'), $t('audit.csv.status'), $t('audit.csv.reason'), $t('audit.csv.time')], r => [
          r.log_name, r.log_nw_ip, r.log_gw_ip, r.log_gw_cs, r.log_agent,
          statusLabel(r.log_status), r.log_reason, r.log_time
        ])"><el-icon :size="13"><Download /></el-icon>{{ $t('common.action.export') }}</el-button>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <span class="panel-icon"><el-icon :size="14"><Key /></el-icon></span>
        <span class="panel-title">{{ $t('menu.auditUserLog') }}</span>
        <span class="panel-sub">Login Trail</span>
      </div>
      <div class="list-toolbar">
        <el-input v-model="keyword" :placeholder="$t('audit.login.searchPlaceholder')" clearable class="search-input" :prefix-icon="Search" style="max-width:280px" @keyup.enter="search" />
        <el-date-picker v-model="dateRange" type="datetimerange" :range-separator="$t('audit.dateRange.to')" :start-placeholder="$t('audit.dateRange.start')" :end-placeholder="$t('audit.dateRange.end')" @change="search" style="width:380px" />
        <el-button @click="reset">{{ $t('common.action.reset') }}</el-button>
        <div class="stats">
          <i18n-t keypath="audit.stats.total" tag="span" class="num" scope="global"><template #n><strong>{{ total }}</strong></template></i18n-t>
          <span><span class="dot" style="background:var(--ogs-log-success)" />{{ $t('audit.stats.success') }} <strong class="num">{{ successCount }}</strong></span>
          <span v-if="failCount > 0"><span class="dot" style="background:var(--ogs-log-fail)" />{{ $t('audit.stats.fail') }} <strong class="num">{{ failCount }}</strong></span>
        </div>
      </div>
      <div class="panel-body" style="padding:0">
        <el-table :data="tableData" :class="['is-compact', 'is-critical-row']" stripe v-loading="loading" style="width:100%" :row-class-name="rowClassName">
        <el-table-column prop="log_name" :label="$t('audit.login.colUser')" min-width="130">
          <template #default="{ row }">
            <span style="font-weight:600;color:var(--ogs-text)">{{ row.log_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.login.colNwIp')" min-width="170">
          <template #default="{ row }">
            <div v-if="row.log_nw_ip" class="ip-pill-wrap" :class="{ 'is-host-expanded': isHostExpanded(row, 'nw') }">
              <span class="ip-pill" @click.stop="toggleHostExpand(row, 'nw')" :title="isHostExpanded(row, 'nw') ? $t('audit.login.clickCollapse') : $t('audit.login.clickExpand')">
                <el-icon :size="10"><Position /></el-icon><span class="ip-pill-text">{{ row.log_nw_ip }}</span>
              </span>
              <span class="ip-actions">
                <span class="ip-action is-toggle" :class="{ 'is-active': isHostExpanded(row, 'nw') }" :title="isHostExpanded(row, 'nw') ? $t('audit.login.collapse') : $t('audit.login.expandFull')" @click.stop="toggleHostExpand(row, 'nw')">
                  <el-icon :size="10">
                    <component :is="isHostExpanded(row, 'nw') ? ArrowUp : ArrowDown" />
                  </el-icon>
                </span>
                <span class="ip-action" :title="$t('audit.clickCopy')" @click.stop="copyText(row.log_nw_ip, $t('audit.copied', { text: row.log_nw_ip }))">
                  <el-icon :size="10"><CopyDocument /></el-icon>
                </span>
              </span>
            </div>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.login.colGwIp')" min-width="170">
          <template #default="{ row }">
            <div v-if="row.log_gw_ip" class="ip-pill-wrap" :class="{ 'is-host-expanded': isHostExpanded(row, 'gw') }">
              <span class="ip-pill" @click.stop="toggleHostExpand(row, 'gw')" :title="isHostExpanded(row, 'gw') ? $t('audit.login.clickCollapse') : $t('audit.login.clickExpand')">
                <el-icon :size="10"><Promotion /></el-icon><span class="ip-pill-text">{{ row.log_gw_ip }}</span>
              </span>
              <span class="ip-actions">
                <span class="ip-action is-toggle" :class="{ 'is-active': isHostExpanded(row, 'gw') }" :title="isHostExpanded(row, 'gw') ? $t('audit.login.collapse') : $t('audit.login.expandFull')" @click.stop="toggleHostExpand(row, 'gw')">
                  <el-icon :size="10">
                    <component :is="isHostExpanded(row, 'gw') ? ArrowUp : ArrowDown" />
                  </el-icon>
                </span>
                <span class="ip-action" :title="$t('audit.clickCopy')" @click.stop="copyText(row.log_gw_ip, $t('audit.copied', { text: row.log_gw_ip }))">
                  <el-icon :size="10"><CopyDocument /></el-icon>
                </span>
              </span>
            </div>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.login.colAddr')" min-width="110">
          <template #default="{ row }">
            <span v-if="row.log_gw_cs" style="color:var(--ogs-text-secondary)">{{ row.log_gw_cs }}</span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.login.colDevice')" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="ua-cell">
              <span class="ua-os">{{ parseOS(row.log_agent) }}</span>
              <span>{{ parseBrowser(row.log_agent) }}</span>
            </span>
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
        <el-table-column :label="$t('audit.login.colTime')" width="120" sortable :sort-by="sortByLogTime">
          <template #default="{ row }">
            <span class="time-cell">
              <span class="time-rel">{{ formatTimeRel(row.log_time) }}</span>
              <span class="time-abs">{{ formatTimeAbs(row.log_time) }}</span>
            </span>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state">
            <el-icon :size="40" style="color:var(--ogs-text-muted)"><Key /></el-icon>
            <p>{{ $t('audit.login.empty') }}</p>
            <span>{{ $t('audit.login.emptyHint') }}</span>
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
import { ref, onMounted } from 'vue'
import { t } from '@/i18n'
import { Search, Download, Position, Promotion, ArrowDown, ArrowUp, CopyDocument } from '@element-plus/icons-vue'
import { useLogTable, type LogRow } from '@/composables/useLogTable'

const {
  tableData, loading, keyword, dateRange, page, pageSize, total,
  successCount, failCount,
  statusClass, statusLabel,
  formatTimeRel, formatTimeAbs,
  loadData, search, reset, handleSizeChange, handlePageChange,
  exportLog, copyText,
} = useLogTable({
  logType: 'login',
  searchKeywordField: 'login_jg_date',
  searchDateField: 'login_jg_date',
})

/** IP 展开状态：nw=内网IP，gw=公网IP，value=tableData 索引集合 */
interface ExpandedHostIds {
  nw: Set<number>
  gw: Set<number>
}

// REV33-M4: 此页面特有 — IP 展开状态跟踪（内网IP / 公网IP 各自维护一套，与 ip-pill-wrap 联动）
const expandedHostIds = ref<ExpandedHostIds>({ nw: new Set<number>(), gw: new Set<number>() })

function toggleHostExpand(row: LogRow, key: 'nw' | 'gw'): void {
  const idx = tableData.value.indexOf(row)
  if (idx < 0) return
  const next: ExpandedHostIds = { nw: new Set(expandedHostIds.value.nw), gw: new Set(expandedHostIds.value.gw) }
  const set = next[key]
  if (set.has(idx)) set.delete(idx)
  else set.add(idx)
  expandedHostIds.value = next
}

function isHostExpanded(row: LogRow, key: 'nw' | 'gw'): boolean {
  const idx = tableData.value.indexOf(row)
  return idx >= 0 && expandedHostIds.value[key].has(idx)
}

function resetHostExpand(): void { expandedHostIds.value = { nw: new Set<number>(), gw: new Set<number>() } }

function rowClassName({ row, rowIndex }: { row: LogRow; rowIndex: number }): string {
  const classes: string[] = []
  if (statusClass(row.log_status) === 'is-fail') classes.push('is-critical')
  if ((expandedHostIds.value.nw.has(rowIndex)) || (expandedHostIds.value.gw.has(rowIndex))) classes.push('is-host-row-expanded')
  return classes.join(' ')
}

function sortByLogTime(row: LogRow): string {
  return String(row.log_time || '')
}

function parseOS(ua: string): string {
  if (!ua) return '?'
  if (/Windows NT 10/.test(ua)) return 'Win10/11'
  if (/Windows NT 6\.3/.test(ua)) return 'Win8.1'
  if (/Windows NT 6\.1/.test(ua)) return 'Win7'
  if (/Windows/.test(ua)) return 'Windows'
  if (/Mac OS X/.test(ua)) return 'macOS'
  if (/iPhone|iPad|iOS/.test(ua)) return 'iOS'
  if (/Android/.test(ua)) return 'Android'
  if (/Linux/.test(ua)) return 'Linux'
  return 'Other'
}
function parseBrowser(ua: string): string {
  if (!ua) return t('common.status.unknown')
  if (/Edg\//.test(ua)) return 'Edge'
  if (/Chrome\//.test(ua) && !/Chromium/.test(ua)) return 'Chrome'
  if (/Firefox\//.test(ua)) return 'Firefox'
  if (/Safari\//.test(ua) && !/Chrome/.test(ua)) return 'Safari'
  if (/curl|wget|postman|httpclient|python-requests/i.test(ua)) return 'API/CLI'
  // REV35-L8: 清理控制字符 + 限制长度，防 UA 污染表格
  return String(ua).replace(/[^\x20-\x7E]/g, '').slice(0, 40)
}

onMounted(loadData)
</script>
