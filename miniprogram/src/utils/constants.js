/**
 * 全局常量 —— 与 Web 端 frontend/src/utils/constants.js 同源（精简）。
 * 状态机必须与后端 TaskStatus.TRANSITIONS 一致：前端只做按钮过滤，后端最终校验。
 */

export const TASK_STATUS = {
  pending: '待派单',
  assigned: '已派单',
  navigating: '前往中',
  collecting: '作业中',
  done: '已完成',
  cancelled: '已取消',
}

export const TASK_TRANSITIONS = {
  pending: ['assigned', 'cancelled'],
  assigned: ['navigating', 'pending', 'cancelled'],
  navigating: ['collecting', 'cancelled'],
  collecting: ['done', 'cancelled'],
  done: [],
  cancelled: [],
}

export function canTransition(current, target) {
  return (TASK_TRANSITIONS[current] || []).includes(target)
}

/** 徽标 class 映射（样式在 App.vue 全局定义） */
export function taskBadgeClass(status) {
  const map = {
    pending: 'badge-pending',
    assigned: 'badge-assigned',
    navigating: 'badge-navigating',
    collecting: 'badge-collecting',
    done: 'badge-done',
    cancelled: 'badge-cancelled',
  }
  return map[status] || 'badge-offline'
}

export const EVENT_STATUS = {
  new: '待处理',
  dispatched: '已派单',
  resolved: '已清理',
  ignored: '已忽略',
}

export const WASTE_CLASSES = {
  foam: '泡沫类',
  plastic: '塑胶类',
  fishing_gear: '渔具类',
  other: '其他',
}

export function classLabel(code) {
  return WASTE_CLASSES[code] || code || '未知'
}

export const ROLE_LABEL = {
  admin: '管理员',
  operator: '操作员',
  viewer: '观察者',
}

export function roleLabel(role) {
  return ROLE_LABEL[role] || role || '未知角色'
}

/** 当前状态下允许的下一步（小程序端给最常用的两条，与 Web 端一致） */
export function nextStates(status) {
  const allowed = TASK_TRANSITIONS[status] || []
  const priority = ['done', 'collecting', 'navigating', 'cancelled']
  return allowed.filter((s) => priority.includes(s)).slice(0, 2)
}
