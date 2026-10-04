/**
 * 登录态（轻量响应式模块）。
 * 小程序端只此一处状态，不值得引 Pinia —— 用 Vue reactive + storage 即可。
 */
import { reactive, computed } from 'vue'
import { getToken, getStoredUser, saveAuth, clearAuth } from '@/api/http'
import { roleLabel } from '@/utils/constants'

const state = reactive({
  token: getToken(),
  user: getStoredUser(),
})

export const isLoggedIn = computed(() => !!state.token)

export const currentUser = computed(() => state.user || {})

export const roleText = computed(() => roleLabel(state.user?.role))

/** operator / admin 才显示写操作（后端 require_operator 是最终裁决） */
export const canWrite = computed(
  () => state.user?.role === 'admin' || state.user?.role === 'operator',
)

export function setAuth(token, user) {
  state.token = token
  state.user = user || {}
  saveAuth(token, user)
}

export function logout() {
  state.token = ''
  state.user = {}
  clearAuth()
}
