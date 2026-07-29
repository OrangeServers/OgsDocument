<template>
  <div class="batch-operation-canvas">
    <main class="canvas-workspace">
        <div v-if="canViewHistory" class="canvas-toolbar">
          <el-button plain @click="router.push('/log-exec')">
            <el-icon><Clock /></el-icon>
            {{ $t('ops.history') }}
          </el-button>
        </div>

        <ol class="canvas-stages" :aria-label="$t('ops.stagesAria')">
          <li :class="{ active: activeStage === 1, done: activeStage > 1 }">
            <span>1</span>
            <div>
              <strong>{{ $t('ops.stage1') }}</strong>
              <small>{{ selectedHosts.length ? $t('ops.assetsCount', { n: selectedHosts.length }) : $t('ops.noAssetsSelected') }}</small>
            </div>
          </li>
          <li :class="{ active: activeStage === 2, done: activeStage > 2 }">
            <span>2</span>
            <div>
              <strong>{{ $t('ops.stage2') }}</strong>
              <small>{{ configSummary }}</small>
            </div>
          </li>
          <li :class="{ active: activeStage === 3 }">
            <span>3</span>
            <div>
              <strong>{{ $t('ops.stage3') }}</strong>
              <small>{{ runSummary }}</small>
            </div>
          </li>
        </ol>

        <section class="preparation-card">
          <div v-if="kind === 'script' && roleLoaded && !canRunScript" class="role-notice">
            <el-icon><Lock /></el-icon>
            <div>
              <strong>{{ $t('ops.scriptAdminOnly') }}</strong>
              <span>{{ $t('ops.scriptAdminOnlyDetail') }}</span>
            </div>
          </div>
          <div class="preparation-card__title">
            <div>
              <span>{{ kind === 'command' ? 'COMMAND' : 'SCRIPT PACKAGE' }}</span>
              <h2>{{ kind === 'command' ? $t('ops.prepareCommand') : $t('ops.prepareScript') }}</h2>
            </div>
            <span class="readiness" :class="{ ready: configReady }">
              <i />
              {{ configReady ? $t('ops.configReady') : $t('ops.configIncomplete') }}
            </span>
          </div>

          <div class="credential-row">
            <label>
              <span>{{ $t('ops.credential') }}</span>
              <el-select
                v-model="sysUser"
                :placeholder="$t('ops.credentialPlaceholder')"
                :disabled="executing || (kind === 'script' && !canRunScript)"
                filterable
              >
                <el-option v-for="user in sysUsers" :key="user" :label="user" :value="user" />
              </el-select>
            </label>
            <p>
              {{ $t('ops.credentialHint') }}
            </p>
          </div>

          <div v-if="kind === 'command'" class="terminal-editor">
            <div class="terminal-editor__bar">
              <span>{{ sysUser || 'credential' }}@batch:~$</span>
              <small>{{ $t('ops.ctrlEnterRun') }}</small>
            </div>
            <textarea
              v-model="command"
              :aria-label="$t('ops.batchCommandTitle')"
              :disabled="executing"
              :placeholder="$t('ops.commandPlaceholder')"
              @keydown.ctrl.enter.prevent="execute()"
            />
          </div>

          <div v-else class="script-package">
            <input
              ref="fileInput"
              class="visually-hidden"
              type="file"
              accept=".sh,.py"
              :disabled="executing"
              @change="onFileChange"
            />
            <div v-if="!scriptFile" class="script-empty">
              <span class="file-mark"><el-icon><UploadFilled /></el-icon></span>
              <div>
                <strong>{{ $t('ops.scriptEmptyTitle') }}</strong>
                <span>{{ $t('ops.scriptEmptyHint') }}</span>
              </div>
              <el-button plain :disabled="executing || !canRunScript" @click="fileInput?.click()">{{ $t('ops.chooseScript') }}</el-button>
            </div>
            <template v-else>
              <div class="script-summary">
                <span class="file-mark"><el-icon><Document /></el-icon></span>
                <div>
                  <strong>{{ scriptFile.name }}</strong>
                  <small>{{ scriptRuntime }} · {{ formatBytes(scriptFile.size) }}</small>
                </div>
                <button type="button" class="text-button" :disabled="executing || !canRunScript" @click="clearScript">
                  {{ $t('ops.remove') }}
                </button>
              </div>
              <div class="script-tabs">
                <button
                  type="button"
                  :class="{ active: scriptTab === 'preview' }"
                  @click="scriptTab = 'preview'"
                >
                  {{ $t('ops.scriptPreviewTab') }}
                </button>
                <button
                  type="button"
                  :class="{ active: scriptTab === 'checks' }"
                  @click="scriptTab = 'checks'"
                >
                  {{ $t('ops.scriptChecksTab') }}
                </button>
              </div>
              <pre v-if="scriptTab === 'preview'" class="script-preview"><code>{{ scriptPreview }}</code></pre>
              <ul v-else class="check-list">
                <li :class="{ passed: scriptTypeValid }">
                  <el-icon><CircleCheckFilled /></el-icon>
                  {{ $t('ops.checkType') }}
                </li>
                <li :class="{ passed: scriptSizeValid }">
                  <el-icon><CircleCheckFilled /></el-icon>
                  {{ $t('ops.checkSize') }}
                </li>
                <li :class="{ passed: scriptEncodingValid }">
                  <el-icon><CircleCheckFilled /></el-icon>
                  {{ $t('ops.checkEncoding') }}
                </li>
                <li class="neutral">
                  <el-icon><InfoFilled /></el-icon>
                  {{ $t('ops.checkRemote') }}
                </li>
              </ul>
            </template>
          </div>

          <footer class="preparation-card__footer">
            <div class="manifest-summary">
              <span>{{ $t('ops.targetLabel') }} <strong>{{ $t('ops.nHosts', { n: selectedHosts.length }) }}</strong></span>
              <span>{{ $t('ops.credLabel') }} <strong>{{ sysUser || $t('ops.notSelected') }}</strong></span>
              <span v-if="kind === 'script'">{{ $t('ops.runtimeLabel') }} <strong>{{ scriptRuntime || '—' }}</strong></span>
              <span v-if="selectedHosts.length > 50" class="manifest-error">{{ $t('ops.maxHostsLimit') }}</span>
            </div>
            <el-button
              type="primary"
              class="primary-action"
              :loading="executing"
              :disabled="!configReady || executing"
              @click="execute()"
            >
              {{ executing ? $t('ops.executing') : kind === 'command' ? $t('ops.runCommand') : $t('ops.runScript') }}
              <el-icon v-if="!executing"><ArrowRight /></el-icon>
            </el-button>
          </footer>
        </section>

        <section v-if="executing || results.length" class="result-explorer">
          <div class="result-explorer__head">
            <div>
              <span>EXECUTION RESULT</span>
              <h2>{{ resultTitle }}</h2>
            </div>
            <div class="result-totals">
              <span v-if="successCount" class="success">{{ $t('ops.nSuccess', { n: successCount }) }}</span>
              <span v-if="failCount" class="failed">{{ $t('ops.nFailed', { n: failCount }) }}</span>
            </div>
          </div>
          <div v-if="executing" class="result-progress" :aria-label="$t('ops.executingAria')">
            <span />
          </div>

          <div v-if="executing" class="executing-state">
            <el-icon class="is-loading"><Loading /></el-icon>
            <div>
              <strong>{{ $t('ops.executingWait') }}</strong>
              <span>{{ $t('ops.executingHint') }}</span>
            </div>
          </div>

          <template v-else>
            <div class="result-table" role="grid" :aria-label="$t('ops.perAssetResultsAria')">
              <div class="result-table__row result-table__header" role="row">
                <span role="columnheader">{{ $t('ops.colAsset') }}</span>
                <span role="columnheader">{{ $t('ops.colStatus') }}</span>
                <span role="columnheader">{{ $t('ops.colSummary') }}</span>
              </div>
              <button
                v-for="item in orderedResults"
                :key="item.alias"
                type="button"
                class="result-table__row"
                :class="{ selected: selectedResult === item.alias }"
                role="row"
                @click="selectedResult = item.alias"
              >
                <strong role="gridcell">{{ item.alias }}</strong>
                <span role="gridcell" class="host-state" :class="item.status">
                  {{ item.status === 'success' ? $t('common.status.success') : $t('common.status.fail') }}
                </span>
                <span role="gridcell">{{ resultExcerpt(item) }}</span>
              </button>
            </div>

            <div v-if="selectedResultData" class="result-terminal">
              <div>
                <strong>{{ selectedResultData.alias }}</strong>
                <span>{{ selectedResultData.status === 'success' ? $t('ops.outputLabel') : $t('ops.failReason') }}</span>
              </div>
              <pre><code>{{ selectedResultData.status === 'success'
                ? selectedResultData.output || $t('ops.noStdout')
                : selectedResultData.error || $t('ops.execFailed') }}</code></pre>
            </div>

            <footer v-if="failCount" class="result-actions">
              <span>{{ $t('ops.retryHint') }}</span>
              <el-button type="primary" plain @click="retryFailed">
                <el-icon><RefreshRight /></el-icon>
                {{ $t('ops.retryFailed', { n: failCount }) }}
              </el-button>
            </footer>
          </template>
        </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowRight,
  CircleCheckFilled,
  Clock,
  Document,
  InfoFilled,
  Loading,
  Lock,
  RefreshRight,
  UploadFilled,
} from '@element-plus/icons-vue'
import { batchCommand, batchScript, getSysUserNameList } from '@/api'
import { loadUserRole, store } from '@/store'
import { t } from '@/i18n'
import { restoreSysUser, rememberSysUser } from '@/utils/sysUser'

type OperationKind = 'command' | 'script'
type RunState = 'idle' | 'completed' | 'partial' | 'failed'
type ScriptTab = 'preview' | 'checks'

interface BatchResultItem {
  alias: string
  status: 'success' | 'failed'
  output: string
  error: string
}

interface BatchResponse {
  code: number
  msg?: string
  command_msg?: string[]
  hostname_list?: string[]
  error_list?: string[]
  items?: Array<{
    alias?: string
    status?: string
    output?: string
    error?: string
  }>
}

const props = defineProps<{
  kind: OperationKind
  selectedHosts: string[]
  sysUser: string
}>()
const emit = defineEmits<{
  'update:selectedHosts': [value: string[]]
  'update:sysUser': [value: string]
}>()
const MAX_SCRIPT_SIZE = 1024 * 1024
const router = useRouter()

const sysUsers = ref<string[]>([])
const selectedHosts = computed({
  get: () => props.selectedHosts,
  set: value => emit('update:selectedHosts', value),
})
const sysUser = computed({
  get: () => props.sysUser,
  set: value => emit('update:sysUser', value),
})

// 选择即记忆：下拉切换即写入（与终端/SFTP 同一 key，跨页面一致）
watch(sysUser, (v) => { if (v) rememberSysUser(v) })

const command = ref('')
const executing = ref(false)
const runState = ref<RunState>('idle')
const results = ref<BatchResultItem[]>([])
const selectedResult = ref('')
const currentRole = ref(String(store.user.role || ''))
const roleLoaded = ref(false)

const fileInput = ref<HTMLInputElement | null>(null)
const scriptFile = ref<File | null>(null)
const scriptPreview = ref('')
const scriptEncodingValid = ref(false)
const scriptTab = ref<ScriptTab>('preview')

const scriptExtension = computed(() => {
  const name = scriptFile.value?.name.toLowerCase() || ''
  if (name.endsWith('.sh')) return '.sh'
  if (name.endsWith('.py')) return '.py'
  return ''
})
const scriptTypeValid = computed(() => Boolean(scriptExtension.value))
const scriptSizeValid = computed(() =>
  Boolean(scriptFile.value && scriptFile.value.size > 0 && scriptFile.value.size <= MAX_SCRIPT_SIZE))
const scriptRuntime = computed(() =>
  scriptExtension.value === '.sh' ? 'Bash' : scriptExtension.value === '.py' ? 'Python 3' : '')
const canRunScript = computed(() => currentRole.value === 'admin')
const canViewHistory = computed(() => ['admin', 'audit'].includes(currentRole.value))
const operationConfigured = computed(() => props.kind === 'command'
  ? Boolean(command.value.trim())
  : Boolean(scriptFile.value && scriptTypeValid.value && scriptSizeValid.value && scriptEncodingValid.value))
const configReady = computed(() =>
  selectedHosts.value.length > 0
  && selectedHosts.value.length <= 50
  && Boolean(sysUser.value)
  && operationConfigured.value
  && (props.kind === 'command' || canRunScript.value))
const activeStage = computed(() => {
  if (executing.value || results.value.length) return 3
  if (selectedHosts.value.length) return 2
  return 1
})
const configSummary = computed(() => {
  if (!selectedHosts.value.length) return t('ops.waitTargets')
  if (selectedHosts.value.length > 50) return t('ops.maxHostsLimit')
  if (!sysUser.value) return t('ops.waitCredential')
  if (!operationConfigured.value) return props.kind === 'command' ? t('ops.waitCommand') : t('ops.waitScript')
  return props.kind === 'command' ? command.value.trim().split(/\s+/)[0] : scriptFile.value?.name || ''
})
const runSummary = computed(() => {
  if (executing.value) return t('ops.executing')
  if (runState.value === 'completed') return t('ops.allDone')
  if (runState.value === 'partial') return t('ops.needAttention', { n: failCount.value })
  if (runState.value === 'failed') return t('ops.execFailed')
  return configReady.value ? t('ops.readyToRun') : t('ops.waitConfig')
})

const successCount = computed(() => results.value.filter(item => item.status === 'success').length)
const failCount = computed(() => results.value.filter(item => item.status === 'failed').length)
const orderedResults = computed(() => [...results.value].sort((a, b) => {
  if (a.status === b.status) return a.alias.localeCompare(b.alias)
  return a.status === 'failed' ? -1 : 1
}))
const selectedResultData = computed(() =>
  results.value.find(item => item.alias === selectedResult.value) || null)
const resultTitle = computed(() => {
  if (executing.value) return t('ops.executing')
  if (runState.value === 'completed') return t('ops.allSuccess')
  if (runState.value === 'partial') return t('ops.partialTitle', { n: failCount.value })
  return t('ops.execFailed')
})

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
}

function resultExcerpt(item: BatchResultItem): string {
  const text = (item.status === 'success' ? item.output : item.error).trim()
  if (!text) return item.status === 'success' ? t('ops.noStdoutShort') : t('ops.execFailed')
  const firstLine = text.split(/\r?\n/, 1)[0]
  return firstLine.length > 100 ? `${firstLine.slice(0, 100)}…` : firstLine
}

function normalizeResponse(response: BatchResponse): BatchResultItem[] {
  if (Array.isArray(response.items) && response.items.length) {
    return response.items.map((item, index) => ({
      alias: item.alias || t('ops.targetN', { n: index + 1 }),
      status: item.status === 'success' ? 'success' : 'failed',
      output: item.output || '',
      error: item.error || '',
    }))
  }
  const successful = (response.command_msg || []).map((output, index) => ({
    alias: response.hostname_list?.[index] || t('ops.targetN', { n: index + 1 }),
    status: 'success' as const,
    output,
    error: '',
  }))
  const failed = (response.error_list || []).map(alias => ({
    alias,
    status: 'failed' as const,
    output: '',
    // 后端 msg 为透传数据，仅在缺失时用本地化兜底文案
    error: response.msg || t('ops.msg.connectFail'),
  }))
  return [...successful, ...failed]
}

async function onFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  scriptFile.value = file
  scriptPreview.value = ''
  scriptEncodingValid.value = false
  scriptTab.value = 'preview'
  if (!file) return
  if (!['.sh', '.py'].some(extension => file.name.toLowerCase().endsWith(extension))) {
    ElMessage.error(t('ops.msg.scriptTypeOnly'))
    return
  }
  if (!scriptSizeValid.value) {
    ElMessage.error(file.size === 0 ? t('ops.msg.scriptEmpty') : t('ops.msg.scriptTooLarge'))
    return
  }
  try {
    const buffer = await file.arrayBuffer()
    const text = new TextDecoder('utf-8', { fatal: true }).decode(buffer)
    scriptEncodingValid.value = true
    scriptPreview.value = text.length > 12000 ? `${text.slice(0, 12000)}\n\n${t('ops.previewTruncated')}` : text
  } catch {
    ElMessage.error(t('ops.msg.scriptNotUtf8'))
  }
}

function clearScript(): void {
  scriptFile.value = null
  scriptPreview.value = ''
  scriptEncodingValid.value = false
  if (fileInput.value) fileInput.value.value = ''
}

async function execute(targets: string[] = selectedHosts.value): Promise<void> {
  if (executing.value) return
  if (!targets.length) {
    ElMessage.warning(t('ops.msg.selectTargets'))
    return
  }
  if (targets.length > 50) {
    ElMessage.warning(t('ops.msg.maxHosts'))
    return
  }
  if (!sysUser.value) {
    ElMessage.warning(t('ops.msg.selectCredential'))
    return
  }
  if (props.kind === 'command' && !command.value.trim()) {
    ElMessage.warning(t('ops.msg.enterCommand'))
    return
  }
  if (props.kind === 'script' && !operationConfigured.value) {
    ElMessage.warning(t('ops.msg.selectValidScript'))
    return
  }
  if (props.kind === 'script' && !canRunScript.value) {
    ElMessage.warning(t('ops.scriptAdminOnly'))
    return
  }

  executing.value = true
  results.value = []
  selectedResult.value = ''
  try {
    let response: BatchResponse
    if (props.kind === 'command') {
      response = await batchCommand({
        host_name: targets,
        command: command.value.trim(),
        sys_user: sysUser.value,
      }) as unknown as BatchResponse
    } else {
      const form = new FormData()
      form.append('file', scriptFile.value as File)
      form.append('name', scriptFile.value?.name || '')
      form.append('put_type', 'sh')
      form.append('sys_user', sysUser.value)
      targets.forEach(alias => form.append('name_list', alias))
      response = await batchScript(form) as unknown as BatchResponse
    }

    const normalized = normalizeResponse(response)
    if (response.code !== 0 && !normalized.length) {
      normalized.push({
        alias: t('ops.requestFailed'),
        status: 'failed',
        output: '',
        error: response.msg || t('ops.msg.notExecuted'),
      })
    }
    results.value = normalized
    selectedResult.value = normalized.find(item => item.status === 'failed')?.alias
      || normalized[0]?.alias
      || ''
    // 凭据记忆已由 watch(sysUser) 统一覆盖，此处不再重复写入
    runState.value = failCount.value === 0 && successCount.value > 0
      ? 'completed'
      : successCount.value > 0
        ? 'partial'
        : 'failed'
    if (runState.value === 'completed') {
      ElMessage.success(t('ops.msg.execSuccessCount', { n: successCount.value }))
    } else if (runState.value === 'partial') {
      ElMessage.warning(t('ops.msg.partialResult', { ok: successCount.value, fail: failCount.value }))
    } else {
      ElMessage.error(response.msg || t('ops.msg.allFailed'))
    }
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : t('ops.requestFailed')
    results.value = [{ alias: t('ops.requestFailed'), status: 'failed', output: '', error: message }]
    selectedResult.value = t('ops.requestFailed')
    runState.value = 'failed'
    ElMessage.error(message)
  } finally {
    executing.value = false
  }
}

async function retryFailed(): Promise<void> {
  const failedAliases = results.value
    .filter(item => item.status === 'failed' && item.alias !== t('ops.requestFailed'))
    .map(item => item.alias)
  if (!failedAliases.length) return
  selectedHosts.value = failedAliases
  await execute(failedAliases)
}

onMounted(async () => {
  try {
    currentRole.value = await loadUserRole() || String(store.user.role || '')
  } finally {
    roleLoaded.value = true
  }
  try {
    const userResponse = await getSysUserNameList() as unknown as {
      code: number
      msg?: string[]
    }
    if (userResponse.code === 0) {
      sysUsers.value = [...(userResponse.msg || [])].sort((a, b) => a.localeCompare(b))
      // 恢复上次选中的凭据（与终端/SFTP 同一 key）
      sysUser.value = restoreSysUser(sysUsers.value)
    }
  } catch {
    ElMessage.error(t('ops.msg.loadCredentialsFail'))
  }
})
</script>

<style scoped>
.batch-operation-canvas {
  /* 画布调色板全部映射到全局主题 token，深浅主题自动适配 */
  --canvas-ink: var(--ogs-text);
  --canvas-muted: var(--ogs-text-secondary);
  --canvas-line: var(--ogs-border);
  --canvas-surface: var(--ogs-bg-elevated);
  --canvas-warm: var(--ogs-bg-sunken);
  --canvas-orange: var(--ogs-primary);
  --canvas-success: var(--ogs-success);
  --canvas-danger: var(--ogs-danger);
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: auto;
  color: var(--canvas-ink);
  background: transparent;
  box-sizing: border-box;
}

.canvas-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  max-width: none;
  margin: 0 auto 18px;
}

.canvas-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.canvas-eyebrow,
.preparation-card__title > div > span,
.result-explorer__head > div > span {
  color: var(--ogs-primary-dark);
  font: 700 11px/1.2 var(--ogs-mono);
  letter-spacing: .14em;
}

.canvas-header h1 {
  margin: 7px 0 4px;
  font-size: 26px;
  line-height: 1.15;
  letter-spacing: -.025em;
}

.canvas-header p {
  margin: 0;
  color: var(--canvas-muted);
  font-size: 13px;
}

.history-button {
  min-height: 36px;
  border-color: var(--canvas-line);
}

.canvas-shell {
  display: grid;
  grid-template-columns: 252px minmax(0, 1fr);
  max-width: none;
  min-height: 680px;
  margin: 0 auto;
  overflow: hidden;
  background: var(--canvas-surface);
  border: 1px solid var(--canvas-line);
  border-radius: 12px;
  box-shadow: var(--ogs-shadow);
}

.canvas-shell.is-drawer-closed {
  grid-template-columns: 0 minmax(0, 1fr);
}

.role-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 14px 0;
  padding: 11px 12px;
  color: var(--ogs-warning);
  background: var(--ogs-warning-soft);
  border: 1px solid color-mix(in srgb, var(--ogs-warning) 30%, transparent);
  border-radius: 7px;
}

.role-notice > div {
  display: grid;
  gap: 2px;
}

.role-notice strong {
  font-size: 12px;
}

.role-notice span {
  color: var(--canvas-muted);
  font-size: 11px;
}

.asset-drawer {
  display: grid;
  min-width: 0;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  background: var(--canvas-warm);
  border-right: 1px solid var(--canvas-line);
  transition: opacity .18s ease;
}

.is-drawer-closed .asset-drawer {
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}

.asset-drawer__head {
  display: flex;
  min-height: 54px;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid var(--canvas-line);
}

.asset-drawer__head > div {
  display: flex;
  gap: 7px;
  align-items: baseline;
}

.asset-drawer__head span,
.asset-group__title span {
  font-size: 12px;
  font-weight: 650;
}

.asset-drawer__head strong,
.asset-group__title small {
  color: var(--canvas-muted);
  font: 600 11px var(--ogs-mono);
}

.asset-drawer__head button,
.asset-drawer-toggle,
.text-button {
  color: var(--canvas-muted);
  background: transparent;
  border: 0;
  cursor: pointer;
}

.asset-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px;
  padding: 0 10px;
  min-height: 34px;
  background: var(--canvas-surface);
  border: 1px solid var(--canvas-line);
  border-radius: 6px;
}

.asset-search input {
  width: 100%;
  min-width: 0;
  color: var(--canvas-ink);
  background: transparent;
  border: 0;
  outline: 0;
  font-size: 12px;
}

.asset-list {
  min-height: 0;
  padding: 0 12px 12px;
  overflow-y: auto;
}

.asset-group + .asset-group {
  margin-top: 15px;
}

.asset-group__title {
  display: flex;
  justify-content: space-between;
  padding: 5px 3px 7px;
  text-transform: none;
}

.asset-option {
  display: grid;
  grid-template-columns: 16px 8px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 8px 4px;
  cursor: pointer;
}

.asset-option input {
  accent-color: var(--canvas-orange);
}

.asset-option__status {
  width: 6px;
  height: 6px;
  background: var(--canvas-success);
  border-radius: 50%;
}

.asset-option__copy {
  min-width: 0;
}

.asset-option__copy strong,
.asset-option__copy small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-option__copy strong {
  font: 650 12px var(--ogs-mono);
}

.asset-option__copy small {
  margin-top: 3px;
  color: var(--canvas-muted);
  font-size: 11px;
}

.asset-empty {
  padding: 28px 8px;
  color: var(--canvas-muted);
  text-align: center;
  font-size: 12px;
}

.asset-drawer__foot {
  display: flex;
  min-height: 42px;
  align-items: center;
  gap: 6px;
  padding: 0 14px;
  color: var(--canvas-muted);
  border-top: 1px solid var(--canvas-line);
  font-size: 11px;
}

.canvas-workspace {
  position: relative;
  min-width: 0;
  min-height: 100%;
  padding: 0 0 24px;
}

.asset-drawer-toggle {
  position: absolute;
  top: 15px;
  left: 18px;
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
}

.canvas-stages {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  max-width: none;
  margin: 0 0 12px;
  padding: 0;
  list-style: none;
}

.canvas-stages li {
  position: relative;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.canvas-stages li::after {
  position: absolute;
  top: 12px;
  right: 8px;
  left: 32px;
  height: 1px;
  content: "";
  background: var(--canvas-line);
}

.canvas-stages li:last-child::after {
  display: none;
}

.canvas-stages li > span {
  z-index: 1;
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  color: var(--ogs-bg-elevated);
  background: var(--ogs-text-muted);
  border-radius: 50%;
  font: 700 11px var(--ogs-mono);
}

.canvas-stages li.active > span {
  color: #fff;
  background: var(--canvas-orange);
}

.canvas-stages li.done > span {
  color: var(--ogs-bg-elevated);
  background: var(--canvas-ink);
}

.canvas-stages li div {
  z-index: 1;
  width: fit-content;
  max-width: calc(100% - 10px);
  padding-right: 8px;
  background: var(--canvas-surface);
}

.canvas-stages strong,
.canvas-stages small {
  display: block;
}

.canvas-stages strong {
  font-size: 11px;
}

.canvas-stages small {
  margin-top: 3px;
  overflow: hidden;
  color: var(--canvas-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preparation-card,
.result-explorer {
  max-width: none;
  margin: 0;
  overflow: hidden;
  background: var(--canvas-surface);
  border: 1px solid var(--canvas-line);
  border-radius: 10px;
}

.preparation-card__title,
.result-explorer__head {
  display: flex;
  min-height: 64px;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  border-bottom: 1px solid var(--canvas-line);
}

.preparation-card__title h2,
.result-explorer__head h2 {
  margin: 5px 0 0;
  font-size: 16px;
}

.readiness {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  color: var(--canvas-muted);
  background: var(--ogs-bg-sunken);
  border-radius: 999px;
  font-size: 11px;
}

.readiness i {
  width: 6px;
  height: 6px;
  background: var(--ogs-text-muted);
  border-radius: 50%;
}

.readiness.ready {
  color: var(--ogs-success);
  background: var(--ogs-success-soft);
}

.readiness.ready i {
  background: var(--canvas-success);
}

.credential-row {
  display: grid;
  grid-template-columns: minmax(220px, 310px) minmax(0, 1fr);
  gap: 22px;
  align-items: end;
  padding: 16px 18px;
}

.credential-row label > span {
  display: block;
  margin-bottom: 7px;
  color: var(--canvas-muted);
  font-size: 11px;
}

.credential-row :deep(.el-select) {
  width: 100%;
}

.credential-row p {
  margin: 0 0 8px;
  color: var(--canvas-muted);
  font-size: 11px;
}

.terminal-editor {
  margin: 0 18px 16px;
  overflow: hidden;
  color: #f3efe9;
  background: #17181b;
  border-radius: 8px;
}

.terminal-editor__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 13px;
  color: #ff9b5d;
  background: #202227;
  font: 11px var(--ogs-mono);
}

.terminal-editor__bar small {
  color: #97999f;
}

.terminal-editor textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 112px;
  padding: 15px;
  resize: vertical;
  color: #f5f1eb;
  background: transparent;
  border: 0;
  outline: 0;
  font: 12px/1.65 var(--ogs-mono);
}

.script-package {
  margin: 0 18px 16px;
  overflow: hidden;
  border: 1px solid var(--canvas-line);
  border-radius: 8px;
}

.script-empty,
.script-summary {
  display: flex;
  min-height: 66px;
  align-items: center;
  gap: 12px;
  padding: 0 14px;
}

.script-empty > div,
.script-summary > div {
  min-width: 0;
  flex: 1;
}

.script-empty strong,
.script-empty span,
.script-summary strong,
.script-summary small {
  display: block;
}

.script-empty strong,
.script-summary strong {
  font-size: 12px;
}

.script-empty span,
.script-summary small {
  margin-top: 4px;
  color: var(--canvas-muted);
  font-size: 11px;
}

.file-mark {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--canvas-orange);
  background: var(--ogs-primary-soft);
  border: 1px dashed color-mix(in srgb, var(--ogs-primary) 45%, transparent);
  border-radius: 7px;
  font-size: 16px;
}

.text-button {
  color: var(--canvas-danger);
  font-size: 12px;
}

.script-tabs {
  display: flex;
  gap: 18px;
  padding: 0 14px;
  border-top: 1px solid var(--canvas-line);
  border-bottom: 1px solid var(--canvas-line);
}

.script-tabs button {
  position: relative;
  padding: 9px 0;
  color: var(--canvas-muted);
  background: transparent;
  border: 0;
  cursor: pointer;
  font-size: 11px;
}

.script-tabs button.active {
  color: var(--canvas-ink);
  font-weight: 650;
}

.script-tabs button.active::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  content: "";
  background: var(--canvas-orange);
}

.script-preview,
.result-terminal pre {
  max-height: 220px;
  margin: 0;
  overflow: auto;
  color: #e9e4dc;
  background: #17181b;
  font: 12px/1.65 var(--ogs-mono);
  white-space: pre-wrap;
  word-break: break-word;
}

.script-preview {
  min-height: 100px;
  padding: 14px;
}

.check-list {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 14px;
  list-style: none;
}

.check-list li {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--canvas-danger);
  font-size: 12px;
}

.check-list li.passed {
  color: var(--canvas-success);
}

.check-list li.neutral {
  color: var(--canvas-muted);
}

.preparation-card__footer {
  display: flex;
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0 18px;
  background: var(--ogs-bg-sunken);
  border-top: 1px solid var(--canvas-line);
}

.manifest-summary {
  display: flex;
  min-width: 0;
  gap: 18px;
  color: var(--canvas-muted);
  font-size: 11px;
}

.manifest-summary strong {
  color: var(--canvas-ink);
}

.manifest-summary .manifest-error {
  color: var(--canvas-danger);
  font-weight: 650;
}

.primary-action {
  min-width: 150px;
  --el-button-bg-color: var(--canvas-orange);
  --el-button-border-color: var(--canvas-orange);
  --el-button-hover-bg-color: var(--ogs-primary-dark);
  --el-button-hover-border-color: var(--ogs-primary-dark);
}

.result-explorer {
  margin-top: 12px;
}

.result-totals {
  display: flex;
  gap: 12px;
  font: 650 11px var(--ogs-mono);
}

.result-totals .success {
  color: var(--canvas-success);
}

.result-totals .failed {
  color: var(--canvas-danger);
}

.result-progress {
  height: 3px;
  overflow: hidden;
  background: var(--ogs-bg-sunken);
}

.result-progress span {
  display: block;
  width: 34%;
  height: 100%;
  background: var(--canvas-orange);
  animation: execution-progress 1.2s ease-in-out infinite alternate;
}

@keyframes execution-progress {
  from { transform: translateX(-100%); }
  to { transform: translateX(295%); }
}

.executing-state {
  display: flex;
  min-height: 120px;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--canvas-muted);
}

.executing-state .el-icon {
  color: var(--canvas-orange);
  font-size: 22px;
}

.executing-state strong,
.executing-state span {
  display: block;
}

.executing-state strong {
  color: var(--canvas-ink);
  font-size: 13px;
}

.executing-state span {
  margin-top: 5px;
  font-size: 11px;
}

.result-table__row {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) 90px minmax(240px, 2.4fr);
  width: 100%;
  min-height: 42px;
  align-items: center;
  gap: 12px;
  padding: 0 14px;
  text-align: left;
  color: var(--canvas-ink);
  background: var(--canvas-surface);
  border: 0;
  border-bottom: 1px solid var(--ogs-border-subtle);
  font-size: 11px;
}

button.result-table__row {
  cursor: pointer;
}

button.result-table__row:hover,
button.result-table__row.selected {
  background: var(--ogs-bg-sunken);
  box-shadow: inset 3px 0 var(--canvas-orange);
}

.result-table__header {
  color: var(--canvas-muted);
  background: var(--ogs-bg-sunken);
  font-weight: 650;
}

.result-table__row > * {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-table__row strong {
  font-family: var(--ogs-mono);
}

.host-state {
  width: fit-content;
  padding: 4px 8px;
  border-radius: 999px;
  font-weight: 650;
}

.host-state.success {
  color: var(--ogs-success);
  background: var(--ogs-success-soft);
}

.host-state.failed {
  color: var(--ogs-danger);
  background: var(--ogs-danger-soft);
}

.result-terminal {
  margin: 14px;
  overflow: hidden;
  border-radius: 8px;
}

.result-terminal > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  color: #f2eee8;
  background: #24262b;
  font-size: 11px;
}

.result-terminal > div strong {
  font-family: var(--ogs-mono);
}

.result-terminal > div span {
  color: #a9a7a3;
}

.result-terminal pre {
  min-height: 90px;
  padding: 13px;
}

.result-actions {
  display: flex;
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 14px;
  color: var(--canvas-muted);
  background: var(--ogs-bg-sunken);
  border-top: 1px solid var(--canvas-line);
  font-size: 11px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 1100px) {
  .batch-operation-canvas {
    padding: 0;
  }

  .canvas-shell {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .canvas-workspace {
    padding: 0 0 20px;
  }
}

@media (max-width: 820px) {
  .canvas-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }

  .canvas-shell,
  .canvas-shell.is-drawer-closed {
    grid-template-columns: 1fr;
  }

  .asset-drawer {
    max-height: 300px;
    border-right: 0;
    border-bottom: 1px solid var(--canvas-line);
  }

  .is-drawer-closed .asset-drawer {
    display: none;
  }

  .canvas-stages {
    margin-top: 0;
  }

  .credential-row {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .preparation-card__footer,
  .result-actions {
    align-items: stretch;
    flex-direction: column;
    padding-top: 12px;
    padding-bottom: 12px;
  }

  .manifest-summary {
    flex-wrap: wrap;
  }

  .result-table__row {
    grid-template-columns: minmax(120px, 1fr) 80px minmax(160px, 2fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .asset-drawer,
  .result-progress span {
    transition: none;
    animation: none;
  }

  .result-progress span {
    width: 100%;
  }
}
</style>
