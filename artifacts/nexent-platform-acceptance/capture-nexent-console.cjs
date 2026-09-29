/*
 * Capture local-Nexent console screenshots as Skill-QA evidence, driving a
 * headless Chrome over the DevTools Protocol (no extra npm dependencies).
 *
 * Usage:
 *   node artifacts/nexent-platform-acceptance/capture-nexent-console.cjs --dump
 *   node artifacts/nexent-platform-acceptance/capture-nexent-console.cjs
 *
 * Scope: LOCAL official-source Nexent console only. Not the Huawei AgentArts
 * hosted-platform acceptance, not海域验证, not感知精度.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const CHROME = process.env.SEASIGHT_CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = Number(process.env.SEASIGHT_CDP_PORT || 9333);
const PROFILE = path.join(os.tmpdir(), "seasight-cdp-profile");
const OUT_DIR = path.join(__dirname, "evidence", "llm-qa-2026-09-30");
const CONSOLE_BASE = process.env.SEASIGHT_CONSOLE || "http://localhost:3000";
const EMAIL = process.env.SEASIGHT_OPERATOR || "seasight.acceptance@nexent.com";
const PASSWORD_FILE = "C:/Users/Liii/nexent/deploy/env/.acceptance-admin.env";
const DUMP_ONLY = process.argv.includes("--dump");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function readEnvValue(file, name) {
  const text = fs.readFileSync(file, "utf8");
  const match = text.match(new RegExp(`^${name}=(.*)$`, "m"));
  return match ? match[1].trim() : "";
}

async function waitForCdp() {
  for (let i = 0; i < 60; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await sleep(500);
  }
  throw new Error("Chrome DevTools endpoint did not come up");
}

class Cdp {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.pending = new Map();
    this.logs = [];
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener("open", () => resolve());
      this.ws.addEventListener("error", (e) => reject(new Error(`ws error: ${e.message || e.type}`)));
    });
    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
      } else if (msg.method === "Runtime.consoleAPICalled") {
        this.logs.push(msg.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
      }
    });
  }

  send(method, params = {}) {
    this.id += 1;
    const id = this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`eval failed: ${JSON.stringify(res.exceptionDetails).slice(0, 600)}`);
    }
    return res.result?.value;
  }

  async goto(url, settleMs = 3500) {
    await this.send("Page.navigate", { url });
    await sleep(settleMs);
  }

  async screenshot(name) {
    const res = await this.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    fs.mkdirSync(OUT_DIR, { recursive: true });
    const file = path.join(OUT_DIR, name);
    fs.writeFileSync(file, Buffer.from(res.data, "base64"));
    console.log("screenshot", name, `${Math.round(res.data.length * 0.75 / 1024)}KB`);
  }
}

// React ignores plain `el.value = x`; go through the native setter + input event.
const FILL_HELPER = `
function fill(el, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}`;

async function openTarget() {
  const res = await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" });
  if (!res.ok) throw new Error(`cannot create target: ${res.status}`);
  const target = await res.json();
  return target.webSocketDebuggerUrl;
}

async function main() {
  const password = readEnvValue(PASSWORD_FILE, "NEXENT_TENANT_PASSWORD");
  if (!password) throw new Error(`no NEXENT_TENANT_PASSWORD in ${PASSWORD_FILE}`);

  fs.mkdirSync(PROFILE, { recursive: true });
  const chrome = spawn(
    CHROME,
    [
      "--headless=new",
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${PROFILE}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-gpu",
      "--hide-scrollbars",
      "--window-size=1680,1050",
      "about:blank",
    ],
    { stdio: "ignore", detached: false },
  );

  try {
    await waitForCdp();
    const cdp = new Cdp(await openTarget());
    await cdp.ready;
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 1680,
      height: 1050,
      deviceScaleFactor: 1,
      mobile: false,
    });

    await cdp.goto(`${CONSOLE_BASE}/zh`, 6000);
    console.log("HOME_TEXT", JSON.stringify(await cdp.eval("document.body.innerText.slice(0, 600)")));

    const inputs = await cdp.eval(`
      JSON.stringify([...document.querySelectorAll("input")].map((el) => ({
        type: el.type, name: el.name, id: el.id, placeholder: el.placeholder,
        autocomplete: el.autocomplete,
      })))`);
    console.log("INPUTS", inputs);

    console.log(
      "BUTTONS",
      await cdp.eval(`JSON.stringify([...document.querySelectorAll("button")].map((b) => (b.innerText || "").trim()).filter(Boolean).slice(0, 40))`),
    );

    if (DUMP_ONLY) {
      await cdp.screenshot("nexent-console-home.png");
      return;
    }

    // Auth is a modal on the homepage, not a standalone route.
    await cdp.eval(`
      (() => {
        const norm = (s) => [...(s || "")].filter((c) => c.trim() !== "").join("");
        const btn = [...document.querySelectorAll("button, a")].find((el) =>
          /^(登录|Login|Signin)$/i.test(norm(el.innerText)));
        if (btn) btn.click();
        return btn ? "opened" : "no-login-button";
      })()`);
    await sleep(2500);
    console.log(
      "MODAL_INPUTS",
      await cdp.eval(`
        JSON.stringify([...document.querySelectorAll("input")].map((el) => ({
          type: el.type, id: el.id, name: el.name, placeholder: el.placeholder,
        })))`),
    );

    const filled = await cdp.eval(`
      (() => {
        ${FILL_HELPER}
        const emailEl = document.getElementById("email");
        const passEl = document.getElementById("password");
        if (!emailEl || !passEl) return "missing inputs";
        fill(emailEl, ${JSON.stringify(EMAIL)});
        fill(passEl, ${JSON.stringify(password)});
        const norm = (s) => [...(s || "")].filter((c) => c.trim() !== "").join("");
        const btn = [...document.querySelectorAll("button")].find((b) =>
          /^(登录|Login|Signin)$/i.test(norm(b.innerText)));
        if (!btn) return "missing button";
        btn.click();
        return "submitted";
      })()`);
    console.log("LOGIN_SUBMIT", filled);
    await sleep(7000);
    console.log("AFTER_LOGIN_URL", await cdp.eval("location.href"));

    await cdp.goto(`${CONSOLE_BASE}/zh/newchat`, 6000);
    await cdp.screenshot("nexent-console-newchat.png");

    const text = await cdp.eval("document.body.innerText.slice(0, 1200)");
    console.log("NEWCHAT_TEXT", JSON.stringify(text));
  } finally {
    chrome.kill();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
