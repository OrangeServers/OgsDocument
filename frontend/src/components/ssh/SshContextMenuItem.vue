<!--
  REV33-M1: SshContextMenuItem + SshContextDivider 子组件
  ----------------------------------------------------------------
  配套 SshContextMenu 使用：
    <SshContextItem icon="VideoPlay">连接终端</SshContextItem>
    <SshContextItem icon="Delete" danger @click="...">关闭全部</SshContextItem>
    <SshContextDivider />
-->
<template>
  <div :class="['ctx-item', { 'is-danger': danger }]" @click="$emit('click', $event)">
    <el-icon v-if="icon" :size="14">
      <component :is="icon" />
    </el-icon>
    <slot />
  </div>
</template>

<script setup lang="ts">
// SshContextMenuItem: 右键菜单子项, icon 接受 Element Plus icon 组件或 string
defineProps<{
  icon?: string | Record<string, unknown> | (() => unknown)
  danger?: boolean
}>()
defineEmits<{
  (e: 'click', ev: MouseEvent): void
}>()
</script>