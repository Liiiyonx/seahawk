<template>
  <view class="tasks">
    <!-- 状态筛选（横向滚动 chips，计数即 Tab 徽标） -->
    <scroll-view class="tasks__chips" scroll-x :show-scrollbar="false">
      <view class="tasks__chips-inner">
        <view
          v-for="s in statusSummary"
          :key="s.key"
          class="tasks__chip"
          :class="{ 'tasks__chip--on': activeStatus === s.key }"
          @tap="toggleStatus(s.key)"
        >
          <text>{{ s.label }}</text>
          <text class="tasks__chip-num">{{ s.count }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- 工单列表 -->
    <view v-if="visibleTasks.length" class="tasks__list">
      <view
        v-for="t in visibleTasks"
        :key="t.task_id"
        class="card tasks__card"
        @tap="openDetail(t)"
      >
        <view class="tasks__card-head">
          <text class="tasks__id">{{ t.task_id }}</text>
          <text class="badge" :class="taskBadgeClass(t.status)">
            {{ TASK_STATUS[t.status] || t.status }}
          </text>
        </view>
        <view class="tasks__row">
          <text class="tasks__row-k">机器人</text>
          <text class="tasks__row-v">{{ t.robot_id || '未分配' }}</text>
        </view>
        <view class="tasks__row">
          <text class="tasks__row-k">目标点</text>
          <text class="tasks__row-v tasks__mono">{{ fmtCoord(t.lng, t.lat) }}</text>
        </view>
        <view class="tasks__row">
          <text class="tasks__row-k">创建</text>
          <text class="tasks__row-v">{{ fmtRelative(t.created_at) }}</text>
        </view>
        <view v-if="t.collected_weight" class="tasks__row">
          <text class="tasks__row-k">打捞量</text>
          <text class="tasks__row-v tasks__hl">
            {{ Number(t.collected_weight).toFixed(2) }} kg
          </text>
        </view>
        <!-- 快捷推进：列表内直接流转，不用进详情 -->
        <view v-if="canWrite && nextStates(t.status).length" class="tasks__actions" @tap.stop>
          <button
            v-for="ns in nextStates(t.status)"
            :key="ns"
            class="btn tasks__action-btn"
            :class="ns === 'cancelled' ? 'btn-danger' : ''"
            size="mini"
            @tap="changeStatus(t, ns)"
          >
            {{ TASK_STATUS[ns] }}
          </button>
        </view>
      </view>
    </view>

    <view v-else class="empty">
      {{ loading ? '加载中…' : '暂无工单' }}
    </view>

    <view class="tasks__footnote">
      <text>共 {{ tasks.length }} 单 · {{ canWrite ? '点击卡片查看详情与生命周期' : '只读账号，操作请使用操作员登录' }}</text>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow, onPullDownRefresh } from '@dcloudio/uni-app'
import { tasksApi } from '@/api'
import { isLoggedIn, canWrite } from '@/stores/auth'
import { TASK_STATUS, taskBadgeClass, nextStates } from '@/utils/constants'

const tasks = ref([])
const loading = ref(false)
const activeStatus = ref('')

const STATUS_ORDER = ['pending', 'assigned', 'navigating', 'collecting', 'done']

const statusSummary = computed(() =>
  STATUS_ORDER.map((k) => ({
    key: k,
    label: TASK_STATUS[k],
    count: tasks.value.filter((t) => t.status === k).length,
  })),
)

const visibleTasks = computed(() =>
  activeStatus.value
    ? tasks.value.filter((t) => t.status === activeStatus.value)
    : tasks.value,
)

function toggleStatus(key) {
  activeStatus.value = activeStatus.value === key ? '' : key
}

function fmtCoord(lng, lat) {
  if (lng == null || lat == null) return '—'
  return `${Number(lng).toFixed(4)}, ${Number(lat).toFixed(4)}`
}

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

async function load() {
  if (!isLoggedIn.value) {
    uni.reLaunch({ url: '/pages/login/login' })
    return
  }
  loading.value = true
  try {
    const res = await tasksApi.list({ page: 1, page_size: 100 })
    tasks.value = res?.items || []
  } catch (err) {
    uni.showToast({ title: err.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function openDetail(task) {
  uni.navigateTo({ url: `/pages/task-detail/task-detail?id=${task.task_id}` })
}

async function changeStatus(task, target) {
  // 完成需要录入打捞量，进详情页走表单（与 Web 端一致：不伪造数据）
  if (target === 'done') {
    openDetail(task)
    return
  }
  const confirmText =
    target === 'cancelled' ? `确认取消工单 ${task.task_id}？` : `推进到「${TASK_STATUS[target]}」？`
  uni.showModal({
    title: '状态流转',
    content: confirmText,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await tasksApi.updateStatus(task.task_id, { status: target })
        uni.showToast({ title: '已更新', icon: 'success' })
        await load()
      } catch (err) {
        uni.showToast({ title: err.message || '操作失败', icon: 'none' })
      }
    },
  })
}

onShow(load)
onPullDownRefresh(async () => {
  await load()
  uni.stopPullDownRefresh()
})
</script>

<style scoped>
.tasks {
  padding-top: 20rpx;
  padding-bottom: calc(24rpx + env(safe-area-inset-bottom));
}

.tasks__chips {
  width: 100%;
  white-space: nowrap;
}

.tasks__chips-inner {
  display: inline-flex;
  gap: 14rpx;
  padding: 0 24rpx 20rpx;
}

.tasks__chip {
  display: inline-flex;
  align-items: center;
  gap: 12rpx;
  min-height: 68rpx;
  padding: 0 26rpx;
  border-radius: 999rpx;
  background: var(--bg-panel);
  color: var(--text-sub);
  font-size: 26rpx;
  border: 1px solid var(--border);
}

.tasks__chip--on {
  background: var(--bg-active);
  border-color: var(--c-primary-dim);
  color: var(--c-primary);
  font-weight: 600;
}

.tasks__chip-num {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.tasks__list {
  display: flex;
  flex-direction: column;
}

.tasks__card {
  margin-bottom: 20rpx;
}

.tasks__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14rpx;
}

.tasks__id {
  font-size: 24rpx;
  color: var(--c-primary);
  font-family: Menlo, Consolas, monospace;
}

.tasks__row {
  display: flex;
  justify-content: space-between;
  gap: 16rpx;
  font-size: 26rpx;
  line-height: 1.9;
}

.tasks__row-k {
  color: var(--text-sub);
  flex-shrink: 0;
}

.tasks__row-v {
  color: var(--text-main);
  text-align: right;
}

.tasks__mono {
  font-family: Menlo, Consolas, monospace;
  font-size: 24rpx;
}

.tasks__hl {
  color: var(--c-primary);
  font-weight: 600;
}

.tasks__actions {
  display: flex;
  gap: 14rpx;
  margin-top: 18rpx;
  padding-top: 18rpx;
  border-top: 1px solid var(--separator);
}

.tasks__action-btn {
  flex: 1;
  min-height: 68rpx;
  font-size: 26rpx;
  background: var(--bg-active);
  color: var(--c-primary);
  border-radius: 16rpx;
}

.tasks__footnote {
  padding: 8rpx 32rpx 0;
  font-size: 22rpx;
  color: var(--text-dim);
  text-align: center;
}
</style>
