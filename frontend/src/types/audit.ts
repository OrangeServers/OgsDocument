// =============================================================================
// OrangeServer Frontend - 审计日志类型
// ti3-TS: 对齐后端 t_log_operate / t_log_login / t_log_command
// =============================================================================

import type { IsoTimestamp } from './common'

/** 登录日志 */
export interface LoginLog {
  id: number
  username: string
  ip: string
  user_agent?: string
  status: 'success' | 'failure' | string
  fail_reason?: string
  login_at: IsoTimestamp
  logout_at?: IsoTimestamp
}

/** 命令执行日志 (WebSSH / 批量命令 / 批量脚本) */
export interface ExecLog {
  id: number
  username: string
  host_id?: number
  host_name?: string
  command: string
  exit_code?: number
  stdout?: string
  stderr?: string
  start_at: IsoTimestamp
  end_at?: IsoTimestamp
  duration?: number
  source: 'webssh' | 'batch_command' | 'batch_script' | 'cron' | string
  status: 'success' | 'failure' | 'running' | string
}

/** 操作日志 (CRUD / 鉴权变更) */
export interface OpLog {
  id: number
  username: string
  action: string         // e.g. 'user.create' / 'host.update'
  target_type?: string   // e.g. 'user' / 'host' / 'cron'
  target_id?: number
  target_name?: string
  detail?: string        // JSON 序列化
  ip?: string
  created_at: IsoTimestamp
  status: 'success' | 'failure' | string
}

/** IP 统计 top-N */
export interface IpTopItem {
  ip: string
  count: number
  last_seen?: IsoTimestamp
}
