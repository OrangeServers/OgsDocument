<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useData } from 'vitepress'

const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')

const icons: Record<string, string> = {
  server:
    '<rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/>',
  terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
  zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  'shield-check':
    '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  'scan-search':
    '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/><path d="m16 16-1.9-1.9"/>',
  'clipboard-list':
    '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/>',
  compass:
    '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
  languages:
    '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
}

const features = computed(() =>
  isZh.value
    ? [
        { icon: 'server', title: '资产与资产组', details: '在同一权限边界内管理主机、分组、标签和系统用户。' },
        { icon: 'terminal', title: 'Web 终端', details: '浏览器内建立 SSH 会话，支持多标签与完整会话记录。' },
        { icon: 'zap', title: '批量命令与脚本', details: '对最多 50 台已授权资产批量执行，逐资产展示结果并记录审计日志。' },
        { icon: 'shield-check', title: '需审批的 AI 运维', details: '模型只能调用后端声明的结构化工具，批量操作永远需要人工审批。' },
        { icon: 'scan-search', title: '只读 AI 诊断', details: '服务端固定的 Linux/Docker 诊断档案，证据脱敏、限长、加密保存且可引用。' },
        { icon: 'clipboard-list', title: '完整审计追踪', details: '登录、命令、平台操作全记录——一切可追溯、可告警。' },
        { icon: 'compass', title: '首次部署向导', details: '零配置启动进入引导页而非崩溃循环，网页向导完成建库与管理员创建。' },
        { icon: 'languages', title: '中英双语界面', details: '全站中英双语，即时切换并持久化到服务端。' },
      ]
    : [
        { icon: 'server', title: 'Assets and groups', details: 'Manage hosts, groups, tags, and system accounts behind one permission boundary.' },
        { icon: 'terminal', title: 'Web terminal', details: 'Browser SSH sessions with tabs and full session recording.' },
        { icon: 'zap', title: 'Batch commands and scripts', details: 'Run across up to 50 authorized assets with per-asset results and audit logs.' },
        { icon: 'shield-check', title: 'Approval-gated AI operations', details: 'The model can only call declared structured tools. Batch actions always require human approval.' },
        { icon: 'scan-search', title: 'Read-only AI diagnostics', details: 'Fixed server-side Linux/Docker diagnostic profiles with encrypted, citable evidence.' },
        { icon: 'clipboard-list', title: 'Full audit trail', details: 'Login, command, and platform operation records — everything traceable and alertable.' },
        { icon: 'compass', title: 'First-run setup wizard', details: 'Boot without configuration and get a guided web setup instead of a crash loop.' },
        { icon: 'languages', title: 'Bilingual UI', details: 'Full Chinese/English interface, switchable instantly and persisted server-side.' },
      ]
)

const root = ref<HTMLElement>()
const armed = ref(false)
const shown = ref(false)

onMounted(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduced || !('IntersectionObserver' in window) || !root.value) return
  armed.value = true
  const ob = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        shown.value = true
        ob.disconnect()
      }
    },
    { threshold: 0.12 }
  )
  ob.observe(root.value)
})
</script>

<template>
  <div ref="root" class="features-grid" :class="{ armed, shown }">
    <div
      v-for="(f, i) in features"
      :key="f.title"
      class="feature-card"
      :style="{ transitionDelay: shown ? `${i * 55}ms` : '0ms' }"
    >
      <div class="icon-box">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          v-html="icons[f.icon]"
        ></svg>
      </div>
      <h3 class="fc-title">{{ f.title }}</h3>
      <p class="fc-details">{{ f.details }}</p>
    </div>
  </div>
</template>

<style scoped>
.features-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: 1fr;
  max-width: 1152px;
  margin: 0 auto;
  padding: 8px 24px 12px;
}
@media (min-width: 640px) {
  .features-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (min-width: 1024px) {
  .features-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
.feature-card {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 22px 20px;
  transition:
    opacity 0.5s ease,
    transform 0.5s ease,
    border-color 0.25s ease,
    box-shadow 0.25s ease;
}
.armed .feature-card {
  opacity: 0;
  transform: translateY(14px);
}
.armed.shown .feature-card {
  opacity: 1;
  transform: none;
}
.feature-card:hover {
  border-color: var(--vp-c-brand-2);
  transform: translateY(-3px);
  box-shadow: 0 10px 28px -8px rgba(230, 119, 0, 0.18);
  transition-delay: 0ms;
}
.icon-box {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-2);
  margin-bottom: 14px;
}
.icon-box svg {
  width: 20px;
  height: 20px;
}
.fc-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  margin: 0 0 6px;
  padding: 0;
  border: none;
  color: var(--vp-c-text-1);
}
.fc-details {
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--vp-c-text-2);
  margin: 0;
}
</style>
