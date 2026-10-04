/**
 * HTTP 客户端（小程序版）。
 *
 * 与 Web 端 frontend/src/api/http.js 同一套纪律：
 * - 后端恒返回 200 + 业务信封 {code, message, data, trace_id}，这里统一拆信封；
 * - 401 / token 失效 → 清登录态并跳登录页（Web 端靠路由守卫，小程序靠这里兜底）；
 * - 错误 message 优先用后端信封里的（比前端兜底文案精确）。
 */

const TOKEN_KEY = 'seasight_token'
const USER_KEY = 'seasight_user'

/** API 基址：.env.local 里配 VITE_API_BASE 覆盖（真机需 https 合法域名） */
export const API_BASE =
  import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

/** WebSocket 基址（告警实时推送；query 带 token，见 docs/api.md 第十节） */
export function wsUrl() {
  const base = import.meta.env.VITE_WS_BASE || API_BASE.replace(/^http/, 'ws')
  const token = uni.getStorageSync(TOKEN_KEY) || ''
  return `${base}/ws/alerts?token=${encodeURIComponent(token)}`
}

export function getToken() {
  return uni.getStorageSync(TOKEN_KEY) || ''
}

export function saveAuth(token, user) {
  uni.setStorageSync(TOKEN_KEY, token)
  uni.setStorageSync(USER_KEY, JSON.stringify(user || {}))
}

export function clearAuth() {
  uni.removeStorageSync(TOKEN_KEY)
  uni.removeStorageSync(USER_KEY)
}

export function getStoredUser() {
  try {
    return JSON.parse(uni.getStorageSync(USER_KEY) || '{}')
  } catch {
    return {}
  }
}

function redirectToLogin() {
  clearAuth()
  // reLaunch 清掉 tabBar 栈，避免未登录状态在各 tab 间残留
  uni.reLaunch({ url: '/pages/login/login' })
}

/**
 * 请求封装。resolve 直接是 data（信封已拆），reject 是 Error（带 message/code）。
 */
export function request(method, path, data = {}, options = {}) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${API_BASE}${path}`,
      method,
      data,
      timeout: 15000,
      header: {
        'Content-Type': 'application/json',
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      },
      success(res) {
        // HTTP 层失败：后端 4xx/5xx 也带业务信封，优先取它的 message
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const payload = res.data
          const serverMessage =
            payload && typeof payload === 'object' && typeof payload.message === 'string'
              ? payload.message.trim()
              : ''
          if (res.statusCode === 401) {
            redirectToLogin()
          }
          const err = new Error(
            serverMessage ||
              (res.statusCode === 403
                ? '无权限执行该操作'
                : res.statusCode >= 500
                  ? '服务异常，请稍后重试'
                  : '请求失败'),
          )
          err.status = res.statusCode
          err.code = payload?.code
          reject(err)
          return
        }

        const body = res.data
        // 非标准响应直接放行
        if (body == null || typeof body !== 'object' || !('code' in body)) {
          resolve(body)
          return
        }
        if (body.code === 0) {
          resolve(body.data)
          return
        }
        // 业务错误码 40x01 表示令牌问题 → 回登录页
        if (body.code === 40001 || body.code === 40101 || body.code === 40102) {
          redirectToLogin()
        }
        const err = new Error(body.message || '请求失败')
        err.code = body.code
        err.traceId = body.trace_id
        reject(err)
      },
      fail(e) {
        reject(new Error('无法连接服务，请检查网络或后端地址'))
        void e
      },
    })
  })
}

export default {
  get: (path, params) => request('GET', path, params),
  post: (path, data) => request('POST', path, data),
  patch: (path, data) => request('PATCH', path, data),
  delete: (path) => request('DELETE', path),
}
