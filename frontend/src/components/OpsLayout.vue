<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <span class="page-eyebrow">{{ eyebrow }}</span>
        <h2>{{ title }}</h2>
        <!--
          REVIEW-14 P1-1: 移除 v-html，改为结构化 desc 渲染
          - desc 为 string：当作纯文本渲染（向后兼容）
          - desc 为 Array<{t, v}>：按段渲染，t ∈ ['text'|'num'|'bold'|'plain']
            · 'text' : 默认纯文本
            · 'num'  : 数字高亮（class="desc-num"，受全局 var(--ogs-primary) 控制）
            · 'bold' : 加粗
            · 'plain': 同 text，别名
          - Vue 模板自带 HTML 转义，无需 v-html 也无 XSS 风险
        -->
        <p v-if="hasDesc" class="page-desc">
          <template v-if="descIsString">{{ desc }}</template>
          <template v-else>
            <span
              v-for="(p, i) in descParts"
              :key="i"
              :class="descClass(p)"
            >{{ p && p.v != null ? p.v : '' }}</span>
          </template>
        </p>
      </div>
      <div class="page-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="ops-split">
      <div class="ops-pane-side">
        <slot name="side" />
      </div>
      <div class="ops-pane-main">
        <slot name="main" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** desc 段类型 */
export interface DescPart {
  t: 'text' | 'num' | 'bold' | 'plain'
  v: string | number
}

const props = defineProps<{
  eyebrow: string
  title: string
  // 向后兼容：string 仍可传（当作纯文本），Array 则按段渲染
  desc?: string | DescPart[]
}>()

// 是否需要渲染 desc
const hasDesc = computed(() => {
  if (Array.isArray(props.desc)) return props.desc.length > 0
  return typeof props.desc === 'string' && props.desc.length > 0
})

// desc 是否为 string
const descIsString = computed(() => typeof props.desc === 'string')

// desc 数组 (已 narrow 为 DescPart[] 供模板 v-for)
const descParts = computed<DescPart[]>(() => Array.isArray(props.desc) ? props.desc : [])

// 根据 part 类型返回 class
function descClass(p: DescPart | null | undefined): string {
  if (!p || typeof p !== 'object') return ''
  switch (p.t) {
    case 'num': return 'desc-num'
    case 'bold': return 'desc-bold'
    case 'plain':
    case 'text':
    default: return ''
  }
}
</script>

<style scoped>
.page-desc {
  margin: 4px 0 0;
  color: var(--ogs-text-secondary, #6b7280);
  font-size: 13px;
  line-height: 1.6;
}
.desc-num {
  color: var(--ogs-primary, #409eff);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.desc-bold {
  color: var(--ogs-text, #111827);
  font-weight: 600;
}
</style>