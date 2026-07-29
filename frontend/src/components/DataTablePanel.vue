<!--
  DataTablePanel · 通用列表页壳（page-header + panel + toolbar + pagination）
  -----------------------------------------------------------------------
  给 5 个列表页共享：HostList / UserList / SysUserList /
  GroupList / UserGroupList。

  用途：消除各列表页重复的页面框架与分页结构，调用方只关心
  - 列定义 (slot default)
  - 工具栏筛选 (slot filters)
  - 活跃筛选 chip (slot active-filter)
  - 统计指标 (slot stats)
  - 业务特有操作 (slot actions)

  使用：
    <DataTablePanel
      eyebrow="ASSETS"
      title="资产列表"
      :subtitle="`共 ${total} 台 · 实时同步`"
      panel-title="资产列表"
      panel-sub="Host Inventory"
      :panel-icon="Monitor"
      :page="currentPage"
      :page-size="pageSize"
      :total="filteredData.length"
      :enable-batch="true"
      :batch-count="selectedRows.length"
      add-text="新增资产"
      @update:page="(p) => currentPage = p"
      @update:page-size="(s) => pageSize = s"
      @refresh="loadData"
      @add="openAdd()"
      @batch-delete="batchDelete"
    >
      <template #filters>
        <el-input v-model="keyword" placeholder="搜索 IP / 名称" ... />
      </template>
      <template #stats>
        <span>共 {{ total }} 台</span>
      </template>
      <el-table :data="pagedData" ...>
        ... 列定义 ...
      </el-table>
    </DataTablePanel>
-->
<template>
  <div class="page-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div>
        <span v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</span>
        <h2>{{ title }}</h2>
        <p v-if="$slots.subtitle || subtitle">
          <slot name="subtitle">{{ subtitle }}</slot>
        </p>
      </div>
      <div class="page-actions">
        <el-button @click="$emit('refresh')">{{ $t('common.action.refresh') }}</el-button>
        <slot name="actions">
          <el-button type="primary" @click="$emit('add')">
            <el-icon><Plus /></el-icon>{{ addText || $t('common.action.add') }}
          </el-button>
        </slot>
        <el-button v-if="enableBatch" type="danger" plain :disabled="!batchCount"
                   @click="$emit('batch-delete')">
          {{ $t('assets.panel.batchDelete') }}{{ batchCount ? ' (' + batchCount + ')' : '' }}
        </el-button>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <span v-if="panelIcon" class="panel-icon">
          <el-icon :size="14"><component :is="panelIcon" /></el-icon>
        </span>
        <span class="panel-title">{{ panelTitle }}</span>
        <span v-if="panelSub" class="panel-sub">{{ panelSub }}</span>
        <div class="panel-actions">
          <slot name="panel-actions" />
        </div>
      </div>

      <!-- 工具栏：左侧筛选 + 活跃筛选 + 右侧统计 -->
      <div class="list-toolbar">
        <slot name="filters" />
        <slot name="active-filter" />
        <div class="stats">
          <slot name="stats" />
        </div>
      </div>

      <!-- 主表格区 -->
      <div class="panel-body" style="padding:0">
        <slot />
      </div>

      <!-- 分页 -->
      <div class="list-pagination">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="pageSizes"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @update:current-page="(p: number) => $emit('update:page', p)"
          @update:page-size="(s: number) => $emit('update:pageSize', s)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'

defineProps<{
  // 页头
  eyebrow?: string
  title: string
  subtitle?: string
  addText?: string

  // Panel 头
  panelTitle: string
  panelSub?: string
  panelIcon?: Record<string, unknown> | (() => unknown)

  // 批量删除按钮
  enableBatch?: boolean
  batchCount?: number

  // 分页（v-model 风格：父组件 :page :page-size :total，监听 update:*）
  page: number
  pageSize: number
  total: number
  pageSizes?: number[]
}>()

defineEmits<{
  (e: 'update:page', v: number): void
  (e: 'update:pageSize', v: number): void
  (e: 'refresh'): void
  (e: 'add'): void
  (e: 'batch-delete'): void
}>()
</script>

<style scoped>
/* page-header / panel / list-toolbar / panel-body / list-pagination
 * 由全局样式提供，本组件不重复定义 */
</style>
