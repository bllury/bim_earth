<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import * as Cesium from 'cesium'
import {
  MAX_MODEL_SCALE,
  MIN_MODEL_SCALE,
  createModelTransform,
  worldPointToModel,
} from '../lib/modelTransforms'
import {
  fetchIfcElementProperties,
  fetchIfcMetadata,
  fetchRecentIfcModel,
  deleteIfcRevision,
  resolveIfcAssetUrl,
  saveIfcElementBusiness,
  saveIfcCamera,
  type CameraState,
  type IfcElementGeometry,
  type IfcMetadataElement,
} from '../services/ifcApi'
import {
  useIfcConversion,
  type IfcConversionTask,
} from '../features/ifc/useIfcConversion'
import {
  logError,
  logInfo,
  logWarn,
  type ConsoleLogLevel,
} from '../features/console/appConsole'
import {
  CONSOLE_HANDLE_HEIGHT,
  CONSOLE_HEIGHT,
  useLayoutState,
} from '../features/layout/useLayoutState'
import { useModelPrimitives } from '../features/viewer/useModelPrimitives'
import {
  useBimModelState,
  type LoadedIfcModelState,
  type UploadedModelState,
} from '../features/viewer/useBimModelState'
import { hiddenElementKeys } from '../features/viewer/selectionState'
import type { PickedIfcFeature } from '../lib/ifcPicking'
import type {
  BimAnnotation,
  BimTreeNode,
  IfcConversionStatus,
  IfcElementProperties,
} from '../types/bim'
import IfcInspectorPanel from './IfcInspectorPanel.vue'
import BimComponentTree from './BimComponentTree.vue'
import SelectionInfoPanel from './SelectionInfoPanel.vue'

const RECENT_RESTORE_KEY = 'bim-earth-allow-recent-restore'

const props = defineProps<{
  viewer: Cesium.Viewer | null
  position: Cesium.Cartesian3 | null
  pickedFeature: PickedIfcFeature | null
}>()

const ifcTasks = ref<IfcConversionTask[]>([])
const {
  glbModels,
  ifcModels,
  selectedModelId,
  coordinateInputs,
  scaleDrafts,
  rotationDrafts,
} = useBimModelState()

/** Number of models, conversions, and pending uploads listed in the sidebar. */
const modelCount = computed(
  () => glbModels.value.length + ifcModels.value.length + ifcTasks.value.length,
)

const isUploading = ref(false)
const isInspectorOpen = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const { modelPanelOpen, consoleOpen } = useLayoutState()

const {
  glbPrimitives,
  ifcTilesets,
  ifcTilesetModelIds,
  removeGlb,
  removeTileset,
  dispose: disposeModelPrimitives,
} = useModelPrimitives()
const loadingIfcModelIds = new Set<string>()
const ifcModelTaskIds = new Map<string, string>()
const ifcProjectIds = new Map<string, string>()
const cameraSaveTimers = new Map<string, number>()
const cameraChangeHandlers = new Map<string, () => void>()
const businessSyncTimers = new Map<string, number>()
const pendingBusinessSync = new Map<string, Record<string, unknown>>()
const BUSINESS_SYNC_DELAY = 500
const recentModelRestoreStarted = ref(false)
const removedIfcModelIds = new Set<string>()
const ifcPropertyCache = new Map<string, IfcElementProperties>()
const ifcGeometryByKey = new Map<string, IfcElementGeometry>()
const ifcMetadataByKey = new Map<string, IfcMetadataElement>()

const selectedIfcElement = shallowRef<{
  modelId: string
  ifcGuid: string
  feature: PickedIfcFeature
  properties: IfcElementProperties | null
} | null>(null)

const activeIfcHighlight = shallowRef<{
  feature: Cesium.Cesium3DTileFeature
  originalColor: Cesium.Color
} | null>(null)

const componentTreeRoots = shallowRef<BimTreeNode[]>([])
const treeSelectionMode = ref<'single' | 'multi'>('single')
const selectedTreeKey = ref<string | null>(null)
const multiSelectedKeys = ref<Set<string>>(new Set())
const selectionOrder = ref<string[]>([])
const selectionItems = shallowRef<SelectionGuideItem[]>([])
const activeSelectionIndex = ref(0)
const readFlightDistanceMultiplier = () => {
  try {
    const stored = Number(localStorage.getItem('bim-earth-flight-distance'))
    return Number.isFinite(stored) ? Math.min(Math.max(stored, 1), 24) : 2.8
  } catch (error) {
    logInfo('本地存储不可用，飞行距离设置使用默认值', error)
    return 2.8
  }
}
const flightDistanceMultiplier = ref(readFlightDistanceMultiplier())
const multiUnselectedOpacity = ref(0.1)
const hiddenTreeKeys = ref<Set<string>>(new Set())
const isolatedTreeKey = ref<string | null>(null)

const featureOriginalColors = new Map<string, Cesium.Color>()
const featureRegistry = new Map<string, Cesium.Cesium3DTileFeature>()
const flashingFeatures = new Map<string, Cesium.Cesium3DTileFeature>()
const activeGuideFeatureKey = ref<string | null>(null)
let flashingTimer: number | undefined
let flashingOn = false

const annotations = ref<BimAnnotation[]>([])
const businessByElement = ref<Record<string, Record<string, unknown>>>({})

const readRecentRestoreEnabled = () => {
  try {
    return localStorage.getItem(RECENT_RESTORE_KEY) !== 'false'
  } catch (error) {
    logInfo('本地存储不可用，最近模型恢复默认开启', error)
    return true
  }
}

const setRecentRestoreEnabled = (enabled: boolean) => {
  try {
    localStorage.setItem(RECENT_RESTORE_KEY, String(enabled))
  } catch (error) {
    logInfo('本地存储不可用，无法保存最近模型恢复开关', error)
    // Storage may be unavailable; persistence of this flag is best-effort.
  }
}

interface SelectionGuideItem {
  key: string
  modelId: string
  ifcGuid: string
  expressId?: string | number
  name: string
  elementType: string
  storey?: string
  feature: PickedIfcFeature
  geometry?: IfcElementGeometry
}

const loadAnnotations = () => {
  try {
    const saved = localStorage.getItem('bim-earth-annotations')
    if (saved) {
      annotations.value = JSON.parse(saved) as BimAnnotation[]
    }
  } catch (error) {
    logInfo('本地存储不可用，构件批注未恢复', error)
    annotations.value = []
  }
}

/** Persists user-created annotations in browser storage. */
const saveAnnotations = () => {
  localStorage.setItem(
    'bim-earth-annotations',
    JSON.stringify(annotations.value),
  )
}

/** Restores per-element business fields from browser storage. */
const loadBusinessData = () => {
  try {
    const saved = localStorage.getItem('bim-earth-business')
    if (saved) {
      businessByElement.value = JSON.parse(saved) as Record<
        string,
        Record<string, unknown>
      >
    }
  } catch (error) {
    logInfo('本地存储不可用，运维字段未恢复', error)
    businessByElement.value = {}
  }
}

/** Persists per-element business fields in browser storage. */
const saveBusinessData = () => {
  localStorage.setItem(
    'bim-earth-business',
    JSON.stringify(businessByElement.value),
  )
}

/** Removes local annotations and business fields belonging to a deleted model. */
const removeLocalModelData = (modelId: string) => {
  annotations.value = annotations.value.filter((item) => item.modelId !== modelId)
  Object.keys(businessByElement.value).forEach((key) => {
    if (key.startsWith(`${modelId}:`)) {
      delete businessByElement.value[key]
    }
  })
  saveAnnotations()
  saveBusinessData()
}

loadAnnotations()
loadBusinessData()

/** Returns a file's lowercase extension for upload dispatch. */
const getFileExtension = (file: File) => file.name.split('.').pop()?.toLowerCase()

/** Creates a stable-enough client-side identifier for local model records. */
const createModelId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** Creates an identifier specifically for converted IFC models. */
const createIfcModelId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `ifc-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** Converts a conversion status into user-facing Chinese text. */
const getIfcStatusText = (status: IfcConversionStatus) => {
  if (status === 'pending') return '等待中'
  if (status === 'processing') return '转换中'
  if (status === 'completed') return '已完成'
  return '失败'
}

/** Progress fill width for a task card: only running tasks fill up. */
const taskProgress = (task: IfcConversionTask) => {
  if (task.status === 'failed') return '0%'
  const value = Math.min(Math.max(task.progress ?? 0, 0), 100)
  return `${value}%`
}

/** Returns the status color used by the conversion task list. */
const getIfcStatusColor = (status: IfcConversionStatus) => {
  if (status === 'pending') return '#ff9800'
  if (status === 'processing') return '#2196f3'
  if (status === 'completed') return '#4caf50'
  return '#f44336'
}

/** Clamps a numeric value to a safe inclusive range. */
const clamp = (value: number, min: number, max: number) => {
  return Math.min(Math.max(value, min), max)
}

/** Reads the minimum local vertical coordinate from a GLTF document. */
const getGltfLocalVerticalMinimum = (gltf: Record<string, unknown>) => {
  const accessors = (gltf.accessors ?? []) as Array<{
    min?: number[]
  }>
  let minimumY = Number.POSITIVE_INFINITY

  const meshes = (gltf.meshes ?? []) as Array<{
    primitives?: Array<{ attributes?: Record<string, number> }>
  }>
  meshes.forEach((mesh) => {
    mesh.primitives?.forEach((primitive) => {
      const positionAccessorIndex = primitive.attributes?.POSITION
      if (typeof positionAccessorIndex !== 'number') return

      const accessor = accessors[positionAccessorIndex]
      const minY = accessor?.min?.[1]
      if (typeof minY === 'number' && Number.isFinite(minY)) {
        minimumY = Math.min(minimumY, minY)
      }
    })
  })

  return Number.isFinite(minimumY) ? minimumY : 0
}

const GLB_MAGIC = 0x46546c67
const GLB_JSON_CHUNK_TYPE = 0x4e4f534a

/** Parses the JSON chunk from a GLB file. */
const parseGlbJson = async (file: File) => {
  const buffer = await file.arrayBuffer()
  const view = new DataView(buffer)

  if (view.getUint32(0, true) !== GLB_MAGIC) {
    throw new Error('无效的 GLB 文件')
  }

  const jsonChunkLength = view.getUint32(12, true)
  const jsonChunkType = view.getUint32(16, true)

  if (jsonChunkType !== GLB_JSON_CHUNK_TYPE) {
    throw new Error('GLB 文件缺少 JSON 数据块')
  }

  const jsonBytes = new Uint8Array(buffer, 20, jsonChunkLength)
  const jsonText = new TextDecoder().decode(jsonBytes)
  return JSON.parse(jsonText)
}

const ARRAY_BUFFER = 34962
const ELEMENT_ARRAY_BUFFER = 34963

const semanticAccessorType: Record<string, string> = {
  POSITION: 'VEC3',
  NORMAL: 'VEC3',
  TANGENT: 'VEC4',
  TEXCOORD_0: 'VEC2',
  TEXCOORD_1: 'VEC2',
  COLOR_0: 'VEC4',
  JOINTS_0: 'VEC4',
  WEIGHTS_0: 'VEC4',
}

/** Checks whether a GLTF accessor stores integer indices. */
const isIndexComponentType = (componentType: number | undefined) => {
  return componentType === 5121 || componentType === 5123 || componentType === 5125
}

/** Repairs missing GLTF buffer targets before Cesium consumes the model. */
const repairGltfAccessorReferences = (gltf: {
  accessors?: Array<{
    type?: string
    componentType?: number
    bufferView?: number
  }>
  bufferViews?: Array<{ target?: number }>
  meshes?: Array<{
    primitives?: Array<{
      attributes?: Record<string, number>
      indices?: number
    }>
  }>
}) => {
  const accessors = gltf.accessors ?? []
  const bufferViews = gltf.bufferViews ?? []

  const getBufferViewTarget = (accessor?: { bufferView?: number }) => {
    if (accessor?.bufferView === undefined) return undefined
    const bufferView = bufferViews[accessor.bufferView]
    return bufferView?.target
  }

  const findAccessor = (
    type: string,
    target: number,
    componentType?: number,
  ) => {
    return accessors.findIndex((accessor) => {
      if (!accessor || accessor.type !== type) return false
      if (getBufferViewTarget(accessor) !== target) return false
      if (componentType !== undefined && accessor.componentType !== componentType) {
        return false
      }
      return true
    })
  }

  gltf.meshes?.forEach((mesh) => {
    mesh.primitives?.forEach((primitive) => {
      const attributes = primitive.attributes ?? {}

      for (const [semantic, accessorIndex] of Object.entries(attributes)) {
        const expectedType = semanticAccessorType[semantic]
        if (!expectedType) continue

        const numericIndex = Number(accessorIndex)
        const currentAccessor = accessors[numericIndex]
        const currentTarget = getBufferViewTarget(currentAccessor)
        const isInvalid =
          !currentAccessor ||
          currentAccessor.type !== expectedType ||
          (currentTarget !== undefined && currentTarget !== ARRAY_BUFFER)

        if (isInvalid) {
          const replacement = findAccessor(expectedType, ARRAY_BUFFER)
          if (replacement !== -1) {
            primitive.attributes![semantic] = replacement
          }
        }
      }

      if (typeof primitive.indices === 'number') {
        const currentAccessor = accessors[primitive.indices]
        const currentTarget = getBufferViewTarget(currentAccessor)
        const isInvalid =
          !currentAccessor ||
          currentAccessor.type !== 'SCALAR' ||
          !isIndexComponentType(currentAccessor.componentType) ||
          (currentTarget !== undefined && currentTarget !== ELEMENT_ARRAY_BUFFER)

        if (isInvalid) {
          const replacement = findAccessor('SCALAR', ELEMENT_ARRAY_BUFFER)
          if (replacement !== -1) {
            primitive.indices = replacement
          }
        }
      }
    })
  })
}

const componentByteSize: Record<number, number> = {
  5120: 1,
  5121: 1,
  5122: 2,
  5123: 2,
  5125: 4,
  5126: 4,
}

const typeComponentCount: Record<string, number> = {
  SCALAR: 1,
  VEC2: 2,
  VEC3: 3,
  VEC4: 4,
  MAT2: 4,
  MAT3: 9,
  MAT4: 16,
}

/** Decodes a base64 buffer into bytes for GLTF editing. */
const base64ToUint8Array = (base64: string) => {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

/** Encodes bytes as base64 for embedding back into GLTF JSON. */
const uint8ArrayToBase64 = (bytes: Uint8Array) => {
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, Math.min(i + chunkSize, bytes.length))
    binary += String.fromCharCode(...chunk)
  }
  return btoa(binary)
}

/** Returns a typed view over one GLTF accessor's binary data. */
const getGltfAccessorView = (gltf: {
  accessors?: Array<{
    bufferView?: number
    componentType?: number
    type?: string
    count?: number
    byteOffset?: number
  }>
  bufferViews?: Array<{
    buffer?: number
    byteOffset?: number
    target?: number
  }>
  buffers?: Array<{ uri?: string }>
}, accessorIndex: number) => {
  const accessor = gltf.accessors?.[accessorIndex]
  const bufferView = gltf.bufferViews?.[accessor?.bufferView ?? -1]
  const buffer = gltf.buffers?.[bufferView?.buffer ?? -1]

  if (!accessor || !bufferView || !buffer || typeof buffer.uri !== 'string') {
    return undefined
  }

  if (!buffer.uri.startsWith('data:')) return undefined

  const commaIndex = buffer.uri.indexOf(',')
  if (commaIndex === -1) return undefined

  const bytes = base64ToUint8Array(buffer.uri.slice(commaIndex + 1))
  const componentSize = componentByteSize[accessor.componentType ?? -1]
  const componentCount = typeComponentCount[accessor.type ?? '']
  if (!componentSize || !componentCount || accessor.count === undefined) return undefined

  const byteOffset = (bufferView.byteOffset ?? 0) + (accessor.byteOffset ?? 0)
  const byteLength = accessor.count * componentSize * componentCount

  if (byteOffset + byteLength > bytes.length) return undefined

  return new DataView(bytes.buffer, bytes.byteOffset + byteOffset, byteLength)
}

/** Reads floating-point accessor data from a GLTF document. */
const readFloat32Array = (gltf: {
  accessors?: Array<{
    componentType?: number
    type?: string
    count?: number
  }>
}, accessorIndex: number) => {
  const accessor = gltf.accessors?.[accessorIndex]
  if (!accessor || accessor.componentType !== 5126 || accessor.type !== 'VEC3') {
    return undefined
  }

  const view = getGltfAccessorView(gltf as never, accessorIndex)
  if (!view || accessor.count === undefined) return undefined

  return new Float32Array(view.buffer, view.byteOffset, accessor.count * 3)
}

/** Reads index accessor data from a GLTF document. */
const readIndexArray = (gltf: {
  accessors?: Array<{
    componentType?: number
    type?: string
    count?: number
  }>
}, accessorIndex: number) => {
  const accessor = gltf.accessors?.[accessorIndex]
  if (!accessor || accessor.type !== 'SCALAR' || accessor.count === undefined) {
    return undefined
  }

  const view = getGltfAccessorView(gltf as never, accessorIndex)
  if (!view) return undefined

  if (accessor.componentType === 5121) {
    return new Uint8Array(view.buffer, view.byteOffset, accessor.count)
  }
  if (accessor.componentType === 5123) {
    return new Uint16Array(view.buffer, view.byteOffset, accessor.count)
  }
  if (accessor.componentType === 5125) {
    return new Uint32Array(view.buffer, view.byteOffset, accessor.count)
  }

  return undefined
}

/** Adds flat normals to GLTF primitives that do not provide normals. */
const ensureFlatNormals = (gltf: {
  meshes?: Array<{
    primitives?: Array<{
      attributes?: Record<string, number>
      indices?: number
    }>
  }>
  accessors?: Array<{
    bufferView?: number
    componentType?: number
    count?: number
    type?: string
  }>
  buffers?: Array<{ byteLength: number; uri?: string }>
  bufferViews?: Array<{
    buffer?: number
    byteOffset?: number
    byteLength?: number
    target?: number
  }>
}) => {
  gltf.meshes?.forEach((mesh) => {
    mesh.primitives?.forEach((primitive) => {
      if (primitive.attributes?.NORMAL !== undefined) return

      const positionAccessorIndex = primitive.attributes?.POSITION
      const indicesAccessorIndex = primitive.indices
      if (typeof positionAccessorIndex !== 'number' || typeof indicesAccessorIndex !== 'number') {
        return
      }

      const positionAccessor = gltf.accessors?.[positionAccessorIndex]
      const positions = readFloat32Array(gltf as never, positionAccessorIndex)
      const indices = readIndexArray(gltf as never, indicesAccessorIndex)
      if (!positionAccessor || !positions || !indices || positionAccessor.count === undefined) return

      const normals = new Float32Array(positionAccessor.count * 3)

      for (let i = 0; i + 2 < indices.length; i += 3) {
        const i0 = indices[i] * 3
        const i1 = indices[i + 1] * 3
        const i2 = indices[i + 2] * 3

        const ax = positions[i0]
        const ay = positions[i0 + 1]
        const az = positions[i0 + 2]

        const bx = positions[i1] - ax
        const by = positions[i1 + 1] - ay
        const bz = positions[i1 + 2] - az

        const cx = positions[i2] - ax
        const cy = positions[i2 + 1] - ay
        const cz = positions[i2 + 2] - az

        const nx = by * cz - bz * cy
        const ny = bz * cx - bx * cz
        const nz = bx * cy - by * cx

        for (const index of [i0, i1, i2]) {
          normals[index] += nx
          normals[index + 1] += ny
          normals[index + 2] += nz
        }
      }

      for (let i = 0; i < normals.length; i += 3) {
        const x = normals[i]
        const y = normals[i + 1]
        const z = normals[i + 2]
        const length = Math.sqrt(x * x + y * y + z * z)
        if (length > 0) {
          normals[i] = x / length
          normals[i + 1] = y / length
          normals[i + 2] = z / length
        }
      }

      const normalBytes = new Uint8Array(normals.buffer)
      gltf.buffers = gltf.buffers ?? []
      gltf.bufferViews = gltf.bufferViews ?? []
      const normalBufferIndex = gltf.buffers.length
      gltf.buffers.push({
        byteLength: normalBytes.byteLength,
        uri: `data:application/octet-stream;base64,${uint8ArrayToBase64(normalBytes)}`,
      })

      const normalBufferViewIndex = gltf.bufferViews.length
      gltf.bufferViews.push({
        buffer: normalBufferIndex,
        byteOffset: 0,
        byteLength: normalBytes.byteLength,
        target: ARRAY_BUFFER,
      })

      gltf.accessors = gltf.accessors ?? []
      const normalAccessorIndex = gltf.accessors.length
      gltf.accessors.push({
        bufferView: normalBufferViewIndex,
        componentType: 5126,
        count: positionAccessor.count,
        type: 'VEC3',
      })

      primitive.attributes!.NORMAL = normalAccessorIndex
    })
  })
}

/** Waits until a Cesium model is ready or reports an error. */
const waitForModelReady = (model: Cesium.Model) => {
  return new Promise<void>((resolve, reject) => {
    if (model.ready) {
      resolve()
      return
    }

    const removeReadyListener = model.readyEvent.addEventListener(() => {
      removeReadyListener()
      removeErrorListener()
      resolve()
    })

    const removeErrorListener = model.errorEvent.addEventListener((error: unknown) => {
      removeReadyListener()
      removeErrorListener()
      reject(error)
    })
  })
}

/** Flies the camera to a loaded GLB model. */
const flyToModel = (model: UploadedModelState) => {
  const record = glbPrimitives.get(model.modelId)
  if (!props.viewer || !record) return

  const radius = record.primitive.boundingSphere.radius
  const range = Math.max(30, radius * 4)
  props.viewer.camera.flyToBoundingSphere(record.primitive.boundingSphere, {
    duration: 2,
    offset: new Cesium.HeadingPitchRange(0, -0.5, range),
  })
}

/** Flies the camera to a loaded IFC tileset. */
const flyToIfcModel = (model: LoadedIfcModelState) => {
  const tileset = ifcTilesets.get(model.modelId)
  if (!props.viewer || !tileset) return

  const boundingSphere = tileset.boundingSphere
  const range = Math.max(30, boundingSphere.radius * 4)
  props.viewer.camera.flyToBoundingSphere(boundingSphere, {
    duration: 2,
    offset: new Cesium.HeadingPitchRange(0, -0.5, range),
  })
}

/** Removes an IFC model and all associated selection state. */
const removeIfcModel = async (modelId: string) => {
  const model = ifcModels.value.find((item) => item.modelId === modelId)
  const taskId = ifcModelTaskIds.get(modelId)
  if (taskId) {
    try {
      await deleteIfcRevision(taskId)
    } catch (error) {
      logError('IFC 持久化模型删除失败:', error)
      return
    }
  }
  setRecentRestoreEnabled(false)
  removedIfcModelIds.add(modelId)
  removeTileset(props.viewer, modelId)
  loadingIfcModelIds.delete(modelId)

  ifcModels.value = ifcModels.value.filter((item) => item.modelId !== modelId)
  if (taskId) {
    removeIfcTask(taskId)
  }
  ifcTasks.value = ifcTasks.value.filter(
    (task) => task.taskId !== taskId && task.fileName !== model?.name,
  )
  ifcModelTaskIds.delete(modelId)

  if (selectedIfcElement.value?.modelId === modelId) {
    activeIfcHighlight.value = null
    selectedIfcElement.value = null
  }
  componentTreeRoots.value = componentTreeRoots.value.filter(
    (root) => root.modelId !== modelId,
  )
  if (selectedTreeKey.value?.startsWith(`${modelId}:`)) {
    selectedTreeKey.value = null
  }
  multiSelectedKeys.value = new Set(
    [...multiSelectedKeys.value].filter((key) => !key.startsWith(`${modelId}:`)),
  )
  const removedFeatureKeys = [...featureRegistry.keys()]
    .filter((key) => key.startsWith(`${modelId}:`))
  removedFeatureKeys.forEach((key) => {
    featureRegistry.delete(key)
    featureOriginalColors.delete(key)
  })
  clearTreeSelection()
  hiddenElementKeys.value = new Set(
    [...hiddenElementKeys.value].filter((key) => !key.startsWith(`${modelId}:`)),
  )
  hiddenTreeKeys.value = new Set(
    [...hiddenTreeKeys.value].filter((key) => !key.startsWith(`model:${modelId}`)),
  )
  coordinateInputs.value = { ...coordinateInputs.value }
  delete coordinateInputs.value[modelId]
  scaleDrafts.value = { ...scaleDrafts.value }
  delete scaleDrafts.value[modelId]
  rotationDrafts.value = { ...rotationDrafts.value }
  delete rotationDrafts.value[modelId]
  if (selectedModelId.value === modelId) {
    selectedModelId.value = null
  }
  removeLocalModelData(modelId)
  if (props.viewer) {
    const handler = cameraChangeHandlers.get(modelId)
    if (handler) {
      props.viewer.camera.changed.removeEventListener(handler)
      cameraChangeHandlers.delete(modelId)
    }
  }
  const timer = cameraSaveTimers.get(modelId)
  if (timer !== undefined) {
    window.clearTimeout(timer)
    cameraSaveTimers.delete(modelId)
  }
  ifcProjectIds.delete(modelId)
}

/** Serializes the Cesium camera into browser-independent Cartesian vectors. */
const getCameraState = (viewer: Cesium.Viewer): CameraState => ({
  position: {
    x: viewer.camera.positionWC.x,
    y: viewer.camera.positionWC.y,
    z: viewer.camera.positionWC.z,
  },
  direction: {
    x: viewer.camera.directionWC.x,
    y: viewer.camera.directionWC.y,
    z: viewer.camera.directionWC.z,
  },
  up: {
    x: viewer.camera.upWC.x,
    y: viewer.camera.upWC.y,
    z: viewer.camera.upWC.z,
  },
})

/** Restores a persisted Cesium camera when its vectors are valid. */
const applyCameraState = (viewer: Cesium.Viewer, state: CameraState | null | undefined) => {
  if (!state) return
  const vectors = [state.position, state.direction, state.up]
  if (
    vectors.some(
      (vector) =>
        !vector ||
        ![vector.x, vector.y, vector.z].every((value) => Number.isFinite(value)),
    )
  ) {
    return
  }
  viewer.camera.setView({
    destination: new Cesium.Cartesian3(state.position.x, state.position.y, state.position.z),
    orientation: {
      direction: new Cesium.Cartesian3(
        state.direction.x,
        state.direction.y,
        state.direction.z,
      ),
      up: new Cesium.Cartesian3(state.up.x, state.up.y, state.up.z),
    },
  })
}

/** Debounces camera persistence for one project while the user navigates. */
const scheduleCameraSave = (modelId: string) => {
  const projectId = ifcProjectIds.get(modelId)
  if (!projectId || !props.viewer) return
  const previousTimer = cameraSaveTimers.get(modelId)
  if (previousTimer !== undefined) window.clearTimeout(previousTimer)
  const timer = window.setTimeout(() => {
    cameraSaveTimers.delete(modelId)
    if (!props.viewer) return
    void saveIfcCamera(projectId, getCameraState(props.viewer)).catch((error) => {
      logWarn('Cesium 相机保存失败:', error)
    })
  }, 500)
  cameraSaveTimers.set(modelId, timer)
}

/** Registers one camera listener for a persisted IFC project. */
const registerCameraPersistence = (modelId: string, projectId?: string) => {
  if (!projectId || !props.viewer || cameraChangeHandlers.has(modelId)) return
  ifcProjectIds.set(modelId, projectId)
  const handler = () => scheduleCameraSave(modelId)
  props.viewer.camera.changed.addEventListener(handler)
  cameraChangeHandlers.set(modelId, handler)
}

/** Loads a converted IFC tileset and registers its feature metadata. */
const loadIfcTileset = async (
  taskId: string,
  fileName: string,
  longitude: number,
  latitude: number,
  tilesetUrl: string,
  metadataUrl?: string,
  modelId?: string,
  projectId?: string,
  camera?: CameraState | null,
) => {
  if (!props.viewer) return

  const loadedModelId = modelId ?? createIfcModelId()
  removedIfcModelIds.delete(loadedModelId)
  if (
    loadingIfcModelIds.has(loadedModelId) ||
    ifcTilesets.has(loadedModelId) ||
    ifcModels.value.some((item) => item.modelId === loadedModelId)
  ) {
    return
  }

  loadingIfcModelIds.add(loadedModelId)
  const resolvedTilesetUrl = resolveIfcAssetUrl(tilesetUrl)
  logInfo(`载入 IFC 模型：${fileName}`, resolvedTilesetUrl)
  const tileset = await Cesium.Cesium3DTileset.fromUrl(resolvedTilesetUrl, {
    show: true,
  })

  if (
    removedIfcModelIds.has(loadedModelId) ||
    ifcTilesets.has(loadedModelId) ||
    ifcModels.value.some((item) => item.modelId === loadedModelId)
  ) {
    if (!tileset.isDestroyed()) {
      tileset.destroy()
    }
    loadingIfcModelIds.delete(loadedModelId)
    return
  }

  props.viewer.scene.primitives.add(tileset)

  const modelMatrix = createModelTransform({
    longitude,
    latitude,
    height: 0,
    scale: 1,
    localVerticalMinimum: 0,
  })
  tileset.modelMatrix = modelMatrix

  const initialBoundingSphere = tileset.boundingSphere
  const initialCenter = initialBoundingSphere?.center
  const initialRadius = initialBoundingSphere?.radius
  let loadDiagnostic =
    `已加入 Cesium 场景，等待 tile 事件。` +
    `包围球中心=[${initialCenter?.x ?? 'NaN'}, ${initialCenter?.y ?? 'NaN'}, ${initialCenter?.z ?? 'NaN'}]，` +
    `半径=${initialRadius ?? 'NaN'}`
  logInfo(`[IFC 载入] ${loadDiagnostic}`)

  const updateLoadDiagnostic = (
    message: string,
    level: ConsoleLogLevel = 'info',
    detail?: unknown,
  ) => {
    if (message === loadDiagnostic) return
    loadDiagnostic = message
    ifcModels.value = ifcModels.value.map((item) =>
      item.modelId === loadedModelId
        ? {
            ...item,
            loadDiagnostic: message,
          }
        : item,
    )

    const writeLog =
      level === 'error' ? logError : level === 'warn' ? logWarn : logInfo
    writeLog(`[IFC 载入] ${message}`, detail)
  }

  let diagnosticTimer: number | undefined
  const clearDiagnosticTimer = () => {
    if (diagnosticTimer !== undefined) {
      window.clearTimeout(diagnosticTimer)
      diagnosticTimer = undefined
    }
  }

  tileset.tileLoad.addEventListener((tile: Cesium.Cesium3DTile) => {
    const content = (
      tile as unknown as {
        content?: {
          featuresLength?: number
          getFeature?: (index: number) => Cesium.Cesium3DTileFeature
        }
      }
    ).content
    if (content?.getFeature && content.featuresLength !== undefined) {
      for (let index = 0; index < content.featuresLength; index += 1) {
        const feature = content.getFeature(index)
        const ifcGuid = feature?.getProperty('ifcGuid') as string | undefined
        if (!feature || !ifcGuid) continue
        const key = `${loadedModelId}:${ifcGuid}`
        featureRegistry.set(key, feature)
        if (!featureOriginalColors.has(key)) {
          featureOriginalColors.set(key, feature.color.clone())
        }
      }
      applyCurrentTreeVisualState()
    }
    updateLoadDiagnostic('tileLoad：已成功加载 tile 内容')
    clearDiagnosticTimer()
  })

  tileset.tileFailed.addEventListener((error: unknown) => {
    const message = error instanceof Error ? error.message : JSON.stringify(error)
    updateLoadDiagnostic(`tileFailed：${message}`, 'error', error)
    clearDiagnosticTimer()
  })

  tileset.allTilesLoaded.addEventListener(() => {
    updateLoadDiagnostic('allTilesLoaded：全部 tile 已加载')
    clearDiagnosticTimer()
  })

  tileset.initialTilesLoaded.addEventListener(() => {
    updateLoadDiagnostic('initialTilesLoaded：初始 tile 已加载')
    clearDiagnosticTimer()
  })

  diagnosticTimer = window.setTimeout(() => {
    updateLoadDiagnostic(
      '30 秒诊断超时：未收到 tileLoad/tileFailed/allTilesLoaded',
      'warn',
      {
        url: resolvedTilesetUrl,
        hasReadyProperty: Object.prototype.hasOwnProperty.call(tileset, 'ready'),
        ready: (tileset as unknown as { ready?: boolean }).ready,
        boundingSphere: tileset.boundingSphere,
      },
    )
  }, 30000)

  try {
    await props.viewer.zoomTo(tileset)
  } catch (error) {
    logWarn('[IFC tileset] zoomTo failed', error)
  }

  const distanceToTileset = props.viewer.camera.distanceToBoundingSphere(
    tileset.boundingSphere,
  )
  const cameraHeight = props.viewer.camera.positionCartographic.height
  const cameraPosition = props.viewer.camera.positionWC
  const tilesetAny = tileset as unknown as {
    _geometricError?: number
    memoryAdjustedScreenSpaceError?: number
    root?: {
      isVisible?: boolean
      hasRenderableContent?: boolean
      contentUnloaded?: boolean
      getScreenSpaceError?: (
        frameState: unknown,
        useParentGeometricError: boolean,
      ) => number
    }
  }
  const rootScreenSpaceError = tilesetAny.root?.getScreenSpaceError?.(
    (props.viewer.scene as unknown as { frameState: unknown }).frameState,
    true,
  )
  const postZoomDiagnostic =
    `zoomTo 完成。相机距离包围球=${distanceToTileset.toFixed(2)}m，` +
    `相机高度=${cameraHeight.toFixed(2)}m，` +
    `相机位置=[${cameraPosition.x.toFixed(2)}, ${cameraPosition.y.toFixed(2)}, ${cameraPosition.z.toFixed(2)}]，` +
    `rootSSE=${rootScreenSpaceError ?? 'NaN'}`
  updateLoadDiagnostic(postZoomDiagnostic)

  ifcTilesets.set(loadedModelId, tileset)
  ifcTilesetModelIds.set(tileset, loadedModelId)
  ifcModelTaskIds.set(loadedModelId, taskId)
  registerCameraPersistence(loadedModelId, projectId)
  loadingIfcModelIds.delete(loadedModelId)
  setRecentRestoreEnabled(true)
  ifcModels.value = [
    ...ifcModels.value,
    {
      modelId: loadedModelId,
      name: fileName,
      tilesetUrl: resolvedTilesetUrl,
      metadataUrl,
      longitude,
      latitude,
      height: 0,
      scale: 1,
      rotationZ: 0,
      conversionStatus: 'completed',
      loadDiagnostic,
    },
  ]
  coordinateInputs.value = {
    ...coordinateInputs.value,
    [loadedModelId]: {
      longitude: longitude.toFixed(6),
      latitude: latitude.toFixed(6),
    },
  }
  scaleDrafts.value = {
    ...scaleDrafts.value,
    [loadedModelId]: '1',
  }
  rotationDrafts.value = {
    ...rotationDrafts.value,
    [loadedModelId]: '0',
  }
  selectedModelId.value = loadedModelId
  applyCameraState(props.viewer, camera)
  void refreshTreeForModel(loadedModelId)
}

const {
  start: startIfcConversion,
  stop: stopIfcConversion,
  dispose: disposeIfcConversion,
} = useIfcConversion(ifcTasks, async (conversion) => {
  await loadIfcTileset(
    conversion.taskId,
    conversion.fileName,
    conversion.longitude,
    conversion.latitude,
    conversion.tilesetUrl,
    conversion.metadataUrl,
    conversion.modelId,
    conversion.projectId,
  )
})

/** Restores the latest completed IFC revision after the viewer becomes ready. */
const restoreRecentIfcModel = async () => {
  if (
    recentModelRestoreStarted.value ||
    !props.viewer ||
    !readRecentRestoreEnabled()
  ) {
    return
  }
  recentModelRestoreStarted.value = true
  try {
    const recent = await fetchRecentIfcModel()
    if (!recent || !props.viewer) return
    await loadIfcTileset(
      recent.revisionId,
      recent.fileName,
      recent.longitude,
      recent.latitude,
      recent.tilesetUrl,
      recent.metadataUrl,
      recent.modelId,
      recent.projectId,
      recent.camera,
    )
  } catch (error) {
    logWarn('最近 IFC 模型恢复失败:', error)
  }
}

watch(
  () => props.viewer,
  (viewer) => {
    if (viewer) void restoreRecentIfcModel()
  },
  { immediate: true },
)

/** Stops polling and removes a conversion task from the task list. */
const removeIfcTask = async (taskId: string) => {
  stopIfcConversion(taskId)
  try {
    await deleteIfcRevision(taskId)
  } catch (error) {
    logError('IFC task delete failed', error)
    return
  }
  setRecentRestoreEnabled(false)
  ifcTasks.value = ifcTasks.value.filter((task) => task.taskId !== taskId)
  for (const [modelId, mappedTaskId] of ifcModelTaskIds) {
    if (mappedTaskId === taskId) {
      ifcModelTaskIds.delete(modelId)
    }
  }
}

/** Builds the hierarchical component tree from IFC semantic metadata. */
const buildTreeRoots = (
  modelId: string,
  modelName: string,
  elements: Array<{
    ifcGuid?: string
    expressId?: string | number
    elementType?: string
    name?: string
    storey?: string
    featureId?: number
  }>,
): BimTreeNode => {
  const storeyMap = new Map<string, Map<string, BimTreeNode[]>>()

  elements.forEach((element) => {
    const ifcGuid = element.ifcGuid
    if (!ifcGuid) return

    const storey = element.storey || '未分层构件'
    const category = element.elementType || '未分类构件'
    const label = element.name || ifcGuid

    const categoryMap = storeyMap.get(storey) ?? new Map<string, BimTreeNode[]>()
    const elementsForCategory = categoryMap.get(category) ?? []
    elementsForCategory.push({
      id: `element:${modelId}:${ifcGuid}`,
      modelId,
      type: 'element',
      label,
      ifcGuid,
      expressId: element.expressId,
      featureId: element.featureId,
      selectable: true,
    })
    categoryMap.set(category, elementsForCategory)
    storeyMap.set(storey, categoryMap)
  })

  const storeyChildren: BimTreeNode[] = []
  storeyMap.forEach((categoryMap, storey) => {
    const categoryChildren: BimTreeNode[] = []
    categoryMap.forEach((elements, category) => {
      categoryChildren.push({
        id: `category:${modelId}:${storey}:${category}`,
        modelId,
        type: 'category',
        label: category,
        selectable: false,
        children: elements,
      })
    })
    storeyChildren.push({
      id: `storey:${modelId}:${storey}`,
      modelId,
      type: 'storey',
      label: storey,
      selectable: false,
      children: categoryChildren,
    })
  })

  return {
    id: `model:${modelId}`,
    modelId,
    type: 'model',
    label: modelName,
    selectable: false,
    children: storeyChildren,
  }
}

/** Loads IFC metadata and refreshes the component tree and geometry index. */
const refreshTreeForModel = async (modelId: string) => {
  const model = ifcModels.value.find((item) => item.modelId === modelId)
  if (!model?.metadataUrl) return

  try {
    const metadata = await fetchIfcMetadata(model.metadataUrl)
    const elements = metadata.semanticElements ?? metadata.features ?? []
    elements.forEach((element) => {
      if (element.ifcGuid) {
        ifcMetadataByKey.set(`${modelId}:${element.ifcGuid}`, element)
      }
      if (element.ifcGuid && element.geometry) {
        ifcGeometryByKey.set(`${modelId}:${element.ifcGuid}`, element.geometry)
      }
    })
    const root = buildTreeRoots(modelId, model.name, elements)
    componentTreeRoots.value = componentTreeRoots.value
      .filter((item) => item.id !== root.id)
      .concat(root)
  } catch (error) {
    logError('IFC 构件树构建失败:', error)
  }
}

const getWorldPositionForElement = (
    modelId: string,
    ifcGuid: string,
  ): Cesium.Cartesian3 | undefined => {
    const geometry = ifcGeometryByKey.get(`${modelId}:${ifcGuid}`)
    const tileset = ifcTilesets.get(modelId)
    if (!geometry || !tileset) return undefined

    const localPosition = new Cesium.Cartesian3(
      geometry.center.x,
      geometry.center.y,
      geometry.center.z,
    )
    return Cesium.Matrix4.multiplyByPoint(
      tileset.modelMatrix,
      localPosition,
      new Cesium.Cartesian3(),
    )
  }

  /** Creates one normalized selection item for the information panel. */
  const getSelectionItem = (
    modelId: string,
    ifcGuid: string,
    feature: PickedIfcFeature,
    fallback?: {
      expressId?: string | number
      name?: string
      elementType?: string
      storey?: string
    },
  ): SelectionGuideItem => {
    const metadata = ifcGeometryByKey.get(`${modelId}:${ifcGuid}`)
    const metadataElement = ifcMetadataByKey.get(`${modelId}:${ifcGuid}`)
    const worldPosition = getWorldPositionForElement(modelId, ifcGuid) ?? feature.worldPosition
    const nextFeature = worldPosition === feature.worldPosition
      ? feature
      : { ...feature, worldPosition }
    return {
      key: `${modelId}:${ifcGuid}`,
      modelId,
      ifcGuid,
      expressId: feature.expressId ?? fallback?.expressId ?? metadataElement?.expressId,
      name: feature.name ?? fallback?.name ?? metadataElement?.name ?? ifcGuid,
      elementType:
        feature.elementType ??
        fallback?.elementType ??
        metadataElement?.elementType ??
        '未分类构件',
      storey: fallback?.storey ?? metadataElement?.storey,
      feature: nextFeature,
      geometry: metadata,
    }
  }

  /** Replaces the ordered selection list and clamps the active index. */
  const setSelectionItems = (items: SelectionGuideItem[], activeIndex: number) => {
    selectionItems.value = items
    activeSelectionIndex.value = items.length
      ? Math.min(Math.max(activeIndex, 0), items.length - 1)
      : 0
  }

  /** Activates one panel item, highlights it, and loads its properties. */
  const selectGuideItem = (index: number) => {
    if (index < 0 || index >= selectionItems.value.length) return
    activeSelectionIndex.value = index
    const item = selectionItems.value[index]
    const feature = item.feature
    activeGuideFeatureKey.value =
      treeSelectionMode.value === 'multi' ? item.key : null
    applyIfcHighlight(feature)
    flyToIfcFeature(feature.feature, item.modelId)
    selectedIfcElement.value = {
      modelId: item.modelId,
      ifcGuid: item.ifcGuid,
      feature,
      properties: ifcPropertyCache.get(item.key) ?? null,
    }
    void loadSelectedElementProperties(item.modelId, item.ifcGuid)
  }

  /** Fetches and caches detailed properties for the active IFC element. */
  const loadSelectedElementProperties = async (modelId: string, ifcGuid: string) => {
    const cacheKey = `${modelId}:${ifcGuid}`
    const cached = ifcPropertyCache.get(cacheKey)
    if (cached) {
      if (
        selectedIfcElement.value?.modelId === modelId &&
        selectedIfcElement.value.ifcGuid === ifcGuid
      ) {
        selectedIfcElement.value = { ...selectedIfcElement.value, properties: cached }
      }
      return
    }

    try {
      const detail = await fetchIfcElementProperties(modelId, ifcGuid)
      mergeServerBusiness(modelId, ifcGuid, detail.business)
      ifcPropertyCache.set(cacheKey, detail)
      if (
        selectedIfcElement.value?.modelId === modelId &&
        selectedIfcElement.value.ifcGuid === ifcGuid
      ) {
        selectedIfcElement.value = { ...selectedIfcElement.value, properties: detail }
      }
    } catch (error) {
      logError('IFC 构件属性加载失败:', error)
    }
  }

  /** Stops the selected-feature flash timer and restores original colors. */
  const stopFlashing = () => {
  let skippedFlashing = 0
  if (flashingTimer !== undefined) {
    window.clearInterval(flashingTimer)
    flashingTimer = undefined
  }
  flashingFeatures.forEach((feature, key) => {
    const original = featureOriginalColors.get(key)
    if (original) {
      try {
        feature.color = getRestoredFeatureColor(key, original)
      } catch {
        // Feature 可能已随 tileset 销毁。
        skippedFlashing += 1
      }
    }
  })
  if (skippedFlashing > 0) {
    logInfo(`已忽略 ${skippedFlashing} 个随 tileset 卸载的构件（停止闪烁还原）`)
  }
  flashingFeatures.clear()
  activeGuideFeatureKey.value = null
  flashingOn = false
}

/** Builds the stable model/GUID key for a Cesium tile feature. */
const getFeatureKey = (feature: Cesium.Cesium3DTileFeature) => {
  const modelId = ifcTilesetModelIds.get(feature.tileset) ?? ''
  const ifcGuid = feature.getProperty('ifcGuid') as string | undefined
  return ifcGuid ? `${modelId}:${ifcGuid}` : null
}

/** Starts the yellow/blue selection flash animation for selected features. */
const startFlashing = (features: Cesium.Cesium3DTileFeature[]) => {
  stopFlashing()
  features.forEach((feature) => {
    const key = getFeatureKey(feature)
    if (!key || hiddenElementKeys.value.has(key)) return
    if (!featureOriginalColors.has(key)) {
      featureOriginalColors.set(key, feature.color.clone())
    }
    flashingFeatures.set(key, feature)
  })

  if (flashingFeatures.size === 0) return

  flashingTimer = window.setInterval(() => {
    flashingOn = !flashingOn
    flashingFeatures.forEach((feature, key) => {
      const original = featureOriginalColors.get(key)
      if (!original) return
      if (hiddenElementKeys.value.has(key)) {
        feature.color = getRestoredFeatureColor(key, original)
      } else {
        feature.color =
          flashingOn && key === activeGuideFeatureKey.value
            ? Cesium.Color.fromCssColorString('#123b75')
            : flashingOn
              ? Cesium.Color.YELLOW
              : original
      }
    })
  }, 500)
}

/** Finds a loaded tile feature by model ID and IFC GUID. */
const getFeatureByKey = (
  modelId: string,
  ifcGuid: string,
): Cesium.Cesium3DTileFeature | null => {
  const registered = featureRegistry.get(`${modelId}:${ifcGuid}`)
  if (registered) return registered

  const tileset = ifcTilesets.get(modelId)
  if (!tileset) return null

  const content = (
    tileset as unknown as {
      root?: {
        content?: {
          getFeature?: (index: number) => Cesium.Cesium3DTileFeature
          featuresLength?: number
        }
      }
    }
  ).root?.content

  if (!content?.getFeature || content.featuresLength === undefined) {
    return null
  }

  for (let index = 0; index < content.featuresLength; index += 1) {
    const feature = content.getFeature(index)
    if (feature?.getProperty('ifcGuid') === ifcGuid) {
      return feature
    }
  }

  return null
}

/** Returns all currently available tile features for one model. */
const getFeaturesForModel = (
  modelId: string,
): Cesium.Cesium3DTileFeature[] => {
  const registered = [...featureRegistry.entries()]
    .filter(([key]) => key.startsWith(`${modelId}:`))
    .map(([, feature]) => feature)
  if (registered.length > 0) return registered

  const tileset = ifcTilesets.get(modelId)
  if (!tileset) return []

  const content = (
    tileset as unknown as {
      root?: {
        content?: {
          getFeature?: (index: number) => Cesium.Cesium3DTileFeature
          featuresLength?: number
        }
      }
    }
  ).root?.content

  if (!content?.getFeature || content.featuresLength === undefined) return []

  const features: Cesium.Cesium3DTileFeature[] = []
  for (let index = 0; index < content.featuresLength; index += 1) {
    const feature = content.getFeature(index)
    if (feature) {
      features.push(feature)
    }
  }
  return features
}

/** Applies hierarchy visibility without letting selection restore hidden features. */
const getRestoredFeatureColor = (key: string, original: Cesium.Color) => {
  if (!hiddenElementKeys.value.has(key)) return original
  return original.withAlpha(multiUnselectedOpacity.value)
}

/** Restores every registered feature to its original appearance. */
const restoreAllFeatureVisuals = () => {
  let skippedFeatures = 0
  featureRegistry.forEach((feature, key) => {
    const original = featureOriginalColors.get(key)
    if (original) {
      try {
        feature.color = getRestoredFeatureColor(key, original)
      } catch {
        // Feature 可能已随 tileset 销毁。
        skippedFeatures += 1
      }
    }
  })
  if (skippedFeatures > 0) {
    logInfo(`已忽略 ${skippedFeatures} 个随 tileset 卸载的构件（配色还原）`)
  }
}

/** Collects all element keys below a hierarchy node. */
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

/** Returns true when every descendant element of a hierarchy node is checked. */
const isTreeNodeChecked = (node: BimTreeNode) => {
  const elementKeys = collectElementKeys(node)
  return (
    elementKeys.length > 0 &&
    elementKeys.every((key) => !hiddenElementKeys.value.has(key))
  )
}

/** Toggles a hierarchy node or single element and applies that state to descendants. */
const toggleTreeVisibility = (node: BimTreeNode) => {
  const elementKeys = collectElementKeys(node)
  if (elementKeys.length === 0) return

  const shouldShow = !isTreeNodeChecked(node)
  const nextHidden = new Set(hiddenElementKeys.value)
  elementKeys.forEach((key) => {
    if (shouldShow) {
      nextHidden.delete(key)
    } else {
      nextHidden.add(key)
    }
  })

  hiddenElementKeys.value = nextHidden
  applyCurrentTreeVisualState()
}

/** Flies to one IFC element using its metadata-derived bounding sphere. */
const flyToIfcFeature = (feature: Cesium.Cesium3DTileFeature, modelId: string) => {
  if (!props.viewer) return

  const ifcGuid = feature.getProperty('ifcGuid') as string | undefined
  const geometry = ifcGuid
    ? ifcGeometryByKey.get(`${modelId}:${ifcGuid}`)
    : undefined
  const worldPosition = ifcGuid
    ? getWorldPositionForElement(modelId, ifcGuid)
    : undefined
  if (geometry && worldPosition) {
    const modelMatrix = ifcTilesets.get(modelId)?.modelMatrix
    const scale = modelMatrix ? Cesium.Matrix4.getMaximumScale(modelMatrix) : 1
    const radius = Math.max(geometry.radius * scale, 1)
    props.viewer.camera.flyToBoundingSphere(
      new Cesium.BoundingSphere(worldPosition, radius),
      {
        duration: 1.2,
        offset: new Cesium.HeadingPitchRange(
          props.viewer.camera.heading,
          -Cesium.Math.toRadians(42),
          clamp(radius * flightDistanceMultiplier.value, 12, 500),
        ),
      },
    )
    return
  }

  const featureWithContent = feature as unknown as {
    content?: {
      tile?: {
        boundingSphere?: Cesium.BoundingSphere
      }
    }
  }
  const boundingSphere =
    featureWithContent.content?.tile?.boundingSphere ??
    ifcTilesets.get(modelId)?.boundingSphere
  if (!boundingSphere) return

  const heading = Number.isFinite(props.viewer.camera.heading)
    ? props.viewer.camera.heading
    : 0
  const range = Math.min(
    500,
    Math.max(12, boundingSphere.radius * flightDistanceMultiplier.value),
  )

  props.viewer.camera.flyToBoundingSphere(boundingSphere, {
    duration: 1.2,
    offset: new Cesium.HeadingPitchRange(
      heading,
      -Cesium.Math.toRadians(45),
      range,
    ),
  })
}

/** Applies opacity to non-selected features while keeping the single selection visible. */
const applySingleSelectionVisualState = () => {
  const selectedKey = selectedTreeKey.value
  if (!selectedKey) {
    restoreAllFeatureVisuals()
    return
  }

  ifcModels.value.forEach((model) => {
    getFeaturesForModel(model.modelId).forEach((feature) => {
      const ifcGuid = feature.getProperty('ifcGuid') as string | undefined
      if (!ifcGuid) return

      const key = `${model.modelId}:${ifcGuid}`
      const original = featureOriginalColors.get(key) ?? feature.color.clone()
      featureOriginalColors.set(key, original)

      if (key === selectedKey && !hiddenElementKeys.value.has(key)) {
        feature.color = original
      } else {
        feature.color = original.withAlpha(multiUnselectedOpacity.value)
      }
    })
  })
}

/** Applies the current single or multi-selection opacity state. */
const applyCurrentTreeVisualState = () => {
  if (treeSelectionMode.value === 'multi') {
    applyMultiVisualState()
    return
  }

  applySingleSelectionVisualState()
}

/** Selects one component-tree element and opens its information panel. */
const applyTreeSelection = async (node: BimTreeNode) => {
  if (!node.ifcGuid || !node.modelId) return

  const feature = getFeatureByKey(node.modelId, node.ifcGuid)
  const key = `${node.modelId}:${node.ifcGuid}`
  if (selectedTreeKey.value === key) {
    clearTreeSelection()
    selectedIfcElement.value = null
    return
  }
  selectedTreeKey.value = key
  multiSelectedKeys.value = new Set()
  isolatedTreeKey.value = key

  if (feature) {
    stopFlashing()
    applyCurrentTreeVisualState()
    if (!hiddenElementKeys.value.has(key)) {
      startFlashing([feature])
    }
    flyToIfcFeature(feature, node.modelId)
  } else {
    logWarn('构件几何当前尚未加载')
    return
  }

  const picked: PickedIfcFeature = {
    feature,
    ifcGuid: node.ifcGuid,
    expressId: node.expressId,
    name: node.label,
    tileset: ifcTilesets.get(node.modelId)!,
  }
  const item = getSelectionItem(node.modelId, node.ifcGuid, picked, {
    expressId: node.expressId,
    name: node.label,
  })
  setSelectionItems([item], 0)

  selectedIfcElement.value = {
    modelId: node.modelId,
    ifcGuid: node.ifcGuid,
    feature: {
      feature,
      ifcGuid: node.ifcGuid,
      elementType: '',
      name: node.label,
      tileset: ifcTilesets.get(node.modelId)!,
    },
    properties: null,
  }

  const cacheKey = `${node.modelId}:${node.ifcGuid}`
  const cached = ifcPropertyCache.get(cacheKey)
  if (cached) {
    selectedIfcElement.value = {
      ...selectedIfcElement.value,
      properties: cached,
    }
  } else {
    try {
      const detail = await fetchIfcElementProperties(node.modelId, node.ifcGuid)
      ifcPropertyCache.set(cacheKey, detail)
      if (
        selectedIfcElement.value?.modelId === node.modelId &&
        selectedIfcElement.value.ifcGuid === node.ifcGuid
      ) {
        selectedIfcElement.value = {
          ...selectedIfcElement.value,
          properties: detail,
        }
      }
    } catch (error) {
      logError('IFC 构件属性加载失败:', error)
    }
  }
}

/** Adds or removes a component-tree item while preserving click order. */
const toggleTreeMultiSelection = (node: BimTreeNode) => {
  if (!node.ifcGuid || !node.modelId) return

  const key = `${node.modelId}:${node.ifcGuid}`
  const next = new Set(multiSelectedKeys.value)
  const wasSelected = next.has(key)
  if (wasSelected) {
    next.delete(key)
    selectionOrder.value = selectionOrder.value.filter((itemKey) => itemKey !== key)
  } else {
    next.add(key)
    selectionOrder.value = [...selectionOrder.value, key]
  }
  multiSelectedKeys.value = next
  selectedTreeKey.value = null
  isolatedTreeKey.value = null
  if (next.size === 0) {
    clearTreeSelection()
    selectedIfcElement.value = null
  } else {
    if (wasSelected) clearIfcHighlight()
    applyMultiVisualState()
    const items = selectionOrder.value
      .map((itemKey) => {
        const [modelId, ...guidParts] = itemKey.split(':')
        const ifcGuid = guidParts.join(':')
        const feature = getFeatureByKey(modelId, ifcGuid)
        if (!feature) return null
        return getSelectionItem(modelId, ifcGuid, {
          feature,
          ifcGuid,
          tileset: ifcTilesets.get(modelId)!,
        })
      })
      .filter((item): item is SelectionGuideItem => item !== null)
    setSelectionItems(items, Math.max(0, items.length - 1))
    if (items.length) selectGuideItem(items.length - 1)
  }
}

/** Applies opacity and flashing to the current multi-selection. */
const applyMultiVisualState = () => {
  stopFlashing()
  if (multiSelectedKeys.value.size === 0) {
    restoreAllFeatureVisuals()
    return
  }
  const selectedFeatures: Cesium.Cesium3DTileFeature[] = []

  ifcModels.value.forEach((model) => {
    getFeaturesForModel(model.modelId).forEach((feature) => {
      const ifcGuid = feature.getProperty('ifcGuid') as string | undefined
      if (!ifcGuid) return
      const key = `${model.modelId}:${ifcGuid}`
      const isSelected = multiSelectedKeys.value.has(key)
      const original = featureOriginalColors.get(key) ?? feature.color.clone()
      featureOriginalColors.set(key, original)
      if (isSelected && !hiddenElementKeys.value.has(key)) {
        selectedFeatures.push(feature)
      } else {
        feature.color = original.withAlpha(multiUnselectedOpacity.value)
      }
    })
  })

  startFlashing(selectedFeatures)
}

/** Clears all tree selection, flashing, and temporary panel items. */
const clearTreeSelection = () => {
  clearIfcHighlight()
  stopFlashing()
  selectedTreeKey.value = null
  multiSelectedKeys.value = new Set()
  isolatedTreeKey.value = null
  selectionOrder.value = []
  setSelectionItems([], 0)
  restoreAllFeatureVisuals()
}

/** Changes selection mode and clears incompatible selection state. */
const setTreeSelectionMode = (mode: 'single' | 'multi') => {
  treeSelectionMode.value = mode
  clearTreeSelection()
}

/** Updates the opacity of non-selected components in multi-select mode. */
const setMultiUnselectedOpacity = (value: number) => {
  multiUnselectedOpacity.value = Math.min(Math.max(value, 0), 1)
  applyCurrentTreeVisualState()
}

/** Restores the currently selected feature's previous color. */
const clearIfcHighlight = () => {
  const highlight = activeIfcHighlight.value
  if (!highlight) return

  if (highlight.feature && highlight.originalColor) {
    try {
      const key = getFeatureKey(highlight.feature)
      highlight.feature.color = key
        ? getRestoredFeatureColor(key, highlight.originalColor)
        : highlight.originalColor
    } catch (error) {
      // Feature 可能已随 tileset 销毁。
      logInfo('构件高亮随 tileset 卸载，已忽略还原', error)
    }
  }
  activeIfcHighlight.value = null
}

/** Applies the active yellow highlight to a picked IFC feature. */
const applyIfcHighlight = (feature: PickedIfcFeature) => {
  const current = activeIfcHighlight.value
  if (current?.feature === feature.feature) {
    return
  }

  clearIfcHighlight()
  const key = getFeatureKey(feature.feature)
  if (key && hiddenElementKeys.value.has(key)) return
  const storedColor = key ? featureOriginalColors.get(key) : undefined
  activeIfcHighlight.value = {
    feature: feature.feature,
    originalColor: storedColor ?? feature.feature.color.clone(),
  }
  feature.feature.color = Cesium.Color.YELLOW
}

/** Handles map clicks and synchronizes tree, panel, highlight, and properties. */
const handlePickedFeature = async (feature: PickedIfcFeature | null) => {
  if (!feature) {
    clearTreeSelection()
    selectedIfcElement.value = null
    return
  }

  const ifcGuid = feature.ifcGuid
  if (!ifcGuid) {
    return
  }

  const modelId = ifcTilesetModelIds.get(feature.tileset)
  if (!modelId) {
    return
  }

  const treeKey = `${modelId}:${ifcGuid}`
  const isSameSingleSelection =
    treeSelectionMode.value === 'single' && isolatedTreeKey.value === treeKey
  const isSameMultiSelection =
    treeSelectionMode.value === 'multi' && multiSelectedKeys.value.has(treeKey)
  if (isSameSingleSelection) {
    clearTreeSelection()
    selectedIfcElement.value = null
    return
  }
  clearIfcHighlight()
  stopFlashing()
  if (treeSelectionMode.value === 'single') {
    selectedTreeKey.value = treeKey
    multiSelectedKeys.value = new Set()
    isolatedTreeKey.value = treeKey
    selectionOrder.value = [treeKey]
    applyCurrentTreeVisualState()
    startFlashing([feature.feature])
  } else {
    const next = new Set(multiSelectedKeys.value)
    if (next.has(treeKey)) {
      next.delete(treeKey)
      selectionOrder.value = selectionOrder.value.filter((key) => key !== treeKey)
    } else {
      next.add(treeKey)
      selectionOrder.value = [...selectionOrder.value, treeKey]
    }
    multiSelectedKeys.value = next
    applyMultiVisualState()
    if (isSameMultiSelection) {
      const remaining = selectionOrder.value
        .map((key) => {
          const [itemModelId, ...guidParts] = key.split(':')
          const itemGuid = guidParts.join(':')
          const itemFeature = getFeatureByKey(itemModelId, itemGuid)
          if (!itemFeature) return null
          return getSelectionItem(itemModelId, itemGuid, {
            feature: itemFeature,
            ifcGuid: itemGuid,
            tileset: ifcTilesets.get(itemModelId)!,
          })
        })
        .filter((item): item is SelectionGuideItem => item !== null)
      setSelectionItems(remaining, Math.max(0, remaining.length - 1))
      if (remaining.length) selectGuideItem(remaining.length - 1)
      else {
        clearTreeSelection()
        selectedIfcElement.value = null
      }
      return
    }
  }

  applyIfcHighlight(feature)
  flyToIfcFeature(feature.feature, modelId)
  const currentItem = getSelectionItem(modelId, ifcGuid, feature)
  const nextItems =
    treeSelectionMode.value === 'single'
      ? [currentItem]
      : selectionOrder.value
          .map((key) => {
            const [itemModelId, ...guidParts] = key.split(':')
            const itemGuid = guidParts.join(':')
            const itemFeature = getFeatureByKey(itemModelId, itemGuid)
            if (!itemFeature) return null
            return getSelectionItem(itemModelId, itemGuid, {
              feature: itemFeature,
              ifcGuid: itemGuid,
              tileset: ifcTilesets.get(itemModelId)!,
            })
          })
          .filter((item): item is SelectionGuideItem => item !== null)
  const nextIndex = Math.max(
    0,
    nextItems.findIndex((item) => item.key === treeKey),
  )
  setSelectionItems(nextItems, nextIndex)
  activeGuideFeatureKey.value =
    treeSelectionMode.value === 'multi' ? treeKey : null

  const cacheKey = `${modelId}:${ifcGuid}`
  const cached = ifcPropertyCache.get(cacheKey)
  const properties = cached ?? null

  selectedIfcElement.value = {
    modelId,
    ifcGuid,
    feature,
    properties,
  }

  if (!cached) {
    try {
      const detail = await fetchIfcElementProperties(modelId, ifcGuid)
      mergeServerBusiness(modelId, ifcGuid, detail.business)
      ifcPropertyCache.set(cacheKey, detail)
      if (
        selectedIfcElement.value?.modelId === modelId &&
        selectedIfcElement.value.ifcGuid === ifcGuid
      ) {
        selectedIfcElement.value = {
          ...selectedIfcElement.value,
          properties: detail,
        }
      }
    } catch (error) {
      logError('IFC 构件属性加载失败:', error)
    }
  }
}

watch(
  () => props.pickedFeature,
  (feature) => {
    void handlePickedFeature(feature)
  },
)

const selectedElementAnnotations = computed(() => {
  if (!selectedIfcElement.value) return []
  return annotations.value.filter(
    (annotation) =>
      annotation.modelId === selectedIfcElement.value?.modelId &&
      annotation.elementGuid === selectedIfcElement.value.ifcGuid,
  )
})

/**
 * Merges business fields stored on the backend into the local cache.
 * Local values win so an edit made while the backend was unreachable is never
 * silently overwritten; the backend only fills fields this browser lacks.
 */
const mergeServerBusiness = (
  modelId: string,
  ifcGuid: string,
  serverBusiness: Record<string, unknown> | undefined,
) => {
  if (!serverBusiness || Object.keys(serverBusiness).length === 0) return

  const cacheKey = `${modelId}:${ifcGuid}`
  const local = businessByElement.value[cacheKey] ?? {}
  const merged = { ...serverBusiness, ...local }
  if (JSON.stringify(merged) === JSON.stringify(local)) return

  businessByElement.value = {
    ...businessByElement.value,
    [cacheKey]: merged,
  }
  saveBusinessData()
}

/** Sends one element's business fields to the backend after a short quiet gap. */
const scheduleBusinessSync = (
  modelId: string,
  ifcGuid: string,
  business: Record<string, unknown>,
) => {
  const cacheKey = `${modelId}:${ifcGuid}`
  pendingBusinessSync.set(cacheKey, business)

  const existing = businessSyncTimers.get(cacheKey)
  if (existing !== undefined) {
    window.clearTimeout(existing)
  }

  businessSyncTimers.set(
    cacheKey,
    window.setTimeout(() => {
      businessSyncTimers.delete(cacheKey)
      const payload = pendingBusinessSync.get(cacheKey)
      pendingBusinessSync.delete(cacheKey)
      if (!payload) return
      void saveIfcElementBusiness(modelId, ifcGuid, payload).catch((error) => {
        logWarn('运维字段同步到后端失败：', error)
      })
    }, BUSINESS_SYNC_DELAY),
  )
}

/** Flushes pending business syncs so unmounting cannot drop an edit. */
const flushBusinessSync = () => {
  businessSyncTimers.forEach((timer) => window.clearTimeout(timer))
  businessSyncTimers.clear()
  pendingBusinessSync.forEach((payload, cacheKey) => {
    const [modelId, ...guidParts] = cacheKey.split(':')
    const ifcGuid = guidParts.join(':')
    void saveIfcElementBusiness(modelId, ifcGuid, payload).catch((error) => {
      logWarn('运维字段同步到后端失败：', error)
    })
  })
  pendingBusinessSync.clear()
}

/** Resolves business fields for the currently active element. */
const selectedElementBusiness = computed(() => {
  const element = selectedIfcElement.value
  if (!element) return {}
  return businessByElement.value[`${element.modelId}:${element.ifcGuid}`] ?? {}
})

/** Updates and persists one business field for the active element. */
const updateBusinessField = (key: string, value: unknown) => {
  const element = selectedIfcElement.value
  if (!element) return

  const cacheKey = `${element.modelId}:${element.ifcGuid}`
  const next = {
    ...(businessByElement.value[cacheKey] ?? {}),
    [key]: value,
  }
  businessByElement.value = {
    ...businessByElement.value,
    [cacheKey]: next,
  }
  saveBusinessData()

  scheduleBusinessSync(element.modelId, element.ifcGuid, next)
}

/** Creates and persists a user annotation for the active element. */
const addAnnotation = (payload: {
  title: string
  content?: string
  type?: BimAnnotation['type']
  dueDate?: string
}) => {
  const element = selectedIfcElement.value
  if (!element) return

  const tileset = ifcTilesets.get(element.modelId)
  const worldPosition = element.feature.worldPosition
  let localPosition = { x: 0, y: 0, z: 0 }

  if (tileset && worldPosition) {
    const local = worldPointToModel(
      tileset.modelMatrix,
      worldPosition,
      new Cesium.Cartesian3(),
    )
    localPosition = {
      x: local.x,
      y: local.y,
      z: local.z,
    }
  }

  const annotation: BimAnnotation = {
    annotationId: createModelId(),
    modelId: element.modelId,
    elementGuid: element.ifcGuid,
    localPosition,
    title: payload.title,
    content: payload.content,
    type: payload.type ?? 'general',
    status: 'open',
    dueDate: payload.dueDate,
    createdAt: Date.now(),
  }

  annotations.value = [...annotations.value, annotation]
  saveAnnotations()
}

/** Toggles an annotation between open and resolved states. */
const updateAnnotationStatus = (
  annotationId: string,
  status: BimAnnotation['status'],
) => {
  annotations.value = annotations.value.map((annotation) =>
    annotation.annotationId === annotationId
      ? { ...annotation, status }
      : annotation,
  )
  saveAnnotations()
}

/** Closes the legacy detailed IFC inspector and its highlight. */
const closeIfcInspector = () => {
  isInspectorOpen.value = false
}

// Clearing the selection also closes the detached property panel.
watch(selectedIfcElement, (element) => {
  if (!element) isInspectorOpen.value = false
})

/** Clears temporary selection guidance and closes its panel. */
const closeSelectionPanel = () => {
  clearTreeSelection()
  selectedIfcElement.value = null
}

/** Updates and persists the camera flight distance multiplier. */
const updateFlightDistance = (value: number) => {
  if (!Number.isFinite(value)) return
  flightDistanceMultiplier.value = clamp(value, 1, 24)
  try {
    localStorage.setItem('bim-earth-flight-distance', String(flightDistanceMultiplier.value))
  } catch (error) {
    logWarn('飞行距离设置无法保存:', error)
  }
}

/** Finds a model in either the GLB or IFC state collection. */
const findManagedModel = (modelId: string) => {
  return (
    glbModels.value.find((model) => model.modelId === modelId) ??
    ifcModels.value.find((model) => model.modelId === modelId) ??
    null
  )
}

/**
 * Reads a numeric input draft. `v-model` on <input type="number"> stores a
 * number, while programmatic writes store a string, so accept both.
 */
const readNumericDraft = (draft: unknown): string => {
  if (typeof draft === 'number') {
    return Number.isFinite(draft) ? draft.toString() : ''
  }
  if (typeof draft === 'string') {
    return draft.trim()
  }
  return ''
}

/** Slider span and range for the logarithmic scale control. */
const SCALE_SLIDER_POSITION_MIN = 0
const SCALE_SLIDER_POSITION_MAX = 1000
const SCALE_SLIDER_MIN = 0.1
const SCALE_SLIDER_MAX = 100

/** Maps a model scale onto the logarithmic scale-slider position. */
const scaleToSliderPosition = (scale: number) => {
  const clamped = Math.min(
    Math.max(scale || SCALE_SLIDER_MIN, SCALE_SLIDER_MIN),
    SCALE_SLIDER_MAX,
  )
  const ratio =
    Math.log(clamped / SCALE_SLIDER_MIN) /
    Math.log(SCALE_SLIDER_MAX / SCALE_SLIDER_MIN)
  return Math.round(ratio * SCALE_SLIDER_POSITION_MAX)
}

/** Maps a scale-slider position back onto a model scale. */
const sliderPositionToScale = (position: number) => {
  const ratio =
    Math.min(
      Math.max(position || 0, SCALE_SLIDER_POSITION_MIN),
      SCALE_SLIDER_POSITION_MAX,
    ) / SCALE_SLIDER_POSITION_MAX
  const scale = SCALE_SLIDER_MIN * (SCALE_SLIDER_MAX / SCALE_SLIDER_MIN) ** ratio
  return Math.round(scale * 100) / 100
}

/** Filled-track width for the scale slider. */
const scaleSliderFill = (scale: number) =>
  `${(scaleToSliderPosition(scale) / SCALE_SLIDER_POSITION_MAX) * 100}%`

/** Filled-track width for the rotation slider. */
const rotationSliderFill = (rotation: number) =>
  `${(Math.min(Math.max(rotation, 0), 360) / 360) * 100}%`

/** Updates a model's geographic anchor and Cesium transform. */
const updateModelPosition = (
  modelId: string,
  longitude: number,
  latitude: number,
) => {
  if (!props.viewer) return

  if (
    isNaN(longitude) ||
    isNaN(latitude) ||
    longitude < -180 ||
    longitude > 180 ||
    latitude < -90 ||
    latitude > 90
  ) {
    logWarn('经纬度输入无效', { modelId, longitude, latitude })
    alert('经纬度输入无效')
    return
  }

  const model = findManagedModel(modelId)
  if (!model) return

  const nextMatrix = createModelTransform({
    longitude,
    latitude,
    height: 0,
    scale: model.scale,
    localVerticalMinimum: 'localVerticalMinimum' in model ? model.localVerticalMinimum : 0,
    rotationZ: model.rotationZ,
  })

  const glbRecord = glbPrimitives.get(modelId)
  const tileset = ifcTilesets.get(modelId)
  if (glbRecord && !glbRecord.primitive.isDestroyed()) {
    glbRecord.primitive.modelMatrix = nextMatrix
  } else if (tileset && !tileset.isDestroyed()) {
    tileset.modelMatrix = nextMatrix
  }

  if ('localVerticalMinimum' in model) {
    glbModels.value = glbModels.value.map((item) =>
      item.modelId === modelId
        ? { ...item, longitude, latitude }
        : item,
    )
  } else {
    ifcModels.value = ifcModels.value.map((item) =>
      item.modelId === modelId
        ? { ...item, longitude, latitude }
        : item,
    )
  }

  coordinateInputs.value = {
    ...coordinateInputs.value,
    [modelId]: {
      longitude: longitude.toFixed(6),
      latitude: latitude.toFixed(6),
    },
  }
}

/** Applies a validated scale to a loaded model. */
const applyModelScale = (modelId: string, nextScale: number) => {
  if (!props.viewer) return

  const model = findManagedModel(modelId)
  if (!model) return

  const safeScale = Number(nextScale)
  if (
    !Number.isFinite(safeScale) ||
    safeScale < MIN_MODEL_SCALE ||
    safeScale > MAX_MODEL_SCALE
  ) {
    logWarn(`模型比例必须在 ${MIN_MODEL_SCALE} 到 ${MAX_MODEL_SCALE} 之间`, { modelId })
    alert(`模型比例必须在 ${MIN_MODEL_SCALE} 到 ${MAX_MODEL_SCALE} 之间`)
    return
  }

  const nextMatrix = createModelTransform({
    longitude: model.longitude,
    latitude: model.latitude,
    height: 0,
    scale: safeScale,
    localVerticalMinimum: 'localVerticalMinimum' in model ? model.localVerticalMinimum : 0,
    rotationZ: model.rotationZ,
  })

  const glbRecord = glbPrimitives.get(modelId)
  const tileset = ifcTilesets.get(modelId)
  if (glbRecord && !glbRecord.primitive.isDestroyed()) {
    glbRecord.primitive.modelMatrix = nextMatrix
  } else if (tileset && !tileset.isDestroyed()) {
    tileset.modelMatrix = nextMatrix
  }

  if ('localVerticalMinimum' in model) {
    glbModels.value = glbModels.value.map((item) =>
      item.modelId === modelId ? { ...item, scale: safeScale } : item,
    )
  } else {
    ifcModels.value = ifcModels.value.map((item) =>
      item.modelId === modelId ? { ...item, scale: safeScale } : item,
    )
  }

  scaleDrafts.value = {
    ...scaleDrafts.value,
    [modelId]: safeScale.toString(),
  }
}

/** Commits the scale text input after validating its numeric value. */
const commitScaleInput = (modelId: string) => {
  const model = findManagedModel(modelId)
  if (!model) return

  const draft = readNumericDraft(scaleDrafts.value[modelId])
  const nextScale = draft === '' ? model.scale : parseFloat(draft)

  if (
    !Number.isFinite(nextScale) ||
    nextScale < MIN_MODEL_SCALE ||
    nextScale > MAX_MODEL_SCALE
  ) {
    logWarn(`模型比例必须在 ${MIN_MODEL_SCALE} 到 ${MAX_MODEL_SCALE} 之间`, { modelId })
    alert(`模型比例必须在 ${MIN_MODEL_SCALE} 到 ${MAX_MODEL_SCALE} 之间`)
    scaleDrafts.value = {
      ...scaleDrafts.value,
      [modelId]: model.scale.toString(),
    }
    return
  }

  applyModelScale(modelId, nextScale)
}

/** Applies a rotation angle to a loaded model. */
const applyModelRotation = (modelId: string, nextRotation: number) => {
  if (!props.viewer) return

  const model = findManagedModel(modelId)
  if (!model) return

  const safeRotation = Number(nextRotation)
  if (!Number.isFinite(safeRotation)) {
    logWarn('旋转角度必须是有效数字', { modelId })
    alert('旋转角度必须是有效数字')
    return
  }

  // 360° is visually identical to 0°, but keeping it as-is lets the slider
  // rest at its right end instead of snapping back to the left.
  const normalizedRotation =
    safeRotation === 360 ? 360 : ((safeRotation % 360) + 360) % 360
  const nextMatrix = createModelTransform({
    longitude: model.longitude,
    latitude: model.latitude,
    height: 0,
    scale: model.scale,
    localVerticalMinimum: 'localVerticalMinimum' in model ? model.localVerticalMinimum : 0,
    rotationZ: normalizedRotation,
  })

  const glbRecord = glbPrimitives.get(modelId)
  const tileset = ifcTilesets.get(modelId)
  if (glbRecord && !glbRecord.primitive.isDestroyed()) {
    glbRecord.primitive.modelMatrix = nextMatrix
  } else if (tileset && !tileset.isDestroyed()) {
    tileset.modelMatrix = nextMatrix
  }

  if ('localVerticalMinimum' in model) {
    glbModels.value = glbModels.value.map((item) =>
      item.modelId === modelId
        ? { ...item, rotationZ: normalizedRotation }
        : item,
    )
  } else {
    ifcModels.value = ifcModels.value.map((item) =>
      item.modelId === modelId
        ? { ...item, rotationZ: normalizedRotation }
        : item,
    )
  }

  rotationDrafts.value = {
    ...rotationDrafts.value,
    [modelId]: normalizedRotation.toString(),
  }
}

/** Commits the rotation text input after normalizing its value. */
const commitRotationInput = (modelId: string) => {
  const model = findManagedModel(modelId)
  if (!model) return

  const draft = readNumericDraft(rotationDrafts.value[modelId])
  const nextRotation = draft === '' ? model.rotationZ : parseFloat(draft)

  if (!Number.isFinite(nextRotation)) {
    logWarn('旋转角度必须是有效数字', { modelId })
    alert('旋转角度必须是有效数字')
    rotationDrafts.value = {
      ...rotationDrafts.value,
      [modelId]: model.rotationZ.toString(),
    }
    return
  }

  applyModelRotation(modelId, nextRotation)
}

/** Loads a GLB file into Cesium and registers its model state. */
const loadGltfModel = async (
  file: File,
  modelId: string,
  allFiles: File[],
): Promise<UploadedModelState | null> => {
  if (!props.viewer || !props.position) return null

  const cartographic = Cesium.Cartographic.fromCartesian(props.position)
  const longitude = Cesium.Math.toDegrees(cartographic.longitude)
  const latitude = Cesium.Math.toDegrees(cartographic.latitude)

  const fileExtension = getFileExtension(file)
  const objectUrls: string[] = []
  let uri: string
  let localVerticalMinimum = 0

  if (fileExtension === 'glb') {
    const glbJson = await parseGlbJson(file)
    localVerticalMinimum = getGltfLocalVerticalMinimum(glbJson as never)
    uri = URL.createObjectURL(file)
    objectUrls.push(uri)
  } else if (fileExtension === 'gltf') {
    const source = await file.text()
    let gltf: Record<string, unknown>

    try {
      gltf = JSON.parse(source) as Record<string, unknown>
    } catch {
      throw new Error('glTF 文件内容不是有效 JSON')
    }

    const fileMap = new Map(allFiles.map((item) => [item.name, item]))

    const resolveUri = (value: string) => {
      if (
        value.startsWith('data:') ||
        value.startsWith('blob:') ||
        /^https?:\/\//.test(value)
      ) {
        return value
      }

      const normalized = value.split('?')[0].split('#')[0]
      const decodedName = decodeURIComponent(normalized)
      const basename = decodedName.split('/').pop() ?? decodedName
      const companionFile =
        fileMap.get(decodedName) ?? allFiles.find((item) => item.name === basename)

      if (!companionFile) {
        throw new Error(`缺少关联资源：${value}，请同时选择 .bin / 贴图文件，或直接使用 .glb`)
      }

      const companionUrl = URL.createObjectURL(companionFile)
      objectUrls.push(companionUrl)
      return companionUrl
    }

    const buffers = gltf.buffers as Array<{ uri?: string }> | undefined
    buffers?.forEach((buffer) => {
      if (typeof buffer.uri === 'string') {
        buffer.uri = resolveUri(buffer.uri)
      }
    })

    const images = gltf.images as Array<{ uri?: string }> | undefined
    images?.forEach((image) => {
      if (typeof image.uri === 'string') {
        image.uri = resolveUri(image.uri)
      }
    })

    repairGltfAccessorReferences(gltf as never)
    ensureFlatNormals(gltf as never)
    localVerticalMinimum = getGltfLocalVerticalMinimum(gltf)

    const jsonBlob = new Blob([JSON.stringify(gltf)], { type: 'model/gltf+json' })
    uri = URL.createObjectURL(jsonBlob)
    objectUrls.push(uri)
  } else {
    return null
  }

  let primitive: Cesium.Model | undefined

  try {
    primitive = await Cesium.Model.fromGltfAsync({
      url: uri,
      modelMatrix: createModelTransform({
        longitude,
        latitude,
        height: 0,
        scale: 1,
        localVerticalMinimum,
      }),
      scene: props.viewer.scene,
      allowPicking: true,
    })

    props.viewer.scene.primitives.add(primitive)
    await waitForModelReady(primitive)
  } catch (error) {
    if (primitive && !primitive.isDestroyed()) {
      props.viewer.scene.primitives.remove(primitive)
      primitive.destroy()
    }
    objectUrls.forEach((url) => URL.revokeObjectURL(url))
    throw error
  }

  primitive.id = file.name
  glbPrimitives.set(modelId, { primitive, objectUrls })

  return {
    modelId,
    name: file.name,
    longitude,
    latitude,
    scale: 1,
    rotationZ: 0,
    localVerticalMinimum,
  }
}

/** Dispatches selected files to the GLB or IFC upload pipeline. */
const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0 || !props.viewer || !props.position) {
    logWarn('上传前未选择放置位置')
    alert('请先在地球上选择放置位置')
    return
  }

  isUploading.value = true
  const allFiles = Array.from(files)
  const loadedModels: UploadedModelState[] = []
  const cartographic = Cesium.Cartographic.fromCartesian(props.position)
  const longitude = Cesium.Math.toDegrees(cartographic.longitude)
  const latitude = Cesium.Math.toDegrees(cartographic.latitude)

  for (const file of allFiles) {
    const fileExtension = getFileExtension(file)

    try {
      if (fileExtension === 'gltf' || fileExtension === 'glb') {
        const model = await loadGltfModel(file, createModelId(), allFiles)
        if (model) {
          loadedModels.push(model)
        }
      } else if (fileExtension === 'ifc') {
        await startIfcConversion(file, longitude, latitude)
      }
    } catch (error) {
      logError('模型加载失败:', error)
      alert(
        `模型 ${file.name} 加载失败：${error instanceof Error ? error.message : '未知错误'}`,
      )
    }
  }

  if (loadedModels.length > 0) {
    glbModels.value = [...glbModels.value, ...loadedModels]
    const nextCoordinates = { ...coordinateInputs.value }
    const nextScales = { ...scaleDrafts.value }
    const nextRotations = { ...rotationDrafts.value }
    loadedModels.forEach((model) => {
      nextCoordinates[model.modelId] = {
        longitude: model.longitude.toFixed(6),
        latitude: model.latitude.toFixed(6),
      }
      nextScales[model.modelId] = model.scale.toString()
      nextRotations[model.modelId] = model.rotationZ.toString()
    })
    coordinateInputs.value = nextCoordinates
    scaleDrafts.value = nextScales
    rotationDrafts.value = nextRotations
    selectedModelId.value = loadedModels[0].modelId
    flyToModel(loadedModels[0])
  }

  isUploading.value = false
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

/** Removes a model and cleans up its associated Cesium resources. */
const removeModel = (modelId: string) => {
  removeGlb(props.viewer, modelId)

  glbModels.value = glbModels.value.filter((model) => model.modelId !== modelId)
  coordinateInputs.value = { ...coordinateInputs.value }
  delete coordinateInputs.value[modelId]
  scaleDrafts.value = { ...scaleDrafts.value }
  delete scaleDrafts.value[modelId]
  rotationDrafts.value = { ...rotationDrafts.value }
  delete rotationDrafts.value[modelId]
  if (selectedModelId.value === modelId) {
    selectedModelId.value = null
  }
  removeLocalModelData(modelId)
}

onBeforeUnmount(() => {
  clearIfcHighlight()
  disposeModelPrimitives(props.viewer)
  disposeIfcConversion()
  if (props.viewer) {
    cameraChangeHandlers.forEach((handler) => {
      props.viewer?.camera.changed.removeEventListener(handler)
    })
  }
  cameraChangeHandlers.clear()
  cameraSaveTimers.forEach((timer) => window.clearTimeout(timer))
  cameraSaveTimers.clear()
  flushBusinessSync()
  ifcProjectIds.clear()
  loadingIfcModelIds.clear()
  ifcModelTaskIds.clear()
  removedIfcModelIds.clear()
})
</script>

<template>
  <aside
    class="bim-sidebar"
    :class="{ 'is-collapsed': !modelPanelOpen }"
    :style="{
      bottom: consoleOpen ? `${CONSOLE_HEIGHT}px` : `${CONSOLE_HANDLE_HEIGHT}px`,
    }"
  >
    <div class="sidebar-titlebar">
      <span class="sidebar-title">模型管理</span>
      <span v-if="modelCount > 0" class="count-badge">{{ modelCount }}</span>
    </div>

    <button
      class="sidebar-handle"
      :aria-expanded="modelPanelOpen"
      :title="modelPanelOpen ? '收起模型管理' : '展开模型管理'"
      @click="modelPanelOpen = !modelPanelOpen"
    >
      <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
        <path
          d="M10 3.5 5.5 8 10 12.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>
      <input
        ref="fileInputRef"
        type="file"
        accept=".gltf,.glb,.ifc,.bin,.png,.jpg,.jpeg,.webp,.ktx2"
        multiple
        class="hidden-input"
        @change="handleFileUpload"
      />

      <button
        class="upload-button"
        :disabled="isUploading"
        @click="fileInputRef?.click()"
      >
        <span class="upload-icon" aria-hidden="true">＋</span>
        {{ isUploading ? '上传中…' : '上传模型' }}
      </button>

      <p v-if="!position" class="hint">请先在地球上点击选择位置</p>

      <div class="model-list">
        <div
          v-for="model in glbModels"
          :key="model.modelId"
          class="model-card"
          :class="{ selected: selectedModelId === model.modelId }"
          @click="selectedModelId = model.modelId"
        >
          <div class="card-head">
            <span class="model-name" :title="model.name">{{ model.name }}</span>
            <button class="mini-button" @click.stop="flyToModel(model)">定位</button>
            <button
              class="mini-button danger"
              @click.stop="removeModel(model.modelId)"
            >
              删除
            </button>
          </div>
          <div class="card-body">
            <div class="field-group coords">
              <input
                class="field coord"
                :value="coordinateInputs[model.modelId]?.longitude ?? model.longitude.toFixed(6)"
                placeholder="经度"
                @input="
                  (event) =>
                    (coordinateInputs[model.modelId] = {
                      longitude: (event.target as HTMLInputElement).value,
                      latitude:
                        coordinateInputs[model.modelId]?.latitude ??
                        model.latitude.toFixed(6),
                    })
                "
              />
              <input
                class="field coord"
                :value="coordinateInputs[model.modelId]?.latitude ?? model.latitude.toFixed(6)"
                placeholder="纬度"
                @input="
                  (event) =>
                    (coordinateInputs[model.modelId] = {
                      longitude:
                        coordinateInputs[model.modelId]?.longitude ??
                        model.longitude.toFixed(6),
                      latitude: (event.target as HTMLInputElement).value,
                    })
                "
              />
              <button
                class="mini-button"
                @click.stop="updateModelPosition(model.modelId, parseFloat(coordinateInputs[model.modelId]?.longitude ?? model.longitude.toFixed(6)), parseFloat(coordinateInputs[model.modelId]?.latitude ?? model.latitude.toFixed(6)))"
              >
                更新坐标
              </button>
            </div>
            <div class="field-group transform">
              <div class="transform-row">
                <label class="field-label">比例</label>
                <input
                  class="slider"
                  type="range"
                  :min="SCALE_SLIDER_POSITION_MIN"
                  :max="SCALE_SLIDER_POSITION_MAX"
                  step="1"
                  :value="scaleToSliderPosition(model.scale)"
                  :style="{ '--slider-fill': scaleSliderFill(model.scale) }"
                  @input="
                    applyModelScale(
                      model.modelId,
                      sliderPositionToScale(
                        ($event.target as HTMLInputElement).valueAsNumber,
                      ),
                    )
                  "
                />
                <input
                  v-model="scaleDrafts[model.modelId]"
                  class="field num"
                  type="number"
                  :min="MIN_MODEL_SCALE"
                  :max="MAX_MODEL_SCALE"
                  step="0.1"
                  @blur="commitScaleInput(model.modelId)"
                  @keydown.enter="commitScaleInput(model.modelId)"
                />
              </div>
              <div class="transform-row">
                <label class="field-label">旋转</label>
                <input
                  class="slider"
                  type="range"
                  min="0"
                  max="360"
                  step="1"
                  :value="model.rotationZ"
                  :style="{ '--slider-fill': rotationSliderFill(model.rotationZ) }"
                  @input="
                    applyModelRotation(
                      model.modelId,
                      ($event.target as HTMLInputElement).valueAsNumber,
                    )
                  "
                />
                <input
                  v-model="rotationDrafts[model.modelId]"
                  class="field num"
                  type="number"
                  min="0"
                  max="360"
                  step="1"
                  @blur="commitRotationInput(model.modelId)"
                  @keydown.enter="commitRotationInput(model.modelId)"
                />
              </div>
            </div>
          </div>
        </div>

        <div
          v-for="task in ifcTasks"
          :key="task.taskId"
          class="task-card"
          :style="{ '--task-progress': taskProgress(task) }"
        >
          <div class="card-head">
            <span class="model-name" :title="task.fileName">{{ task.fileName }}</span>
            <span
              class="task-status"
              :style="{ color: getIfcStatusColor(task.status) }"
            >
              {{ getIfcStatusText(task.status) }}
            </span>
            <button
              class="mini-button danger"
              @click.stop="removeIfcTask(task.taskId)"
            >
              删除
            </button>
          </div>
        </div>

        <div
          v-for="model in ifcModels"
          :key="model.modelId"
          class="model-card"
          :class="{ selected: selectedModelId === model.modelId }"
          @click="selectedModelId = model.modelId"
        >
          <div class="card-head">
            <span class="model-name" :title="model.name">{{ model.name }}</span>
            <button class="mini-button" @click.stop="flyToIfcModel(model)">定位</button>
            <button
              class="mini-button danger"
              @click.stop="removeIfcModel(model.modelId)"
            >
              删除
            </button>
          </div>
          <div class="card-body">
            <div class="field-group coords">
              <input
                class="field coord"
                :value="coordinateInputs[model.modelId]?.longitude ?? model.longitude.toFixed(6)"
                placeholder="经度"
                @input="
                  (event) =>
                    (coordinateInputs[model.modelId] = {
                      longitude: (event.target as HTMLInputElement).value,
                      latitude:
                        coordinateInputs[model.modelId]?.latitude ??
                        model.latitude.toFixed(6),
                    })
                "
              />
              <input
                class="field coord"
                :value="coordinateInputs[model.modelId]?.latitude ?? model.latitude.toFixed(6)"
                placeholder="纬度"
                @input="
                  (event) =>
                    (coordinateInputs[model.modelId] = {
                      longitude:
                        coordinateInputs[model.modelId]?.longitude ??
                        model.longitude.toFixed(6),
                      latitude: (event.target as HTMLInputElement).value,
                    })
                "
              />
              <button
                class="mini-button"
                @click.stop="updateModelPosition(model.modelId, parseFloat(coordinateInputs[model.modelId]?.longitude ?? model.longitude.toFixed(6)), parseFloat(coordinateInputs[model.modelId]?.latitude ?? model.latitude.toFixed(6)))"
              >
                更新坐标
              </button>
            </div>
            <div class="field-group transform">
              <div class="transform-row">
                <label class="field-label">比例</label>
                <input
                  class="slider"
                  type="range"
                  :min="SCALE_SLIDER_POSITION_MIN"
                  :max="SCALE_SLIDER_POSITION_MAX"
                  step="1"
                  :value="scaleToSliderPosition(model.scale)"
                  :style="{ '--slider-fill': scaleSliderFill(model.scale) }"
                  @input="
                    applyModelScale(
                      model.modelId,
                      sliderPositionToScale(
                        ($event.target as HTMLInputElement).valueAsNumber,
                      ),
                    )
                  "
                />
                <input
                  v-model="scaleDrafts[model.modelId]"
                  class="field num"
                  type="number"
                  :min="MIN_MODEL_SCALE"
                  :max="MAX_MODEL_SCALE"
                  step="0.1"
                  @blur="commitScaleInput(model.modelId)"
                  @keydown.enter="commitScaleInput(model.modelId)"
                />
              </div>
              <div class="transform-row">
                <label class="field-label">旋转</label>
                <input
                  class="slider"
                  type="range"
                  min="0"
                  max="360"
                  step="1"
                  :value="model.rotationZ"
                  :style="{ '--slider-fill': rotationSliderFill(model.rotationZ) }"
                  @input="
                    applyModelRotation(
                      model.modelId,
                      ($event.target as HTMLInputElement).valueAsNumber,
                    )
                  "
                />
                <input
                  v-model="rotationDrafts[model.modelId]"
                  class="field num"
                  type="number"
                  min="0"
                  max="360"
                  step="1"
                  @blur="commitRotationInput(model.modelId)"
                  @keydown.enter="commitRotationInput(model.modelId)"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
  </aside>

  <!-- Rendered outside the sliding sidebar so collapsing it cannot move them. -->
  <SelectionInfoPanel
    v-if="selectionItems.length"
    :viewer="props.viewer"
    :items="selectionItems"
    :active-index="activeSelectionIndex"
    :flight-distance-multiplier="flightDistanceMultiplier"
    :properties="selectedIfcElement?.properties ?? null"
    @select="selectGuideItem"
    @update-flight-distance="updateFlightDistance"
    @open-inspector="isInspectorOpen = true"
    @close="closeSelectionPanel"
  />

  <IfcInspectorPanel
    v-if="isInspectorOpen && selectedIfcElement"
    :element="selectedIfcElement"
    :annotations="selectedElementAnnotations"
    :business="selectedElementBusiness"
    @close="closeIfcInspector"
    @add-annotation="addAnnotation"
    @update-status="updateAnnotationStatus"
    @update-business="updateBusinessField"
  />

  <BimComponentTree
    :roots="componentTreeRoots"
    :selection-mode="treeSelectionMode"
    :selected-key="selectedTreeKey"
    :multi-selected-keys="multiSelectedKeys"
    :unselected-opacity="multiUnselectedOpacity"
    :hidden-keys="hiddenElementKeys"
    @select-element="applyTreeSelection"
    @toggle-multi-element="toggleTreeMultiSelection"
    @clear-selection="clearTreeSelection"
    @set-mode="setTreeSelectionMode"
    @set-opacity="setMultiUnselectedOpacity"
    @toggle-visibility="toggleTreeVisibility"
  />

</template>

<style scoped>
.bim-sidebar {
  /* Light theme tokens; a dark theme only needs to override this block. */
  --sb-bg: #ffffff;
  --sb-fg: #24292f;
  --sb-muted: #6e7781;
  --sb-border: #e6e8eb;
  --sb-hover: #f3f4f6;
  --sb-accent: #1a56db;
  --sb-accent-soft: #f2f7ff;
  --sb-accent-hover: #e6f0ff;
  --sb-accent-border: #c9dcfb;
  --sb-danger: #c4362f;
  --sb-danger-soft: #fdecec;
  --sb-danger-border: #f2c9c7;
  --sb-warning: #9a6700;
  --sb-card-bg: #fbfcfd;
  --sb-card-border: #e6e8eb;
  --sb-card-selected-bg: #f2f7ff;
  --sb-card-selected-border: #a9c7f5;
  --sb-input-bg: #ffffff;
  --sb-input-border: #d7dbe0;
  --sb-placeholder: #9aa4ae;
  --sb-focus-ring: rgba(26, 86, 219, 0.12);
  /* Upload-button blue darkened ~20% and shifted toward black. */
  --sb-slider: #123c94;
  --sb-slider-track: #c9ced6;
  --sb-slider-shadow: rgba(15, 23, 42, 0.22);

  position: fixed;
  top: 0;
  left: 0;
  width: 320px;
  display: flex;
  flex-direction: column;
  background: var(--sb-bg);
  /* Drawn as a shadow so the border box stays exactly 320px wide and the
     handle lands at x=0 when the panel is slid away. */
  box-shadow: 1px 0 0 var(--sb-border);
  color: var(--sb-fg);
  font-size: 13px;
  z-index: 1200;
  transition: transform 0.22s ease, bottom 0.22s ease;
}

.bim-sidebar.is-collapsed {
  transform: translateX(-100%);
}

.sidebar-titlebar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 10px;
  border-bottom: 1px solid var(--sb-border);
}

.sidebar-title {
  font-weight: 600;
  color: var(--sb-fg);
}

.sidebar-handle {
  position: absolute;
  left: 100%;
  top: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--sb-border);
  border-left: none;
  border-radius: 0 6px 6px 0;
  background: var(--sb-bg);
  box-shadow: 1px 1px 3px rgba(15, 23, 42, 0.14);
  color: var(--sb-muted);
  cursor: pointer;
}

.sidebar-handle:hover {
  background: var(--sb-hover);
  color: var(--sb-fg);
}

.sidebar-handle svg {
  transition: transform 0.22s ease;
}

.bim-sidebar.is-collapsed .sidebar-handle {
  background: var(--sb-accent-soft);
  border-color: var(--sb-accent-border);
  color: var(--sb-accent);
}

.bim-sidebar.is-collapsed .sidebar-handle svg {
  transform: rotate(180deg);
}

.count-badge {
  flex: 0 0 auto;
  min-width: 18px;
  padding: 1px 6px;
  border-radius: 9px;
  background: var(--sb-accent-soft);
  border: 1px solid var(--sb-accent-border);
  color: var(--sb-accent);
  font-size: 11px;
  text-align: center;
}

.hidden-input {
  display: none;
}

.upload-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 0 0 auto;
  margin: 10px 10px 0 10px;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--sb-accent);
  background: var(--sb-accent-soft);
  border: 1px solid var(--sb-accent-border);
  border-radius: 6px;
  cursor: pointer;
}

.upload-button:hover:not(:disabled) {
  background: var(--sb-accent-hover);
}

.upload-button:disabled {
  color: var(--sb-muted);
  background: var(--sb-hover);
  border-color: var(--sb-border);
  cursor: not-allowed;
}

.upload-icon {
  font-size: 14px;
  line-height: 1;
}

.hint {
  flex: 0 0 auto;
  margin: 8px 10px 0 10px;
  font-size: 12px;
  color: var(--sb-warning);
}

.model-list {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding: 10px;
}

.model-card,
.task-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 9px;
  background: var(--sb-card-bg);
  border: 1px solid var(--sb-card-border);
  border-radius: 6px;
  cursor: pointer;
}

.model-card.selected {
  background: var(--sb-card-selected-bg);
  border-color: var(--sb-card-selected-border);
}

/* Conversion progress sweeps across the whole task card, left to right. */
.task-card {
  position: relative;
  overflow: hidden;
}

.task-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: var(--task-progress, 0%);
  background: linear-gradient(
    90deg,
    rgba(26, 86, 219, 0.08),
    rgba(26, 86, 219, 0.18)
  );
  transition: width 0.6s ease-out;
  pointer-events: none;
}

.task-card .card-head {
  position: relative;
  z-index: 1;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.model-name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-button {
  flex: 0 0 auto;
  padding: 2px 7px;
  font-family: inherit;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--sb-fg);
  background: var(--sb-input-bg);
  border: 1px solid var(--sb-input-border);
  border-radius: 4px;
  cursor: pointer;
}

.mini-button:hover {
  background: var(--sb-hover);
}

.mini-button.danger {
  color: var(--sb-danger);
  border-color: var(--sb-danger-border);
}

.mini-button.danger:hover {
  background: var(--sb-danger-soft);
}

.card-body {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.field-group {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.field-group.coords {
  flex: 1 1 auto;
}

.field-group.transform {
  flex: 1 1 100%;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
}

.field {
  padding: 3px 6px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--sb-fg);
  background: var(--sb-input-bg);
  border: 1px solid var(--sb-input-border);
  border-radius: 4px;
}

.field::placeholder {
  color: var(--sb-placeholder);
}

.field:focus {
  outline: none;
  border-color: var(--sb-accent-border);
  box-shadow: 0 0 0 2px var(--sb-focus-ring);
}

.field.coord {
  flex: 1 1 74px;
  min-width: 0;
}

.field.num {
  width: 52px;
  text-align: right;
}

.field-label {
  flex: 0 0 auto;
  font-size: 11.5px;
  color: var(--sb-muted);
}

.transform-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.transform-row .field-label {
  flex: 0 0 28px;
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
    var(--sb-slider) 0 var(--slider-fill, 0%),
    var(--sb-slider-track) var(--slider-fill, 0%) 100%
  );
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border-radius: 50%;
  background: var(--sb-bg);
  border: 2px solid var(--sb-slider);
  box-shadow: 0 1px 2px var(--sb-slider-shadow);
}

.slider::-moz-range-track {
  height: 4px;
  border-radius: 2px;
  background: var(--sb-slider-track);
}

.slider::-moz-range-progress {
  height: 4px;
  border-radius: 2px;
  background: var(--sb-slider);
}

.slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--sb-bg);
  border: 2px solid var(--sb-slider);
}

.task-status {
  flex: 0 0 auto;
  font-size: 11.5px;
  white-space: nowrap;
}

</style>
