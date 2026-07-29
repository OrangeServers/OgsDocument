/**
 * 系统凭据选择记忆（WebSSHCore 终端 / FileTransfer SFTP 共用）
 *
 * 语义：选择即记忆 —— 用户在下拉中选中某凭据即写入 localStorage；
 * 恢复时若记忆值已不在凭据列表中（被删除/改名），fallback 到列表第一个。
 */

const LAST_SYS_USER_KEY = 'ogs:last-sys-user'

/** 从记忆恢复应选中的凭据；列表为空返回 '' */
export function restoreSysUser(users: string[]): string {
  if (!users.length) return ''
  const last = localStorage.getItem(LAST_SYS_USER_KEY)
  return last && users.includes(last) ? last : users[0]
}

/** 记忆当前选中凭据（空值不写入） */
export function rememberSysUser(user: string): void {
  if (user) localStorage.setItem(LAST_SYS_USER_KEY, user)
}
