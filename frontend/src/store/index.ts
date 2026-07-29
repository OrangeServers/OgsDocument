// =============================================================================
// OrangeServer Frontend 全局 store (reactive 模式, ti3-TS 加类型)
// =============================================================================
import { reactive, type Reactive } from 'vue'
import { getUserAlias, getUserAuth, getSettings } from '@/api'
import type { CurrentUser, TerminalTab, TerminalSysUser, AppSettings, ThemeKey, UserRole } from '@/types'

// 终端实例类型 (来自 xterm, 不在 types/ 中以避免引入 @types/xterm)
type TerminalInstance = unknown
type FitAddonInstance = unknown

// reactive store 形状
interface StoreShape {
  user: CurrentUser
  theme: {
    headerBg: string
    sidebarBg: string
    current: ThemeKey | string
  }
  settings: AppSettings
  sidebarCollapsed: boolean
  loading: boolean
  terminal: {
    tabs: TerminalTab[]
    activeTabId: string
    /** 系统用户名列表 (后端 getSysUserNameList 返回 string[]) */
    sysUsers: string[]
    /** 当前选中的系统用户名 (string, 与 sysUsers 元素类型一致) */
    sysUser: string
    treeCache: unknown[]
    treeLoaded: boolean
  }
}

// 非响应式的终端实例池
interface TermPoolShape {
  instances: Map<string, TerminalInstance>
  fitAddons: Map<string, FitAddonInstance>
  wsMap: Map<string, WebSocket>
  resizeObservers: Map<string, ResizeObserver>
  tabSeq: number
}

export const store: Reactive<StoreShape> = reactive({
  // 用户信息
  user: {
    username: '',
    alias: '',
    role: '',
    avatar: '',
  },
  // 主题配色
  theme: {
    headerBg: 'rgba(255, 255, 255, 0.78)',
    sidebarBg: 'linear-gradient(180deg, #1E3A8A 0%, #1E40AF 50%, #2563EB 100%)',
    current: 'blue',
  },
  // 设置
  settings: {
    login_time: 30,
    register_status: 'on',
    color_matching: 'orange',
    login_fail_limit: 5,
    lock_duration: 30,
    password_expire_days: 90,
    mfa_enabled: 'off',
    password_complexity: 'off',
    ssh_timeout: 30,
    terminal_scrollback: 10000,
    session_record: 'on',
    max_concurrent_sessions: 3,
    log_retention_days: 180,
    command_audit: 'on',
    upload_size_limit: 500,
    allow_upload: 'on',
    allow_download: 'on',
    mail_notify: 'off',
    alert_email: '',
    system_name: 'OrangeServer',
    login_notice: '',
    language: 'zh-CN',
  },
  // 侧边栏折叠
  sidebarCollapsed: false,
  // 加载状态
  loading: false,
  // ========== Terminal (WebSSH) ==========
  // Tab 元数据（响应式）。实例引用单独挂在 termPool，避免 xterm 内部 mutation 触发渲染
  terminal: {
    tabs: [],            // [{ id, host, sysUser, status, createdAt }]
    activeTabId: '',
    // 系统用户（全局共享）
    sysUsers: [],
    sysUser: '',
    // 资产树缓存（独立窗口复用）
    treeCache: [],
    treeLoaded: false,
  },
})

// ========== Terminal 实例池（非响应式） ==========
// xterm 内部 mutation 频繁，放在 reactive 中会触发大量无意义渲染
// REV34-M13: 跨窗口 openTerminal 请求（取代 setTimeout 800ms 魔法数字）
//   主窗口调 _queueOpenTerminal 后 window.open('/remote-session')
//   子窗口 RemoteSession.vue onMounted 读 _consumeOpenTerminal() 拿到 host/user
//   同一套 localStorage 机制保证主/子同源跨窗口可读
const _PENDING_TERMINAL_KEY: string = 'ogs:pending-terminal'
interface PendingTerminal {
  host: unknown
  user: unknown
  ts: number
}
function _queueOpenTerminal(host: unknown, user: unknown): void {
  try {
    const payload: PendingTerminal = { host, user, ts: Date.now() }
    localStorage.setItem(_PENDING_TERMINAL_KEY, JSON.stringify(payload))
  } catch (e) {
    /* localStorage 满 / 隐私模式 — fallback 由 setTimeout 兜底 */
  }
}
function _consumeOpenTerminal(): { host: unknown; user: unknown } | null {
  try {
    const raw = localStorage.getItem(_PENDING_TERMINAL_KEY)
    if (!raw) return null
    localStorage.removeItem(_PENDING_TERMINAL_KEY)
    const obj = JSON.parse(raw) as PendingTerminal
    // 30s 以内的请求才接受，防 stale 数据误伤
    if (Date.now() - (obj.ts || 0) > 30000) return null
    return { host: obj.host, user: obj.user }
  } catch (e) {
    return null
  }
}

export { _queueOpenTerminal, _consumeOpenTerminal }

export const termPool: TermPoolShape = {
  instances: new Map(),    // id -> Terminal
  fitAddons: new Map(),   // id -> FitAddon
  wsMap: new Map(),       // id -> WebSocket
  resizeObservers: new Map(), // id -> ResizeObserver
  tabSeq: 0,
}

// ========== Terminal 业务方法 ==========

// 新建 Tab（仅元数据）
// sysUser 接受 string (用户名) 或 TerminalSysUser (完整对象); string 会自动包装为最小 TerminalSysUser
export function createTab(host: unknown, sysUser?: string | TerminalSysUser): string {
  const id: string = `tab_${++termPool.tabSeq}`
  const hostObj = host as TerminalTab['host']
  const sysUserObj: TerminalSysUser = (typeof sysUser === 'string' || !sysUser)
    ? (sysUser as string
      ? { id: 0, name: sysUser as string, username: sysUser as string, auth_type: 'password' }
      : (store.terminal.sysUser as unknown as TerminalSysUser))
    : sysUser
  const tab: TerminalTab = {
    id,
    host: hostObj,
    sysUser: sysUserObj,
    status: 'connecting',
    createdAt: new Date().toISOString(),
    title: hostObj?.name
      ? `${hostObj.name}@${sysUserObj.name || sysUserObj.username || ''}`
      : (sysUserObj.name || sysUserObj.username || id),
  }
  store.terminal.tabs.push(tab)
  store.terminal.activeTabId = id
  if (sysUser) store.terminal.sysUser = (typeof sysUser === 'string' ? sysUser : sysUser.username)
  return id
}

// 关闭 Tab（仅元数据；实例由组件负责销毁）
export function removeTab(id: string): void {
  const idx: number = store.terminal.tabs.findIndex(t => t.id === id)
  if (idx === -1) return
  store.terminal.tabs.splice(idx, 1)
  if (store.terminal.activeTabId === id) {
    if (store.terminal.tabs.length) {
      const next = store.terminal.tabs[Math.max(0, idx - 1)]
      store.terminal.activeTabId = next.id
    } else {
      store.terminal.activeTabId = ''
    }
  }
}

// 更新 Tab 状态
export function updateTabStatus(id: string, status: TerminalTab['status']): void {
  const tab: TerminalTab | undefined = store.terminal.tabs.find(t => t.id === id)
  if (tab) tab.status = status
}

// 加载用户信息
export async function loadUserInfo(): Promise<void> {
  try {
    const res: ApiResponseAlias = await getUserAlias() as unknown as ApiResponseAlias
    if (res.alias !== undefined) {
      store.user.alias = res.alias
      store.user.username = res.username ?? ''
      store.user.avatar = `/local/image/test_get/${res.username ?? 'default'}`
    }
  } catch (e) {
    /* ignore */
  }
}

// 加载用户权限
// P0-8: 失败时显式返 null，与“未初始化（空串）”区分。
// 返 null 代表“后端拿不到”（网络 / 401 / 500），应由路由守卫按未知处理
// 返 '' 代表“未加载”，仅出现在首屏未调用过 loadUserRole 时
export async function loadUserRole(): Promise<UserRole | string | null> {
  try {
    const res = await getUserAuth() as unknown as {
      code: number
      data?: { usrole?: string }
      usrole?: string
    }
    // BUGFIX: 后端返回 {code:0, data:{usrole:'admin'}, msg:'ok'}
    //   axios 拦截器返回 res.data (AxiosResponse.data) = 完整 JSON
    //   旧代码取 res.usrole (顶层), 但实际角色在 res.data.usrole (嵌套)
    const role: string | undefined = res.data?.usrole ?? res.usrole
    if (res.code === 0 && role) {
      store.user.role = role
    }
    return store.user.role || null
  } catch (e) {
    return null
  }
}

// 加载系统设置
export async function loadSettings(): Promise<void> {
  try {
    const res: Record<string, unknown> = await getSettings() as unknown as Record<string, unknown>
    if (res.color_matching !== undefined) {
      // 同步所有设置到 store
      const keys: string[] = Object.keys(store.settings)
      for (const key of keys) {
        const v = res[key]
        if (v !== undefined && v !== null) {
          (store.settings as Record<string, unknown>)[key] = v
        }
      }
      applyTheme(res.color_matching as string)
      // I18N: 服务端语言为权威，覆盖 localStorage/浏览器语言的首屏猜测
      if (typeof res.language === 'string' && res.language) {
        const { setLocale } = await import('@/i18n')
        setLocale(res.language)
      }
    }
  } catch (e) {
    /* ignore */
  }
}

// 应用主题配色 - 通过 data-theme 属性切换 CSS 变量
export function applyTheme(color: string): void {
  store.theme.current = color
  if (color === 'blue') {
    document.documentElement.setAttribute('data-theme', 'blue')
    store.theme.headerBg = 'rgba(255, 255, 255, 0.78)'
    store.theme.sidebarBg = 'linear-gradient(180deg, #1E3A8A 0%, #1E40AF 50%, #2563EB 100%)'
  } else if (color === 'black') {
    document.documentElement.setAttribute('data-theme', 'black')
    store.theme.headerBg = 'rgba(10, 10, 10, 0.7)'
    store.theme.sidebarBg = '#0A0A0A'
  } else {
    document.documentElement.setAttribute('data-theme', 'orange')
    store.theme.headerBg = 'rgba(255, 255, 255, 0.72)'
    store.theme.sidebarBg = '#18181B'
  }
}

// 切换侧边栏
// dev only: 暴露到 window 方便调试/UI 验证
if (typeof window !== 'undefined' && import.meta.env.DEV) {
  interface DevWindow extends Window {
    __store__?: Reactive<StoreShape>
    __termPool__?: TermPoolShape
    __createTab__?: typeof createTab
    __removeTab__?: typeof removeTab
    __updateTabStatus__?: typeof updateTabStatus
    __clearAuthState__?: typeof clearAuthState
    __queueOpenTerminal__?: typeof _queueOpenTerminal
    __consumeOpenTerminal__?: typeof _consumeOpenTerminal
  }
  const w: DevWindow = window as unknown as DevWindow
  w.__store__ = store
  w.__termPool__ = termPool
  w.__createTab__ = createTab
  w.__removeTab__ = removeTab
  w.__updateTabStatus__ = updateTabStatus
  w.__clearAuthState__ = clearAuthState
  w.__queueOpenTerminal__ = _queueOpenTerminal
  w.__consumeOpenTerminal__ = _consumeOpenTerminal
}

export function toggleSidebar(): void {
  store.sidebarCollapsed = !store.sidebarCollapsed
}

// =====================================================================
// REVIEW-14 P1-4: clearAuthState - 退出登录 / 401 统一清理状态
// =====================================================================
// 复用点：
//   - Layout.doLogout() 调用 (用户主动退出)
//   - api/index.ts 401 拦截器调用 (token 过期)
// 清理范围：
//   1. 关闭所有 WebSocket 连接（防 token 已作废但 ws 仍跑命令）
//   2. 清空 xterm 实例池 (instances / fitAddons / resizeObservers / wsMap)
//   3. 重置 store.user 为空字串（防旧用户头像残留）
//   4. 重置 store.terminal 全部字段 (tabs / sysUsers / treeCache 等)
//   5. 保留主题设置 (theme) 与登入设置 (settings) - 下次登入后重新覆盖
// =====================================================================
export function clearAuthState(): void {
  try {
    // 1. 关 ws
    for (const id of termPool.wsMap.keys()) {
      try {
        termPool.wsMap.get(id)?.close()
      } catch (_) {
        /* 关闭异常吞掉 */
      }
    }
    // 2. 清池
    termPool.wsMap.clear()
    termPool.instances.clear()
    termPool.fitAddons.clear()
    termPool.resizeObservers.clear()
    // 3. 清 user
    Object.assign(store.user, { username: '', alias: '', role: '', avatar: '' })
    // 4. 清 terminal
    store.terminal.tabs = []
    store.terminal.activeTabId = ''
    store.terminal.sysUser = ''
    store.terminal.sysUsers = []
    store.terminal.treeCache = []
    store.terminal.treeLoaded = false
  } catch (_) {
    // 清理是幂等操作，任何异常都吞掉
  }
}

// 内部类型别名: 兼容旧 api/index.js 返回的非 ApiResponse 包装 (Phase B 收紧)
type ApiResponseAlias = {
  alias?: string
  username?: string
  code?: number
  usrole?: string
  [k: string]: unknown
}
