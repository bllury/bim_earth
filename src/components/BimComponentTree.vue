<script setup lang="ts">
import { ref } from 'vue'
import type { BimTreeNode } from '../types/bim'
import {
  CONSOLE_HANDLE_HEIGHT,
  CONSOLE_HEIGHT,
  useLayoutState,
} from '../features/layout/useLayoutState'

const props = defineProps<{
  roots: BimTreeNode[]
  selectionMode: 'single' | 'multi'
  selectedKey: string | null
  multiSelectedKeys: Set<string>
  unselectedOpacity: number
  hiddenKeys: Set<string>
}>()

const emit = defineEmits<{
  selectElement: [node: BimTreeNode]
  toggleMultiElement: [node: BimTreeNode]
  clearSelection: []
  setMode: [mode: 'single' | 'multi']
  setOpacity: [value: number]
  toggleVisibility: [node: BimTreeNode]
}>()

const expanded = ref<Set<string>>(new Set())
const { consoleOpen, treePanelOpen } = useLayoutState()

const toggleExpanded = (id: string) => {
  const next = new Set(expanded.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }

  expanded.value = next
}

const collectElementKeys = (node: BimTreeNode): string[] => {
  const keys: string[] = []
  const collect = (current: BimTreeNode) => {
    if (current.type === 'element' && current.ifcGuid) {
      keys.push(`${current.modelId}:${current.ifcGuid}`)
      return
    }

    current.children?.forEach(collect)
  }

  collect(node)
  return keys
}

const isElementChecked = (node: BimTreeNode) => {
  if (!node.ifcGuid) return false
  return !props.hiddenKeys.has(`${node.modelId}:${node.ifcGuid}`)
}

const isNodeChecked = (node: BimTreeNode) => {
  const elementKeys = collectElementKeys(node)
  return (
    elementKeys.length > 0 &&
    elementKeys.every((key) => !props.hiddenKeys.has(key))
  )
}

const isNodeIndeterminate = (node: BimTreeNode) => {
  const elementKeys = collectElementKeys(node)
  const hiddenCount = elementKeys.filter((key) => props.hiddenKeys.has(key)).length
  return hiddenCount > 0 && hiddenCount < elementKeys.length
}

const hasElementDescendants = (node: BimTreeNode) => {
  return collectElementKeys(node).length > 0
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

</script>

<template>
  <aside
    class="bim-tree-panel"
    :class="{ 'is-collapsed': !treePanelOpen }"
    :style="{
      bottom: consoleOpen ? `${CONSOLE_HEIGHT}px` : `${CONSOLE_HANDLE_HEIGHT}px`,
    }"
  >
    <div class="tree-titlebar">
      <span class="tree-title">构件树</span>
      <span v-if="roots.length" class="count-badge">{{ roots.length }}</span>
    </div>

    <button
      class="tree-handle"
      :aria-expanded="treePanelOpen"
      :title="treePanelOpen ? '收起构件树' : '展开构件树'"
      @click="treePanelOpen = !treePanelOpen"
    >
      <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
        <path
          d="M6 3.5 10.5 8 6 12.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <div class="tree-content">
      <div class="tree-toolbar">
        <div class="mode-switch">
          <button :class="{ active: selectionMode === 'single' }" @click="emit('setMode', 'single')">单选</button>
          <button :class="{ active: selectionMode === 'multi' }" @click="emit('setMode', 'multi')">多选</button>
        </div>
        <button @click="emit('clearSelection')">清空选择</button>
      </div>
      <div class="opacity-control">
        <label>未选构件透明度：{{ Math.round(unselectedOpacity * 100) }}%</label>
        <input
          class="slider"
          type="range"
          min="0"
          max="1"
          step="0.05"
          :value="unselectedOpacity"
          :style="{ '--slider-fill': `${unselectedOpacity * 100}%` }"
          @input="emit('setOpacity', parseFloat(($event.target as HTMLInputElement).value))"
        />
      </div>
      <div class="tree-root">
        <div v-if="!roots.length" class="tree-empty">IFC 构件树暂无数据，请等待模型元数据加载完成</div>
        <div v-for="root in roots" :key="root.id">
          <div class="tree-node" :class="{ selectable: root.selectable, selected: isSelected(root) }" @click="onNodeClick(root)">
            <input type="checkbox" :checked="isNodeChecked(root)" :indeterminate="isNodeIndeterminate(root)" :disabled="!hasElementDescendants(root)" @click.stop @change="emit('toggleVisibility', root)" />
            <span v-if="root.children?.length" class="toggle" @click.stop="toggleExpanded(root.id)">{{ expanded.has(root.id) ? '−' : '+' }}</span>
            <span v-else class="toggle-placeholder" />
            <span class="label" :title="root.label">{{ root.label }}</span>
          </div>
          <div v-if="expanded.has(root.id) && root.children?.length" class="children">
            <div v-for="storey in root.children" :key="storey.id">
              <div class="tree-node" @click="onNodeClick(storey)">
                <input type="checkbox" :checked="isNodeChecked(storey)" :indeterminate="isNodeIndeterminate(storey)" :disabled="!hasElementDescendants(storey)" @click.stop @change="emit('toggleVisibility', storey)" />
                <span v-if="storey.children?.length" class="toggle" @click.stop="toggleExpanded(storey.id)">{{ expanded.has(storey.id) ? '−' : '+' }}</span>
                <span v-else class="toggle-placeholder" />
                <span class="label" :title="storey.label">{{ storey.label }}</span>
              </div>
              <div v-if="expanded.has(storey.id) && storey.children?.length" class="children">
                <div v-for="category in storey.children" :key="category.id">
                  <div class="tree-node" @click="onNodeClick(category)">
                    <input type="checkbox" :checked="isNodeChecked(category)" :indeterminate="isNodeIndeterminate(category)" :disabled="!hasElementDescendants(category)" @click.stop @change="emit('toggleVisibility', category)" />
                    <span v-if="category.children?.length" class="toggle" @click.stop="toggleExpanded(category.id)">{{ expanded.has(category.id) ? '−' : '+' }}</span>
                    <span v-else class="toggle-placeholder" />
                    <span class="label" :title="category.label">{{ category.label }}</span>
                  </div>
                  <div v-if="expanded.has(category.id) && category.children?.length" class="children">
                    <div v-for="element in category.children" :key="element.id" class="tree-node leaf" :class="{ selected: isSelected(element) }" :title="element.label" @click="onNodeClick(element)">
                      <input type="checkbox" :checked="isElementChecked(element)" @click.stop @change="emit('toggleVisibility', element)" />
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
    </div>
  </aside>
</template>

<style scoped>
.bim-tree-panel {
  /* Light theme tokens; a dark theme only needs to override this block. */
  --tp-bg: #ffffff;
  --tp-fg: #24292f;
  --tp-muted: #6e7781;
  --tp-border: #e6e8eb;
  --tp-hover: #f3f4f6;
  --tp-accent: #1a56db;
  --tp-accent-soft: #f2f7ff;
  --tp-accent-border: #c9dcfb;
  --tp-row-hover: #f0f7ff;
  --tp-selected-bg: #dbeafe;
  --tp-input-border: #d7dbe0;
  /* Same slider palette as the model sidebar's scale / rotation controls. */
  --tp-slider: #123c94;
  --tp-slider-track: #c9ced6;
  --tp-slider-shadow: rgba(15, 23, 42, 0.22);

  position: fixed;
  top: 0;
  right: 0;
  width: 340px;
  display: flex;
  flex-direction: column;
  background: var(--tp-bg);
  /* Drawn as a shadow so the border box stays exactly 340px wide and the
     handle lands flush with the right edge when the panel slides away. */
  box-shadow: -1px 0 0 var(--tp-border);
  color: var(--tp-fg);
  font-size: 13px;
  z-index: 1200;
  transition: transform 0.22s ease, bottom 0.22s ease;
}

.bim-tree-panel.is-collapsed {
  transform: translateX(100%);
}

.tree-titlebar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 10px;
  border-bottom: 1px solid var(--tp-border);
}

.tree-title {
  font-weight: 600;
  color: var(--tp-fg);
}

.count-badge {
  min-width: 18px;
  padding: 1px 6px;
  border-radius: 9px;
  background: var(--tp-accent-soft);
  border: 1px solid var(--tp-accent-border);
  color: var(--tp-accent);
  font-size: 11px;
  text-align: center;
}

.tree-handle {
  position: absolute;
  right: 100%;
  top: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--tp-border);
  border-right: none;
  border-radius: 6px 0 0 6px;
  background: var(--tp-bg);
  box-shadow: -1px 1px 3px rgba(15, 23, 42, 0.14);
  color: var(--tp-muted);
  cursor: pointer;
}

.tree-handle:hover {
  background: var(--tp-hover);
  color: var(--tp-fg);
}

.tree-handle svg {
  transition: transform 0.22s ease;
}

.bim-tree-panel.is-collapsed .tree-handle {
  background: var(--tp-accent-soft);
  border-color: var(--tp-accent-border);
  color: var(--tp-accent);
}

.bim-tree-panel.is-collapsed .tree-handle svg {
  transform: rotate(180deg);
}

.tree-content {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
}

.tree-toolbar {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  padding: 8px;
  border-bottom: 1px solid var(--tp-border);
}

.mode-switch {
  display: flex;
  gap: 5px;
}

button {
  padding: 3px 8px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--tp-fg);
  background: var(--tp-bg);
  border: 1px solid var(--tp-input-border);
  border-radius: 5px;
  cursor: pointer;
}

button:hover {
  background: var(--tp-hover);
}

button.active {
  background: var(--tp-accent);
  border-color: var(--tp-accent);
  color: #ffffff;
}

.opacity-control {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  font-size: 11.5px;
  color: var(--tp-muted);
  border-bottom: 1px solid var(--tp-border);
}

.slider {
  -webkit-appearance: none;
  appearance: none;
  flex: 1 1 auto;
  min-width: 0;
  height: 16px;
  margin: 0;
  background: transparent;
  cursor: pointer;
}

.slider::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(
    to right,
    var(--tp-slider) 0 var(--slider-fill, 0%),
    var(--tp-slider-track) var(--slider-fill, 0%) 100%
  );
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border-radius: 50%;
  background: var(--tp-bg);
  border: 2px solid var(--tp-slider);
  box-shadow: 0 1px 2px var(--tp-slider-shadow);
}

.slider::-moz-range-track {
  height: 4px;
  border-radius: 2px;
  background: var(--tp-slider-track);
}

.slider::-moz-range-progress {
  height: 4px;
  border-radius: 2px;
  background: var(--tp-slider);
}

.slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--tp-bg);
  border: 2px solid var(--tp-slider);
}

.tree-root {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.tree-empty {
  padding: 18px 8px;
  color: var(--tp-muted);
  font-size: 11.5px;
  text-align: center;
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

.tree-node input[type='checkbox'] {
  flex: 0 0 auto;
  margin: 0 2px 0 0;
  accent-color: var(--tp-accent);
}

.tree-node.selectable,
.tree-node.leaf {
  cursor: pointer;
}

.tree-node.leaf:hover {
  background: var(--tp-row-hover);
}

.tree-node.selected {
  background: var(--tp-selected-bg);
}

.toggle,
.toggle-placeholder {
  width: 14px;
  text-align: center;
  flex: 0 0 14px;
  color: var(--tp-muted);
}

.label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
}

.element-type {
  font-size: 11px;
  color: var(--tp-muted);
}
</style>
