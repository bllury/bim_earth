<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as Cesium from 'cesium'
import type { PickedIfcFeature } from '../lib/ifcPicking'
import type { IfcElementGeometry } from '../services/ifcApi'
import type { IfcElementProperties } from '../types/bim'
import { TREE_WIDTH, useLayoutState } from '../features/layout/useLayoutState'
import { logInfo } from '../features/console/appConsole'

interface SelectionItem {
  key: string
  modelId: string
  ifcGuid: string
  expressId?: string | number
  name: string
  elementType: string
  storey?: string
  geometry?: IfcElementGeometry
  feature: PickedIfcFeature
}

const props = defineProps<{
  viewer: Cesium.Viewer | null
  items: SelectionItem[]
  activeIndex: number
  flightDistanceMultiplier: number
  properties: IfcElementProperties | null
}>()

const emit = defineEmits<{
  select: [index: number]
  updateFlightDistance: [value: number]
  openInspector: []
  close: []
}>()

const PANEL_WIDTH = 330
const { treePanelOpen } = useLayoutState()

const panelElement = ref<HTMLElement | null>(null)
const line = ref({ x1: 0, y1: 0, x2: 0, y2: 0, visible: false })

/** Clamps a numeric value to a safe inclusive range. */
const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max)

const PANEL_STATE_KEY = 'bim-earth-selection-panel-state'

/** Restores the panel position and folded state, clamped to the viewport. */
const readStoredPanelState = () => {
  const fallback = {
    position: {
      x: Math.max(
        12,
        window.innerWidth - PANEL_WIDTH - 16 - (treePanelOpen.value ? TREE_WIDTH : 0),
      ),
      y: 20,
    },
    collapsed: false,
  }

  try {
    const saved = localStorage.getItem(PANEL_STATE_KEY)
    if (!saved) return fallback

    const parsed = JSON.parse(saved) as {
      x?: unknown
      y?: unknown
      collapsed?: unknown
    }
    const x = Number(parsed?.x)
    const y = Number(parsed?.y)
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return { ...fallback, collapsed: parsed?.collapsed === true }
    }

    return {
      position: {
        x: clamp(x, 0, Math.max(0, window.innerWidth - PANEL_WIDTH)),
        y: clamp(y, 0, Math.max(0, window.innerHeight - 40)),
      },
      collapsed: parsed?.collapsed === true,
    }
  } catch (error) {
    logInfo('本地存储不可用，信息面板状态未恢复', error)
    return fallback
  }
}

const storedPanelState = readStoredPanelState()
const panelPosition = ref(storedPanelState.position)
const collapsed = ref(storedPanelState.collapsed)

/** Persists the panel position and folded state. */
const savePanelState = () => {
  try {
    localStorage.setItem(
      PANEL_STATE_KEY,
      JSON.stringify({
        ...panelPosition.value,
        collapsed: collapsed.value,
      }),
    )
  } catch (error) {
    logInfo('本地存储不可用，信息面板状态未保存', error)
  }
}

const dragState = ref<{
  pointerId: number
  startX: number
  startY: number
  originX: number
  originY: number
} | null>(null)

let removePostRender: (() => void) | undefined
let guideFrame: number | undefined

const activeItem = () => props.items[props.activeIndex]

/** Renders an optional element field as displayable text. */
const displayText = (value: unknown) =>
  value === undefined || value === null || value === ''
    ? '未提供'
    : String(value)

/** 基础信息 rows for the active element. */
const basicRows = computed(() => {
  const item = activeItem()
  const basic = props.properties?.basic ?? {}
  return [
    { label: 'IFC GUID', value: displayText(basic.ifcGuid ?? item?.ifcGuid) },
    { label: '名称', value: displayText(basic.name ?? item?.name) },
    {
      label: 'Express ID',
      value: displayText(basic.expressId ?? item?.expressId),
    },
    {
      label: '构件类型',
      value: displayText(basic.elementType ?? item?.elementType),
    },
    { label: '楼层', value: displayText(basic.storey ?? item?.storey) },
    { label: '专业', value: displayText(basic.discipline) },
  ]
})

/** 材料信息 for the active element. */
const materials = computed(() => props.properties?.materials ?? [])

/** Filled-track width for the flight-distance slider (1x ~ 24x). */
const flightDistanceFill = computed(
  () => `${((props.flightDistanceMultiplier - 1) / 23) * 100}%`,
)

/** Schedules one guide-line refresh per animation frame. */
const scheduleGuideLine = () => {
  if (guideFrame !== undefined) return
  guideFrame = window.requestAnimationFrame(() => {
    guideFrame = undefined
    updateGuideLine()
  })
}

/** Starts dragging the panel from its header. */
const handleDragStart = (event: PointerEvent) => {
  if ((event.target as HTMLElement).closest('button')) return

  dragState.value = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: panelPosition.value.x,
    originY: panelPosition.value.y,
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

/** Moves the panel while keeping the guide line attached to it. */
const handleDragMove = (event: PointerEvent) => {
  const state = dragState.value
  if (!state || state.pointerId !== event.pointerId) return

  const width = panelElement.value?.offsetWidth ?? PANEL_WIDTH
  const height = panelElement.value?.offsetHeight ?? 120
  panelPosition.value = {
    x: clamp(
      state.originX + event.clientX - state.startX,
      0,
      Math.max(0, window.innerWidth - width),
    ),
    y: clamp(
      state.originY + event.clientY - state.startY,
      0,
      Math.max(0, window.innerHeight - height),
    ),
  }
  scheduleGuideLine()
}

/** Ends dragging and releases pointer capture. */
const handleDragEnd = (event: PointerEvent) => {
  if (dragState.value?.pointerId !== event.pointerId) return

  dragState.value = null
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture(event.pointerId)) {
    target.releasePointerCapture(event.pointerId)
  }
  scheduleGuideLine()
  savePanelState()
}

/** Collapses or expands the panel body and re-anchors the guide line. */
const toggleCollapsed = () => {
  collapsed.value = !collapsed.value
  scheduleGuideLine()
  savePanelState()
}

/** Reprojects the selected element and connects it to the panel edge. */
const updateGuideLine = () => {
  const viewer = props.viewer
  const item = activeItem()
  const geometryPosition =
    item?.geometry && item.feature.tileset
      ? Cesium.Matrix4.multiplyByPoint(
          item.feature.tileset.modelMatrix,
          new Cesium.Cartesian3(
            item.geometry.center.x,
            item.geometry.center.y,
            item.geometry.center.z,
          ),
          new Cesium.Cartesian3(),
        )
      : undefined
  const position = geometryPosition ?? item?.feature.worldPosition
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

watch(
  () => props.properties,
  scheduleGuideLine,
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
  if (guideFrame !== undefined) {
    window.cancelAnimationFrame(guideFrame)
    guideFrame = undefined
  }
  savePanelState()
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

  <aside
    ref="panelElement"
    class="selection-info-panel"
    :class="{ collapsed }"
    :style="{ left: `${panelPosition.x}px`, top: `${panelPosition.y}px` }"
    @wheel="onWheel"
  >
    <header
      class="selection-header"
      @pointerdown="handleDragStart"
      @pointermove="handleDragMove"
      @pointerup="handleDragEnd"
      @pointercancel="handleDragEnd"
    >
      <button
        type="button"
        class="panel-chevron"
        :class="{ expanded: !collapsed }"
        :aria-expanded="!collapsed"
        :title="collapsed ? '展开信息面板' : '收起信息面板'"
        @pointerdown.stop
        @click="toggleCollapsed"
      >
        <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
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
      <div class="selection-title">
        <strong>当前选中构件</strong>
        <span v-if="items.length"> {{ activeIndex + 1 }} / {{ items.length }}</span>
      </div>
      <button
        type="button"
        class="inspector-button"
        title="打开完整 IFC 构件属性"
        @pointerdown.stop
        @click="emit('openInspector')"
      >
        IFC 构件属性
      </button>
      <button
        type="button"
        class="panel-close"
        title="关闭面板"
        @pointerdown.stop
        @click="emit('close')"
      >
        ✕
      </button>
    </header>

    <template v-if="!collapsed">
      <div
        v-if="items.length"
        class="selection-dots"
        role="tablist"
        aria-label="选中构件"
      >
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

        <section class="info-section">
          <h4>基础信息</h4>
          <p v-for="row in basicRows" :key="row.label">
            <span class="info-label">{{ row.label }}</span>{{ row.value }}
          </p>
        </section>

        <section class="info-section">
          <h4>材料信息</h4>
          <p v-if="!materials.length" class="info-empty">未提供</p>
          <div
            v-for="(material, index) in materials"
            :key="index"
            class="material-item"
          >
            <p><span class="info-label">名称</span>{{ material.name || '未提供' }}</p>
            <p><span class="info-label">类别</span>{{ material.category || '未提供' }}</p>
            <p><span class="info-label">等级</span>{{ material.grade || '未提供' }}</p>
            <p><span class="info-label">厚度</span>{{ material.thickness ?? '未提供' }}</p>
          </div>
        </section>

        <label class="flight-distance">
          飞行距离：{{ props.flightDistanceMultiplier.toFixed(1) }}x
          <input
            class="slider"
            type="range"
            min="1"
            max="24"
            step="1"
            :value="props.flightDistanceMultiplier"
            :style="{ '--slider-fill': flightDistanceFill }"
            @input="emit('updateFlightDistance', parseFloat(($event.target as HTMLInputElement).value))"
          />
        </label>
        <p class="selection-tip">滚轮或点击圆点切换构件信息</p>
      </div>
    </template>
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
  /* Light theme tokens; a dark theme only needs to override this block. */
  --sp-bg: #ffffff;
  --sp-fg: #24292f;
  --sp-muted: #6e7781;
  --sp-border: #e6e8eb;
  --sp-hover: #f3f4f6;
  --sp-accent: #1a56db;
  --sp-accent-hover: #e6f0ff;
  --sp-accent-soft: #f2f7ff;
  --sp-accent-border: #c9dcfb;
  --sp-section-bg: #fafbfc;
  --sp-slider: #123c94;
  --sp-slider-track: #c9ced6;
  --sp-slider-shadow: rgba(15, 23, 42, 0.22);

  position: fixed;
  /* Above the sidebar, tree panel, and console so nothing can cover it. */
  z-index: 1300;
  width: 330px;
  max-height: 62vh;
  display: flex;
  flex-direction: column;
  color: var(--sp-fg);
  background: var(--sp-bg);
  border: 1px solid var(--sp-border);
  border-radius: 8px;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.18);
  font-size: 13px;
}

.selection-header {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--sp-border);
  cursor: move;
  touch-action: none;
  user-select: none;
}

.selection-title {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 5px;
}

.selection-title strong {
  font-size: 12.5px;
  font-weight: 600;
}

.selection-title span {
  color: var(--sp-muted);
  font-size: 11.5px;
}

.panel-chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  color: var(--sp-muted);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: transform 0.15s ease, background-color 0.15s ease;
}

.panel-chevron:hover {
  background: var(--sp-hover);
  color: var(--sp-fg);
}

.panel-chevron.expanded {
  transform: rotate(90deg);
}

.inspector-button {
  flex: 0 0 auto;
  padding: 3px 8px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--sp-accent);
  background: var(--sp-accent-soft);
  border: 1px solid var(--sp-accent-border);
  border-radius: 5px;
  cursor: pointer;
}

.inspector-button:hover {
  background: var(--sp-accent-hover);
}

.panel-close {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  font-size: 12px;
  color: var(--sp-muted);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.panel-close:hover {
  background: var(--sp-hover);
  color: var(--sp-fg);
}

.selection-dots {
  flex: 0 0 auto;
  display: flex;
  gap: 9px;
  padding: 10px 12px 2px;
}

.selection-dot {
  width: 11px;
  height: 11px;
  padding: 0;
  background: #b9c2cc;
  border: 0;
  border-radius: 50%;
  cursor: pointer;
}

.selection-dot.active {
  background: var(--sp-accent);
  box-shadow: 0 0 0 3px var(--sp-accent-soft);
}

.selection-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 12px 12px;
}

.selection-body h3 {
  margin: 0 0 8px;
  overflow: hidden;
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-section {
  margin-bottom: 10px;
}

.info-section h4 {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
}

.info-section p {
  margin: 2px 0;
  font-size: 11.5px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.info-label {
  display: inline-block;
  width: 62px;
  color: var(--sp-muted);
}

.info-empty {
  color: var(--sp-muted);
}

.material-item {
  padding: 6px 8px;
  margin-bottom: 6px;
  background: var(--sp-section-bg);
  border: 1px solid var(--sp-border);
  border-radius: 6px;
}

.selection-tip {
  margin: 8px 0 0;
  color: var(--sp-muted);
  font-size: 11.5px;
}

.flight-distance {
  display: block;
  margin-top: 10px;
  color: var(--sp-muted);
  font-size: 11.5px;
}

.flight-distance input {
  display: block;
  width: 100%;
  margin-top: 4px;
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
    var(--sp-slider) 0 var(--slider-fill, 0%),
    var(--sp-slider-track) var(--slider-fill, 0%) 100%
  );
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border-radius: 50%;
  background: var(--sp-bg);
  border: 2px solid var(--sp-slider);
  box-shadow: 0 1px 2px var(--sp-slider-shadow);
}

.slider::-moz-range-track {
  height: 4px;
  border-radius: 2px;
  background: var(--sp-slider-track);
}

.slider::-moz-range-progress {
  height: 4px;
  border-radius: 2px;
  background: var(--sp-slider);
}

.slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--sp-bg);
  border: 2px solid var(--sp-slider);
}
</style>
