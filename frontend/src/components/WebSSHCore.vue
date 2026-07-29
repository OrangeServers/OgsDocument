<template>
  <div class="wssh-core">
    <!-- 资产树 -->
    <div class="wssh-tree-pane">
      <div class="tree-pane-head">
        <el-icon :size="14"><Grid /></el-icon>
        <span>{{ $t('ssh.tree.selectAsset') }}</span>
      </div>
      <div class="tree-pane-body">
        <div class="sys-user-row">
          <span class="config-label">{{ $t('ssh.tree.sysCred') }}</span>
          <el-select v-model="sysUser" :placeholder="$t('ssh.tree.selectUser')" size="small" style="flex:1" :disabled="!sysUsers.length">
            <el-option v-for="u in sysUsers" :key="u" :label="u" :value="u" />
          </el-select>
        </div>
        <el-input v-model="treeFilter" :placeholder="$t('ssh.tree.searchPlaceholder')" prefix-icon="Search" clearable size="small" class="tree-search" />
        <div class="tree-scroll">
          <el-tree
            ref="treeRef"
            :data="treeData"
            node-key="id"
            :default-expanded-keys="[1]"
            :filter-node-method="filterNode"
            :props="{ label:'title', children:'children' }"
            @node-click="onTreeNodeClick"
          >
            <template #default="{ node, data }">
              <div
                class="tree-node"
                :class="{ 'is-group': !node.isLeaf, 'is-host': node.isLeaf }"
                @contextmenu.prevent.stop="onTreeCtxMenu($event, data, node)"
              >
                <el-icon v-if="!node.isLeaf" class="node-icon group-icon" :size="14">
                  <FolderOpened v-if="node.expanded" /><Folder v-else />
                </el-icon>
                <el-icon v-else class="node-icon host-icon" :size="13"><Monitor /></el-icon>
                <span class="node-label">{{ data.title }}</span>
                <el-tag v-if="!node.isLeaf && data.children" size="small" type="info" class="node-count">{{ data.children.length }}</el-tag>
              </div>
            </template>
          </el-tree>
        </div>
      </div>
    </div>

    <!-- 终端区 -->
    <div class="wssh-term-pane">
      <div class="term-bar">
        <div class="term-bar-left">
          <span class="win-dots" aria-hidden="true"><i class="r" /><i class="y" /><i class="g" /></span>
          <span class="term-bar-title">{{ $t('ssh.term.title') }}</span>
          <span v-if="tabs.length" class="term-bar-count">{{ tabs.length }}</span>
          <span class="term-bar-active">{{ activeHostLabel }}</span>
        </div>
        <div class="term-bar-right">
          <el-tooltip :content="$t('ssh.term.duplicateTooltip')" placement="bottom">
            <el-button
              size="small"
              class="dup-btn"
              plain
              :disabled="!activeTabId"
              :icon="CopyDocument"
              @click="duplicateActive"
            >{{ $t('ssh.term.duplicate') }}</el-button>
          </el-tooltip>
          <el-tooltip :content="$t('ssh.term.closeOthersTooltip')" placement="bottom">
            <span class="term-bar-btn" @click="closeOthers"><el-icon :size="14"><CloseBold /></el-icon></span>
          </el-tooltip>
        </div>
      </div>

      <!-- REV33-M1: Tab 标签条 -->
      <div v-if="typedTabs.length" ref="tabStripRef" class="tab-strip" @wheel.prevent="onTabStripWheel">
        <div
          v-for="tab in typedTabs"
          :key="tab.id"
          :class="['tab-chip', { active: tab.id === activeTabId, error: tab.status === 'error' }]"
          @click="activeTabId = tab.id"
          @mousedown.middle.prevent="closeTab(tab.id)"
          @contextmenu.prevent.stop="onTabCtxMenu($event, tab)"
        >
          <span :class="['tab-dot', `is-${tab.status}`]"></span>
          <el-icon :size="12" class="tab-icon"><Monitor /></el-icon>
          <!-- UI优化：title 展示完整 host@user，截断时 hover 可辨识 -->
          <span class="tab-label" :title="`${tab.host?.name || tab.host}@${tab.sysUser?.name || tab.sysUser?.username || tab.sysUser}`">{{ tab.host?.name || tab.host }}</span>
          <span class="tab-user">@{{ tab.sysUser?.name || tab.sysUser?.username || tab.sysUser }}</span>
          <span class="tab-close" @click.stop="closeTab(tab.id)" :title="$t('ssh.term.closeTab')">
            <el-icon :size="12"><Close /></el-icon>
          </span>
        </div>
      </div>

      <div class="term-stage">
        <!-- 无 Tab 占位 -->
        <div v-if="!tabs.length" class="term-empty">
          <div class="term-empty-window">
            <div class="empty-bar"><span class="dot r"/><span class="dot y"/><span class="dot g"/><span class="empty-title">Orange Shell</span></div>
            <div class="empty-body">
              <div class="empty-step"><kbd>1</kbd><span>{{ $t('ssh.term.emptySteps.one') }}</span></div>
              <div class="empty-step"><kbd>2</kbd><span>{{ $t('ssh.term.emptySteps.two') }}</span></div>
              <div class="empty-step"><kbd>3</kbd><span>{{ $t('ssh.term.emptySteps.three') }}</span></div>
            </div>
          </div>
        </div>
        <!-- Tab 内容 -->
        <div v-else class="term-tabs">
          <div v-for="tab in typedTabs" :key="tab.id" v-show="tab.id === activeTabId" class="term-pane" :ref="(el: Element | ComponentPublicInstance | null) => setTermRef(tab.id, el as HTMLElement | null)"></div>
        </div>
      </div>
    </div>

    <!-- REV33-M1: 资产树右键菜单（使用 SshContextMenu 组件） -->
    <SshContextMenu
      :visible="treeCtx.visible"
      :x="treeCtx.x"
      :y="treeCtx.y"
      @close="closeTreeCtx"
    >
      <SshContextMenuItem icon="VideoPlay" @click="ctxAction('connect')">{{ $t('ssh.ctx.connect') }}</SshContextMenuItem>
      <SshContextMenuItem icon="FolderOpened" @click="ctxAction('sftp')">{{ $t('ssh.ctx.sftpOnly') }}</SshContextMenuItem>
      <SshContextDivider />
      <SshContextMenuItem icon="CopyDocument" @click="ctxAction('duplicate')">{{ $t('ssh.ctx.duplicateNew') }}</SshContextMenuItem>
      <SshContextMenuItem icon="DocumentCopy" @click="ctxAction('copy-name')">{{ $t('ssh.ctx.copyName') }}</SshContextMenuItem>
      <SshContextMenuItem icon="Promotion" @click="ctxAction('copy-ssh')">{{ $t('ssh.ctx.copySsh') }}</SshContextMenuItem>
      <SshContextDivider />
      <SshContextMenuItem icon="InfoFilled" @click="ctxAction('detail')">{{ $t('ssh.ctx.detail') }}</SshContextMenuItem>
    </SshContextMenu>

    <!-- REV33-M1: Tab 右键菜单 -->
    <SshContextMenu
      :visible="tabCtx.visible"
      :x="tabCtx.x"
      :y="tabCtx.y"
      @close="closeTabCtx"
    >
      <SshContextMenuItem icon="Aim" @click="tabCtxAction('activate')">{{ $t('ssh.ctx.activate') }}</SshContextMenuItem>
      <SshContextMenuItem icon="CopyDocument" @click="tabCtxAction('duplicate')">{{ $t('ssh.ctx.duplicate') }}</SshContextMenuItem>
      <SshContextDivider />
      <SshContextMenuItem icon="Close" @click="tabCtxAction('close')">{{ $t('ssh.ctx.close') }}</SshContextMenuItem>
      <SshContextMenuItem icon="CloseBold" @click="tabCtxAction('close-others')">{{ $t('ssh.ctx.closeOthers') }}</SshContextMenuItem>
      <SshContextMenuItem icon="Delete" danger @click="tabCtxAction('close-all')">{{ $t('ssh.ctx.closeAll') }}</SshContextMenuItem>
    </SshContextMenu>

    <!-- 资产详情弹窗 (REVIEW-14-P0-2: 独立 Vue 组件, 去除 dangerouslyUseHTMLString) -->
    <HostDetailDialog
      v-model="detailVisible"
      :host="detailHost"
      :sys-user="sysUser"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick, type Ref, type ComponentPublicInstance } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CopyDocument, DocumentCopy, Close, CloseBold, Delete,
  Folder, FolderOpened, Monitor, Grid, VideoPlay, Promotion, InfoFilled, Aim,
} from '@element-plus/icons-vue'
import { getTreeData, getSysUserNameList } from '@/api'
import { t } from '@/i18n'
import { store, createTab, removeTab, termPool } from '@/store'
import { safeDestroy, useWebSSH } from '@/composables/useWebSSH'
import { restoreSysUser, rememberSysUser } from '@/utils/sysUser'
import HostDetailDialog from '@/components/HostDetailDialog.vue'
import SshContextMenu from '@/components/ssh/SshContextMenu.vue'
import SshContextMenuItem from '@/components/ssh/SshContextMenuItem.vue'
import SshContextDivider from '@/components/ssh/SshContextDivider.vue'
import type { TerminalTab } from '@/types/terminal'

// ===== el-tree 节点最小结构 =====
interface TreeNode {
  id: number | string
  title: string
  children?: TreeNode[]
  [k: string]: unknown
}

// ===== el-tree 实例暴露 =====
interface ElTreeInstance {
  filter: (val: string) => void
}

// ===== 右键菜单动作类型 =====
type TreeCtxAction = 'connect' | 'sftp' | 'duplicate' | 'copy-name' | 'copy-ssh' | 'detail'
type TabCtxAction = 'activate' | 'duplicate' | 'close' | 'close-others' | 'close-all'

// ===== 资产树右键菜单状态 =====
interface TreeCtxState {
  visible: boolean
  x: number
  y: number
  data: TreeNode | null
}

// ===== Tab 右键菜单状态 =====
interface TabCtxState {
  visible: boolean
  x: number
  y: number
  tab: TerminalTab | null
}

// ===== REV33-M1: WebSSH 生命周期委托给 composable =====
const {
  setTermRef,
  closeTab,
  tabs,
  activeTabId,
} = useWebSSH()

// ===== 响应式 store 引用（保留：sysUser / sysUsers / treeData） =====
const sysUsers = computed({
  get: () => store.terminal.sysUsers,
  set: v => { store.terminal.sysUsers = v },
})
const sysUser = computed({
  get: () => store.terminal.sysUser,
  set: v => { store.terminal.sysUser = v },
})
const treeData = computed({
  get: () => store.terminal.treeCache,
  set: v => { store.terminal.treeCache = v },
})

const activeHostLabel = computed(() => {
  const tab = (tabs.value as unknown as TerminalTab[]).find(x => x.id === activeTabId.value)
  return tab ? `${tab.host?.name || tab.host} @ ${tab.sysUser?.name || tab.sysUser?.username || tab.sysUser}` : ''
})

/** 给模板 v-for 用的类型化 tabs (TerminalTab[]) */
const typedTabs = computed<TerminalTab[]>(() => tabs.value as unknown as TerminalTab[])

// ===== 资产树相关 =====
const treeRef = ref<ElTreeInstance | null>(null)
const treeFilter = ref('')
const tabStripRef: Ref<HTMLElement | null> = ref(null)

// 鼠标滚轮在 tab-strip 上滚动 → 转为横向滚动
function onTabStripWheel(e: WheelEvent): void {
  const el = tabStripRef.value
  if (!el) return
  const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
  if (delta !== 0) el.scrollLeft += delta
}

function filterNode(val: string, data: TreeNode): boolean {
  if (!val) return true
  return (data.title || '').toLowerCase().includes(val.toLowerCase())
}
watch(treeFilter, val => { treeRef.value?.filter(val) })

// ===== 数据加载 =====
async function loadInitial(): Promise<void> {
  try {
    const [tRes, sRes] = await Promise.all([getTreeData(), getSysUserNameList()]) as unknown as [
      { host?: TreeNode[] },
      { code: number; msg?: string[] },
    ]
    if (tRes.host) {
      const tree = tRes.host
      for (const g of tree) if (g.children) g.children.sort((a, b) => a.title.localeCompare(b.title))
      tree.sort((a, b) => a.title.localeCompare(b.title))
      treeData.value = tree
      store.terminal.treeLoaded = true
    }
    if (sRes.code === 0) {
      sysUsers.value = (sRes.msg || []).sort()
      // 恢复上次选中的凭据（localStorage 记忆），fallback 到列表第一个
      if (sysUsers.value.length && !sysUser.value) {
        sysUser.value = restoreSysUser(sysUsers.value)
      }
    }
  } catch (_) { /* 静默 */ }
}

// 选择即记忆：下拉切换、右键连接、复制连接等所有路径统一由 watch 覆盖
watch(sysUser, (v) => { if (v) rememberSysUser(v) })

// ===== Tab / 资产树操作 =====
function onTreeNodeClick(data: TreeNode, node: { isLeaf: boolean }): void {
  if (!node.isLeaf) return
  if (!sysUser.value) { ElMessage.warning(t('ssh.msg.selectCredFirst')); return }
  createTab(data.title, sysUser.value)
}

function duplicateActive(): string | undefined {
  const tab = (tabs.value as unknown as TerminalTab[]).find(x => x.id === activeTabId.value)
  if (!tab) { ElMessage.warning(t('ssh.msg.noActiveSession')); return undefined }
  // 复制哪个会话的凭据就记哪个（可能与当前下拉值不同）
  if (tab.sysUser) rememberSysUser(tab.sysUser.name || tab.sysUser.username || '')
  const id = createTab(tab.host, tab.sysUser)
  ElMessage.success(t('ssh.msg.duplicated', {
    target: `${tab.host?.name || tab.host} @ ${tab.sysUser?.name || tab.sysUser?.username || tab.sysUser}`,
  }))
  return id
}
function closeOthers(): void {
  const keepId = activeTabId.value
  if (!keepId) return
  const toClose = (tabs.value as unknown as TerminalTab[]).filter(item => item.id !== keepId).map(item => item.id)
  toClose.forEach(id => safeDestroy(id))
  toClose.forEach(id => removeTab(id))
  ElMessage.success(t('ssh.msg.closedOthers'))
}

// ===== 资产树右键菜单 =====
const treeCtx = ref<TreeCtxState>({ visible: false, x: 0, y: 0, data: null })
const detailVisible = ref(false)
const detailHost = ref<TreeNode | null>(null)
function onTreeCtxMenu(e: MouseEvent, data: TreeNode, node: { isLeaf: boolean }): void {
  if (!node.isLeaf) return
  if (!sysUser.value) { ElMessage.warning(t('ssh.msg.selectUserFirst')); return }
  let x = e.clientX, y = e.clientY
  if (x + 220 > window.innerWidth) x = window.innerWidth - 220
  if (y + 280 > window.innerHeight) y = window.innerHeight - 280
  treeCtx.value = { visible: true, x, y, data }
}
function closeTreeCtx(): void { treeCtx.value.visible = false }
function ctxAction(action: TreeCtxAction): void {
  const d = treeCtx.value.data
  if (!d) return
  if (action === 'connect') {
    createTab(d.title, sysUser.value)
  } else if (action === 'sftp') {
    const host = d.title
    const user = sysUser.value
    const params = new URLSearchParams({ tab: 'sftp', host, user })
    const url = `${window.location.origin}/remote-session?${params.toString()}`
    const win = window.open(url, '_blank')
    if (!win) {
      ElMessage.warning(t('ssh.msg.popupBlocked'))
    } else {
      ElMessage.success(t('ssh.msg.sftpOpened', { target: `${host} @ ${user}` }))
    }
  } else if (action === 'duplicate') {
    createTab(d.title, sysUser.value)
    ElMessage.success(t('ssh.msg.duplicated', { target: `${d.title} @ ${sysUser.value}` }))
  } else if (action === 'copy-name') {
    copyToClipboard(d.title, t('ssh.msg.copiedHost', { name: d.title }))
  } else if (action === 'copy-ssh') {
    const cmd = `ssh ${sysUser.value}@${d.title}`
    copyToClipboard(cmd, t('ssh.msg.copiedSsh', { cmd }))
  } else if (action === 'detail') {
    detailHost.value = { ...d }
    detailVisible.value = true
  }
  closeTreeCtx()
}

function copyToClipboard(text: string, msg: string): void {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => ElMessage.success(msg)).catch(() => fallbackCopy(text, msg))
  } else {
    fallbackCopy(text, msg)
  }
}
function fallbackCopy(text: string, msg: string): void {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'; ta.style.left = '-9999px'
  document.body.appendChild(ta)
  ta.select()
  try { document.execCommand('copy'); ElMessage.success(msg) } catch (_) { ElMessage.error(t('ssh.msg.copyFail')) }
  document.body.removeChild(ta)
}

// ===== Tab 右键菜单 =====
const tabCtx = ref<TabCtxState>({ visible: false, x: 0, y: 0, tab: null })
function onTabCtxMenu(e: MouseEvent, tab: TerminalTab): void {
  let x = e.clientX, y = e.clientY
  if (x + 200 > window.innerWidth) x = window.innerWidth - 200
  if (y + 200 > window.innerHeight) y = window.innerHeight - 200
  tabCtx.value = { visible: true, x, y, tab }
}
function closeTabCtx(): void { tabCtx.value.visible = false }
function tabCtxAction(action: TabCtxAction): void {
  const tab = tabCtx.value.tab
  if (!tab) return
  if (action === 'activate') activeTabId.value = tab.id
  else if (action === 'duplicate') {
    if (tab.sysUser) rememberSysUser(tab.sysUser.name || tab.sysUser.username || '')
    createTab(tab.host, tab.sysUser)
    ElMessage.success(t('ssh.msg.duplicated', {
      target: `${tab.host?.name || tab.host} @ ${tab.sysUser?.name || tab.sysUser?.username || tab.sysUser}`,
    }))
  }
  else if (action === 'close') closeTab(tab.id)
  else if (action === 'close-others') {
    activeTabId.value = tab.id
    closeOthers()
  } else if (action === 'close-all') {
    const ids = (tabs.value as unknown as TerminalTab[]).map(x => x.id)
    ids.forEach(id => safeDestroy(id))
    ids.forEach(id => removeTab(id))
    ElMessage.success(t('ssh.msg.closedAll'))
  }
  closeTabCtx()
}

// ===== 生命周期 =====
onMounted(() => {
  loadInitial()
  nextTick(() => {
    for (const t of tabs.value as unknown as TerminalTab[]) {
      if (!(termPool.instances as unknown as Map<string, unknown>).has(t.id)) {
        const container = document.querySelector(`.term-tabs .term-pane:nth-child(${(tabs.value as unknown as TerminalTab[]).indexOf(t) + 1})`) as HTMLElement | null
        if (container) setTermRef(t.id, container)
      }
    }
  })
})

// REV33-M1: onBeforeUnmount 清理已由 useWebSSH 接管（遍历 tabs 调用 safeDestroy）
</script>

<style scoped>
.wssh-core {
  display: flex;
  background: var(--ogs-terminal-bg, #18181B);
  border-radius: var(--ogs-radius-md);
  overflow: hidden;
  height: 100%;
  width: 100%;
}

/* ===== 资产树（官网终端风：#131519 纯黑系，与终端区 #16181D 分层） ===== */
.wssh-tree-pane {
  width: 240px;
  flex-shrink: 0;
  background: #131519;
  border-right: 1px solid rgba(255,255,255,0.07);
  display: flex;
  flex-direction: column;
}
.tree-pane-head {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.85);
  border-bottom: 1px solid rgba(255,255,255,0.07);
}
.tree-pane-head .el-icon { color: var(--ogs-primary); }
.tree-pane-body { padding: 12px; flex: 1; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.sys-user-row {
  display: flex; align-items: center; gap: 8px;
  padding-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.07);
}
.sys-user-row .config-label { color: rgba(255,255,255,0.55); font-size: 12px; white-space: nowrap; }

/* el-select / el-input 深色化（全局 index.css 的 EP 覆盖全带 !important，此处必须同级对抗） */
.wssh-tree-pane :deep(.el-select__wrapper) {
  background: rgba(255,255,255,0.05) !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1) inset !important;
  border-radius: 6px !important;
  min-height: 30px;
}
.wssh-tree-pane :deep(.el-select__wrapper:hover) { box-shadow: 0 0 0 1px rgba(255,255,255,0.25) inset !important; }
.wssh-tree-pane :deep(.el-select__wrapper.is-focused) { box-shadow: 0 0 0 1px var(--ogs-primary) inset !important; }
.wssh-tree-pane :deep(.el-select__selected-item),
.wssh-tree-pane :deep(.el-select__placeholder) {
  color: rgba(255,255,255,0.85) !important;
  font-family: var(--ogs-mono); font-size: 12.5px;
}
.wssh-tree-pane :deep(.el-select__placeholder.is-transparent) { color: rgba(255,255,255,0.35) !important; }
.wssh-tree-pane :deep(.el-select__suffix) { color: rgba(255,255,255,0.4) !important; }
.wssh-tree-pane :deep(.el-input__wrapper) {
  background: rgba(255,255,255,0.05) !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1) inset !important;
  border-radius: 6px !important;
}
.wssh-tree-pane :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px var(--ogs-primary) inset !important; }
.wssh-tree-pane :deep(.el-input__inner) { color: rgba(255,255,255,0.85) !important; font-size: 12.5px; }
.wssh-tree-pane :deep(.el-input__inner::placeholder) { color: rgba(255,255,255,0.35) !important; }
.wssh-tree-pane :deep(.el-input__prefix) { color: rgba(255,255,255,0.4) !important; }
.wssh-tree-pane :deep(.el-input__clear) { color: rgba(255,255,255,0.4) !important; }

.tree-scroll { overflow-y: auto; flex: 1; min-height: 0; }
.tree-scroll :deep(.el-tree) { background: transparent; }
.tree-scroll :deep(.el-tree-node__content) { height: 32px; border-radius: 6px; padding-right: 8px; }
/* 全局 index.css 对 el-tree hover / is-current 有 !important 浅色覆盖，此处需同级对抗 */
.tree-scroll :deep(.el-tree-node__content:hover) { background: rgba(255,255,255,0.05) !important; cursor: pointer; }
.tree-scroll :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: color-mix(in srgb, var(--ogs-primary) 16%, transparent) !important;
  color: #F2F3F5 !important;
}
.tree-scroll :deep(.el-tree-node__expand-icon) { color: rgba(255,255,255,0.4); }
.tree-scroll :deep(.el-tree-node__expand-icon.is-leaf) { color: transparent; }
.tree-node { display: flex; align-items: center; gap: 6px; flex: 1; overflow: hidden; }
.tree-node .node-icon { flex-shrink: 0; }
.tree-node .node-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; color: rgba(255,255,255,0.8); }
.tree-node .node-count { margin-left: auto; transform: scale(0.85); transform-origin: right center; }
.tree-node .node-count :deep(.el-tag),
.tree-node :deep(.el-tag) {
  background: rgba(255,255,255,0.08); border-color: transparent; color: rgba(255,255,255,0.55);
}
.tree-node.is-group .group-icon { color: #F5A97F; }
.tree-node.is-group .node-label { font-weight: 600; }
.tree-node.is-host {
  padding: 2px 8px; border-radius: 6px;
  background: rgba(255,255,255,0.045); cursor: pointer; position: relative;
  transition: background 0.15s;
}
.tree-node.is-host:hover { background: color-mix(in srgb, var(--ogs-primary) 14%, transparent) !important; }
.tree-node.is-host .host-icon { color: var(--ogs-primary); }
.tree-node.is-host .node-label { font-family: var(--ogs-mono); font-size: 12.5px; color: #CDD6F4; }

/* ===== 终端区（官网终端风 #16181D） ===== */
.wssh-term-pane { flex: 1; min-width: 0; display: flex; flex-direction: column; background: #16181D; }
.term-bar {
  height: 42px; padding: 0 14px;
  display: flex; align-items: center; justify-content: space-between;
  background: #1A1D23; border-bottom: 1px solid rgba(255,255,255,0.07); flex-shrink: 0;
}
.term-bar-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.win-dots { display: inline-flex; gap: 6px; margin-right: 2px; }
.win-dots i { width: 10px; height: 10px; border-radius: 50%; }
.win-dots .r { background: #FF5F57; }
.win-dots .y { background: #FEBC2E; }
.win-dots .g { background: #28C840; }
.term-bar-title { font-size: 12.5px; font-weight: 600; color: rgba(255,255,255,0.85); letter-spacing: 0.02em; font-family: var(--ogs-mono); }
.term-bar-count {
  font-size: 11px; padding: 1px 6px; border-radius: 999px;
  background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.6);
  font-family: var(--ogs-mono);
}
.term-bar-sep { color: rgba(255,255,255,0.3); margin: 0 2px; }
.term-bar-active {
  font-size: 12px; color: rgba(255,255,255,0.6); font-family: var(--ogs-mono);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.term-bar-right { display: flex; align-items: center; gap: 6px; }
/* 终端区永远暗底，按钮不依赖全局主题，直接强制暗色适配 */
.term-bar-right :deep(.el-button) {
  background: rgba(255,255,255,0.08) !important;
  border-color: rgba(255,255,255,0.2) !important;
  color: rgba(255,255,255,0.85) !important;
}
.term-bar-right :deep(.el-button:hover) {
  background: rgba(255,255,255,0.14) !important;
  border-color: rgba(255,255,255,0.35) !important;
  color: #fff !important;
}
.term-bar-right :deep(.el-button.is-disabled),
.term-bar-right :deep(.el-button.is-disabled:hover) {
  background: rgba(255,255,255,0.05) !important;
  border-color: rgba(255,255,255,0.12) !important;
  color: rgba(255,255,255,0.45) !important;
}
/* 复制连接：官网审批按钮风——品牌橙实心 + 发光 */
.term-bar-right :deep(.el-button.dup-btn) {
  background: var(--ogs-primary) !important;
  border-color: var(--ogs-primary) !important;
  color: #fff !important;
  box-shadow: 0 2px 10px color-mix(in srgb, var(--ogs-primary) 45%, transparent);
}
.term-bar-right :deep(.el-button.dup-btn:hover) {
  background: var(--ogs-primary-dark) !important;
  border-color: var(--ogs-primary-dark) !important;
  color: #fff !important;
}
.term-bar-right :deep(.el-button.dup-btn.is-disabled),
.term-bar-right :deep(.el-button.dup-btn.is-disabled:hover) {
  background: color-mix(in srgb, var(--ogs-primary) 14%, transparent) !important;
  border-color: color-mix(in srgb, var(--ogs-primary) 22%, transparent) !important;
  color: color-mix(in srgb, var(--ogs-primary) 60%, transparent) !important;
  box-shadow: none;
}
.term-bar-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 5px;
  color: rgba(255,255,255,0.5); cursor: pointer; transition: all 0.15s;
}
.term-bar-btn:hover { background: rgba(255,255,255,0.06); color: #F8F8F2; }
.term-bar-btn[disabled] { opacity: 0.4; cursor: not-allowed; }

/* ===== Tab 标签条 ===== */
.tab-strip {
  height: 34px;
  display: flex; align-items: stretch;
  background: #101216;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  overflow-x: auto; overflow-y: hidden;
  flex-shrink: 0;
  scroll-behavior: smooth;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.22) rgba(255,255,255,0.04);
}
.tab-strip::-webkit-scrollbar { height: 8px; }
.tab-strip::-webkit-scrollbar-track { background: rgba(255,255,255,0.03); }
.tab-strip::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.18);
  border-radius: 4px;
  border: 2px solid transparent;
  background-clip: padding-box;
  transition: background 0.15s;
}
.tab-strip::-webkit-scrollbar-thumb:hover {
  background: rgba(255,255,255,0.32);
  background-clip: padding-box;
  border: 2px solid transparent;
}
.tab-strip::-webkit-scrollbar-button { display: none; }

.tab-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 0 8px; min-width: 100px; max-width: 220px; /* UI优化：放宽截断，提升多会话辨识度 */
  background: transparent; color: rgba(255,255,255,0.55);
  font-size: 12px; cursor: pointer;
  border-right: 1px solid rgba(255,255,255,0.05);
  transition: background 0.15s, color 0.15s;
  position: relative;
  user-select: none;
  flex-shrink: 0;
}
.tab-chip:hover { background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.85); }
.tab-chip.active {
  background: #16181D; color: #F2F3F5;
}
.tab-chip.active::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
  background: var(--ogs-primary); border-radius: 1px 1px 0 0;
}
.tab-chip.error .tab-dot { background: #FF5F57 !important; }

.tab-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: rgba(255,255,255,0.3);
}
.tab-dot.is-connecting { background: #FAB005; animation: pulse 1.2s infinite; }
.tab-dot.is-connected { background: #40C057; }
.tab-dot.is-error { background: #FF5F57; }
.tab-dot.is-closed { background: #6C7086; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.tab-icon { color: rgba(255,255,255,0.4); flex-shrink: 0; }
.tab-label {
  font-family: var(--ogs-mono); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0;
}
.tab-user {
  font-size: 10.5px; color: rgba(255,255,255,0.4); font-family: var(--ogs-mono);
  flex-shrink: 0;
}
.tab-close {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; border-radius: 3px;
  color: rgba(255,255,255,0.4); cursor: pointer; flex-shrink: 0;
  transition: all 0.15s;
}
.tab-close:hover { background: rgba(255, 95, 87, 0.2); color: #FF5F57; }

/* ===== Stage ===== */
.term-stage { flex: 1; min-height: 0; position: relative; overflow: hidden; }
.term-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 20px; }
.term-empty-window {
  width: 100%; max-width: 400px; border-radius: 12px; overflow: hidden;
  border: 1px solid rgba(255,255,255,0.09);
  box-shadow:
    0 24px 64px -16px rgba(0,0,0,0.55),
    0 0 64px -16px color-mix(in srgb, var(--ogs-primary) 22%, transparent);
}
.empty-bar { background: rgba(255,255,255,0.035); border-bottom: 1px solid rgba(255,255,255,0.06); padding: 9px 12px; display: flex; align-items: center; gap: 7px; }
.empty-bar .dot { width: 10px; height: 10px; border-radius: 50%; }
.empty-bar .dot.r { background: #FF5F57; } .empty-bar .dot.y { background: #FEBC2E; } .empty-bar .dot.g { background: #28C840; }
.empty-title { flex: 1; text-align: center; color: rgba(255,255,255,0.4); font-size: 11px; font-family: var(--ogs-mono); }
.empty-body { background: #16181D; color: rgba(255,255,255,0.55); padding: 18px 20px; font-family: var(--ogs-mono); font-size: 13px; line-height: 1.9; }
.empty-step { display: flex; align-items: center; gap: 8px; }
.empty-step kbd {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 22px; height: 20px; padding: 0 5px; border-radius: 4px;
  background: color-mix(in srgb, var(--ogs-primary) 15%, transparent);
  color: var(--ogs-primary-light);
  font-family: var(--ogs-mono); font-size: 11px;
  border: 1px solid color-mix(in srgb, var(--ogs-primary) 30%, transparent);
}

/* ===== Tab panes ===== */
.term-tabs { position: absolute; inset: 0; }
.term-pane { position: absolute; inset: 0; padding: 4px 0 0 4px; background: #16181D; }
.term-pane :deep(.xterm) { height: 100%; padding: 4px; }
.term-pane :deep(.xterm-viewport) { overflow-y: auto !important; }
</style>