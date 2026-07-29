<template>
  <article class="diagnostic-card" :class="`status-${run.status}`" aria-live="polite">
    <header class="diagnostic-head">
      <span class="diagnostic-mark">
        <el-icon v-if="isActive" class="is-loading"><Loading /></el-icon>
        <el-icon v-else-if="isSuccessful"><CircleCheckFilled /></el-icon>
        <el-icon v-else><WarningFilled /></el-icon>
      </span>
      <div class="diagnostic-title">
        <span>READ-ONLY DIAGNOSTIC</span>
        <h3>{{ run.profile_name || $t('ai.diagnostic.defaultProfile') }}</h3>
      </div>
      <el-tag :type="statusTagType" effect="light">{{ statusLabel }}</el-tag>
    </header>

    <div v-if="isHighPrivilege" class="privilege-warning" role="note">
      <el-icon><WarningFilled /></el-icon>
      <span>
        {{ $t('ai.diagnostic.privilegeBefore') }} <b>{{ run.system_user?.alias || 'root' }}</b>{{ $t('ai.diagnostic.privilegeAfter') }}
      </span>
    </div>

    <div class="diagnostic-progress">
      <div class="progress-copy">
        <span>{{ isActive ? $t('ai.diagnostic.collecting') : progressTitle }}</span>
        <b>{{ progressPercent }}%</b>
      </div>
      <el-progress
        :percentage="progressPercent"
        :show-text="false"
        :stroke-width="6"
        :status="progressStatus"
      />
      <div class="progress-facts">
        <span><b>{{ targetCount }}</b> {{ $t('ai.diagnostic.targets') }}</span>
        <span class="is-complete"><b>{{ completedCount }}</b> {{ $t('ai.diagnostic.completed') }}</span>
        <span :class="{ 'is-failed': failedCount > 0 }"><b>{{ failedCount }}</b> {{ $t('ai.diagnostic.failed') }}</span>
        <span><b>{{ run.summary?.evidence_count || 0 }}</b> {{ $t('ai.diagnostic.evidenceUnit') }}</span>
      </div>
    </div>

    <div v-if="assetRows.length" class="asset-progress" :aria-label="$t('ai.diagnostic.assetAria')">
      <div
        v-for="asset in assetRows"
        :key="`${asset.target_id || ''}-${asset.alias}`"
        class="asset-row"
      >
        <span class="asset-state" :class="`is-${asset.status}`" />
        <code>{{ asset.alias }}</code>
        <span class="asset-probes">
          {{ asset.completed_probes ?? (asset.status === 'completed' ? asset.total_probes : 0) }}
          <template v-if="asset.total_probes != null">/{{ asset.total_probes }}</template>
        </span>
        <span class="asset-label" :title="asset.error || ''">
          {{ asset.error || assetStatusLabel(asset.status) }}
        </span>
      </div>
    </div>

    <section v-if="run.report" class="diagnostic-report">
      <div class="report-heading">
        <span>{{ $t('ai.diagnostic.conclusion') }}</span>
        <span v-if="severityLabel" class="confidence">{{ severityLabel }}</span>
      </div>
      <template v-if="hasFindings">
        <p class="report-conclusion">
          {{ run.report.summary || $t('ai.diagnostic.conclusionFallback') }}
        </p>
        <ul class="finding-list">
          <li v-for="(finding, index) in run.report.findings?.slice(0, 3)" :key="finding.id || index">
            <span :class="`severity-${finding.severity || 'info'}`" />
            <div>
              <strong>{{ finding.title }}</strong>
              <small v-if="finding.summary">{{ finding.summary }}</small>
            </div>
          </li>
        </ul>
      </template>
      <div v-else-if="run.report.evidence_insufficient" class="insufficient-evidence">
        <el-icon><DocumentChecked /></el-icon>
        <div>
          <strong>{{ $t('ai.diagnostic.insufficientTitle') }}</strong>
          <span>{{ $t('ai.diagnostic.insufficientDesc') }}</span>
        </div>
      </div>
      <div v-else class="healthy-evidence">
        <el-icon><CircleCheckFilled /></el-icon>
        <div>
          <strong>{{ $t('ai.diagnostic.healthyTitle') }}</strong>
          <span>{{ $t('ai.diagnostic.healthyDesc') }}</span>
        </div>
      </div>
    </section>

    <p v-if="run.error" class="diagnostic-error">{{ run.error }}</p>

    <footer class="diagnostic-actions">
      <span>{{ updatedLabel }}</span>
      <div>
        <el-button
          v-if="isActive"
          text
          size="small"
          @click="$emit('cancel', run)"
        >{{ $t('ai.diagnostic.cancel') }}</el-button>
        <el-button
        :disabled="!run.summary?.evidence_count"
          plain
          size="small"
          @click="$emit('open-evidence', run)"
        >
          {{ $t('ai.diagnostic.viewEvidence') }}
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowRight,
  CircleCheckFilled,
  DocumentChecked,
  Loading,
  WarningFilled,
} from '@element-plus/icons-vue'
import { currentLocale, t } from '@/i18n'
import type {
  AiDiagnosticAssetStatus,
  AiDiagnosticRun,
} from '@/types/ai'

const props = defineProps<{ run: AiDiagnosticRun }>()

defineEmits<{
  cancel: [run: AiDiagnosticRun]
  'open-evidence': [run: AiDiagnosticRun]
}>()

const isActive = computed(() => ['queued', 'running'].includes(props.run.status))
const isSuccessful = computed(() => props.run.status === 'completed')
const assetRows = computed(() => props.run.asset_progress || [])
const targetCount = computed(() => props.run.target_count || assetRows.value.length)
const completedCount = computed(() =>
  props.run.success_count
  ?? assetRows.value.filter(item => item.status === 'completed').length,
)
const failedCount = computed(() =>
  props.run.failed_count
  ?? assetRows.value.filter(item => item.status === 'failed').length,
)
const progressPercent = computed(() => {
  if (props.run.status === 'completed') return 100
  if (!targetCount.value) return isActive.value ? 4 : 100
  return Math.min(100, Math.round(
    ((completedCount.value + failedCount.value) / targetCount.value) * 100,
  ))
})
const hasFindings = computed(() =>
  !props.run.report?.evidence_insufficient
  && Boolean(props.run.report?.findings?.length),
)
const isHighPrivilege = computed(() =>
  props.run.system_user?.is_privileged === true
  || /^root(?:$|@)/i.test(props.run.system_user?.alias || ''),
)
const severityLabel = computed(() => {
  const severity = props.run.report?.severity || props.run.summary?.severity
  if (!severity) return ''
  const labels: Record<string, string> = {
    info: t('ai.severity.info'),
    warning: t('ai.severity.warning'),
    high: t('ai.severity.high'),
    critical: t('ai.severity.critical'),
  }
  return t('ai.diagnostic.severityLine', { label: labels[severity] || severity })
})
const progressStatus = computed<'success' | 'exception' | undefined>(() => {
  if (props.run.status === 'completed') return 'success'
  if (props.run.status === 'failed') return 'exception'
  return undefined
})
const statusTagType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  if (props.run.status === 'completed') return 'success'
  if (['failed', 'interrupted'].includes(props.run.status)) return 'danger'
  if (['cancelled', 'expired'].includes(props.run.status)) return 'info'
  return 'warning'
})
const statusLabel = computed(() => ({
  queued: t('ai.diagnostic.status.queued'),
  running: t('ai.diagnostic.status.running'),
  completed: t('ai.diagnostic.status.completed'),
  partial: t('ai.diagnostic.status.partial'),
  failed: t('ai.diagnostic.status.failed'),
  cancelled: t('ai.diagnostic.status.cancelled'),
  interrupted: t('ai.diagnostic.status.interrupted'),
  expired: t('ai.diagnostic.status.expired'),
}[props.run.status]))
const progressTitle = computed(() => ({
  queued: t('ai.diagnostic.progress.queued'),
  running: t('ai.diagnostic.progress.running'),
  completed: t('ai.diagnostic.progress.completed'),
  partial: t('ai.diagnostic.progress.partial'),
  failed: t('ai.diagnostic.progress.failed'),
  cancelled: t('ai.diagnostic.progress.cancelled'),
  interrupted: t('ai.diagnostic.progress.interrupted'),
  expired: t('ai.diagnostic.progress.expired'),
} satisfies Record<AiDiagnosticRun['status'], string>)[props.run.status])
const updatedLabel = computed(() => {
  if (!props.run.updated_at) return t('ai.diagnostic.runId', { id: props.run.id.slice(0, 8) })
  const date = new Date(props.run.updated_at)
  if (Number.isNaN(date.getTime())) return t('ai.diagnostic.runId', { id: props.run.id.slice(0, 8) })
  return t('ai.diagnostic.updatedAt', {
    time: new Intl.DateTimeFormat(currentLocale(), {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(date),
  })
})

function assetStatusLabel(status: AiDiagnosticAssetStatus): string {
  return {
    queued: t('ai.diagnostic.assetStatus.queued'),
    running: t('ai.diagnostic.assetStatus.running'),
    completed: t('ai.diagnostic.assetStatus.completed'),
    failed: t('ai.diagnostic.assetStatus.failed'),
    skipped: t('ai.diagnostic.assetStatus.skipped'),
  }[status]
}
</script>

<style scoped>
.diagnostic-card {
  width: calc(100% - 40px);
  margin-left: 40px;
  overflow: hidden;
  border: 1px solid var(--ogs-border);
  border-top: 3px solid var(--ogs-primary);
  border-radius: 12px;
  background: var(--ogs-surface, #fff);
  box-shadow: 0 10px 28px rgb(15 23 42 / 5%);
}
.diagnostic-card.status-completed { border-top-color: var(--ogs-success); }
.diagnostic-card.status-failed,
.diagnostic-card.status-interrupted { border-top-color: var(--ogs-danger); }
.diagnostic-head {
  min-height: 65px;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ogs-border-subtle);
}
.diagnostic-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: var(--ogs-primary);
  background: var(--ogs-primary-soft);
}
.status-completed .diagnostic-mark { color: var(--ogs-success); background: rgb(16 185 129 / 9%); }
.status-failed .diagnostic-mark,
.status-interrupted .diagnostic-mark { color: var(--ogs-danger); background: rgb(239 68 68 / 9%); }
.diagnostic-title { min-width: 0; }
.diagnostic-title > span {
  color: var(--ogs-primary);
  font-family: var(--ogs-mono);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .13em;
}
.diagnostic-title h3 {
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--ogs-text);
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.privilege-warning {
  margin: 12px 16px 0;
  padding: 9px 11px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  color: #9a3412;
  background: #fff7ed;
  font-size: 11px;
  line-height: 1.5;
}
[data-theme="black"] .privilege-warning {
  background: rgba(251, 146, 60, 0.08);
  border-color: rgba(251, 146, 60, 0.25);
  color: #fdba74;
}
.privilege-warning .el-icon { margin-top: 2px; flex: 0 0 auto; }
.diagnostic-progress { padding: 14px 16px 12px; }
.progress-copy { display: flex; justify-content: space-between; margin-bottom: 8px; color: var(--ogs-text-secondary); font-size: 11px; }
.progress-copy b { color: var(--ogs-text); font-family: var(--ogs-mono); }
.progress-facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; margin-top: 11px; }
.progress-facts span { color: var(--ogs-text-muted); font-size: 9px; text-align: center; }
.progress-facts b { display: block; color: var(--ogs-text); font-family: var(--ogs-mono); font-size: 15px; }
.progress-facts .is-complete b { color: var(--ogs-success); }
.progress-facts .is-failed b { color: var(--ogs-danger); }
.asset-progress {
  margin: 0 16px 14px;
  overflow: hidden;
  border: 1px solid var(--ogs-border-subtle);
  border-radius: 8px;
}
.asset-row {
  min-height: 34px;
  display: grid;
  grid-template-columns: 7px minmax(0, 1fr) auto minmax(50px, 140px);
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border-bottom: 1px solid var(--ogs-border-subtle);
  font-size: 10px;
}
.asset-row:last-child { border-bottom: 0; }
.asset-row code { overflow: hidden; color: var(--ogs-text-secondary); text-overflow: ellipsis; white-space: nowrap; }
.asset-state { width: 7px; height: 7px; border-radius: 50%; background: var(--ogs-text-muted); }
.asset-state.is-running { background: var(--ogs-info); box-shadow: 0 0 0 3px rgb(59 130 246 / 10%); }
.asset-state.is-completed { background: var(--ogs-success); }
.asset-state.is-failed { background: var(--ogs-danger); }
.asset-probes { color: var(--ogs-text-muted); font-family: var(--ogs-mono); }
.asset-label { overflow: hidden; color: var(--ogs-text-secondary); text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.diagnostic-report { padding: 14px 16px; border-top: 1px solid var(--ogs-border-subtle); background: var(--ogs-bg-soft, #fafafa); }
.report-heading { display: flex; align-items: center; justify-content: space-between; color: var(--ogs-text-muted); font-size: 10px; font-weight: 700; }
.confidence { color: var(--ogs-success); font-family: var(--ogs-mono); }
.report-conclusion { margin: 8px 0 0; color: var(--ogs-text); font-size: 12px; line-height: 1.65; }
.report-impact { margin: 7px 0 0; color: var(--ogs-text-secondary); font-size: 10px; }
.report-impact b { margin-right: 8px; color: var(--ogs-text); }
.finding-list { margin: 10px 0 0; padding: 0; list-style: none; }
.finding-list li { display: grid; grid-template-columns: 7px minmax(0, 1fr); gap: 8px; padding: 7px 0; border-top: 1px solid var(--ogs-border-subtle); }
.finding-list li > span { width: 7px; height: 7px; margin-top: 5px; border-radius: 2px; background: var(--ogs-info); }
.finding-list li > span.severity-warning { background: var(--ogs-warning); }
.finding-list li > span.severity-high,
.finding-list li > span.severity-critical { background: var(--ogs-danger); }
.finding-list strong,
.finding-list small { display: block; }
.finding-list strong { color: var(--ogs-text); font-size: 11px; }
.finding-list small { margin-top: 2px; color: var(--ogs-text-secondary); font-size: 10px; line-height: 1.5; }
.insufficient-evidence { display: flex; gap: 10px; margin-top: 10px; color: var(--ogs-text-secondary); }
.insufficient-evidence > .el-icon { margin-top: 2px; color: var(--ogs-info); font-size: 18px; }
.insufficient-evidence strong,
.insufficient-evidence span,
.healthy-evidence strong,
.healthy-evidence span { display: block; }
.insufficient-evidence strong { color: var(--ogs-text); font-size: 11px; }
.insufficient-evidence span { margin-top: 2px; font-size: 10px; }
.healthy-evidence { display: flex; gap: 10px; margin-top: 10px; color: var(--ogs-text-secondary); }
.healthy-evidence > .el-icon { margin-top: 2px; color: var(--ogs-success); font-size: 18px; }
.healthy-evidence strong { color: var(--ogs-text); font-size: 11px; }
.healthy-evidence span { margin-top: 2px; font-size: 10px; }
.diagnostic-error { margin: 0; padding: 11px 16px; color: var(--ogs-danger); background: rgb(239 68 68 / 5%); font-size: 11px; }
.diagnostic-actions {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  border-top: 1px solid var(--ogs-border-subtle);
}
.diagnostic-actions > span { color: var(--ogs-text-muted); font-family: var(--ogs-mono); font-size: 9px; }
.diagnostic-actions > div { display: flex; gap: 5px; }
.diagnostic-card :deep(.el-button:focus-visible) { outline: 2px solid var(--ogs-primary); outline-offset: 2px; }
@media (max-width: 760px) {
  .diagnostic-card { width: 100%; margin-left: 0; }
  .diagnostic-head { padding: 11px 12px; }
  .diagnostic-progress { padding-inline: 12px; }
  .asset-progress { margin-inline: 12px; }
  .diagnostic-report { padding-inline: 12px; }
  .privilege-warning { margin-inline: 12px; }
  .diagnostic-actions { align-items: flex-start; padding-inline: 12px; }
  .diagnostic-actions > span { margin-top: 7px; }
}
@media (max-width: 440px) {
  .progress-facts { grid-template-columns: repeat(2, 1fr); row-gap: 10px; }
  .asset-row { grid-template-columns: 7px minmax(0, 1fr) auto; }
  .asset-probes { display: none; }
  .asset-label { max-width: 74px; }
  .diagnostic-actions { flex-direction: column; }
  .diagnostic-actions > div { width: 100%; justify-content: flex-end; }
}
@media (prefers-reduced-motion: reduce) {
  .diagnostic-card :deep(.is-loading) { animation: none; }
}
</style>
