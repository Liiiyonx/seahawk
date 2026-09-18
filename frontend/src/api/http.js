/**
 * HTTP 客户端。
 *
 * 后端约定：HTTP 状态码恒为 200，业务结果看 body.code。
 * 这样做的代价是前端必须统一拆信封 —— 所以拦截器里做，
 * 组件拿到的直接就是 data，不用每处都写 .data.data。
 */
import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// ---------- 请求拦截：注入身份令牌 ----------
http.interceptors.request.use((config) => {
  // 令牌由登录接口签发，后端从 Authorization 头验签解析角色。
  // 不传 X-User/X-Role：那些是前端可伪造的字段，不能作为权限依据。
  const token = localStorage.getItem('seasight_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ---------- 响应拦截：拆信封 ----------
http.interceptors.response.use(
  (response) => {
    const body = response.data

    // 非标准响应（如文件流）直接放行
    if (body == null || typeof body !== 'object' || !('code' in body)) {
      return body
    }

    if (body.code === 0) {
      return body.data
    }

    // 业务错误：统一抛出，由调用方 catch
    const err = new Error(body.message || '请求失败')
    err.code = body.code
    err.traceId = body.trace_id
    return Promise.reject(err)
  },
  (error) => {
    const status = error.response?.status
    let message = error.message

    if (status === 401) message = '未登录或登录已过期'
    else if (status === 403) message = '无权限执行该操作'
    else if (status === 404) message = '接口不存在'
    else if (status >= 500) message = '服务异常，请稍后重试'
    else if (error.code === 'ECONNABORTED') message = '请求超时'
    else if (!error.response) message = '无法连接后端服务，请确认后端已启动'

    const err = new Error(message)
    err.status = status
    return Promise.reject(err)
  },
)

export default http
