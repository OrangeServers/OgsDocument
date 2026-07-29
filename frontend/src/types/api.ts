// =============================================================================
// OrangeServer Frontend - axios 拦截器与 HTTP 类型
// ti3-TS: 兼容后端 csrf_token + x-www-form-urlencoded 序列化
// =============================================================================

import type {
  AxiosRequestConfig,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from 'axios'

/** HTTP 错误码 (HTTP status) */
export type HttpStatus = number

/** 业务错误: HTTP 4xx/5xx 抛错时携带 */
export interface ApiError {
  status: HttpStatus
  code?: number
  message: string
  url?: string
  method?: string
}

/** POST 提交体: 任意可序列化对象 (FormData 走原生) */
export type RequestBody =
  | Record<string, unknown>
  | FormData
  | string
  | null
  | undefined

/** GET 请求的 query 参数类型 */
export type QueryParams = Record<string, string | number | boolean | undefined>

/** 扩展 axios 配置 (前端业务约定) */
export interface ApiRequestConfig extends AxiosRequestConfig {
  /** 是否跳过 CSRF header 注入 (登录/注册/验证码等公开接口已由后端豁免) */
  skipCsrf?: boolean
  /** 是否跳过 401 自动跳转登录 */
  skipAuthRedirect?: boolean
}

/** axios 拦截器用的 request config 类型 (内部) */
export type InternalRequestConfig = InternalAxiosRequestConfig & {
  skipCsrf?: boolean
  skipAuthRedirect?: boolean
}

/** axios 响应 (保留完整 axios response) */
export type ApiRawResponse<T> = AxiosResponse<{
  code: number
  data: T
  msg: string
}>

/** http.get/post 风格的简写返回 */
export type ApiData<T> = Promise<T>
