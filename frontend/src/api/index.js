/**
 * 接口封装 —— 与后端 app/api/v1/*.py 一一对应。
 */
import http from './http'

// ---------- 事件 ----------
export const eventsApi = {
  /** 事件列表 */
  list(params = {}) {
    return http.get('/events', { params })
  },

  /** 事件详情 */
  detail(eventId) {
    return http.get(`/events/${eventId}`)
  },

  /** 人工更新事件状态（忽略误报 / 确认清理） */
  updateStatus(eventId, payload) {
    return http.patch(`/events/${eventId}`, payload)
  },

  /** 热力图网格聚合 */
  heatmap(params = {}) {
    return http.get('/events/heatmap', { params })
  },

  /** 事件上报（边缘盒 HTTP 通道，MQTT 为主、HTTP 为备份） */
  report(payload) {
    return http.post('/events', payload)
  },
}

// ---------- 任务（工单） ----------
export const tasksApi = {
  list(params = {}) {
    return http.get('/tasks', { params })
  },

  detail(taskId) {
    return http.get(`/tasks/${taskId}`)
  },

  /** 人工创建任务 */
  create(payload) {
    return http.post('/tasks', payload)
  },

  /** 更新任务状态（走后端状态机校验） */
  updateStatus(taskId, payload) {
    return http.patch(`/tasks/${taskId}`, payload)
  },

  /** 手动触发补派 */
  dispatchPending() {
    return http.post('/tasks/dispatch/pending')
  },

  /** 导出工单 CSV（返回 Blob） */
  export(params = {}) {
    return http.get('/tasks/export', { params, responseType: 'blob' })
  },
}

// ---------- 设备 ----------
export const devicesApi = {
  list(params = {}) {
    return http.get('/devices', { params })
  },

  detail(deviceId) {
    return http.get(`/devices/${deviceId}`)
  },

  /** 取视频流地址（go2rtc 的 flv / webrtc / hls） */
  stream(deviceId) {
    return http.get(`/devices/${deviceId}/stream`)
  },
}

// ---------- 机器人 ----------
export const robotsApi = {
  list() {
    return http.get('/robots')
  },

  detail(robotId) {
    return http.get(`/robots/${robotId}`)
  },
}

// ---------- 统计 ----------
export const statsApi = {
  /** 大屏指标卡 */
  dashboard() {
    return http.get('/stats/dashboard')
  },

  /** 类别分布（饼图） */
  classes(hours = 24) {
    return http.get('/stats/classes', { params: { hours } })
  },

  /** 事件趋势（折线） */
  trend(hours = 24) {
    return http.get('/stats/trend', { params: { hours } })
  },

  /** 站内通知（最近告警 + 工单动态） */
  notifications(params = {}) {
    return http.get('/stats/notifications', { params })
  },
}

// ---------- 报表 ----------
export const reportsApi = {
  daily(params = {}) {
    return http.get('/reports/daily', { params })
  },

  summary(days = 7) {
    return http.get('/reports/summary', { params: { days } })
  },

  /** 导出日报表 CSV（返回 Blob） */
  export(params = {}) {
    return http.get('/reports/export', { params, responseType: 'blob' })
  },
}

// ---------- 认证 ----------
export const authApi = {
  login(username, password) {
    return http.post('/auth/login', { username, password })
  },

  me() {
    return http.get('/auth/me')
  },
}

/** 把 Blob 保存为本地文件（导出 CSV 用） */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
