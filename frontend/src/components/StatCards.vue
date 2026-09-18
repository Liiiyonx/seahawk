<template>
  <div class="stat-grid">
    <div
      v-for="(card, i) in cards"
      :key="card.key"
      class="stat-card"
      :class="{ 'stat-card--link': card.hint }"
      :style="{ '--card-color': card.color, animationDelay: `${i * 50}ms` }"
    >
      <div class="stat-card__glow"></div>
      <div class="stat-card__label">{{ card.label }}</div>
      <div class="stat-card__value">
        <span class="stat-card__num grad-text">
          {{ card.text || fmtNumber(display[card.key] ?? card.numeric, card.digits) }}
        </span>
        <span v-if="card.unit" class="stat-card__unit">{{ card.unit }}</span>
      </div>
      <div v-if="card.sub" class="stat-card__sub">{{ card.sub }}</div>
    </div>
  </div>
</template>

<script setup>
/**
 * 指标卡 —— 大屏的第一眼。
 *
 * 数字用 requestAnimationFrame 从旧值滚动到新值（count-up），
 * 避免大屏刷新时数字「跳变」——流畅的数字过渡比静态刷新更有「活」的感觉。
 */
import { computed, reactive, watch, onUnmounted } from 'vue'
import { fmtNumber } from '@/utils/format'

const props = defineProps({
  stats: { type: Object, default: () => ({}) },
})

const cards = computed(() => {
  const s = props.stats || {}
  return [
    { key: 'events', label: '24 小时事件', numeric: s.event_count_24h || 0, digits: 0, unit: '条', color: '#f5a623', sub: '' },
    { key: 'pending', label: '待派单工单', numeric: s.pending_tasks || 0, digits: 0, unit: '单', color: '#eaf2fb', sub: (s.pending_tasks || 0) > 0 ? '需要关注' : '全部已派发' },
    { key: 'collecting', label: '作业中', numeric: s.collecting_tasks || 0, digits: 0, unit: '单', color: '#18e0c8', sub: '' },
    { key: 'done', label: '今日完成', numeric: s.done_tasks_24h || 0, digits: 0, unit: '单', color: '#3ddc84', sub: '' },
    { key: 'robots', label: '机器人在线', text: `${s.robots_online || 0}/${s.robots_total || 0}`, unit: '台', color: (s.robots_online || 0) > 0 ? '#4a9eff' : '#f2564c', sub: '' },
    { key: 'weight', label: '累计清理', numeric: s.collected_kg_total || 0, digits: 1, unit: 'kg', color: '#3ddc84', sub: '' },
  ]
})

// 每个数字卡片的当前动画值（count-up 过程中的中间值）
const display = reactive({})
const rafs = new Set()

function animate(key, target, duration = 750) {
  const start = display[key] ?? 0
  const t0 = performance.now()
  function step(now) {
    const p = Math.min((now - t0) / duration, 1)
    const eased = 1 - Math.pow(1 - p, 3) // ease-out cubic
    display[key] = start + (target - start) * eased
    if (p < 1) {
      const raf = requestAnimationFrame(step)
      rafs.add(raf)
    }
  }
  const raf = requestAnimationFrame(step)
  rafs.add(raf)
}

watch(
  cards,
  (list) => {
    for (const c of list) {
      if (c.numeric != null) animate(c.key, c.numeric)
    }
  },
  { immediate: true, deep: true },
)

onUnmounted(() => rafs.forEach((r) => cancelAnimationFrame(r)))
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

.stat-card {
  background: var(--bg-panel);
  backdrop-filter: blur(14px) saturate(1.25);
  -webkit-backdrop-filter: blur(14px) saturate(1.25);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 13px 16px;
  position: relative;
  overflow: hidden;
  animation: rise-in 0.5s var(--ease) both;
  transition: transform var(--dur) var(--ease), border-color var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: var(--border-bright);
  box-shadow: var(--shadow-glow);
}

/* 顶部渐变光带（用卡片主题色） */
.stat-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--card-color), transparent);
  opacity: 0.55;
}

/* 右上角柔和光晕 */
.stat-card__glow {
  position: absolute;
  top: -30px;
  right: -30px;
  width: 90px;
  height: 90px;
  border-radius: 50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--card-color) 22%, transparent), transparent 70%);
  pointer-events: none;
}

.stat-card__label {
  font-size: 12px;
  color: var(--text-sub);
  letter-spacing: 0.4px;
  margin-bottom: 5px;
}

.stat-card__value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.stat-card__num {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'JetBrains Mono', Consolas, monospace;
}

.stat-card__unit {
  font-size: 12px;
  color: var(--text-sub);
  font-weight: 400;
}

.stat-card__sub {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 4px;
}

@media (max-width: 1400px) {
  .stat-grid { grid-template-columns: repeat(3, 1fr); }
}
</style>
