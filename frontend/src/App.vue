<template>
  <RouterView v-if="isLoginPage" />
  <div v-else class="layout">
    <!-- 顶栏 -->
    <header class="layout__header">
      <div class="brand">
        <LogoMark :size="30" />
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
        <button
          class="theme-toggle"
          :title="theme === 'light' ? '切换到深色模式' : '切换到浅色模式'"
          @click="toggleThemeBtn"
        >
          {{ theme === 'light' ? '☀' : '☾' }}
        </button>

        <div class="notif">
          <button class="notif__bell" @click="toggleNotif">
            通知
            <span v-if="unreadCount" class="notif__badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
          </button>
          <div v-if="showNotif" class="notif__panel" @click.stop>
            <div class="notif__head">
              <span>通知中心</span>
              <button class="notif__read" @click="markAllRead">全部已读</button>
            </div>
            <div class="notif__list">
              <div
                v-for="n in notifications"
                :key="(n.event_id || n.task_id) + n.time"
                class="notif__item"
              >
                <span class="notif__dot" :class="n.type === 'event' ? 'notif__dot--event' : 'notif__dot--task'"></span>
                <div class="notif__body">
                  <div class="notif__title">{{ n.title }}</div>
                  <div class="notif__time">{{ fmtTime(n.time) }}</div>
                </div>
              </div>
              <div v-if="!notifications.length" class="notif__empty">暂无通知</div>
            </div>
          </div>
        </div>

        <span v-if="currentUser" class="user">
          <span class="user__name">{{ currentUser.full_name || currentUser.username }}</span>
          <span class="user__role">{{ roleLabel(currentUser.role) }}</span>
          <button class="user__logout" @click="logout">退出</button>
        </span>
        <span class="conn" :class="store.wsConnected ? 'conn--on' : 'conn--off'">
          <i class="conn__dot"></i>
          {{ store.wsConnected ? '实时已连接' : '实时已断开' }}
        </span>
        <span class="clock">{{ clock }}</span>
      </div>
    </header>

    <!-- 内容 -->
    <main class="layout__main">
      <RouterView v-slot="{ Component }">
        <transition name="fade-slide" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { RouterView, RouterLink, useRoute, useRouter } from 'vue-router'
import { routes } from '@/router'
import { useRealtimeStore } from '@/stores/realtime'
import { getUser, clearAuth, roleLabel } from '@/utils/auth'
import { statsApi } from '@/api'
import { fmtTime } from '@/utils/format'
import { getTheme, toggleTheme } from '@/utils/theme'
import LogoMark from '@/components/LogoMark.vue'

const store = useRealtimeStore()
const route = useRoute()
const router = useRouter()
const navRoutes = routes.filter((r) => r.meta?.title && !r.meta?.noLayout)

// 登录页不渲染主布局（无顶栏/导航）
const isLoginPage = computed(() => route.name === 'login')

const currentUser = ref(getUser())

function logout() {
  clearAuth()
  currentUser.value = null
  router.replace('/login')
}

// ---------- 主题切换 ----------
const theme = ref(getTheme())

function toggleThemeBtn() {
  theme.value = toggleTheme()
}

// ---------- 站内通知铃铛 ----------
const NOTIF_KEY = 'seasight_last_read'
const notifications = ref([])
const showNotif = ref(false)
const unreadCount = ref(0)

function lastReadAt() {
  return Number(localStorage.getItem(NOTIF_KEY) || 0)
}

async function loadNotifications() {
  try {
    const items = await statsApi.notifications({ hours: 24, limit: 50 })
    notifications.value = items || []
    const last = lastReadAt()
    unreadCount.value = notifications.value.filter(
      (n) => new Date(n.time || 0).getTime() > last,
    ).length
  } catch {
    /* 通知加载失败不阻断主流程 */
  }
}

function toggleNotif() {
  showNotif.value = !showNotif.value
  if (showNotif.value) loadNotifications()
}

function markAllRead() {
  const latest = notifications.value[0]?.time
  if (latest) {
    localStorage.setItem(NOTIF_KEY, String(new Date(latest).getTime()))
    unreadCount.value = 0
  }
}

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
let notifTimer = null

onMounted(async () => {
  tickClock()
  clockTimer = setInterval(tickClock, 1000)

  store.startRealtime()
  await store.refreshAll()
  loadNotifications()

  pollTimer = setInterval(() => store.refreshAll(), 30000)
  notifTimer = setInterval(loadNotifications, 30000)
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(pollTimer)
  clearInterval(notifTimer)
  store.stopRealtime()
})
</script>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: transparent;
}

/* ---------- 顶栏（玻璃拟态） ---------- */
.layout__header {
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 26px;
  padding: 0 20px;
  background: rgba(8, 16, 26, 0.55);
  backdrop-filter: blur(16px) saturate(1.2);
  -webkit-backdrop-filter: blur(16px) saturate(1.2);
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.brand__name {
  font-family: '华文行楷', 'STXingkai', '楷体', 'KaiTi', 'STKaiti', serif;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: 4px;
  background: var(--grad-primary);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 0 10px rgba(24, 224, 200, 0.28));
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
  position: relative;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 13px;
  font-size: 13px;
  color: var(--text-sub);
  text-decoration: none;
  border-radius: var(--radius);
  transition: color 0.2s var(--ease), background 0.2s var(--ease);
  white-space: nowrap;
}

/* 导航下划线动效 */
.nav__item::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 1px;
  width: 0;
  height: 2px;
  border-radius: 1px;
  background: var(--grad-primary);
  transform: translateX(-50%);
  transition: width 0.25s var(--ease);
}

.nav__item:hover {
  color: var(--text-main);
  background: var(--bg-hover);
}

.nav__item:hover::after,
.nav__item--active::after {
  width: 56%;
}

.nav__item--active {
  color: var(--c-primary);
  background: rgba(24, 224, 200, 0.08);
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

.user {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.user__name {
  color: var(--text-main);
}

.user__role {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  color: var(--c-primary);
  background: rgba(18, 216, 196, 0.1);
  border: 1px solid rgba(18, 216, 196, 0.22);
}

.user__logout {
  padding: 2px 9px;
  font-size: 11px;
  color: var(--text-sub);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
}

.user__logout:hover {
  color: var(--text-main);
  border-color: var(--border-bright);
}

/* ---------- 主题切换 ---------- */
.theme-toggle {
  width: 30px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  color: var(--text-sub);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: color 0.2s var(--ease), border-color 0.2s var(--ease);
}

.theme-toggle:hover {
  color: var(--c-primary);
  border-color: var(--c-primary-dim);
}

/* ---------- 通知铃铛 ---------- */
.notif {
  position: relative;
}

.notif__bell {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--text-sub);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
}

.notif__bell:hover {
  color: var(--text-main);
  border-color: var(--border-bright);
}

.notif__badge {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  font-size: 10px;
  line-height: 16px;
  text-align: center;
  color: #fff;
  background: var(--c-danger);
}

.notif__panel {
  position: absolute;
  top: 32px;
  right: 0;
  width: 320px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  z-index: 90;
  overflow: hidden;
}

.notif__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  font-size: 13px;
  color: var(--text-main);
  border-bottom: 1px solid var(--border);
}

.notif__read {
  font-size: 12px;
  color: var(--c-primary);
  background: none;
  border: none;
  cursor: pointer;
}

.notif__list {
  overflow-y: auto;
  padding: 6px 0;
}

.notif__item {
  display: flex;
  gap: 9px;
  padding: 8px 14px;
}

.notif__item:hover {
  background: var(--bg-hover);
}

.notif__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}

.notif__dot--event {
  background: var(--c-warn);
}

.notif__dot--task {
  background: var(--c-primary);
}

.notif__body {
  min-width: 0;
}

.notif__title {
  font-size: 12.5px;
  color: var(--text-main);
  line-height: 1.45;
}

.notif__time {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

.notif__empty {
  padding: 24px 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-dim);
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
