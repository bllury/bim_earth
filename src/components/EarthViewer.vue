<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import { pickIfcFeatures } from '../lib/ifcPicking'
import type { PickedIfcFeature } from '../lib/ifcPicking'
import {
  hiddenElementKeys,
  ifcTilesetModelIds,
} from '../features/viewer/selectionState'

const props = defineProps<{
  selectedPosition: Cesium.Cartesian3 | null
}>()

const emit = defineEmits<{
  viewerReady: [viewer: Cesium.Viewer]
  positionChange: [position: Cesium.Cartesian3]
  ifcFeaturePicked: [feature: PickedIfcFeature | null]
}>()

const container = ref<HTMLDivElement | null>(null)
const viewer = shallowRef<Cesium.Viewer | null>(null)
const markerEntity = shallowRef<Cesium.Entity | null>(null)
const clickHandler = shallowRef<Cesium.ScreenSpaceEventHandler | null>(null)

/** Recreates the coordinate marker and label at the selected world position. */
const updateMarker = () => {
  const currentViewer = viewer.value
  if (!currentViewer) return

  if (markerEntity.value) {
    currentViewer.entities.remove(markerEntity.value)
    markerEntity.value = null
  }

  if (!props.selectedPosition) return

  const cartographic = Cesium.Cartographic.fromCartesian(props.selectedPosition)
  const longitude = Cesium.Math.toDegrees(cartographic.longitude)
  const latitude = Cesium.Math.toDegrees(cartographic.latitude)

  markerEntity.value = currentViewer.entities.add({
    id: 'placement-marker',
    position: props.selectedPosition,
    point: {
      pixelSize: 16,
      color: Cesium.Color.fromCssColorString('#ff3b30'),
      heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    },
    label: {
      text:
        `经度 ${longitude.toFixed(6)}°\n` +
        `纬度 ${latitude.toFixed(6)}°\n` +
        `高度 ${cartographic.height.toFixed(2)}m`,
      font: '14px sans-serif',
      pixelOffset: new Cesium.Cartesian2(0, -32),
      showBackground: true,
      backgroundColor: Cesium.Color.fromCssColorString('#ffffff').withAlpha(0.9),
      fillColor: Cesium.Color.fromCssColorString('#111111'),
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
      verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
      heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
      disableDepthTestDistance: Number.POSITIVE_INFINITY,
    },
  })
}

watch(
  () => props.selectedPosition,
  () => updateMarker(),
)

onMounted(() => {
  if (!container.value) return

  const currentViewer = new Cesium.Viewer(container.value, {
    animation: false,
    baseLayerPicker: false,
    fullscreenButton: true,
    geocoder: false,
    homeButton: true,
    infoBox: false,
    sceneModePicker: false,
    selectionIndicator: false,
    timeline: false,
    navigationHelpButton: false,
    baseLayer: new Cesium.ImageryLayer(
      new Cesium.UrlTemplateImageryProvider({
        url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
        subdomains: ['1', '2', '3', '4'],
        minimumLevel: 3,
        maximumLevel: 18,
      }),
    ),
  })

  currentViewer.scene.globe.enableLighting = false

  const skyAtmosphere = currentViewer.scene.skyAtmosphere
  const sun = currentViewer.scene.sun
  const moon = currentViewer.scene.moon
  if (skyAtmosphere) skyAtmosphere.show = false
  if (sun) sun.show = false
  if (moon) moon.show = false

  currentViewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(116.397, 39.908, 20000000),
  })

  viewer.value = currentViewer

  const handler = new Cesium.ScreenSpaceEventHandler(currentViewer.scene.canvas)
  handler.setInputAction((event: { position: Cesium.Cartesian2 }) => {
    const ifcFeatures = pickIfcFeatures(currentViewer, event.position)
    const pickableFeature = ifcFeatures.find((feature) => {
      const modelId = ifcTilesetModelIds.get(feature.tileset)
      return Boolean(
        modelId &&
          feature.ifcGuid &&
          !hiddenElementKeys.value.has(`${modelId}:${feature.ifcGuid}`),
      )
    })

    if (pickableFeature) {
      emit('ifcFeaturePicked', pickableFeature)
      return
    }

    if (ifcFeatures.length > 0) {
      emit('ifcFeaturePicked', null)
      return
    }

    const earthPosition = currentViewer.scene.pickPosition(event.position)
    if (Cesium.defined(earthPosition)) {
      emit('positionChange', earthPosition)
    }
    emit('ifcFeaturePicked', null)
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
  clickHandler.value = handler

  emit('viewerReady', currentViewer)
})

onBeforeUnmount(() => {
  if (clickHandler.value) {
    clickHandler.value.destroy()
    clickHandler.value = null
  }

  if (viewer.value && !viewer.value.isDestroyed()) {
    viewer.value.destroy()
  }

  viewer.value = null
  markerEntity.value = null
})
</script>

<template>
  <div ref="container" class="earth-viewer" />
</template>

<style scoped>
.earth-viewer {
  width: 100%;
  height: 100vh;
  position: relative;
}
</style>
