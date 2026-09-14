<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as Cesium from 'cesium'
import type { PickedIfcFeature } from '../lib/ifcPicking'

interface SelectionItem {
  key: string
  ifcGuid: string
  expressId?: string | number
  name: string
  elementType: string
  storey?: string
  feature: PickedIfcFeature
}

const props = defineProps<{
  viewer: Cesium.Viewer | null
  items: SelectionItem[]
  activeIndex: number
  flightDistanceMultiplier: number
}>()

const emit = defineEmits<{
  select: [index: number]
  updateFlightDistance: [value: number]
  close: []
}>()

const line = ref({ x1: 0, y1: 0, x2: 0, y2: 0, visible: false })
const panelElement = ref<HTMLElement | null>(null)
let removePostRender: (() => void) | undefined

const activeItem = () => props.items[props.activeIndex]

/** Reprojects the selected element and connects it to the panel edge. */
const updateGuideLine = () => {
  const viewer = props.viewer
  const position = activeItem()?.feature.worldPosition
  if (!viewer || !position) {
    line.value = { ...line.value, visible: false }
    return
  }

  const windowPosition = Cesium.SceneTransforms.worldToWindowCoordinates(
    viewer.scene,
    position,
  )
  if (!windowPosition) {
    line.value = { ...line.value, visible: false }
    return
  }

  const panelBounds = panelElement.value?.getBoundingClientRect()
  if (!panelBounds) {
    line.value = { ...line.value, visible: false }
    return
  }

  const panelAnchorY = panelBounds.top + Math.min(panelBounds.height / 2, 150)
  line.value = {
    x1: windowPosition.x,
    y1: windowPosition.y,
    x2: panelBounds.left,
    y2: panelAnchorY,
    visible: true,
  }
}

/** Moves the active selection to the previous item. */
const selectPrevious = () => {
  if (props.items.length === 0) return
  emit('select', (props.activeIndex - 1 + props.items.length) % props.items.length)
}

/** Moves the active selection to the next item. */
const selectNext = () => {
  if (props.items.length === 0) return
  emit('select', (props.activeIndex + 1) % props.items.length)
}

/** Uses the mouse wheel to cycle through selected elements. */
const onWheel = (event: WheelEvent) => {
  event.preventDefault()
  if (event.deltaY > 0) selectNext()
  else selectPrevious()
}

watch(
  () => [props.activeIndex, props.items.length, props.viewer],
  updateGuideLine,
  { flush: 'post' },
)

/** Subscribes to Cesium post-render updates for a live guide line. */
const attachViewerListener = (viewer: Cesium.Viewer | null) => {
  removePostRender?.()
  removePostRender = undefined
  if (viewer) {
    const callback = () => updateGuideLine()
    viewer.scene.postRender.addEventListener(callback)
    removePostRender = () => viewer.scene.postRender.removeEventListener(callback)
  }
}

watch(
  () => props.viewer,
  (viewer) => {
    attachViewerListener(viewer)
    updateGuideLine()
  },
)

onMounted(() => {
  attachViewerListener(props.viewer)
  window.addEventListener('resize', updateGuideLine)
  updateGuideLine()
})

onBeforeUnmount(() => {
  removePostRender?.()
  window.removeEventListener('resize', updateGuideLine)
})
</script>

<template>
  <svg v-if="line.visible" class="selection-guide-lines" aria-hidden="true">
    <line
      :x1="line.x1"
      :y1="line.y1"
      :x2="line.x2"
      :y2="line.y2"
    />
    <circle :cx="line.x1" :cy="line.y1" r="4" />
  </svg>

  <aside ref="panelElement" class="selection-info-panel" @wheel="onWheel">
    <header class="selection-header">
      <div>
        <strong>当前选中构件</strong>
        <span v-if="items.length"> {{ activeIndex + 1 }} / {{ items.length }}</span>
      </div>
      <button type="button" @click="emit('close')">关闭</button>
    </header>

    <div v-if="items.length" class="selection-dots" role="tablist" aria-label="选中构件">
      <button
        v-for="(item, index) in items"
        :key="item.key"
        type="button"
        class="selection-dot"
        :class="{ active: index === activeIndex }"
        :aria-label="`切换到第 ${index + 1} 个构件`"
        @click="emit('select', index)"
      />
    </div>

    <div v-if="items.length" class="selection-body">
      <h3>{{ items[activeIndex]?.name }}</h3>
      <p><strong>构件类型：</strong>{{ items[activeIndex]?.elementType || '未提供' }}</p>
      <p><strong>IFC GUID：</strong>{{ items[activeIndex]?.ifcGuid }}</p>
      <p><strong>Express ID：</strong>{{ items[activeIndex]?.expressId ?? '未提供' }}</p>
      <p><strong>楼层：</strong>{{ items[activeIndex]?.storey || '未提供' }}</p>
      <label class="flight-distance">
        飞行距离：{{ props.flightDistanceMultiplier.toFixed(1) }}x
        <input
          type="range"
          min="1"
          max="8"
          step="0.5"
          :value="props.flightDistanceMultiplier"
          @input="emit('updateFlightDistance', parseFloat(($event.target as HTMLInputElement).value))"
        />
      </label>
      <p class="selection-tip">滚轮或点击圆点切换构件信息</p>
    </div>
  </aside>
</template>

<style scoped>
.selection-guide-lines {
  position: fixed;
  inset: 0;
  z-index: 1090;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  overflow: visible;
}

.selection-guide-lines line {
  stroke: #123b75;
  stroke-width: 2;
  stroke-dasharray: 6 4;
}

.selection-guide-lines circle {
  fill: #123b75;
  stroke: white;
  stroke-width: 2;
}

.selection-info-panel {
  position: fixed;
  top: 20px;
  right: 16px;
  z-index: 1100;
  width: 330px;
  max-height: 46vh;
  overflow: hidden;
  color: #1f2937;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #d7e3f1;
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.2);
}

.selection-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid #e5e7eb;
}

.selection-header span {
  color: #64748b;
  font-size: 12px;
}

.selection-header button {
  padding: 4px 8px;
  color: white;
  background: #64748b;
  border: 0;
  border-radius: 4px;
  cursor: pointer;
}

.selection-dots {
  display: flex;
  gap: 9px;
  padding: 12px 14px 4px;
}

.selection-dot {
  width: 11px;
  height: 11px;
  padding: 0;
  background: #aab4c2;
  border: 0;
  border-radius: 50%;
  cursor: pointer;
}

.selection-dot.active {
  background: #1976d2;
  box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.18);
}

.selection-body {
  padding: 10px 14px 14px;
}

.selection-body h3 {
  margin: 0 0 10px;
  overflow: hidden;
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selection-body p {
  margin: 6px 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.selection-tip {
  color: #64748b;
  font-size: 12px !important;
}

.flight-distance {
  display: block;
  margin-top: 12px;
  color: #475569;
  font-size: 12px;
}

.flight-distance input {
  display: block;
  width: 100%;
  margin-top: 5px;
}
</style>
