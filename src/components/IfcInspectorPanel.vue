<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { BimAnnotation, IfcElementProperties } from '../types/bim'
import type { PickedIfcFeature } from '../lib/ifcPicking'
import { TREE_WIDTH, useLayoutState } from '../features/layout/useLayoutState'
import { logInfo } from '../features/console/appConsole'

interface SelectedIfcElement {
  modelId: string
  ifcGuid: string
  feature: PickedIfcFeature
  properties: IfcElementProperties | null
}

const props = defineProps<{
  element: SelectedIfcElement
  annotations: BimAnnotation[]
  business: Record<string, unknown>
}>()

const emit = defineEmits<{
  close: []
  addAnnotation: [
    payload: {
      title: string
      content?: string
      type?: BimAnnotation['type']
      dueDate?: string
    },
  ]
  updateStatus: [annotationId: string, status: BimAnnotation['status']]
  updateBusiness: [key: string, value: unknown]
}>()

const title = ref('')
const content = ref('')
const type = ref<BimAnnotation['type']>('general')
const dueDate = ref('')
const { treePanelOpen } = useLayoutState()

/** Clamps a numeric value to a safe inclusive range. */
const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max)

const INSPECTOR_SIZE_KEY = 'bim-earth-inspector-size'

/** Restores panel size, position, and folded state, clamped to the viewport. */
const readStoredPanelState = () => {
  const defaultSize = {
    width: Math.min(640, Math.max(360, window.innerWidth - 80)),
    height: Math.min(620, Math.max(260, window.innerHeight - 120)),
  }
  const fallback = {
    size: defaultSize,
    // Starts left of the component-tree panel so it never opens underneath it.
    position: {
      x: Math.max(
        12,
        window.innerWidth -
          defaultSize.width -
          16 -
          (treePanelOpen.value ? TREE_WIDTH : 0),
      ),
      y: 20,
    },
    collapsed: false,
  }

  try {
    const saved = localStorage.getItem(INSPECTOR_SIZE_KEY)
    if (!saved) return fallback

    const parsed = JSON.parse(saved) as {
      width?: unknown
      height?: unknown
      x?: unknown
      y?: unknown
      collapsed?: unknown
    }
    const width = Number(parsed?.width)
    const height = Number(parsed?.height)
    if (!Number.isFinite(width) || !Number.isFinite(height)) return fallback

    const size = {
      width: clamp(width, 360, Math.max(360, window.innerWidth - 40)),
      height: clamp(height, 260, Math.max(260, window.innerHeight - 40)),
    }
    const x = Number(parsed?.x)
    const y = Number(parsed?.y)

    return {
      size,
      position:
        Number.isFinite(x) && Number.isFinite(y)
          ? {
              x: clamp(x, 0, Math.max(0, window.innerWidth - size.width)),
              y: clamp(y, 0, Math.max(0, window.innerHeight - 40)),
            }
          : fallback.position,
      collapsed: parsed?.collapsed === true,
    }
  } catch (error) {
    logInfo('本地存储不可用，属性面板状态未恢复', error)
    return fallback
  }
}

const storedPanelState = readStoredPanelState()
const panelSize = ref(storedPanelState.size)
const panelPosition = ref(storedPanelState.position)
const collapsed = ref(storedPanelState.collapsed)

/** Persists size, position, and folded state across closings and reloads. */
const savePanelState = () => {
  try {
    localStorage.setItem(
      INSPECTOR_SIZE_KEY,
      JSON.stringify({
        ...panelSize.value,
        ...panelPosition.value,
        collapsed: collapsed.value,
      }),
    )
  } catch (error) {
    logInfo('本地存储不可用，属性面板状态未保存', error)
  }
}

/** Applies the panel geometry, collapsing to the header when folded. */
const panelStyle = computed(() => ({
  left: `${panelPosition.value.x}px`,
  top: `${panelPosition.value.y}px`,
  width: `${panelSize.value.width}px`,
  height: collapsed.value ? 'auto' : `${panelSize.value.height}px`,
}))

const resizeState = ref<{
  pointerId: number
  startX: number
  startY: number
  originWidth: number
  originHeight: number
} | null>(null)

/** Starts resizing the panel from its bottom-right corner. */
const handleResizeStart = (event: PointerEvent) => {
  resizeState.value = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originWidth: panelSize.value.width,
    originHeight: panelSize.value.height,
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

/** Resizes the panel, keeping it on screen. */
const handleResizeMove = (event: PointerEvent) => {
  const state = resizeState.value
  if (!state || state.pointerId !== event.pointerId) return

  panelSize.value = {
    width: clamp(
      state.originWidth + event.clientX - state.startX,
      360,
      Math.max(360, window.innerWidth - 40),
    ),
    height: clamp(
      state.originHeight + event.clientY - state.startY,
      260,
      Math.max(260, window.innerHeight - 40),
    ),
  }
}

/** Ends a resize gesture and releases pointer capture. */
const handleResizeEnd = (event: PointerEvent) => {
  if (resizeState.value?.pointerId !== event.pointerId) return

  resizeState.value = null
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture(event.pointerId)) {
    target.releasePointerCapture(event.pointerId)
  }
  savePanelState()
}
const dragState = ref<{
  pointerId: number
  startX: number
  startY: number
  originX: number
  originY: number
} | null>(null)

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

const handleDragMove = (event: PointerEvent) => {
  const state = dragState.value
  if (!state || state.pointerId !== event.pointerId) return

  const panelWidth = 380
  const panelHeight = 120
  panelPosition.value = {
    x: Math.min(
      Math.max(0, state.originX + event.clientX - state.startX),
      Math.max(0, window.innerWidth - panelWidth),
    ),
    y: Math.min(
      Math.max(0, state.originY + event.clientY - state.startY),
      Math.max(0, window.innerHeight - panelHeight),
    ),
  }
}

const handleDragEnd = (event: PointerEvent) => {
  if (dragState.value?.pointerId !== event.pointerId) return

  dragState.value = null
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture(event.pointerId)) {
    target.releasePointerCapture(event.pointerId)
  }
  savePanelState()
}

onBeforeUnmount(() => {
  dragState.value = null
  savePanelState()
})

const basic = computed(() => {
  const feature = props.element.feature
  const properties = props.element.properties
  return {
    modelId: props.element.modelId,
    ifcGuid: props.element.ifcGuid,
    name: properties?.basic?.name ?? feature.name ?? '未提供',
    expressId: properties?.basic?.expressId ?? feature.expressId ?? '',
    elementType: properties?.basic?.elementType ?? feature.elementType ?? '未提供',
    storey: properties?.basic?.storey ?? '',
    discipline: properties?.basic?.discipline ?? '',
  }
})

const materials = computed(() => props.element.properties?.materials ?? [])
const propertySets = computed(() => props.element.properties?.propertySets ?? {})
const business = computed(() => props.business ?? {})

/** Raw parsed payload shown in the data-source code block. */
const sourceJson = computed(() => {
  const properties = props.element.properties
  return JSON.stringify(
    {
      modelId: properties?.modelId ?? props.element.modelId,
      ifcGuid: properties?.ifcGuid ?? props.element.ifcGuid,
      expressId: properties?.expressId ?? '',
      basic: properties?.basic ?? {},
      materials: properties?.materials ?? [],
      propertySets: properties?.propertySets ?? {},
      business: props.business ?? {},
    },
    null,
    2,
  )
})

type BusinessFieldKey =
  | 'installationDate'
  | 'warrantyPeriod'
  | 'expiryDate'
  | 'lastInspectionDate'
  | 'nextInspectionDate'
  | 'inspectionCycle'
  | 'maintenanceStatus'
  | 'responsibleUnit'
  | 'remarks'

/** Normalizes a stored business value into the string form controls expect. */
const businessText = (key: BusinessFieldKey) => {
  const value = business.value[key]
  if (value === null || value === undefined) return ''
  return typeof value === 'string' ? value : String(value)
}

const businessStatusText = computed(() => {
  const value = business.value?.maintenanceStatus
  if (!value) return '未配置'
  return String(value)
})

const submit = () => {
  if (!title.value.trim()) return
  emit('addAnnotation', {
    title: title.value.trim(),
    content: content.value.trim() || undefined,
    type: type.value,
    dueDate: dueDate.value || undefined,
  })
  title.value = ''
  content.value = ''
  dueDate.value = ''
  type.value = 'general'
}
</script>

<template>
  <div
    class="ifc-inspector-panel"
    :class="{ collapsed }"
    :style="panelStyle"
  >
    <div
      class="inspector-header"
      @pointerdown="handleDragStart"
      @pointermove="handleDragMove"
      @pointerup="handleDragEnd"
      @pointercancel="handleDragEnd"
    >
      <h3>IFC 构件属性</h3>
      <button
        class="inspector-chevron"
        :class="{ expanded: !collapsed }"
        :aria-expanded="!collapsed"
        :title="collapsed ? '展开属性面板' : '收起属性面板'"
        @pointerdown.stop
        @click="collapsed = !collapsed; savePanelState()"
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
      <button
        class="inspector-close"
        title="关闭属性面板"
        @pointerdown.stop
        @click="emit('close')"
      >
        ✕
      </button>
    </div>

    <div v-if="!collapsed" class="inspector-body">
      <section>
        <h4>基础信息</h4>
        <p><strong>模型 ID：</strong>{{ basic.modelId }}</p>
        <p><strong>IFC GUID：</strong>{{ basic.ifcGuid }}</p>
        <p><strong>名称：</strong>{{ basic.name }}</p>
        <p><strong>Express ID：</strong>{{ basic.expressId }}</p>
        <p><strong>构件类型：</strong>{{ basic.elementType }}</p>
        <p><strong>楼层：</strong>{{ basic.storey || '未提供' }}</p>
        <p><strong>专业：</strong>{{ basic.discipline || '未提供' }}</p>
      </section>

      <section>
        <h4>材料信息</h4>
        <div v-if="materials.length === 0">未提供</div>
        <div class="card-grid material-grid">
          <div
            v-for="(material, index) in materials"
            :key="index"
            class="material-item"
          >
            <p><strong>名称：</strong>{{ material.name ?? '未提供' }}</p>
            <p><strong>类别：</strong>{{ material.category ?? '未提供' }}</p>
            <p><strong>等级：</strong>{{ material.grade ?? '未提供' }}</p>
            <p><strong>厚度：</strong>{{ material.thickness ?? '未提供' }}</p>
          </div>
        </div>
      </section>

      <section>
        <h4>IFC Property Set</h4>
        <div v-if="Object.keys(propertySets).length === 0">未提供</div>
        <div class="card-grid pset-grid">
          <div
            v-for="(properties, psetName) in propertySets"
            :key="psetName"
            class="pset-group"
          >
            <h5>{{ psetName }}</h5>
            <p v-for="(value, key) in properties" :key="key">
              <strong>{{ key }}：</strong>{{ value }}
            </p>
          </div>
        </div>
      </section>

      <section>
        <h4>运维信息</h4>
        <p><strong>维护状态：</strong>{{ businessStatusText }}</p>
        <p v-for="(value, key) in business" :key="key">
          <strong>{{ key }}：</strong>{{ value }}
        </p>
        <div class="business-form">
          <input
            :value="businessText('installationDate')"
            type="date"
            @input="emit('updateBusiness', 'installationDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="businessText('warrantyPeriod')"
            placeholder="保质期"
            @input="emit('updateBusiness', 'warrantyPeriod', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="businessText('expiryDate')"
            type="date"
            @input="emit('updateBusiness', 'expiryDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="businessText('lastInspectionDate')"
            type="date"
            @input="emit('updateBusiness', 'lastInspectionDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="businessText('nextInspectionDate')"
            type="date"
            @input="emit('updateBusiness', 'nextInspectionDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="businessText('inspectionCycle')"
            placeholder="年检周期"
            @input="emit('updateBusiness', 'inspectionCycle', ($event.target as HTMLInputElement).value)"
          />
          <select
            :value="businessText('maintenanceStatus')"
            @change="emit('updateBusiness', 'maintenanceStatus', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">未配置</option>
            <option value="正常">正常</option>
            <option value="即将到期">即将到期</option>
            <option value="已过期">已过期</option>
          </select>
          <input
            :value="businessText('responsibleUnit')"
            placeholder="责任单位"
            @input="emit('updateBusiness', 'responsibleUnit', ($event.target as HTMLInputElement).value)"
          />
          <textarea
            :value="businessText('remarks')"
            placeholder="备注"
            @input="emit('updateBusiness', 'remarks', ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
      </section>

      <section>
        <h4>构件批注</h4>
        <div v-if="annotations.length === 0">暂无批注</div>
        <div class="card-grid annotation-grid">
          <div
            v-for="annotation in annotations"
            :key="annotation.annotationId"
            class="annotation-item"
          >
            <strong>{{ annotation.title }}</strong>
            <p v-if="annotation.content">{{ annotation.content }}</p>
            <p>状态：{{ annotation.status === 'resolved' ? '已解决' : '进行中' }}</p>
            <p v-if="annotation.dueDate">到期日期：{{ annotation.dueDate }}</p>
            <button @click="emit('updateStatus', annotation.annotationId, annotation.status === 'resolved' ? 'open' : 'resolved')">
              {{ annotation.status === 'resolved' ? '重新打开' : '标记已解决' }}
            </button>
          </div>
        </div>

        <div class="annotation-form">
          <input v-model="title" placeholder="批注标题" />
          <textarea v-model="content" placeholder="批注内容" />
          <select v-model="type">
            <option value="general">普通</option>
            <option value="inspection">巡检</option>
            <option value="maintenance">维护</option>
            <option value="issue">问题</option>
          </select>
          <input v-model="dueDate" type="date" />
          <button @click="submit">添加批注</button>
        </div>
      </section>

      <section>
        <h4>数据源</h4>
        <div class="code-block">
          <div class="code-header">
            <span class="code-label">JSON · IFC 构件解析数据源</span>
            <span class="code-meta">{{ props.element.ifcGuid }}</span>
          </div>
          <pre class="code-body">{{ sourceJson }}</pre>
        </div>
      </section>
    </div>

    <div
      v-if="!collapsed"
      class="resize-handle"
      title="拖动调整面板大小"
      @pointerdown.stop="handleResizeStart"
      @pointermove="handleResizeMove"
      @pointerup="handleResizeEnd"
      @pointercancel="handleResizeEnd"
    />
  </div>
</template>

<style scoped>
.ifc-inspector-panel {
  /* Light theme tokens; a dark theme only needs to override this block. */
  --ip-bg: #ffffff;
  --ip-fg: #24292f;
  --ip-muted: #6e7781;
  --ip-border: #e6e8eb;
  --ip-hover: #f3f4f6;
  --ip-accent: #1a56db;
  --ip-accent-hover: #e6f0ff;
  --ip-accent-soft: #f2f7ff;
  --ip-accent-border: #c9dcfb;
  --ip-section-bg: #fafbfc;
  --ip-input-border: #d7dbe0;
  --ip-code-bg: #f8f9fb;
  --ip-code-fg: #1f2937;

  position: fixed;
  /* Highest layer: never covered by sidebar, tree panel, or console. */
  z-index: 1310;
  display: flex;
  flex-direction: column;
  color: var(--ip-fg);
  background: var(--ip-bg);
  border: 1px solid var(--ip-border);
  border-radius: 8px;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.22);
  font-size: 13px;
}

.inspector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: 0 0 auto;
  padding: 8px 10px;
  border-bottom: 1px solid var(--ip-border);
  cursor: move;
  touch-action: none;
  user-select: none;
}

.inspector-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.inspector-header button,
.annotation-item button,
.annotation-form button {
  padding: 3px 8px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--ip-accent);
  background: var(--ip-accent-soft);
  border: 1px solid var(--ip-accent-border);
  border-radius: 5px;
  cursor: pointer;
}

.inspector-header button:hover,
.annotation-item button:hover,
.annotation-form button:hover {
  background: var(--ip-accent-hover);
}

.inspector-header .inspector-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  font-size: 13px;
  color: var(--ip-muted);
  background: transparent;
  border: none;
}

.inspector-header .inspector-close:hover {
  color: var(--ip-fg);
  background: var(--ip-hover);
}

.inspector-chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  margin-left: auto;
  padding: 0;
  color: var(--ip-muted);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: transform 0.15s ease, background-color 0.15s ease;
}

.inspector-chevron:hover {
  color: var(--ip-fg);
  background: var(--ip-hover);
}

.inspector-chevron.expanded {
  transform: rotate(90deg);
}

.inspector-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
}

/* Module cards reflow into more columns as the window is resized. */
.card-grid {
  display: grid;
  gap: 8px;
}

.material-grid {
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}

.pset-grid {
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
}

.annotation-grid {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
}

.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(
    135deg,
    transparent 0 55%,
    var(--ip-border) 55% 65%,
    transparent 65% 75%,
    var(--ip-muted) 75% 85%,
    transparent 85%
  );
  border-bottom-right-radius: 8px;
}

section {
  margin-bottom: 14px;
}

h4 {
  margin: 0 0 6px 0;
  font-size: 12.5px;
  font-weight: 600;
}

h5 {
  margin: 6px 0 3px 0;
  font-size: 12px;
  color: var(--ip-fg);
}

p {
  margin: 2px 0;
  font-size: 11.5px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.material-item,
.pset-group,
.annotation-item {
  padding: 6px 8px;
  margin-bottom: 6px;
  background: var(--ip-section-bg);
  border: 1px solid var(--ip-border);
  border-radius: 6px;
}

.code-block {
  border: 1px solid var(--ip-border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--ip-code-bg);
}

.code-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: var(--ip-section-bg);
  border-bottom: 1px solid var(--ip-border);
  font-size: 11px;
}

.code-label {
  font-weight: 600;
  color: var(--ip-fg);
}

.code-meta {
  margin-left: auto;
  min-width: 0;
  color: var(--ip-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.code-body {
  margin: 0;
  padding: 8px;
  max-height: 240px;
  overflow: auto;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: var(--ip-code-fg);
  white-space: pre;
}

.annotation-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.annotation-form input,
.annotation-form textarea,
.annotation-form select {
  padding: 5px 7px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--ip-fg);
  background: var(--ip-bg);
  border: 1px solid var(--ip-input-border);
  border-radius: 5px;
}

.business-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.business-form input,
.business-form select,
.business-form textarea {
  padding: 5px 7px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--ip-fg);
  background: var(--ip-bg);
  border: 1px solid var(--ip-input-border);
  border-radius: 5px;
}

.business-form textarea {
  grid-column: 1 / -1;
}
</style>
