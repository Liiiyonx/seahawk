/**
 * 主题管理：深色（默认）与浅色切换，localStorage 持久化。
 *
 * 实现：给 <html> 设 data-theme 属性（'dark' / 'light'），
 * CSS 用 `html[data-theme='light']` 覆盖浅色变量，默认（:root）即深色。
 */

const THEME_KEY = 'seasight_theme'

export function getTheme() {
  return localStorage.getItem(THEME_KEY) || 'dark'
}

export function applyTheme(theme) {
  const t = theme === 'light' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', t)
  localStorage.setItem(THEME_KEY, t)
  return t
}

export function toggleTheme() {
  return applyTheme(getTheme() === 'light' ? 'dark' : 'light')
}

export function initTheme() {
  applyTheme(getTheme())
}
