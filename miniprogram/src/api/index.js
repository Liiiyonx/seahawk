/**
 * 接口封装（小程序端精简版）—— 只放小程序用得到的接口，
 * 与后端 docs/api.md 契约一一对应。
 */
import http from './http'

// ---------- 认证 ----------
export const authApi = {
  login(username, password) {
    return http.post('/auth/login', { username, password })
  },
  me() {
    return http.get('/auth/me')
  },
}

// ---------- 任务（工单） ----------
export const tasksApi = {
  list(params = {}) {
    return http.get('/tasks', params)
  },
  detail(taskId) {
    return http.get(`/tasks/${taskId}`)
  },
  /** 状态流转走后端状态机校验（前端只做展示过滤） */
  updateStatus(taskId, payload) {
    return http.patch(`/tasks/${taskId}`, payload)
  },
}

// ---------- 事件 ----------
export const eventsApi = {
  list(params = {}) {
    return http.get('/events', params)
  },
}

// ---------- 统计 ----------
export const statsApi = {
  dashboard() {
    return http.get('/stats/dashboard')
  },
  /** 站内通知（告警页轮询兜底用，与 WS 推送同构） */
  notifications(params = {}) {
    return http.get('/stats/notifications', params)
  },
}
