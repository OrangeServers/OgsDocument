// =====================================================================
// REVIEW-14 P1-7: WebSocket URL 解析与同源校验
// ti3-TS: 加类型注解
// =====================================================================

/** resolveWsUrl 入参 */
export interface ResolveWsUrlOpts {
  /** import.meta.env.VITE_WS_URL */
  envWsUrl?: string
  /** VITE_API_TARGET 的 origin (http://host:port) */
  apiTarget?: string
  /** window.location.origin (兜底) */
  pageOrigin?: string
}

/**
 * 安全解析 WS URL
 *   1. 必须以 ws:// 或 wss:// 开头
 *   2. 协议必须与页面协议一致 (https 页必须 wss://)
 *   3. 主机名必须与 VITE_API_TARGET 主机名一致 (同源策略的宽松版)
 *   校验失败时回退到相对路径 (/local/websocket) 防止 ws 不可用.
 */
export function resolveWsUrl(opts: ResolveWsUrlOpts): string {
  const envWs: string = (opts && opts.envWsUrl) || ''
  const apiTarget: string = (opts && opts.apiTarget) || ''
  const pageOrigin: string = (opts && opts.pageOrigin)
    || (typeof window !== 'undefined' ? window.location.origin : '')

  // 1. 优先用 VITE_WS_URL, 但必须通过安全校验
  if (envWs) {
    const reason: string | null = _validateWsUrl(envWs, apiTarget, pageOrigin)
    if (!reason) {
      return envWs
    }
    // 校验失败: dev 抛错, prod 静默回退 (Vite 静态替换 import.meta.env.DEV)
    if (typeof console !== 'undefined') {
      console.warn('[ws] VITE_WS_URL invalid, falling back to relative path:', reason, 'url=', envWs)
    }
  }

  // 2. 回退: 相对路径
  const wsProtocol: 'wss:' | 'ws:' = (typeof window !== 'undefined' && window.location.protocol === 'https:')
    ? 'wss:'
    : 'ws:'
  const host: string = (typeof window !== 'undefined' && window.location.host) || ''
  return `${wsProtocol}//${host}/local/websocket`
}

/**
 * 校验 WS URL
 * @returns null 表示通过; 字符串表示失败原因
 */
function _validateWsUrl(wsUrl: string, apiTarget: string, _pageOrigin: string): string | null {
  if (typeof wsUrl !== 'string' || !wsUrl) return 'empty'
  let u: URL
  try { u = new URL(wsUrl) } catch (_) { return 'parse-failed' }
  if (u.protocol !== 'ws:' && u.protocol !== 'wss:') return 'bad-protocol:' + u.protocol

  // 页面协议为 https 时强制 wss
  const pageProto: 'https' | 'http' = (typeof window !== 'undefined' && window.location.protocol === 'https:')
    ? 'https'
    : 'http'
  if (pageProto === 'https' && u.protocol !== 'wss:') {
    return 'page-is-https-but-ws-not-wss'
  }

  // 主机名必须与 VITE_API_TARGET 同源 (不同 port 允许)
  if (apiTarget) {
    let apiHost = ''
    try { apiHost = new URL(apiTarget).hostname } catch (_) { /* parse 失败时跳过 */ }
    if (apiHost && u.hostname !== apiHost) {
      return 'ws-host-not-match-api-host:ws=' + u.hostname + ',api=' + apiHost
    }
  }

  return null
}
