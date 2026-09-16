<template>
  <div class="layout">
    <!-- 顶部工具栏 -->
    <header class="toolbar">
      <strong>◇ BIM Earth</strong>
      <span class="toolbar-spacer" />
      <button
        :class="{ active: leftOpen && activePanel === 'coordinate' }"
        @click="togglePanel('coordinate')"
      >坐标</button>
      <button
        :class="{ active: leftOpen && activePanel === 'model-tree' }"
        @click="togglePanel('model-tree')"
      >构件树</button>
      <button
        :class="{ active: leftOpen && activePanel === 'model-uploader' }"
        @click="togglePanel('model-uploader')"
      >模型上传</button>
      <button>⚙ 设置</button>
      <button>⋮</button>
    </header>

    <div class="workspace">
      <!-- 中间三维视口（始终占满） -->
      <main class="viewport">
        <button class="toggle left" @click="leftOpen = !leftOpen">
          {{ leftOpen ? '‹' : '›' }}
        </button>
        <button class="toggle right" @click="rightOpen = !rightOpen">
          {{ rightOpen ? '›' : '‹' }}
        </button>
        <div class="scene-slot">
          <slot />
        </div>
      </main>

      <!-- 左侧边栏（绝对定位） -->
      <aside v-show="leftOpen" class="panel left-panel">
        <div class="panel-title">
          <span>{{ panelTitle }}</span>
          <button @click="closeLeftPanel">‹</button>
        </div>
        <div class="panel-body">
          <div v-show="activePanel === 'coordinate'" class="panel-section">
            <slot name="coordinate-panel" />
          </div>
          <div v-show="activePanel === 'model-tree'" class="panel-section">
            <slot name="model-tree" />
          </div>
          <div v-show="activePanel === 'model-uploader'" class="panel-section">
            <slot name="model-uploader" />
          </div>
        </div>
      </aside>

      <!-- 右侧边栏（绝对定位） -->
      <aside v-show="rightOpen" class="panel right-panel">
        <div class="panel-title">
          属性
          <button @click="rightOpen = false">›</button>
        </div>
        <section class="panel-section">
          <h3>选中对象</h3>
          <slot name="selection">
            <div class="content"><p>未选择对象</p></div>
          </slot>
        </section>
        <section class="panel-section">
          <h3>属性信息</h3>
          <slot name="properties">
            <div class="content">
              <p>类别　—</p>
              <p>类型　—</p>
              <p>标高　—</p>
            </div>
          </slot>
        </section>
      </aside>
    </div>

    <footer class="status">
      <span>● 系统就绪</span>
      <span>对象 0</span>
      <span>视图：3D</span>
      <span class="toolbar-spacer">FPS 60</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const leftOpen = ref(false)
const rightOpen = ref(false)
const activePanel = ref<'coordinate' | 'model-tree' | 'model-uploader' | null>(null)

const panelTitle = computed(() => {
  if (activePanel.value === 'coordinate') return '坐标'
  if (activePanel.value === 'model-tree') return '构件树'
  if (activePanel.value === 'model-uploader') return '模型管理'
  return '面板'
})

const emit = defineEmits<{
  (e: 'panel-change', panel: 'coordinate' | 'model-tree' | 'model-uploader' | null): void
}>()

const togglePanel = (panelName: 'coordinate' | 'model-tree' | 'model-uploader') => {
  if (leftOpen.value && activePanel.value === panelName) {
    leftOpen.value = false
    activePanel.value = null
  } else {
    leftOpen.value = true
    activePanel.value = panelName
  }
  emit('panel-change', activePanel.value)
}

const closeLeftPanel = () => {
  leftOpen.value = false
  activePanel.value = null
  emit('panel-change', null)
}

// 向外同步当前面板状态
watch(activePanel, (val) => {
  emit('panel-change', val)
})
</script>

<style scoped>
:global(*) { box-sizing: border-box; }

.layout {
  height: 100vh;
  display: grid;
  grid-template-rows: 48px 1fr 28px;
  overflow: hidden;
  background: #0d1117;
  color: #d7dee9;
  font: 13px system-ui, sans-serif;
}

.toolbar, .status {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  background: #151b24;
  border-bottom: 1px solid #273140;
  z-index: 20;
}

.toolbar strong { color: #f4f7fb; font-size: 15px; }
.toolbar-spacer { flex: 1; }

.toolbar button, .panel button {
  border: 0;
  border-radius: 5px;
  padding: 6px 10px;
  background: transparent;
  color: #aeb9c8;
  cursor: pointer;
}
.toolbar button:hover, .panel button:hover {
  background: #26364d;
  color: #82cfff;
}
.toolbar button.active {
  background: #26364d;
  color: #82cfff;
}

.workspace {
  position: relative;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

/* 地球始终占满 */
.viewport {
  position: absolute;
  inset: 0;
  background: #0b111a;
}
.scene-slot {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.toggle {
  position: absolute;
  top: 12px;
  z-index: 15;
  border: 1px solid #344355;
  border-radius: 5px;
  padding: 6px 9px;
  background: #1c2633;
  color: #b9c5d4;
  cursor: pointer;
}
.toggle.left { left: 12px; }
.toggle.right { right: 12px; }

/* 左侧边栏 - 绝对定位 */
.left-panel {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 320px;
  z-index: 10;
  background: #151b24;
  border-right: 1px solid #273140;
  display: flex;
  flex-direction: column;
  box-shadow: 4px 0 16px rgba(0,0,0,0.3);
}

/* 右侧边栏 */
.right-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 320px;
  z-index: 10;
  background: #151b24;
  border-left: 1px solid #273140;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 16px rgba(0,0,0,0.3);
}

.panel-title {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 45px;
  padding: 0 12px;
  border-bottom: 1px solid #273140;
  font-weight: 600;
}

.panel-body {
  flex: 1;
  overflow: auto;
}

.panel-section {
  height: 100%;
}

.panel-section h3 {
  margin: 14px 12px 8px;
  color: #7f8da0;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.content {
  padding: 12px;
}
.content p {
  padding: 8px 0;
  border-bottom: 1px solid #222c38;
  color: #aeb9c8;
}

.status {
  border-top: 1px solid #273140;
  border-bottom: 0;
  color: #8290a2;
  font-size: 11px;
  z-index: 20;
}
.status span:first-child { color: #43d17b; }

/* ========== 强制侧栏内的组件变成深色流式布局 ========== */
.panel-section :deep(.model-panel),
.panel-section :deep(.component-tree-wrap),
.panel-section :deep([class*="panel"]) {
  position: static !important;
  left: auto !important;
  top: auto !important;
  right: auto !important;
  width: 100% !important;
  max-width: 100% !important;
  max-height: none !important;
  margin: 0 !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
  color: #d7dee9 !important;
}

.panel-section :deep(.component-tree-wrap) {
  display: block !important;
}

.panel-section :deep(h3),
.panel-section :deep(h4),
.panel-section :deep(.panel-header) {
  color: #d7dee9 !important;
  background: transparent !important;
  border-bottom: 1px solid #273140 !important;
}

.panel-section :deep(.upload-button) {
  background: #2e7d32 !important;
  color: white !important;
  width: 100%;
}

.panel-section :deep(input),
.panel-section :deep(select) {
  background: #1c2633 !important;
  border: 1px solid #344355 !important;
  color: #d7dee9 !important;
}

.panel-section :deep(.hint) {
  color: #ffb74d !important;
}
</style>