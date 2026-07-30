<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useData, withBase } from 'vitepress'
import { installCommands, type InstallRoute } from '../installCommands'

const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')

const copied = ref(false)
const route = ref<InstallRoute>('global')
const cmd = computed(() => installCommands[route.value])
const routeSummary = computed(() => {
  if (route.value === 'china') {
    return isZh.value
      ? '从 Gitee 获取固定版本脚本，后端使用腾讯云 TCR，公共依赖镜像走国内线路。'
      : 'Uses the fixed-tag Gitee launcher, Tencent Cloud TCR, and mainland mirrors for public images.'
  }
  return isZh.value
    ? '从 GitHub Release 获取并校验固定版本部署包，后端使用 GHCR。'
    : 'Downloads and verifies the fixed-version bundle from GitHub Release and uses GHCR.'
})

watch(
  isZh,
  (value) => {
    route.value = value ? 'china' : 'global'
    copied.value = false
  },
  { immediate: true }
)
watch(route, () => {
  copied.value = false
})

async function copy() {
  try {
    await navigator.clipboard.writeText(cmd.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1600)
  } catch {
    /* clipboard unavailable */
  }
}

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
    { threshold: 0.2 }
  )
  ob.observe(root.value)
})
</script>

<template>
  <section ref="root" class="home-cta" :class="{ armed, shown }">
    <div class="cta-glow"></div>
    <div class="cta-inner">
      <h2 class="cta-title">{{ isZh ? '从全新安装开始' : 'Start from a fresh install' }}</h2>
      <p class="cta-sub">
        {{
          isZh
            ? '选择适合服务器网络的线路；首次网页向导创建管理员并完成初始化。'
            : 'Choose the route that fits the server network; the first-run wizard creates the administrator and completes setup.'
        }}
      </p>
      <div
        class="route-switch"
        role="group"
        :aria-label="isZh ? '选择部署线路' : 'Choose a deployment route'"
      >
        <button
          :class="{ active: route === 'global' }"
          :aria-pressed="route === 'global'"
          @click="route = 'global'"
        >
          {{ isZh ? '全球线路' : 'Global' }}
        </button>
        <button
          :class="{ active: route === 'china' }"
          :aria-pressed="route === 'china'"
          @click="route = 'china'"
        >
          {{ isZh ? '中国大陆' : 'Mainland China' }}
        </button>
      </div>
      <p class="route-summary">{{ routeSummary }}</p>
      <div class="cta-cmd">
        <pre><span class="ps">$</span> {{ cmd }}</pre>
        <button
          class="copy-btn"
          :class="{ ok: copied }"
          aria-live="polite"
          @click="copy"
        >
          {{ copied ? (isZh ? '已复制' : 'Copied') : isZh ? '复制' : 'Copy' }}
        </button>
      </div>
      <div class="cta-actions">
        <a
          class="cta-btn primary"
          :href="withBase(isZh ? '/zh/guide/getting-started.html' : '/guide/getting-started.html')"
        >
          {{ isZh ? '阅读快速开始' : 'Read the quickstart' }}
        </a>
        <a
          class="cta-btn ghost"
          href="https://github.com/OrangeServers/OrangeServer"
          target="_blank"
          rel="noopener"
        >
          GitHub →
        </a>
      </div>
    </div>
  </section>
</template>

<style scoped>
.home-cta {
  position: relative;
  max-width: 1152px;
  margin: 56px auto 0;
  padding: 0 24px;
  transition:
    opacity 0.6s ease,
    transform 0.6s ease;
}
.home-cta.armed {
  opacity: 0;
  transform: translateY(18px);
}
.home-cta.armed.shown {
  opacity: 1;
  transform: none;
}
.cta-inner {
  position: relative;
  background: #16181d;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 18px;
  padding: 52px 32px 48px;
  text-align: center;
  overflow: hidden;
}
.cta-glow {
  position: absolute;
  inset: 0;
  margin: 0 24px;
  border-radius: 18px;
  background: radial-gradient(ellipse 60% 80% at 50% 120%, rgba(247, 103, 7, 0.35), transparent 70%);
  pointer-events: none;
}
.cta-title {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #f2f3f5;
  margin: 0 0 12px;
  padding: 0;
  border: none;
}
.cta-sub {
  font-size: 15px;
  color: #9aa0ab;
  margin: 0 auto 30px;
  max-width: 520px;
  line-height: 1.7;
}
.route-switch {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.3);
}
.route-switch button {
  border: 0;
  border-radius: 999px;
  padding: 7px 15px;
  background: transparent;
  color: #9aa0ab;
  font-size: 12.5px;
  font-weight: 650;
  cursor: pointer;
}
.route-switch button:hover {
  color: #f2f3f5;
}
.route-switch button.active {
  background: #c2410c;
  color: #fff;
  box-shadow: 0 3px 12px rgba(247, 103, 7, 0.35);
}
.route-switch button:focus-visible {
  outline: 2px solid #ffa94d;
  outline-offset: 2px;
}
.route-summary {
  min-height: 22px;
  margin: 12px auto 16px;
  max-width: 620px;
  color: #aeb3bd;
  font-size: 12.5px;
  line-height: 1.6;
}
.cta-cmd {
  position: relative;
  max-width: 640px;
  margin: 0 auto 30px;
  background: rgba(0, 0, 0, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 16px 90px 16px 20px;
  text-align: left;
}
.cta-cmd pre {
  margin: 0;
  font-family: ui-monospace, 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  line-height: 1.9;
  color: #d4d7de;
  white-space: pre;
  overflow-x: auto;
}
.cta-cmd .ps {
  color: #f76707;
  font-weight: 700;
}
.copy-btn {
  position: absolute;
  top: 50%;
  right: 14px;
  transform: translateY(-50%);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.06);
  color: #c9ced6;
  font-size: 12.5px;
  font-weight: 600;
  padding: 7px 14px;
  cursor: pointer;
  transition:
    background 0.2s,
    color 0.2s,
    border-color 0.2s;
}
.copy-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}
.copy-btn.ok {
  border-color: rgba(64, 192, 87, 0.6);
  color: #69db7c;
}
.cta-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
.cta-btn {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 11px 26px;
  font-size: 14.5px;
  font-weight: 600;
  text-decoration: none;
  transition:
    background 0.2s,
    border-color 0.2s,
    transform 0.2s;
}
.cta-btn.primary {
  background: #f76707;
  color: #fff;
  box-shadow: 0 6px 24px -4px rgba(247, 103, 7, 0.55);
}
.cta-btn.primary:hover {
  background: #e8590c;
  transform: translateY(-1px);
}
.cta-btn.ghost {
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #d4d7de;
}
.cta-btn.ghost:hover {
  border-color: rgba(255, 255, 255, 0.45);
  color: #fff;
}
@media (max-width: 640px) {
  .cta-inner {
    padding: 40px 20px 36px;
  }
  .cta-title {
    font-size: 24px;
  }
  .cta-cmd {
    padding: 14px 16px;
  }
  .route-switch button {
    padding-inline: 11px;
  }
  .cta-cmd pre {
    font-size: 11.5px;
  }
  .copy-btn {
    position: static;
    transform: none;
    margin-top: 12px;
  }
}
</style>
