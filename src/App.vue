<script setup lang="ts">
import { shallowRef, ref } from 'vue'
import * as Cesium from 'cesium'
import EarthViewer from './components/EarthViewer.vue'
import CoordinatePanel from './components/CoordinatePanel.vue'
import ModelUploader from './components/ModelUploader.vue'
import Layout from './ui/Layout.vue'
import type { PickedIfcFeature } from './lib/ifcPicking'

const viewer = shallowRef<Cesium.Viewer | null>(null)
const selectedPosition = shallowRef<Cesium.Cartesian3 | null>(null)
const pickedIfcFeature = shallowRef<PickedIfcFeature | null>(null)

const currentPanel = ref<'coordinate' | 'model-tree' | 'model-uploader' | null>(null)

const handleViewerReady = (value: Cesium.Viewer) => {
  viewer.value = value
}

const handlePositionChange = (position: Cesium.Cartesian3) => {
  selectedPosition.value = position
}

const handleIfcFeaturePicked = (feature: PickedIfcFeature | null) => {
  pickedIfcFeature.value = feature
}

const onPanelChange = (panel: 'coordinate' | 'model-tree' | 'model-uploader' | null) => {
  currentPanel.value = panel
}
</script>

<template>
  <Layout @panel-change="onPanelChange">
    <!-- 地球始终渲染 -->
    <EarthViewer
      :selected-position="selectedPosition"
      @viewer-ready="handleViewerReady"
      @position-change="handlePositionChange"
      @ifc-feature-picked="handleIfcFeaturePicked"
    />

    <!-- 坐标 -->
    <template #coordinate-panel>
      <CoordinatePanel
        :viewer="viewer"
        :selected-position="selectedPosition"
        @coordinate-selected="handlePositionChange"
      />
    </template>

    <!-- 构件树（只显示树） -->
    <template #model-tree>
      <div class="sidebar-tree">
        <ModelUploader
          :viewer="viewer"
          :position="selectedPosition"
          :picked-feature="pickedIfcFeature"
        />
      </div>
    </template>

    <!-- 模型上传（只显示上传面板） -->
    <template #model-uploader>
      <div class="sidebar-uploader">
        <ModelUploader
          :viewer="viewer"
          :position="selectedPosition"
          :picked-feature="pickedIfcFeature"
        />
      </div>
    </template>
  </Layout>
</template>

<style scoped>
/* ========== 通用侧边栏容器 ========== */
.sidebar-tree,
.sidebar-uploader {
  position: relative;
  width: 100%;
  height: 100%;
  overflow-x: hidden; /* 防止横向溢出 */
  overflow-y: auto;   /* 允许纵向滚动 */
  padding: 12px;      /* 给整个侧边栏一点内边距，让内容不贴边 */
  box-sizing: border-box;
}

/* ========== 构件树模式 ========== */
.sidebar-tree :deep(.model-panel) {
  display: none !important;
}

/* 强制构件树容器自适应侧边栏宽度 */
.sidebar-tree :deep(.component-tree-wrap) {
  display: block !important;
  position: relative !important;
  width: 100% !important;
  max-width: 100% !important;
  height: auto !important;
  margin: 0 !important;
  padding: 0 !important; /* 外层不需要 padding，交给上面的 sidebar-tree 控制 */
  background: transparent !important;
  box-shadow: none !important;
  border: none !important;
  border-radius: 0 !important;
  transform: none !important;
}

/* 确保构件树内部所有元素都自适应，不越界 */
.sidebar-tree :deep(.component-tree-wrap *) {
  position: relative !important;
  left: auto !important;
  top: auto !important;
  right: auto !important;
  transform: none !important;
  max-width: 100% !important; /* 防止内部元素把侧边栏撑破 */
}

/* 清除内部所有背景色，融入侧边栏 */
.sidebar-tree :deep(.component-tree-wrap .panel),
.sidebar-tree :deep(.component-tree-wrap .card),
.sidebar-tree :deep(.component-tree-wrap [class*="panel"]),
.sidebar-tree :deep(.component-tree-wrap [class*="tree"]),
.sidebar-tree :deep(.component-tree-wrap [class*="header"]) {
  background: transparent !important;
  color: #d7dee9 !important;
  box-shadow: none !important;
  border-color: #273140 !important;
}

/* 美化构件树内的按钮和输入框 */
.sidebar-tree :deep(button) {
  border-radius: 4px;
  margin-right: 4px; /* 按钮之间留点缝隙 */
}

.sidebar-tree :deep(input),
.sidebar-tree :deep(select),
.sidebar-tree :deep(.range) {
  background: #1c2633 !important;
  border: 1px solid #344355 !important;
  color: #d7dee9 !important;
  width: 100% !important; /* 输入框占满宽度 */
  box-sizing: border-box;
}

/* ========== 模型上传模式 ========== */
.sidebar-uploader :deep(.component-tree-wrap) {
  display: none !important;
}

.sidebar-uploader :deep(.model-panel) {
  display: flex !important;
  flex-direction: column; /* 改为纵向排列，适应侧边栏 */
  position: relative !important;
  width: 100% !important;
  max-width: 100% !important;
  margin: 0 !important;
  border: none !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: transparent !important;
  color: #d7dee9 !important;
}

.sidebar-uploader :deep(.model-panel .panel-header),
.sidebar-uploader :deep(.model-panel h3),
.sidebar-uploader :deep(.model-panel h4) {
  color: #d7dee9 !important;
  background: transparent !important;
  border-bottom: 1px solid #273140 !important;
}

.sidebar-uploader :deep(.upload-button) {
  background: #2e7d32 !important;
  color: white !important;
  width: 100% !important;
}

.sidebar-uploader :deep(input),
.sidebar-uploader :deep(select) {
  background: #1c2633 !important;
  border: 1px solid #344355 !important;
  color: #d7dee9 !important;
  width: 100% !important;
  box-sizing: border-box;
}

.sidebar-uploader :deep(.hint) {
  color: #ffb74d !important;
}

.sidebar-uploader :deep(.model-card),
.sidebar-uploader :deep(.task-card),
.sidebar-uploader :deep(.transform-panel) {
  background: #1c2633 !important;
  border: 1px solid #273140 !important;
  color: #d7dee9 !important;
  width: 100% !important; /* 卡片也撑满宽度 */
  box-sizing: border-box;
}
</style>