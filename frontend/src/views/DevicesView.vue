<template>
  <div class="page">
    <!-- 设备统计 -->
    <div class="dev-stats">
      <div class="dev-stat">
        <span class="dev-stat__label">设备总数</span>
        <span class="dev-stat__value">{{ store.devices.length }}</span>
      </div>
      <div class="dev-stat">
        <span class="dev-stat__label">在线</span>
        <span class="dev-stat__value text-primary">{{ store.onlineDevices.length }}</span>
      </div>
      <div class="dev-stat">
        <span class="dev-stat__label">机器人在线</span>
        <span class="dev-stat__value">{{ store.onlineRobots.length }}</span>
      </div>
      <div class="dev-stat">
        <span class="dev-stat__label">离线/故障</span>
        <span class="dev-stat__value text-danger">
          {{ store.devices.filter((d) => d.status !== 'online').length }}
        </span>
      </div>
    </div>

    <div class="dev-layout">
      <!-- 设备列表 -->
      <section class="panel">
        <div class="panel-title">
          <span>设备清单</span>
          <div class="dev-filter">
            <button
              v-for="t in typeFilters"
              :key="t.key"
              :class="{ on: filterType === t.key }"
              @click="filterType = t.key"
            >
              {{ t.label }}
            </button>
          </div>
        </div>
        <div class="dev-list">
          <div
            v-for="d in filteredDevices"
            :key="d.device_id"
            class="dev-item"
            :class="{ 'dev-item--on': selected?.device_id === d.device_id }"
            @click="select(d)"
          >
            <div class="dev-item__head">
              <span class="dev-item__name">{{ d.name }}</span>
              <span class="badge" :class="`badge-${d.status}`">
                {{ DEVICE_STATUS[d.status] || d.status }}
              </span>
            </div>
            <div class="dev-item__meta">
              <span class="mono">{{ d.device_id }}</span>
              <span>{{ DEVICE_TYPE[d.device_type] || d.device_type }}</span>
            </div>
            <div class="dev-item__meta">
              <span class="mono">{{ fmtCoord(d.lng, d.lat) }}</span>
              <span>{{ d.last_heartbeat ? fmtRelative(d.last_heartbeat) : '无心跳' }}</span>
            </div>
          </div>
          <div v-if="!filteredDevices.length" class="empty">暂无设备</div>
        </div>
      </section>

      <!-- 右侧：地图 + 机器人详情 -->
      <div class="dev-right">
        <MapPanel
          class="dev-map"
          :heatmap="store.heatmap"
          :devices="store.devices"
          :robots="store.robots"
          :events="store.recentEvents.slice(0, 40)"
        />

        <section class="panel robot-detail">
          <div class="panel-title">
            <span>{{ selected ? selected.name : '选择设备查看详情' }}</span>
          </div>
          <div class="panel-body" v-if="selected">
            <div class="kv">
              <span class="kv__k">设备编号</span>
              <span class="kv__v mono">{{ selected.device_id }}</span>
            </div>
            <div class="kv">
              <span class="kv__k">设备类型</span>
              <span class="kv__v">{{ DEVICE_TYPE[selected.device_type] || selected.device_type }}</span>
            </div>
            <div class="kv">
              <span class="kv__k">坐标</span>
              <span class="kv__v mono">{{ fmtCoord(selected.lng, selected.lat, 6) }}</span>
            </div>
            <div class="kv">
              <span class="kv__k">最后心跳</span>
              <span class="kv__v">{{ selected.last_heartbeat ? fmtTime(selected.last_heartbeat) : '—' }}</span>
            </div>

            <!-- 机器人专属：三仓与电量 -->
            <template v-if="selected.device_type === 'robot'">
              <div class="kv">
                <span class="kv__k">电量</span>
                <span class="kv__v" :style="{ color: batteryColor(selected.meta?.battery) }">
                  {{ selected.meta?.battery ?? '—' }}%
                </span>
              </div>
              <div class="kv" v-for="(v, k) in (selected.meta?.bins || {})" :key="k">
                <span class="kv__k">{{ BIN_LABEL[k] || k }}</span>
                <span class="kv__v">{{ fmtUsage(v) }}</span>
              </div>
            </template>

            <!-- 摄像头专属：视频流 -->
            <template v-if="selected.device_type === 'shore_camera'">
              <div class="dev-video">
                <VideoPlayer
                  :key="selected.device_id"
                  :device-id="selected.device_id"
                  :name="selected.name"
                  :stream-url="selected.stream_url || ''"
                />
              </div>
              <div class="kv">
                <span class="kv__k">视频流</span>
                <span class="kv__v">
                  <span v-if="selected.stream_url" class="text-primary">已配置</span>
                  <span v-else class="text-dim">未配置</span>
                </span>
              </div>
            </template>

            <!-- 原始 meta -->
            <details class="dev-meta">
              <summary>原始扩展信息 (meta)</summary>
              <pre>{{ JSON.stringify(selected.meta || {}, null, 2) }}</pre>
            </details>
          </div>
          <div v-else class="empty">点击左侧设备查看详情</div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import MapPanel from '@/components/MapPanel.vue'
import VideoPlayer from '@/components/VideoPlayer.vue'
import { useRealtimeStore } from '@/stores/realtime'
import { DEVICE_STATUS, DEVICE_TYPE } from '@/utils/constants'
import { fmtCoord, fmtRelative, fmtTime, fmtUsage, batteryColor } from '@/utils/format'

const store = useRealtimeStore()

const selected = ref(null)
const filterType = ref('')

const typeFilters = [
  { key: '', label: '全部' },
  { key: 'shore_camera', label: '摄像头' },
  { key: 'robot', label: '机器人' },
  { key: 'drone', label: '无人机' },
]

const BIN_LABEL = { foam: '泡沫仓', plastic: '塑胶仓', mixed: '混合仓' }

const filteredDevices = computed(() =>
  filterType.value
    ? store.devices.filter((d) => d.device_type === filterType.value)
    : store.devices,
)

function select(device) {
  selected.value = device
}

onMounted(() => {
  if (!store.devices.length) store.loadOverview()
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.dev-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  flex-shrink: 0;
}

.dev-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 14px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.dev-stat__label {
  font-size: 12px;
  color: var(--text-sub);
}

.dev-stat__value {
  font-size: 20px;
  font-weight: 600;
  font-family: 'SF Mono', Consolas, monospace;
}

.dev-layout {
  display: grid;
  grid-template-columns: 1.3fr 2fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.dev-layout > .panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.dev-filter {
  display: flex;
  gap: 4px;
}

.dev-filter button {
  padding: 2px 9px;
  font-size: 12px;
  color: var(--text-sub);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
}

.dev-filter button.on {
  color: var(--c-primary);
  border-color: var(--c-primary-dim);
  background: rgba(18, 216, 196, 0.09);
}

.dev-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dev-item {
  padding: 8px 11px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.dev-item:hover {
  border-color: var(--border-bright);
}

.dev-item--on {
  border-color: var(--c-primary-dim);
  background: rgba(18, 216, 196, 0.07);
}

.dev-item__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 3px;
}

.dev-item__name {
  font-size: 13px;
  color: var(--text-main);
  font-weight: 500;
}

.dev-item__meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 11.5px;
  color: var(--text-sub);
}

.mono {
  font-family: 'SF Mono', Consolas, monospace;
}

/* 右侧 */
.dev-right {
  display: grid;
  grid-template-rows: 1.3fr 1fr;
  gap: 12px;
  min-height: 0;
}

.dev-map {
  min-height: 0;
}

.robot-detail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.robot-detail .panel-body {
  flex: 1;
  overflow-y: auto;
}

.kv {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(28, 42, 58, 0.5);
  font-size: 13px;
}

.kv__k { color: var(--text-sub); flex-shrink: 0; }
.kv__v { color: var(--text-main); text-align: right; word-break: break-all; }

.dev-video {
  height: 190px;
  margin: 10px 0;
}

.dev-meta {
  margin-top: 12px;
  font-size: 12px;
}

.dev-meta summary {
  color: var(--text-sub);
  cursor: pointer;
  padding: 5px 0;
}

.dev-meta pre {
  background: var(--bg-page);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 9px;
  overflow-x: auto;
  color: var(--text-sub);
  font-size: 11px;
  line-height: 1.6;
  font-family: 'SF Mono', Consolas, monospace;
}

@media (max-width: 1400px) {
  .dev-layout { grid-template-columns: 1fr; }
  .dev-right { grid-template-rows: 320px 1fr; }
}
</style>
