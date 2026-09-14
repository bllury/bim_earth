<script setup lang="ts">
import { ref, watch } from 'vue'
import * as Cesium from 'cesium'

const props = defineProps<{
  viewer: Cesium.Viewer | null
  selectedPosition: Cesium.Cartesian3 | null
}>()

const emit = defineEmits<{
  coordinateSelected: [position: Cesium.Cartesian3, lon: number, lat: number]
}>()

const searchText = ref('')
const coordinates = ref<{ lon: number; lat: number; height: number } | null>(null)
const longitudeInput = ref('')
const latitudeInput = ref('')

const AMAP_WEB_SERVICE_KEY = import.meta.env.VITE_AMAP_KEY as string | undefined

const geocodeAmap = (address: string) => {
  return new Promise<{ longitude: number; latitude: number }>((resolve, reject) => {
    if (!AMAP_WEB_SERVICE_KEY) {
      reject(new Error('请先配置高德地图 API Key（VITE_AMAP_KEY）'))
      return
    }

    const callbackName = `amapGeocodeCallback_${Date.now()}_${Math.random().toString(36).slice(2)}`
    const script = document.createElement('script')
    let settled = false

    const cleanup = () => {
      if (script.parentNode) {
        script.parentNode.removeChild(script)
      }
      delete (window as unknown as Record<string, unknown>)[callbackName]
    }

    const timeout = window.setTimeout(() => {
      if (settled) return
      settled = true
      cleanup()
      reject(new Error('高德地图搜索超时，请检查网络或 API Key'))
    }, 10000)

    ;(window as unknown as Record<string, unknown>)[callbackName] = (data: {
      geocodes?: Array<{ location?: string }>
      info?: string
    }) => {
      if (settled) return
      settled = true
      window.clearTimeout(timeout)
      cleanup()

      const location = data?.geocodes?.[0]?.location
      if (!location) {
        reject(new Error(data?.info || '未找到该地点'))
        return
      }

      const [longitudeText, latitudeText] = String(location).split(',')
      const longitude = parseFloat(longitudeText)
      const latitude = parseFloat(latitudeText)

      if (isNaN(longitude) || isNaN(latitude)) {
        reject(new Error('高德地图返回了无效的经纬度'))
        return
      }

      resolve({ longitude, latitude })
    }

    script.onerror = () => {
      if (settled) return
      settled = true
      window.clearTimeout(timeout)
      cleanup()
      reject(new Error('高德地图搜索请求失败，请检查网络或 API Key'))
    }

    script.src =
      'https://restapi.amap.com/v3/geocode/geo' +
      `?key=${encodeURIComponent(AMAP_WEB_SERVICE_KEY)}` +
      `&address=${encodeURIComponent(address)}` +
      '&output=JSON' +
      `&callback=${encodeURIComponent(callbackName)}`

    document.head.appendChild(script)
  })
}

const updateCoordinates = (
  position: Cesium.Cartesian3,
  emitSelection = true,
) => {
  const cartographic = Cesium.Cartographic.fromCartesian(position)
  const lon = Cesium.Math.toDegrees(cartographic.longitude)
  const lat = Cesium.Math.toDegrees(cartographic.latitude)
  const height = cartographic.height

  coordinates.value = { lon, lat, height }
  longitudeInput.value = lon.toFixed(6)
  latitudeInput.value = lat.toFixed(6)
  if (emitSelection) {
    emit('coordinateSelected', position, lon, lat)
  }
}

watch(
  () => props.selectedPosition,
  (position) => {
    if (position) updateCoordinates(position, false)
  },
  { immediate: true },
)

const handleSearch = async () => {
  if (!searchText.value.trim() || !props.viewer) return

  try {
    const { longitude, latitude } = await geocodeAmap(searchText.value)
    const position = Cesium.Cartesian3.fromDegrees(longitude, latitude, 0)

    props.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(longitude, latitude, 10000),
      duration: 2,
    })

    updateCoordinates(position)
  } catch (error) {
    console.error('搜索失败:', error)
    alert(error instanceof Error ? error.message : '搜索失败，请检查网络连接')
  }
}

const handleCoordinateInput = () => {
  const lon = parseFloat(longitudeInput.value)
  const lat = parseFloat(latitudeInput.value)

  if (
    isNaN(lon) ||
    isNaN(lat) ||
    lon < -180 ||
    lon > 180 ||
    lat < -90 ||
    lat > 90
  ) {
    alert('请输入有效的经度（-180 到 180）和纬度（-90 到 90）')
    return
  }

  const position = Cesium.Cartesian3.fromDegrees(lon, lat, 0)
  if (props.viewer) {
    props.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(lon, lat, 10000),
      duration: 2,
    })
  }

  updateCoordinates(position)
}
</script>

<template>
  <div class="coordinate-panel">
    <h3>📍 坐标选择</h3>

    <div class="search-row">
      <input
        v-model="searchText"
        type="text"
        placeholder="搜索地点名称..."
        @keydown.enter="handleSearch"
      />
      <button @click="handleSearch">搜索</button>
    </div>

    <div class="manual-coordinate-row">
      <input v-model="longitudeInput" type="number" step="any" placeholder="经度" />
      <input v-model="latitudeInput" type="number" step="any" placeholder="纬度" />
      <button class="manual-button" @click="handleCoordinateInput">定位</button>
    </div>

    <div v-if="coordinates" class="coordinate-info">
      <div><strong>当前选择位置：</strong></div>
      <div>经度: {{ coordinates.lon.toFixed(6) }}°</div>
      <div>纬度: {{ coordinates.lat.toFixed(6) }}°</div>
      <div>高度: {{ coordinates.height.toFixed(2) }}m</div>
    </div>

    <div class="hint">
      📍 点击地球或搜索地点选择新模型放置位置；在模型管理中通过经纬度更新坐标微调模型。
    </div>
  </div>
</template>

<style scoped>
.coordinate-panel {
  position: absolute;
  top: 20px;
  left: 20px;
  z-index: 1000;
  background: white;
  padding: 15px;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  width: 280px;
}

h3 {
  margin: 0 0 10px 0;
}

.search-row {
  display: flex;
  gap: 5px;
  margin-bottom: 10px;
}

.search-row input {
  flex: 1;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.search-row button {
  padding: 8px 12px;
  background: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.manual-button {
  width: 100%;
  padding: 8px;
  margin-bottom: 10px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.manual-coordinate-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 5px;
  margin-bottom: 10px;
}

.manual-coordinate-row input {
  min-width: 0;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}

.manual-coordinate-row .manual-button {
  width: auto;
  margin-bottom: 0;
  padding: 8px 12px;
}

.coordinate-info {
  padding: 10px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 13px;
}

.hint {
  margin-top: 10px;
  font-size: 12px;
  color: #666;
}
</style>
