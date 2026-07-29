// =====================================================================
// host.js 工具 — 主机名/IP/端口校验
// ti3-TS: 加类型注解 + element-plus async-validator 回调类型
// =====================================================================
import { t } from '@/i18n'

/** 主机名解析输入: 字符串 (逗号分隔) 或字符串数组 */
export type HostListInput = string | string[] | null | undefined

/**
 * 主机名解析
 * 兼容两种后端字段格式:
 *   - 字符串（逗号分隔）: "yw199,yw200,test-python-238"
 *   - 数组: ["yw199", "yw200", "test-python-238"]
 * 输出统一为去空、去重、保持原顺序的字符串数组。
 */
export function parseHostList(host: HostListInput): string[] {
  if (host == null) return []
  if (Array.isArray(host)) {
    const seen = new Set<string>()
    const out: string[] = []
    for (const item of host) {
      const s = String(item == null ? '' : item).trim()
      if (!s || seen.has(s)) continue
      seen.add(s)
      out.push(s)
    }
    return out
  }
  if (typeof host === 'string') {
    const seen = new Set<string>()
    const out: string[] = []
    for (const raw of host.split(',')) {
      const s = raw.trim()
      if (!s || seen.has(s)) continue
      seen.add(s)
      out.push(s)
    }
    return out
  }
  return []
}

// =====================================================================
// REVIEW-14 P1-2: 主机 IP / 端口校验
// =====================================================================
// IPv4 严格校验: 0-255 四段, 点分十进制
const IPV4_RE: RegExp = /^(25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)){3}$/

/**
 * 校验 IPv4 地址
 * @param ip IP 字符串
 * @returns true 表示合法
 */
export function isValidIPv4(ip: string): boolean {
  if (typeof ip !== 'string') return false
  const s = ip.trim()
  if (!s) return false
  return IPV4_RE.test(s)
}

/**
 * 校验端口: 1-65535 整数
 * @param port 端口字符串或数字
 * @returns 是否合法
 */
export function isValidPort(port: string | number | null | undefined): boolean {
  if (port == null || port === '') return false
  const s = String(port).trim()
  if (!/^\d+$/.test(s)) return false
  const n = Number(s)
  return Number.isInteger(n) && n >= 1 && n <= 65535
}

// Element Plus async-validator 适配器 (供 el-form :rules 使用)
// element-plus 表单规则: (rule, value, callback) => void
type AsyncValidatorCallback = (err?: Error) => void
type AsyncValidatorRule = unknown
type AsyncValidatorFn = (
  rule: AsyncValidatorRule,
  value: unknown,
  callback: AsyncValidatorCallback
) => void

export const ipv4Validator: AsyncValidatorFn = (rule, value, callback) => {
  if (value == null || value === '') {
    callback(new Error(t('common.validation.ipRequired')))
    return
  }
  if (!isValidIPv4(String(value))) {
    callback(new Error(t('common.validation.ipInvalid')))
    return
  }
  callback()
}

export const portValidator: AsyncValidatorFn = (rule, value, callback) => {
  if (value == null || value === '') {
    callback(new Error(t('common.validation.portRequired')))
    return
  }
  if (!isValidPort(value as string | number | null | undefined)) {
    callback(new Error(t('common.validation.portRange')))
    return
  }
  callback()
}

