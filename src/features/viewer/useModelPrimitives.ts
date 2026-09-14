import * as Cesium from 'cesium'
import { ifcTilesetModelIds } from './selectionState'

export interface GlbPrimitiveRecord {
  primitive: Cesium.Model
  objectUrls: string[]
}

export const useModelPrimitives = () => {
  const glbPrimitives = new Map<string, GlbPrimitiveRecord>()
  const ifcTilesets = new Map<string, Cesium.Cesium3DTileset>()

  /** Removes one GLB primitive and revokes its object URLs. */
  const removeGlb = (viewer: Cesium.Viewer | null, modelId: string) => {
    const record = glbPrimitives.get(modelId)
    if (!record) return

    if (viewer) {
      viewer.scene.primitives.remove(record.primitive)
    }
    if (!record.primitive.isDestroyed()) {
      record.primitive.destroy()
    }
    record.objectUrls.forEach((url) => URL.revokeObjectURL(url))
    glbPrimitives.delete(modelId)
  }

  /** Removes one IFC tileset and its reverse lookup entry. */
  const removeTileset = (viewer: Cesium.Viewer | null, modelId: string) => {
    const tileset = ifcTilesets.get(modelId)
    if (!tileset) return

    if (viewer) {
      viewer.scene.primitives.remove(tileset)
    }
    if (!tileset.isDestroyed()) {
      tileset.destroy()
    }
    ifcTilesets.delete(modelId)
    ifcTilesetModelIds.delete(tileset)
  }

  /** Releases every loaded primitive and tileset owned by the viewer. */
  const dispose = (viewer: Cesium.Viewer | null) => {
    glbPrimitives.forEach((record) => {
      if (viewer) viewer.scene.primitives.remove(record.primitive)
      if (!record.primitive.isDestroyed()) record.primitive.destroy()
      record.objectUrls.forEach((url) => URL.revokeObjectURL(url))
    })
    glbPrimitives.clear()

    ifcTilesets.forEach((tileset) => {
      if (viewer) viewer.scene.primitives.remove(tileset)
      if (!tileset.isDestroyed()) tileset.destroy()
    })
    ifcTilesets.clear()
    ifcTilesetModelIds.clear()
  }

  return {
    glbPrimitives,
    ifcTilesets,
    ifcTilesetModelIds,
    removeGlb,
    removeTileset,
    dispose,
  }
}
