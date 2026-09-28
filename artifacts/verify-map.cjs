const { createRequire } = require('node:module')
const { mkdir, readFile, writeFile } = require('node:fs/promises')
const path = require('node:path')

const requireFromHere = createRequire(__filename)
const playwright = requireFromHere(
  'C:\\Users\\Liii\\AppData\\Roaming\\npm\\node_modules\\@playwright\\mcp\\node_modules\\playwright-core',
)
const { chromium } = playwright

const ROOT = path.resolve(__dirname, '..')
const FRONTEND = process.env.SEASIGHT_FRONTEND_URL || 'http://127.0.0.1:5175'
const PUBLIC_BASE = process.env.SEASIGHT_PUBLIC_URL || ''
const BROWSER_PATH =
  process.env.SEASIGHT_BROWSER_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const STATE_PATH = path.join(ROOT, 'artifacts', 'browser-acceptance', 'admin-storage.json')
const OUT_DIR = path.join(ROOT, 'artifacts', 'map-verification')

function overlap(a, b) {
  if (!a || !b) return false
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  )
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const storageState = PUBLIC_BASE
    ? undefined
    : JSON.parse(await readFile(STATE_PATH, 'utf8'))
  if (storageState) {
    storageState.origins = storageState.origins.map((state) => ({
      ...state,
      origin: new URL(FRONTEND).origin,
    }))
  }

  const browser = await chromium.launch({
    headless: true,
    executablePath: BROWSER_PATH,
    args: PUBLIC_BASE ? ['--ignore-certificate-errors'] : [],
  })
  const results = []

  try {
    for (const viewport of [
      { name: 'desktop', width: 1440, height: 900 },
      { name: 'mobile', width: 390, height: 844 },
      { name: 'mobile-narrow', width: 320, height: 568 },
    ]) {
      const context = await browser.newContext({
        viewport,
        storageState,
        ignoreHTTPSErrors: Boolean(PUBLIC_BASE),
      })
      const page = await context.newPage()
      const pageErrors = []
      const consoleErrors = []
      page.on('pageerror', (error) => pageErrors.push(error.message))
      page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
      })

      if (PUBLIC_BASE) {
        await page.goto(`${PUBLIC_BASE}/login`, { waitUntil: 'domcontentloaded' })
        await page.locator('#username').waitFor({ state: 'visible' })
        await page.fill('#username', 'admin')
        await page.fill('#password', 'admin123456')
        await page.locator('.login__btn').click()
        await page.waitForURL('**/dashboard', { timeout: 30000 })
      } else {
        await page.goto(`${FRONTEND}/dashboard`, { waitUntil: 'domcontentloaded' })
      }
      await page.locator('.col-map .offline-map').first().waitFor({ state: 'visible' })
      await page.waitForTimeout(500)

      const chart = page.locator('.col-map')
      const controls = page.locator('.col-map .map-controls')
      const tools = page.locator('.col-map .map-tools')
      const badge = page.locator('.col-map .offline-badge')
      const markers = page.locator('.col-map .offline-map__marker')
      const outline = page.locator('.col-map .offline-map__coast')

      const initialTransform = await outline.evaluate(
        (element) => element.parentElement.getAttribute('transform') || '',
      )
      await page.locator('.col-map .map-controls button[title="放大"]').click()
      const zoomedTransform = await outline.evaluate(
        (element) => element.parentElement.getAttribute('transform') || '',
      )

      const markerCount = await markers.count()
      if (markerCount > 0) {
        await markers.first().click({ force: true })
      }
      const infoVisible = await page.locator('.col-map .offline-info').isVisible()

      const controlBox = await controls.boundingBox()
      const toolsBox = await tools.boundingBox()
      const badgeBox = await badge.boundingBox()
      const screenshot = path.join(OUT_DIR, `${viewport.name}-map.png`)
      await chart.screenshot({ path: screenshot })

      const result = {
        viewport,
        screenshot,
        offline_visible: await page.locator('.col-map .offline-map').isVisible(),
        error_visible: await page.locator('.col-map .map-error').count(),
        outline_path_length: (await outline.getAttribute('d'))?.length || 0,
        marker_count: markerCount,
        marker_info_visible: infoVisible,
        zoom_changed: initialTransform !== zoomedTransform,
        controls_overlap_tools: overlap(controlBox, toolsBox),
        controls_overlap_badge: overlap(controlBox, badgeBox),
        tools_overlap_badge: overlap(toolsBox, badgeBox),
        control_box: controlBox,
        tools_box: toolsBox,
        badge_box: badgeBox,
        page_errors: pageErrors,
        console_errors: consoleErrors,
      }
      results.push(result)
      await context.close()
    }
  } finally {
    await browser.close()
  }

  const reportPath = path.join(OUT_DIR, 'latest.json')
  await writeFile(reportPath, `${JSON.stringify(results, null, 2)}\n`)
  console.log(JSON.stringify(results, null, 2))
  console.log(`Report: ${reportPath}`)
}

main().catch((error) => {
  console.error(error.stack || error)
  process.exitCode = 1
})
