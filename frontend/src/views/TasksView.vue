<template>
  <div class="page">
    <!-- 状态统计条 -->
    <div class="status-bar">
      <div
        v-for="s in statusSummary"
        :key="s.key"
        class="status-chip"
        :class="{ 'status-chip--on': filters.status === s.key }"
        @click="toggleStatus(s.key)"
      >
        <span class="status-chip__label">{{ s.label }}</span>
        <span class="status-chip__num" :style="{ color: s.color }">{{ s.count }}</span>
      </div>
      <div class="status-bar__spacer"></div>
      <button v-if="canWriteOps" class="btn" @click="openManual">人工建单</button>
      <button v-if="canWriteOps" class="btn" @click="dispatchPending" :disabled="dispatching">
        {{ dispatching ? '派单中…' : '触发补派' }}
      </button>
      <button class="btn" @click="exportCsv">导出 CSV</button>
      <button class="btn" @click="load">刷新</button>
    </div>

    <!-- 看板列 -->
    <div class="kanban">
      <section v-for="col in columns" :key="col.status" class="kanban__col">
        <div class="kanban__head">
          <span>
            <i class="kanban__dot" :style="{ background: col.color }"></i>
            {{ col.label }}
          </span>
          <span class="kanban__count">{{ grouped[col.status]?.length || 0 }}</span>
        </div>

        <div class="kanban__body">
          <article
            v-for="t in grouped[col.status] || []"
            :key="t.task_id"
            class="tcard"
            @click="openDetail(t)"
          >
            <div class="tcard__head">
              <span class="tcard__id">{{ t.task_id }}</span>
              <span class="tcard__pri" :class="`tcard__pri--${t.priority}`">
                P{{ t.priority }}
              </span>
            </div>

            <div class="tcard__row">
              <span class="text-sub">机器人</span>
              <span>{{ t.robot_id || '未分配' }}</span>
            </div>
            <div class="tcard__row">
              <span class="text-sub">目标点</span>
              <span class="num">{{ fmtCoord(t.lng, t.lat) }}</span>
            </div>
            <div class="tcard__row">
              <span class="text-sub">创建</span>
              <span>{{ fmtRelative(t.created_at) }}</span>
            </div>
            <div v-if="t.collected_weight" class="tcard__row">
              <span class="text-sub">打捞量</span>
              <span class="text-primary">{{ Number(t.collected_weight).toFixed(2) }} kg</span>
            </div>

            <!-- 可执行动作 -->
            <div v-if="canWriteOps && nextStates(t).length" class="tcard__actions" @click.stop>
              <button
                v-for="ns in nextStates(t)"
                :key="ns"
                class="tcard__btn"
                :class="ns === 'cancelled' ? 'tcard__btn--danger' : ''"
                @click="changeStatus(t, ns)"
              >
                {{ TASK_STATUS[ns] }}
              </button>
            </div>
          </article>

          <div v-if="!grouped[col.status]?.length" class="kanban__empty">暂无工单</div>
        </div>
      </section>
    </div>

    <!-- 详情抽屉 -->
    <div v-if="detail" class="drawer" @click.self="detail = null">
      <div class="drawer__panel panel">
        <div class="panel-title">
          <span>工单详情 · {{ detail.task_id }}</span>
          <button class="drawer__close" @click="detail = null">×</button>
        </div>
        <div class="panel-body drawer__body">
          <div class="kv" v-for="kv in detailRows" :key="kv.label">
            <span class="kv__k">{{ kv.label }}</span>
            <span class="kv__v">{{ kv.value }}</span>
          </div>

          <!-- 时间戳链：工单生命周期的完整证据 -->
          <div class="timeline">
            <div class="timeline__title">生命周期</div>
            <div v-for="step in timeline" :key="step.label" class="timeline__item">
              <span class="timeline__dot" :class="{ 'timeline__dot--done': step.time }"></span>
              <span class="timeline__label">{{ step.label }}</span>
              <span class="timeline__time">{{ step.time ? fmtTime(step.time) : '—' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 完成工单录入框：打捞量由操作员如实填写，不复用随机数 -->
    <div v-if="completing" class="drawer" @click.self="completing = null">
      <div class="drawer__panel panel">
        <div class="panel-title">
          <span>完成工单 · {{ completing.task_id }}</span>
          <button class="drawer__close" @click="completing = null">×</button>
        </div>
        <div class="panel-body drawer__body">
          <div class="form-row">
            <label class="form-label">打捞重量（kg）</label>
            <input
              v-model="completion.weight"
              class="form-input"
              type="number"
              min="0"
              step="0.01"
              placeholder="如实填写本次清理量，可留空"
            />
            <span class="form-hint">来自人工称重或机器人仓容，留空则暂不记录</span>
          </div>
          <div class="form-row">
            <label class="form-label">复核结果</label>
            <select v-model="completion.review" class="form-input">
              <option value="confirmed">确认清理</option>
              <option value="not_found">到场未发现</option>
              <option value="recheck">需人工复查</option>
            </select>
          </div>
          <div class="drawer__actions">
            <button class="btn" @click="completing = null">取消</button>
            <button class="btn btn--primary" @click="confirmDone">确认完成</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 人工建单：漏检兜底，操作员手动指定位置/机器人创建任务 -->
    <div v-if="manual" class="drawer" @click.self="manual = false">
      <div class="drawer__panel panel">
        <div class="panel-title">
          <span>人工建单（漏检兜底）</span>
          <button class="drawer__close" @click="manual = false">×</button>
        </div>
        <div class="panel-body drawer__body">
          <div class="form-row">
            <label class="form-label">目标经度（lng）</label>
            <input
              v-model="manualForm.lng"
              class="form-input"
              type="number"
              step="0.0001"
              placeholder="如 119.6521"
            />
          </div>
          <div class="form-row">
            <label class="form-label">目标纬度（lat）</label>
            <input
              v-model="manualForm.lat"
              class="form-input"
              type="number"
              step="0.0001"
              placeholder="如 26.3864"
            />
          </div>
          <div class="form-row">
            <label class="form-label">执行机器人（空则进入待派单）</label>
            <select v-model="manualForm.robot_id" class="form-input">
              <option value="">不指定（待自动派单）</option>
              <option v-for="r in store.robots" :key="r.robot_id" :value="r.robot_id">
                {{ r.name || r.robot_id }}（{{ r.status === 'online' ? '在线' : '离线' }}）
              </option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">优先级</label>
            <select v-model.number="manualForm.priority" class="form-input">
              <option :value="1">P1 紧急</option>
              <option :value="3">P3 普通</option>
              <option :value="5">P5 一般</option>
            </select>
          </div>
          <div class="drawer__actions">
            <button class="btn" @click="manual = false">取消</button>
            <button class="btn btn--primary" @click="submitManual">创建任务</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 工单看板 —— 用看板而不是纯表格，是因为工单是有"流动"的：
 * 从待派单一路走到完成，看板能一眼看出一堆积压在哪一列。
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { tasksApi, downloadBlob } from '@/api'
import { useRealtimeStore } from '@/stores/realtime'
import {
  TASK_STATUS,
  TASK_TRANSITIONS,
  REVIEW_RESULT,
} from '@/utils/constants'
import { fmtCoord, fmtRelative, fmtTime } from '@/utils/format'
import { canWrite } from '@/utils/auth'

const store = useRealtimeStore()

// viewer / 匿名只读：隐藏写操作（后端 require_operator 才是最终裁决）
const canWriteOps = canWrite()

const tasks = ref([])
const detail = ref(null)
const dispatching = ref(false)
const filters = reactive({ status: '' })
// 完成工单的录入表单：打捞重量必须由操作员如实填写，不再伪造随机数
const completing = ref(null)
const completion = reactive({ weight: '', review: 'confirmed' })
// 人工建单：漏检兜底
const manual = ref(false)
const manualForm = reactive({ lng: '', lat: '', robot_id: '', priority: 5 })

const COLUMNS = [
  { status: 'pending', label: '待派单', color: '#8b96a8' },
  { status: 'assigned', label: '已派单', color: '#8a6cff' },
  { status: 'navigating', label: '前往中', color: '#4a9eff' },
  { status: 'collecting', label: '作业中', color: '#12d8c4' },
  { status: 'done', label: '已完成', color: '#3ddc84' },
]

const columns = computed(() =>
  filters.status ? COLUMNS.filter((c) => c.status === filters.status) : COLUMNS,
)

const grouped = computed(() => {
  const g = {}
  for (const c of COLUMNS) g[c.status] = []
  for (const t of tasks.value) {
    if (g[t.status]) g[t.status].push(t)
  }
  return g
})

const statusSummary = computed(() =>
  COLUMNS.map((c) => ({
    key: c.status,
    label: c.label,
    color: c.color,
    count: grouped.value[c.status]?.length || 0,
  })),
)

/** 当前状态下允许的下一步（与后端状态机一致，前端只做展示过滤） */
function nextStates(task) {
  const allowed = TASK_TRANSITIONS[task.status] || []
  // 演示用：不暴露全部跳转，只给最常用的两条
  const priority = ['done', 'collecting', 'navigating', 'cancelled']
  return allowed.filter((s) => priority.includes(s)).slice(0, 2)
}

const detailRows = computed(() => {
  if (!detail.value) return []
  const d = detail.value
  return [
    { label: '事件编号', value: d.event_id || '—' },
    { label: '执行机器人', value: d.robot_id || '未分配' },
    { label: '目标坐标', value: fmtCoord(d.lng, d.lat) },
    { label: '状态', value: TASK_STATUS[d.status] || d.status },
    { label: '优先级', value: `P${d.priority}` },
    { label: '打捞重量', value: d.collected_weight ? `${Number(d.collected_weight).toFixed(2)} kg` : '—' },
    { label: '复核结果', value: REVIEW_RESULT[d.review_result] || d.review_result || '—' },
    { label: '备注', value: d.remark || '—' },
  ]
})

const timeline = computed(() => {
  if (!detail.value) return []
  const d = detail.value
  return [
    { label: '创建', time: d.created_at },
    { label: '派单', time: d.assigned_at },
    { label: '确认', time: d.ack_at },
    { label: '开工', time: d.started_at },
    { label: '完成', time: d.finished_at },
  ]
})

async function load() {
  try {
    const res = await tasksApi.list({ page: 1, page_size: 200 })
    tasks.value = res?.items || []
  } catch (err) {
    store.error = err.message
  }
}

async function exportCsv() {
  try {
    const blob = await tasksApi.export({ status: filters.status || undefined })
    downloadBlob(blob, `工单台账_${new Date().toISOString().slice(0, 10)}.csv`)
  } catch (err) {
    store.error = err.message
  }
}

function toggleStatus(key) {
  filters.status = filters.status === key ? '' : key
}

function openDetail(task) {
  detail.value = task
}

async function changeStatus(task, target) {
  // 完成工单需要操作员真实录入打捞量与复核结果，不再伪造随机数
  if (target === 'done') {
    completing.value = task
    completion.weight = ''
    completion.review = 'confirmed'
    return
  }
  await applyStatus(task, target)
}

async function applyStatus(task, target, extra = {}) {
  try {
    await tasksApi.updateStatus(task.task_id, { status: target, ...extra })
    await load()
    if (detail.value?.task_id === task.task_id) {
      detail.value = tasks.value.find((t) => t.task_id === task.task_id) || null
    }
  } catch (err) {
    store.error = err.message
  }
}

async function confirmDone() {
  const weight = Number(completion.weight)
  const payload = { review_result: completion.review }
  // 只有如实填写了合法重量才上报；留空则不打捞量（保持后端 NULL）
  if (completion.weight !== '' && !Number.isNaN(weight) && weight >= 0) {
    payload.collected_weight = weight
  }
  const task = completing.value
  completing.value = null
  if (task) await applyStatus(task, 'done', payload)
}

function openManual() {
  manual.value = true
  manualForm.lng = ''
  manualForm.lat = ''
  manualForm.robot_id = ''
  manualForm.priority = 5
}

async function submitManual() {
  const lng = Number(manualForm.lng)
  const lat = Number(manualForm.lat)
  if (manualForm.lng === '' || manualForm.lat === '' || Number.isNaN(lng) || Number.isNaN(lat)) {
    store.error = '请输入有效的目标经纬度'
    return
  }
  try {
    await tasksApi.create({
      target: { lng, lat },
      robot_id: manualForm.robot_id || undefined,
      priority: manualForm.priority,
    })
    manual.value = false
    await load()
  } catch (err) {
    store.error = err.message
  }
}

async function dispatchPending() {
  dispatching.value = true
  try {
    const res = await tasksApi.dispatchPending()
    await load()
    const n = res?.dispatched ?? res?.length ?? 0
    if (n === 0) store.error = '当前无待派单事件（可能无可用机器人）'
  } catch (err) {
    store.error = err.message
  } finally {
    dispatching.value = false
  }
}

onMounted(load)

// 有新工单推送时自动刷新列表
store.$subscribe(() => {
  if (store.taskFeed.length) load()
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

.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  flex-shrink: 0;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 11px;
  border-radius: 14px;
  border: 1px solid var(--border);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.status-chip:hover {
  border-color: var(--border-bright);
}

.status-chip--on {
  border-color: var(--c-primary-dim);
  background: rgba(18, 216, 196, 0.08);
}

.status-chip__label {
  color: var(--text-sub);
}

.status-chip__num {
  font-weight: 600;
  font-family: 'SF Mono', Consolas, monospace;
}

.status-bar__spacer {
  flex: 1;
}

.btn {
  padding: 3px 12px;
  font-size: 13px;
  color: var(--text-main);
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  border-color: var(--c-primary-dim);
  color: var(--c-primary);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---------- 看板 ---------- */
.kanban {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.kanban__col {
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-height: 0;
}

.kanban__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.kanban__dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: 1px;
}

.kanban__count {
  font-size: 12px;
  color: var(--text-sub);
  font-family: 'SF Mono', Consolas, monospace;
}

.kanban__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.kanban__empty {
  text-align: center;
  color: var(--text-dim);
  font-size: 12px;
  padding: 20px 0;
}

/* ---------- 工单卡 ---------- */
.tcard {
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 10px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.tcard:hover {
  border-color: var(--border-bright);
}

.tcard__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
}

.tcard__id {
  font-size: 11px;
  color: var(--c-primary);
  font-family: 'SF Mono', Consolas, monospace;
}

.tcard__pri {
  font-size: 10px;
  padding: 0 5px;
  border-radius: 8px;
  background: rgba(139, 150, 168, 0.16);
  color: var(--text-sub);
}

.tcard__pri--1 { background: rgba(242, 86, 76, 0.18); color: var(--c-danger); }
.tcard__pri--2 { background: rgba(245, 166, 35, 0.18); color: var(--c-warn); }
.tcard__pri--3 { background: rgba(74, 158, 255, 0.18); color: var(--c-info); }

.tcard__row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11.5px;
  line-height: 1.75;
}

.tcard__actions {
  display: flex;
  gap: 5px;
  margin-top: 7px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

.tcard__btn {
  flex: 1;
  padding: 2px 6px;
  font-size: 11px;
  color: var(--c-primary);
  background: rgba(18, 216, 196, 0.09);
  border: 1px solid rgba(18, 216, 196, 0.24);
  border-radius: 3px;
  cursor: pointer;
}

.tcard__btn:hover {
  background: rgba(18, 216, 196, 0.18);
}

.tcard__btn--danger {
  color: var(--c-danger);
  background: rgba(242, 86, 76, 0.09);
  border-color: rgba(242, 86, 76, 0.24);
}

.tcard__btn--danger:hover {
  background: rgba(242, 86, 76, 0.18);
}

/* ---------- 抽屉 ---------- */
.drawer {
  position: fixed;
  inset: 0;
  background: rgba(3, 6, 10, 0.6);
  display: flex;
  justify-content: flex-end;
  z-index: 50;
}

.drawer__panel {
  width: 420px;
  max-width: 92vw;
  height: 100%;
  border-radius: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer__close {
  background: none;
  border: none;
  color: var(--text-sub);
  font-size: 19px;
  cursor: pointer;
  line-height: 1;
}

.drawer__close:hover {
  color: var(--text-main);
}

.drawer__body {
  flex: 1;
  overflow-y: auto;
}

.kv {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 0;
  border-bottom: 1px solid rgba(28, 42, 58, 0.5);
  font-size: 13px;
}

.kv__k {
  color: var(--text-sub);
  flex-shrink: 0;
}

.kv__v {
  color: var(--text-main);
  text-align: right;
  word-break: break-all;
}

.timeline {
  margin-top: 16px;
}

.timeline__title {
  font-size: 13px;
  color: var(--text-sub);
  margin-bottom: 9px;
}

.timeline__item {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  align-items: center;
  gap: 7px;
  padding: 5px 0;
  font-size: 12.5px;
}

.timeline__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--border-bright);
  margin-left: 3px;
}

.timeline__dot--done {
  background: var(--c-primary);
  box-shadow: 0 0 0 3px rgba(18, 216, 196, 0.16);
}

.timeline__label {
  color: var(--text-main);
}

.timeline__time {
  color: var(--text-sub);
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 11.5px;
}

/* ---------- 完成工单录入框 ---------- */
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.form-label {
  font-size: 12.5px;
  color: var(--text-sub);
}

.form-input {
  width: 100%;
  padding: 7px 10px;
  font-size: 13px;
  color: var(--text-main);
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  outline: none;
}

.form-input:focus {
  border-color: var(--c-primary-dim);
}

.form-hint {
  font-size: 11px;
  color: var(--text-dim);
}

.drawer__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.btn--primary {
  color: #06251f;
  background: var(--c-primary);
  border-color: var(--c-primary);
}

.btn--primary:hover:not(:disabled) {
  color: #06251f;
  border-color: var(--c-primary);
  filter: brightness(1.05);
}

@media (max-width: 1400px) {
  .kanban { grid-template-columns: repeat(3, 1fr); }
}
</style>
