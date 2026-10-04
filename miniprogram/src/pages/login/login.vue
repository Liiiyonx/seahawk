<template>
  <view class="login">
    <!-- 品牌区 -->
    <view class="login__hero">
      <view class="login__logo">
        <text class="login__logo-icon">◈</text>
      </view>
      <text class="login__title">探海灵眸</text>
      <text class="login__subtitle">SeaSight · 海洋漂浮垃圾智能治理平台</text>
    </view>

    <!-- 表单卡片 -->
    <view class="login__card">
      <view class="login__field">
        <text class="login__label">账号</text>
        <input
          v-model="form.username"
          class="form-input"
          type="text"
          placeholder="请输入账号"
          placeholder-class="login__placeholder"
          :adjust-position="true"
        />
      </view>
      <view class="login__field">
        <text class="login__label">密码</text>
        <view class="login__pw">
          <input
            v-model="form.password"
            class="form-input login__pw-input"
            :password="!showPw"
            placeholder="请输入密码"
            placeholder-class="login__placeholder"
          />
          <text class="login__pw-toggle" @tap="showPw = !showPw">
            {{ showPw ? '隐藏' : '显示' }}
          </text>
        </view>
      </view>

      <button
        class="btn btn-primary login__submit"
        :class="{ 'btn-disabled': submitting || !form.username || !form.password }"
        :disabled="submitting || !form.username || !form.password"
        @tap="submit"
      >
        {{ submitting ? '登录中…' : '登 录' }}
      </button>

      <text v-if="errorText" class="login__error">{{ errorText }}</text>
    </view>

    <text class="login__footnote">与 Web 端共用账号体系 · JWT 令牌存储于本机</text>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { authApi } from '@/api'
import { setAuth } from '@/stores/auth'

const form = reactive({ username: '', password: '' })
const showPw = ref(false)
const submitting = ref(false)
const errorText = ref('')

async function submit() {
  if (submitting.value || !form.username || !form.password) return
  submitting.value = true
  errorText.value = ''
  try {
    const data = await authApi.login(form.username, form.password)
    // 后端返回 {access_token, user}（见 docs/api.md 二、认证）
    setAuth(data.access_token, data.user || { username: form.username })
    uni.reLaunch({ url: '/pages/tasks/tasks' })
  } catch (err) {
    errorText.value = err.message || '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 48rpx;
  padding-top: 18vh;
  background: var(--bg-page);
  box-sizing: border-box;
}

.login__hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 64rpx;
}

.login__logo {
  width: 128rpx;
  height: 128rpx;
  border-radius: 34rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #0877e8, #00a6c8);
  box-shadow: 0 12rpx 36rpx rgba(0, 122, 255, 0.28);
  margin-bottom: 28rpx;
}

.login__logo-icon {
  font-size: 60rpx;
  color: #ffffff;
}

.login__title {
  font-size: 52rpx;
  font-weight: 700;
  color: var(--text-main);
  letter-spacing: 4rpx;
}

.login__subtitle {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: var(--text-dim);
}

.login__card {
  width: 100%;
  background: var(--bg-panel);
  border-radius: var(--radius-lg);
  padding: 40rpx 32rpx 36rpx;
}

.login__field {
  margin-bottom: 28rpx;
}

.login__label {
  display: block;
  font-size: 26rpx;
  color: var(--text-sub);
  margin-bottom: 12rpx;
}

.login__placeholder {
  color: var(--text-dim);
}

.login__pw {
  position: relative;
}

.login__pw-input {
  padding-right: 120rpx;
}

.login__pw-toggle {
  position: absolute;
  right: 24rpx;
  top: 50%;
  transform: translateY(-50%);
  font-size: 26rpx;
  color: var(--c-primary);
}

.login__submit {
  margin-top: 12rpx;
  width: 100%;
}

.login__error {
  display: block;
  margin-top: 20rpx;
  font-size: 26rpx;
  color: var(--c-danger);
  text-align: center;
}

.login__footnote {
  margin-top: 48rpx;
  font-size: 22rpx;
  color: var(--text-dim);
}
</style>
