<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { BimAnnotation, IfcElementProperties } from '../types/bim'
import type { PickedIfcFeature } from '../lib/ifcPicking'

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
const panelPosition = ref({
  x: Math.max(20, window.innerWidth - 420),
  y: 20,
})
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
}

onBeforeUnmount(() => {
  dragState.value = null
})

const basic = computed(() => {
  const feature = props.element.feature
  const properties = props.element.properties
  return {
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
    :style="{ left: `${panelPosition.x}px`, top: `${panelPosition.y}px` }"
  >
    <div
      class="inspector-header"
      @pointerdown="handleDragStart"
      @pointermove="handleDragMove"
      @pointerup="handleDragEnd"
      @pointercancel="handleDragEnd"
    >
      <h3>IFC 构件属性</h3>
      <button @click="emit('close')">关闭</button>
    </div>

    <div class="inspector-body">
      <section>
        <h4>基础信息</h4>
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
        <div v-for="(material, index) in materials" :key="index" class="material-item">
          <p><strong>名称：</strong>{{ material.name ?? '未提供' }}</p>
          <p><strong>类别：</strong>{{ material.category ?? '未提供' }}</p>
          <p><strong>等级：</strong>{{ material.grade ?? '未提供' }}</p>
          <p><strong>厚度：</strong>{{ material.thickness ?? '未提供' }}</p>
        </div>
      </section>

      <section>
        <h4>IFC Property Set</h4>
        <div v-if="Object.keys(propertySets).length === 0">未提供</div>
        <div v-for="(properties, psetName) in propertySets" :key="psetName" class="pset-group">
          <h5>{{ psetName }}</h5>
          <p v-for="(value, key) in properties" :key="key">
            <strong>{{ key }}：</strong>{{ value }}
          </p>
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
            :value="business.installationDate"
            type="date"
            @input="emit('updateBusiness', 'installationDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="business.warrantyPeriod"
            placeholder="保质期"
            @input="emit('updateBusiness', 'warrantyPeriod', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="business.expiryDate"
            type="date"
            @input="emit('updateBusiness', 'expiryDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="business.lastInspectionDate"
            type="date"
            @input="emit('updateBusiness', 'lastInspectionDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="business.nextInspectionDate"
            type="date"
            @input="emit('updateBusiness', 'nextInspectionDate', ($event.target as HTMLInputElement).value)"
          />
          <input
            :value="business.inspectionCycle"
            placeholder="年检周期"
            @input="emit('updateBusiness', 'inspectionCycle', ($event.target as HTMLInputElement).value)"
          />
          <select
            :value="business.maintenanceStatus"
            @change="emit('updateBusiness', 'maintenanceStatus', ($event.target as HTMLSelectElement).value)"
          >
            <option value="">未配置</option>
            <option value="正常">正常</option>
            <option value="即将到期">即将到期</option>
            <option value="已过期">已过期</option>
          </select>
          <input
            :value="business.responsibleUnit"
            placeholder="责任单位"
            @input="emit('updateBusiness', 'responsibleUnit', ($event.target as HTMLInputElement).value)"
          />
          <textarea
            :value="business.remarks"
            placeholder="备注"
            @input="emit('updateBusiness', 'remarks', ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
      </section>

      <section>
        <h4>构件批注</h4>
        <div v-if="annotations.length === 0">暂无批注</div>
        <div v-for="annotation in annotations" :key="annotation.annotationId" class="annotation-item">
          <strong>{{ annotation.title }}</strong>
          <p v-if="annotation.content">{{ annotation.content }}</p>
          <p>状态：{{ annotation.status === 'resolved' ? '已解决' : '进行中' }}</p>
          <p v-if="annotation.dueDate">到期日期：{{ annotation.dueDate }}</p>
          <button @click="emit('updateStatus', annotation.annotationId, annotation.status === 'resolved' ? 'open' : 'resolved')">
            {{ annotation.status === 'resolved' ? '重新打开' : '标记已解决' }}
          </button>
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
    </div>
  </div>
</template>

<style scoped>
.ifc-inspector-panel {
  position: fixed;
  z-index: 1200;
  width: 380px;
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}

.inspector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #ddd;
  cursor: move;
  touch-action: none;
  user-select: none;
}

.inspector-header h3 {
  margin: 0;
}

.inspector-header button,
.annotation-item button,
.annotation-form button {
  padding: 5px 8px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.inspector-body {
  overflow-y: auto;
  padding: 12px;
}

section {
  margin-bottom: 16px;
}

h4 {
  margin: 0 0 8px 0;
}

h5 {
  margin: 8px 0 4px 0;
}

p {
  margin: 3px 0;
  font-size: 13px;
}

.material-item,
.pset-group,
.annotation-item {
  padding: 8px;
  margin-bottom: 8px;
  background: #f5f5f5;
  border-radius: 4px;
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
  padding: 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}

.business-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 8px;
}

.business-form input,
.business-form select,
.business-form textarea {
  padding: 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}

.business-form textarea {
  grid-column: 1 / -1;
}
</style>
