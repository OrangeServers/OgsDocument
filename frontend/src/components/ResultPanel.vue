<template>
  <div class="panel panel-result">
    <div class="panel-head">
      <span class="panel-icon"><el-icon :size="14"><Monitor /></el-icon></span>
      <span class="panel-title">{{ title || $t('ops.execResult') }}</span>
      <span class="panel-sub">{{ sub || 'Output' }}</span>
      <span class="panel-actions" v-if="results.length">
        <slot name="stats">
          <span class="result-stat">
            <span class="dot" style="background:var(--ogs-success)" />{{ $t('common.status.success') }} <strong class="num">{{ success }}</strong>
          </span>
          <span v-if="fail > 0" class="result-stat">
            <span class="dot" style="background:var(--ogs-danger)" />{{ $t('common.status.fail') }} <strong class="num">{{ fail }}</strong>
          </span>
        </slot>
      </span>
    </div>
    <div class="result-body">
      <!-- Loading -->
      <div v-if="loading" class="result-loading">
        <el-icon class="is-loading" :size="20"><Loading /></el-icon>
        <span>{{ loadingText || $t('ops.executingEllipsis') }}</span>
      </div>
      <!-- Empty -->
      <div v-else-if="results.length === 0" class="result-empty">
        <div class="terminal-placeholder">
          <div class="terminal-bar">
            <span class="dot r" /><span class="dot y" /><span class="dot g" />
            <span class="bar-title">{{ emptyTitle || 'Terminal' }}</span>
          </div>
          <div class="terminal-body">
            <slot name="empty-steps" />
          </div>
        </div>
      </div>
      <!-- Split: 左侧主机列表 + 右侧终端详情 -->
      <div v-else class="result-split">
        <div class="result-host-list">
          <div
            v-for="(r, i) in results"
            :key="i"
            class="result-host-card"
            :class="{ active: i === activeIndex, 'is-error': r.error }"
            @click="activeIndex = i"
          >
            <el-icon :size="14" class="host-icon"><Monitor /></el-icon>
            <span class="host-name" :title="r.host">{{ r.host }}</span>
            <el-tag v-if="r.error" type="danger" size="small" effect="plain">{{ $t('common.status.fail') }}</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">{{ $t('common.status.success') }}</el-tag>
          </div>
        </div>
        <div class="result-host-detail">
          <div class="result-host-bar">
            <span class="bar-dot" :class="current.error ? 'r' : 'g'" />
            <span class="bar-title">{{ current.host }}</span>
            <span class="bar-status">{{ current.error ? $t('ops.connFailed') : $t('ops.execSuccess') }}</span>
            <span class="bar-meta">{{ activeIndex + 1 }} / {{ results.length }}</span>
          </div>
          <pre class="result-output" :class="{ 'is-error': current.error }">{{ current.output }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Monitor, Loading } from '@element-plus/icons-vue'

/**
 * 结果面板 · 操作中心共用
 *
 * 布局：左侧主机卡片列 + 右侧选中主机的终端详情。N 台机器时 N 个卡片纵列
 *       排开，点击切换右侧输出，4-10 台机器一眼看全。
 *
 * props:
 *   - results: [{ host, output, error }] 结果列表
 *   - loading: 是否正在执行
 *   - success / fail: 成功/失败计数
 *   - title / sub: panel-head 标题（title 缺省用 ops.execResult 本地化文案）
 *   - loadingText: loading 文案（缺省用 ops.executingEllipsis 本地化文案）
 *   - emptyTitle: 终端占位卡顶部 bar-title
 *
 * slots:
 *   - stats: 自定义 stats 区（替换默认成功/失败 pill）
 *   - empty-steps: 自定义占位步骤（1·2·3）
 */

/** 单条结果 */
export interface ResultItem {
  host: string
  output?: string
  error?: boolean | string
  [k: string]: unknown
}

const props = withDefaults(defineProps<{
  results?: ResultItem[]
  loading?: boolean
  success?: number
  fail?: number
  title?: string
  sub?: string
  loadingText?: string
  emptyTitle?: string
}>(), {
  results: () => [] as ResultItem[],
  loading: false,
  success: 0,
  fail: 0,
  title: '',
  sub: 'Output',
  loadingText: '',
  emptyTitle: 'Terminal',
})

const activeIndex = ref(0)
const current = computed<ResultItem>(() => props.results?.[activeIndex.value] || { host: '', output: '', error: false })

// results 重置（变空）时回到 0
watch(() => props.results?.length || 0, (n) => { if (n === 0) activeIndex.value = 0 })
</script>
