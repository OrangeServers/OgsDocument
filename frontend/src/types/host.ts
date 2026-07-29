// =============================================================================
// OrangeServer Frontend - 资产 (Host/Group) 类型
// ti3-TS: 对齐后端 t_acc_host / t_acc_group / t_auth_host
// =============================================================================

import type { IsoTimestamp, NumStr, UserRole } from './common'

/** 资产 (主机) 实体 */
export interface Host {
  id: number
  name: string
  host: string
  port: number
  user: string
  group_id: number | null
  group_name?: string
  desc?: string
  is_active?: boolean
  tags?: string[]
  os_type?: 'linux' | 'windows' | 'macos' | string
  created_at?: IsoTimestamp
  updated_at?: IsoTimestamp
}

/** 资产组 */
export interface HostGroup {
  id: number
  name: string
  parent_id?: number | null
  description?: string
  host_count?: number
  children?: HostGroup[]
  hosts?: Host[]
  created_at?: IsoTimestamp
}

/** 资产树节点 (前端组装: 组 + 主机) */
export interface AssetTreeNode {
  id: string // `g_<id>` 或 `h_<id>`
  label: string
  type: 'group' | 'host'
  raw_id: number
  group_id?: number | null
  children?: AssetTreeNode[]
  isLeaf: boolean
}

/** 主机新建/编辑表单 */
export interface HostForm {
  id?: number
  name: string
  host: string
  port: number
  user: string
  group_id: number | null
  desc?: string
  os_type?: string
  tags?: string[]
  password?: string // 临时密码, 用于首次注入
}

/** 系统用户 (ssh 登录用) */
export interface SysUser {
  id: number
  name: string
  username: string
  auth_type: 'password' | 'key'
  key_id?: number
  desc?: string
}

/** 主机-用户-组 关联 (auth matrix) */
export interface HostAuthBinding {
  host_id: number
  sys_user_id: number
  group_id: number
  binding_id?: number
  created_at?: IsoTimestamp
}
