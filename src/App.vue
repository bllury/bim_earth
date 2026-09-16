<script setup lang="ts">
import { shallowRef } from 'vue'
import * as Cesium from 'cesium'
import EarthViewer from './components/EarthViewer.vue'
import CoordinatePanel from './components/CoordinatePanel.vue'
import ModelUploader from './components/ModelUploader.vue'
import type { PickedIfcFeature } from './lib/ifcPicking'

const viewer = shallowRef<Cesium.Viewer | null>(null)
const selectedPosition = shallowRef<Cesium.Cartesian3 | null>(null)
const pickedIfcFeature = shallowRef<PickedIfcFeature | null>(null)

const handleViewerReady = (value: Cesium.Viewer) => {
  viewer.value = value
}

const handlePositionChange = (position: Cesium.Cartesian3) => {
  selectedPosition.value = position
}

const handleIfcFeaturePicked = (feature: PickedIfcFeature | null) => {
  pickedIfcFeature.value = feature
}
</script>

<template>
  <div class="app-shell">
    <EarthViewer
      :selected-position="selectedPosition"
      @viewer-ready="handleViewerReady"
      @position-change="handlePositionChange"
      @ifc-feature-picked="handleIfcFeaturePicked"
    />
    <CoordinatePanel
      :viewer="viewer"
      :selected-position="selectedPosition"
      @coordinate-selected="handlePositionChange"
    />
    <ModelUploader
      :viewer="viewer"
      :position="selectedPosition"
      :picked-feature="pickedIfcFeature"
    />
  </div>
</template>

<style scoped>
.app-shell {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
</style>
