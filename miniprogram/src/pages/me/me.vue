<template>
  <view class="me">
    <!-- 用户卡片 -->
    <view class="card me__card">
      <view class="me__avatar">
        <text>{{ avatarChar }}</text>
      </view>
      <view class="me__info">
        <text class="me__name">{{ user.full_name || user.username || '未登录' }}</text>
        <text class="me__role">{{ roleText }}</text>
      </view>
    </view>

    <!-- 今日速览（登录后展示） -->
    <view v-if="stats" class="card">
      <view class="card-title">今日速览</view>
      <view class="me__stats">
        <view class="me__stat">
          <text class="me__stat-num">{{ stats.events_24h ?? '—' }}</text>
          <text class="me__stat-label">24h 事件</text>
        </view>
        <view class="me__stat">
          <text class="me__stat-num">{{ stats.pending_tasks ?? '—' }}</text>
          <text class="me__stat-label">待派单</text>
        </view>
        <view class="me__stat">
          <text class="me__stat-num">{{ stats.active_tasks ?? '—' }}</text>
          <text class="me__stat-label">进行中</text>
        </view>
        <view class="me__stat">
          <text class="me__stat-num">{{ stats.robots_online ?? '—' }}</text>
          <text class="me__stat-label">机器人在线</text>
        </view>
      </view>
    </view>

    <!-- 操作区 -->
    <view class="card">
      <button class="btn me__logout" @tap="logoutConfirm">退出登录</button>
    </view>

    <text class="me__footnote">探海灵眸 Oceanus · 小程序作业端 v1.0</text>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { statsApi } from '@/api'
import { isLoggedIn, currentUser, roleText, logout } from '@/stores/auth'

const stats = ref(null)

const user = computed(() => currentUser.value)

const avatarChar = computed(
  () => (user.value.full_name || user.value.username || '?').slice(0, 1),
)

async function load() {
  if (!isLoggedIn.value) {
    uni.reLaunch({ url: '/pages/login/login' })
    return
  }
  try {
    stats.value = await statsApi.dashboard()
  } catch {
    /* 速览是增强项，失败不影响页面 */
  }
}

function logoutConfirm() {
  uni.showModal({
    title: '退出登录',
    content: '确定要退出当前账号吗？',
    success: (res) => {
      if (!res.confirm) return
      logout()
      uni.reLaunch({ url: '/pages/login/login' })
    },
  })
}

onShow(load)
</script>

<style scoped>
.me {
  padding: 20rpx 0 40rpx;
}

.me__card {
  display: flex;
  align-items: center;
  gap: 24rpx;
}

.me__avatar {
  width: 104rpx;
  height: 104rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #0877e8, #00a6c8);
  color: #ffffff;
  font-size: 44rpx;
  font-weight: 600;
  flex-shrink: 0;
}

.me__info {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  min-width: 0;
}

.me__name {
  font-size: 34rpx;
  font-weight: 600;
  color: var(--text-main);
}

.me__role {
  font-size: 24rpx;
  color: var(--text-sub);
}

.me__stats {
  display: flex;
  gap: 12rpx;
}

.me__stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8rpx;
  padding: 18rpx 0;
  border-radius: var(--radius);
  background: var(--bg-panel-2);
}

.me__stat-num {
  font-size: 40rpx;
  font-weight: 700;
  color: var(--text-main);
  font-variant-numeric: tabular-nums;
}

.me__stat-label {
  font-size: 22rpx;
  color: var(--text-dim);
}

.me__logout {
  color: var(--c-danger);
  background: rgba(255, 59, 48, 0.1);
}

.me__footnote {
  display: block;
  margin-top: 32rpx;
  font-size: 22rpx;
  color: var(--text-dim);
  text-align: center;
}
</style>
