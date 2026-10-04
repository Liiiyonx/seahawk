import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

// API 地址在 src/api/http.js 里读取 import.meta.env.VITE_API_BASE（.env.local 可覆盖）：
// - 微信开发者工具：详情 → 本地设置 → 勾选「不校验合法域名」即可连 localhost
// - 真机 / 体验版：必须是 https 且在 mp.weixin.qq.com 配置过的 request 合法域名
export default defineConfig({
  plugins: [uni()],
})
