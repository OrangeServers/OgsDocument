// =============================================================================
// OrangeServer Frontend - WebSSH / 终端类型
// ti3-TS: 终端实例/Tab/会话抽象, 避免 xterm 内部 mutation 触发响应式
// =============================================================================

import type { IsoTimestamp, OnOff } from './common'

/** WebSSH Tab (前端 store.terminal.tabs) */
export interface TerminalTab {
  id: string              // UUID, 前端生成
  host: TerminalHost      // 关联主机
  sysUser: TerminalSysUser
  status: 'connecting' | 'connected' | 'closed' | 'failed' | string
  createdAt: IsoTimestamp
  title: string           // 显示用 (e.g. "host@user")
}

/** 终端关联的最小化 Host (避免引用整个 Host 大对象) */
export interface TerminalHost {
  id: number
  name: string
  host: string
  port: number
  os_type?: string
}

/** 终端关联的最小化 SysUser */
export interface TerminalSysUser {
  id: number
  name: string
  username: string
  auth_type: 'password' | 'key'
  key_id?: number
}

/** WebSocket 会话描述 (前端视图用, 真实 terminal 在 store.termPool) */
export interface SshSession {
  id: string
  tabId: string
  url: string             // ws://.../ssh/<id>
  status: TerminalTab['status']
  openedAt: IsoTimestamp
  closedAt?: IsoTimestamp
}

/** SFTP 远程文件 (简化) */
export interface SftpFile {
  name: string
  path: string
  is_dir: boolean
  size: number
  mtime: IsoTimestamp
  mode: string            // e.g. '-rw-r--r--'
}

/** SFTP 浏览目录响应 */
export interface SftpDirListing {
  path: string
  cwd: string
  files: SftpFile[]
}
