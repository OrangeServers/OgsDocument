// =============================================================================
// OrangeServer Frontend - 认证/用户类型
// ti3-TS: 对齐后端 AccUser / AccGroup
// =============================================================================

import type { IsoTimestamp, NumStr, UserRole } from './common'

/** 用户实体 (与后端 t_acc_user 字段一致) */
export interface User {
  id: number
  username: string
  alias?: string
  email?: string
  role: UserRole
  avatar?: string
  is_active?: boolean
  is_locked?: boolean
  group_id?: number | null
  group_name?: string
  created_at?: IsoTimestamp
  updated_at?: IsoTimestamp
  last_login?: IsoTimestamp
}

/** 登录表单 */
export interface LoginForm {
  username: string
  password: string
  captcha?: string
  captcha_id?: string
}

/** 注册表单 */
export interface RegisterForm {
  username: string
  password: string
  password2: string
  email: string
  captcha?: string
  captcha_id?: string
}

/** 密码修改 */
export interface ChangePasswordForm {
  old_password: string
  new_password: string
  new_password2: string
}

/** 用户组 (对齐后端 t_acc_group) */
export interface UserGroup {
  id: number
  name: string
  description?: string
  role?: UserRole
  user_count?: number
  created_at?: IsoTimestamp
}

/** 简化的当前用户 (store 内存) */
export interface CurrentUser {
  username: string
  alias: string
  role: UserRole
  avatar: string
  /** 所属用户组 (可选, loadUserInfo 后回填) */
  group?: string
}

/** token 存储介质 (cookie / localStorage / 内存) */
export type TokenStorage = 'cookie' | 'localStorage' | 'memory'

/** 验证码响应 */
export interface CaptchaResponse {
  captcha_id: string
  captcha_img: string // base64
}
