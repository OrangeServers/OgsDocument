<template>
  <DataTablePanel
    eyebrow="ASSETS"
    :title="$t('assets.host.title')"
    :subtitle="$t('assets.host.subtitle', { total })"
    :panel-title="$t('assets.host.title')"
    panel-sub="Host Inventory"
    :panel-icon="Monitor"
    :add-text="$t('assets.host.add')"
    :enable-batch="true"
    :batch-count="selectedRows.length"
    :page="currentPage"
    :page-size="pageSize"
    :total="total"
    @update:page="(p) => currentPage = p"
    @update:page-size="(s) => pageSize = s"
    @refresh="loadData"
    @add="openAdd()"
    @batch-delete="batchDelete"
  >
    <template #filters>
      <el-input v-model="keyword" :placeholder="$t('assets.host.searchPlaceholder')" clearable
                class="search-input" :prefix-icon="Search" @input="onSearch" />
      <el-select v-model="groupFilter" :placeholder="$t('assets.host.filterByGroup')" clearable
                 @change="onFilterChange" style="width:160px">
        <el-option v-for="g in groups" :key="g" :label="g" :value="g" />
      </el-select>
    </template>

    <template #active-filter>
      <span v-if="groupFilter && fromGroup" class="active-filter" :title="$t('assets.host.fromGroupTip', { name: fromGroup })">
        <span class="filter-label">{{ $t('assets.host.filterGroupLabel') }}</span>
        <span class="filter-value">{{ groupFilter }}</span>
        <span class="filter-clear" @click="clearGroupFilter" :title="$t('assets.host.clearFilter')">
          <el-icon :size="10"><Close /></el-icon>
        </span>
      </span>
    </template>

    <template #stats>
      <I18nT keypath="assets.host.stats.total" tag="span" class="num" scope="global">
        <template #n><strong>{{ total }}</strong></template>
      </I18nT>
      <span><span class="dot dot-online" />{{ $t('common.status.online') }} <strong class="num">{{ onlineCount }}</strong></span>
      <span><span class="dot dot-offline" />{{ $t('common.status.offline') }} <strong class="num">{{ offlineCount }}</strong></span>
      <span><span class="dot dot-configured" />{{ $t('assets.host.stats.configured') }} <strong class="num">{{ configuredCount }}</strong></span>
      <span><span class="dot dot-unconfigured" />{{ $t('assets.host.stats.unconfigured') }} <strong class="num">{{ unconfiguredCount }}</strong></span>
    </template>

    <el-table :data="pagedData" class="is-compact" stripe
              v-loading="loading" style="width:100%">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="id" label="ID" width="56" sortable>
        <template #default="{ row }">
          <span class="num" style="color:var(--ogs-text-muted)">#{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.host.col.status')" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="hostStatus(row)==='online'" size="small" type="success" effect="light" round>
            <span class="tag-dot online"></span>{{ $t('common.status.online') }}
          </el-tag>
          <el-tag v-else-if="hostStatus(row)==='offline'" size="small" type="info" effect="plain" round>
            <span class="tag-dot offline"></span>{{ $t('common.status.offline') }}
          </el-tag>
          <el-tag v-else size="small" type="warning" effect="plain" round>
            <span class="tag-dot unknown"></span>{{ $t('common.status.unknown') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="alias" :label="$t('assets.host.col.name')" min-width="150">
        <template #default="{ row }">
          <span style="font-weight:600;color:var(--ogs-text)">{{ row.alias }}</span>
          <el-tag v-if="!row.configured" size="small" type="warning" effect="plain" style="margin-left:6px">{{ $t('assets.host.unconfiguredTag') }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.host.col.ip')" width="150">
        <template #default="{ row }">
          <span class="ip-copy" @click="copyIp(row.host_ip)" :title="$t('assets.host.copyIpTip')">
            {{ row.host_ip }}
            <el-icon class="copy-hint" :size="11"><CopyDocument /></el-icon>
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="host_port" :label="$t('assets.host.col.port')" width="64">
        <template #default="{ row }">
          <span class="port-cell num">{{ row.host_port }}</span>
        </template>
      </el-table-column>
      <!-- UI修复：移除"登录用户"列——后端 host list 不返回 host_user（登录用户由系统用户表
           关联，非逐机配置），该列恒为"—"无信息量。如需展示需后端补关联查询。 -->
      <el-table-column :label="$t('assets.host.col.group')" width="100">
        <template #default="{ row }">
          <span :class="['group-tag', groupTagClass(row.group)]">{{ row.group }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.host.col.actions')" width="148" fixed="right" align="right">
        <template #default="scope">
          <span class="action-icon-btn" @click="openTerminal(scope.row)" :title="$t('assets.host.terminalTip')">
            <el-icon :size="14"><Monitor /></el-icon>
          </span>
          <span class="action-icon-btn" @click="openSftp(scope.row)" :title="$t('assets.host.sftpTip')">
            <el-icon :size="14"><FolderOpened /></el-icon>
          </span>
          <span class="action-divider" />
          <span class="action-icon-btn" @click="openEdit(scope.row)" :title="$t('common.action.edit')">
            <el-icon :size="14"><EditPen /></el-icon>
          </span>
          <span class="action-icon-btn is-danger" @click="doDelete(scope.row)" :title="$t('common.action.delete')">
            <el-icon :size="14"><Delete /></el-icon>
          </span>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-state">
          <el-icon :size="40" style="color:var(--ogs-text-muted)"><Monitor /></el-icon>
          <p>{{ $t('assets.host.empty.title') }}</p>
          <span>{{ $t('assets.host.empty.hint') }}</span>
        </div>
      </template>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('assets.host.dialog.edit') : $t('assets.host.dialog.add')" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item v-if="isEdit" label="ID">
          <el-input v-model="form.id" disabled />
        </el-form-item>
        <el-form-item :label="$t('assets.host.form.alias')" prop="alias">
          <el-input v-model="form.alias" maxlength="25" show-word-limit :placeholder="$t('assets.host.form.aliasPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('assets.host.col.ip')" prop="host_ip">
          <el-input v-model="form.host_ip" :placeholder="$t('assets.host.form.ipPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('assets.host.col.port')" prop="host_port">
          <el-input v-model="form.host_port" :placeholder="$t('assets.host.form.portPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('assets.host.col.group')" prop="group">
          <el-select v-model="form.group" :placeholder="$t('assets.host.form.groupPlaceholder')" style="width:100%">
            <el-option v-for="g in groups" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button v-if="!isEdit" type="success" @click="submitForm(true)" :loading="submitting">{{ $t('assets.action.saveAndContinue') }}</el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </DataTablePanel>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute, type LocationQuery } from 'vue-router'
import { ElMessage } from 'element-plus'
import { I18nT } from 'vue-i18n'
import {
  Search, Close, CopyDocument, EditPen, Delete,
  Monitor, FolderOpened,
} from '@element-plus/icons-vue'
import {
  getHostList, getHostListPage, deleteHost, getHostGroupNameList,
  addHost, updateHost,
} from '@/api'
import { createTab, _queueOpenTerminal } from '@/store'
import { ipv4Validator, portValidator } from '@/utils/host'
import { useListCrud } from '@/composables/useListCrud'
import { t } from '@/i18n'
// REV35-L5: 资产组标签颜色抽到 utils/groupClassifier
import { groupTagClass } from '@/utils/groupClassifier'
import DataTablePanel from '@/components/DataTablePanel.vue'

/** 主机行 (后端动态结构) */
interface HostRow {
  id: number | string
  alias: string
  host_ip: string
  host_port?: number | string
  host_user?: string
  group?: string
  is_online?: boolean
  configured?: boolean
  [k: string]: unknown
}

/** 主机表单 */
interface HostForm {
  id: number | string
  alias: string
  host_ip: string
  host_port: number | string
  group: string
}

/** 资产组名列表响应 */
interface GroupNameListResponse {
  code: number
  group_name_list_msg?: string[]
  [k: string]: unknown
}

const route = useRoute()

const defaultForm = (): HostForm => ({ id: '', alias: '', host_ip: '', host_port: '', group: '' })
// REVIEW-14 P1-2: IP 格式 + 端口 1-65535 范围校验
// I18N: computed 惰性求值，语言切换后校验消息随之更新
const rules = computed(() => ({
  alias: [{ required: true, message: t('assets.host.rules.alias'), trigger: 'blur' }],
  host_ip: [
    { required: true, message: t('assets.host.rules.ip'), trigger: 'blur' },
    { validator: ipv4Validator, trigger: 'blur' },
  ],
  host_port: [
    { required: true, message: t('assets.host.rules.port'), trigger: 'blur' },
    { validator: portValidator, trigger: 'blur' },
  ],
  group: [{ required: true, message: t('assets.host.rules.group'), trigger: 'change' }],
}))

// 业务特有：groupFilter 影响加载哪个 API
const groups = ref<string[]>([])
const groupFilter = ref<string>('')
const fromGroup = ref<string>('')

// 用 useListCrud 提供 keyword 过滤后的数据，再叠加 groupFilter
const {
  allData, loading, selectedRows, keyword,
  dialogVisible, isEdit, submitting, formRef, form,
  currentPage, pageSize,
  filteredData: kwFiltered,
  onSearch, loadData, openAdd, openEdit,
  submitForm, doDelete, batchDelete,
} = useListCrud({
  api: {
    load: () => Promise.resolve({}), // 不直接用，customLoad 替代
    dataKey: 'host_list_msg',
    create: addHost as unknown as (payload: unknown) => Promise<unknown>,
    update: updateHost as unknown as (payload: unknown) => Promise<unknown>,
    delete: deleteHost as unknown as (payload: unknown) => Promise<unknown>,
    deletePayload: (row) => ({ host_ip: (row as HostRow).host_ip }),
  },
  searchFields: ['host_ip', 'alias'],
  keepOpenFields: ['alias', 'host_ip', 'host_port'],
  entityKey: 'common.entity.host',
  // 业务特有：groupFilter 决定调 getHostList 还是 getHostListPage
  customLoad: async () => {
    return groupFilter.value
      ? await getHostListPage({ group_name: groupFilter.value }) as unknown as Record<string, unknown>
      : await getHostList() as unknown as Record<string, unknown>
  },
})

// 重新计算 filteredData（叠加 groupFilter）
const filteredData = computed<HostRow[]>(() => {
  let data = kwFiltered.value as HostRow[]
  if (groupFilter.value) {
    data = data.filter(r => r.group === groupFilter.value)
  }
  return data
})
const pagedData = computed<HostRow[]>(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})
const total = computed<number>(() => filteredData.value.length)

// ---------- 业务特有：分组筛选 + 关键资产 + 状态指示 ----------
async function loadGroups(): Promise<void> {
  try {
    const res = (await getHostGroupNameList()) as unknown as GroupNameListResponse
    if (res.code === 0) groups.value = res.group_name_list_msg || []
  } catch {
    // 静默：失败时仅留空下拉
  }
}

function onFilterChange(val: string | undefined): void {
  groupFilter.value = val || ''
  fromGroup.value = ''
  loadData()
}

function clearGroupFilter(): void {
  groupFilter.value = ''
  fromGroup.value = ''
  loadData()
}

function hostStatus(row: HostRow): string {
  if (row.is_online === true) return 'online'
  if (row.is_online === false) return 'offline'
  return 'unknown'
}

// 统计
const onlineCount = computed<number>(() => (allData.value as HostRow[]).filter(r => hostStatus(r) === 'online').length)
const offlineCount = computed<number>(() => total.value - onlineCount.value)
const configuredCount = computed<number>(() => (allData.value as HostRow[]).filter(r => r.configured === true).length)
const unconfiguredCount = computed<number>(() => total.value - configuredCount.value)

// ---------- 业务特有：IP 复制 ----------
function copyIp(ip: string): void {
  if (!ip) return
  const fallback = (): void => {
    const ta = document.createElement('textarea')
    ta.value = ip
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      ElMessage.success(t('assets.host.msg.copied', { ip }))
    } catch {
      ElMessage.warning(t('common.copyFail'))
    } finally {
      document.body.removeChild(ta)
    }
  }
  if (navigator.clipboard) {
    navigator.clipboard.writeText(ip).then(
      () => ElMessage.success(t('assets.host.msg.copied', { ip })),
      () => fallback()
    )
  } else {
    fallback()
  }
}

// ---------- 业务特有：远程打开 ----------
// REV34-M13: 跨窗口 openTerminal 不再使用 setTimeout 800ms 魔法数字
//   写入 localStorage 跨窗口“待打开任务” → 子窗口 RemoteSession.vue onMounted 读取
//   同时也加 URL params 作为冗余通道（独立 SFTP 窗口 一直这样用，保留兼容）
function openTerminal(row: HostRow): void {
  const user = row.host_user || 'root'
  _queueOpenTerminal(row.alias, user)  // 子窗口会读这条
  const win = window.open('/remote-session', '_blank')
  if (!win) {
    ElMessage.warning(t('assets.host.msg.popupBlocked'))
    return
  }
  ElMessage.success(t('assets.host.msg.terminalOpened', { name: row.alias }))
}

function openSftp(row: HostRow): void {
  const params = new URLSearchParams({
    tab: 'sftp',
    host: row.alias,
    user: row.host_user || 'root',
  })
  const win = window.open('/remote-session?' + params.toString(), '_blank')
  if (!win) {
    ElMessage.warning(t('assets.host.msg.popupBlocked'))
  } else {
    ElMessage.success(t('assets.host.msg.sftpOpened', { name: row.alias }))
  }
}

onMounted(() => {
  loadGroups()
  const q: LocationQuery = route.query
  if (typeof q.group === 'string') {
    groupFilter.value = q.group
    fromGroup.value = q.group
  }
  loadData()
})
</script>

<style scoped>
/* 状态 Tag 内圆点 */
.tag-dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
.tag-dot.online { background: var(--ogs-success); box-shadow: 0 0 4px var(--ogs-success); }
.tag-dot.offline { background: var(--ogs-text-muted); }
.tag-dot.unknown { background: var(--ogs-warning); }

/* 配置状态圆点 */
.list-toolbar .stats .dot-configured {
  background: var(--ogs-success);
  box-shadow: 0 0 0 3px var(--ogs-success-soft);
}
.list-toolbar .stats .dot-unconfigured {
  background: var(--ogs-warning);
  box-shadow: 0 0 0 3px var(--ogs-warning-soft);
}

.action-link.is-muted { color: var(--ogs-text-secondary); }
.action-link.is-muted:hover { color: var(--ogs-text); }
.action-link.is-danger { color: var(--ogs-danger); }
.action-link.is-danger:hover { color: var(--ogs-danger); opacity: 0.75; }

.action-icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 4px;
  cursor: pointer; color: var(--ogs-primary);
  background: transparent;
  transition: background 0.15s, color 0.15s;
  vertical-align: middle;
}
.action-icon-btn + .action-icon-btn { margin-left: 2px; }
.action-icon-btn:hover { background: var(--ogs-primary-soft); }
.action-icon-btn.is-danger { color: var(--ogs-danger); }
.action-icon-btn.is-danger:hover { background: rgba(220, 38, 38, 0.08); }
.action-icon-btn + .action-divider { margin-left: 4px; }

.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 60px 20px; gap: 8px;
  color: var(--ogs-text-secondary);
}
.empty-state p {
  font-size: 14px; font-weight: 600;
  color: var(--ogs-text); margin-top: 8px;
}
.empty-state span {
  font-size: 12px; color: var(--ogs-text-muted);
}
</style>
