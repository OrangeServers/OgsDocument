<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <span class="page-eyebrow">ACL</span>
        <h2>{{ $t('authority.title') }}</h2>
        <p>{{ $t('authority.subtitle') }} <strong>{{ total }}</strong> {{ $t('authority.subtitleUnit') }}</p>
      </div>
      <div class="page-actions">
        <el-button @click="loadData">{{ $t('common.action.refresh') }}</el-button>
        <el-button type="primary" @click="openAdd"><el-icon><Plus /></el-icon>{{ $t('authority.createRule') }}</el-button>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <span class="panel-icon"><el-icon :size="14"><Lock /></el-icon></span>
        <span class="panel-title">{{ $t('authority.panelTitle') }}</span>
        <span class="panel-sub">Access Control</span>
      </div>
      <div class="list-toolbar">
        <el-input v-model="keyword" :placeholder="$t('authority.searchPlaceholder')" clearable class="search-input" :prefix-icon="Search" @input="onSearch" />
        <div class="stats">
          <span class="num">{{ $t('authority.stats.totalPrefix') }} <strong>{{ total }}</strong> {{ $t('authority.stats.totalSuffix') }}</span>
          <span><span class="dot" style="background:var(--ogs-primary)" />{{ $t('authority.stats.active') }} <strong class="num">{{ activeCount }}</strong></span>
          <span v-if="systemCount > 0"><span class="dot" style="background:var(--ogs-warning)" />{{ $t('authority.stats.system') }} <strong class="num">{{ systemCount }}</strong></span>
        </div>
      </div>
      <div class="panel-body" style="padding:0">
        <el-table :data="filteredData" :class="['is-compact']" stripe v-loading="loading" style="width:100%" :row-class-name="rowClassName">
        <el-table-column :label="$t('authority.columns.name')" min-width="160" prop="name">
          <template #default="{ row }">
            <span style="font-weight:600;color:var(--ogs-text)">{{ row.name }}</span>
            <span v-if="isSystemRule(row.name)" class="critical-badge" :title="$t('authority.sysBadgeTitle')">SYS</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('authority.columns.users')" min-width="160">
          <template #default="{ row }">
            <span v-if="!safeList(row.user).length" class="chip is-empty">{{ $t('authority.allUsers') }}</span>
            <el-popover v-else :width="420" placement="bottom-start" :show-arrow="false" trigger="click" :hide-after="0" popper-class="cmd-popover ip-popover" :offset="6">
              <template #reference>
                <div class="ip-pill-wrap" :title="safeList(row.user).length > 1 ? $t('authority.popover.viewAllUsers') : ''" @click.stop>
                  <span class="ip-pill">
                    <el-icon :size="10"><User /></el-icon>
                    <span class="ip-pill-text">{{ safeList(row.user)[0] }}</span>
                  </span>
                  <span v-if="safeList(row.user).length > 1" class="ip-pill-more" :title="$t('authority.popover.moreUsers', { n: safeList(row.user).length - 1 })">
                    +{{ safeList(row.user).length - 1 }}
                  </span>
                  <span class="ip-pill-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><User /></el-icon>
                    <span>{{ $t('authority.columns.users') }}</span>
                    <span class="cmd-popover-badge cmd-popover-badge--ghost">{{ $t('authority.popover.userCount', { n: safeList(row.user).length }) }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span v-if="row.name" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.name }}
                    </span>
                    <span v-if="isSystemRule(row.name)" class="cmd-popover-chip is-active">
                      <el-icon :size="10"><Lock /></el-icon>{{ $t('authority.systemDefault') }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content">
                  <ul class="ip-popover-list">
                    <li v-for="(u, i) in safeList(row.user)" :key="i" class="ip-popover-item">
                      <span class="ip-popover-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                      <el-icon :size="11" class="ip-popover-ico"><User /></el-icon>
                      <span class="ip-popover-name">{{ u }}</span>
                      <span class="ip-popover-copy" :title="$t('authority.popover.copyUser')" @click.stop="copyText(u)">
                        <el-icon :size="10"><CopyDocument /></el-icon>
                      </span>
                    </li>
                  </ul>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('authority.popover.closeTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(safeList(row.user).join('\n'))">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('authority.popover.copyAll') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column :label="$t('authority.columns.userGroups')" min-width="160">
          <template #default="{ row }">
            <span v-if="!safeList(row.user_group).length" style="color:var(--ogs-text-muted)">—</span>
            <el-popover v-else :width="420" placement="bottom-start" :show-arrow="false" trigger="click" :hide-after="0" popper-class="cmd-popover ip-popover" :offset="6">
              <template #reference>
                <div class="ip-pill-wrap" :title="safeList(row.user_group).length > 1 ? $t('authority.popover.viewAllUserGroups') : ''" @click.stop>
                  <span class="ip-pill">
                    <el-icon :size="10"><UserFilled /></el-icon>
                    <span class="ip-pill-text">{{ safeList(row.user_group)[0] }}</span>
                  </span>
                  <span v-if="safeList(row.user_group).length > 1" class="ip-pill-more" :title="$t('authority.popover.moreGroups', { n: safeList(row.user_group).length - 1 })">
                    +{{ safeList(row.user_group).length - 1 }}
                  </span>
                  <span class="ip-pill-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><UserFilled /></el-icon>
                    <span>{{ $t('authority.columns.userGroups') }}</span>
                    <span class="cmd-popover-badge cmd-popover-badge--ghost">{{ $t('authority.popover.groupCount', { n: safeList(row.user_group).length }) }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span v-if="row.name" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.name }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content">
                  <ul class="ip-popover-list">
                    <li v-for="(g, i) in safeList(row.user_group)" :key="i" class="ip-popover-item">
                      <span class="ip-popover-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                      <el-icon :size="11" class="ip-popover-ico"><UserFilled /></el-icon>
                      <span class="ip-popover-name">{{ g }}</span>
                      <span class="ip-popover-copy" :title="$t('authority.popover.copyGroup')" @click.stop="copyText(g)">
                        <el-icon :size="10"><CopyDocument /></el-icon>
                      </span>
                    </li>
                  </ul>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('authority.popover.closeTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(safeList(row.user_group).join('\n'))">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('authority.popover.copyAll') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column :label="$t('authority.columns.hostGroups')" min-width="160">
          <template #default="{ row }">
            <span v-if="!safeList(row.host_group).length" style="color:var(--ogs-text-muted)">—</span>
            <el-popover v-else :width="440" placement="bottom-start" :show-arrow="false" trigger="click" :hide-after="0" popper-class="cmd-popover ip-popover" :offset="6">
              <template #reference>
                <div class="ip-pill-wrap" :title="safeList(row.host_group).length > 1 ? $t('authority.popover.viewAllHostGroups') : ''" @click.stop>
                  <span :class="['ip-pill', hostChipClass(safeList(row.host_group)[0])]">
                    <el-icon :size="10"><FolderOpened /></el-icon>
                    <span class="ip-pill-text">{{ safeList(row.host_group)[0] }}</span>
                  </span>
                  <span v-if="safeList(row.host_group).length > 1" class="ip-pill-more" :title="$t('authority.popover.moreGroups', { n: safeList(row.host_group).length - 1 })">
                    +{{ safeList(row.host_group).length - 1 }}
                  </span>
                  <span class="ip-pill-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><FolderOpened /></el-icon>
                    <span>{{ $t('authority.columns.hostGroups') }}</span>
                    <span class="cmd-popover-badge cmd-popover-badge--ghost">{{ $t('authority.popover.groupCount', { n: safeList(row.host_group).length }) }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span v-if="row.name" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.name }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content">
                  <ul class="ip-popover-list">
                    <li v-for="(g, i) in safeList(row.host_group)" :key="i" class="ip-popover-item">
                      <span class="ip-popover-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                      <el-icon :size="11" class="ip-popover-ico"><FolderOpened /></el-icon>
                      <span :class="['ip-popover-name', hostChipClass(g)]">{{ g }}</span>
                      <span class="ip-popover-copy" :title="$t('authority.popover.copyGroup')" @click.stop="copyText(g)">
                        <el-icon :size="10"><CopyDocument /></el-icon>
                      </span>
                    </li>
                  </ul>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('authority.popover.closeTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(safeList(row.host_group).join('\n'))">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('authority.popover.copyAll') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column :label="$t('authority.columns.sysUsers')" min-width="160">
          <template #default="{ row }">
            <span v-if="!safeList(row.sys_user).length" style="color:var(--ogs-text-muted)">—</span>
            <el-popover v-else :width="420" placement="bottom-start" :show-arrow="false" trigger="click" :hide-after="0" popper-class="cmd-popover ip-popover" :offset="6">
              <template #reference>
                <div class="ip-pill-wrap" :title="safeList(row.sys_user).length > 1 ? $t('authority.popover.viewAllSysUsers') : ''" @click.stop>
                  <span class="ip-pill">
                    <el-icon :size="10"><Avatar /></el-icon>
                    <span class="ip-pill-text">{{ safeList(row.sys_user)[0] }}</span>
                  </span>
                  <span v-if="safeList(row.sys_user).length > 1" class="ip-pill-more" :title="$t('authority.popover.moreUsers', { n: safeList(row.sys_user).length - 1 })">
                    +{{ safeList(row.sys_user).length - 1 }}
                  </span>
                  <span class="ip-pill-hint" aria-hidden="true">
                    <el-icon :size="10"><ZoomIn /></el-icon>
                  </span>
                </div>
              </template>
              <div class="cmd-popover-body" @click.stop>
                <div class="cmd-popover-head">
                  <div class="cmd-popover-title">
                    <el-icon :size="13"><Avatar /></el-icon>
                    <span>{{ $t('authority.columns.sysUsers') }}</span>
                    <span class="cmd-popover-badge cmd-popover-badge--ghost">{{ $t('authority.popover.groupCount', { n: safeList(row.sys_user).length }) }}</span>
                  </div>
                  <div class="cmd-popover-meta">
                    <span v-if="row.name" class="cmd-popover-chip">
                      <el-icon :size="10"><Document /></el-icon>{{ row.name }}
                    </span>
                  </div>
                </div>
                <div class="cmd-popover-content">
                  <ul class="ip-popover-list">
                    <li v-for="(u, i) in safeList(row.sys_user)" :key="i" class="ip-popover-item">
                      <span class="ip-popover-idx">{{ String(i + 1).padStart(2, '0') }}</span>
                      <el-icon :size="11" class="ip-popover-ico"><Avatar /></el-icon>
                      <span class="ip-popover-name">{{ u }}</span>
                      <span class="ip-popover-copy" :title="$t('authority.popover.copyUser')" @click.stop="copyText(u)">
                        <el-icon :size="10"><CopyDocument /></el-icon>
                      </span>
                    </li>
                  </ul>
                </div>
                <div class="cmd-popover-foot">
                  <span class="cmd-popover-tip">
                    <el-icon :size="10"><InfoFilled /></el-icon>
                    {{ $t('authority.popover.closeTip') }}
                  </span>
                  <el-button size="small" plain type="primary" @click="copyText(safeList(row.sys_user).join('\n'))">
                    <el-icon :size="12"><CopyDocument /></el-icon>
                    <span>{{ $t('authority.popover.copyAll') }}</span>
                  </el-button>
                </div>
              </div>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column :label="$t('authority.columns.remarks')" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.remarks" style="color:var(--ogs-text-secondary)">{{ row.remarks }}</span>
            <span v-else style="color:var(--ogs-text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('authority.columns.actions')" width="160" fixed="right" align="right">
          <template #default="scope">
            <span class="action-link" :class="{ 'is-disabled': isSystemRule(scope.row.name) }" @click="openEdit(scope.row)">{{ $t('common.action.edit') }}</span>
            <span class="action-divider" />
            <span class="action-link is-danger" :class="{ 'is-disabled': isSystemRule(scope.row.name) }" @click="doDelete(scope.row)">{{ $t('common.action.delete') }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state">
            <el-icon :size="40" style="color:var(--ogs-text-muted)"><Lock /></el-icon>
            <p>{{ $t('authority.empty') }}</p>
            <span>{{ $t('authority.emptyHint') }}</span>
          </div>
        </template>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('authority.dialog.editTitle') : $t('authority.dialog.createTitle')" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item :label="$t('authority.dialog.name')" prop="name">
          <el-input v-model="form.name" :disabled="isEdit" />
        </el-form-item>
        <el-form-item :label="$t('authority.dialog.user')">
          <el-select v-model="form.user" multiple :placeholder="$t('authority.dialog.selectUser')" style="width:100%">
            <el-option v-for="u in userOptions" :key="u.name" :label="u.name" :value="u.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('authority.dialog.userGroup')">
          <el-select v-model="form.user_group" multiple :placeholder="$t('authority.dialog.selectUserGroup')" style="width:100%">
            <el-option v-for="g in userGroupOptions" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('authority.dialog.hostGroup')">
          <el-select v-model="form.host_group" multiple :placeholder="$t('authority.dialog.selectHostGroup')" style="width:100%">
            <el-option v-for="g in hostGroupOptions" :key="g.name" :label="g.name" :value="g.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('authority.dialog.sysUser')">
          <el-select v-model="form.sys_user" multiple :placeholder="$t('authority.dialog.selectSysUser')" style="width:100%">
            <el-option v-for="u in sysUserOptions" :key="u.name" :label="u.name" :value="u.name" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('authority.dialog.remarks')">
          <el-input v-model="form.remarks" :placeholder="$t('authority.dialog.remarksPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button v-if="!isEdit" type="success" @click="submitForm(true)" :loading="submitting">{{ $t('authority.dialog.saveContinue') }}</el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, User, UserFilled, FolderOpened, Avatar, ZoomIn, Document, InfoFilled, CopyDocument } from '@element-plus/icons-vue'
import { getAuthList, getAuthOptions, deleteAuth, http } from '@/api'
import { t } from '@/i18n'

// 协议值：后端系统默认授权规则名，不参与翻译
const SYSTEM_RULE_NAME = '所有权限' // i18n-ignore

function isSystemRule(name: string | undefined): boolean {
  return name === SYSTEM_RULE_NAME
}

/** 权限行 (后端 auth_host_list_msg 返回) */
interface AuthRow {
  name: string
  user?: string[] | string | null
  user_group?: string[] | string | null
  host_group?: string[] | string | null
  sys_user?: string[] | string | null
  remarks?: string
  [k: string]: unknown
}

/** 选项 (name 字段是后端下拉选项) */
interface NameOption {
  name: string
  [k: string]: unknown
}

/** 表单 */
interface AuthForm {
  name: string
  user: string[]
  user_group: string[]
  host_group: string[]
  sys_user: string[]
  remarks: string
}

/** auth 列表响应 */
interface AuthListResp {
  auth_host_list_msg?: AuthRow[]
  [k: string]: unknown
}

/** options 响应 (4 种 req_type 复用) */
interface AuthOptionsResp {
  msg?: NameOption[]
  [k: string]: unknown
}

// 通用 helper：任意可能为 null / undefined / 非数组的字段，安全返回数组
function safeList(x: string | string[] | null | undefined): string[] {
  if (Array.isArray(x)) return x
  if (x == null) return []
  return [x]
}

// 通用复制（带 Element Plus 成功提示）
function copyText(text: string | undefined | null): void {
  if (!text) return
  const fb = (): void => {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.cssText = 'position:fixed;opacity:0'
    document.body.appendChild(ta)
    ta.select()
    try { document.execCommand('copy'); ElMessage.success(t('common.copySuccess')) }
    catch { ElMessage.warning(t('common.copyFail')) }
    finally { document.body.removeChild(ta) }
  }
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => ElMessage.success(t('common.copySuccess')), fb)
  else fb()
}

const tableData = ref<AuthRow[]>([])
const keyword = ref<string>('')
const loading = ref<boolean>(false)
const dialogVisible = ref<boolean>(false)
const isEdit = ref<boolean>(false)
const submitting = ref<boolean>(false)
const formRef = ref<{ validate: () => Promise<boolean> } | null>(null)
const userOptions = ref<NameOption[]>([])
const userGroupOptions = ref<NameOption[]>([])
const hostGroupOptions = ref<NameOption[]>([])
const sysUserOptions = ref<NameOption[]>([])
const form = ref<AuthForm>({ name: '', user: [], user_group: [], host_group: [], sys_user: [], remarks: '' })
// computed：校验提示随语言切换即时更新
const rules = computed(() => ({ name: [{ required: true, message: t('authority.rules.nameRequired'), trigger: 'blur' }] }))

const filteredData = computed<AuthRow[]>(() => {
  if (!keyword.value) return tableData.value
  const kw = keyword.value.toLowerCase()
  return tableData.value.filter(r =>
    (r.name && r.name.toLowerCase().includes(kw)) ||
    (r.remarks && r.remarks.toLowerCase().includes(kw))
  )
})
const total = computed<number>(() => filteredData.value.length)
const activeCount = computed<number>(() => filteredData.value.filter(r => !isSystemRule(r.name)).length)
const systemCount = computed<number>(() => filteredData.value.filter(r => isSystemRule(r.name)).length)

function onSearch(): void {}

function hostChipClass(group: string | null | undefined): string {
  if (!group) return ''
  const g = group.toLowerCase()
  if (/prod|prd|生产|线上/.test(g)) return 'is-prod' // i18n-ignore（协议值：分组名分类关键字）
  if (/stag|stg|预发|灰度/.test(g)) return 'is-staging' // i18n-ignore
  if (/test|测试|qa/.test(g)) return 'is-test' // i18n-ignore
  if (/cache|redis|mq|中间件|db/.test(g)) return 'is-cache' // i18n-ignore
  return 'is-other'
}

function rowClassName({ row }: { row: AuthRow }): string {
  return isSystemRule(row.name) ? 'is-warn' : ''
}

async function loadData(): Promise<void> {
  loading.value = true
  try {
    const res = (await getAuthList()) as unknown as AuthListResp
    if (res.auth_host_list_msg) tableData.value = res.auth_host_list_msg
  } finally { loading.value = false }
}

async function loadOptions(): Promise<void> {
  try {
    const [userRes, ugRes, hgRes, suRes] = await Promise.all([
      getAuthOptions({ req_type: 'user' } as unknown as Record<string, unknown>) as unknown as Promise<AuthOptionsResp>,
      getAuthOptions({ req_type: 'user_group' } as unknown as Record<string, unknown>) as unknown as Promise<AuthOptionsResp>,
      getAuthOptions({ req_type: 'host_group' } as unknown as Record<string, unknown>) as unknown as Promise<AuthOptionsResp>,
      getAuthOptions({ req_type: 'sys_user' } as unknown as Record<string, unknown>) as unknown as Promise<AuthOptionsResp>,
    ])
    userOptions.value = userRes.msg || []
    userGroupOptions.value = ugRes.msg || []
    hostGroupOptions.value = hgRes.msg || []
    sysUserOptions.value = suRes.msg || []
  } catch {
    // 静默：options 加载失败仅留空下拉
  }
}

async function openAdd(): Promise<void> {
  isEdit.value = false
  form.value = { name: '', user: [], user_group: [], host_group: [], sys_user: [], remarks: '' }
  dialogVisible.value = true
  await loadOptions()
}

async function openEdit(row: AuthRow): Promise<void> {
  isEdit.value = true
  form.value = {
    name: row.name,
    user: Array.isArray(row.user) ? row.user : [],
    user_group: Array.isArray(row.user_group) ? row.user_group : [],
    host_group: Array.isArray(row.host_group) ? row.host_group : [],
    sys_user: Array.isArray(row.sys_user) ? row.sys_user : [],
    remarks: row.remarks || '',
  }
  dialogVisible.value = true
  await loadOptions()
}

async function submitForm(keepOpen = false): Promise<void> {
  await formRef.value?.validate()
  submitting.value = true
  try {
    const url = isEdit.value ? '/auth/host/update' : '/auth/host/add'
    await http.post(url, form.value as unknown as Record<string, unknown>)
    ElMessage.success(t('authority.msg.opSuccess'))
    if (keepOpen && !isEdit.value) {
      form.value.name = ''; form.value.remarks = ''
    } else {
      dialogVisible.value = false
    }
    loadData()
  } catch { ElMessage.error(t('common.crud.operationFail')) }
  finally { submitting.value = false }
}

async function doDelete(row: AuthRow): Promise<void> {
  if (isSystemRule(row.name)) {
    ElMessage.warning(t('authority.msg.systemNoDelete'))
    return
  }
  await ElMessageBox.confirm(t('authority.msg.deleteConfirm'), t('common.crud.prompt'), { type: 'warning' })
  try {
    await deleteAuth({ name: row.name } as unknown as Record<string, unknown>)
    loadData()
    ElMessage.success(t('common.crud.deleteSuccess'))
  } catch { ElMessage.error(t('common.crud.deleteFail')) }
}

onMounted(loadData)
</script>
