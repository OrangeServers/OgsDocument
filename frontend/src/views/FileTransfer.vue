<template>
  <OpsLayout
    eyebrow="TRANSFER · SFTP"
    :title="$t('fileTransfer.title')"
    :desc="[
      { t: 'text', v: $t('fileTransfer.desc') },
      { t: 'bold', v: currentHost || '—' },
    ]"
  >
    <template #side>
      <AssetTreePanel
        mode="single"
        :tree-data="treeData"
        :connected-host="currentHost"
        :checked="sysUser"
        @pick="onNodeClick"
      >
        <template #before-tree>
          <div class="sys-user-row">
            <span class="config-label">{{ $t('fileTransfer.sysUser') }}</span>
            <el-select v-model="sysUser" :placeholder="$t('fileTransfer.selectUser')" size="small" style="flex:1" :disabled="!sysUsers.length">
              <el-option v-for="u in sysUsers" :key="u" :label="u" :value="u" />
            </el-select>
          </div>
        </template>
      </AssetTreePanel>
    </template>

    <template #main>
      <div class="panel panel-sftp">
        <!-- 未连接时占位 -->
        <div v-if="!connected" class="sftp-empty">
          <div class="terminal-placeholder">
            <div class="terminal-bar"><span class="dot r"/><span class="dot y"/><span class="dot g"/><span class="bar-title">SFTP</span></div>
            <div class="terminal-body">
              <div class="step"><span class="step-num">1</span> {{ $t('fileTransfer.steps.one') }}</div>
              <div class="step"><span class="step-num">2</span> {{ $t('fileTransfer.steps.two') }}</div>
              <div class="step"><span class="step-num">3</span> {{ $t('fileTransfer.steps.three') }}</div>
            </div>
          </div>
        </div>

        <!-- 已连接：文件浏览器 -->
        <template v-else>
          <div class="panel-head" style="flex-shrink:0">
            <span class="panel-icon"><el-icon :size="14"><FolderOpened /></el-icon></span>
            <span class="panel-title">{{ currentHost }}</span>
            <span class="panel-sub">Remote FS</span>
            <span class="panel-actions">
              <el-button size="small" @click="doRefresh"><el-icon><Refresh /></el-icon>{{ $t('common.action.refresh') }}</el-button>
              <el-button size="small" @click="showNewDir = true"><el-icon><FolderAdd /></el-icon>{{ $t('fileTransfer.newFolder') }}</el-button>
              <el-button size="small" type="primary" @click="triggerUpload"><el-icon><Upload /></el-icon>{{ $t('fileTransfer.uploadFile') }}</el-button>
              <input ref="uploadInput" type="file" multiple style="display:none" @change="onFileSelect" />
              <el-button size="small" type="danger" plain @click="doDisconnect"><el-icon><Close /></el-icon>{{ $t('fileTransfer.disconnect') }}</el-button>
            </span>
          </div>
          <!-- 路径栏 -->
          <div class="path-bar">
            <el-button size="small" @click="goRoot"><el-icon><HomeFilled /></el-icon></el-button>
            <el-button size="small" @click="goBack"><el-icon><ArrowLeft /></el-icon></el-button>
            <div class="path-input-wrap">
              <el-input v-model="currentPath" size="small" @keyup.enter="navigateTo(currentPath)">
                <template #prefix><el-icon><Folder /></el-icon></template>
              </el-input>
            </div>
            <el-button size="small" @click="navigateTo(currentPath)"><el-icon><Right /></el-icon></el-button>
          </div>
          <!-- 上传进度 -->
          <div v-if="uploading" class="upload-progress-bar">
            <el-progress :percentage="uploadPercent" :format="() => `${uploadPercent}%`" :stroke-width="6" style="flex:1" />
            <span class="upload-info">{{ $t('fileTransfer.uploadingLabel', { name: uploadFileName }) }}</span>
          </div>
          <!-- 文件列表 -->
          <div class="file-list-area">
            <el-table :data="fileList" stripe v-loading="loading" size="small" @row-dblclick="onRowDblClick" @row-contextmenu="onRowContextMenu">
              <el-table-column prop="name" :label="$t('fileTransfer.columns.name')" min-width="300">
                <template #default="{ row }">
                  <div style="display:flex;align-items:center;gap:8px;cursor:pointer">
                    <el-icon :size="16" :color="row.isDir ? '#E6A23C' : '#909399'">
                      <FolderOpened v-if="row.isDir" /><Document v-else />
                    </el-icon>
                    <span>{{ row.name }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="$t('fileTransfer.columns.size')" width="120">
                <template #default="{ row }">{{ row.isDir ? '-' : formatSize(row.size) }}</template>
              </el-table-column>
              <el-table-column :label="$t('fileTransfer.columns.mtime')" width="180">
                <template #default="{ row }">{{ formatTime(row.mtime) }}</template>
              </el-table-column>
              <el-table-column :label="$t('fileTransfer.columns.ops')" width="80" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" type="primary" link @click.stop="showContextMenu($event, row)"><el-icon><More /></el-icon></el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </div>
    </template>
  </OpsLayout>

  <!-- 新建文件夹弹窗 -->
  <el-dialog v-model="showNewDir" :title="$t('fileTransfer.newFolder')" width="400px">
    <el-input v-model="newDirName" :placeholder="$t('fileTransfer.newFolderPlaceholder')" />
    <template #footer>
      <el-button @click="showNewDir=false">{{ $t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="doCreateDir">{{ $t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <!-- 右键菜单 -->
  <div v-if="ctxMenuVisible" class="file-ctx-menu" :style="ctxMenuStyle" @click.stop>
    <div class="ctx-item" @click="ctxOpen"><el-icon :size="14"><FolderOpened /></el-icon>{{ $t('fileTransfer.ctx.open') }}</div>
    <div class="ctx-item" @click="ctxDownload" v-if="ctxRow && !ctxRow.isDir"><el-icon :size="14"><Download /></el-icon>{{ $t('fileTransfer.ctx.download') }}</div>
    <div class="ctx-item" @click="ctxUploadHere"><el-icon :size="14"><Upload /></el-icon>{{ $t('fileTransfer.ctx.uploadHere') }}</div>
    <div class="ctx-divider" />
    <div class="ctx-item" @click="ctxNewDir"><el-icon :size="14"><FolderAdd /></el-icon>{{ $t('fileTransfer.newFolder') }}</div>
    <div class="ctx-item" @click="ctxRename"><el-icon :size="14"><EditPen /></el-icon>{{ $t('fileTransfer.ctx.rename') }}</div>
    <div class="ctx-divider" />
    <div class="ctx-item ctx-danger" @click="ctxDelete"><el-icon :size="14"><Delete /></el-icon>{{ $t('common.action.delete') }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, Refresh, FolderAdd, Upload, Close, HomeFilled, ArrowLeft, Right, Folder, Document, Download, EditPen, Delete, More } from '@element-plus/icons-vue'
import OpsLayout from '@/components/OpsLayout.vue'
import AssetTreePanel from '@/components/AssetTreePanel.vue'
import { getTreeData, getSysUserNameList } from '@/api'
import { currentLocale, t } from '@/i18n'
import { resolveWsUrl } from '@/utils/ws'
import { restoreSysUser, rememberSysUser } from '@/utils/sysUser'

// ===== 文件/目录项 (SFTP ls 返回结构) =====
interface FileEntry {
  name: string
  path: string
  isDir: boolean
  size?: number
  mtime?: number
  [k: string]: unknown
}

// ===== 资产树节点 (与 AssetTreePanel.TreeNode 对齐, id 后端有返回) =====
interface TreeNode {
  id: number | string
  title: string
  children?: TreeNode[]
  [k: string]: unknown
}

// ===== 资产树响应 =====
interface TreeResp {
  host?: TreeNode[]
  [k: string]: unknown
}

// ===== 系统用户列表响应 =====
interface SysUserResp {
  code: number
  msg?: string[]
  [k: string]: unknown
}

// ===== WebSocket JSON 消息 (按 action 区分) =====
interface WsBaseMsg {
  action: string
  status?: string
  message?: string
  [k: string]: unknown
}

interface WsAuthMsg extends WsBaseMsg {
  action: 'auth'
  hostname?: string
}

interface WsLsMsg extends WsBaseMsg {
  action: 'ls'
  path?: string
  entries?: FileEntry[]
}

interface WsDownloadStartMsg extends WsBaseMsg {
  action: 'download_start'
  path: string
  filename: string
  size: number
}

interface WsDownloadEndMsg extends WsBaseMsg {
  action: 'download_end'
  path: string
}

interface WsUploadProgressMsg extends WsBaseMsg {
  action: 'upload_progress'
  transferred: number
  total: number
}

interface DownloadInfo {
  filename: string
  size: number
}

type WsMsg = WsBaseMsg | WsAuthMsg | WsLsMsg | WsDownloadStartMsg | WsDownloadEndMsg | WsUploadProgressMsg

// ===== 下载缓冲 (path -> chunks / info) =====
type DownloadBuffers = Record<string, ArrayBuffer[]>
type PendingDownloads = Record<string, DownloadInfo>

// ===== ctx menu 位置样式 =====
interface CtxMenuStyle {
  left: string
  top: string
}

// ===== 入口参数（从独立窗口 /remote-session?tab=sftp&host=xxx&user=yyy 透传） =====
interface Props {
  initialHost?: string
  initialUser?: string
}
const props = withDefaults(defineProps<Props>(), {
  initialHost: '',
  initialUser: '',
})

// ===== 资产树数据 =====
const treeData = ref<TreeNode[]>([])
const sysUsers = ref<string[]>([])
const sysUser = ref<string>('')

onMounted(async () => {
  try {
    const [tRes, sRes] = await Promise.all([
      getTreeData() as unknown as Promise<TreeResp>,
      getSysUserNameList() as unknown as Promise<SysUserResp>,
    ])
    if (tRes.host) {
      const tree = tRes.host
      for (const group of tree) {
        if (group.children) group.children.sort((a, b) => a.title.localeCompare(b.title))
      }
      tree.sort((a, b) => a.title.localeCompare(b.title))
      treeData.value = tree
    }
    if (sRes.code === 0) {
      sysUsers.value = (sRes.msg || []).sort((a, b) => a.localeCompare(b))
      // 恢复上次选中的凭据（localStorage 记忆），fallback 到列表第一个
      if (sysUsers.value.length) sysUser.value = restoreSysUser(sysUsers.value)
    }
  } catch {
    // 静默：资产树 / 用户列表加载失败仅留空
  }

  // 独立窗口入口参数：自动连接目标主机
  if (props.initialHost) {
    if (props.initialUser) sysUser.value = props.initialUser
    await nextTick()
    ElMessage.info(t('fileTransfer.msg.connecting', { target: `${props.initialHost}@${sysUser.value}` }))
    connectSftp(props.initialHost)
  }
})

// 选择即记忆：下拉切换、自动连接等所有路径统一由 watch 覆盖
watch(sysUser, (v) => { if (v) rememberSysUser(v) })

// ===== SFTP 连接 =====
const connected = ref<boolean>(false)
const currentHost = ref<string>('')
const currentPath = ref<string>('/')
const fileList = ref<FileEntry[]>([])
const loading = ref<boolean>(false)
const showNewDir = ref<boolean>(false)
const newDirName = ref<string>('')
const uploading = ref<boolean>(false)
const uploadPercent = ref<number>(0)
const uploadFileName = ref<string>('')
const uploadInput = ref<HTMLInputElement | null>(null)
let ws: WebSocket | null = null
let downloadBuffers: DownloadBuffers = {}
let pendingDownloads: PendingDownloads = {}
// REV31-H1: 跟踪当前活动下载的 path，用于把 binary chunk 写入正确的 buffer
//   原始 bug：循环内 return 导致只有第一个 key 能收到数据
//   修复：维护 activeDownloadPath，binary 数据直接 push 到对应 buffer
let activeDownloadPath = ''

function getSftpWsUrl(): string {
  // REV31-H2: SFTP WS URL 必须走 resolveWsUrl 校验（ws/wss 协议 + host 匹配 VITE_API_TARGET）
  //   与 WebSSHCore 保持一致的安全策略
  const envWs = import.meta.env.VITE_WS_URL as string | undefined
  // 如果配置了 VITE_WS_URL，按 replace 规则生成 sftp 端点
  const candidate = envWs
    ? envWs.replace(/\/local\/websocket$/, '/local/sftp/websocket')
    : ''
  // resolveWsUrl 校验失败时回退到相对路径，但 sftp 路径需手动拼接
  if (candidate) {
    return resolveWsUrl({ envWsUrl: candidate })
  }
  // 无 VITE_WS_URL：直接拼 sftp 相对路径（同源）
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${window.location.host}/local/sftp/websocket`
}

function onNodeClick(host: string): void {
  if (!sysUser.value) {
    ElMessage.warning(t('fileTransfer.msg.selectUserFirst'))
    return
  }
  connectSftp(host)
}

function connectSftp(host: string): void {
  if (ws) { ws.close(); ws = null }

  const url = getSftpWsUrl()
  ws = new WebSocket(url)
  ws.binaryType = 'arraybuffer'

  ws.onopen = (): void => {
    if (ws) {
      ws.send(JSON.stringify({ hostname: host, username: sysUser.value }))
    }
  }

  ws.onmessage = (evt: MessageEvent): void => {
    if (typeof evt.data === 'string') {
      try {
        handleJsonMessage(JSON.parse(evt.data) as WsMsg)
      } catch {
        ElMessage.error(t('fileTransfer.msg.parseFail'))
      }
    } else {
      handleBinaryData(evt.data as ArrayBuffer)
    }
  }

  ws.onerror = (): void => {
    ElMessage.error(t('fileTransfer.msg.connectFail'))
    connected.value = false
  }

  ws.onclose = (): void => {
    connected.value = false
    ws = null
  }
}

function handleJsonMessage(msg: WsMsg): void {
  const action = msg.action

  if (action === 'auth') {
    const m = msg as WsAuthMsg
    if (m.status === 'ok') {
      connected.value = true
      currentHost.value = m.hostname || ''
      sendAction('ls', { path: '/' })
    } else {
      ElMessage.error(m.message || t('fileTransfer.msg.authFail'))
      connected.value = false
    }
    return
  }

  if (action === 'ls') {
    const m = msg as WsLsMsg
    if (m.status === 'ok') {
      currentPath.value = m.path || '/'
      fileList.value = m.entries || []
    } else {
      ElMessage.error(m.message || t('fileTransfer.msg.listFail'))
    }
    loading.value = false
    return
  }

  if (action === 'download_start') {
    const m = msg as WsDownloadStartMsg
    downloadBuffers[m.path] = []
    pendingDownloads[m.path] = { filename: m.filename, size: m.size }
    // REV31-H1: 标记当前活动下载 path，binary chunk 路由到正确 buffer
    activeDownloadPath = m.path
    return
  }

  if (action === 'download_end') {
    const m = msg as WsDownloadEndMsg
    const path = m.path
    const info = pendingDownloads[path]
    const chunks = downloadBuffers[path]
    if (info && chunks) {
      const blob = new Blob(chunks)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = info.filename; a.click()
      URL.revokeObjectURL(url)
    }
    delete downloadBuffers[path]
    delete pendingDownloads[path]
    // REV31-H1: 清空活动下载标记
    if (activeDownloadPath === path) activeDownloadPath = ''
    return
  }

  if (action === 'upload_start') {
    if (msg.status !== 'ok') {
      uploading.value = false
      ElMessage.error(msg.message || t('fileTransfer.msg.uploadFail'))
    }
    return
  }

  if (action === 'upload_progress') {
    const m = msg as WsUploadProgressMsg
    if (m.total > 0) uploadPercent.value = Math.round(m.transferred / m.total * 100)
    return
  }

  if (action === 'upload_end') {
    uploading.value = false
    uploadPercent.value = 0
    if (msg.status === 'ok') {
      ElMessage.success(t('fileTransfer.msg.uploadOk'))
      doRefresh()
    } else {
      ElMessage.error(msg.message || t('fileTransfer.msg.uploadFail'))
    }
    return
  }

  if (action === 'mkdir') {
    if (msg.status === 'ok') {
      ElMessage.success(t('fileTransfer.msg.mkdirOk'))
      showNewDir.value = false
      newDirName.value = ''
      doRefresh()
    } else {
      ElMessage.error(msg.message || t('fileTransfer.msg.mkdirFail'))
    }
    return
  }

  if (action === 'rm') {
    if (msg.status === 'ok') {
      ElMessage.success(t('fileTransfer.msg.rmOk'))
      doRefresh()
    } else {
      ElMessage.error(msg.message || t('fileTransfer.msg.rmFail'))
    }
    return
  }

  if (action === 'rename') {
    if (msg.status === 'ok') {
      ElMessage.success(t('fileTransfer.msg.renameOk'))
      doRefresh()
    } else {
      ElMessage.error(msg.message || t('fileTransfer.msg.renameFail'))
    }
    return
  }

  if (msg.status === 'error') {
    ElMessage.error(msg.message || t('fileTransfer.msg.opFail'))
    loading.value = false
  }
}

// REV31-H1: 修复循环 return bug
//   原始代码:  for (path of keys) { push(data); return }  // 第一次迭代就退出
//   根本原因：binary frame 没有 path metadata，需前端维护 activeDownloadPath
//   修复：把 binary chunk 直接 push 到 activeDownloadPath 对应的 buffer
//   边界：无 active download 或 buffer 已被清空时丢弃（避免脏数据）
function handleBinaryData(data: ArrayBuffer): void {
  if (activeDownloadPath && downloadBuffers[activeDownloadPath]) {
    downloadBuffers[activeDownloadPath].push(data)
  }
  // 兜底：兜底遍历（兼容未来多文件并发），但每个 buffer 只命中一次
  // 注：SFTP 协议本身串行下载（按 sendAction('download') 单条消息触发），
  //     所以单 activeDownloadPath 已足够覆盖当前架构
}

function sendAction(action: string, params: Record<string, unknown> = {}): void {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action, ...params }))
  }
}

// ===== 文件操作 =====
function navigateTo(path: string): void {
  loading.value = true
  sendAction('ls', { path })
}

function onRowDblClick(row: FileEntry): void {
  if (row.isDir) {
    navigateTo(row.path)
  }
}

function goRoot(): void { navigateTo('/') }

function goBack(): void {
  if (currentPath.value === '/') return
  const parts = currentPath.value.replace(/\/$/, '').split('/')
  parts.pop()
  navigateTo(parts.length <= 1 ? '/' : parts.join('/'))
}

function doRefresh(): void {
  loading.value = true
  sendAction('ls', { path: currentPath.value })
}

function doDownload(row: FileEntry): void {
  if (row.isDir) {
    ElMessage.warning(t('fileTransfer.msg.dirDownloadUnsupported'))
    return
  }
  sendAction('download', { path: row.path })
  ElMessage.info(t('fileTransfer.msg.downloadStart', { name: row.name }))
}

function triggerUpload(): void {
  uploadInput.value?.click()
}

async function onFileSelect(e: Event): Promise<void> {
  const target = e.target as HTMLInputElement
  const files = target.files
  if (!files || !files.length) return

  for (const file of Array.from(files)) {
    await uploadOneFile(file)
  }
  target.value = ''
}

function uploadOneFile(file: File): Promise<void> {
  return new Promise<void>((resolve) => {
    uploading.value = true
    uploadPercent.value = 0
    uploadFileName.value = file.name

    const remotePath = currentPath.value === '/' ? '/' + file.name : currentPath.value + '/' + file.name

    sendAction('upload_start', {
      path: currentPath.value,
      filename: file.name,
      size: file.size,
      remote_path: remotePath,
    })

    const chunkSize = 65536
    let offset = 0

    const readNext = (): void => {
      if (offset >= file.size) {
        sendAction('upload_end', { path: remotePath })
        resolve()
        return
      }
      const slice = file.slice(offset, offset + chunkSize)
      const reader = new FileReader()
      reader.onload = (evt: ProgressEvent<FileReader>): void => {
        if (ws && ws.readyState === WebSocket.OPEN && evt.target?.result instanceof ArrayBuffer) {
          ws.send(evt.target.result)
          offset += evt.target.result.byteLength
        }
        setTimeout(readNext, 0)
      }
      reader.readAsArrayBuffer(slice)
    }

    setTimeout(readNext, 50)
  })
}

async function doCreateDir(): Promise<void> {
  if (!newDirName.value) return
  const path = currentPath.value === '/' ? '/' + newDirName.value : currentPath.value + '/' + newDirName.value
  sendAction('mkdir', { path })
}

async function doDelete(row: FileEntry): Promise<void> {
  try {
    await ElMessageBox.confirm(t('fileTransfer.msg.deleteConfirm', { name: row.name }), t('common.crud.prompt'), { type: 'warning' })
  } catch {
    return
  }
  sendAction('rm', { path: row.path, isDir: row.isDir })
}

async function doRename(row: FileEntry): Promise<void> {
  let value: string
  try {
    const result = await ElMessageBox.prompt(t('fileTransfer.msg.renamePrompt'), t('fileTransfer.ctx.rename'), {
      inputValue: row.name,
      confirmButtonText: t('common.action.save'),
      cancelButtonText: t('common.action.cancel'),
    })
    value = result.value
  } catch {
    return
  }
  if (!value || value === row.name) return
  const newPath = currentPath.value === '/' ? '/' + value : currentPath.value + '/' + value
  sendAction('rename', { old_path: row.path, new_path: newPath })
}

function doDisconnect(): void {
  if (ws) { ws.close(); ws = null }
  connected.value = false
  fileList.value = []
  currentPath.value = '/'
}

// ===== 工具函数 =====
function formatSize(bytes: number | null | undefined): string {
  if (bytes == null) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}

function formatTime(ts: number | null | undefined): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString(currentLocale())
}

// ===== 右键菜单 =====
const ctxMenuVisible = ref<boolean>(false)
const ctxMenuStyle = ref<CtxMenuStyle>({ left: '0px', top: '0px' })
const ctxRow = ref<FileEntry | null>(null)

function onRowContextMenu(row: FileEntry, _column: unknown, event: MouseEvent): void {
  event.preventDefault()
  ctxRow.value = row
  let x = event.clientX, y = event.clientY
  if (x + 200 > window.innerWidth) x = window.innerWidth - 200
  if (y + 240 > window.innerHeight) y = window.innerHeight - 240
  ctxMenuStyle.value = { left: x + 'px', top: y + 'px' }
  ctxMenuVisible.value = true
}

function showContextMenu(e: MouseEvent, row: FileEntry): void {
  ctxRow.value = row
  const target = e.target as HTMLElement
  const rect = target.getBoundingClientRect()
  ctxMenuStyle.value = { left: rect.left + 'px', top: (rect.bottom + 4) + 'px' }
  ctxMenuVisible.value = true
}

function closeCtx(): void { ctxMenuVisible.value = false }

function ctxOpen(): void {
  if (!ctxRow.value) { closeCtx(); return }
  if (ctxRow.value.isDir) navigateTo(ctxRow.value.path)
  else doDownload(ctxRow.value)
  closeCtx()
}

function ctxDownload(): void {
  if (ctxRow.value) doDownload(ctxRow.value)
  closeCtx()
}

function ctxUploadHere(): void {
  if (ctxRow.value?.isDir) {
    navigateTo(ctxRow.value.path)
    nextTick(() => triggerUpload())
  } else {
    triggerUpload()
  }
  closeCtx()
}

function ctxNewDir(): void {
  if (ctxRow.value?.isDir) {
    navigateTo(ctxRow.value.path)
    nextTick(() => { showNewDir.value = true })
  } else {
    showNewDir.value = true
  }
  closeCtx()
}

function ctxRename(): void {
  if (ctxRow.value) doRename(ctxRow.value)
  closeCtx()
}

function ctxDelete(): void {
  if (ctxRow.value) doDelete(ctxRow.value)
  closeCtx()
}

function onDocClick(_e: MouseEvent): void {
  if (ctxMenuVisible.value) ctxMenuVisible.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  if (ws) { ws.close(); ws = null }
})
</script>

<style scoped>
/* 仅本页特有：系统用户行 + SFTP 浏览器 + 路径栏 + 上传进度 */
.sys-user-row { display: flex; align-items: center; gap: 8px; padding: 4px 2px 0; }
.sys-user-row .config-label { font-size: 12px; color: var(--ogs-text-secondary); white-space: nowrap; }

.panel-sftp { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.sftp-empty { flex: 1; display: flex; align-items: center; justify-content: center; padding: 24px; }

.path-bar { display: flex; align-items: center; gap: 8px; padding: 8px 16px; border-bottom: 1px solid var(--ogs-border-subtle); background: var(--ogs-bg); flex-shrink: 0; }
.path-input-wrap { flex: 1; }

.upload-progress-bar { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: var(--ogs-primary-soft); border-bottom: 1px solid var(--ogs-primary-ring); }
.upload-info { font-size: 12px; color: var(--ogs-primary-dark); white-space: nowrap; font-family: var(--ogs-mono); }

.file-list-area { flex: 1; min-height: 0; overflow-y: auto; }
</style>

<!-- 右键菜单挂在 body 上，scoped 不生效，需全局样式 -->
<style>
.file-ctx-menu {
  position: fixed; z-index: 9999;
  background: var(--ogs-surface, #fff); border: 1px solid var(--ogs-border, #dcdfe6); border-radius: 8px;
  padding: 4px 0; min-width: 180px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}
.file-ctx-menu .ctx-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 16px; font-size: 13px; color: var(--ogs-text, #303133);
  cursor: pointer; transition: all 0.15s;
}
.file-ctx-menu .ctx-item:hover { background: var(--ogs-bg-sunken, #f0f4f8); color: var(--ogs-primary, #E6A23C); }
.file-ctx-menu .ctx-item.ctx-danger { color: var(--ogs-danger, #F56C6C); }
.file-ctx-menu .ctx-item.ctx-danger:hover { background: rgba(239, 68, 68, 0.08); color: var(--ogs-danger, #F56C6C); }
.file-ctx-menu .ctx-divider { height: 1px; background: var(--ogs-border-subtle, #ebeef5); margin: 4px 0; }
</style>
