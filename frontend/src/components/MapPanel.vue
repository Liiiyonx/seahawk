<template>
  <div class="map-panel panel">
    <div class="panel-title">
      <span>垃圾分布热力与设备态势</span>
      <div class="map-legend">
        <span v-for="c in legend" :key="c.key" class="map-legend__item">
          <i class="dot" :style="{ background: c.color }"></i>{{ c.label }}
        </span>
      </div>
    </div>
    <div class="map-panel__body">
      <div id="seasight-map" ref="mapEl"></div>

      <!-- 图层开关 -->
      <div class="map-tools">
        <label v-for="layer in layers" :key="layer.key" class="map-tools__item">
          <input type="checkbox" v-model="layer.on" @change="refresh" />
          <span>{{ layer.label }}</span>
        </label>
      </div>

      <!-- 加载失败兜底 -->
      <div v-if="loadError" class="map-error">
        <p>地图加载失败</p>
        <p class="map-error__hint">{{ loadError }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 地图组件（腾讯地图 GL JS）。
 *
 * ★ 合规说明
 *   地图服务只允许使用腾讯地图 / 高德 / 百度 / 天地图。
 *   本项目用腾讯地图，且采用官方的 key 代理模式：
 *   - SDK 从官方 CDN 加载，URL 上**不带 key 参数**
 *   - SDK 内部请求自动走本地代理，密钥由后端持有
 *   - 前端不出现任何密钥，避免被反编译窃取
 *
 * 注意：_TMapSecurityConfig 必须在 SDK script 标签之前设置。
 * 两者同时用会白屏，所以这里不能在组件内再调 setConfig。
 */
import { ref, onMounted, onUnmounted, watch, reactive } from 'vue'
import { classColor, classLabel, CLASS_ORDER } from '@/utils/constants'

const props = defineProps({
  /** 热力图网格：[{lng, lat, count, density, main_class}] */
  heatmap: { type: Array, default: () => [] },
  /** 设备：[{device_id, name, lng, lat, status, device_type}] */
  devices: { type: Array, default: () => [] },
  /** 机器人：[{robot_id, name, lng, lat, status, battery}] */
  robots: { type: Array, default: () => [] },
  /** 近期事件（用于打点） */
  events: { type: Array, default: () => [] },
  center: { type: Object, default: () => ({ lng: 119.86, lat: 26.35 }) },
  zoom: { type: Number, default: 11 },
})

const mapEl = ref(null)
const loadError = ref('')

const layers = reactive([
  { key: 'heat', label: '热力分布', on: true },
  { key: 'cameras', label: '摄像头', on: true },
  { key: 'robots', label: '机器人', on: true },
  { key: 'events', label: '事件点', on: true },
])

const legend = CLASS_ORDER.map((k) => ({
  key: k,
  label: classLabel(k),
  color: classColor(k),
}))

let map = null
let heatLayer = null
let cameraLayer = null
let robotLayer = null
let eventLayer = null

const SDK_URL = 'https://map.qq.com/api/gljs?v=1.exp'
const WB_PROXY = 'http://127.0.0.1:__WB_HTTP_PORT__/_TMapService/_wbt/__WB_TMAP_SECRET__'

// ----------------------------------------------------------------------
// SDK 加载
// ----------------------------------------------------------------------
function loadSdk() {
  return new Promise((resolve, reject) => {
    if (window.TMap) {
      resolve()
      return
    }

    // key 代理配置 —— 必须早于 SDK 脚本
    window._TMapSecurityConfig = { serviceHost: WB_PROXY }

    const script = document.createElement('script')
    script.src = SDK_URL
    script.async = true
    script.onload = () => (window.TMap ? resolve() : reject(new Error('SDK 加载后未挂载 TMap')))
    script.onerror = () => reject(new Error('无法从 CDN 加载腾讯地图 SDK（检查网络）'))
    document.head.appendChild(script)
  })
}

// ----------------------------------------------------------------------
// 图标（内联 SVG，不引用官方 demo 图片路径）
// ----------------------------------------------------------------------
function svgIcon(color, shape = 'pin') {
  const svg =
    shape === 'boat'
      ? `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 30 30">
           <circle cx="15" cy="15" r="12" fill="${color}" opacity="0.22"/>
           <circle cx="15" cy="15" r="6" fill="${color}" stroke="#070d14" stroke-width="1.5"/>
         </svg>`
      : shape === 'dot'
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
             <circle cx="8" cy="8" r="4" fill="${color}" stroke="#070d14" stroke-width="1.4"/>
           </svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="30" viewBox="0 0 26 30">
             <path d="M13 1C7 1 2.5 5.6 2.5 11.4c0 7.4 10.5 17.6 10.5 17.6s10.5-10.2 10.5-17.6C23.5 5.6 19 1 13 1z"
                   fill="${color}" stroke="#070d14" stroke-width="1.4"/>
             <circle cx="13" cy="11" r="3.6" fill="#070d14" opacity="0.65"/>
           </svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

// ----------------------------------------------------------------------
// 图层构建
// ----------------------------------------------------------------------
function buildHeatLayer() {
  if (heatLayer) {
    heatLayer.setMap(null)
    heatLayer = null
  }
  if (!layers.find((l) => l.key === 'heat')?.on) return
  if (!props.heatmap?.length) return

  // 网格中心点 + 按事件数决定半径与透明度。
  // ★ 用密度而非总数决定颜色深浅 —— 网格大小不同时总数没有可比性。
  const maxDensity = Math.max(...props.heatmap.map((c) => c.density || 0), 1e-9)

  const geometries = props.heatmap.map((cell, i) => {
    const ratio = Math.min(1, (cell.density || 0) / maxDensity)
    const color = classColor(cell.main_class || 'other')
    return {
      id: `heat-${i}`,
      styleId: `heat-${Math.round(ratio * 5)}`,
      position: new window.TMap.LatLng(cell.lat, cell.lng),
    }
  })

  const styles = {}
  for (let i = 0; i <= 5; i++) {
    const ratio = i / 5
    styles[`heat-${i}`] = new window.TMap.CircleStyle({
      color: classColor('foam'),
      showBorder: false,
      // 半径按网格边长的一半缩放（500m 网格 → 半径约 250m 对应像素）
      radius: 14 + ratio * 26,
      opacity: 0.14 + ratio * 0.46,
    })
  }

  heatLayer = new window.TMap.MultiCircle({
    map,
    styles,
    geometries,
  })
}

function buildCameraLayer() {
  if (cameraLayer) {
    cameraLayer.setMap(null)
    cameraLayer = null
  }
  if (!layers.find((l) => l.key === 'cameras')?.on) return

  const cams = (props.devices || []).filter((d) => d.device_type !== 'robot')
  if (!cams.length) return

  cameraLayer = new window.TMap.MultiMarker({
    map,
    styles: {
      online: new window.TMap.MarkerStyle({
        width: 22,
        height: 26,
        anchor: { x: 11, y: 26 },
        src: svgIcon('#12d8c4'),
      }),
      offline: new window.TMap.MarkerStyle({
        width: 22,
        height: 26,
        anchor: { x: 11, y: 26 },
        src: svgIcon('#5a6678'),
      }),
    },
    geometries: cams.map((d) => ({
      id: d.device_id,
      styleId: d.status === 'online' ? 'online' : 'offline',
      position: new window.TMap.LatLng(d.lat, d.lng),
      properties: {
        title: d.name,
        content: `<div style="font-size:12px;line-height:1.7">
          <b>${d.name}</b><br/>
          编号：${d.device_id}<br/>
          状态：${d.status === 'online' ? '在线' : '离线'}
        </div>`,
      },
    })),
  })

  cameraLayer.on('click', (evt) => {
    const p = evt.geometry?.properties
    if (p) showInfo(p.title, p.content)
  })
}

function buildRobotLayer() {
  if (robotLayer) {
    robotLayer.setMap(null)
    robotLayer = null
  }
  if (!layers.find((l) => l.key === 'robots')?.on) return
  if (!props.robots?.length) return

  robotLayer = new window.TMap.MultiMarker({
    map,
    styles: {
      idle: new window.TMap.MarkerStyle({
        width: 28,
        height: 28,
        anchor: { x: 14, y: 14 },
        src: svgIcon('#4a9eff', 'boat'),
      }),
      busy: new window.TMap.MarkerStyle({
        width: 28,
        height: 28,
        anchor: { x: 14, y: 14 },
        src: svgIcon('#12d8c4', 'boat'),
      }),
      offline: new window.TMap.MarkerStyle({
        width: 28,
        height: 28,
        anchor: { x: 14, y: 14 },
        src: svgIcon('#5a6678', 'boat'),
      }),
    },
    geometries: (props.robots || []).map((r) => {
      const busy = ['navigating', 'collecting', 'assigned'].includes(r.status)
      const styleId =
        r.status === 'online' || busy ? (busy ? 'busy' : 'idle') : 'offline'
      return {
        id: r.robot_id,
        styleId,
        position: new window.TMap.LatLng(r.lat, r.lng),
        properties: {
          title: r.name || r.robot_id,
          content: `<div style="font-size:12px;line-height:1.7">
            <b>${r.name || r.robot_id}</b><br/>
            编号：${r.robot_id}<br/>
            状态：${r.status}<br/>
            电量：${r.battery ?? '—'}%
          </div>`,
        },
      }
    }),
  })

  robotLayer.on('click', (evt) => {
    const p = evt.geometry?.properties
    if (p) showInfo(p.title, p.content)
  })
}

function buildEventLayer() {
  if (eventLayer) {
    eventLayer.setMap(null)
    eventLayer = null
  }
  if (!layers.find((l) => l.key === 'events')?.on) return

  const events = props.events || []
  if (!events.length) return

  const styles = {}
  for (const cls of CLASS_ORDER) {
    styles[cls] = new window.TMap.MarkerStyle({
      width: 16,
      height: 16,
      anchor: { x: 8, y: 8 },
      src: svgIcon(classColor(cls), 'dot'),
    })
  }

  eventLayer = new window.TMap.MultiMarker({
    map,
    styles,
    geometries: events.map((e, i) => ({
      id: e.event_id || `evt-${i}`,
      styleId: CLASS_ORDER.includes(e.main_class) ? e.main_class : 'other',
      position: new window.TMap.LatLng(e.lat, e.lng),
      properties: {
        title: `${classLabel(e.main_class)} ${e.det_count || 1} 个`,
        content: `<div style="font-size:12px;line-height:1.7">
          <b>${classLabel(e.main_class)}</b><br/>
          设备：${e.device_id || '—'}<br/>
          数量：${e.det_count || 1}<br/>
          置信度：${e.max_confidence ? (Number(e.max_confidence) * 100).toFixed(0) + '%' : '—'}
        </div>`,
      },
    })),
  })

  eventLayer.on('click', (evt) => {
    const p = evt.geometry?.properties
    if (p) showInfo(p.title, p.content)
  })
}

let infoWindow = null
function showInfo(title, content) {
  if (!infoWindow) {
    infoWindow = new window.TMap.InfoWindow({
      map,
      offset: { x: 0, y: -30 },
    })
  }
  infoWindow.setContent(content)
  infoWindow.setPosition(null)
  // 简化处理：直接用内容替换，不强制定位（避免与 marker 位置耦合）
  infoWindow.open()
}

function refresh() {
  if (!map) return
  buildHeatLayer()
  buildCameraLayer()
  buildRobotLayer()
  buildEventLayer()
}

// ----------------------------------------------------------------------
// 生命周期
// ----------------------------------------------------------------------
onMounted(async () => {
  try {
    await loadSdk()

    map = new window.TMap.Map(mapEl.value, {
      zoom: props.zoom,
      center: new window.TMap.LatLng(props.center.lat, props.center.lng),
      // ★ 不传 mapStyleId —— 自定义样式需在控制台单独开通，否则底图变灰
      baseMap: { type: 'vector' },
    })

    refresh()
  } catch (err) {
    loadError.value = err.message || String(err)
  }
})

onUnmounted(() => {
  for (const layer of [heatLayer, cameraLayer, robotLayer, eventLayer]) {
    try {
      layer?.setMap(null)
    } catch {
      /* 忽略 */
    }
  }
  map = null
})

watch(
  () => [props.heatmap, props.devices, props.robots, props.events],
  refresh,
  { deep: false },
)
</script>

<style scoped>
.map-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.map-panel__body {
  position: relative;
  flex: 1;
  min-height: 320px;
}

#seasight-map {
  width: 100%;
  height: 100%;
  min-height: 320px;
  background: var(--bg-panel-2);
}

.map-legend {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--text-sub);
  font-weight: 400;
}

.map-legend__item {
  display: flex;
  align-items: center;
}

.map-tools {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(7, 13, 20, 0.9);
  border: 1px solid var(--border-bright);
  border-radius: var(--radius);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  z-index: 5;
}

.map-tools__item {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-sub);
  cursor: pointer;
  user-select: none;
}

.map-tools__item input {
  accent-color: var(--c-primary);
  cursor: pointer;
}

.map-error {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--bg-panel-2);
  color: var(--text-sub);
  font-size: 13px;
}

.map-error__hint {
  font-size: 12px;
  color: var(--text-dim);
}
</style>
