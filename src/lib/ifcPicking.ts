import * as Cesium from 'cesium'

export interface PickedIfcFeature {
  feature: Cesium.Cesium3DTileFeature
  featureId?: number
  ifcGuid?: string
  expressId?: string | number
  elementType?: string
  name?: string
  properties?: Record<string, unknown>
  worldPosition?: Cesium.Cartesian3
  tileset: Cesium.Cesium3DTileset
}

export const pickIfcFeature = (
  viewer: Cesium.Viewer,
  windowPosition: Cesium.Cartesian2,
): PickedIfcFeature | null => {
  const picked = viewer.scene.pick(windowPosition)

  if (!(picked instanceof Cesium.Cesium3DTileFeature)) {
    return null
  }

  const getProperty = <T,>(name: string, fallback?: T) => {
    const value = picked.getProperty(name) as T | undefined
    return value === undefined ? fallback : value
  }

  return {
    feature: picked,
    featureId: typeof picked.featureId === 'number' ? picked.featureId : undefined,
    ifcGuid: getProperty<string>('ifcGuid'),
    expressId: getProperty<string | number>('expressId'),
    elementType: getProperty<string>('elementType'),
    name: getProperty<string>('name'),
    properties: picked.getPropertyIds().reduce<Record<string, unknown>>(
      (result: Record<string, unknown>, propertyName: string) => {
        result[propertyName] = picked.getProperty(propertyName)
        return result
      },
      {},
    ),
    worldPosition: viewer.scene.pickPosition(windowPosition) ?? undefined,
    tileset: picked.tileset,
  }
}
