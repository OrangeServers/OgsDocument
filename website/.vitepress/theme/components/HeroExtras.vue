<script setup lang="ts">
import { computed, ref } from 'vue'
import { useData } from 'vitepress'

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
</script>

<template>
  <div class="hero-extras">
    <div class="badges">
      <a
        href="https://github.com/OrangeServers/OrangeServer"
        target="_blank"
        rel="noopener"
      >
        <img
          src="https://img.shields.io/badge/GitHub-OrangeServers%2FOrangeServer-16181d?logo=github"
          alt="GitHub repository"
          height="20"
        />
      </a>
      <a
        href="https://github.com/OrangeServers/OrangeServer/blob/main/LICENSE"
        target="_blank"
        rel="noopener"
      >
        <img
          src="https://img.shields.io/badge/License-Apache--2.0-f76707?labelColor=16181d"
          alt="License Apache-2.0"
          height="20"
        />
      </a>
    </div>
    <div class="install">
      <pre><span class="ps">$</span> git clone https://github.com/OrangeServers/OrangeServer.git
<span class="ps">$</span> cd OrangeServer && make docker-up</pre>
      <button
        class="copy"
        :class="{ ok: copied }"
        :title="isZh ? '复制' : 'Copy'"
        :aria-label="isZh ? '复制安装命令' : 'Copy install commands'"
        @click="copy"
      >
        <svg
          v-if="!copied"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
          <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
        </svg>
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.hero-extras {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 22px;
  align-items: flex-start;
}
.badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.badges a {
  display: inline-flex;
  line-height: 0;
}
.badges img {
  border-radius: 4px;
}
.install {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #16181d;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 10px;
  padding: 10px 8px 10px 16px;
  max-width: 100%;
  box-shadow: 0 8px 28px -10px rgba(20, 16, 10, 0.4);
}
.install pre {
  margin: 0;
  font-family: ui-monospace, 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.8;
  color: #d4d7de;
  white-space: pre;
  overflow-x: auto;
}
.install .ps {
  color: #f76707;
  font-weight: 700;
}
.copy {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #8b8f99;
  cursor: pointer;
  transition:
    background 0.2s,
    color 0.2s;
}
.copy:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #e8eaee;
}
.copy.ok {
  color: #40c057;
}
.copy svg {
  width: 15px;
  height: 15px;
}

@media (max-width: 639px) {
  .hero-extras {
    align-items: center;
  }
  .install pre {
    font-size: 11px;
  }
}
</style>
