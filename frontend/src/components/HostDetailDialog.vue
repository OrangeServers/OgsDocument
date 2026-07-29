<template>
  <el-dialog
    :model-value="modelValue"
    :title="$t('assets.detail.title')"
    width="420px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-if="host" class="host-detail">
      <div class="detail-row">
        <span class="detail-label">{{ $t('assets.detail.hostname') }}</span>
        <span class="detail-value">{{ host.title || '-' }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">{{ $t('assets.detail.sysUser') }}</span>
        <span class="detail-value">{{ sysUser || '-' }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">{{ $t('assets.detail.group') }}</span>
        <span class="detail-value">{{ host.group || '-' }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">{{ $t('assets.detail.tags') }}</span>
        <span class="detail-value">
          <template v-if="host.tags && host.tags.length">
            <el-tag
              v-for="(tag, idx) in host.tags"
              :key="idx"
              size="small"
              type="info"
              class="detail-tag"
            >{{ tag }}</el-tag>
          </template>
          <span v-else>-</span>
        </span>
      </div>
    </div>
    <template #footer>
      <el-button type="primary" @click="$emit('update:modelValue', false)">{{ $t('common.action.close') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// REVIEW-14-P0-2: 独立 Vue 组件,去除 ElMessageBox.alert + dangerouslyUseHTMLString
//   原实现：拼 HTML 字符串注入弹窗，后端返回的主机名/分组/标签未转义即可 XSS
//   修复：纯模板绑定，Vue 自动转义插值

/** 主机详情对象 (后端可携带 tags/group/title) */
interface HostDetail {
  title?: string
  group?: string
  tags?: string[]
  [k: string]: unknown
}

defineProps<{
  modelValue: boolean
  host?: HostDetail | null
  sysUser?: string
}>()
defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()
</script>

<style scoped>
.host-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0;
}
.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 13px;
  line-height: 1.6;
}
.detail-label {
  flex-shrink: 0;
  width: 72px;
  color: var(--ogs-text-secondary);
  font-weight: 500;
}
.detail-value {
  flex: 1;
  color: var(--ogs-text);
  word-break: break-all;
}
.detail-tag {
  margin-right: 6px;
}
</style>