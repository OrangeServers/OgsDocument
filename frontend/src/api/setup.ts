// =============================================================================
// SETUP-WIZARD: 首次部署配置向导专用 API 客户端
// 不复用 api/index.ts 的 http 实例：那边强制 form-urlencoded 且 401 会跳 /login，
// 向导阶段无登录态、走 JSON、鉴权用 X-Setup-Token 头。
// =============================================================================
import { t } from '@/i18n'
import axios, { type AxiosInstance } from 'axios'

export interface SetupStatus {
  mode: 'setup' | 'normal' | 'maintenance'
  missing?: string[]
  env_locked?: string[]
  deployment?: 'docker' | 'bare'
  token_file?: string
  error?: string
  hint?: string
}

export interface SetupCheckResult {
  ok: boolean
  msg: string
  server_version?: string
  db_exists?: boolean
  has_tables?: boolean
}

export interface SetupPrefill {
  mysql: {
    host: string
    port: number
    dbname: string
    user: string
    password_configured: boolean
  }
  redis: {
    host: string
    port: number
    db: number
    password_configured: boolean
  }
}

export interface SetupStep {
  name: string
  ok: boolean
  msg: string
}

export interface SetupApplyResult {
  ok: boolean
  msg?: string
  steps?: SetupStep[]
}

export interface SetupApplyPayload {
  mysql: { host: string; port: number; dbname: string; user: string; password: string }
  redis: { host: string; port: number; password: string; db: number }
  admin: { username: string; password: string; email: string }
  secrets?: { secret_key?: string; fernet_key?: string }
  settings?: { system_name?: string; register_status?: string; login_notice?: string }
  mail?: { smtp_host: string; smtp_port: number; security: 'ssl' | 'starttls' | 'none'; from_email: string; password: string }
}

const client: AxiosInstance = axios.create({
  timeout: 150000, // apply 含建表 + 连接复测，放宽超时
  headers: { 'Content-Type': 'application/json' },
})

let setupToken = ''

export function setSetupToken(token: string): void {
  setupToken = token
}

client.interceptors.request.use(config => {
  if (setupToken) config.headers['X-Setup-Token'] = setupToken
  return config
})

export async function getSetupStatus(): Promise<SetupStatus> {
  const res = await client.get('/setup/api/status')
  return res.data as SetupStatus
}

export async function verifySetupToken(token: string): Promise<boolean> {
  try {
    await client.post('/setup/api/verify_token', {}, { headers: { 'X-Setup-Token': token } })
    return true
  } catch {
    return false
  }
}

export async function getSetupPrefill(): Promise<SetupPrefill> {
  const res = await client.get('/setup/api/prefill')
  return res.data as SetupPrefill
}

export async function testMysql(payload: SetupApplyPayload['mysql']): Promise<SetupCheckResult> {
  try {
    const res = await client.post('/setup/api/test_mysql', payload)
    return res.data as SetupCheckResult
  } catch (error) {
    return { ok: false, msg: axiosMessage(error) }
  }
}

export async function testRedis(payload: SetupApplyPayload['redis']): Promise<SetupCheckResult> {
  try {
    const res = await client.post('/setup/api/test_redis', payload)
    return res.data as SetupCheckResult
  } catch (error) {
    return { ok: false, msg: axiosMessage(error) }
  }
}

export async function testSmtp(payload: NonNullable<SetupApplyPayload['mail']> & { send_to?: string }): Promise<SetupCheckResult> {
  try {
    const res = await client.post('/setup/api/test_smtp', payload)
    return res.data as SetupCheckResult
  } catch (error) {
    return { ok: false, msg: axiosMessage(error) }
  }
}

export async function applySetup(payload: SetupApplyPayload): Promise<SetupApplyResult> {
  try {
    const res = await client.post('/setup/api/apply', payload)
    return res.data as SetupApplyResult
  } catch (error) {
    const data = axios.isAxiosError(error) ? error.response?.data as SetupApplyResult | undefined : undefined
    return data && typeof data === 'object'
      ? { ok: false, msg: data.msg || axiosMessage(error), steps: data.steps }
      : { ok: false, msg: axiosMessage(error) }
  }
}

function axiosMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const msg = (error.response?.data as { msg?: string } | undefined)?.msg
    if (msg) return msg
    if (error.response) return t('common.http.requestFailed', { status: error.response.status })
    return t('common.http.unreachable')
  }
  return error instanceof Error ? error.message : t('common.status.unknown')
}
