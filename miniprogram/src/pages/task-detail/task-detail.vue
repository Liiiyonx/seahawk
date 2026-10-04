<template>
  <view class="detail">
    <!-- 状态头 -->
    <view class="card detail__head">
      <view class="detail__head-row">
        <text class="detail__id">{{ task.task_id }}</text>
        <text class="badge" :class="taskBadgeClass(task.status)">
          {{ TASK_STATUS[task.status] || task.status || '…' }}
        </text>
      </view>
      <view class="detail__rows">
        <view class="detail__row">
          <text class="detail__row-k">执行机器人</text>
          <text class="detail__row-v">{{ task.robot_id || '未分配' }}</text>
        </view>
        <view class="detail__row">
          <text class="detail__row-k">事件编号</text>
          <text class="detail__row-v detail__mono">{{ task.event_id || '—' }}</text>
        </view>
        <view class="detail__row">
          <text class="detail__row-k">目标坐标</text>
          <text class="detail__row-v detail__mono">{{ fmtCoord(task.lng, task.lat) }}</text>
        </view>
        <view class="detail__row">
          <text class="detail__row-k">优先级</text>
          <text class="detail__row-v">P{{ task.priority ?? '—' }}</text>
        </view>
        <view class="detail__row">
          <text class="detail__row-k">打捞重量</text>
          <text class="detail__row-v">
            {{ task.collected_weight != null ? `${Number(task.collected_weight).toFixed(2)} kg` : '—' }}
          </text>
        </view>
      </view>
    </view>

    <!-- 生命周期时间轴 -->
    <view class="card">
      <view class="card-title">生命周期</view>
      <view
        v-for="step in timeline"
        :key="step.label"
        class="detail__step"
        :class="{ 'detail__step--done': step.time }"
      >
        <view class="detail__dot" />
        <text class="detail__step-label">{{ step.label }}</text>
        <text class="detail__step-time">{{ step.time ? fmtTime(step.time) : '—' }}</text>
      </view>
    </view>

    <!-- 状态流转 -->
    <view v-if="canWrite && nextStates(task.status).length" class="card">
      <view class="card-title">推进状态</view>
      <view class="detail__actions">
        <button
          v-for="ns in nextStates(task.status)"
          :key="ns"
          class="btn detail__action-btn"
          :class="ns === 'cancelled' ? 'btn-danger' : 'btn-primary'"
          @tap="changeStatus(ns)"
        >
          {{ TASK_STATUS[ns] }}
        </button>
      </view>
      <text class="detail__hint">状态机由后端校验，非法流转会被拒绝</text>
    </view>

    <!-- 完成录入：打捞量必须如实填写（与 Web 端一致：不伪造数据） -->
    <view v-if="showDoneForm" class="card detail__done">
      <view class="card-title">完成工单 · 录入</view>
      <view class="detail__field">
        <text class="detail__label">打捞重量（kg）</text>
        <input
          v-model="doneForm.weight"
          class="form-input"
          type="digit"
          placeholder="如实填写本次清理量，可留空"
        />
        <text class="detail__field-hint">来自人工称重或机器人仓容，留空则暂不记录</text>
      </view>
      <view class="detail__field">
        <text class="detail__label">复核结果</text>
        <picker :range="reviewOptions" :value="doneForm.reviewIndex" @change="onReviewChange">
          <view class="form-input detail__picker">
            {{ reviewOptions[doneForm.reviewIndex] }}
          </view>
        </picker>
      </view>
      <view class="detail__actions">
        <button class="btn" @tap="showDoneForm = false">取消</button>
        <button class="btn btn-primary" :disabled="submitting" @tap="confirmDone">
          {{ submitting ? '提交中…' : '确认完成' }}
        </button>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { tasksApi } from '@/api'
import { canWrite } from '@/stores/auth'
import { TASK_STATUS, taskBadgeClass, nextStates } from '@/utils/constants'

const task = ref({})
const taskId = ref('')
const showDoneForm = ref(false)
const submitting = ref(false)
const doneForm = reactive({ weight: '', reviewIndex: 0 })

const reviewOptions = ['确认清理', '到场未发现', '需人工复查']
const reviewValues = ['confirmed', 'not_found', 'recheck']

const timeline = computed(() => {
  const t = task.value
  return [
    { label: '创建', time: t.created_at },
    { label: '派单', time: t.assigned_at },
    { label: '确认（ACK）', time: t.ack_at },
    { label: '开工', time: t.started_at },
    { label: '完成', time: t.finished_at },
  ]
})

function fmtCoord(lng, lat) {
  if (lng == null || lat == null) return '—'
  return `${Number(lng).toFixed(4)}, ${Number(lat).toFixed(4)}`
}

function fmtTime(time) {
  const d = new Date(time)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function onReviewChange(e) {
  doneForm.reviewIndex = Number(e.detail.value) || 0
}

async function load() {
  if (!taskId.value) return
  try {
    task.value = (await tasksApi.detail(taskId.value)) || {}
  } catch (err) {
    uni.showToast({ title: err.message || '加载失败', icon: 'none' })
  }
}

function changeStatus(target) {
  if (target === 'done') {
    showDoneForm.value = true
    doneForm.weight = ''
    doneForm.reviewIndex = 0
    return
  }
  const confirmText =
    target === 'cancelled' ? `确认取消工单 ${taskId.value}？` : `推进到「${TASK_STATUS[target]}」？`
  uni.showModal({
    title: '状态流转',
    content: confirmText,
    success: (res) => {
      if (!res.confirm) return
      applyStatus(target)
    },
  })
}

async function applyStatus(target, extra = {}) {
  submitting.value = true
  try {
    await tasksApi.updateStatus(taskId.value, { status: target, ...extra })
    uni.showToast({ title: '已更新', icon: 'success' })
    showDoneForm.value = false
    await load()
  } catch (err) {
    uni.showToast({ title: err.message || '操作失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

async function confirmDone() {
  const weight = Number(doneForm.weight)
  const payload = { review_result: reviewValues[doneForm.reviewIndex] }
  // 只有如实填写了合法重量才上报；留空不打捞量（保持后端 NULL）
  if (doneForm.weight !== '' && !Number.isNaN(weight) && weight >= 0) {
    payload.collected_weight = weight
  }
  await applyStatus('done', payload)
}

onLoad((query) => {
  taskId.value = query?.id || ''
  load()
})
</script>

<style scoped>
.detail {
  padding: 20rpx 0 40rpx;
}

.detail__head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14rpx;
}

.detail__id {
  font-size: 26rpx;
  color: var(--c-primary);
  font-family: Menlo, Consolas, monospace;
}

.detail__row {
  display: flex;
  justify-content: space-between;
  gap: 16rpx;
  font-size: 26rpx;
  line-height: 1.9;
}

.detail__row-k {
  color: var(--text-sub);
  flex-shrink: 0;
}

.detail__row-v {
  color: var(--text-main);
  text-align: right;
  word-break: break-all;
}

.detail__mono {
  font-family: Menlo, Consolas, monospace;
  font-size: 24rpx;
}

.detail__step {
  display: flex;
  align-items: center;
  gap: 18rpx;
  padding: 12rpx 0;
  font-size: 26rpx;
}

.detail__dot {
  width: 14rpx;
  height: 14rpx;
  border-radius: 50%;
  background: var(--border);
  flex-shrink: 0;
}

.detail__step--done .detail__dot {
  background: var(--c-primary);
  box-shadow: 0 0 0 8rpx rgba(0, 122, 255, 0.14);
}

.detail__step-label {
  color: var(--text-main);
}

.detail__step-time {
  margin-left: auto;
  color: var(--text-sub);
  font-size: 24rpx;
  font-family: Menlo, Consolas, monospace;
}

.detail__actions {
  display: flex;
  gap: 16rpx;
  margin-top: 8rpx;
}

.detail__action-btn {
  flex: 1;
}

.detail__hint {
  display: block;
  margin-top: 16rpx;
  font-size: 22rpx;
  color: var(--text-dim);
  text-align: center;
}

.detail__done {
  border: 1px solid rgba(0, 122, 255, 0.3);
}

.detail__field {
  margin-bottom: 24rpx;
}

.detail__label {
  display: block;
  font-size: 26rpx;
  color: var(--text-sub);
  margin-bottom: 12rpx;
}

.detail__field-hint {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: var(--text-dim);
}

.detail__picker {
  display: flex;
  align-items: center;
  color: var(--text-main);
}
</style>
