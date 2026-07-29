// =====================================================================
// REV35-L4: danger 工具 — 检测危险命令 (rm -rf / dd / mkfs / drop table ...)
// ti3-TS: 加类型注解
// =====================================================================

/**
 * 判断命令是否为高危操作
 * @param cmd 命令字符串 (可空)
 * @returns 是否为危险命令
 */
export function isDangerCommand(cmd: string | null | undefined): boolean {
  if (!cmd) return false
  const c = String(cmd).toLowerCase()
  return /\brm\s+-rf?\s+\//.test(c)
      || /\bdd\s+if=/.test(c)
      || /\bmkfs/.test(c)
      || /\bformat\s+[a-z]:/i.test(cmd)
      || /\bdrop\s+(database|table|schema)\b/.test(c)
      || /\bshutdown\b|\breboot\b|\bpoweroff\b|\binit\s+0\b|\binit\s+6\b/.test(c)
      || /:(){\s*:\|:&\s*};:/.test(cmd)
      || /\bchmod\s+-r\s+777\s+\//.test(c)
      || /\bfdisk\s+\/dev\/sd[a-z]/.test(c)
}
