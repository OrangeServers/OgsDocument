// =============================================================================
// Vite 配置 (ti3-TS: 迁移到 TS)
// =============================================================================
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 后端地址，开发环境从 .env.development 读取
// REVIEW-14 P1-5: 默认值清空（防硬编码内网 IP 泄露后端拓扑）
//   缺失或不合法时直接报错，强制开发者配置 .env.development
// 注意：vite.config.ts 在 esbuild 阶段加载，process.env 不会自动包含 .env 文件内容，
//       必须用 Vite 自带的 loadEnv() 显式读取。
const env = loadEnv('development', process.cwd(), '')
const API_SERVER: string = env.VITE_API_TARGET || ''
if (!API_SERVER) {
  throw new Error(
    '[vite.config.ts] VITE_API_TARGET 未配置！\n' +
    '  请在 pycharm_ogsfront/.env.development 中设置：\n' +
    '    VITE_API_TARGET=http://your-backend-host:port\n' +
    '  示例：VITE_API_TARGET=http://127.0.0.1:28000'
  )
}
if (!/^https?:\/\//i.test(API_SERVER)) {
  throw new Error(
    '[vite.config.ts] VITE_API_TARGET 格式不正确，必须以 http:// 或 https:// 开头：' + API_SERVER
  )
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: {
    port: 5173,
    proxy: {
      // 只代理 HTTP 请求，WebSocket 开发环境直连后端（Vite 8.x 的 WS 代理不转发升级请求）
      '^/local(?:/|$)': {
        target: API_SERVER,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            const ip = (req.socket?.remoteAddress || '127.0.0.1').replace('::ffff:', '')
            proxyReq.setHeader('X-Real-IP', ip)
            proxyReq.setHeader('X-Forwarded-For', ip)
          })
          proxy.on('error', (err, req) => {
            console.error('[Proxy Error]', req.method, req.url, err.message)
          })
        }
      },
      '^/server(?:/|$)': {
        target: API_SERVER,
        changeOrigin: true
      },
      '^/account(?:/|$)': {
        target: API_SERVER,
        changeOrigin: true
      },
      '^/mail(?:/|$)': {
        target: API_SERVER,
        changeOrigin: true
      },
      '^/auth(?:/|$)': {
        target: API_SERVER,
        changeOrigin: true
      },
      '^/ai(?:/|$)': {
        target: API_SERVER,
        changeOrigin: true
      },
      // SETUP-WIZARD: 首次部署向导 API
      '^/setup/api(?:/|$)': {
        target: API_SERVER,
        changeOrigin: true
      },
    }
  }
})
