<template>
  <div class="agents">
    <div class="agents__head">
      <div>
        <h2 class="agents__title">智能体协同中枢</h2>
        <p class="agents__sub">
          「感知—决策—执行」闭环由 6 个智能体协同完成，每个智能体对应平台的一个真实能力模块。
        </p>
      </div>
      <span class="agents__count">{{ agents.length }} 个智能体在线</span>
    </div>

    <div class="agents__grid">
      <article
        v-for="(a, i) in agents"
        :key="a.id"
        class="agent-card"
        :style="{ animationDelay: `${i * 60}ms` }"
      >
        <div class="agent-card__top">
          <div class="agent-card__badge">{{ a.glyph }}</div>
          <div class="agent-card__id">
            <div class="agent-card__name">{{ a.name }}</div>
            <div class="agent-card__codename">{{ a.codename }}</div>
          </div>
          <span class="agent-card__status">
            <i class="agent-card__dot"></i>
            {{ a.status === 'running' ? '运行中' : '待命' }}
          </span>
        </div>

        <div class="agent-card__role">{{ a.role }}</div>

        <p class="agent-card__desc">{{ a.description }}</p>

        <div class="agent-card__caps">
          <span v-for="c in a.capabilities" :key="c" class="agent-card__cap">{{ c }}</span>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { aiApi } from '@/api'
import { useRealtimeStore } from '@/stores/realtime'

const store = useRealtimeStore()
const agents = ref([])

onMounted(async () => {
  try {
    agents.value = (await aiApi.agents()) || []
  } catch {
    // 后端未起时展示空状态，不阻断页面
    store.error = '智能体列表加载失败（后端未启动）'
  }
})
</script>

<style scoped>
.agents {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}

.agents__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.agents__title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-main);
  letter-spacing: 1px;
}

.agents__sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-sub);
}

.agents__count {
  font-size: 12px;
  color: var(--c-primary);
  white-space: nowrap;
}

.agents__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.agent-card {
  background: var(--bg-panel);
  backdrop-filter: blur(14px) saturate(1.25);
  -webkit-backdrop-filter: blur(14px) saturate(1.25);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px 18px 16px;
  animation: rise-in 0.5s var(--ease) both;
  transition: transform var(--dur) var(--ease), border-color var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}

.agent-card:hover {
  transform: translateY(-3px);
  border-color: var(--border-bright);
  box-shadow: var(--shadow-glow);
}

.agent-card__top {
  display: flex;
  align-items: center;
  gap: 12px;
}

.agent-card__badge {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
  font-weight: 600;
  color: #06251f;
  background: var(--grad-primary);
  border-radius: 12px;
}

.agent-card__id {
  flex: 1;
  min-width: 0;
}

.agent-card__name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-main);
}

.agent-card__codename {
  font-size: 12px;
  color: var(--c-primary);
  letter-spacing: 1px;
}

.agent-card__status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--c-success);
  white-space: nowrap;
}

.agent-card__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-success);
  animation: pulse-ring 1.8s ease-out infinite;
}

.agent-card__role {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-sub);
}

.agent-card__desc {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-sub);
}

.agent-card__caps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.agent-card__cap {
  padding: 2px 9px;
  font-size: 11px;
  color: var(--text-sub);
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 10px;
}

@media (max-width: 1400px) {
  .agents__grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
