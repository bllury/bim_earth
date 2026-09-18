import type { IfcConversionStatus, IfcElementProperties } from '../types/bim'

const IFC_API_BASE =
  (import.meta.env.VITE_IFC_API_BASE as string | undefined) ?? '/api'

export interface IfcConvertAccepted {
  taskId: string
  projectId: string
  revisionId: string
}

export interface IfcConvertResult {
  taskId: string
  status: IfcConversionStatus
  progress?: number
  message?: string
  tilesetUrl?: string
  metadataUrl?: string
  modelId?: string
  error?: string
  projectId?: string
  revisionId?: string
}

export interface RecentIfcModel {
  projectId: string
  projectName: string
  revisionId: string
  fileName: string
  modelId: string
  tilesetUrl: string
  metadataUrl: string
  longitude: number
  latitude: number
  camera?: CameraState | null
}

export interface CameraState {
  position: { x: number; y: number; z: number }
  direction: { x: number; y: number; z: number }
  up: { x: number; y: number; z: number }
}

export interface IfcMetadataElement {
  modelId?: string
  ifcGuid?: string
  expressId?: string | number
  elementType?: string
  name?: string
  storey?: string
  featureId?: number
  basic?: Record<string, unknown>
  materials?: unknown[]
  propertySets?: Record<string, Record<string, unknown>>
  business?: Record<string, unknown>
  geometry?: IfcElementGeometry
}

export interface IfcElementGeometry {
  min: { x: number; y: number; z: number }
  max: { x: number; y: number; z: number }
  center: { x: number; y: number; z: number }
  radius: number
}

export interface IfcMetadataResponse {
  modelId?: string
  featureIdField?: string
  features?: IfcMetadataElement[]
  semanticElements?: IfcMetadataElement[]
}

export const uploadIfcFile = async (
  file: File,
  longitude = 0,
  latitude = 0,
): Promise<IfcConvertAccepted> => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('longitude', String(longitude))
  formData.append('latitude', String(latitude))

  const response = await fetch(`${IFC_API_BASE}/ifc/convert`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    let message = `IFC 上传失败（${response.status}）`
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) {
        message = data.detail
      }
    } catch {
      // 后端可能没有返回 JSON
    }
    throw new Error(message)
  }

  return (await response.json()) as IfcConvertAccepted
}

export const fetchIfcConversionStatus = async (
  taskId: string,
): Promise<IfcConvertResult> => {
  const response = await fetch(`${IFC_API_BASE}/ifc/convert/${taskId}`)

  if (!response.ok) {
    let message = `查询 IFC 转换状态失败（${response.status}）`
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) {
        message = data.detail
      }
    } catch {
      // 后端可能没有返回 JSON
    }
    throw new Error(message)
  }

  return (await response.json()) as IfcConvertResult
}

export const resolveIfcAssetUrl = (path: string) => {
  if (/^https?:\/\//.test(path) || path.startsWith('/')) {
    return path
  }

  return `${IFC_API_BASE}/${path.replace(/^\/+/, '')}`
}

export const fetchIfcElementProperties = async (
  modelId: string,
  ifcGuid: string,
): Promise<IfcElementProperties> => {
  const response = await fetch(
    `${IFC_API_BASE}/ifc/models/${encodeURIComponent(modelId)}/elements/${encodeURIComponent(ifcGuid)}/properties`,
  )

  if (!response.ok) {
    let message = `IFC Property Set 查询失败（${response.status}）`
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) {
        message = data.detail
      }
    } catch {
      // 后端可能没有返回 JSON
    }
    throw new Error(message)
  }

  return (await response.json()) as IfcElementProperties
}

export const fetchIfcMetadata = async (
  metadataUrl: string,
): Promise<IfcMetadataResponse> => {
  const resolvedUrl = resolveIfcAssetUrl(metadataUrl)
  const response = await fetch(resolvedUrl)

  if (!response.ok) {
    throw new Error(`IFC metadata 加载失败（${response.status}）`)
  }

  return (await response.json()) as IfcMetadataResponse
}

export const fetchRecentIfcModel = async (): Promise<RecentIfcModel | null> => {
  const response = await fetch(`${IFC_API_BASE}/ifc/recent`)
  if (!response.ok) {
    throw new Error(`最近 IFC 模型加载失败（${response.status}）`)
  }
  return (await response.json()) as RecentIfcModel | null
}

export const saveIfcCamera = async (
  projectId: string,
  camera: CameraState,
): Promise<void> => {
  const response = await fetch(
    `${IFC_API_BASE}/ifc/projects/${encodeURIComponent(projectId)}/camera`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectId, camera }),
    },
  )
  if (!response.ok) {
    throw new Error(`Cesium 相机保存失败（${response.status}）`)
  }
}

export const saveIfcElementBusiness = async (
  modelId: string,
  ifcGuid: string,
  business: Record<string, unknown>,
): Promise<void> => {
  const response = await fetch(
    `${IFC_API_BASE}/ifc/models/${encodeURIComponent(modelId)}/elements/${encodeURIComponent(ifcGuid)}/business`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ business }),
    },
  )
  if (!response.ok) {
    throw new Error(`运维字段保存失败（${response.status}）`)
  }
}

export const deleteIfcRevision = async (revisionId: string): Promise<void> => {
  const response = await fetch(
    `${IFC_API_BASE}/ifc/revisions/${encodeURIComponent(revisionId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) {
    throw new Error(`IFC 模型删除失败（${response.status}）`)
  }
}
