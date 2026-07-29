<template>
  <div class="rs-shell">
    <!-- 顶部紧凑工具栏 -->
    <header class="rs-topbar">
      <div class="rs-brand">
        <img src="/juzi11.png" alt="logo" class="rs-logo" />
        <div class="rs-title">
          <span class="rs-name">{{ $t('ssh.session.title') }}</span>
          <span class="rs-sub">{{ store.user.alias || 'user' }} · Remote Session</span>
        </div>
      </div>

      <nav class="rs-tabs">
        <button
          v-for="tabItem in tabs"
          :key="tabItem.key"
          :class="['rs-tab', { active: activeTab === tabItem.key }]"
          @click="activeTab = tabItem.key"
        >
          <el-icon :size="14"><component :is="tabItem.icon" /></el-icon>
          <span>{{ tabItem.label }}</span>
        </button>
      </nav>

      <div class="rs-actions">
        <span class="rs-status">
          <span class="status-dot online no-pulse" style="width:6px;height:6px"></span>
          {{ $t('ssh.session.pool', { n: store.terminal.tabs.length }) }}
        </span>
        <el-tooltip :content="$t('ssh.session.backHome')" placement="bottom">
          <button class="rs-icon-btn" @click="goHome">
            <el-icon :size="14"><HomeFilled /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </header>

    <!-- 内容区 -->
    <main class="rs-body">
      <div v-show="activeTab === 'terminal'" class="rs-pane">
        <WebSSHCore />
      </div>
      <div v-show="activeTab === 'sftp'" class="rs-pane rs-pane-sftp">
        <FileTransfer :initial-host="initialHost" :initial-user="initialUser" />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Monitor, FolderOpened, HomeFilled } from '@element-plus/icons-vue'
import WebSSHCore from '@/components/WebSSHCore.vue'
import FileTransfer from '@/views/FileTransfer.vue'
import { store, createTab, _consumeOpenTerminal, loadUserInfo } from '@/store'
import { t } from '@/i18n'

/** RemoteSession 顶部 tab 类型 (URL 白名单同步) */
type RemoteTab = 'terminal' | 'sftp'

/** 单个 tab 元数据 */
interface TabMeta {
  key: RemoteTab
  label: string
  icon: Component
}

/** URL 解析结果 (空串 = 未通过白名单) */
interface RouteQuery {
  tab: string
  host: string
  user: string
}

const router = useRouter()
const activeTab = ref<RemoteTab>('terminal')

// 解析 URL 参数：?tab=sftp&host=xxx&user=yyy
// 独立 SFTP 窗口从资产树右键菜单触发：window.open('/remote-session?tab=sftp&host=...&user=...')
// REV35-L12: URL 参数白名单 + 长度限制 + 安全字符过滤，防通过 URL 传入可疑 payload
const _TAB_ALLOW: Set<string> = new Set<RemoteTab>(['sftp', 'terminal'])
const _HOST_RE: RegExp = /^[A-Za-z0-9._:@/-]+$/       // 主机名 / IP / user@host:port
const _USER_RE: RegExp = /^[A-Za-z0-9_-]{1,32}$/      // 远程用户
const _MAX_LEN: number = 128
const _safe = (raw: unknown, re: RegExp, max: number = _MAX_LEN): string => {
  if (typeof raw !== 'string') return ''
  const trimmed = raw.slice(0, max).trim()
  return re.test(trimmed) ? trimmed : ''
}
const routeQuery: RouteQuery = (() => {
  try {
    const search: string = window.location.search || ''
    const usp = new URLSearchParams(search)
    const tab = (usp.get('tab') || '').toLowerCase()
    return {
      tab: _TAB_ALLOW.has(tab) ? tab : '',
      host: _safe(usp.get('host'), _HOST_RE),
      user: _safe(usp.get('user'), _USER_RE, 32),
    }
  } catch {
    return { tab: '', host: '', user: '' }
  }
})()
let initialHost: string = routeQuery.host
let initialUser: string = routeQuery.user
if (routeQuery.tab === 'sftp' || routeQuery.tab === 'terminal') {
  activeTab.value = routeQuery.tab
}

const tabs = computed<TabMeta[]>(() => [
  { key: 'terminal', label: t('ssh.session.terminalTab'), icon: Monitor },
  { key: 'sftp', label: t('ssh.session.sftpTab'), icon: FolderOpened },
])

// REV34-M13: 优先从 localStorage 读取主窗口排队过来的 openTerminal 请求
//   原 setTimeout(800) + try/catch 静默吞错模式已删除
//   localStorage 与 URL params 并存：URL 优先（明确意图），localStorage 兜底
onMounted(async () => {
  await loadUserInfo() // BUGFIX: 加载用户别名，显示在顶栏
  if (!initialHost) {
    const pending = _consumeOpenTerminal()
    if (pending) {
      initialHost = (pending.host as string) || ''
      initialUser = (pending.user as string) || ''
    }
  }
  // 仅在 terminal 面板 且 拿到 host 时才创建 Tab
  if (activeTab.value === 'terminal' && initialHost) {
    try {
      createTab(initialHost, initialUser || 'root')
    } catch (e) {
      const err = e as Error
      ElMessage.error(t('ssh.session.createTabFail', { msg: err.message || t('ssh.session.unknownError') }))
    }
  }
})

function goHome(): void {
  try {
    window.close()
  } catch {
    // 静默：window.close 在非脚本打开的窗口里会拒绝，按设计回退到 router.push
  }
  setTimeout(() => {
    if (!window.closed) router.push('/dashboard')
  }, 100)
}
</script>

<style scoped>
.rs-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #18181B;
  color: rgba(255,255,255,0.85);
  font-family: var(--ogs-font-sans);
}

/* ===== 顶栏 ===== */
.rs-topbar {
  height: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 16px;
  background: rgba(22, 24, 29, 0.95);
  border-bottom: 1px solid rgba(255,255,255,0.08);
  backdrop-filter: blur(8px);
}
.rs-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.rs-logo {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: #fff;
  padding: 2px;
}
.rs-title { display: flex; flex-direction: column; line-height: 1.15; }
.rs-name { font-size: 14px; font-weight: 700; letter-spacing: 0.02em; }
.rs-sub {
  font-size: 10.5px; color: rgba(255,255,255,0.4);
  font-family: var(--ogs-mono); letter-spacing: 0.04em;
}

/* ===== Tabs ===== */
.rs-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  justify-content: center;
}
.rs-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: rgba(255,255,255,0.55);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.rs-tab:hover { color: rgba(255,255,255,0.85); background: rgba(255,255,255,0.04); }
.rs-tab.active {
  background: color-mix(in srgb, var(--ogs-primary) 12%, transparent);
  border-color: color-mix(in srgb, var(--ogs-primary) 35%, transparent);
  color: var(--ogs-primary-light);
  font-weight: 600;
}

/* ===== Actions ===== */
.rs-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.rs-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: rgba(255,255,255,0.5);
  font-family: var(--ogs-mono);
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
}
.rs-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.65);
  cursor: pointer;
  transition: all 0.15s;
}
.rs-icon-btn:hover { background: rgba(255,255,255,0.06); color: #fff; }

/* ===== Body ===== */
.rs-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--ogs-bg, #F4F6F9);
}
.rs-pane {
  flex: 1;
  min-height: 0;
  display: flex;
}
.rs-pane-sftp {
  background: var(--ogs-bg, #F4F6F9);
}

/* 内部：覆盖 WebSSHCore 默认容器，让它在独立窗口里更紧凑 */
.rs-pane :deep(.wssh-core) {
  height: 100%;
  border-radius: 0;
  border: none;
}

/* ===== FileTransfer 内部组件重写 ===== */
.rs-pane-sftp :deep(.page-container) {
  width: 100%;
  height: 100%;
  padding: 0;
  max-width: none;
}
.rs-pane-sftp :deep(.page-header) { display: none; }   /* 隐藏 FileTransfer 自带的标题（顶部工具栏已表达） */
.rs-pane-sftp :deep(.ops-split) {
  width: 100%;
  height: 100%;
  padding: 12px;
  box-sizing: border-box;
  gap: 12px;
}
.rs-pane-sftp :deep(.panel-sftp) { height: 100%; }
.rs-pane-sftp :deep(.el-overlay) { z-index: 2000 !important; }   /* 新建文件夹弹窗层级 */

/* ============================================================
   SFTP 面板深色化（官网终端风，与终端 tab 统一为 #16181D 系）
   仅在远程会话窗口生效；主界面文件传输页保持亮色
   ============================================================ */
.rs-pane-sftp { background: #16181D; }
.rs-pane-sftp :deep(.page-container) { background: transparent; }

/* —— 面板容器 —— */
.rs-pane-sftp :deep(.panel) {
  background: #131519;
  border: 1px solid rgba(255,255,255,0.07);
}
.rs-pane-sftp :deep(.panel-sftp) { background: #16181D; }
.rs-pane-sftp :deep(.panel-head) {
  border-bottom-color: rgba(255,255,255,0.07);
  flex-wrap: wrap;
  row-gap: 4px;
}
.rs-pane-sftp :deep(.panel-title) { color: rgba(255,255,255,0.85); white-space: nowrap; }
.rs-pane-sftp :deep(.panel-sub) { color: rgba(255,255,255,0.35); white-space: nowrap; }
.rs-pane-sftp :deep(.panel-icon) {
  color: var(--ogs-primary);
  background: color-mix(in srgb, var(--ogs-primary) 12%, transparent);
}
.rs-pane-sftp :deep(.panel-actions .el-tag) {
  background: rgba(255,255,255,0.07) !important;
  border-color: rgba(255,255,255,0.1) !important;
  color: rgba(255,255,255,0.6) !important;
}
.rs-pane-sftp :deep(.panel-actions .el-tag--success) {
  background: color-mix(in srgb, #40C057 14%, transparent) !important;
  border-color: color-mix(in srgb, #40C057 30%, transparent) !important;
  color: #51CF66 !important;
}

/* —— 输入框 / 选择器（同级 !important 对抗全局 EP 覆盖） —— */
.rs-pane-sftp :deep(.el-input__wrapper),
.rs-pane-sftp :deep(.el-select__wrapper) {
  background: rgba(255,255,255,0.05) !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1) inset !important;
}
.rs-pane-sftp :deep(.el-input__wrapper.is-focus),
.rs-pane-sftp :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px var(--ogs-primary) inset !important;
}
.rs-pane-sftp :deep(.el-input__inner) { color: rgba(255,255,255,0.85) !important; }
.rs-pane-sftp :deep(.el-input__inner::placeholder) { color: rgba(255,255,255,0.35) !important; }
.rs-pane-sftp :deep(.el-input__prefix),
.rs-pane-sftp :deep(.el-input__clear),
.rs-pane-sftp :deep(.el-select__suffix) { color: rgba(255,255,255,0.4) !important; }
.rs-pane-sftp :deep(.el-select__selected-item),
.rs-pane-sftp :deep(.el-select__placeholder) {
  color: rgba(255,255,255,0.85) !important;
  font-family: var(--ogs-mono); font-size: 12.5px;
}
.rs-pane-sftp :deep(.el-select__placeholder.is-transparent) { color: rgba(255,255,255,0.35) !important; }
.rs-pane-sftp :deep(.sys-user-row .config-label) { color: rgba(255,255,255,0.55); }

/* —— 资产树节点 —— */
.rs-pane-sftp :deep(.el-tree) { background: transparent; }
.rs-pane-sftp :deep(.el-tree-node__content:hover) { background: rgba(255,255,255,0.05) !important; }
.rs-pane-sftp :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: color-mix(in srgb, var(--ogs-primary) 16%, transparent) !important;
  color: #F2F3F5 !important;
}
.rs-pane-sftp :deep(.el-tree-node__expand-icon) { color: rgba(255,255,255,0.4); }
.rs-pane-sftp :deep(.el-tree-node__expand-icon.is-leaf) { color: transparent; }
.rs-pane-sftp :deep(.tree-node .node-label) { color: rgba(255,255,255,0.8); }
.rs-pane-sftp :deep(.tree-node .node-count .el-tag) {
  background: rgba(255,255,255,0.08) !important;
  border-color: transparent !important;
  color: rgba(255,255,255,0.55) !important;
}
.rs-pane-sftp :deep(.tree-node.is-group .group-icon) { color: #F5A97F; }
.rs-pane-sftp :deep(.tree-node.is-host) { background: rgba(255,255,255,0.045); }
.rs-pane-sftp :deep(.tree-node.is-host:hover) {
  background: color-mix(in srgb, var(--ogs-primary) 14%, transparent) !important;
}
.rs-pane-sftp :deep(.tree-node.is-host .host-icon) { color: var(--ogs-primary); }
.rs-pane-sftp :deep(.tree-node.is-host .node-label) {
  font-family: var(--ogs-mono); font-size: 12.5px; color: #CDD6F4;
}
.rs-pane-sftp :deep(.tree-node.is-connected) { box-shadow: inset 2px 0 0 var(--ogs-primary); }

/* —— 空态占位窗（与终端空态统一） —— */
.rs-pane-sftp :deep(.terminal-placeholder) {
  background: #16181D;
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 12px;
  box-shadow:
    0 24px 64px -16px rgba(0,0,0,0.55),
    0 0 64px -16px color-mix(in srgb, var(--ogs-primary) 22%, transparent);
}
.rs-pane-sftp :deep(.terminal-bar) {
  background: rgba(255,255,255,0.035) !important;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.rs-pane-sftp :deep(.terminal-bar .bar-title) { color: rgba(255,255,255,0.4); }
.rs-pane-sftp :deep(.terminal-body) {
  background: #16181D !important;
  color: rgba(255,255,255,0.55);
}
.rs-pane-sftp :deep(.terminal-body .step-num) {
  background: color-mix(in srgb, var(--ogs-primary) 15%, transparent);
  color: var(--ogs-primary-light);
  border: 1px solid color-mix(in srgb, var(--ogs-primary) 30%, transparent);
}

/* —— 按钮（默认幽灵深色；primary 保持实心橙） —— */
.rs-pane-sftp :deep(.el-button) {
  background: rgba(255,255,255,0.06) !important;
  border-color: rgba(255,255,255,0.14) !important;
  color: rgba(255,255,255,0.8) !important;
}
.rs-pane-sftp :deep(.el-button:hover) {
  background: rgba(255,255,255,0.1) !important;
  border-color: rgba(255,255,255,0.25) !important;
  color: #fff !important;
}
.rs-pane-sftp :deep(.el-button--primary) {
  background: var(--ogs-primary) !important;
  border-color: var(--ogs-primary) !important;
  color: #fff !important;
}
.rs-pane-sftp :deep(.el-button--primary:hover) {
  background: var(--ogs-primary-dark) !important;
  border-color: var(--ogs-primary-dark) !important;
}
.rs-pane-sftp :deep(.el-button--danger.is-plain) {
  background: color-mix(in srgb, #FF5F57 10%, transparent) !important;
  border-color: color-mix(in srgb, #FF5F57 35%, transparent) !important;
  color: #FF8787 !important;
}
.rs-pane-sftp :deep(.el-button.is-link),
.rs-pane-sftp :deep(.el-button--primary.is-link) {
  background: transparent !important;
  border-color: transparent !important;
  color: var(--ogs-primary-light) !important;
}

/* —— 路径栏 / 上传进度 —— */
.rs-pane-sftp :deep(.path-bar) {
  background: #16181D;
  border-bottom-color: rgba(255,255,255,0.07);
}
.rs-pane-sftp :deep(.upload-progress-bar) {
  background: color-mix(in srgb, var(--ogs-primary) 10%, transparent);
  border-bottom-color: color-mix(in srgb, var(--ogs-primary) 25%, transparent);
}
.rs-pane-sftp :deep(.upload-info) { color: var(--ogs-primary-light); }
.rs-pane-sftp :deep(.el-progress-bar__outer) { background: rgba(255,255,255,0.1) !important; }

/* —— 文件列表 el-table（变量与直接规则均需 !important 对抗全局） —— */
.rs-pane-sftp :deep(.el-table) {
  --el-table-bg-color: transparent !important;
  --el-table-tr-bg-color: transparent !important;
  --el-table-header-bg-color: #1A1D23 !important;
  --el-table-header-text-color: rgba(255,255,255,0.55) !important;
  --el-table-text-color: #D4D7DE !important;
  --el-table-row-hover-bg-color: rgba(255,255,255,0.045) !important;
  --el-table-border-color: rgba(255,255,255,0.07) !important;
  --el-fill-color-light: rgba(255,255,255,0.025) !important;
  background: transparent !important;
  color: #D4D7DE !important;
}
.rs-pane-sftp :deep(.el-table th.el-table__cell) {
  background: #1A1D23 !important;
  color: rgba(255,255,255,0.55) !important;
}
.rs-pane-sftp :deep(.el-table tr) { background: transparent !important; }
.rs-pane-sftp :deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(255,255,255,0.025) !important;
}
.rs-pane-sftp :deep(.el-table .el-table__cell) {
  border-bottom-color: rgba(255,255,255,0.06) !important;
}
.rs-pane-sftp :deep(.el-table__inner-wrapper::before),
.rs-pane-sftp :deep(.el-table__border-left-patch) { background: rgba(255,255,255,0.07); }
</style>

<!-- 右键菜单挂 body，scoped 无法触达；用 :has(.rs-shell) 限定仅远程会话窗口内深色，
     主界面文件传输页菜单保持亮色 -->
<style>
body:has(.rs-shell) .file-ctx-menu {
  background: #1A1D23;
  border-color: rgba(255,255,255,0.1);
  box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}
body:has(.rs-shell) .file-ctx-menu .ctx-item { color: rgba(255,255,255,0.8); }
body:has(.rs-shell) .file-ctx-menu .ctx-item:hover {
  background: rgba(255,255,255,0.06);
  color: var(--ogs-primary-light);
}
body:has(.rs-shell) .file-ctx-menu .ctx-item.ctx-danger { color: #FF8787; }
body:has(.rs-shell) .file-ctx-menu .ctx-item.ctx-danger:hover {
  background: rgba(255,95,87,0.12);
  color: #FF8787;
}
body:has(.rs-shell) .file-ctx-menu .ctx-divider { background: rgba(255,255,255,0.08); }
</style>