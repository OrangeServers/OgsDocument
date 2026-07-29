<template>
  <OpsLayout
    eyebrow="OPERATIONS · BATCH COMMAND"
    :title="$t('ops.batchCommandTitle')"
    :desc="desc"
  >
    <template #side>
      <AssetTreePanel v-model:checked="selectedHosts" :tree-data="treeData" mode="multi" />
    </template>

    <template #main>
      <BatchOperationCanvas
        v-model:selected-hosts="selectedHosts"
        v-model:sys-user="sysUser"
        kind="command"
      />
    </template>
  </OpsLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import OpsLayout, { type DescPart } from '@/components/OpsLayout.vue'
import AssetTreePanel from '@/components/AssetTreePanel.vue'
import BatchOperationCanvas from '@/components/BatchOperationCanvas.vue'
import { getTreeData } from '@/api'
import { t } from '@/i18n'

interface TreeNode {
  id: number | string
  title: string
  children?: TreeNode[]
  [key: string]: unknown
}

const treeData = ref<TreeNode[]>([])
const selectedHosts = ref<string[]>([])
const sysUser = ref('')

// desc 为响应式 computed：语言切换 / 选中数变化时即时更新
const desc = computed<DescPart[]>(() => [
  { t: 'text', v: t('ops.commandDescPrefix') },
  { t: 'num', v: selectedHosts.value.length },
  { t: 'text', v: t('ops.descCredential') },
  { t: 'bold', v: sysUser.value || '—' },
])

onMounted(async () => {
  try {
    const response = await getTreeData() as unknown as { host?: TreeNode[] }
    treeData.value = (response.host || [])
      .map(group => ({
        ...group,
        children: [...(group.children || [])].sort((a, b) => a.title.localeCompare(b.title)),
      }))
      .sort((a, b) => a.title.localeCompare(b.title))
  } catch {
    // 资产树沿用原页面的静默降级；右侧操作会在无目标时保持禁用。
  }
})
</script>
