/**
 * 全局Toast通知系统
 * 
 * 解决智能体控制台"点击无反馈"问题：
 * - 操作成功/失败即时提示
 * - 支持操作按钮（如"重试"、"查看"）
 * - 自动消失 + 常驻错误
 */

import { ref, readonly } from 'vue'

// 通知类型
export const ToastType = {
  SUCCESS: 'success',
  ERROR: 'error',
  INFO: 'info',
  WARNING: 'warning',
  LOADING: 'loading',
}

// 全局通知列表
const toasts = ref([])
let seq = 0

/**
 * 显示通知
 * @param {Object} options
 * @param {string} options.message 消息内容
 * @param {string} options.type 类型
 * @param {number} options.duration 持续时间(ms)，0=常驻
 * @param {Array} options.actions 操作按钮 [{label, onClick}]
 * @returns {Function} 关闭函数
 */
export function showToast({ message, type = ToastType.INFO, duration = 3000, actions = [] }) {
  const id = ++seq
  const toast = {
    id,
    message,
    type,
    actions,
    visible: true,
  }
  
  toasts.value.push(toast)
  
  if (duration > 0) {
    setTimeout(() => removeToast(id), duration)
  }
  
  return () => removeToast(id)
}

/**
 * 移除通知
 */
export function removeToast(id) {
  const idx = toasts.value.findIndex(t => t.id === id)
  if (idx >= 0) {
    toasts.value[idx].visible = false
    // 动画结束后真正移除
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, 300)
  }
}

/**
 * 清空所有通知
 */
export function clearToasts() {
  toasts.value = []
}

// 便捷方法
export const toast = {
  success(msg, opts = {}) {
    return showToast({ message: msg, type: ToastType.SUCCESS, duration: 3000, ...opts })
  },
  
  error(msg, opts = {}) {
    return showToast({ message: msg, type: ToastType.ERROR, duration: 0, ...opts })
  },
  
  info(msg, opts = {}) {
    return showToast({ message: msg, type: ToastType.INFO, duration: 4000, ...opts })
  },
  
  warning(msg, opts = {}) {
    return showToast({ message: msg, type: ToastType.WARNING, duration: 5000, ...opts })
  },
  
  loading(msg) {
    return showToast({ message: msg, type: ToastType.LOADING, duration: 0 })
  },
}

// 供组件使用的只读列表
export const toastList = readonly(toasts)
