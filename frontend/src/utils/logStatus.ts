// =====================================================================
// REV35-L3: log status 工具 — 3 个 Audit + Dashboard + 命令日志共用
// ti3-TS: 加类型注解
// =====================================================================

/** 状态判定: 后端 log_status 字段类型多样, 容忍所有变体 */
export type LogStatusInput = boolean | number | string | null | undefined

/**
 * 判断日志状态是否为成功
 * 容忍类型: boolean true / 数字 1 / 字符串 '1' / 'true' / 'success' / '成功'
 */
export function isSuccess(s: LogStatusInput): boolean {
  return s === true || s === 1 || s === '1' || s === 'true' || s === 'success' || s === '成功' // i18n-ignore 后端协议值
}

/**
 * 判断日志状态是否为失败
 */
export function isFail(s: LogStatusInput): boolean {
  return s === false
    || s === 0
    || s === '0'
    || s === 'false'
    || s === 'fail'
    || s === 'failed'
    || s === 'error'
    || s === '失败' // i18n-ignore 后端协议值
}

/** 判断日志状态是否为部分失败（兼容已有“部分成功”历史记录） */
export function isPartial(s: LogStatusInput): boolean {
  return s === 'partial'
    || s === 'partial_success'
    || s === '部分成功' // i18n-ignore 后端协议值
    || s === '部分失败' // i18n-ignore 后端协议值
}

/** 状态 CSS class 联合类型 */
export type StatusClass = 'is-success' | 'is-fail' | 'is-warn' | 'is-unknown'

/**
 * 状态 → CSS class 映射
 */
export function statusClass(s: LogStatusInput): StatusClass {
  if (isSuccess(s)) return 'is-success'
  if (isFail(s)) return 'is-fail'
  if (isPartial(s)) return 'is-warn'
  return 'is-unknown'
}

// I18N: 类型解耦——上面 isSuccess/isFail/isPartial 里的 '成功'/'失败' 等
//   中文串是后端/存量数据的协议输入值（不是展示文案），原样保留；
//   展示层改为 kind → t('common.status.<kind>')。旧的中文联合类型已移除。
export type StatusKind = 'success' | 'fail' | 'partial' | 'unknown'

/** 状态 → 语义 kind（视图层用 t(`common.status.${kind}`) 渲染） */
export function statusKind(s: LogStatusInput): StatusKind {
  if (isSuccess(s)) return 'success'
  if (isFail(s)) return 'fail'
  if (isPartial(s)) return 'partial'
  return 'unknown'
}

import { t } from '@/i18n'

/** 状态 → 当前语言 label（保留旧函数名，返回值随语言变化） */
export function statusLabel(s: LogStatusInput): string {
  return t(`common.status.${statusKind(s)}`)
}
