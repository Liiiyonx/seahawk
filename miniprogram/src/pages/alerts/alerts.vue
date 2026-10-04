<template>
  <view class="alerts">
    <!-- 连接状态条 -->
    <view class="alerts__conn" :class="wsConnected ? 'alerts__conn--on' : 'alerts__conn--off'">
      <view class="alerts__conn-dot" />
      <text>{{ wsConnected ? '实时推送已连接' : '实时已断开 · 30 秒轮询兜底' }}</text>
    </view>

    <!-- 告警流 -->
    <view v-if="events.length" class="alerts__list">
      <view v-for="(evt, i) in events" :key="evt.event_id" class="card alerts__item">
        <view class="alerts__head">
          <text class="alerts__class">{{ classLabel(evt.main_class) }}</text>
          <text class="alerts__time">{{ fmtRelative(evt.event_time) }}</text>
        </view>
        <view class="alerts__meta">
          <text>{{ evt.device_id || '未知设备' }}</text>
          <text>{{ evt.det_count || 1 }} 个目标</text>
          <text class="alerts__conf">
            {{ evt.max_confidence != null ? `${Math.round(evt.max_confidence * 100)}%` : '—' }}
          </text>
        </view>
        <view v-if="i === 0 && evt._isNew" class="alerts__new-tag">NEW</view>
      </view>
    </view>

    <view v-else class="empty">
      {{ loading ? '加载中…' : '暂无告警事件' }}
    </view>
  </view>
</template>

<script setup>
/**
 * 告警页：WebSocket 实时推送（docs/api.md 第十节）+ 30s 轮询兜底。
 * 与 Web 大屏同一信道：ws /api/v1/ws/alerts?token=<access_token>。
 * 收到新事件震动一下 —— 现场场景里手机多在口袋里，视觉提醒不可靠。
 */
import { ref, onUnmounted } from 'vue'
import { onShow, onHide, onPullDownRefresh } from '@dcloudio/uni-app'
import { statsApi } from '@/api'
import { wsUrl, getToken } from '@/api/http'
import { isLoggedIn } from '@/stores/auth'
import { classLabel } from '@/utils/constants'

const events = ref([])
const loading = ref(false)
const wsConnected = ref(false)

let socketTask = null
let pollTimer = null
let visible = false

function fmtRelative(time) {
  if (!time) return '—'
  const diff = Date.now() - new Date(time).getTime()
  if (Number.isNaN(diff)) return '—'
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  return `${Math.floor(h / 24)} 天前`
}

function upsertEvent(evt) {
  if (!evt?.event_id) return
  const idx = events.value.findIndex((e) => e.event_id === evt.event_id)
  const item = { ...evt, _isNew: idx < 0 }
  if (idx >= 0) {
    events.value.splice(idx, 1, item)
  } else {
    events.value.unshift(item)
    if (events.value.length > 100) events.value.pop()
    // 新告警：短震动（App/微信真机支持，工具内静默失败）
    uni.vibrateShort({ type: 'light', fail: () => {} })
  }
}

/** WS 推送的消息结构见 api.md：{type: 'event'|'task', data: {...}} */
function handleWsMessage(raw) {
  try {
    const msg = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (msg?.type === 'event' && msg.data) upsertEvent(msg.data)
  } catch {
    /* 非 JSON 帧忽略 */
  }
}

function connectWs() {
  if (!getToken()) return
  closeWs()
  socketTask = uni.connectSocket({
    url: wsUrl(),
    complete: () => {},
  })
  socketTask.onOpen(() => {
    wsConnected.value = true
  })
  socketTask.onMessage((res) => handleWsMessage(res.data))
  socketTask.onClose(() => {
    wsConnected.value = false
    // 页面还活着就 5 秒后重连（指数退避可后续再加）
    if (visible) setTimeout(() => visible && connectWs(), 5000)
  })
  socketTask.onError(() => {
    wsConnected.value = false
  })
}

function closeWs() {
  if (socketTask) {
    try {
      socketTask.close()
    } catch {
      /* 已关闭 */
    }
    socketTask = null
  }
  wsConnected.value = false
}

async function load() {
  if (!isLoggedIn.value) {
    uni.reLaunch({ url: '/pages/login/login' })
    return
  }
  loading.value = true
  try {
    // notifications 与 WS 推送同构（event/task 两条流），作轮询兜底
    const items = await statsApi.notifications({ hours: 24, limit: 50 })
    events.value = (items || [])
      .filter((n) => n.type === 'event')
      .map((n) => ({ ...n, _isNew: false }))
  } catch {
    /* 轮询失败不打断页面：WS 推送仍在工作 */
  } finally {
    loading.value = false
  }
}

function startAll() {
  visible = true
  load()
  connectWs()
  pollTimer = setInterval(load, 30000)
}

function stopAll() {
  visible = false
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
  closeWs()
}

onShow(startAll)
onHide(stopAll)
onUnmounted(stopAll)
onPullDownRefresh(async () => {
  await load()
  uni.stopPullDownRefresh()
})
</script>

<style scoped>
.alerts {
  padding: 20rpx 0 calc(24rpx + env(safe-area-inset-bottom));
}

.alerts__conn {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin: 0 24rpx 20rpx;
  padding: 14rpx 24rpx;
  border-radius: 999rpx;
  font-size: 24rpx;
  background: var(--bg-panel);
}

.alerts__conn--on {
  color: var(--c-success);
}

.alerts__conn--off {
  color: var(--c-danger);
}

.alerts__conn-dot {
  width: 14rpx;
  height: 14rpx;
  border-radius: 50%;
  background: currentColor;
}

.alerts__item {
  position: relative;
  margin-bottom: 20rpx;
}

.alerts__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10rpx;
}

.alerts__class {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--text-main);
}

.alerts__time {
  font-size: 22rpx;
  color: var(--text-dim);
}

.alerts__meta {
  display: flex;
  gap: 28rpx;
  font-size: 24rpx;
  color: var(--text-sub);
  font-family: Menlo, Consolas, monospace;
}

.alerts__conf {
  color: var(--c-primary);
}

.alerts__new-tag {
  position: absolute;
  top: -10rpx;
  right: 20rpx;
  padding: 2rpx 14rpx;
  border-radius: 999rpx;
  background: var(--c-warn);
  color: #ffffff;
  font-size: 20rpx;
  font-weight: 700;
}
</style>
