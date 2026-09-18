/**
 * 认证状态管理 —— 令牌与用户信息的读写集中在此。
 *
 * 后端认证模型：
 *   - 登录（POST /auth/login）签发签名令牌，载荷含 sub/role/scope/exp；
 *   - 业务接口从 Authorization: Bearer <token> 解析身份（服务端验签）；
 *   - 未登录 → 匿名 viewer（只读）；写操作需 operator / admin。
 *
 * 所以前端只需要「存令牌 + 请求时带上」，角色判断用登录响应里返回的
 * role（仅用于 UI 显隐），真正的权限裁决在后端，前端显隐只是体验优化。
 */

const TOKEN_KEY = 'seasight_token'
const USER_KEY = 'seasight_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user || {}))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isLoggedIn() {
  return !!getToken()
}

/** 是否有写权限（仅前端显隐用，后端才是最终裁决） */
export function canWrite() {
  const u = getUser()
  return !!u && (u.role === 'admin' || u.role === 'operator')
}

export function roleLabel(role) {
  return { admin: '系统管理员', operator: '乡镇操作员', viewer: '访客' }[role] || role || '访客'
}
