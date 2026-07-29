// =============================================================================
// OrangeServer Frontend - 定时任务类型
// ti3-TS: 对齐后端 t_cron / t_cron_log
// =============================================================================

import type { IsoTimestamp, OnOff, UserRole } from './common'

/** 定时任务 (cron job) */
export interface CronJob {
  id: number
  name: string
  cron: string           // 5 位或 6 位 cron 表达式
  command: string
  host_ids: number[]     // 目标主机 ID 列表
  group_ids?: number[]   // 目标组 ID 列表
  is_active: OnOff
  desc?: string
  owner?: string
  created_at?: IsoTimestamp
  updated_at?: IsoTimestamp
  last_run_at?: IsoTimestamp
  last_status?: 'success' | 'failure' | 'running' | string
}

/** cron 任务表单 */
export interface CronForm {
  id?: number
  name: string
  cron: string
  command: string
  host_ids: number[]
  group_ids?: number[]
  is_active: OnOff
  desc?: string
}

/** cron 任务执行结果 (单主机) */
export interface CronResult {
  id: number
  job_id: number
  host_id: number
  host_name: string
  start_at: IsoTimestamp
  end_at?: IsoTimestamp
  duration?: number      // 秒
  exit_code?: number
  stdout?: string
  stderr?: string
  status: 'pending' | 'running' | 'success' | 'failure'
}

/** cron 表达式下次执行时间预测 */
export interface CronNextRun {
  cron: string
  next_runs: IsoTimestamp[] // 接下来 N 次执行时间
}
