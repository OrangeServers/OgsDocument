<template>
  <DataTablePanel
    eyebrow="GROUPS"
    :title="$t('users.group.title')"
    :panel-title="$t('users.group.panelTitle')"
    panel-sub="User Groups"
    :panel-icon="Avatar"
    :add-text="$t('users.group.add')"
    :page="currentPage"
    :page-size="pageSize"
    :total="total"
    @update:page="(p) => currentPage = p"
    @update:page-size="(s) => pageSize = s"
    @refresh="loadData"
    @add="openAdd()"
  >
    <template #subtitle>
      <I18nT keypath="users.group.subtitle" scope="global">
        <template #total><strong>{{ total }}</strong></template>
        <template #members><strong class="num" style="color:var(--ogs-primary)">{{ totalUsers }}</strong></template>
      </I18nT>
    </template>

    <template #filters>
      <el-input v-model="keyword" :placeholder="$t('users.group.searchPlaceholder')" clearable
                class="search-input" :prefix-icon="Search" @input="onSearch" />
    </template>

    <template #stats>
      <I18nT keypath="users.group.stats.totalGroups" tag="span" class="num" scope="global">
        <template #n><strong>{{ total }}</strong></template>
      </I18nT>
      <span><span class="dot" style="background:var(--ogs-primary)" />{{ $t('users.group.stats.totalMembers') }} <strong class="num">{{ totalUsers }}</strong></span>
      <span>
        <span class="dot" style="background:var(--ogs-success)" />
        <I18nT keypath="users.group.stats.avgPerGroup" scope="global">
          <template #n><strong class="num">{{ avgUsers }}</strong></template>
        </I18nT>
      </span>
    </template>

    <el-table :data="pagedData" :class="['is-compact']" stripe v-loading="loading" style="width:100%">
      <el-table-column prop="id" label="ID" width="62" sortable>
        <template #default="{ row }">
          <span class="num" style="color:var(--ogs-text-muted)">#{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('users.group.col.name')" min-width="180">
        <template #default="{ row }">
          <span class="group-name-cell">
            <span class="action-link" @click="goGroupUsers(row.name)">{{ row.name }}</span>
            <el-icon v-if="row.nums" :size="12" class="group-go-hint"><ArrowRight /></el-icon>
          </span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('users.group.col.memberCount')" width="110" align="center">
        <template #default="{ row }">
          <span v-if="row.nums" class="count-badge is-clickable" @click="goGroupUsers(row.name)"
                :title="$t('users.group.viewMembers', { n: row.nums })">{{ row.nums }}</span>
          <span v-else class="count-badge is-zero">0</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('users.group.col.remarks')" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.remarks" style="color:var(--ogs-text-secondary)">{{ row.remarks }}</span>
          <span v-else style="color:var(--ogs-text-muted)">—</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('users.group.col.actions')" width="160" fixed="right" align="right">
        <template #default="scope">
          <span class="action-link" @click="openEdit(scope.row)">{{ $t('common.action.edit') }}</span>
          <span class="action-divider" />
          <span class="action-link is-danger" @click="doDelete(scope.row)">{{ $t('common.action.delete') }}</span>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-state">
          <el-icon :size="40" style="color:var(--ogs-text-muted)"><Avatar /></el-icon>
          <p>{{ $t('users.group.empty.title') }}</p>
          <span>{{ $t('users.group.empty.hint') }}</span>
        </div>
      </template>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('users.group.dialog.edit') : $t('users.group.dialog.add')" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item v-if="isEdit" label="ID"><el-input v-model="form.id" disabled /></el-form-item>
        <el-form-item :label="$t('users.group.form.name')" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item v-if="isEdit" :label="$t('users.group.form.nums')"><el-input v-model="form.nums" disabled /></el-form-item>
        <el-form-item :label="$t('users.group.form.remarks')"><el-input v-model="form.remarks" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button v-if="!isEdit" type="success" @click="submitForm(true)" :loading="submitting">{{ $t('users.action.saveAndContinue') }}</el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </DataTablePanel>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { I18nT } from 'vue-i18n'
import { Search, Avatar, ArrowRight } from '@element-plus/icons-vue'
import {
  getUserGroupList, addUserGroup, updateUserGroup, deleteUserGroup,
} from '@/api'
import { useListCrud } from '@/composables/useListCrud'
import { t } from '@/i18n'
import DataTablePanel from '@/components/DataTablePanel.vue'

/** 用户组行 (后端动态结构) */
interface UserGroupRow {
  id: number | string
  name: string
  nums?: number | string
  remarks?: string
  [k: string]: unknown
}

/** 用户组表单 */
interface UserGroupForm {
  id: number | string
  name: string
  nums: number | string
  remarks: string
}

const router = useRouter()

const defaultForm = (): UserGroupForm => ({ id: '', name: '', nums: '', remarks: '' })
// I18N: computed 惰性求值，语言切换后校验消息随之更新
const rules = computed(() => ({
  name: [{ required: true, message: t('users.group.rules.name'), trigger: 'blur' }],
}))

const {
  allData, loading,
  dialogVisible, isEdit, submitting, formRef, form, keyword,
  currentPage, pageSize,
  filteredData, pagedData, total,
  onSearch, loadData, openAdd, openEdit,
  submitForm, doDelete,
} = useListCrud({
  api: {
    load: getUserGroupList as unknown as () => Promise<Record<string, unknown>>,
    dataKey: 'group_list_msg',
    create: addUserGroup as unknown as (payload: unknown) => Promise<unknown>,
    update: updateUserGroup as unknown as (payload: unknown) => Promise<unknown>,
    delete: deleteUserGroup as unknown as (payload: unknown) => Promise<unknown>,
    deletePayload: (row) => ({ name: (row as UserGroupRow).name }),
  },
  searchFields: ['name', 'remarks'],
  keepOpenFields: ['name', 'remarks'],
  entityKey: 'common.entity.userGroup',
  onAfterLoad: (data) => (data as UserGroupRow[]).sort((a, b) => (a.name || '').localeCompare(b.name || '')),
})

// 统计
const totalUsers = computed(() => (allData.value as UserGroupRow[]).reduce((sum, r) => sum + (parseInt(String(r.nums)) || 0), 0))
const avgUsers = computed(() => {
  if (!allData.value.length) return 0
  return Math.round(totalUsers.value / allData.value.length)
})

function goGroupUsers(groupName: string): void {
  router.push({ path: '/user-list', query: { group: groupName } })
}

// BUGFIX: useListCrud 不会自动调用 loadData，组件必须显式调用
onMounted(loadData)
</script>

<style scoped>
.group-name-cell { display: inline-flex; align-items: center; gap: 6px; }
.group-go-hint {
  color: var(--ogs-text-muted);
  transition: transform 0.15s, color 0.15s;
}
.group-name-cell:has(.action-link):hover .group-go-hint {
  color: var(--ogs-primary);
  transform: translateX(2px);
}
</style>
