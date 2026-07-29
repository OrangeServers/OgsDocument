<template>
  <DataTablePanel
    :eyebrow="$t('assets.group.eyebrow')"
    :title="$t('assets.group.title')"
    :subtitle="$t('assets.group.subtitle')"
    :panel-title="$t('assets.group.panelTitle')"
    panel-sub="Group Registry"
    :panel-icon="FolderOpened"
    :add-text="$t('assets.group.add')"
    :page="currentPage"
    :page-size="pageSize"
    :total="total"
    @update:page="(p) => currentPage = p"
    @update:page-size="(s) => pageSize = s"
    @refresh="loadData"
    @add="openAdd()"
  >
    <template #filters>
      <el-input v-model="keyword" :placeholder="$t('assets.group.searchPlaceholder')" clearable
                class="search-input" :prefix-icon="Search" @input="currentPage=1" />
    </template>

    <template #stats>
      <span><span class="dot dot-online"></span>{{ $t('assets.group.stats.configured') }} <strong class="num">{{ stats.configured }}</strong></span>
      <span><span class="dot" style="background:var(--ogs-text-muted)"></span>{{ $t('assets.group.stats.empty') }} <strong class="num">{{ stats.empty }}</strong></span>
      <span>{{ $t('assets.group.stats.totalHosts') }} <strong class="num">{{ stats.totalHosts }}</strong></span>
    </template>

    <template #panel-actions>
      <span class="list-meta">
        <span class="status-dot online no-pulse"></span>
        <I18nT keypath="assets.group.stats.totalGroups" tag="span" scope="global">
          <template #n><strong class="num">{{ allData.length }}</strong></template>
        </I18nT>
      </span>
    </template>

    <el-table :data="pagedData" stripe v-loading="loading" class="is-compact" :row-class-name="rowClassName">
      <el-table-column type="selection" width="50" />
      <el-table-column prop="id" label="#" width="60">
        <template #default="{ row }">
          <span class="short-id">#{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.group.col.name')" min-width="160">
        <template #default="{ row }">
          <div class="group-name-cell">
            <span
              :class="['group-tag', 'is-clickable', groupTagClass(row.name)]"
              @click="goGroupHosts(row.name)"
              :title="row.nums ? $t('assets.group.viewGroupHosts', { name: row.name, n: row.nums }) : $t('assets.group.noHosts')"
            >
              {{ row.name }}
            </span>
            <span v-if="isCriticalGroup(row.name)" class="critical-badge">{{ $t('assets.group.critical') }}</span>
            <el-icon v-if="row.nums && +row.nums > 0" :size="12" class="group-go-hint"><ArrowRight /></el-icon>
          </div>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.group.col.hostCount')" width="140" align="center">
        <template #default="{ row }">
          <span
            :class="['count-badge', !row.nums || +row.nums === 0 ? 'is-zero' : 'is-clickable']"
            :title="row.nums ? $t('assets.group.viewHosts', { n: row.nums }) : $t('assets.group.noHosts')"
            @click="row.nums ? goGroupHosts(row.name) : null"
          >
            {{ row.nums || 0 }}
          </span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.group.col.remarks')" min-width="200">
        <template #default="{ row }">
          <span v-if="row.remarks" class="remark-text">{{ row.remarks }}</span>
          <span v-else class="remark-empty">—</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('assets.group.col.actions')" width="160" fixed="right" align="right">
        <template #default="scope">
          <span class="action-link" @click="openEdit(scope.row)">{{ $t('common.action.edit') }}</span>
          <span class="action-divider"></span>
          <span class="action-link is-danger" @click="doDelete(scope.row)">{{ $t('common.action.delete') }}</span>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty-state">
          <div class="empty-icon"><el-icon :size="24"><FolderOpened /></el-icon></div>
          <div class="empty-title">{{ keyword ? $t('assets.group.empty.matchTitle') : $t('assets.group.empty.title') }}</div>
          <div class="empty-desc">{{ keyword ? $t('assets.group.empty.matchHint') : $t('assets.group.empty.hint') }}</div>
        </div>
      </template>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? $t('assets.group.dialog.edit') : $t('assets.group.dialog.add')" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item v-if="isEdit" label="ID">
          <el-input v-model="form.id" disabled />
        </el-form-item>
        <el-form-item :label="$t('assets.group.form.name')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('assets.group.form.namePlaceholder')" />
        </el-form-item>
        <el-form-item v-if="isEdit" :label="$t('assets.group.form.nums')">
          <el-input v-model="form.nums" disabled />
        </el-form-item>
        <el-form-item :label="$t('assets.group.form.remarks')">
          <el-input v-model="form.remarks" type="textarea" :rows="2" :placeholder="$t('assets.group.form.remarksPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">{{ $t('common.action.cancel') }}</el-button>
        <el-button v-if="!isEdit" type="success" plain @click="submitForm(true)" :loading="submitting">{{ $t('assets.action.saveAndContinue') }}</el-button>
        <el-button type="primary" @click="submitForm(false)" :loading="submitting">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </DataTablePanel>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { I18nT } from 'vue-i18n'
import { Search, FolderOpened, ArrowRight } from '@element-plus/icons-vue'
import {
  getHostGroupList, addHostGroup, updateHostGroup, deleteHostGroup,
} from '@/api'
import { useListCrud } from '@/composables/useListCrud'
import { t } from '@/i18n'
// REV35-L5: 组名 5 色抽到 utils/groupClassifier
import { groupTagClass } from '@/utils/groupClassifier'
import DataTablePanel from '@/components/DataTablePanel.vue'

/** 资产组行 (后端动态结构) */
interface AssetGroupRow {
  id: number | string
  name: string
  nums?: number | string
  remarks?: string
  [k: string]: unknown
}

/** 资产组表单 */
interface AssetGroupForm {
  id: number | string
  name: string
  nums: number | string
  remarks: string
}

const router = useRouter()

const defaultForm = (): AssetGroupForm => ({ id: '', name: '', nums: '', remarks: '' })
// I18N: computed 惰性求值，语言切换后校验消息随之更新
const rules = computed(() => ({
  name: [{ required: true, message: t('assets.group.rules.name'), trigger: 'blur' }],
}))

const {
  allData, loading, keyword,
  dialogVisible, isEdit, submitting, formRef, form,
  currentPage, pageSize,
  pagedData, total,
  loadData, openAdd, openEdit,
  submitForm, doDelete,
} = useListCrud({
  api: {
    load: getHostGroupList as unknown as () => Promise<Record<string, unknown>>,
    dataKey: 'group_list_msg',
    create: addHostGroup as unknown as (payload: unknown) => Promise<unknown>,
    update: updateHostGroup as unknown as (payload: unknown) => Promise<unknown>,
    delete: deleteHostGroup as unknown as (payload: unknown) => Promise<unknown>,
    deletePayload: (row) => ({ name: (row as AssetGroupRow).name }),
  },
  searchFields: ['name', 'remarks'],
  keepOpenFields: ['name', 'remarks'],
  entityKey: 'common.entity.group',
  // 业务特有：删除前提示「该组下 X 台主机的归属关系也会被解除」
  deleteConfirmText: (row) =>
    t('assets.group.deleteConfirm', {
      name: (row as AssetGroupRow).name,
      n: (row as AssetGroupRow).nums || 0,
    }),
  onAfterLoad: (data) => (data as AssetGroupRow[]).sort((a, b) => (a.name || '').localeCompare(b.name || '')),
})

// ---------- 业务特有：关键组识别 ----------
// REV35-L5: groupTagClass 已抽到 utils/groupClassifier.js

function isCriticalGroup(name: string): boolean {
  if (!name) return false
  const g = name.toLowerCase()
  return /prod|生产|master|主库|admin|manage|超管|core|核心/.test(g) // i18n-ignore 协议值：匹配后端组名
}

function rowClassName({ row }: { row: AssetGroupRow }): string {
  return isCriticalGroup(row.name) ? 'is-critical-row' : ''
}

// 统计
const stats = computed(() => {
  const rows = allData.value as AssetGroupRow[]
  const configured = rows.filter(r => r.nums && +r.nums > 0).length
  const empty = rows.length - configured
  const totalHosts = rows.reduce((sum, r) => sum + (parseInt(String(r.nums)) || 0), 0)
  return { configured, empty, totalHosts }
})

function goGroupHosts(groupName: string): void {
  router.push({ path: '/host-list', query: { group: groupName } })
}

// BUGFIX: useListCrud 不会自动调用 loadData，组件必须显式调用
onMounted(loadData)
</script>

<style scoped>
.list-meta {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--ogs-text-secondary);
}
.list-meta strong { color: var(--ogs-text); font-family: var(--ogs-mono); }

.group-name-cell { display: inline-flex; align-items: center; gap: 6px; }
.group-go-hint {
  color: var(--ogs-text-muted); margin-left: 2px;
  transition: transform 0.15s, color 0.15s;
}
.group-tag.is-clickable,
.count-badge.is-clickable { cursor: pointer; }
.group-tag.is-clickable:hover { filter: brightness(0.92); }
.group-name-cell:has(.is-clickable):hover .group-go-hint {
  color: var(--ogs-primary); transform: translateX(2px);
}
.remark-text { font-size: 12.5px; color: var(--ogs-text-secondary); }
.remark-empty { color: var(--ogs-text-muted); font-style: italic; }

.action-link.is-danger { color: var(--ogs-critical); }
.action-link.is-danger:hover { color: var(--ogs-critical); opacity: 0.7; }
</style>
