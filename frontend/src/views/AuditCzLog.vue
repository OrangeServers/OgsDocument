<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <span class="page-eyebrow">AUDIT · OPERATION</span>
        <h2>{{ $t('menu.auditCzLog') }}</h2>
        <p>{{ $t('audit.cz.desc') }} · <i18n-t keypath="audit.stats.total" tag="span" scope="global"><template #n><strong>{{ total }}</strong></template></i18n-t> · {{ $t('audit.stats.success') }} <strong class="num" style="color:var(--ogs-log-success)">{{ successCount }}</strong> · {{ $t('audit.stats.fail') }} <strong class="num" style="color:var(--ogs-log-fail)">{{ failCount }}</strong></p>
      </div>
      <div class="page-actions">
        <el-button @click="loadData">{{ $t('common.action.refresh') }}</el-button>
        <el-button type="primary" plain @click="exportLog('op-log', [$t('audit.csv.user'), $t('audit.csv.type'), $t('audit.csv.info'), $t('audit.csv.details'), $t('audit.csv.status'), $t('audit.csv.reason'), $t('audit.csv.time')], r => [
          r.log_name, r.log_type, r.log_info, r.log_details,
          statusLabel(r.log_status),
          r.log_reason, r.log_time
        ])">
          <el-icon :size="13"><Download /></el-icon>{{ $t('common.action.export') }}
        </el-button>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <span class="panel-icon"><el-icon :size="14"><EditPen /></el-icon></span>
        <span class="panel-title">{{ $t('menu.auditCzLog') }}</span>
        <span class="panel-sub">Operation Trail</span>
      </div>
      <div class="list-toolbar">
        <el-input v-model="keyword" :placeholder="$t('audit.cz.searchPlaceholder')" clearable class="search-input" :prefix-icon="Search" style="max-width:280px" @keyup.enter="search" />
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
        <el-table-column prop="log_name" :label="$t('audit.cz.colUser')" min-width="110">
          <template #default="{ row }">
            <span style="font-weight:600;color:var(--ogs-text)">{{ row.log_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.cz.colType')" width="130">
          <template #default="{ row }">
            <span v-if="row.log_type" :class="['group-tag', typeClass(row.log_type)]">{{ row.log_type }}</span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.cz.colDetail')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.log_info" style="color:var(--ogs-text)">{{ row.log_info }}</span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('audit.cz.colDetails')" min-width="220">
          <template #default="{ row }">
            <el-popover
              v-if="row.log_details"
              :width="520"
              placement="bottom-start"
              :show-arrow="false"
              trigger="click"
              :hide-after="0"
              popper-class="cmd-popover"
              :offset="6"
            >
              <template #reference>
                <div class="cmd-expandable" :title="$t('audit.cz.clickViewFullDetails')" @click.stop>
                  <span class="cmd-text">{{ row.log_details }}</span>
                  <span class="cmd-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><Memo /></el-icon>
                    <span>{{ $t('audit.cz.detailsTitle') }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><User /></el-icon>{{ row.log_name || '—' }}
                    </span>
                    <span v-if="row.log_info" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.log_info }}
                    </span>
                    <span v-if="row.log_type" class="cmd-popover-chip">
                      <el-icon :size="10"><EditPen /></el-icon>{{ row.log_type }}
                    </span>
                    <span class="cmd-popover-chip">
                      <el-icon :size="10"><Clock /></el-icon>{{ formatTimeAbs(row.log_time) || row.log_time || '—' }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content">
                  <pre class="cmd-popover-pre">{{ row.log_details }}</pre>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('audit.popoverCloseTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(row.log_details, $t('audit.cz.detailsCopied'))">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('audit.cz.copyDetails') }}</span>
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
        <el-table-column :label="$t('audit.cz.colTime')" width="120" sortable>
          <template #default="{ row }">
            <span class="time-cell">
              <span class="time-rel">{{ formatTimeRel(row.log_time) }}</span>
              <span class="time-abs">{{ formatTimeAbs(row.log_time) }}</span>
            </span>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state">
            <el-icon :size="40" style="color:var(--ogs-text-muted)"><EditPen /></el-icon>
            <p>{{ $t('audit.cz.empty') }}</p>
            <span>{{ $t('audit.cz.emptyHint') }}</span>
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
import { onMounted } from 'vue'
import { Search, Download, ZoomIn, Memo, User, Clock, Document, EditPen, InfoFilled, CopyDocument } from '@element-plus/icons-vue'
import { useLogTable, type LogRow } from '@/composables/useLogTable'

const {
  tableData, loading, keyword, dateRange, page, pageSize, total,
  successCount, failCount,
  statusClass, statusLabel,
  formatTimeRel, formatTimeAbs,
  loadData, search, reset, handleSizeChange, handlePageChange,
  exportLog, copyText,
} = useLogTable({
  logType: 'cz',
  searchKeywordField: 'cz_jg_date',
  searchDateField: 'cz_jg_date',
})

function typeClass(type: string): string {
  const s = (type || '').toLowerCase()
  if (/add|create|insert|新建|创建/.test(s)) return 'is-test' // i18n-ignore
  if (/update|edit|modify|修改|更新/.test(s)) return 'is-staging' // i18n-ignore
  if (/delete|del|remove|删除|移除/.test(s)) return 'is-prod' // i18n-ignore
  if (/login|logout|认证|授权/.test(s)) return 'is-cache' // i18n-ignore
  return 'is-other'
}

function rowClassName({ row }: { row: LogRow }): string {
  return statusClass(row.log_status) === 'is-fail' ? 'is-critical' : ''
}

onMounted(loadData)
</script>