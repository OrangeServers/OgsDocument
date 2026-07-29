<template>
  <DataTablePanel
    eyebrow="IDENTITY"
    :title="$t('users.user.title')"
    :panel-title="$t('users.user.title')"
    panel-sub="Platform Users"
    :panel-icon="User"
    :add-text="$t('users.user.add')"
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
    <template #subtitle>
      <I18nT keypath="users.user.subtitle" scope="global">
        <template #total><strong>{{ total }}</strong></template>
        <template #admin><strong class="num" style="color:var(--ogs-role-admin)">{{ adminCount }}</strong></template>
      </I18nT>
    </template>

    <template #filters>
      <el-input v-model="keyword" :placeholder="$t('users.user.searchPlaceholder')" clearable
                class="search-input" :prefix-icon="Search" @input="onSearch" />
      <el-select v-model="groupFilter" :placeholder="$t('users.user.filterByGroup')" clearable
                 @change="onFilterChange" style="width:160px">
        <el-option v-for="g in groups" :key="g" :label="g" :value="g" />
      </el-select>
    </template>

    <template #active-filter>
      <!-- 跳转来源提示：从「用户组」点过来的活跃筛选 -->
      <span v-if="groupFilter && fromGroup" class="active-filter" :title="$t('users.user.fromGroupTip', { name: fromGroup })">
        <span class="filter-label">{{ $t('users.user.filterGroupLabel') }}</span>
        <span class="filter-value">{{ groupFilter }}</span>
        <span class="filter-clear" @click="clearGroupFilter" :title="$t('users.user.clearFilter')">
          <el-icon :size="10"><Close /></el-icon>
        </span>
      </span>
    </template>

    <template #stats>
      <I18nT keypath="users.user.stats.total" tag="span" class="num" scope="global">
        <template #n><strong>{{ total }}</strong></template>
      </I18nT>
      <span><span class="dot" style="background:var(--ogs-role-admin)" />{{ $t('users.user.stats.admin') }} <strong class="num">{{ adminCount }}</strong></span>
      <span><span class="dot" style="background:var(--ogs-role-audit)" />{{ $t('users.user.stats.audit') }} <strong class="num">{{ auditCount }}</strong></span>
      <span><span class="dot" style="background:var(--ogs-role-user)" />{{ $t('users.user.stats.normal') }} <strong class="num">{{ userCount }}</strong></span>
    </template>

    <el-table :data="pagedData" :class="['is-compact']" stripe v-loading="loading"
              style="width:100%" :row-class-name="rowClassName">
      <el-table-column type="selection" width="44" />
      <el-table-column prop="id" label="ID" width="62" sortable>
        <template #default="{ row }">
          <span class="num" style="color:var(--ogs-text-muted)">#{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" :label="$t('users.user.col.username')" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span style="font-weight:600;color:var(--ogs-text)">{{ row.name }}</span>
          <span v-if="row.usrole === 'admin'" class="critical-badge" :title="$t('users.role.admin')">ADMIN</span>
        </template>
      </el-table-column>
      <el-table-column prop="alias" :label="$t('users.user.col.alias')" min-width="110">
        <template #default="{ row }">
          <span class="num" style="color:var(--ogs-text-secondary)">{{ row.alias || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="mail" :label="$t('users.user.col.mail')" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.mail" style="font-family:var(--ogs-mono);font-size:var(--ogs-table-font-size)">{{ row.mail }}</span>
          <span v-else style="color:var(--ogs-text-muted)">—</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('users.user.col.group')" min-width="120">
        <template #default="{ row }">
          <span v-if="row.group" :class="['group-tag', groupTagClass(row.group)]">{{ row.group }}</span>
          <span v-else style="color:var(--ogs-text-muted)">—</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('users.user.col.role')" width="100" align="center">
        <template #default="{ row }">
          <span :class="['role-tag', roleClass(row.usrole)]">{{ roleLabel(row.usrole) }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('users.user.col.actions')" width="260" fixed="right" align="right">
        <template #default="scope">
          <span class="action-link" @click="openEdit(scope.row)">{{ $t('common.action.edit') }}</span>
          <span class="action-link is-muted" @click="openResetPwd(scope.row)">{{ $t('users.user.resetPwd') }}</span>
          <span class="action-divider" />
          <span class="action-link is-danger" @click="doDelete(scope.row)">{{ $t('common.action.delete') }}</span>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-state">
          <el-icon :size="40" style="color:var(--ogs-text-muted)"><User /></el-icon>
          <p>{{ $t('users.user.empty.title') }}</p>
          <span>{{ $t('users.user.empty.hint') }}</span>
        </div>
      </template>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('users.user.dialog.edit') : $t('users.user.dialog.add')" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item v-if="isEdit" label="ID"><el-input v-model="form.id" disabled /></el-form-item>
        <el-form-item :label="$t('users.user.form.username')" prop="name"><el-input v-model="form.name" :disabled="isEdit" /></el-form-item>
        <el-form-item :label="$t('users.user.form.alias')" prop="alias"><el-input v-model="form.alias" /></el-form-item>
        <el-form-item :label="$t('users.user.form.mail')"><el-input v-model="form.mail" /></el-form-item>
        <el-form-item :label="$t('users.user.form.role')">
          <el-select v-model="form.usrole" style="width:100%">
            <el-option :label="$t('users.user.form.roleOption.admin')" value="admin" />
            <el-option :label="$t('users.user.form.roleOption.audit')" value="audit" />
            <el-option :label="$t('users.user.form.roleOption.user')" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!isEdit" :label="$t('users.user.form.password')" prop="password"><el-input v-model="form.password" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button v-if="!isEdit" type="success" @click="submitForm(true)" :loading="submitting">{{ $t('users.action.saveAndContinue') }}</el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗（业务特有：管理员二次确认 sudo 模式） -->
    <el-dialog v-model="pwdDialogVisible" :title="$t('users.user.pwdDialog.title')" width="460px">
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px" @submit.prevent="submitResetPwd">
        <el-form-item :label="$t('users.user.pwdDialog.username')"><el-input :value="pwdForm.name" disabled /></el-form-item>
        <el-form-item :label="$t('users.user.pwdDialog.newPwd')" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password :placeholder="$t('users.user.pwdDialog.newPwdPlaceholder')" />
        </el-form-item>
        <!-- REVIEW-14 P1-8: 管理员二次确认（sudo 模式） -->
        <el-form-item :label="$t('users.user.pwdDialog.adminPwd')" prop="admin_password">
          <el-input v-model="pwdForm.admin_password" type="password" show-password :placeholder="$t('users.user.pwdDialog.adminPwdPlaceholder')" />
          <div class="sudo-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ $t('users.user.pwdDialog.sudoHint') }}</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdDialogVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="submitResetPwd" :loading="pwdSubmitting">{{ $t('users.user.pwdDialog.confirm') }}</el-button>
      </template>
    </el-dialog>
  </DataTablePanel>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute, type LocationQuery } from 'vue-router'
import { ElMessage } from 'element-plus'
import { I18nT } from 'vue-i18n'
import { Search, Close, User, InfoFilled } from '@element-plus/icons-vue'
import { getUserListAll, getGroupNameList, resetUserPwd, http } from '@/api'
import { store } from '@/store'
import { useListCrud } from '@/composables/useListCrud'
import { t } from '@/i18n'
import DataTablePanel from '@/components/DataTablePanel.vue'
// REV35-L5: 组名 5 色抽到 utils/groupClassifier
import { groupTagClass } from '@/utils/groupClassifier'

/** 用户行 (后端动态结构) */
interface UserRow {
  id: number | string
  name: string
  alias?: string
  mail?: string
  usrole?: string
  group?: string
  password?: string
  remarks?: string
  [k: string]: unknown
}

/** 用户表单 */
interface UserForm {
  id: number | string
  name: string
  alias: string
  mail: string
  usrole: string
  password: string
  group: string
  remarks?: string
}

/** 重置密码表单 */
interface PwdForm {
  name: string
  new_password: string
  admin_password: string
}

/** 通用 HTTP 响应 */
interface ApiResp {
  code: number
  msg?: string
  group_name_list_msg?: string[]
  [k: string]: unknown
}

const route = useRoute()

const defaultForm = (): UserForm => ({
  id: '', name: '', alias: '', mail: '', usrole: 'user', password: '', group: '',
})
// I18N: computed 惰性求值，语言切换后校验消息随之更新
const rules = computed(() => ({
  name: [{ required: true, message: t('users.user.rules.username'), trigger: 'blur' }],
  alias: [{ required: true, message: t('users.user.rules.alias'), trigger: 'blur' }],
}))

// 业务特有：add/update payload 不同（add 不带 id/remarks，update 带）
async function userApiSubmit(payload: unknown, isEdit: boolean): Promise<void> {
  const url = isEdit ? '/account/user/update' : '/account/user/add'
  const p = payload as UserForm
  const body = isEdit
    ? { id: p.id, name: p.name, alias: p.alias, password: p.password,
        usrole: p.usrole, mail: p.mail, group: p.group, remarks: p.remarks || '' }
    : { name: p.name, alias: p.alias, password: p.password,
        usrole: p.usrole, mail: p.mail, group: p.group }
  const res = (await http.post(url, body)) as unknown as ApiResp
  if (res.code !== 0) {
    ElMessage.error(res.msg || t('common.crud.operationFail'))
    throw new Error(res.msg || 'fail')
  }
}

// 用 useListCrud 提供 filteredData（keyword 过滤后），再加 groupFilter
// 注意：useListCrud 的 pagedData/total 不感知 groupFilter，故在 UserList 内部重算
const {
  allData, loading, selectedRows, keyword,
  dialogVisible, isEdit, submitting, formRef, form,
  currentPage, pageSize,
  filteredData: kwFiltered, // 仅 keyword 过滤后的数据
  onSearch, loadData, openAdd, openEdit,
  submitForm, doDelete, batchDelete,
} = useListCrud({
  api: {
    load: getUserListAll as unknown as () => Promise<Record<string, unknown>>,
    dataKey: 'acc_user_list_msg',
    create: (payload) => userApiSubmit(payload, false),
    update: (payload) => userApiSubmit(payload, true),
    delete: (row) => http.post('/account/user/del', { name: (row as UserRow).name }) as unknown as Promise<unknown>,
  },
  searchFields: ['name', 'alias', 'mail'],
  keepOpenFields: ['name', 'alias', 'mail', 'password'],
  entityKey: 'common.entity.user',
})

// ---------- 业务特有：分组筛选 + 角色统计 ----------
const groups = ref<string[]>([])
const groupFilter = ref<string>('')
const fromGroup = ref<string>('')

// 重新计算过滤数据（加入 groupFilter）
const filteredData = computed<UserRow[]>(() => {
  let data = kwFiltered.value as UserRow[]
  if (groupFilter.value) {
    data = data.filter(r => r.group === groupFilter.value)
  }
  return data
})
const pagedData = computed<UserRow[]>(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})
const total = computed<number>(() => filteredData.value.length)

async function loadGroups(): Promise<void> {
  try {
    const res = (await getGroupNameList()) as unknown as ApiResp
    if (res.code === 0) groups.value = res.group_name_list_msg || []
  } catch {
    // 静默：失败时仅留空下拉
  }
}

function onFilterChange(): void {
  currentPage.value = 1
  fromGroup.value = ''  // 用户手动选择视为非「来源」
}

function clearGroupFilter(): void {
  groupFilter.value = ''
  fromGroup.value = ''
  currentPage.value = 1
}

// ---------- 角色统计 ----------
const adminCount = computed<number>(() => (allData.value as UserRow[]).filter(r => r.usrole === 'admin').length)
const auditCount = computed<number>(() => (allData.value as UserRow[]).filter(r => r.usrole === 'audit').length)
const userCount = computed<number>(() => (allData.value as UserRow[]).filter(r => r.usrole === 'user').length)

// ---------- 角色/组名样式 ----------
function roleClass(role: string): string {
  if (role === 'admin') return 'is-admin'
  if (role === 'audit') return 'is-audit'
  if (role === 'user') return 'is-user'
  return 'is-default'
}

function roleLabel(role: string): string {
  if (role === 'admin') return t('users.role.admin')
  if (role === 'audit') return t('users.role.audit')
  if (role === 'user') return t('users.role.user')
  return t('users.role.unknown')
}

// REV35-L5: groupTagClass 已抽到 utils/groupClassifier.js

function rowClassName({ row }: { row: UserRow }): string {
  return row.usrole === 'admin' ? 'is-critical' : ''
}

// 包装 openEdit：兼容旧数据中非标准角色（如 'develop'），修正为 'user'
function openEditWithRole(row: UserRow): void {
  openEdit(row)
  const role = String(form.value.usrole || '')
  if (!['admin','audit','user'].includes(role)) {
    form.value.usrole = 'user'
  }
}

// ---------- 重置密码弹窗（业务特有：sudo 模式） ----------
const pwdDialogVisible = ref<boolean>(false)
const pwdSubmitting = ref<boolean>(false)
const pwdFormRef = ref<{ validate: () => Promise<boolean> } | null>(null)
const pwdForm = ref<PwdForm>({ name: '', new_password: '', admin_password: '' })
// I18N: computed 惰性求值，语言切换后校验消息随之更新
const pwdRules = computed(() => ({
  new_password: [
    { required: true, message: t('users.user.pwdDialog.rules.newPwdRequired'), trigger: 'blur' },
    { min: 6, message: t('users.user.pwdDialog.rules.newPwdMin'), trigger: 'blur' },
  ],
  admin_password: [
    { required: true, message: t('users.user.pwdDialog.rules.adminPwdRequired'), trigger: 'blur' },
    { min: 1, message: t('users.user.pwdDialog.rules.adminPwdEmpty'), trigger: 'blur' },
  ],
}))
function openResetPwd(row: UserRow): void {
  pwdForm.value = { name: row.name, new_password: '', admin_password: '' }
  pwdDialogVisible.value = true
}
async function submitResetPwd(): Promise<void> {
  await pwdFormRef.value?.validate()
  if (!pwdForm.value.admin_password) {
    ElMessage.error(t('users.user.pwdDialog.msg.adminPwdNeeded'))
    return
  }
  pwdSubmitting.value = true
  try {
    await resetUserPwd({
      name: pwdForm.value.name,
      new_password: pwdForm.value.new_password,
      admin_password: pwdForm.value.admin_password,
      admin_name: (store?.user?.username) || '',
    } as unknown as Record<string, unknown>)
    ElMessage.success(t('users.user.pwdDialog.msg.success'))
    pwdDialogVisible.value = false
  } catch {
    ElMessage.error(t('users.user.pwdDialog.msg.fail'))
  } finally {
    pwdSubmitting.value = false
  }
}

onMounted(() => {
  loadGroups()
  const q: LocationQuery = route.query
  if (typeof q.group === 'string') {
    groupFilter.value = q.group
    fromGroup.value = q.group
  }
  loadData() // BUGFIX: useListCrud 不会自动调用 loadData，组件必须显式调用
})
</script>

<style scoped>
/* REVIEW-14 P1-8: 管理员二次确认提示 */
.sudo-hint {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 12px; line-height: 1.5;
  color: var(--ogs-text-muted, #909399);
  margin-top: 4px; margin-bottom: -8px;
}
.sudo-hint .el-icon {
  color: var(--ogs-warning, #e6a23c); font-size: 14px;
  flex-shrink: 0; margin-top: 1px;
}
</style>
