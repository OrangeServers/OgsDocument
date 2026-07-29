// =============================================================================
// OrangeServer Frontend - 系统设置类型
// ti3-TS: 对齐后端 t_sys_settings
// =============================================================================

import type { OnOff } from './common'

/** 主题配色 key */
export type ThemeKey = 'orange' | 'blue' | 'green' | 'dark' | string

/** 主题完整配置 (含渐变色) */
export interface Theme {
  key: ThemeKey
  headerBg: string
  sidebarBg: string
  label: string
}

/** 系统设置 (前端 store.settings 镜像后端 t_sys_settings) */
export interface AppSettings {
  login_time: number                 // 登录态有效期 (分钟)
  register_status: OnOff             // 是否开放注册
  color_matching: ThemeKey           // 主题配色 key
  login_fail_limit: number           // 登录失败锁定阈值
  lock_duration: number              // 锁定时长 (分钟)
  password_expire_days: number       // 密码有效期 (天)
  mfa_enabled: OnOff                 // 是否启用 MFA
  password_complexity: OnOff         // 强制密码复杂度
  ssh_timeout: number                // SSH 连接超时 (秒)
  terminal_scrollback: number        // 终端回滚行数
  session_record: OnOff              // 会话录像
  max_concurrent_sessions: number    // 最大并发会话
  log_retention_days: number         // 日志保留天数
  command_audit: OnOff               // 命令审计
  upload_size_limit: number          // 上传文件大小 (MB)
  allow_upload: OnOff
  allow_download: OnOff
  mail_notify: OnOff                 // 邮件告警通知
  alert_email: string
  system_name: string                // 系统名
  login_notice: string               // 登录页公告
  language: string                   // I18N: 界面语言 zh-CN | en-US（服务端权威）
}

/** 主题键 (从 localStorage 读, 用于主题切换) */
export const THEME_KEY_STORAGE = 'ogs_theme'
