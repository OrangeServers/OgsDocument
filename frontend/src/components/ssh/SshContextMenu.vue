<!--
  REV33-M1: SshContextMenu - 通用右键菜单
  ----------------------------------------------------------------
  抽离 WebSSHCore 的两类右键菜单：
    1. 资产树右键菜单（连接、SFTP、复制、复制名、复制 SSH、详情）
    2. Tab 右键菜单（切换、复制、关闭、关闭其他、关闭全部）

  API：
    <SshContextMenu
      :visible="treeCtx.visible"
      :x="treeCtx.x"
      :y="treeCtx.y"
      @close="treeCtx.visible = false"
    >
      <SshContextItem icon="VideoPlay" @click="ctxAction('connect')">连接终端</SshContextItem>
      <SshContextItem icon="FolderOpened" @click="ctxAction('sftp')">仅打开 SFTP</SshContextItem>
      <SshContextDivider />
      <SshContextItem icon="CopyDocument" danger @click="ctxAction('copy-name')">复制主机名</SshContextItem>
    </SshContextMenu>

  特点：
    - 菜单挂在 body（fixed 定位），scoped 不生效，CSS 提到全局
    - 边界检查：超出视口自动反向（left/right, top/bottom）
    - 自动关闭：点外部 / Esc
-->
<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="host-ctx-menu"
      :style="{ left: x + 'px', top: y + 'px' }"
      @click.stop
    >
      <slot />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps<{
  visible?: boolean
  x?: number
  y?: number
  /** 视口边距（避免菜单超出） */
  margin?: number
}>()
const emit = defineEmits<{
  (e: 'close'): void
}>()

function onDocClick(): void { if (props.visible) emit('close') }
function onEsc(e: KeyboardEvent): void { if (e.key === 'Escape' && props.visible) emit('close') }

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onEsc)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onEsc)
})

// visible 变化时若 true 可在此插入定位修正（边界检查由调用方传入 x/y 时做）
watch(() => props.visible, v => {
  if (v) {
    // 自动修正：菜单大小约 200-220px，提前预留空间
    if (typeof window !== 'undefined') {
      const el = document.querySelector('.host-ctx-menu') as HTMLElement | null
      if (el) {
        const rect = el.getBoundingClientRect()
        if (rect.right > window.innerWidth - (props.margin ?? 8)) {
          el.style.left = Math.max(props.margin ?? 8, window.innerWidth - rect.width - (props.margin ?? 8)) + 'px'
        }
        if (rect.bottom > window.innerHeight - (props.margin ?? 8)) {
          el.style.top = Math.max(props.margin ?? 8, window.innerHeight - rect.height - (props.margin ?? 8)) + 'px'
        }
      }
    }
  }
})
</script>

<style>
/* 全局样式（Teleport 到 body） */
.host-ctx-menu {
  position: fixed; z-index: 9999;
  background: #1E1E2E; border: 1px solid #313244; border-radius: 8px;
  padding: 4px 0; min-width: 200px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  font-family: var(--ogs-font-sans);
}
.host-ctx-menu .ctx-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; font-size: 12.5px; color: rgba(255,255,255,0.8);
  cursor: pointer; transition: all 0.12s;
}
.host-ctx-menu .ctx-item:hover {
  background: rgba(251,146,60,0.12); color: #FB923C;
}
.host-ctx-menu .ctx-item.is-danger { color: #F38BA8; }
.host-ctx-menu .ctx-item.is-danger:hover {
  background: rgba(243,139,168,0.12); color: #F38BA8;
}
.host-ctx-menu .ctx-divider {
  height: 1px; background: #313244; margin: 4px 0;
}
</style>