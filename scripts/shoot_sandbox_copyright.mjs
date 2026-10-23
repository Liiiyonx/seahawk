// 沙盘篇（拆分登记 03）说明书截图采集脚本。
//
// 前置：本地演示栈已运行 —— 后端 8010（BACKGROUND_WORKERS_ENABLED=false）
//       + 前端 dev 服务器（默认 5174），演示数据已用
//       deploy/postgres/refresh_demo_data.sql 刷新。
//
// 用法：
//   node scripts/shoot_sandbox_copyright.mjs              # 全部 7 张
//   node scripts/shoot_sandbox_copyright.mjs vessel       # 只拍指定组（调试用）
//
// 采集 7 张（写入 artifacts/ui-responsive/，与旧截图不重名、不覆盖）：
//   1920x1080-sandbox-dashboard.png   大屏全景（3D 沙盘 + 指标 + 事件流）
//   1920x1080-sandbox-vessel.png      船机点选操作卡（打捞机器人）
//   1920x1080-sandbox-tracked.png     履带式滩涂清除车操作卡
//   1920x1080-sandbox-route.png       作业航线与目标点操作卡
//   1920x1080-sandbox-debris.png      海漂垃圾分布图层
//   1920x1080-sandbox-hero.png        三维沙盘全景（全屏）
//   1920x1080-sandbox-simulation.png  仿真推演页（运行态）
//
// 点选机制（实测结论，勿回退到网格盲扫）：
//   · 船体/浮标一律用 Vue 组件实例（dev 模式 __vueParentComponent.setupState）
//     拿 camera + 实体坐标，做 NDC 投影后精确点击 —— 盲扫实测命中不了。
//   · 浮标（约 2~4px）需先放大镜头再邻域密扫；且演示态下船常驻在目标点上，
//     会截胡点击 —— 故航线组需要在仿真推进后（船离目标）拍摄。
//   · 每次截图前清悬停（pointerleave），否则悬停提示卡会残留在画面上。
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(
  'C:/Users/Liii/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core',
)

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.env.SHOT_BASE || 'http://localhost:5174'
const API = process.env.SHOT_API || 'http://127.0.0.1:8010'
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../artifacts/ui-responsive')
const CREDS = { username: process.env.SHOT_USER || 'admin',
                password: process.env.SHOT_PASS || 'admin123456' }

const ONLY = process.argv.slice(2)
const want = (key) => ONLY.length === 0 || ONLY.includes(key)

mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({ headless: true, executablePath: CHROME })
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  locale: 'zh-CN',
  deviceScaleFactor: 1,
})
const page = await ctx.newPage()

const errors = []
page.on('pageerror', (e) => errors.push(String(e.message).slice(0, 160)))
page.on('console', (m) => {
  if (m.type() === 'error') errors.push('[console] ' + m.text().slice(0, 160))
})

const report = []
const shot = async (key, note) => {
  const file = join(OUT, `1920x1080-sandbox-${key}.png`)
  await page.screenshot({ path: file, fullPage: false })
  report.push({ key, note, file })
  console.log(`  ✓ ${key} 已保存${note ? '（' + note + '）' : ''}`)
}

// ---------- 登录 ----------
const loginRes = await page.request.post(`${API}/api/v1/auth/login`, { data: CREDS })
if (!loginRes.ok()) {
  console.error(`✗ 登录失败 ${loginRes.status()}：${await loginRes.text()}`)
  process.exit(1)
}
const loginBody = await loginRes.json()
const TOKEN = loginBody?.data?.access_token
if (!TOKEN) { console.error('✗ 未取到 access_token'); process.exit(1) }
const U = loginBody.data
console.log(`登录成功：${U.full_name || U.username}（${U.role}）`)

async function openDashboard() {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.evaluate(({ t, u }) => {
    localStorage.setItem('seasight_token', t)
    localStorage.setItem('seasight_user', JSON.stringify({ username: u.username, role: u.role }))
    localStorage.setItem('seasight_theme', 'light')
  }, { t: TOKEN, u: U })
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle' })
  await page.waitForSelector('canvas.sandbox-map__canvas', { timeout: 30000 })
  await page.waitForFunction(() => !document.querySelector('.sandbox-map__loading'), null,
    { timeout: 90000 })
  await page.waitForTimeout(2500)
}

// ---------- 页内工具 ----------
async function clearHoverAndCard({ keepCard = false } = {}) {
  await page.evaluate((keepCard) => {
    const canvas = document.querySelector('canvas.sandbox-map__canvas')
    if (canvas) {
      canvas.dispatchEvent(new PointerEvent('pointerleave', { bubbles: true }))
    }
    if (!keepCard) document.querySelector('.sandbox-map__action-close')?.click()
  }, keepCard)
  await page.waitForTimeout(350)
}

async function zoomIn(times = 1) {
  for (let i = 0; i < times; i += 1) {
    await page.click('button[title="放大"]')
    await page.waitForTimeout(700)
  }
}

// 投影：返回 { vessels: [{id,name,x,y}], targets: [{robotId,taskId,phase,x,y}] }
async function projectAll() {
  return await page.evaluate(() => {
    const inst = document.querySelector('.sandbox-map')?.__vueParentComponent
    const st = inst?.setupState
    const cam = st?.camera
    const canvas = document.querySelector('canvas.sandbox-map__canvas')
    if (!cam || !canvas) return { vessels: [], targets: [] }
    const r = canvas.getBoundingClientRect()
    const proj = (p) => {
      const q = p.clone().project(cam)
      return { x: Math.round(r.left + ((q.x + 1) / 2) * r.width),
               y: Math.round(r.top + ((-q.y + 1) / 2) * r.height) }
    }
    const vessels = []
    const vm = st.vesselManager
    if (vm?.vessels) {
      for (const [id, v] of vm.vessels) {
        const g = v.model?.group
        if (!g) continue
        const p = g.position.clone(); p.y += 2
        vessels.push({ id, ...proj(p) })
      }
    }
    const targets = []
    const rm = st.routeManager
    if (rm?.routes) {
      for (const [robotId, route] of rm.routes) {
        if (!route?.targetPos || !route.targetGroup?.visible) continue
        targets.push({ robotId, taskId: route.taskId, phase: route.phase, ...proj(route.targetPos) })
      }
    }
    return { vessels, targets }
  })
}

// 在 (x,y) 邻域密扫点击，读操作卡文本；命中 accept 则停
async function denseClick(x, y, acceptSrc, { radius = 36, step = 4, settle = 2 } = {}) {
  return await page.evaluate(async ({ x, y, acceptSrc, radius, step, settle }) => {
    const accept = new Function('txt', `return (${acceptSrc})(txt)`)
    const canvas = document.querySelector('canvas.sandbox-map__canvas')
    const frame = () => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)))
    const cardEl = () => document.querySelector('.sandbox-map__action')
    const cardText = () => (cardEl()?.innerText || '').replace(/\s+/g, ' ').trim()
    const close = () => document.querySelector('.sandbox-map__action-close')?.click()
    const send = (type, cx, cy) => canvas.dispatchEvent(new PointerEvent(type, {
      clientX: cx, clientY: cy, bubbles: true, cancelable: true,
      pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0,
    }))
    let n = 0
    for (let dy = -radius; dy <= radius; dy += step) {
      for (let dx = -radius; dx <= radius; dx += step) {
        n += 1
        send('pointermove', x + dx, y + dy)
        send('click', x + dx, y + dy)
        for (let i = 0; i < settle; i += 1) await frame()
        const txt = cardText()
        if (txt && accept(txt)) return { ok: true, x: x + dx, y: y + dy, text: txt, scanned: n }
        if (cardEl()) { close(); await frame() }
      }
    }
    return { ok: false, scanned: n }
  }, { x, y, acceptSrc, radius, step, settle })
}

// 精确点选船体（投影 + 小偏移探针）
async function clickVessel(robotId, typeText) {
  const { vessels } = await projectAll()
  const v = vessels.find((x) => x.id === robotId)
  if (!v) return { ok: false, why: `未找到船体 ${robotId}` }
  const res = await page.evaluate(async ({ x, y, acceptSrc }) => {
    const accept = new Function('txt', `return (${acceptSrc})(txt)`)
    const canvas = document.querySelector('canvas.sandbox-map__canvas')
    const frame = () => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)))
    const cardText = () => (document.querySelector('.sandbox-map__action')?.innerText || '').replace(/\s+/g, ' ').trim()
    const send = (type, cx, cy) => canvas.dispatchEvent(new PointerEvent(type, {
      clientX: cx, clientY: cy, bubbles: true, cancelable: true,
      pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0,
    }))
    const tried = []
    for (const dy of [0, 4, -4, 8, -8, 14]) {
      send('pointermove', x, y + dy); send('click', x, y + dy)
      await frame(); await frame()
      const t = cardText()
      tried.push({ dy, t: t.slice(0, 50) })
      if (t && accept(t)) return { ok: true, dy, text: t, tried }
      if (document.querySelector('.sandbox-map__action')) {
        document.querySelector('.sandbox-map__action-close')?.click(); await frame()
      }
    }
    return { ok: false, why: '未命中', tried }
  }, { x: v.x, y: v.y, acceptSrc: `(t) => t.indexOf('类型：${typeText}') >= 0` })
  return { ...res, vessel: v }
}

// ---------- 1) 大屏全景 ----------
if (want('dashboard')) {
  await openDashboard()
  await clearHoverAndCard()
  const probe = await page.evaluate(() => {
    const t = document.body.innerText
    return { chars: t.replace(/\s+/g, '').length,
             emptyHints: (t.match(/暂无|加载失败|服务暂不可用/g) || []).length }
  })
  console.log(`  大屏探测：字符 ${probe.chars} / 空态提示 ${probe.emptyHints}`)
  await shot('dashboard', '大屏全景')
}

if (['vessel', 'tracked', 'route', 'debris', 'hero'].some(want)) {
  if (!want('dashboard')) await openDashboard()

  // ---------- 2) 打捞机器人操作卡（放大 2 档后投影点选）----------
  if (want('vessel')) {
    await clearHoverAndCard()
    await zoomIn(2)
    const res = await clickVessel('RBT-002', '打捞机器人')
    console.log(`  vessel：${JSON.stringify(res).slice(0, 260)}`)
    if (res.ok) { await clearHoverAndCard({ keepCard: true }); await shot('vessel', '船机点选操作卡') }
  }

  // ---------- 3) 履带式滩涂清除车（放大 2 档后投影点选）----------
  if (want('tracked')) {
    await clearHoverAndCard()
    await zoomIn(2)
    let res = await clickVessel('RBT-006', '滩涂清除车')
    if (!res.ok) res = await clickVessel('RBT-004', '滩涂清除车')
    console.log(`  tracked：${JSON.stringify(res).slice(0, 260)}`)
    if (res.ok) { await clearHoverAndCard({ keepCard: true }); await shot('tracked', '履带滩涂车操作卡') }
  }

  // ---------- 4) 航线 / 作业目标点（放大 4 档 + 邻域密扫）----------
  if (want('route')) {
    await clearHoverAndCard()
    await zoomIn(4)
    const { targets } = await projectAll()
    console.log(`  可见航线目标 ${targets.length} 个：${targets.map((t) => `${t.taskId}(${t.phase})`).join(', ')}`)
    const rank = { navigating: 0, collecting: 1, assigned: 2 }
    targets.sort((a, b) => (rank[a.phase] ?? 9) - (rank[b.phase] ?? 9))
    let done = null
    for (const t of targets) {
      const res = await denseClick(t.x, t.y, `(t) => /作业目标点/.test(t) && /关联工单/.test(t)`,
        { radius: 40, step: 3 })
      console.log(`  route ${t.taskId}：${JSON.stringify(res).slice(0, 160)}`)
      if (res.ok) { done = { t, res }; break }
    }
    if (done) {
      await clearHoverAndCard({ keepCard: true })
      await shot('route', `航线目标点（${done.t.taskId}）`)
    }
  }

  // ---------- 5) 海漂垃圾图层 ----------
  if (want('debris')) {
    await clearHoverAndCard()
    const res = await denseClick(
      (await page.evaluate(() => {
        const r = document.querySelector('canvas.sandbox-map__canvas').getBoundingClientRect()
        return { x: Math.round(r.left + r.width * 0.72), y: Math.round(r.top + r.height * 0.3) }
      })).x,
      (await page.evaluate(() => {
        const r = document.querySelector('canvas.sandbox-map__canvas').getBoundingClientRect()
        return { x: Math.round(r.left + r.width * 0.72), y: Math.round(r.top + r.height * 0.3) }
      })).y,
      `(t) => /垃圾/.test(t) && /查看相关事件/.test(t)`, { radius: 200, step: 22 })
    console.log(`  debris：${JSON.stringify(res).slice(0, 200)}`)
    if (res.ok) { await clearHoverAndCard({ keepCard: true }); await shot('debris', '垃圾分布图层') }
  }

  // ---------- 6) 三维沙盘全景（全屏 + 放大 1 档）----------
  if (want('hero')) {
    await clearHoverAndCard()
    await page.click('button[title="回到默认视角"]').catch(() => {})
    await page.waitForTimeout(1200)
    await page.click('button[title="全屏查看"]')
    await page.waitForTimeout(2600)
    await page.click('button[title="放大"]').catch(() => {})
    await page.waitForTimeout(1200)
    await clearHoverAndCard()
    await shot('hero', '三维沙盘全景（全屏）')
  }
}

// ---------- 7) 仿真推演页（运行态）----------
if (want('simulation')) {
  const TASK = process.env.SIM_TASK || 'tsk_demo_1002'
  await page.goto(`${BASE}/simulation/${TASK}`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.sim-controls', { timeout: 30000 })
  await page.waitForTimeout(1500)
  await page.click('.sim-controls__speeds button:nth-child(2)').catch(() => {})
  await page.waitForTimeout(400)
  const startBtn = page.locator('button:has-text("启动")').first()
  if (await startBtn.count()) {
    const disabled = await startBtn.isDisabled().catch(() => true)
    if (!disabled) {
      await startBtn.click()
      console.log('  已点「启动」，等待推演进入作业中…')
    } else {
      console.log('  「启动」不可用（可能已在运行或任务不可仿真），直接等状态…')
    }
  }
  let phase = ''
  for (let i = 0; i < 80; i += 1) {
    await page.waitForTimeout(1500)
    const snap = await page.request.get(`${API}/api/v1/simulations/${TASK}`, {
      headers: { Authorization: `Bearer ${TOKEN}` },
    })
    if (snap.ok()) {
      const d = (await snap.json())?.data || {}
      phase = d.phase || d.state || ''
      if (phase === 'collecting' || phase === 'done') break
    }
  }
  console.log(`  推演相位：${phase || '(未取到)'}`)
  await page.waitForTimeout(1500)
  await shot('simulation', `仿真推演页运行态（${phase}）`)
}

await browser.close()

console.log('')
console.log(`页面错误：${errors.length ? errors.slice(0, 6).join(' | ') : '无'}`)
const ok = report.filter((x) => x.file).length
console.log(`采集完成：${ok} 张`)
for (const r of report) console.log(`  - ${r.file}`)
if (ok < (ONLY.length || 7)) {
  console.log('⚠ 有未采集的项，请检查上方日志')
  process.exitCode = 2
}
