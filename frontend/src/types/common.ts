// =============================================================================
// OrangeServer Frontend - 公共基础类型
// ti3-TS: 渐进式 TypeScript 迁移的公共类型沉淀
// 原则: 业务无关的容器/响应/分页结构放这里, 业务类型按模块拆 (auth/host/cron...)
// =============================================================================

/** API 业务码: 0 成功, 1xx 业务警告, 2xx 业务错误, 401 未登录, 403 无权限, 5xx 系统 */
export type ApiCode = number

/** ISO 时间戳 (字符串形式, 不解析为 Date 以避免序列化问题) */
export type IsoTimestamp = string

/** 数字字符串 (ID 用, 避免精度问题) */
export type NumStr = string

/** 分页请求参数 */
export interface PaginationParams {
  page?: number
  pageSize?: number
  keyword?: string
  [k: string]: unknown
}

/** 分页响应 */
export interface PaginationResult<T> {
  list: T[]
  total: number
  page: number
  pageSize: number
}

/** 通用业务响应 (后端 ApiResponsePayload 一致: code/data/msg) */
export interface ApiResponse<T = unknown> {
  code: ApiCode
  data: T
  msg: string
}

/** 列表响应 (data 是 PaginationResult) */
export type ListResponse<T> = ApiResponse<PaginationResult<T>>

/** 元素项响应 (data 是单条) */
export type ItemResponse<T> = ApiResponse<T>

/** 表单通用状态: idle / submitting / success / error */
export type FormState = 'idle' | 'submitting' | 'success' | 'error'

/** 异步操作结果 (前端简化版, 替代 try/catch 双返回值) */
export type AsyncResult<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E }

/** 角色: 后端 user.py 角色模型一致 */
export type UserRole = 'admin' | 'audit' | 'user' | string

/** 开关 on/off 字符串 (后端 Settings 模型字段) */
export type OnOff = 'on' | 'off'

/** 通用 key-value 字典 (避免 Record<string, any>) */
export type Dict<T = unknown> = { [k: string]: T }

/** 必填工具类型 */
export type RequiredKey<T, K extends keyof T> = T & Required<Pick<T, K>>

/** 省略指定 key */
export type OmitKey<T, K extends keyof T> = Omit<T, K>

/** 提取数组元素的 type 工具 */
export type ArrayItem<T> = T extends (infer U)[] ? U : never
