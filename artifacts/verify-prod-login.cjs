const { chromium } = require(
  process.env.PLAYWRIGHT_CORE_PATH ||
    'C:\\Users\\Liii\\AppData\\Roaming\\npm\\node_modules\\@playwright\\mcp\\node_modules\\playwright-core',
)
const { mkdir, writeFile, readFile } = require('node:fs/promises')
const path = require('node:path')

const BASE = process.env.SEASIGHT_PUBLIC_URL || 'https://8.153.151.13/seasight'
const BROWSER_PATH =
  process.env.SEASIGHT_BROWSER_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const OUT_DIR = path.join(__dirname, 'prod-login-verification')
const REPO_ROOT = path.join(__dirname, '..')

// ★ 目标站点用的是自签名证书（浏览器会告警）。Playwright 那边靠
//   `ignoreHTTPSErrors: true` 绕过去了，但 **Node 原生 fetch 不吃这个开关** ——
//   它直接抛 `DEPTH_ZERO_SELF_SIGNED_CERT`。而这个 fetch 在脚本**最后**，
//   一旦抛出，前面所有结果（含账号登录结论）连同 latest.json 一起丢掉。
//   2026-09-27 实测就是「账号全绿，然后整个报告消失」。
//   所以这里显式声明不安全模式，并如实打印出来。
const INSECURE_TLS = process.env.SEASIGHT_STRICT_TLS !== '1'
if (INSECURE_TLS) {
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'
}

// ---------------------------------------------------------------------------
// 演示账号：**从源码派生**，不再手抄一份。
//
// ★ 这里原本硬编码三个账号（admin / operator / viewer），而登录页展示四个
//   （多了 approver）。于是「approver 在生产库里根本不存在，点它只得到 401」
//   这个缺口从未被登录验收覆盖 —— 见 2026-09-27 线上验收报告 P0-5。
//   手抄的清单一定会和产品漂移，所以改成从源码里读：
//     · 登录页 LoginDemoPanel.vue  —— 演示面板一键填入的凭据（用户实际会点的）
//     · bootstrap_demo_users.py    —— 服务端能被创建的账号（权威定义）
// ---------------------------------------------------------------------------
const PANEL_SOURCE = path.join(
  REPO_ROOT, 'frontend', 'src', 'components', 'LoginDemoPanel.vue',
)
const BOOTSTRAP_SOURCE = path.join(
  REPO_ROOT, 'backend', 'scripts', 'bootstrap_demo_users.py',
)

const FALLBACK_ACCOUNTS = [
  { username: 'admin', password: 'admin123456' },
  { username: 'operator', password: 'operator123456' },
  { username: 'approver', password: 'approver123456' },
  { username: 'viewer', password: 'viewer123456' },
]

async function loadAccounts() {
  const notes = []
  let accounts = null

  try {
    const text = await readFile(PANEL_SOURCE, 'utf8')
    const pattern = /username:\s*'([^']+)'\s*,\s*password:\s*'([^']+)'/g
    const found = [...text.matchAll(pattern)].map((m) => ({
      username: m[1],
      password: m[2],
    }))
    if (found.length >= 2) {
      accounts = found
      notes.push(`账号清单来源：LoginDemoPanel.vue（${found.length} 个）`)
    } else {
      notes.push('LoginDemoPanel.vue 里没解析出账号，回落到内置清单')
    }
  } catch (error) {
    notes.push(`读不到 LoginDemoPanel.vue（${error.code || error.message}），回落到内置清单`)
  }

  accounts = accounts || FALLBACK_ACCOUNTS

  // 交叉核对：登录页展示的账号，服务端必须也能创建出来。
  try {
    const text = await readFile(BOOTSTRAP_SOURCE, 'utf8')
    const pattern =
      /DemoAccount\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']/g
    const defined = new Set([...text.matchAll(pattern)].map((m) => m[1]))
    if (defined.size) {
      const missing = accounts
        .map((item) => item.username)
        .filter((name) => !defined.has(name))
      notes.push(
        missing.length
          ? `⚠️ 登录页展示了 bootstrap_demo_users.py 里没有的账号：${missing.join(', ')}`
          : `账号清单与 bootstrap_demo_users.py 一致（${[...defined].join(', ')}）`,
      )
    } else {
      notes.push('bootstrap_demo_users.py 里没解析出账号（解析器可能失效）')
    }
  } catch (error) {
    notes.push(`读不到 bootstrap_demo_users.py（${error.code || error.message}）`)
  }

  if (!accounts.some((item) => item.username === 'approver')) {
    notes.push('⚠️ 清单里没有 approver —— 审批链路的第二自然人无人扮演')
  }

  return { accounts, notes }
}

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'mobile-small', width: 320, height: 568 },
]

async function inspectLayout(page) {
  return page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth
    const visibleControls = [...document.querySelectorAll('button, input')].filter((el) => {
      const style = getComputedStyle(el)
      const rect = el.getBoundingClientRect()
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
    })
    const clippedControls = visibleControls
      .map((el) => {
        const rect = el.getBoundingClientRect()
        return {
          selector: el.id
            ? `#${el.id}`
            : `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`,
          text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 80),
          left: Math.round(rect.left * 10) / 10,
          right: Math.round(rect.right * 10) / 10,
          width: Math.round(rect.width * 10) / 10,
        }
      })
      .filter((item) => item.left < -0.5 || item.right > viewportWidth + 0.5)

    const card = document.querySelector('.login__card')?.getBoundingClientRect()
    return {
      viewport_width: viewportWidth,
      document_client_width: document.documentElement.clientWidth,
      document_scroll_width: document.documentElement.scrollWidth,
      body_scroll_width: document.body.scrollWidth,
      horizontal_overflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1 ||
        document.body.scrollWidth > document.documentElement.clientWidth + 1,
      card: card
        ? {
            left: Math.round(card.left * 10) / 10,
            right: Math.round(card.right * 10) / 10,
            width: Math.round(card.width * 10) / 10,
          }
        : null,
      clipped_controls: clippedControls,
    }
  })
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const { accounts, notes } = await loadAccounts()
  console.log('演示账号清单：')
  for (const note of notes) console.log(`  · ${note}`)
  console.log(`  → ${accounts.map((item) => item.username).join(', ')}`)

  const browser = await chromium.launch({
    executablePath: BROWSER_PATH,
    headless: true,
    args: ['--ignore-certificate-errors'],
  })
  const report = {
    base_url: BASE,
    tls_verification: INSECURE_TLS ? 'skipped（自签名证书，未校验）' : 'strict',
    accounts: accounts.map((item) => item.username),
    account_notes: notes,
    layouts: [],
    logins: [],
    resources: {},
  }
  if (INSECURE_TLS) {
    console.log('TLS：跳过证书校验（自签名证书站点；严格模式用 SEASIGHT_STRICT_TLS=1）')
  }

  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        ignoreHTTPSErrors: true,
      })
      const page = await context.newPage()
      const pageErrors = []
      const consoleErrors = []
      page.on('pageerror', (error) => pageErrors.push(error.message))
      page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
      })

      const response = await page.goto(`${BASE}/login`, {
        waitUntil: 'domcontentloaded',
        timeout: 30000,
      })
      await page.waitForSelector('.login__card')
      await page.waitForTimeout(500)
      const layout = await inspectLayout(page)
      layout.name = viewport.name
      layout.status = response?.status()
      layout.page_errors = pageErrors
      layout.console_errors = consoleErrors
      report.layouts.push(layout)

      const screenshotPath = path.join(OUT_DIR, `${viewport.name}-login.png`)
      await page.screenshot({ path: screenshotPath, fullPage: true })
      layout.screenshot = screenshotPath
      await context.close()
    }

    const fillContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
      ignoreHTTPSErrors: true,
    })
    const fillPage = await fillContext.newPage()
    await fillPage.goto(`${BASE}/login`, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    })
    await fillPage.waitForSelector('.login-demo__item')
    const fillChecks = []
    for (let index = 0; index < accounts.length; index += 1) {
      await fillPage.locator('.login-demo__item').nth(index).click()
      fillChecks.push({
        index,
        username: await fillPage.locator('#username').inputValue(),
        password: await fillPage.locator('#password').inputValue(),
        focused: await fillPage.evaluate(() => document.activeElement?.classList.contains('login__btn')),
      })
    }
    report.fill_checks = fillChecks
    await fillContext.close()

    for (const account of accounts) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        ignoreHTTPSErrors: true,
      })
      const page = await context.newPage()
      const pageErrors = []
      const consoleErrors = []
      page.on('pageerror', (error) => pageErrors.push(error.message))
      page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
      })

      // ★ 每个账号独立隔离：一个账号登不上（比如库里根本没有它）不能让
      //   后面账号的结果一起丢失 —— 那样就只剩「脚本挂了」，看不出到底谁有问题。
      //   线上 P0-5 的 approver 就是登不上；旧版脚本一旦卡住会直接抛出，
      //   整轮验证中止，其余账号的全绿结论也一并作废。
      const loginResult = {
        username: account.username,
        login_status: null,
        final_url: null,
        dashboard_visible: false,
        login_error: null,
        page_errors: pageErrors,
        console_errors: consoleErrors,
      }
      try {
        const response = await page.goto(`${BASE}/login`, {
          waitUntil: 'domcontentloaded',
          timeout: 30000,
        })
        await page.waitForSelector('.login-demo__item')
        const accountIndex = accounts.findIndex((item) => item.username === account.username)
        await page.locator('.login-demo__item').nth(accountIndex).click()
        await page.locator('.login__btn').click()
        await page.waitForURL('**/dashboard', { timeout: 20000 })
        await page.waitForSelector('.dashboard', { timeout: 20000 })
        loginResult.login_status = response?.status()
        loginResult.final_url = page.url()
        loginResult.dashboard_visible = await page.locator('.dashboard').isVisible()
      } catch (error) {
        loginResult.login_error = String(error.message || error).split('\n')[0]
        loginResult.final_url = page.url()
      }
      const screenshotPath = path.join(OUT_DIR, `dashboard-${account.username}.png`)
      await page.screenshot({ path: screenshotPath, fullPage: true })
      loginResult.screenshot = screenshotPath
      report.logins.push(loginResult)
      await context.close()
    }

    // ★ 逐个资源 try/catch：静态资源检查失败只该记一条问题，
    //   不该让整份报告（含上面所有账号的登录结论）一起消失。
    for (const resource of ['favicon.svg', 'apple-touch-icon.png']) {
      try {
        const response = await fetch(`${BASE}/${resource}`, { redirect: 'follow' })
        report.resources[resource] = {
          status: response.status,
          content_type: response.headers.get('content-type'),
        }
      } catch (error) {
        report.resources[resource] = {
          status: null,
          error: String(error.cause?.code || error.message || error).split('\n')[0],
        }
      }
    }
  } finally {
    await browser.close()
  }

  const failures = []
  // ★ 账号清单本身也是验收对象：清单漏人 = 那一类账号**从未被验证过**。
  //   线上 P0-5 就是「清单里没有 approver → 没人发现 approver 登不上」。
  if (!report.accounts.includes('approver')) {
    failures.push('账号清单缺少 approver —— 审批链路没人能演，且该账号不会被验证')
  }
  for (const note of report.account_notes) {
    if (note.startsWith('⚠️')) failures.push(`账号清单：${note}`)
  }
  for (const layout of report.layouts) {
    if (layout.status !== 200) failures.push(`${layout.name}: login status ${layout.status}`)
    if (layout.horizontal_overflow) failures.push(`${layout.name}: horizontal overflow`)
    if (layout.clipped_controls.length) failures.push(`${layout.name}: clipped controls`)
    if (layout.page_errors.length) failures.push(`${layout.name}: page errors`)
  }
  for (const check of report.fill_checks || []) {
    const expected = accounts[check.index]
    if (check.username !== expected.username || check.password !== expected.password) {
      failures.push(`fill ${expected.username}: credentials mismatch`)
    }
    if (!check.focused) failures.push(`fill ${expected.username}: submit button not focused`)
  }
  for (const login of report.logins) {
    if (login.login_error) {
      failures.push(`${login.username}: 登录失败 —— ${login.login_error}`)
      continue
    }
    if (!String(login.final_url || '').includes('/dashboard')) {
      failures.push(`${login.username}: dashboard redirect failed`)
    }
    if (!login.dashboard_visible) failures.push(`${login.username}: dashboard not visible`)
    if (login.page_errors.length) failures.push(`${login.username}: page errors`)
  }
  for (const [name, resource] of Object.entries(report.resources)) {
    if (resource.error) failures.push(`${name}: 请求失败 ${resource.error}`)
    else if (resource.status !== 200) failures.push(`${name}: status ${resource.status}`)
  }
  report.failures = failures
  report.passed = failures.length === 0

  await writeFile(
    path.join(OUT_DIR, 'latest.json'),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8',
  )
  console.log(JSON.stringify(report, null, 2))
  process.exit(failures.length ? 1 : 0)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
