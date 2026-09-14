import { ref } from 'vue'
import type * as Cesium from 'cesium'

export const hiddenElementKeys = ref<Set<string>>(new Set())
export const ifcTilesetModelIds = new Map<Cesium.Cesium3DTileset, string>()
