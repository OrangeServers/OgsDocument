// ============================================================
//  useListCrud · 通用列表 CRUD 状态机
//  ti3-TS: 加类型注解
//  ------------------------------------------------------------
//  给 5 个列表页共享：HostList / UserList / SysUserList /
//  GroupList / UserGroupList。
//
//  抽取：loading/selectedRows/keyword/dialogVisible/isEdit/
//  submitting/formRef/form/currentPage/pageSize 状态 +
//  filteredData/pagedData/total computed +
//  loadData/submitForm(keepOpen)/doDelete/batchDelete 行为
//  ------------------------------------------------------------
//  配置项：
//    api.load()                必填：加载全部数据
//    api.dataKey               必填：响应中数据字段名（如 host_list_msg）
//    api.create(form) / update(form) / delete(row)  按需
//    api.deletePayload(row)    可选：默认 (row) => row
//    api.formKey?              可选：批量删除提示中的"实体名"
//    searchFields              必填：前端模糊搜索匹配字段 ['name','alias']
//    keepOpenFields            可选：新增模式保存后清空的字段（'保存并继续'）
//    preLoad()                 可选：loadData 前钩子（如加载 group 列表）
//    onAfterLoad(data)         可选：loadData 后钩子（排序/转 map）
//    onBeforeSubmit(form, isEdit) 可选：返回最终提交 payload
//    onLoadError               可选：自定义错误提示，默认 '加载数据失败'
// ============================================================
import { ref, computed, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { t } from '@/i18n'

/** 通用列表行 (灵活 record) */
export type CrudRow = Record<string, unknown>

/** 通用表单值 */
export type CrudForm = Record<string, unknown>

/** 通用响应体 (带动态 data 字段) */
export interface CrudResponse {
  [k: string]: unknown
}

/** 自定义 hook: 提交前包装 payload */
export type BeforeSubmitFn = (form: CrudForm, isEdit: boolean) => CrudForm | unknown

/** 自定义 hook: 加载后处理数据 */
export type AfterLoadFn = (data: CrudRow[]) => CrudRow[]

/** useListCrud API 配置 */
export interface UseListCrudApi {
  load: () => Promise<CrudResponse>
  dataKey: string
  create?: (payload: CrudForm | unknown) => Promise<unknown>
  update?: (payload: CrudForm | unknown) => Promise<unknown>
  delete?: (payload: unknown) => Promise<unknown>
  deletePayload?: (row: CrudRow) => unknown
}

/** useListCrud 全部配置 */
export interface UseListCrudOpts {
  api: UseListCrudApi
  searchFields: string[]
  keepOpenFields?: string[]
  preLoad?: () => Promise<void> | void
  onAfterLoad?: AfterLoadFn
  onBeforeSubmit?: BeforeSubmitFn
  onLoadError?: string
  customLoad?: () => Promise<CrudResponse>
  deleteConfirmText?: (row: CrudRow) => string
  batchDeleteConfirmText?: (n: number) => string
  deleteSuccessText?: string
  /** @deprecated 改用 entityKey（i18n key），字符串项语言切换后不更新 */
  batchDeleteEntity?: string
  /** I18N: 实体名 i18n key（common.entity.*），确认框/批删提示惰性取当前语言 */
  entityKey?: string
}

/** useListCrud 返回值 */
export interface UseListCrudReturn {
  // 状态
  allData: Ref<CrudRow[]>
  loading: Ref<boolean>
  selectedRows: Ref<CrudRow[]>
  keyword: Ref<string>
  dialogVisible: Ref<boolean>
  isEdit: Ref<boolean>
  submitting: Ref<boolean>
  formRef: Ref<unknown>
  form: Ref<CrudForm>
  currentPage: Ref<number>
  pageSize: Ref<number>
  // 派生
  filteredData: ComputedRef<CrudRow[]>
  pagedData: ComputedRef<CrudRow[]>
  total: ComputedRef<number>
  // 行为
  onSearch: () => void
  onSelect: (selection: CrudRow[]) => void
  loadData: () => Promise<void>
  openAdd: (defaults?: CrudForm) => void
  openEdit: (row: CrudRow) => void
  submitForm: (keepOpen?: boolean) => Promise<void>
  doDelete: (row: CrudRow) => Promise<void>
  batchDelete: () => Promise<void>
  reset: () => void
}

// Vue 3 computed Ref type
import type { ComputedRef } from 'vue'

export function useListCrud(opts: UseListCrudOpts): UseListCrudReturn {
  // I18N: 默认文案全部惰性求值（调用时取当前语言）；调用方可传 entityKey
  //   （common.entity.* 的 key）定制实体名，或沿用旧的字符串型定制项。
  const entity = (): string => (
    opts.batchDeleteEntity ?? t(opts.entityKey || 'common.entity.record')
  )
  const {
    api,
    searchFields,
    keepOpenFields = [],
    preLoad,
    onAfterLoad,
    onBeforeSubmit,
    onLoadError,
    deleteConfirmText = (_row: CrudRow) => t('common.crud.deleteConfirm', { entity: entity() }),
    batchDeleteConfirmText = (n: number) => t('common.crud.deleteConfirmBatch', { n, entity: entity() }),
    deleteSuccessText,
  } = opts

  if (!api || !api.load) throw new Error('[useListCrud] api.load is required')
  if (!api.dataKey) throw new Error('[useListCrud] api.dataKey is required')
  if (!Array.isArray(searchFields) || !searchFields.length) {
    throw new Error('[useListCrud] searchFields is required (non-empty array)')
  }
  // customLoad 可选：如果提供，loadData 完全调用 customLoad()，
  // 让调用方根据内部状态（如 groupFilter）决定调用哪个 API
  const useCustomLoad = typeof opts.customLoad === 'function'

  const allData: Ref<CrudRow[]> = ref([])
  const loading: Ref<boolean> = ref(false)
  const selectedRows: Ref<CrudRow[]> = ref([])
  const keyword: Ref<string> = ref('')
  const dialogVisible: Ref<boolean> = ref(false)
  const isEdit: Ref<boolean> = ref(false)
  const submitting: Ref<boolean> = ref(false)
  const formRef: Ref<unknown> = ref()
  const form: Ref<CrudForm> = ref({})
  const currentPage: Ref<number> = ref(1)
  const pageSize: Ref<number> = ref(10)

  const filteredData: ComputedRef<CrudRow[]> = computed(() => {
    if (!keyword.value) return allData.value
    const kw = keyword.value.toLowerCase()
    return allData.value.filter((r) =>
      searchFields.some((f) => {
        const v = r?.[f]
        return typeof v === 'string' && v.toLowerCase().includes(kw)
      })
    )
  })
  const pagedData: ComputedRef<CrudRow[]> = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    return filteredData.value.slice(start, start + pageSize.value)
  })
  const total: ComputedRef<number> = computed(() => filteredData.value.length)

  function onSearch(): void { currentPage.value = 1 }
  function onSelect(selection: CrudRow[]): void { selectedRows.value = selection }

  async function loadData(): Promise<void> {
    loading.value = true
    try {
      if (preLoad) await preLoad()
      const res = useCustomLoad ? await opts.customLoad!() : await api.load()
      const data: CrudRow[] = (res?.[api.dataKey] as CrudRow[]) || []
      allData.value = onAfterLoad ? onAfterLoad(data) : data
    } catch {
      ElMessage.error(onLoadError || t('common.crud.loadFail'))
    } finally {
      loading.value = false
    }
  }

  function openAdd(defaults: CrudForm = {}): void {
    isEdit.value = false
    form.value = { ...defaults }
    dialogVisible.value = true
  }

  function openEdit(row: CrudRow): void {
    isEdit.value = true
    form.value = { ...row }
    dialogVisible.value = true
  }

  async function submitForm(keepOpen: boolean = false): Promise<void> {
    const refVal = formRef.value as { validate?: () => Promise<boolean> | void } | null | undefined
    if (refVal?.validate) await refVal.validate()
    submitting.value = true
    try {
      const payload = onBeforeSubmit
        ? onBeforeSubmit(form.value, isEdit.value)
        : form.value
      const apiFn = isEdit.value ? api.update : api.create
      if (!apiFn) throw new Error(t('common.crud.noApi'))
      await apiFn(payload)
      ElMessage.success(isEdit.value ? t('common.crud.updateSuccess') : t('common.crud.createSuccess'))
      if (keepOpen && !isEdit.value) {
        keepOpenFields.forEach((f) => { form.value[f] = '' })
      } else {
        dialogVisible.value = false
      }
      loadData()
    } catch {
      ElMessage.error(t('common.crud.operationFail'))
    } finally {
      submitting.value = false
    }
  }

  async function doDelete(row: CrudRow): Promise<void> {
    await ElMessageBox.confirm(deleteConfirmText(row), t('common.crud.prompt'), { type: 'warning' })
    try {
      const payload = api.deletePayload ? api.deletePayload(row) : row
      await api.delete!(payload)
      await loadData()
      ElMessage.success(deleteSuccessText ?? t('common.crud.deleteSuccess'))
    } catch {
      ElMessage.error(t('common.crud.deleteFail'))
    }
  }

  async function batchDelete(): Promise<void> {
    const n = selectedRows.value.length
    if (!n) return
    await ElMessageBox.confirm(batchDeleteConfirmText(n), t('common.crud.prompt'), { type: 'warning' })
    let success = 0
    let fail = 0
    for (const row of selectedRows.value) {
      try {
        const payload = api.deletePayload ? api.deletePayload(row) : row
        await api.delete!(payload)
        success++
      } catch {
        fail++
      }
    }
    loadData()
    if (fail === 0) {
      ElMessage.success(t('common.crud.batchDeleteSuccess', { n: success, entity: entity() }))
    } else {
      ElMessage.warning(t('common.crud.batchDeletePartial', { n: success, failed: fail }))
    }
  }

  function reset(): void {
    keyword.value = ''
    currentPage.value = 1
  }

  return {
    // 状态
    allData, loading, selectedRows, keyword,
    dialogVisible, isEdit, submitting, formRef, form,
    currentPage, pageSize,
    // 派生
    filteredData, pagedData, total,
    // 行为
    onSearch, onSelect, loadData, openAdd, openEdit,
    submitForm, doDelete, batchDelete, reset,
  }
}
