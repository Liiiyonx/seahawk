<template>
  <div class="login">
    <div class="login__card panel">
      <div class="login__brand">
        <span class="login__mark">◈</span>
        <div>
          <div class="login__name">探海灵眸</div>
          <div class="login__sub">SeaSight · 海漂垃圾智能治理平台</div>
        </div>
      </div>

      <form class="login__form" @submit.prevent="submit">
        <label class="login__label" for="username">账号</label>
        <input
          id="username"
          v-model="username"
          class="login__input"
          type="text"
          autocomplete="username"
          placeholder="请输入账号"
        />

        <label class="login__label" for="password">密码</label>
        <input
          id="password"
          v-model="password"
          class="login__input"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
        />

        <button class="login__btn" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登 录' }}
        </button>

        <p v-if="error" class="login__error">{{ error }}</p>
      </form>

      <button class="login__preview" @click="preview">
        以访客身份预览（无需后端）
      </button>

      <details class="login__demo">
        <summary>演示账号（点击一行即可自动填入）</summary>
        <table class="login__demo-table">
          <tbody>
            <tr class="demo-row" @click="fillDemo('admin', 'admin123456')">
              <td>admin / admin123456</td><td>系统管理员 · 全部权限</td>
            </tr>
            <tr class="demo-row" @click="fillDemo('operator', 'operator123456')">
              <td>operator / operator123456</td><td>乡镇操作员 · 马鼻镇辖区</td>
            </tr>
            <tr class="demo-row" @click="fillDemo('viewer', 'viewer123456')">
              <td>viewer / viewer123456</td><td>访客 · 只读大屏</td>
            </tr>
          </tbody>
        </table>
      </details>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { authApi } from '@/api'
import { setAuth } from '@/utils/auth'

const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  if (!username.value || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await authApi.login(username.value, password.value)
    setAuth(res.access_token, {
      username: username.value,
      role: res.role,
      full_name: res.full_name,
      township_scope: res.township_scope,
    })
    router.replace(route.query.redirect || '/dashboard')
  } catch (err) {
    error.value = err.message || '登录失败'
  } finally {
    loading.value = false
  }
}

function preview() {
  // 访客预览：无需后端即可进入看 UI 骨架与设计（数据为空，接口会静默失败）
  setAuth('guest-preview', { username: '预览', role: 'viewer', full_name: '访客预览' })
  router.replace('/dashboard')
}

function fillDemo(u, p) {
  // 一键填入演示账号，避免手动输入
  username.value = u
  password.value = p
  error.value = ''
}
</script>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: var(--bg-page);
}

.login__card {
  width: 360px;
  max-width: 92vw;
  padding: 30px 32px;
  border-radius: var(--radius-lg, 12px);
}

.login__brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.login__mark {
  color: var(--c-primary);
  font-size: 30px;
}

.login__name {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 3px;
  color: var(--text-main);
}

.login__sub {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

.login__form {
  display: flex;
  flex-direction: column;
}

.login__label {
  font-size: 12.5px;
  color: var(--text-sub);
  margin: 12px 0 6px;
}

.login__input {
  padding: 9px 12px;
  font-size: 14px;
  color: var(--text-main);
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 5px;
  outline: none;
}

.login__input:focus {
  border-color: var(--c-primary-dim);
}

.login__btn {
  margin-top: 22px;
  padding: 10px;
  font-size: 15px;
  letter-spacing: 4px;
  color: #06251f;
  background: var(--grad-primary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: box-shadow 0.2s var(--ease);
}

.login__btn:hover:not(:disabled) {
  box-shadow: 0 6px 20px rgba(24, 224, 200, 0.3);
}

.login__btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login__preview {
  width: 100%;
  margin-top: 10px;
  padding: 8px;
  font-size: 13px;
  color: var(--text-sub);
  background: transparent;
  border: 1px dashed var(--border-bright);
  border-radius: 6px;
  cursor: pointer;
  transition: color 0.2s var(--ease), border-color 0.2s var(--ease);
}

.login__preview:hover {
  color: var(--c-primary);
  border-color: var(--c-primary-dim);
}

.login__error {
  margin-top: 12px;
  font-size: 12.5px;
  color: var(--c-danger);
}

.login__demo {
  margin-top: 22px;
  font-size: 12px;
  color: var(--text-sub);
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.login__demo summary {
  cursor: pointer;
  user-select: none;
}

.login__demo-table {
  margin-top: 8px;
  width: 100%;
  font-size: 12px;
  color: var(--text-sub);
  border-collapse: collapse;
}

.login__demo-table td {
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.login__demo-table td:first-child {
  color: var(--c-primary);
  font-family: 'SF Mono', Consolas, monospace;
  padding-right: 10px;
}

.demo-row {
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s var(--ease);
}

.demo-row:hover {
  background: rgba(24, 224, 200, 0.08);
}
</style>
