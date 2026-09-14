import { computed, ref, shallowRef } from 'vue'
import type { IfcConversionStatus } from '../../types/bim'

export interface UploadedModelState {
  modelId: string
  name: string
  longitude: number
  latitude: number
  scale: number
  rotationZ: number
  localVerticalMinimum: number
}

export interface LoadedIfcModelState {
  modelId: string
  name: string
  tilesetUrl: string
  metadataUrl?: string
  longitude: number
  latitude: number
  height: number
  scale: number
  rotationZ: number
  conversionStatus: IfcConversionStatus
  loadDiagnostic?: string
}

export const useBimModelState = () => {
  const glbModels = shallowRef<UploadedModelState[]>([])
  const ifcModels = shallowRef<LoadedIfcModelState[]>([])
  const selectedModelId = ref<string | null>(null)
  const coordinateInputs = ref<Record<string, { longitude: string; latitude: string }>>({})
  const scaleDrafts = ref<Record<string, string>>({})
  const rotationDrafts = ref<Record<string, string>>({})

  /** Resolves the currently selected GLB or IFC model. */
  const selectedModel = computed<
    UploadedModelState | LoadedIfcModelState | null
  >(() => {
    return (
      glbModels.value.find((model) => model.modelId === selectedModelId.value) ??
      ifcModels.value.find((model) => model.modelId === selectedModelId.value) ??
      null
    )
  })

  return {
    glbModels,
    ifcModels,
    selectedModelId,
    selectedModel,
    coordinateInputs,
    scaleDrafts,
    rotationDrafts,
  }
}
