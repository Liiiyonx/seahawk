<template>
  <div class="page">
    <!-- 筛选栏 -->
    <div class="toolbar panel">
      <div class="toolbar__group">
        <label>时间范围</label>
        <select v-model.number="filters.hours" @change="load">
          <option :value="6">近 6 小时</option>
          <option :value="24">近 24 小时</option>
          <option :value="72">近 3 天</option>
          <option :value="168">近 7 天</option>
        </select>
      </div>

      <div class="toolbar__group">
        <label>垃圾类别</label>
        <select v-model="filters.mainClass" @change="load">
          <option value="">全部类别</option>
          <option v-for="c in CLASS_ORDER" :key="c" :value="c">
            {{ classLabel(c) }}
          </option>
        </select>
      </div>

      <div class="toolbar__group">
        <label>处理状态</label>
        <select v-model="filters.status" @change="load">
          <option value="">全部状态</option>
          <option v-for="(label, key) in EVENT_STATUS" :key="key" :value="key">
            {{ label }}
          </option>
        </select>
      </div>

      <div class="toolbar__group">
        <label>设备</label>
        <select v-model="filters.deviceId" @change="load">
          <option value="">全部设备</option>
          <option v-for="d in store.devices" :key="d.device_id" :value="d.device_id">
            {{ d.name }}
          </option>
        </select>
      </div>

      <div class="toolbar__spacer"></div>

      <span class="toolbar__count">共 {{ total }} 条</span>
      <button class="btn" @click="load">刷新</button>
    </div>

    <!-- 列表 -->
    <div class="panel table-panel">
      <table class="data-table">
        <thead>
          <tr>
            <th style="width: 60px">序号</th>
            <th style="width: 130px">发现时间</th>
            <th style="width: 110px">设备</th>
            <th style="width: 100px">类别</th>
            <th style="width: 80px">目标数</th>
            <th style="width: 90px">置信度</th>
            <th style="width: 150px">坐标</th>
            <th style="width: 90px">状态</th>
            <th>关联工单</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(e, i) in items" :key="e.event_id">
            <td class="num text-dim">{{ (page - 1) * pageSize + i + 1 }}</td>
            <td class="num">{{ fmtShortTime(e.event_time) }}</td>
            <td class="text-sub">{{ e.device_id }}</td>
            <td>
              <i class="dot" :style="{ background: classColor(e.main_class) }"></i>
              {{ e.main_class_label || classLabel(e.main_class) }}
            </td>
            <td class="num">{{ e.det_count }}</td>
            <td class="num">{{ fmtConfidence(e.max_confidence) }}</td>
            <td class="num text-sub">{{ fmtCoord(e.lng, e.lat) }}</td>
            <td>
              <span class="badge" :class="`badge-${e.status}`">
                {{ EVENT_STATUS[e.status] || e.status }}
              </span>
            </td>
            <td class="text-dim" style="font-size: 12px">
              {{ taskMap[e.event_id] ? taskMap[e.event_id] : '—' }}
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="!items.length" class="empty">
        {{ loading ? '加载中…' : '没有符合条件的事件' }}
      </div>

      <!-- 分页 -->
      <div v-if="total > pageSize" class="pager">
        <button class="btn" :disabled="page <= 1" @click="goto(page - 1)">上一页</button>
        <span class="pager__info">
          第 {{ page }} / {{ Math.ceil(total / pageSize) }} 页
        </span>
        <button
          class="btn"
          :disabled="page >= Math.ceil(total / pageSize)"
          @click="goto(page + 1)"
        >
          下一页
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { eventsApi, tasksApi } from '@/api'
import { useRealtimeStore } from '@/stores/realtime'
import { CLASS_ORDER, EVENT_STATUS, classLabel, classColor } from '@/utils/constants'
import { fmtShortTime, fmtConfidence, fmtCoord } from '@/utils/format'

const store = useRealtimeStore()

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(30)
const loading = ref(false)
const taskMap = ref({})

const filters = reactive({
  hours: 24,
  mainClass: '',
  status: '',
  deviceId: '',
})

async function load() {
  loading.value = true
  try {
    const res = await eventsApi.list({
      hours: filters.hours,
      main_class: filters.mainClass || undefined,
      status: filters.status || undefined,
      device_id: filters.deviceId || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    items.value = res?.items || []
    total.value = res?.meta?.total ?? items.value.length
    await buildTaskMap()
  } catch (err) {
    store.error = err.message
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

/** 把事件与工单关联起来，列表里直接能看出"这条有没有被处理" */
async function buildTaskMap() {
  try {
    const res = await tasksApi.list({ limit: 200 })
    const tasks = res?.items || []
    const map = {}
    for (const t of tasks) {
      if (t.event_id) map[t.event_id] = t.task_id
    }
    taskMap.value = map
  } catch {
    /* 关联失败不影响主列表 */
  }
}

function goto(p) {
  page.value = p
  load()
}

onMounted(load)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 9px 14px;
  flex-shrink: 0;
}

.toolbar__group {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.toolbar__group label {
  color: var(--text-sub);
}

.toolbar__group select {
  background: var(--bg-panel-2);
  color: var(--text-main);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 3px 8px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
}

.toolbar__group select:focus {
  border-color: var(--c-primary-dim);
}

.toolbar__spacer {
  flex: 1;
}

.toolbar__count {
  font-size: 12px;
  color: var(--text-sub);
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
  opacity: 0.4;
  cursor: not-allowed;
}

.table-panel {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 12px;
  border-top: 1px solid var(--border);
}

.pager__info {
  font-size: 13px;
  color: var(--text-sub);
}
</style>
