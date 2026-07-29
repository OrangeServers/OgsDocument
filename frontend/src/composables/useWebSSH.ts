// =====================================================================
// REV33-M1: useWebSSH composable - xterm/WS 生命周期管理
// ti3-TS: 加类型注解
// =====================================================================
// 抽离 WebSSHCore.vue 中的：
//   1. initTerminal: xterm + WebSocket 初始化
//   2. safeDestroy: 反向清理（ws.close + ResizeObserver disconnect + term.dispose）
//   3. watch(tabs): 增/减 tab 时同步实例
//   4. watch(activeTabId): 切换时重新 fit + 滚到可见区
//
// 设计：useWebSSH 返回 register(elRef, {id,host,sysUser}) / unregister(id) / fitAll()
// WebSSHCore 调用 register 注入 tab，组件卸载时遍历 unregister + onBeforeUnmount
// =====================================================================
import { ref, computed, watch, nextTick, onBeforeUnmount, type ComputedRef, type WritableComputedRef } from 'vue'
import { Terminal, type ITheme } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { resolveWsUrl } from '@/utils/ws'
import { store, termPool, removeTab, updateTabStatus } from '@/store'

const XTERM_THEME: ITheme = {
  // 官网终端风：#16181D 纯黑底；ANSI 色保留高可读性调色板
  foreground: '#D4D7DE',
  background: '#16181D',
  cursor: '#F76707',
  selectionBackground: 'rgba(247,103,7,0.28)',
  black: '#45475A', red: '#F38BA8', green: '#A6E3A1', yellow: '#F9E2AF',
  blue: '#89B4FA', magenta: '#F5C2E7', cyan: '#94E2D5', white: '#BAC2DE',
}

/** 读取当前主题主色（--ogs-primary，跟随 orange/blue/black 三主题），失败回退品牌橙 */
function resolvePrimaryColor(): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue('--ogs-primary').trim()
  return v || '#F76707'
}

/** hex 颜色转 rgba 字符串（xterm 只接受颜色值，不支持 CSS 变量） */
function hexToRgba(hex: string, alpha: number): string {
  const m = hex.replace('#', '').match(/^([0-9a-f]{6})$/i)
  if (!m) return `rgba(247,103,7,${alpha})`
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`
}

/** 生成跟随当前主题变量的 xterm 主题（光标/选区色跟随 --ogs-primary） */
function resolveXtermTheme(): ITheme {
  const primary = resolvePrimaryColor()
  return { ...XTERM_THEME, cursor: primary, selectionBackground: hexToRgba(primary, 0.28) }
}

/** 终端实例 Map (复用 store.termPool) */
type TermInstanceMap = Map<string, Terminal>
type TermFitMap = Map<string, FitAddon>
type WsMap = Map<string, WebSocket>
type ResizeMap = Map<string, ResizeObserver>

/**
 * 初始化单个 xterm + WebSocket
 * @param id tab id
 * @param host 主机名
 * @param sysU 系统用户名
 * @param container xterm 容器
 */
export function initTerminal(id: string, host: string, sysU: string, container: HTMLElement): void {
  const term = new Terminal({
    rows: 30,
    convertEol: true,
    scrollback: Number(store.settings.terminal_scrollback) || 1000,
    disableStdin: false,
    cursorStyle: 'underline',
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "'JetBrains Mono','Consolas','Monaco','Courier New',monospace",
    theme: resolveXtermTheme(),
  })
  const fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(container)
  fitAddon.fit()

  ;(termPool.instances as unknown as TermInstanceMap).set(id, term)
  ;(termPool.fitAddons as unknown as TermFitMap).set(id, fitAddon)

  term.writeln(`\x1b[1;33m  Welcome to Orange Shell\x1b[0m`)
  term.writeln(`\x1b[90m  Connecting to \x1b[37m${host}\x1b[90m as \x1b[37m${sysU}\x1b[90m...\x1b[0m\r\n`)

  // REVIEW-14 P1-7: WS URL 校验 + 同源检查
  const wsUrl = resolveWsUrl({
    envWsUrl: import.meta.env.VITE_WS_URL,
    apiTarget: import.meta.env.VITE_API_TARGET,
    pageOrigin: window.location.origin,
  })

  let ws: WebSocket
  try {
    ws = new WebSocket(wsUrl)
  } catch (e) {
    const err = e as Error
    term.writeln(`\r\n\x1b[31mWebSocket creation failed: ${err.message}\x1b[0m`)
    updateTabStatus(id, 'error')
    return
  }
  ;(termPool.wsMap as unknown as WsMap).set(id, ws)

  ws.onopen = (): void => {
    ws.send(JSON.stringify({ hostname: host, username: sysU }))
    // 不发送额外 '\r'，SSH invoke_shell() 已自带初始 prompt
    updateTabStatus(id, 'connected')
    term.writeln(`\x1b[32m  ✓ Connected\x1b[0m\r\n`)
  }
  ws.onmessage = (e: MessageEvent): void => { try { term.write(e.data) } catch (_) { /* 渲染异常吞掉 */ } }
  ws.onerror = (): void => {
    term.writeln(`\r\n\x1b[31m  ✗ Connection error\x1b[0m`)
    updateTabStatus(id, 'error')
  }
  ws.onclose = (e: CloseEvent): void => {
    term.writeln(`\r\n\x1b[33m  ⚠ Connection closed (code: ${e.code})\x1b[0m`)
    updateTabStatus(id, 'closed')
  }
  term.onData((d: string): void => { if (ws.readyState === WebSocket.OPEN) ws.send(d) })

  const ro = new ResizeObserver(() => { try { fitAddon.fit() } catch (_) { /* 容器卸载时跳过 */ } })
  ro.observe(container)
  ;(termPool.resizeObservers as unknown as ResizeMap).set(id, ro)
}

/**
 * 安全销毁：关闭 ws + ResizeObserver disconnect + term.dispose + 清理池
 * @param id tab id
 */
export function safeDestroy(id: string): void {
  const ws = (termPool.wsMap as unknown as WsMap).get(id)
  if (ws) { try { ws.close() } catch (_) { /* 已关闭时跳过 */ } ; (termPool.wsMap as unknown as WsMap).delete(id) }
  const ro = (termPool.resizeObservers as unknown as ResizeMap).get(id)
  if (ro) { ro.disconnect(); (termPool.resizeObservers as unknown as ResizeMap).delete(id) }
  const term = (termPool.instances as unknown as TermInstanceMap).get(id)
  if (term) { try { term.dispose() } catch (_) { /* 重复 dispose 时跳过 */ } ; (termPool.instances as unknown as TermInstanceMap).delete(id) }
  ;(termPool.fitAddons as unknown as TermFitMap).delete(id)
}

/** termRef 字典: tabId -> HTMLElement */
export interface TermRefMap {
  [id: string]: HTMLElement
}

/** useWebSSH 返回值 */
export interface UseWebSSHReturn {
  termRefs: TermRefMap
  setTermRef: (id: string, el: HTMLElement | null) => void
  register: (id: string, host: string, sysUser: string) => void
  unregister: (id: string) => void
  closeTab: (id: string) => void
  fitActive: () => void
  /** tabs 类型为 unknown[] (来源 store), 调用方需在 v-for 中按 TerminalTab 显式处理 */
  tabs: ComputedRef<unknown[]>
  activeTabId: WritableComputedRef<string>
}

/**
 * useWebSSH composable
 */
export function useWebSSH(): UseWebSSHReturn {
  const termRefs: TermRefMap = {}

  function setTermRef(id: string, el: HTMLElement | null): void {
    if (el) termRefs[id] = el
  }

  function register(id: string, host: string, sysUser: string): void {
    const container = termRefs[id]
    if (!container) return
    if ((termPool.instances as unknown as TermInstanceMap).has(id)) return
    initTerminal(id, host, sysUser, container)
  }

  function unregister(id: string): void {
    safeDestroy(id)
  }

  function closeTab(id: string): void {
    safeDestroy(id)
    removeTab(id)
  }

  function fitActive(): void {
    nextTick(() => {
      const activeId = store.terminal.activeTabId
      const fit = (termPool.fitAddons as unknown as TermFitMap).get(activeId)
      if (fit) try { fit.fit() } catch (_) { /* 容器不可见时跳过 */ }
    })
  }

  // 监听 tabs 变化：关闭时销毁、新增时初始化
  watch(
    () => store.terminal.tabs.map((t) => ({ id: t.id, host: t.host, sysUser: t.sysUser })),
    (next, prev) => {
      const prevIds = new Set((prev || []).map((t) => t.id))
      const nextIds = new Set(next.map((t) => t.id))
      // 关闭
      for (const id of prevIds) {
        if (!nextIds.has(id)) safeDestroy(id)
      }
      // 新增
      nextTick(() => {
        for (const t of next) {
          if (!prevIds.has(t.id)) {
            // BUGFIX: host 可能是字符串(createTab传入)或 TerminalHost 对象
            const hostStr = typeof t.host === 'string'
              ? t.host
              : (t.host?.host || t.host?.name || '')
            const sysUserName = typeof t.sysUser === 'string'
              ? t.sysUser
              : (t.sysUser?.name || t.sysUser?.username || '')
            register(t.id, hostStr, sysUserName)
          }
        }
      })
    },
    { deep: true }
  )

  // 切换 tab 时重新 fit
  watch(() => store.terminal.activeTabId, () => fitActive())

  // 组件卸载时清理所有 tab 实例
  onBeforeUnmount(() => {
    for (const t of store.terminal.tabs) {
      try { safeDestroy(t.id) } catch (_) { /* 单 tab 销毁失败不影响其他 */ }
    }
  })

  return {
    termRefs,
    setTermRef,
    register,
    unregister,
    closeTab,
    fitActive,
    tabs: computed(() => store.terminal.tabs as unknown as unknown[]),
    activeTabId: computed({
      get: () => store.terminal.activeTabId,
      set: (v: string) => { store.terminal.activeTabId = v },
    }),
  }
}
