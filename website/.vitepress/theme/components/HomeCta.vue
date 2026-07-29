<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useData, withBase } from 'vitepress'

const { lang } = useData()
const isZh = computed(() => lang.value === 'zh-CN')

const copied = ref(false)
const cmd =
  'git clone https://github.com/OrangeServers/OrangeServer.git\ncd OrangeServer && make docker-up'

async function copy() {
  try {
    await navigator.clipboard.writeText(cmd)
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
      <h2 class="cta-title">{{ isZh ? '60 秒跑起来' : 'Up and running in 60 seconds' }}</h2>
      <p class="cta-sub">
        {{
          isZh
            ? 'Docker Compose 一键起栈，首次启动由网页向导完成建库与初始化。'
            : 'One Docker Compose command. The first-run web wizard handles schema and setup.'
        }}
      </p>
      <div class="cta-cmd">
        <pre><span class="ps">$</span> git clone https://github.com/OrangeServers/OrangeServer.git
<span class="ps">$</span> cd OrangeServer && make docker-up</pre>
        <button class="copy-btn" :class="{ ok: copied }" @click="copy">
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
