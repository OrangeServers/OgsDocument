// =============================================================================
// OrangeServer Frontend API 客户端
// ti3-TS: 从 api/index.js 迁移, 加 axios 拦截器类型 + 业务响应封装
// =============================================================================
import axios, {
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
  AxiosError,
} from 'axios'
import type {
  ApiResponse,
  RequestBody,
  ApiError,
} from '@/types'

const http: AxiosInstance = axios.create({
  timeout: 30000,
  withCredentials: true,
})

// HIGH-9：从 cookie 读 csrf_token（与 HttpOnly ogs_token 隔离，前端 JS 可读）
function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[2]) : ''
}

// ===== 401 熔断器 =====
// 登录态失效（后端重启/session 过期）后，各组件可能持续发请求形成 401 风暴 + 消息刷屏。
// 首次 401 时置位 authDead，后续需登录请求直接 fast-fail 不再发出；匿名接口放行；重新登录成功时复位。
let authDead = false
export function isAuthDead(): boolean {
  return authDead
}

const ANON_URL_PATTERNS: readonly string[] = [
  '/local/captcha/', '/account/login', '/account/chk_username', '/account/com_register',
  '/mail/', '/local/health', '/local/status', '/local/settings/open', '/setup/',
]
function isAnonymousUrl(url = ''): boolean {
  return ANON_URL_PATTERNS.some((p) => url.includes(p))
}

// 请求拦截：POST 统一发 application/x-www-form-urlencoded（与旧版 jQuery 一致）
http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  // 熔断：登录态已死，需登录请求直接失败（不发网络请求，从源头掐断 401 循环）
  if (authDead && !isAnonymousUrl(config.url)) {
    return Promise.reject(new AxiosError('auth dead, request blocked by circuit breaker', 'ERR_AUTH_DEAD', config))
  }
  if (config.method === 'get' && config.data) {
    config.params = config.data
    delete config.data
  } else if (config.method === 'post' && config.data && !(config.data instanceof FormData)) {
    // 用浏览器原生 URLSearchParams，编码格式与 jQuery $.param() 完全一致
    const params = new URLSearchParams()
    const flatten = (obj: Record<string, unknown>, prefix: string): void => {
      for (const [key, val] of Object.entries(obj)) {
        const k = prefix ? `${prefix}[${key}]` : key
        if (val == null) {
          params.append(key, '')
        } else if (Array.isArray(val)) {
          // 数组用 repeat 模式: key=a&key=b（与 jQuery traditional:true 一致）
          val.forEach((v: unknown) => params.append(key, v == null ? '' : String(v)))
        } else if (typeof val === 'object') {
          flatten(val as Record<string, unknown>, k)
        } else {
          params.append(key, String(val))
        }
      }
    }
    flatten(config.data as Record<string, unknown>, '')
    config.data = params.toString()
    if (config.headers) {
      config.headers['Content-Type'] = 'application/x-www-form-urlencoded'
    }
  }
  // HIGH-9：所有 POST 请求统一加 X-CSRF-Token header（从 cookie 读 csrf_token）
  //   公开接口（登录/注册/验证码/忘记密码等）后端自动豁免校验
  if (config.method === 'post' && config.headers) {
    const csrfToken = getCookie('csrf_token')
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken
    }
  }
  return config
})

// 响应拦截：统一错误处理
http.interceptors.response.use(
  (res: AxiosResponse) => {
    // 重新登录成功 → 熔断复位，后续请求恢复放行
    if (res.config.url?.includes('/account/login_dl2') && (res.data as { code?: number })?.code === 0) {
      authDead = false
    }
    return res.data
  },
  async (err: AxiosError) => {
    if (err.response) {
      console.error('[API Error]', err.config?.url, err.response.status, err.response.data)
    }
    if (err.response && err.response.status === 401) {
      // 置位熔断器：本次登录态已失效，后续需登录请求直接 fast-fail
      authDead = true
      // REVIEW-14 P1-4: 401 时调 clearAuthState 统一清 store + ws（Layout.doLogout 也复用同一函数）
      try {
        const { clearAuthState } = await import('@/store')
        clearAuthState()
      } catch (e) { /* store 未加载时忽略 */ }
      // 动态 import router 防循环依赖
      try {
        const { default: router } = await import('@/router')
        if (router.currentRoute.value.path !== '/login') {
          router.push('/login').catch(() => {})
        }
      } catch (e) {
        // fallback: router 加载失败时走整页刷新
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// ========== 业务 API 简写 ==========
// 约定: API 函数统一返回 ApiResponse<unknown> (后端 {code, data, msg}),
//       调用方按需断言 data 字段的具体类型. 避免每个 API 都强加返回类型导致
//       业务类型与后端响应形状不一致时大面积报错 (Phase B 可逐 API 收紧).
type ApiCall = (data?: RequestBody) => Promise<ApiResponse<unknown>>
type ApiCallNoArgs = () => Promise<ApiResponse<unknown>>

const p = (url: string): ApiCallNoArgs => () => http.post(url) as unknown as Promise<ApiResponse<unknown>>
const pj = (url: string): ApiCall => (data) => http.post(url, data) as unknown as Promise<ApiResponse<unknown>>

// ========== Auth ==========
// P1-5: 图形验证码（匿名）
export const getCaptcha: ApiCallNoArgs = p('/local/captcha/get')
// UI修复：健康检查（GET /local/health，匿名公开接口，返回 {status:'ok'}），供侧栏真实状态展示
export const getHealth: ApiCallNoArgs = () => http.get('/local/health') as unknown as Promise<ApiResponse<unknown>>
export const login: ApiCall = pj('/account/login_dl2')
export const logout: ApiCallNoArgs = p('/account/login_out')
export const checkAuth: ApiCallNoArgs = p('/local/app_auth_ck')
export const checkUsername: ApiCall = pj('/account/chk_username')
export const register: ApiCall = pj('/account/com_register')
export const sendMail: ApiCall = pj('/mail/send_user_mail')

// ========== User ==========
export const getUserAlias: ApiCallNoArgs = p('/account/user/alias')
export const getUserAuth: ApiCallNoArgs = p('/account/user/auth_list')
export const getUserInfo: ApiCall = pj('/account/user/list')
export const updateUserInfo: ApiCall = pj('/account/user/update')

// ========== Settings ==========
export const getSettings: ApiCall = pj('/local/settings/get')
export const getOpenSettings: ApiCallNoArgs = p('/local/settings/open')
export const updateSettings: ApiCall = pj('/local/settings/update')
// SMTP 授权码仅写入；读取接口不会返回已保存的明文。
export const getMailSettings: ApiCallNoArgs = p('/local/settings/mail/get')
export const updateMailSettings: ApiCall = pj('/local/settings/mail/update')
export const testMailSettings: ApiCall = pj('/local/settings/mail/test')
// REV38-M3: appInit 改调正式 endpoint /local/status（/local/init 已废弃为 alias，运行时返 410 Gone）
export const appInit: ApiCallNoArgs = () =>
  http.post('/local/status', { status: 'ogsfront' }) as unknown as Promise<ApiResponse<unknown>>

// ========== Host ==========
export const getHostList: ApiCall = pj('/server/host/list_all')
export const getHostListPage: ApiCall = pj('/server/host/list_page')
export const getHostDetail: ApiCall = pj('/server/host/list')
export const addHost: ApiCall = pj('/server/host/add')
export const updateHost: ApiCall = pj('/server/host/update')
export const deleteHost: ApiCall = pj('/server/host/del')
export const getHostGroupNameList: ApiCallNoArgs = p('/server/host/group/name_list')
export const getHostGroupList: ApiCall = pj('/server/host/group/list_all')
export const getHostGroupDetail: ApiCall = pj('/server/host/group/list')
export const addHostGroup: ApiCall = pj('/server/host/group/add')
export const updateHostGroup: ApiCall = pj('/server/host/group/update')
export const deleteHostGroup: ApiCall = pj('/server/host/group/del')

// ========== SysUser ==========
export const getSysUserList: ApiCall = pj('/server/sys/user/list_all')
export const getSysUserDetail: ApiCall = pj('/server/sys/user/list')
export const addSysUser: ApiCall = pj('/server/sys/user/add')
export const updateSysUser: ApiCall = pj('/server/sys/user/update')
export const deleteSysUser: ApiCall = pj('/server/sys/user/del')

// ========== Group ==========
export const getGroupNameList: ApiCallNoArgs = p('/account/group/name_list')
export const getUserGroupList: ApiCall = pj('/account/group/list_all')
export const getUserGroupDetail: ApiCall = pj('/account/group/list')
export const addUserGroup: ApiCall = pj('/account/group/add')
export const updateUserGroup: ApiCall = pj('/account/group/update')
export const deleteUserGroup: ApiCall = pj('/account/group/del')

// ========== SysUser Name ==========
export const getSysUserNameList: ApiCallNoArgs = p('/server/sys/user/name_list')

// ========== Tree ==========
export const getTreeData: ApiCallNoArgs = p('/local/data')

// ========== User Account ==========
export const getUserListAll: ApiCall = pj('/account/user/list_all')
export const resetUserPwd: ApiCall = pj('/account/user/reset_pwd')

// ========== Forgot Password ==========
export const forgotPwdSend: ApiCall = pj('/account/forgot_pwd_send')
export const forgotPwdReset: ApiCall = pj('/account/forgot_pwd_reset')

// ========== Dashboard ==========
export const getCountList: ApiCallNoArgs = p('/server/count_list_all')
export const getChartUpdate: ApiCallNoArgs = p('/local/chart/update')
export const getChartCount: ApiCallNoArgs = p('/local/chart/count')

// ========== Batch operations ==========
// The existing endpoints are synchronous and may legitimately run longer than
// the global 30-second request timeout when several hosts are selected.
export const batchCommand: ApiCall = (data) =>
  http.post('/server/host_list_cmd', data, { timeout: 0 }) as unknown as Promise<ApiResponse<unknown>>
export const batchScript = (data: FormData): Promise<ApiResponse<unknown>> =>
  http.post('/server/file/put', data, { timeout: 0 }) as unknown as Promise<ApiResponse<unknown>>

// ========== AI Agent ==========
export const getAiProviders: ApiCallNoArgs = () =>
  http.get('/ai/providers') as unknown as Promise<ApiResponse<unknown>>
// 仪表盘：AI 运维近 7 天执行统计
export const getAiStats: ApiCallNoArgs = () =>
  http.get('/ai/stats') as unknown as Promise<ApiResponse<unknown>>

// ========== Authority ==========
export const getAuthList: ApiCallNoArgs = () =>
  http.post('/auth/host/list_all', { page: 1, limit: 99999 }) as unknown as Promise<ApiResponse<unknown>>
export const getAuthUpList: ApiCall = pj('/auth/host/uplist')
export const getAuthOptions: ApiCall = pj('/auth/host/list')
export const deleteAuth: ApiCall = pj('/auth/host/del')

// ========== Cron ==========
export const getCronList: ApiCallNoArgs = () =>
  http.post('/local/cron/list_all', { page: 1, limit: 99999 }) as unknown as Promise<ApiResponse<unknown>>
export const deleteCron: ApiCall = pj('/local/cron/del')
export const pauseCron: ApiCall = pj('/local/cron/pause')
export const resumeCron: ApiCall = pj('/local/cron/resume')
export const batchCron: ApiCall = pj('/local/cron/com_list')
export const runCron: ApiCall = pj('/local/cron/run')
export const getCronLastResult: ApiCall = pj('/local/cron/last_result')

// ========== Logs ==========
export const getLogs: ApiCall = pj('/account/logs/log')
export const getLogsByDate: ApiCall = pj('/account/logs/date')
export const searchLogs: ApiCall = pj('/account/logs/select')
// REV34-M12: 登录 IP Top N 聚合（Dashboard loginTop 专用）
export const getLoginIpTop: ApiCall = pj('/local/log/login/ip_top')

// ========== File ==========
// REV38-M5: getFileList 已迁移到 /local/file/list（/local/file/def_get 保留为 alias，运行时仍可用，但前端统一调正式 endpoint）
export const getFileList: ApiCall = pj('/local/file/list')
export const uploadFile: ApiCall = pj('/local/file/put')
export const createDir: ApiCall = pj('/local/file/add')
export const deleteFile: ApiCall = pj('/local/file/del')
export const renameFile: ApiCall = pj('/local/file/rename')
export const getFileSize: ApiCall = pj('/local/file/size')

// ========== Image ==========
// REV16 B10 HIGH-2：username 走白名单 [A-Za-z0-9_.\-]{1,32}，防止配合后端 GetUserImage 路径越界
//   配合 [B9 HIGH-2](REV16_P2-5_init_review.md) 的后端 GetUserImage 路径越界读
//   双向防御：前端白名单 + 后端 realpath 越界检测
const _AVATAR_NAME_RE: RegExp = /^[A-Za-z0-9_.\-]{1,32}$/
export function getUserAvatar(username: string | null | undefined): string {
  const safe = (typeof username === 'string' && _AVATAR_NAME_RE.test(username)) ? username : 'default'
  return `/local/image/test_get/${safe}`
}
// REV34-M10: 头像上传 endpoint 改为正式 /local/image/upload（去掉 test_ 前缀）
//   后端 /local/image/test_put 仍保留为旧 alias，不影响历史数据
export const uploadAvatar: ApiCall = pj('/local/image/upload')

// 导出 http 实例，供视图中的额外请求使用（自动走 form 编码）
export { http }

// 类型导出 (re-export) 供业务方断言 data 字段
export type { ApiResponse, ApiError, RequestBody }
