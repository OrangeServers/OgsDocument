<template>
  <DataTablePanel
    eyebrow="CREDENTIALS"
    :title="$t('assets.sysUser.title')"
    :panel-title="$t('assets.sysUser.panelTitle')"
    panel-sub="Host Credentials"
    :panel-icon="Key"
    :add-text="$t('assets.sysUser.add')"
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
      <I18nT keypath="assets.sysUser.subtitle" scope="global">
        <template #total><strong>{{ total }}</strong></template>
        <template #key><strong class="num" style="color:var(--ogs-auth-key)">{{ keyCount }}</strong></template>
        <template #pwd><strong class="num" style="color:var(--ogs-auth-pwd)">{{ pwdCount }}</strong></template>
      </I18nT>
    </template>

    <template #filters>
      <el-input v-model="keyword" :placeholder="$t('assets.sysUser.searchPlaceholder')" clearable
                class="search-input" :prefix-icon="Search" @input="onSearch" />
    </template>

    <template #stats>
      <I18nT keypath="assets.sysUser.stats.total" tag="span" class="num" scope="global">
        <template #n><strong>{{ total }}</strong></template>
      </I18nT>
      <span><span class="dot" style="background:var(--ogs-proto-ssh)" />SSH <strong class="num">{{ sshCount }}</strong></span>
      <span><span class="dot" style="background:var(--ogs-proto-ftp)" />FTP <strong class="num">{{ ftpCount }}</strong></span>
      <span><span class="dot" style="background:var(--ogs-auth-key)" />{{ $t('assets.sysUser.stats.key') }} <strong class="num">{{ keyCount }}</strong></span>
      <span v-if="noCredCount > 0"><span class="dot" style="background:var(--ogs-danger)" />{{ $t('assets.sysUser.stats.noCred') }} <strong class="num">{{ noCredCount }}</strong></span>
    </template>

    <el-table :data="pagedData" :class="['is-compact']" stripe v-loading="loading"
              style="width:100%" :row-class-name="rowClassName">
      <el-table-column type="selection" width="44" />
      <el-table-column prop="id" label="ID" width="62" sortable>
        <template #default="{ row }">
          <span class="num" style="color:var(--ogs-text-muted)">#{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="alias" :label="$t('assets.sysUser.col.name')" min-width="160">
        <template #default="{ row }">
          <span style="font-weight:600;color:var(--ogs-text)">{{ row.alias }}</span>
          <span v-if="isPrivilegedUser(row.host_user)" class="critical-badge" :title="$t('assets.sysUser.privilegedTip')">ROOT</span>
        </template>
      </el-table-column>
      <el-table-column prop="host_user" :label="$t('assets.sysUser.col.username')" min-width="120">
        <template #default="{ row }">
          <span class="num" style="font-family:var(--ogs-mono);font-size:13px">{{ row.host_user }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.sysUser.col.protocol')" width="90" align="center">
        <template #default="{ row }">
          <span :class="['proto-tag', protoClass(row.agreement)]">{{ row.agreement || 'ssh' }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.sysUser.col.authType')" width="110" align="center">
        <template #default="{ row }">
          <span v-if="row.host_key" class="auth-tag is-key">{{ $t('assets.sysUser.auth.key') }}</span>
          <span v-else-if="row.host_password" class="auth-tag is-pwd">{{ $t('assets.sysUser.auth.password') }}</span>
          <span v-else class="auth-tag is-none">{{ $t('assets.sysUser.auth.none') }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remarks" :label="$t('assets.sysUser.col.remarks')" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.remarks" style="color:var(--ogs-text-secondary)">{{ row.remarks }}</span>
          <span v-else style="color:var(--ogs-text-muted)">—</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.sysUser.col.actions')" width="160" fixed="right" align="right">
        <template #default="scope">
          <span class="action-link" @click="openEdit(scope.row)">{{ $t('common.action.edit') }}</span>
          <span class="action-divider" />
          <span class="action-link is-danger" @click="doDelete(scope.row)">{{ $t('common.action.delete') }}</span>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-state">
          <el-icon :size="40" style="color:var(--ogs-text-muted)"><Key /></el-icon>
          <p>{{ $t('assets.sysUser.empty.title') }}</p>
          <span>{{ $t('assets.sysUser.empty.hint') }}</span>
        </div>
      </template>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('assets.sysUser.dialog.edit') : $t('assets.sysUser.dialog.add')" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item v-if="isEdit" label="ID"><el-input v-model="form.id" disabled /></el-form-item>
        <el-form-item :label="$t('assets.sysUser.form.alias')" prop="alias"><el-input v-model="form.alias" :placeholder="$t('assets.sysUser.form.aliasPlaceholder')" /></el-form-item>
        <el-form-item :label="$t('assets.sysUser.form.username')" prop="host_user"><el-input v-model="form.host_user" :placeholder="$t('assets.sysUser.form.usernamePlaceholder')" /></el-form-item>
        <el-form-item :label="$t('assets.sysUser.form.protocol')">
          <el-select v-model="form.agreement" style="width:100%">
            <el-option label="ssh" value="ssh" />
            <el-option label="ftp" value="ftp" />
            <el-option :label="$t('assets.sysUser.form.protocolCustom')" value="自定义" /><!-- i18n-ignore 协议值：与后端存储值一致 -->
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('assets.sysUser.form.password')"><el-input v-model="form.host_password" type="password" :placeholder="$t('assets.sysUser.form.optional')" show-password /></el-form-item>
        <el-form-item :label="$t('assets.sysUser.form.key')"><el-input v-model="form.host_key" type="textarea" :rows="2" :placeholder="$t('assets.sysUser.form.optional')" /></el-form-item>
        <el-form-item :label="$t('assets.sysUser.form.remarks')"><el-input v-model="form.remarks" :placeholder="$t('assets.sysUser.form.optional')" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button v-if="!isEdit" type="success" @click="submitForm(true)" :loading="submitting">{{ $t('assets.action.saveAndContinue') }}</el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </DataTablePanel>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { I18nT } from 'vue-i18n'
import { Search, Key } from '@element-plus/icons-vue'
import {
  getSysUserList, addSysUser, updateSysUser, deleteSysUser,
} from '@/api'
import { useListCrud } from '@/composables/useListCrud'
import { t } from '@/i18n'
import DataTablePanel from '@/components/DataTablePanel.vue'

/** 系统用户行 (后端动态结构) */
interface SysUserRow {
  id: number | string
  alias: string
  host_user: string
  agreement?: string
  host_password?: string
  host_key?: string
  remarks?: string
  [k: string]: unknown
}

/** 系统用户表单 */
interface SysUserForm {
  id: number | string
  alias: string
  host_user: string
  agreement: string
  host_password: string
  host_key: string
  remarks: string
}

const defaultForm = (): SysUserForm => ({
  id: '', alias: '', host_user: '', agreement: 'ssh',
  host_password: '', host_key: '', remarks: '',
})
// I18N: computed 惰性求值，语言切换后校验消息随之更新
const rules = computed(() => ({
  alias: [{ required: true, message: t('assets.sysUser.rules.alias'), trigger: 'blur' }],
  host_user: [{ required: true, message: t('assets.sysUser.rules.username'), trigger: 'blur' }],
}))

const crud = useListCrud({
  api: {
    load: getSysUserList as unknown as () => Promise<Record<string, unknown>>,
    dataKey: 'sys_user_list_msg',
    create: addSysUser as unknown as (payload: unknown) => Promise<unknown>,
    update: updateSysUser as unknown as (payload: unknown) => Promise<unknown>,
    delete: deleteSysUser as unknown as (payload: unknown) => Promise<unknown>,
    deletePayload: (row) => ({ alias: (row as SysUserRow).alias }),
  },
  searchFields: ['alias', 'host_user', 'remarks'],
  keepOpenFields: ['alias', 'host_user', 'host_password', 'host_key'],
  entityKey: 'common.entity.sysUser',
})
const {
  allData, loading, selectedRows, keyword,
  dialogVisible, isEdit, submitting, formRef, form,
  currentPage, pageSize,
  pagedData, total,
  onSearch, loadData, openAdd, openEdit,
  submitForm, doDelete, batchDelete,
} = crud

// ---------- 业务特有：协议样式 + 特权用户标记 + 行高亮 ----------
function protoClass(agreement: string): string {
  const a = (agreement || 'ssh').toLowerCase()
  if (a === 'ssh') return 'is-ssh'
  if (a === 'ftp') return 'is-ftp'
  return 'is-other'
}

function isPrivilegedUser(user: string): boolean {
  if (!user) return false
  const u = user.toLowerCase()
  return ['root', 'administrator', 'admin', 'sa', 'sysadmin'].includes(u)
}

function rowClassName({ row }: { row: SysUserRow }): string {
  return isPrivilegedUser(row.host_user) ? 'is-warn' : ''
}

// 统计 computed
const sshCount = computed(() => (allData.value as SysUserRow[]).filter(r => (r.agreement || 'ssh') === 'ssh').length)
const ftpCount = computed(() => (allData.value as SysUserRow[]).filter(r => r.agreement === 'ftp').length)
const keyCount = computed(() => (allData.value as SysUserRow[]).filter(r => r.host_key).length)
const pwdCount = computed(() => (allData.value as SysUserRow[]).filter(r => !r.host_key && r.host_password).length)
const noCredCount = computed(() => (allData.value as SysUserRow[]).filter(r => !r.host_key && !r.host_password).length)

// BUGFIX: useListCrud 不会自动调用 loadData，组件必须显式调用
onMounted(loadData)
</script>

<style scoped>
/* proto-tag / auth-tag / critical-badge 等由全局样式提供 */
</style>
