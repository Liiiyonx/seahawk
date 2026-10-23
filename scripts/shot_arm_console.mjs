#!/usr/bin/env node
/**
 * 抓机械臂控制台（ArmSimConsole）截图，供软著说明书使用。
 *
 * 为什么不用 Playwright：本机没装 playwright-core（既有的
 * ui_responsive_audit.mjs 依赖它，但 node_modules 里没有），而 Node 24 自带
 * 全局 WebSocket，直接用 Chrome 的 DevTools Protocol 就能驱动截图，零依赖。
 *
 * 为什么不走真实页面：/simulation 要后端 + Postgres + Redis + EMQX 整套起来，
 * 而控制台显示的内容全部来自 props。用 arm-shot.html 独立挂载组件即可，
 * 既省掉整套依赖，也不会因后端空数据渲染成空态。
 *
 * 前置：
 *   1. 前端 dev server 在跑（frontend: npm run dev），且能访问 /arm-shot.html
 *   2. Chrome 已安装
 *
 * 用法：
 *   node scripts/shot_arm_console.mjs [目标URL] [输出目录]
 *
 * 产物：
 *   artifacts/arm-console/arm-console.png      控制台默认态（已配置跳转）
 *   artifacts/arm-console/arm-console-nx.png   点击后 nx 协议态（面板变绿）
 */
import { spawn } from 'node:child_process'
import { mkdir, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const CHROME =
  process.env.SEASIGHT_BROWSER_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const CDP_PORT = Number(process.env.ARM_SHOT_CDP_PORT || 9333)
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const TARGET_URL = process.argv[2] || 'http://127.0.0.1:5173/arm-shot.html'
const OUT_DIR = path.resolve(process.argv[3] || path.join(ROOT, 'artifacts', 'arm-console'))
const PROFILE = path.join(OUT_DIR, '_chrome-profile')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class CDP {
  constructor(ws) {
    this.ws = ws
    this.seq = 0
    this.pending = new Map()
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        if (msg.error) reject(new Error(JSON.stringify(msg.error)))
        else resolve(msg.result)
      }
    })
  }

  send(method, params = {}, sessionId) {
    const id = ++this.seq
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }))
    })
  }

  close() {
    try {
      this.ws.close()
    } catch {
      /* 关闭失败无所谓，进程要退了 */
    }
  }
}

async function waitForDevtools() {
  for (let i = 0; i < 100; i += 1) {
    try {
      const r = await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`)
      if (r.ok) return await r.json()
    } catch {
      /* 还没起来，继续等 */
    }
    await sleep(200)
  }
  throw new Error('Chrome DevTools 端口未就绪')
}

/** 轮询等待页面里出现某个选择器，返回它的裁剪矩形。 */
async function waitForElementRect(cdp, session, selector, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const { result } = await cdp.send(
      'Runtime.evaluate',
      {
        expression: `(() => {
          const el = document.querySelector(${JSON.stringify(selector)})
          if (!el) return null
          const r = el.getBoundingClientRect()
          if (!r.width || !r.height) return null
          return { x: r.x, y: r.y + window.scrollY, width: r.width, height: r.height }
        })()`,
        returnByValue: true,
      },
      session,
    )
    if (result?.value) return result.value
    await sleep(250)
  }
  throw new Error(`等不到元素：${selector}`)
}

/**
 * 截取指定矩形区域。
 *
 * ★ scale 只能是 1：设备像素比已经由 Emulation.setDeviceMetricsOverride 的
 *   deviceScaleFactor=2 提供，clip.scale 再乘 2 等于 4 倍 —— 实测出图
 *   4528×6128，既臃肿又会让 Word 里缩放后发虚。两处只能用一处。
 */
async function shoot(cdp, session, rect, outPath, pad = 0) {
  const { data } = await cdp.send(
    'Page.captureScreenshot',
    {
      format: 'png',
      captureBeyondViewport: true,
      clip: {
        x: Math.max(0, rect.x - pad),
        y: Math.max(0, rect.y - pad),
        width: rect.width + pad * 2,
        height: rect.height + pad * 2,
        scale: 1,
      },
    },
    session,
  )
  await writeFile(outPath, Buffer.from(data, 'base64'))
  return outPath
}

/** 取某个选择器的矩形（页面坐标）。 */
async function rectOf(cdp, session, selector) {
  const { result } = await cdp.send('Runtime.evaluate', {
    expression: `(() => {
      const el = document.querySelector(${JSON.stringify(selector)})
      if (!el) return null
      const r = el.getBoundingClientRect()
      return { x: r.x, y: r.y + window.scrollY, width: r.width, height: r.height }
    })()`,
    returnByValue: true,
  }, session)
  return result.value
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  await rm(PROFILE, { recursive: true, force: true })

  const chrome = spawn(
    CHROME,
    [
      '--headless=new',
      `--remote-debugging-port=${CDP_PORT}`,
      `--user-data-dir=${PROFILE}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      '--hide-scrollbars',
      '--window-size=1100,1500',
      'about:blank',
    ],
    { stdio: 'ignore', detached: false },
  )

  let cdp
  try {
    await waitForDevtools()

    const created = await fetch(
      `http://127.0.0.1:${CDP_PORT}/json/new?${encodeURIComponent('about:blank')}`,
      { method: 'PUT' },
    ).then((r) => r.json())

    const ws = new WebSocket(created.webSocketDebuggerUrl)
    await new Promise((resolve, reject) => {
      ws.addEventListener('open', resolve, { once: true })
      ws.addEventListener('error', reject, { once: true })
    })
    cdp = new CDP(ws)

    const { sessionId } = await cdp.send('Target.attachToTarget', {
      targetId: created.id,
      flatten: true,
    })
    await cdp.send('Page.enable', {}, sessionId)
    await cdp.send('Emulation.setDeviceMetricsOverride',
      { width: 1100, height: 1500, deviceScaleFactor: 2, mobile: false }, sessionId)

    await cdp.send('Page.navigate', { url: TARGET_URL }, sessionId)
    await waitForElementRect(cdp, sessionId, '.arm-console')
    await cdp.send('Runtime.evaluate', { expression: 'window.scrollTo(0,0)' }, sessionId)
    await sleep(300)

    const dump = async (label) => {
      const { result } = await cdp.send('Runtime.evaluate', {
        expression: `(() => ({
          tag: document.querySelector('.arm-console__tag')?.innerText || '',
          tagClass: document.querySelector('.arm-console__tag')?.className || '',
          reachClass: document.querySelector('.arm-console__reach-hint')?.className || '',
          target: (document.querySelector('.arm-console')?.innerText || '').split('\\n').slice(0,4).join(' | '),
        }))()`,
        returnByValue: true,
      }, sessionId)
      console.log(`[${label}]`, JSON.stringify(result.value))
    }

    await dump('默认态')

    // ★★ 为什么不拍整面板：模板里 `真机热点 192.168.149.1` 与
    //    `登录账号 ubuntu / hiwonder` 是**硬编码**的（ArmSimConsole.vue 第 70~76 行）。
    //    整面板图会把现场热点地址与登录口令原样印进递交版权中心的公开登记文件 ——
    //    正是本项目自订纪律明令避免的那类问题（verify_copyright_sensitive.py
    //    开头就写着「审查报告 P0-4 是登录页截图里明文显示账号口令」）。
    //    故只拍三个不含凭据的区域：面板上半（接入方式/执行后端/任务上下文）、
    //    头部特写、舵机遥测区。信息量够，且无一处含口令。
    // ★ 裁剪边界以「必须排除的行」为锚点，而不是以「想保留的最后一行为止」。
    //   初版写成「截到『当前工单』行底部」，结果边界正好压在「真机热点」行的
    //   上边缘 —— 差一个像素就把 192.168.149.1 带进公开登记文件。锚在要排除的
    //   那一行的上沿、再退 MARGIN 像素，边界就永远落在两行之间的空白里。
    const GAP = 10
    const panelTop = await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        const root = document.querySelector('.arm-console')
        if (!root) return null
        const rows = [...document.querySelectorAll('.arm-console__row')]
        const EXCLUDE = ['真机热点', '登录账号']
        const stop = rows.find((r) => EXCLUDE.some((k) => r.textContent.includes(k)))
        if (!stop) return null
        const rr = root.getBoundingClientRect()
        const sr = stop.getBoundingClientRect()
        const height = sr.top - rr.top - ${GAP}
        if (height <= 0) return null
        return { x: rr.x, y: rr.y + window.scrollY, width: rr.width, height }
      })()`,
      returnByValue: true,
    }, sessionId)
    if (panelTop.result.value) {
      const rect = panelTop.result.value
      // ★ 自检：把落在裁剪区内的信息行逐条列出来，并断言其中没有凭据行。
      //   靠肉眼看图判断「有没有印上口令」不可靠 —— 图会被缩放、会被裁切，
      //   而这一步是几何判断，可复现。任何一次重抓都自动受检。
      const { result: covered } = await cdp.send('Runtime.evaluate', {
        expression: `(() => {
          const bottom = ${rect.y} + ${rect.height}
          return [...document.querySelectorAll('.arm-console__row')]
            .map((r) => {
              const rr = r.getBoundingClientRect()
              // 用行的中心点判定归属，避免边界像素的 1px 抖动造成误判
              const mid = rr.top + window.scrollY + rr.height / 2
              return { label: r.querySelector('span')?.innerText || '', mid }
            })
            .filter((r) => r.mid > ${rect.y} && r.mid < bottom)
            .map((r) => r.label)
        })()`,
        returnByValue: true,
      }, sessionId)
      const labels = covered.value || []
      console.log('裁剪区内信息行:', JSON.stringify(labels))
      const forbidden = ['真机热点', '登录账号']
      const leaked = labels.filter((l) => forbidden.some((f) => l.includes(f)))
      if (leaked.length) {
        throw new Error(`裁剪区含凭据行：${leaked.join('、')} —— 会印进公开登记文件，必须调整裁剪边界`)
      }
      console.log('凭据行检查: 未纳入 ✓')
      const p1 = await shoot(cdp, sessionId, rect,
        path.join(OUT_DIR, 'arm-console-top.png'), 16)
      console.log('已生成:', p1)
    }

    // 头部特写：标题 + 「nx 协议」绿色标签 + 打开仿真台按钮
    const head = await rectOf(cdp, sessionId, '.arm-console__head')
    if (head) {
      const p2 = await shoot(cdp, sessionId, head, path.join(OUT_DIR, 'arm-console-head.png'), 12)
      console.log('已生成:', p2)
    }

    // 舵机遥测区：逐舵机电压/温度/位置 —— 手册里「真机确实执行了」的硬证据
    const servos = await rectOf(cdp, sessionId, '.arm-console__servos')
    if (servos) {
      const p3 = await shoot(cdp, sessionId, servos, path.join(OUT_DIR, 'arm-console-servos.png'), 16)
      console.log('已生成:', p3)
    }

    // 自检：把带凭据的整面板图删掉，杜绝误用
    const { unlink } = await import('node:fs/promises')
    await unlink(path.join(OUT_DIR, 'arm-console.png')).catch(() => {})
    console.log('已删除含凭据的整面板图 arm-console.png（若存在）')

    // 点「打开仿真台」→ probe() 对 nx:// 返回 ok:null → 提示切到协议唤起排障文案
    await cdp.send('Runtime.evaluate', {
      expression: `document.querySelector('.arm-console__open')?.click()`,
    }, sessionId)
    await sleep(900)
    await dump('点击后')
  } finally {
    cdp?.close()
    chrome.kill()
    // Chrome 对 user-data-dir 的清理是异步的，稍等再删，免得留下锁文件
    await sleep(400)
    await rm(PROFILE, { recursive: true, force: true }).catch(() => {})
  }
}

main().catch((err) => {
  console.error('截图失败:', err.message)
  process.exit(1)
})
