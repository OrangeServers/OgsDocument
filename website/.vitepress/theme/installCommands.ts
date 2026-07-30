export type InstallRoute = 'global' | 'china'

export const installCommands: Record<InstallRoute, string> = {
  global:
    'set -o pipefail; curl -fsSL https://github.com/OrangeServers/OrangeServer/releases/download/v1.0.3/bootstrap-compose.sh | sudo bash -s -- --version v1.0.3',
  china:
    'set -o pipefail; curl -fsSL https://gitee.com/orangeservers/OrangeServer/raw/v1.0.3/ops/bootstrap-compose-cn.sh | sudo bash -s -- --version v1.0.3',
}
