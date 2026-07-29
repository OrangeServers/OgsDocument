<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useData, withBase } from 'vitepress'

const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')

const shots = computed(() =>
  isZh.value
    ? [
        { src: '/screens/dashboard.png', cap: '仪表盘 · 实时总览与 AI 执行统计' },
        { src: '/screens/ai-agent.png', cap: 'AI 运维 · 需审批的批量操作' },
        { src: '/screens/assets.png', cap: '资产中心 · 分组、标签与系统用户' },
        { src: '/screens/batch-ops.png', cap: '批量命令 · 逐资产结果与审计' },
        { src: '/screens/web-terminal.png', cap: 'Web 终端 · 浏览器 SSH 与会话录制' },
        { src: '/screens/settings-ai.png', cap: 'AI 服务商配置 · 密钥加密存储' },
      ]
    : [
        { src: '/screens/dashboard.png', cap: 'Dashboard · live overview and AI execution stats' },
        { src: '/screens/ai-agent.png', cap: 'AI operations · approval-gated batch actions' },
        { src: '/screens/assets.png', cap: 'Assets · groups, tags and system accounts' },
        { src: '/screens/batch-ops.png', cap: 'Batch commands · per-asset results and audit' },
        { src: '/screens/web-terminal.png', cap: 'Web terminal · browser SSH with session recording' },
        { src: '/screens/settings-ai.png', cap: 'AI providers · keys encrypted at rest' },
      ]
)

const active = ref<number | null>(null)
const root = ref<HTMLElement>()
const armed = ref(false)
const shown = ref(false)

function open(i: number) {
  active.value = i
}
function close() {
  active.value = null
}
function step(d: number) {
  if (active.value === null) return
  const n = shots.value.length
  active.value = (active.value + d + n) % n
}
function onKey(e: KeyboardEvent) {
  if (active.value === null) return
  if (e.key === 'Escape') close()
  if (e.key === 'ArrowLeft') step(-1)
  if (e.key === 'ArrowRight') step(1)
}

watch(active, (v) => {
  document.body.style.overflow = v === null ? '' : 'hidden'
})

onMounted(() => {
  window.addEventListener('keydown', onKey)
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
    { threshold: 0.08 }
  )
  ob.observe(root.value)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
</script>

<template>
  <section ref="root" class="gallery" :class="{ armed, shown }">
    <h2 class="g-title">{{ isZh ? '产品实景' : 'See it running' }}</h2>
    <p class="g-sub">
      {{
        isZh
          ? '全部是真实界面，没有渲染图。点击查看大图。'
          : 'Real product screens, no mockups. Click to zoom.'
      }}
    </p>
    <div class="g-grid">
      <figure
        v-for="(s, i) in shots"
        :key="s.src"
        class="g-item"
        :style="{ transitionDelay: shown ? `${i * 70}ms` : '0ms' }"
        tabindex="0"
        role="button"
        :aria-label="s.cap"
        @click="open(i)"
        @keydown.enter="open(i)"
      >
        <img :src="withBase(s.src)" :alt="s.cap" loading="lazy" />
        <figcaption>{{ s.cap }}</figcaption>
      </figure>
    </div>

    <Teleport to="body">
      <div v-if="active !== null" class="lightbox" @click="close">
        <button class="lb-close" :aria-label="isZh ? '关闭' : 'Close'" @click="close">✕</button>
        <button class="lb-nav prev" :aria-label="isZh ? '上一张' : 'Previous'" @click.stop="step(-1)">‹</button>
        <figure class="lb-figure" @click.stop>
          <img :src="withBase(shots[active].src)" :alt="shots[active].cap" />
          <figcaption>{{ shots[active].cap }}</figcaption>
        </figure>
        <button class="lb-nav next" :aria-label="isZh ? '下一张' : 'Next'" @click.stop="step(1)">›</button>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.gallery {
  max-width: 1152px;
  margin: 0 auto;
  padding: 48px 24px 24px;
}
.g-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0 0 8px;
  padding: 0;
  border: none;
  text-align: center;
  color: var(--vp-c-text-1);
}
.g-sub {
  text-align: center;
  font-size: 14px;
  color: var(--vp-c-text-2);
  margin: 0 0 32px;
}
.g-grid {
  display: grid;
  gap: 20px;
  grid-template-columns: 1fr;
}
@media (min-width: 768px) {
  .g-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
.g-item {
  margin: 0;
  cursor: zoom-in;
  transition:
    opacity 0.55s ease,
    transform 0.55s ease;
}
.armed .g-item {
  opacity: 0;
  transform: translateY(16px);
}
.armed.shown .g-item {
  opacity: 1;
  transform: none;
}
.g-item img {
  display: block;
  width: 100%;
  border-radius: 10px;
  border: 1px solid var(--vp-c-divider);
  box-shadow: 0 6px 24px -6px rgba(0, 0, 0, 0.14);
  transition:
    transform 0.3s ease,
    box-shadow 0.3s ease;
}
.g-item:hover img,
.g-item:focus-visible img {
  transform: translateY(-4px);
  box-shadow: 0 16px 40px -8px rgba(230, 119, 0, 0.22);
  border-color: var(--vp-c-brand-3);
}
.g-item figcaption {
  margin-top: 10px;
  text-align: center;
  font-size: 13px;
  color: var(--vp-c-text-2);
}

.lightbox {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(10, 10, 12, 0.82);
  backdrop-filter: blur(6px);
  animation: lb-in 0.2s ease both;
  padding: 24px;
}
@keyframes lb-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
.lb-figure {
  margin: 0;
  max-width: min(1200px, 86vw);
  animation: lb-zoom 0.25s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}
@keyframes lb-zoom {
  from {
    opacity: 0;
    transform: scale(0.96);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.lb-figure img {
  display: block;
  max-width: 100%;
  max-height: 78vh;
  border-radius: 10px;
  box-shadow: 0 40px 120px rgba(0, 0, 0, 0.6);
}
.lb-figure figcaption {
  margin-top: 14px;
  text-align: center;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.75);
}
.lb-close {
  position: absolute;
  top: 18px;
  right: 22px;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  font-size: 16px;
  cursor: pointer;
  transition: background 0.2s;
}
.lb-close:hover {
  background: rgba(255, 255, 255, 0.22);
}
.lb-nav {
  flex: none;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.2s;
}
.lb-nav:hover {
  background: rgba(247, 103, 7, 0.75);
}
@media (max-width: 640px) {
  .lb-nav {
    display: none;
  }
}
</style>
