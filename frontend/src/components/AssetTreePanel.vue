<template>
  <div class="panel panel-tree">
    <div class="panel-head">
      <span class="panel-icon"><el-icon :size="14"><Grid /></el-icon></span>
      <span class="panel-title">{{ $t('assets.tree.title') }}</span>
      <span class="panel-sub">Asset Picker</span>
      <span class="panel-actions">
        <el-tag v-if="mode === 'multi' && Array.isArray(checked)" size="small" type="info" effect="plain">{{ $t('assets.tree.selectedCount', { n: checked.length }) }}</el-tag>
        <el-tag v-else-if="connectedHost" size="small" type="success" effect="plain">● {{ connectedHost }}</el-tag>
        <el-tag v-else size="small" type="info" effect="plain">{{ $t('assets.tree.clickToConnect') }}</el-tag>
      </span>
    </div>
    <div class="ops-tree">
      <slot name="before-tree" />
      <el-input v-model="filter" :placeholder="$t('assets.tree.searchPlaceholder')" prefix-icon="Search" clearable size="small" class="tree-search" />
      <div class="tree-scroll">
        <el-tree
          ref="treeRef"
          :data="treeData"
          :show-checkbox="mode === 'multi'"
          :node-key="'id'"
          :default-expanded-keys="[1]"
          :filter-node-method="filterNode"
          :props="{ label:'title', children:'children' }"
          @check="mode === 'multi' && onCheckMulti()"
          @node-click="onNodeClick"
        >
          <template #default="{ node, data }">
            <div class="tree-node" :class="{ 'is-group': !node.isLeaf, 'is-host': node.isLeaf, 'is-connected': node.isLeaf && data.title === connectedHost }">
              <el-icon v-if="!node.isLeaf" class="node-icon group-icon" :size="16">
                <FolderOpened v-if="node.expanded" />
                <Folder v-else />
              </el-icon>
              <el-icon v-else class="node-icon host-icon" :size="14"><Monitor /></el-icon>
              <span class="node-label">{{ data.title }}</span>
              <el-tag v-if="!node.isLeaf && data.children" size="small" type="info" class="node-count">{{ data.children.length }}</el-tag>
            </div>
          </template>
        </el-tree>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Grid, Folder, FolderOpened, Monitor } from '@element-plus/icons-vue'

/**
 * 资产树面板 · 操作中心共用
 *
 * props:
 *   - treeData: 资产树数据
 *   - mode: 'multi'（checkbox 多选，用于 BatchCommand/BatchScript）
 *           | 'single'（点选单选，用于 FileTransfer，可结合 @pick 回调）
 *   - checked (v-model:checked): 已选项（multi 模式返回主机名数组，single 模式返回单个主机名）
 *   - connectedHost: 当前连接的主机名（single 模式时高亮该 host），如 SFTP 当前会话主机
 *
 * emits:
 *   - update:checked
 *   - pick: single 模式下点击节点触发
 */

/** 树节点最小结构 (后端可携带 group/children/tags) */
interface TreeNode {
  id: number | string
  title: string
  children?: TreeNode[]
  group?: string
  tags?: string[]
  [k: string]: unknown
}

/** el-tree 实例暴露的方法 */
interface ElTreeInstance {
  filter: (val: string) => void
  getCheckedNodes: (leafOnly: boolean, includeHalfChecked: boolean) => TreeNode[]
}

const props = defineProps<{
  treeData?: TreeNode[]
  mode?: 'multi' | 'single'
  checked?: string[] | string
  connectedHost?: string
}>()
const emit = defineEmits<{
  (e: 'update:checked', v: string[] | string): void
  (e: 'pick', v: string): void
}>()

const treeRef = ref<ElTreeInstance | null>(null)
const filter = ref('')

watch(filter, val => { treeRef.value?.filter(val) })
watch(() => props.treeData, () => { treeRef.value?.filter(filter.value) })

function filterNode(val: string, data: TreeNode): boolean {
  if (!val) return true
  return (data.title || '').toLowerCase().includes(val.toLowerCase())
}

function onCheckMulti(): void {
  const nodes = treeRef.value?.getCheckedNodes(true, false) || []
  emit('update:checked', nodes.map(n => n.title))
}

function onPickSingle(data: TreeNode, node: { isLeaf: boolean }): void {
  if (!node.isLeaf) return
  emit('pick', data.title)
  emit('update:checked', data.title)
}

/** el-tree @node-click 入口: 透传 data/node 到 onPickSingle (type-narrow) */
function onNodeClick(data: TreeNode, node: { isLeaf: boolean }): void {
  if (props.mode !== 'single') return
  onPickSingle(data, node)
}
</script>