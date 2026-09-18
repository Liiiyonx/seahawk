<template>
  <div class="stat-grid">
    <div v-for="card in cards" :key="card.key" class="stat-card">
      <div class="stat-card__label">{{ card.label }}</div>
      <div class="stat-card__value" :style="{ color: card.color }">
        {{ card.value }}
        <span v-if="card.unit" class="stat-card__unit">{{ card.unit }}</span>
      </div>
      <div v-if="card.sub" class="stat-card__sub">{{ card.sub }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtNumber } from '@/utils/format'

const props = defineProps({
  stats: { type: Object, default: () => ({}) },
})

const cards = computed(() => {
  const s = props.stats || {}
  return [
    {
      key: 'events',
      label: '24 小时事件',
      value: fmtNumber(s.event_count_24h || 0),
      unit: '条',
      color: 'var(--c-warn)',
    },
    {
      key: 'pending',
      label: '待派单工单',
      value: fmtNumber(s.pending_tasks || 0),
      unit: '单',
      color: 'var(--text-main)',
      sub: s.pending_tasks > 0 ? '需要关注' : '全部已派发',
    },
    {
      key: 'collecting',
      label: '作业中',
      value: fmtNumber(s.collecting_tasks || 0),
      unit: '单',
      color: 'var(--c-primary)',
    },
    {
      key: 'done',
      label: '今日完成',
      value: fmtNumber(s.done_tasks_24h || 0),
      unit: '单',
      color: 'var(--c-success)',
    },
    {
      key: 'robots',
      label: '机器人在线',
      value: `${s.robots_online || 0}/${s.robots_total || 0}`,
      unit: '台',
      color: (s.robots_online || 0) > 0 ? 'var(--c-info)' : 'var(--c-danger)',
    },
    {
      key: 'weight',
      label: '累计清理',
      value: fmtNumber(s.collected_kg_total || 0, 1),
      unit: 'kg',
      color: 'var(--c-success)',
    },
  ]
})
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
}

.stat-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 13px;
  position: relative;
  overflow: hidden;
}

.stat-card::after {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: linear-gradient(180deg, var(--c-primary), transparent);
  opacity: 0.5;
}

.stat-card__label {
  font-size: 12px;
  color: var(--text-sub);
  margin-bottom: 3px;
}

.stat-card__value {
  font-size: 23px;
  font-weight: 600;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', Consolas, monospace;
}

.stat-card__unit {
  font-size: 12px;
  color: var(--text-sub);
  font-weight: 400;
  margin-left: 3px;
}

.stat-card__sub {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

@media (max-width: 1400px) {
  .stat-grid { grid-template-columns: repeat(3, 1fr); }
}
</style>
