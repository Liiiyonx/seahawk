<template>
  <div class="dashboard">
    <!-- 指标卡 -->
    <StatCards :stats="store.stats" class="dashboard__stats" />

    <!-- 主区：左（视频宫格） 中（地图） 右（实时事件） -->
    <div class="dashboard__grid">
      <!-- 视频宫格 -->
      <section class="panel col-video">
        <div class="panel-title">
          <span>现场视频</span>
          <div class="video-switch">
            <button
              v-for="n in [1, 4]"
              :key="n"
              :class="{ on: gridSize === n }"
              @click="gridSize = n"
            >
              {{ n === 1 ? '单画面' : '四宫格' }}
            </button>
          </div>
        </div>
        <div class="video-grid" :class="`video-grid--${gridSize}`">
          <VideoPlayer
            v-for="cam in visibleCameras"
            :key="cam.device_id"
            :device-id="cam.device_id"
            :name="cam.name"
            :stream-url="cam.stream_url || ''"
            :detections="detectionsFor(cam.device_id)"
            class="video-grid__cell"
          />
          <div v-if="!visibleCameras.length" class="empty">暂无可用摄像头</div>
        </div>
      </section>

      <!-- 地图 -->
      <MapPanel
        class="col-map"
        :heatmap="store.heatmap"
        :devices="store.devices"
        :robots="store.robots"
        :events="store.recentEvents.slice(0, 60)"
      />

      <!-- 实时事件流 -->
      <section class="panel col-feed">
        <div class="panel-title">
          <span>实时告警</span>
          <span class="text-dim" style="font-size: 12px; font-weight: 400">
            {{ store.recentEvents.length }} 条
          </span>
        </div>
        <div class="feed">
          <div
            v-for="evt in store.recentEvents.slice(0, 30)"
            :key="evt.event_id"
            class="feed__item"
            :class="{ 'feed__item--new': evt._isNew }"
          >
            <div class="feed__head">
              <span class="feed__class">
                <i class="dot" :style="{ background: classColor(evt.main_class) }"></i>
                {{ classLabel(evt.main_class) }}
              </span>
              <span class="feed__time">{{ fmtRelative(evt.event_time) }}</span>
            </div>
            <div class="feed__meta">
              <span>{{ evt.device_id }}</span>
              <span>{{ evt.det_count || 1 }} 个目标</span>
              <span class="text-primary">{{ fmtConfidence(evt.max_confidence) }}</span>
            </div>
          </div>
          <div v-if="!store.recentEvents.length" class="empty">暂无告警事件</div>
        </div>
      </section>
    </div>

    <!-- 底部：趋势 + 类别分布 + 机器人状态 -->
    <div class="dashboard__bottom">
      <ChartPanel title="24 小时事件趋势" :option="trendOption" :height="180" class="bottom-chart" />
      <ChartPanel title="垃圾类别分布" :option="classOption" :height="180" class="bottom-chart" />

      <section class="panel robot-panel">
        <div class="panel-title">
          <span>机器人状态</span>
          <span class="text-dim" style="font-size: 12px; font-weight: 400">
            {{ store.onlineRobots.length }}/{{ store.robots.length }} 在线
          </span>
        </div>
        <div class="robot-list">
          <div v-for="r in store.robots" :key="r.robot_id" class="robot-item">
            <div class="robot-item__top">
              <span class="robot-item__name">{{ r.name || r.robot_id }}</span>
              <span class="badge" :class="badgeClass(r.status)">
                {{ STATUS_LABEL[r.status] || r.status }}
              </span>
            </div>
            <div class="robot-item__bars">
              <div class="bar">
                <span class="bar__label">电量</span>
                <div class="bar__track">
                  <div
                    class="bar__fill"
                    :style="{
                      width: `${r.battery ?? 0}%`,
                      background: batteryColor(r.battery),
                    }"
                  ></div>
                </div>
                <span class="bar__val">{{ r.battery ?? '—' }}%</span>
              </div>
              <div class="bar" v-for="(v, k) in (r.bins || {})" :key="k">
                <span class="bar__label">{{ BIN_LABEL[k] || k }}</span>
                <div class="bar__track">
                  <div
                    class="bar__fill bar__fill--bin"
                    :style="{ width: `${(Number(v) || 0) * 100}%` }"
                  ></div>
                </div>
                <span class="bar__val">{{ fmtUsage(v) }}</span>
              </div>
            </div>
          </div>
          <div v-if="!store.robots.length" class="empty">暂无机器人接入</div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
/**
 * 监测大屏 —— 平台的门面，也是评委会第一眼看的东西。
 *
 * 布局取舍：视频与地图是"现场感"来源，必须占最大面积；
 * 告警流放右侧是因为它变化最快，眼睛扫一眼就能读到；
 * 趋势/类别/机器人放底部，属于"态势"而非"现场"。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import StatCards from '@/components/StatCards.vue'
import VideoPlayer from '@/components/VideoPlayer.vue'
import MapPanel from '@/components/MapPanel.vue'
import ChartPanel from '@/components/ChartPanel.vue'
import { useRealtimeStore } from '@/stores/realtime'
import { statsApi } from '@/api'
import {
  classLabel,
  classColor,
  CLASS_ORDER,
  WASTE_CLASSES,
} from '@/utils/constants'
import { fmtRelative, fmtConfidence, fmtUsage, batteryColor } from '@/utils/format'

const store = useRealtimeStore()
const gridSize = ref(4)

const STATUS_LABEL = {
  online: '在线',
  offline: '离线',
  idle: '待命',
  navigating: '前往中',
  collecting: '作业中',
  assigned: '已派单',
}

const BIN_LABEL = { foam: '泡沫仓', plastic: '塑胶仓', mixed: '混合仓' }

function badgeClass(status) {
  const map = {
    online: 'badge-online',
    idle: 'badge-online',
    offline: 'badge-offline',
    navigating: 'badge-navigating',
    collecting: 'badge-collecting',
    assigned: 'badge-assigned',
  }
  return map[status] || 'badge-offline'
}

// 只把设备类型是摄像头的放进宫格（无人机没有 RTSP 常驻流）
const cameras = computed(() =>
  store.devices.filter((d) => d.device_type === 'shore_camera'),
)
const visibleCameras = computed(() =>
  gridSize.value === 1 ? cameras.value.slice(0, 1) : cameras.value.slice(0, 4),
)

/** 某设备最近一条事件里的检测框（用于画面叠加） */
function detectionsFor(deviceId) {
  const evt = store.recentEvents.find((e) => e.device_id === deviceId)
  return evt?.detections || []
}

// ---------- 图表 ----------
const trend = ref([])
const classes = ref([])

async function loadCharts() {
  try {
    const [t, c] = await Promise.all([statsApi.trend(24), statsApi.classes(24)])
    trend.value = t || []
    classes.value = c || []
  } catch {
    /* 图表失败不阻断大屏 */
  }
}

const trendOption = computed(() => ({
  grid: { left: 42, right: 14, top: 20, bottom: 26 },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: trend.value.map((d) => {
      const dt = new Date(d.time)
      return `${String(dt.getHours()).padStart(2, '0')}:00`
    }),
    axisLine: { lineStyle: { color: '#1c2a3a' } },
    axisLabel: { color: '#8b96a8', fontSize: 11 },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#141f2b' } },
    axisLabel: { color: '#8b96a8', fontSize: 11 },
  },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: trend.value.map((d) => d.count),
      lineStyle: { color: '#12d8c4', width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(18,216,196,0.34)' },
            { offset: 1, color: 'rgba(18,216,196,0.02)' },
          ],
        },
      },
    },
  ],
}))

const classOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} 条 ({d}%)' },
  legend: {
    orient: 'vertical',
    right: 6,
    top: 'center',
    textStyle: { color: '#8b96a8', fontSize: 11 },
    itemWidth: 9,
    itemHeight: 9,
  },
  series: [
    {
      type: 'pie',
      radius: ['48%', '72%'],
      center: ['36%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#0d1620', borderWidth: 2 },
      label: { show: false },
      data: CLASS_ORDER.map((k) => {
        const found = classes.value.find((c) => c.main_class === k)
        return {
          name: WASTE_CLASSES[k].label,
          value: found?.count || 0,
          itemStyle: { color: WASTE_CLASSES[k].color },
        }
      }).filter((d) => d.value > 0),
    },
  ],
}))

// ---------- 定时 ----------
let chartTimer = null

onMounted(async () => {
  await loadCharts()
  chartTimer = setInterval(loadCharts, 60000)
})

onUnmounted(() => clearInterval(chartTimer))
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.dashboard__stats {
  flex-shrink: 0;
}

/* 主区三列：视频 3 / 地图 4 / 告警 2.4 */
.dashboard__grid {
  display: grid;
  grid-template-columns: 3fr 4fr 2.4fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.col-video,
.col-map,
.col-feed {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.video-switch {
  display: flex;
  gap: 4px;
}

.video-switch button {
  padding: 2px 9px;
  font-size: 12px;
  color: var(--text-sub);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
}

.video-switch button.on {
  color: var(--c-primary);
  border-color: var(--c-primary-dim);
  background: rgba(18, 216, 196, 0.09);
}

.video-grid {
  flex: 1;
  min-height: 0;
  padding: 8px;
  display: grid;
  gap: 6px;
}

.video-grid--1 { grid-template-columns: 1fr; }
.video-grid--4 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }

.video-grid__cell {
  min-height: 0;
}

/* 告警流 */
.feed {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px;
}

.feed__item {
  padding: 7px 9px;
  border-radius: 4px;
  border-left: 2px solid transparent;
  transition: background 0.15s;
}

.feed__item:hover {
  background: var(--bg-hover);
}

.feed__item--new {
  border-left-color: var(--c-warn);
  background: rgba(245, 166, 35, 0.09);
}

.feed__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.feed__class {
  font-size: 13px;
  color: var(--text-main);
}

.feed__time {
  font-size: 11px;
  color: var(--text-dim);
}

.feed__meta {
  display: flex;
  gap: 10px;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-sub);
  font-family: 'SF Mono', Consolas, monospace;
}

/* 底部一行 */
.dashboard__bottom {
  display: grid;
  grid-template-columns: 1fr 1fr 1.1fr;
  gap: 12px;
  flex-shrink: 0;
}

.bottom-chart {
  min-height: 0;
}

.robot-panel {
  display: flex;
  flex-direction: column;
  max-height: 230px;
}

.robot-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px;
}

.robot-item {
  padding: 7px 0;
  border-bottom: 1px solid rgba(28, 42, 58, 0.5);
}

.robot-item:last-child {
  border-bottom: none;
}

.robot-item__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
}

.robot-item__name {
  font-size: 13px;
  color: var(--text-main);
}

.robot-item__bars {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.bar {
  display: grid;
  grid-template-columns: 48px 1fr 40px;
  align-items: center;
  gap: 7px;
  font-size: 11px;
}

.bar__label {
  color: var(--text-sub);
}

.bar__track {
  height: 4px;
  background: var(--bg-panel-2);
  border-radius: 2px;
  overflow: hidden;
}

.bar__fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s;
}

.bar__fill--bin {
  background: var(--c-info);
}

.bar__val {
  color: var(--text-sub);
  text-align: right;
  font-family: 'SF Mono', Consolas, monospace;
}

@media (max-width: 1500px) {
  .dashboard__grid { grid-template-columns: 1fr 1.3fr; }
  .col-feed { grid-column: span 2; max-height: 220px; }
  .dashboard__bottom { grid-template-columns: 1fr 1fr; }
}
</style>
