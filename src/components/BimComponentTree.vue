<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import type { BimTreeNode } from '../types/bim'

const props = defineProps<{
  roots: BimTreeNode[]
  selectionMode: 'single' | 'multi'
  selectedKey: string | null
  multiSelectedKeys: Set<string>
  unselectedOpacity: number
}>()

const emit = defineEmits<{
  selectElement: [node: BimTreeNode]
  toggleMultiElement: [node: BimTreeNode]
  clearSelection: []
  setMode: [mode: 'single' | 'multi']
  setOpacity: [value: number]
}>()

const expanded = ref<Set<string>>(new Set())
const collapsed = ref(false)
const position = ref({ x: 320, y: 20 })
const dragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })

const toggleExpanded = (id: string) => {
  const next = new Set(expanded.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expanded.value = next
}

const isSelected = (node: BimTreeNode) => {
  if (node.type !== 'element' || !node.ifcGuid) return false
  const key = `${node.modelId}:${node.ifcGuid}`
  return props.selectionMode === 'single'
    ? props.selectedKey === key
    : props.multiSelectedKeys.has(key)
}

const onNodeClick = (node: BimTreeNode) => {
  if (!node.selectable || node.type !== 'element') {
    if (node.children?.length) {
      toggleExpanded(node.id)
    }
    return
  }

  if (props.selectionMode === 'single') {
    emit('selectElement', node)
  } else {
    emit('toggleMultiElement', node)
  }
}

const startDrag = (event: PointerEvent) => {
  dragging.value = true
  dragOffset.value = {
    x: event.clientX - position.value.x,
    y: event.clientY - position.value.y,
  }
  window.addEventListener('pointermove', onDrag)
  window.addEventListener('pointerup', stopDrag)
}

const onDrag = (event: PointerEvent) => {
  if (!dragging.value) return
  position.value = {
    x: Math.max(0, Math.min(window.innerWidth - 40, event.clientX - dragOffset.value.x)),
    y: Math.max(0, Math.min(window.innerHeight - 40, event.clientY - dragOffset.value.y)),
  }
}

const stopDrag = () => {
  dragging.value = false
  window.removeEventListener('pointermove', onDrag)
  window.removeEventListener('pointerup', stopDrag)
}

onBeforeUnmount(stopDrag)
</script>

<template>
  <div
    class="component-tree"
    :class="{ collapsed }"
    :style="{ left: `${position.x}px`, top: `${position.y}px` }"
  >
    <div class="tree-header" @pointerdown="startDrag">
      <strong>构件树</strong>
      <button @pointerdown.stop @click="collapsed = !collapsed">
        {{ collapsed ? '展开' : '收起' }}
      </button>
    </div>
    <template v-if="!collapsed">
    <div class="tree-toolbar" @pointerdown.stop>
      <div class="mode-switch">
        <button :class="{ active: selectionMode === 'single' }" @click="emit('setMode', 'single')">
          单选隔离
        </button>
        <button :class="{ active: selectionMode === 'multi' }" @click="emit('setMode', 'multi')">
          多选
        </button>
      </div>
      <button @click="emit('clearSelection')">清空选择</button>
    </div>

    <div v-if="selectionMode === 'multi'" class="opacity-control">
      <label>未选构件透明度：{{ Math.round(unselectedOpacity * 100) }}%</label>
      <input
        type="range"
        min="0.1"
        max="1"
        step="0.05"
        :value="unselectedOpacity"
        @input="emit('setOpacity', parseFloat(($event.target as HTMLInputElement).value))"
      />
    </div>

    <div class="tree-root">
      <div v-for="root in roots" :key="root.id">
        <div
          class="tree-node"
          :class="{ selectable: root.selectable, selected: isSelected(root) }"
          @click="onNodeClick(root)"
        >
          <span v-if="root.children?.length" class="toggle" @click.stop="toggleExpanded(root.id)">
            {{ expanded.has(root.id) ? '−' : '+' }}
          </span>
          <span v-else class="toggle-placeholder" />
          <span class="label" :title="root.label">{{ root.label }}</span>
        </div>

        <div v-if="expanded.has(root.id) && root.children?.length" class="children">
          <div v-for="storey in root.children" :key="storey.id">
            <div class="tree-node" @click="onNodeClick(storey)">
              <span v-if="storey.children?.length" class="toggle" @click.stop="toggleExpanded(storey.id)">
                {{ expanded.has(storey.id) ? '−' : '+' }}
              </span>
              <span v-else class="toggle-placeholder" />
              <span class="label" :title="storey.label">{{ storey.label }}</span>
            </div>

            <div v-if="expanded.has(storey.id) && storey.children?.length" class="children">
              <div v-for="category in storey.children" :key="category.id">
                <div class="tree-node" @click="onNodeClick(category)">
                  <span v-if="category.children?.length" class="toggle" @click.stop="toggleExpanded(category.id)">
                    {{ expanded.has(category.id) ? '−' : '+' }}
                  </span>
                  <span v-else class="toggle-placeholder" />
                  <span class="label" :title="category.label">{{ category.label }}</span>
                </div>

                <div v-if="expanded.has(category.id) && category.children?.length" class="children">
                  <div
                    v-for="element in category.children"
                    :key="element.id"
                    class="tree-node leaf"
                    :class="{ selected: isSelected(element) }"
                    :title="element.label"
                    @click="onNodeClick(element)"
                  >
                    <span class="toggle-placeholder" />
                    <span class="label">{{ element.label }}</span>
                    <span class="element-type">{{ element.label === element.ifcGuid ? '' : element.type }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    </template>
  </div>
</template>

<style scoped>
.component-tree {
  position: fixed;
  z-index: 1050;
  width: 340px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
}

.component-tree.collapsed {
  width: auto;
  max-height: none;
}

.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  cursor: move;
  user-select: none;
  touch-action: none;
  border-bottom: 1px solid #ddd;
}

.tree-toolbar {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  padding: 8px;
  border-bottom: 1px solid #ddd;
}

.mode-switch {
  display: flex;
  gap: 5px;
}

button {
  padding: 5px 7px;
  font-size: 12px;
  background: #eee;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
}

button.active {
  background: #2196f3;
  color: white;
}

.opacity-control {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  font-size: 12px;
  border-bottom: 1px solid #ddd;
}

.opacity-control input {
  flex: 1;
}

.tree-root {
  overflow-y: auto;
  padding: 8px;
}

.children {
  margin-left: 12px;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 4px;
  border-radius: 3px;
  cursor: default;
}

.tree-node.selectable,
.tree-node.leaf {
  cursor: pointer;
}

.tree-node.leaf:hover {
  background: #f0f7ff;
}

.tree-node.selected {
  background: #d9edff;
}

.toggle,
.toggle-placeholder {
  width: 14px;
  text-align: center;
  flex: 0 0 14px;
}

.label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.element-type {
  font-size: 11px;
  color: #888;
}
</style>
