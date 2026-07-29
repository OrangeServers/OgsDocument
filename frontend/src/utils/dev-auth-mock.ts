// =====================================================================
// REVIEW-14 P0-3: Dev 登录态 mock 多重防护
// ti3-TS: 加类型注解
// =====================================================================

// hostname 白名单: 仅本机回环地址允许 dev mock
const HOSTNAME_WHITELIST: Set<string> = new Set([
  'localhost',
  '127.0.0.1',
  '[::1]',
])

// 防护 5: 模块级一次性标志
let _installed = false

/**
 * 防护 1~4: 运行时守卫
 * @returns true 表示通过所有守卫, 可继续 mock
 */
function _passesGuards(): boolean {
  // 防护 1: Vite 内建静态常量 (dev=true / prod=false, prod 时被 tree-shake)
  if (typeof import.meta === 'undefined' || !import.meta.env || !import.meta.env.DEV) {
    if (typeof console !== 'undefined') {
      console.warn('[dev-auth-mock] BLOCKED by guard-1: import.meta.env.DEV is not true')
    }
    return false
  }

  // 防护 2: 通用 NODE_ENV 二次检查
  // Vite 浏览器开发环境通常没有 Node.js process 全局；import.meta.env.DEV
  // 已是主要静态门禁。仅在 process 确实存在时做第二次环境校验。
  if (typeof process !== 'undefined' && process.env && process.env.NODE_ENV && process.env.NODE_ENV !== 'development') {
    if (typeof console !== 'undefined') {
      console.warn('[dev-auth-mock] BLOCKED by guard-2: NODE_ENV =', process.env.NODE_ENV)
    }
    return false
  }

  // 防护 3: 浏览器环境必须存在
  if (typeof window === 'undefined' || typeof document === 'undefined' || typeof XMLHttpRequest === 'undefined') {
    if (typeof console !== 'undefined') {
      console.warn('[dev-auth-mock] BLOCKED by guard-3: window/document/XHR missing')
    }
    return false
  }

  // 防护 4: hostname 白名单
  const host: string = String(window.location.hostname || '').toLowerCase()
  if (!HOSTNAME_WHITELIST.has(host)) {
    if (typeof console !== 'undefined') {
      console.warn('[dev-auth-mock] BLOCKED by guard-4: hostname not in whitelist:', host)
    }
    return false
  }

  return true
}

/**
 * 安装 dev 登录态 mock
 * - 必须先通过 6 重防护
 * - 入口: main.ts 仅在 import.meta.env.DEV 为 true 时调用
 */
export async function installDevAuthMock(): Promise<string | null> {
  // 防护 5: 一次性
  if (_installed) return null
  // 防护 1~4: 守卫
  if (!_passesGuards()) return null
  _installed = true

  const params = new URLSearchParams(window.location.search)
  const devUser: string | null = params.get('dev_login')
  const devToken: string | null = params.get('dev_token')
  // 没有 dev 参数时不安装 mock (避免无意义 hook 全局 API)
  if (!devUser && !devToken) return null

  interface OkResp { code: number; msg: string }
  const okResp = (): OkResp => ({ code: 0, msg: 'ok' })
  const roleResp = () => ({
    code: 0,
    msg: 'ok',
    data: { usrole: devUser === 'admin' ? 'admin' : 'user' },
  })
  const mockResponse = (url: string): object | null => {
    if (url.indexOf('/local/app_auth_ck') !== -1) return okResp()
    if (url.indexOf('/account/user/auth_list') !== -1) return roleResp()
    return null
  }

  // 防护 6: 固化原始引用 (在覆盖前一次性保存, 防链式污染)
  const origFetch = window.fetch
  const origOpen = XMLHttpRequest.prototype.open
  const origSend = XMLHttpRequest.prototype.send
  try { Object.freeze(origFetch) } catch (_) { /* IE 兼容兜底 */ }
  try { Object.freeze(origOpen) } catch (_) { /* IE 兼容兜底 */ }
  try { Object.freeze(origSend) } catch (_) { /* IE 兼容兜底 */ }

  // Hook window.fetch: 仅 mock /local/app_auth_ck 接口
  window.fetch = function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url: string = typeof input === 'string'
      ? input
      : (input && typeof input === 'object' && 'url' in input ? String((input as Request).url) : '')
    const body = mockResponse(url)
    if (body) {
      return Promise.resolve(new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    }
    return origFetch.call(this, input, init)
  }

  // Hook XMLHttpRequest: 同样仅 mock /local/app_auth_ck 接口
  // 给原型注入新方法 (XHR 原型 augment)
  interface DevMockXHR extends XMLHttpRequest { __devMockUrl?: string }
  XMLHttpRequest.prototype.open = function (this: DevMockXHR, method: string, url: string | URL): void {
    try { this.__devMockUrl = typeof url === 'string' ? url : url.toString() } catch (_) { /* 不可写时跳过 */ }
    // XMLHttpRequest.open 签名: open(method, url, async?, username?, password?)
    // 显式传 async=true 避免 ts(2554) 期望 4-6 个参数
    return origOpen.call(this, method, url, true)
  }
  XMLHttpRequest.prototype.send = function (this: DevMockXHR, _body?: Document | XMLHttpRequestBodyInit | null): void {
    const url: string = (this && this.__devMockUrl) || ''
    const body = mockResponse(url)
    if (body) {
      try {
        Object.defineProperty(this, 'readyState', { configurable: true, get: function () { return 4 } })
        Object.defineProperty(this, 'status', { configurable: true, get: function () { return 200 } })
        Object.defineProperty(this, 'responseText', { configurable: true, get: function () { return JSON.stringify(body) } })
        Object.defineProperty(this, 'response', { configurable: true, get: function () { return JSON.stringify(body) } })
      } catch (_) { /* defineProperty 失败时跳过 */ }
      if (typeof this.onreadystatechange === 'function') {
        try { this.onreadystatechange.call(this, new Event('readystatechange')) } catch (_) { /* 业务回调异常吞掉 */ }
      }
      setTimeout(() => {
        if (typeof this.onload === 'function') {
          // XHR onload 事件签名是 ProgressEvent<EventTarget>, 用 ProgressEvent 构造避免 ts(2769)
          try { this.onload.call(this, new ProgressEvent('load')) } catch (_) { /* 业务回调异常吞掉 */ }
        }
      }, 0)
      return
    }
    return origSend.call(this, _body)
  }

  // Mock store.user + 写 cookie + 跳转
  // 动态 import 避免循环依赖 (store / router 互相引用)
  try {
    const { store } = await import('@/store')
    const roles: Record<string, string> = { admin: 'admin', user: 'user' }
    if (devUser) {
      store.user = {
        username: devUser,
        alias: devUser === 'admin' ? '管理员' : devUser,
        role: roles[devUser] || 'user',
        avatar: '',
      }
    }
    if (devToken) {
      document.cookie = 'ogs_token=' + devToken + '; path=/'
    } else if (devUser) {
      document.cookie = 'ogs_token=dev-mock-' + devUser + '; path=/'
    }
    return params.get('goto') || '/dashboard'
  } catch {
    return null
  }
}

// 默认导出便于 main.ts 整体引入
export default { installDevAuthMock }
