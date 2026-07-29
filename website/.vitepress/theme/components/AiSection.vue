<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useData, withBase } from 'vitepress'

const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')

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
    { threshold: 0.25 }
  )
  ob.observe(root.value)
})
</script>

<template>
  <section ref="root" class="ai-section" :class="{ armed, shown }">
    <p class="eyebrow">{{ isZh ? '设计原则' : 'Design principle' }}</p>
    <h2 class="ai-title">
      {{ isZh ? 'AI 运维不是「把 Shell 交给模型」' : 'AI operations is not “handing the shell to a model”' }}
    </h2>
    <p class="ai-body">
      {{
        isZh
          ? '大模型只能调用后端声明的结构化工具：不能生成 SQL，不能拿到 Shell，不能执行任何未经人工审批的操作。诊断仅限服务端固定的只读档案，证据经过脱敏、限长，并加密落盘。'
          : 'The model can only call structured tools declared by the backend. It cannot run SQL, cannot open a shell, and cannot execute anything that has not been explicitly approved by a human. Diagnostics are limited to fixed read-only profiles whose evidence is sanitized, size-capped, and encrypted at rest.'
      }}
    </p>
    <div class="ai-chips">
      <span class="chip">{{ isZh ? '无 SQL' : 'No SQL' }}</span>
      <span class="chip">{{ isZh ? '无 Shell' : 'No shell' }}</span>
      <span class="chip">{{ isZh ? '必须人工审批' : 'Approval required' }}</span>
      <span class="chip">{{ isZh ? '证据可引用' : 'Citable evidence' }}</span>
    </div>
    <a class="ai-link" :href="withBase(isZh ? '/zh/guide/ai-ops.html' : '/guide/ai-ops.html')">
      {{ isZh ? '了解 AI 运维的完整边界' : 'Read the full AI operations boundary' }}
      <span class="arrow">→</span>
    </a>
  </section>
</template>

<style scoped>
.ai-section {
  max-width: 760px;
  margin: 0 auto;
  padding: 72px 24px 40px;
  text-align: center;
  transition:
    opacity 0.6s ease,
    transform 0.6s ease;
}
.ai-section.armed {
  opacity: 0;
  transform: translateY(16px);
}
.ai-section.armed.shown {
  opacity: 1;
  transform: none;
}
.eyebrow {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--vp-c-brand-2);
  margin: 0 0 14px;
}
.ai-title {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.3;
  letter-spacing: -0.01em;
  margin: 0 0 18px;
  padding: 0;
  border: none;
  color: var(--vp-c-text-1);
}
.ai-body {
  font-size: 16px;
  line-height: 1.8;
  color: var(--vp-c-text-2);
  margin: 0 0 24px;
}
.ai-chips {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 26px;
}
.chip {
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
  color: var(--vp-c-brand-2);
  background: var(--vp-c-brand-soft);
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 4px 13px;
}
.ai-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--vp-c-brand-2);
  text-decoration: none;
}
.ai-link .arrow {
  transition: transform 0.2s ease;
}
.ai-link:hover .arrow {
  transform: translateX(4px);
}
@media (max-width: 640px) {
  .ai-title {
    font-size: 24px;
  }
}
</style>
