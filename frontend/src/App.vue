<template>
  <div class="layout">
    <!-- 顶栏 -->
    <header class="layout__header">
      <div class="brand">
        <span class="brand__mark">◈</span>
        <span class="brand__name">探海灵眸</span>
        <span class="brand__sub">SeaSight · 海漂垃圾智能治理平台</span>
      </div>

      <nav class="nav">
        <RouterLink
          v-for="r in navRoutes"
          :key="r.path"
          :to="r.path"
          class="nav__item"
          active-class="nav__item--active"
        >
          <span class="nav__icon">{{ r.meta.icon }}</span>
          <span>{{ r.meta.title }}</span>
        </RouterLink>
      </nav>

      <div class="header-right">
        <span class="conn" :class="store.wsConnected ? 'conn--on' : 'conn--off'">
          <i class="conn__dot"></i>
          {{ store.wsConnected ? '实时已连接' : '实时已断开' }}
        </span>
        <span class="clock">{{ clock }}</span>
      </div>
    </header>

    <!-- 内容 -->
    <main class="layout__main">
      <RouterView />
    </main>

    <!-- 全局错误条 -->
    <div v-if="store.error" class="error-bar">
      <span>{{ store.error }}</span>
      <button @click="store.refreshAll()">重试</button>
      <button class="error-bar__close" @click="store.error = ''">×</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterView, RouterLink } from 'vue-router'
import { routes } from '@/router'
import { useRealtimeStore } from '@/stores/realtime'

const store = useRealtimeStore()
const navRoutes = routes.filter((r) => r.meta?.title)

// ---------- 时钟 ----------
const clock = ref('')
let clockTimer = null

function tickClock() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes(),
  )}:${p(d.getSeconds())}`
}

// 每 30 秒静默刷新一次兜底数据。
// 为什么需要：WebSocket 只推增量，若某条消息丢了大屏就会一直少数据。
let pollTimer = null

onMounted(async () => {
  tickClock()
  clockTimer = setInterval(tickClock, 1000)

  store.startRealtime()
  await store.refreshAll()

  pollTimer = setInterval(() => store.refreshAll(), 30000)
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(pollTimer)
  store.stopRealtime()
})
</script>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-page);
}

/* ---------- 顶栏 ---------- */
.layout__header {
  height: 52px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 26px;
  padding: 0 18px;
  background: linear-gradient(180deg, #0d1620, #0a121b);
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-shrink: 0;
}

.brand__mark {
  color: var(--c-primary);
  font-size: 17px;
}

.brand__name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--text-main);
}

.brand__sub {
  font-size: 11px;
  color: var(--text-dim);
  letter-spacing: 0.3px;
}

.nav {
  display: flex;
  gap: 3px;
  flex: 1;
}

.nav__item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 13px;
  font-size: 13px;
  color: var(--text-sub);
  text-decoration: none;
  border-radius: var(--radius);
  border: 1px solid transparent;
  transition: all 0.16s;
  white-space: nowrap;
}

.nav__item:hover {
  color: var(--text-main);
  background: var(--bg-hover);
}

.nav__item--active {
  color: var(--c-primary);
  background: rgba(18, 216, 196, 0.09);
  border-color: rgba(18, 216, 196, 0.28);
}

.nav__icon {
  font-size: 12px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}

.conn {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
}

.conn--on { color: var(--c-success); }
.conn--off { color: var(--c-danger); }

.conn__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.conn--on .conn__dot {
  animation: blink 2s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.clock {
  font-size: 12px;
  color: var(--text-sub);
  font-family: 'SF Mono', Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

/* ---------- 主体 ---------- */
.layout__main {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

/* ---------- 错误条 ---------- */
.error-bar {
  position: fixed;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: rgba(242, 86, 76, 0.14);
  border: 1px solid rgba(242, 86, 76, 0.4);
  border-radius: var(--radius);
  color: #ffb4ae;
  font-size: 13px;
  z-index: 100;
}

.error-bar button {
  padding: 2px 9px;
  font-size: 12px;
  color: var(--text-main);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 3px;
  cursor: pointer;
}

.error-bar button:hover {
  background: rgba(255, 255, 255, 0.16);
}

.error-bar__close {
  padding: 2px 7px !important;
}
</style>
