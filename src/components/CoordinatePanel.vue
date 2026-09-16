<script setup lang="ts">
import { ref, watch } from 'vue'
import * as Cesium from 'cesium'
import { logError, logInfo, logWarn } from '../features/console/appConsole'

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

    logInfo(`搜索到地点：${searchText.value}`, { longitude, latitude })
    updateCoordinates(position)
  } catch (error) {
    logError('搜索失败:', error)
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
    logWarn('经纬度输入无效（经度 -180~180，纬度 -90~90）', { lon, lat })
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

  logInfo('按经纬度定位', { longitude: lon, latitude: lat })
  updateCoordinates(position)
}
</script>

<template>
  <div class="coordinate-cluster">
    <div class="search-bar">
      <input
        v-model="searchText"
        class="search-input"
        type="text"
        placeholder="搜索地点名称…"
        @keydown.enter="handleSearch"
      />
      <button class="search-button" title="搜索" @click="handleSearch">
        <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
          <circle
            cx="7"
            cy="7"
            r="4.2"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
          />
          <path
            d="M10.2 10.2 13.5 13.5"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
          />
        </svg>
      </button>
    </div>

    <div class="coord-row">
      <input
        v-model="longitudeInput"
        class="coord-input"
        type="number"
        step="any"
        placeholder="经度"
      />
      <input
        v-model="latitudeInput"
        class="coord-input"
        type="number"
        step="any"
        placeholder="纬度"
      />
      <button
        class="compass-button"
        title="按经纬度定位"
        @click="handleCoordinateInput"
      >
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <circle
            cx="8"
            cy="8"
            r="6.1"
            fill="none"
            stroke="currentColor"
            stroke-width="1.3"
          />
          <path
            d="M10.6 5.4 9.2 9.2 5.4 10.6 6.8 6.8Z"
            fill="currentColor"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.coordinate-cluster {
  /* Light theme tokens; a dark theme only needs to override this block. */
  --cp-bg: #ffffff;
  --cp-fg: #24292f;
  --cp-muted: #6e7781;
  --cp-border: #e6e8eb;
  --cp-accent: #1a56db;
  --cp-accent-hover: #1545af;
  --cp-accent-soft: #f2f7ff;
  --cp-accent-border: #c9dcfb;
  --cp-accent-ring: rgba(26, 86, 219, 0.12);
  --cp-field-border: #d7dbe0;
  --cp-placeholder: #9aa4ae;
  --cp-shadow: 0 2px 8px rgba(15, 23, 42, 0.14);

  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  width: 420px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--cp-fg);
  font-size: 13px;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.search-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 38px;
  padding: 0 16px;
  font-family: inherit;
  font-size: 13.5px;
  color: var(--cp-fg);
  background: var(--cp-bg);
  border: 1px solid var(--cp-field-border);
  border-radius: 19px;
  box-shadow: var(--cp-shadow);
  outline: none;
}

.search-input::placeholder {
  color: var(--cp-placeholder);
}

.search-input:focus {
  border-color: var(--cp-accent-border);
  box-shadow: 0 0 0 3px var(--cp-accent-ring);
}

.search-button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  padding: 0;
  color: #ffffff;
  background: var(--cp-accent);
  border: none;
  border-radius: 50%;
  box-shadow: var(--cp-shadow);
  cursor: pointer;
}

.search-button:hover {
  background: var(--cp-accent-hover);
}

.coord-row {
  display: flex;
  align-items: center;
  gap: 6px;
  /* Inset from both sides and 20% narrower than the search bar. */
  width: 80%;
  margin: 0 auto;
}

.coord-input {
  flex: 1 1 0;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  font-family: inherit;
  font-size: 11.5px;
  color: var(--cp-fg);
  background: var(--cp-bg);
  border: 1px solid var(--cp-field-border);
  border-radius: 5px;
  box-shadow: var(--cp-shadow);
}

.coord-input::placeholder {
  color: var(--cp-placeholder);
}

.coord-input:focus {
  outline: none;
  border-color: var(--cp-accent-border);
  box-shadow: 0 0 0 2px var(--cp-accent-ring);
}

.compass-button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--cp-accent);
  background: var(--cp-bg);
  border: 1px solid var(--cp-accent-border);
  border-radius: 50%;
  box-shadow: var(--cp-shadow);
  cursor: pointer;
}

.compass-button:hover {
  color: var(--cp-accent-hover);
  background: var(--cp-accent-soft);
}
</style>
