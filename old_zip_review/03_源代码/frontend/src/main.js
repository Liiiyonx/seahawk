import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './assets/main.css'
import { initTheme } from './utils/theme'

initTheme()

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.mount('#app')

// PWA：仅生产注册 Service Worker（dev 下缓存热更新产物会捣乱）
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {
      /* 注册失败不影响页面本身 —— PWA 是增强项 */
    })
  })
}
