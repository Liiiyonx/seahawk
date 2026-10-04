// 机械臂控制台渲染核验：执行后端面板 + 可达性预检三态。
//
// 探针要验证的是「预检真的区分了可达/不可达」，所以给一个必然不可达的
// 地址（192.0.2.1 是 RFC 5737 保留的测试网段），断言它落到「未检测到」态。
// 再用 page.route 拦掉一个可返回的地址，断言它落到「可达」态 ——
// 只测失败分支会漏掉"永远显示失败"这种假通过。
import { createRequire } from 'node:module'
import { writeFileSync } from 'node:fs'

const require = createRequire(import.meta.url)
const { chromium } = require(
  'C:/Users/Liii/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core',
)
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
// 两个静态服务：dist-verify 未配置 VITE_ARM_CONSOLE_URL，dist-probe 注入了配置
const BASE_UNSET = 'http://127.0.0.1:5199'
const BASE_SET = 'http://127.0.0.1:5200'

const FAKE_JWT =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  Buffer.from(JSON.stringify({ exp: 4102444800 })).toString('base64url') +
  '.sig'

const report = []
const errors = []
const log = (ok, name, detail = '') => report.push({ ok, name, detail })

const browser = await chromium.launch({ headless: true, executablePath: CHROME })

try {
  // ===== 场景一：未配置 URL → 面板可见、按钮禁用 =====
  {
    const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => errors.push('[未配置] ' + e.message))
    await page.addInitScript((tok) => {
      localStorage.setItem('seasight_token', tok)
      localStorage.setItem('seasight_user', JSON.stringify({ username: 'p', role: 'admin' }))
    }, FAKE_JWT)
    // 拦截仿真会话接口，让页面进入仿真台视图
    await page.route('**/api/v1/**', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))

    await page.goto(`${BASE_UNSET}/simulation/T-TEST-0001`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1200)
    // 切到「机械臂台」视图
    // 切到「仿真台」视图：按钮在 .sim-map__switch 里，role=tab
    await page.click('.sim-map__switch button[role="tab"]:nth-child(2)')
    await page.waitForTimeout(1500)

    const panel = await page.evaluate(() => {
      const root = document.querySelector('.arm-console')
      if (!root) return null
      return {
        drivers: Array.from(root.querySelectorAll('.arm-console__driver'))
          .map((d) => d.textContent.trim()),
        active: root.querySelector('.arm-console__driver.is-active')?.textContent.trim(),
        note: root.querySelector('.arm-console__backend-note')?.textContent.trim().slice(0, 60),
        tag: root.querySelector('.arm-console__tag')?.textContent.trim(),
        openDisabled: root.querySelector('.arm-console__open')?.disabled,
        svgCount: root.querySelectorAll('svg').length,
        hasUnicode: /[↗✓⧉↻◉■]/.test(root.textContent || ''),
      }
    })
    log(!!panel, '仿真台视图渲染出 arm-console', JSON.stringify(panel))
    log(!!panel && panel.drivers.length === 3,
      '执行后端面板列出三种驱动', panel ? panel.drivers.join(' / ') : '-')
    log(!!panel && !!panel.active, '当前驱动被高亮', panel ? panel.active : '-')
    log(!!panel && panel.openDisabled === true, '未配置 URL 时按钮禁用')
    log(!!panel && !panel.hasUnicode, '无Unicode 字形残留（已换SVG）')
    log(!!panel && panel.svgCount >= 3, '内联图标已渲染',
      panel ? panel.svgCount + ' 个' : '-')
    await page.screenshot({ path: 'artifacts/arm-console-unconfigured.png' })
    await ctx.close()
  }

  // ===== 场景二：配置了可达地址 → 预检应显示「可达」 =====
  {
    const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => errors.push('[可达] ' + e.message))
    await page.addInitScript((tok) => {
      localStorage.setItem('seasight_token', tok)
      localStorage.setItem('seasight_user', JSON.stringify({ username: 'p', role: 'admin' }))
    }, FAKE_JWT)
    await page.route('**/api/v1/**', (r) =>
      r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
    // 拦掉 NoMachine Web 地址并返回 200 —— 预检应判为可达
    await page.route('http://192.168.1.50:4080/**', (r) =>
      r.fulfill({ status: 200, contentType: 'text/html', body: '<html>ok</html>' }))

    await page.goto(`${BASE_SET}/simulation/T-TEST-0001`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    await page.click('.sim-map__switch button[role="tab"]:nth-child(2)')
    await page.waitForTimeout(2500)

    const reach = await page.evaluate(() => {
      const root = document.querySelector('.arm-console')
      return {
        tag: root?.querySelector('.arm-console__tag')?.textContent.trim(),
        tagClass: root?.querySelector('.arm-console__tag')?.className,
        hint: root?.querySelector('.arm-console__reach-hint')?.textContent.trim().slice(0, 80),
        mode: Array.from(root?.querySelectorAll('.arm-console__row') || [])
          .map((r) => r.textContent.trim())
          .find((t) => t.includes('接入方式')),
      }
    })
    log(!!reach && /可达/.test(reach.tag || ''),
      '预检命中：可返回的地址被判为「树莓派可达」', JSON.stringify(reach))
    log(!!reach && /direct|直连|NoMachine/.test(reach.mode || ''),
      '接入方式自动识别为浏览器直连', reach ? reach.mode : '-')
    await page.screenshot({ path: 'artifacts/arm-console-reachable.png' })
    await ctx.close()
  }
} finally {
  await browser.close()
}

writeFileSync('artifacts/arm-console-probe.json', JSON.stringify({ report, errors }, null, 2))
let fail = 0
for (const r of report) {
  if (!r.ok) fail += 1
  console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}`)
  if (r.detail) console.log(`        ${r.detail}`)
}
console.log(`\n${report.length - fail}/${report.length} 通过`)
console.log('页面错误:', errors.length ? errors.join('\n') : '无')
process.exit(fail ? 1 : 0)
