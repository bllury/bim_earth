export interface BimModelTransform {
  longitude: number
  latitude: number
  height: number
  scale: number
  rotationZ: number
}

export type SourceModelType = 'gltf' | 'glb' | 'ifc' | '3d-tiles'

export type IfcConversionStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'

export interface BimModelState {
  modelId: string
  name: string
  transform: BimModelTransform
  createdAt: number
}

export interface BimAnnotation {
  annotationId: string
  modelId: string
  elementGuid: string
  localPosition: {
    x: number
    y: number
    z: number
  }
  nodePath?: string
  title: string
  content?: string
  type?: 'inspection' | 'maintenance' | 'issue' | 'general'
  status?: 'open' | 'resolved'
  dueDate?: string
  createdAt: number
}

export interface BimAnnotationState {
  modelId: string
  annotations: BimAnnotation[]
}

export interface AnnotationMonitorRequest {
  annotationId: string
  modelId: string
  endpoint: string
  payload?: Record<string, unknown>
}

export interface IfcTilesModelState {
  modelId: string
  name: string
  sourceType: Extract<SourceModelType, 'ifc' | '3d-tiles'>
  tilesetUrl: string
  metadataUrl?: string
  longitude: number
  latitude: number
  height: number
  scale: number
  rotationZ: number
  conversionStatus: IfcConversionStatus
}

export interface IfcMaterialSummary {
  name?: string
  category?: string
  grade?: string
  thickness?: number | null
  raw?: Record<string, unknown>
}

export interface IfcElementProperties {
  modelId: string
  ifcGuid: string
  expressId?: string | number
  basic: Record<string, unknown>
  materials: IfcMaterialSummary[]
  propertySets: Record<string, Record<string, unknown>>
  business: Record<string, unknown>
}

export interface BimTreeNode {
  id: string
  modelId: string
  type: 'model' | 'project' | 'building' | 'storey' | 'space' | 'category' | 'element'
  label: string
  ifcGuid?: string
  expressId?: string | number
  featureId?: number
  children?: BimTreeNode[]
  selectable: boolean
}
