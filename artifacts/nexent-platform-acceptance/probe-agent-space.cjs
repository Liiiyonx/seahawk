const path = require("path");
const fs = require("fs");
const { chromium } = require(
  "C:/Users/Liii/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core"
);

const BASE = "http://127.0.0.1:5010";
const WEB_BASE = "http://localhost:3000";
const ENV_FILE = "C:/Users/Liii/nexent/deploy/env/.env";
const TA_ENV_FILE = "C:/Users/Liii/nexent/deploy/env/.acceptance-admin.env";

function readEnvValue(file, name) {
  const text = fs.readFileSync(file, "utf8");
  const match = text.match(new RegExp(`^${name}=(.*)$`, "m"));
  return match ? match[1].trim() : "";
}

function redact(value, depth = 0) {
  if (value == null || typeof value === "string" || typeof value === "number") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.slice(0, 12).map((v) => redact(v, depth + 1));
  }
  if (typeof value === "object" && depth < 4) {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      if (/key|token|secret|password|authorization/i.test(k)) {
        out[k] = "<redacted>";
      } else {
        out[k] = redact(v, depth + 1);
      }
    }
    return out;
  }
  return String(value);
}

async function api(pathname, { method = "GET", token, body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}${pathname}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { raw: text.slice(0, 500) };
  }
  return { status: res.status, json };
}

function summarizeAgents(value) {
  const list = Array.isArray(value) ? value : value?.data ?? value?.items ?? [];
  return list.map((a) => ({
    agent_id: a.agent_id,
    name: a.name,
    display_name: a.display_name,
    is_available: a.is_available,
    is_published: a.is_published,
    current_version_no: a.current_version_no,
    model_names: a.model_names,
    unavailable_reasons: a.unavailable_reasons,
  }));
}

function summarizeModels(value) {
  const list = Array.isArray(value) ? value : value?.data ?? value?.models ?? [];
  return list.map((m) => ({
    model_id: m.model_id ?? m.id,
    name: m.name ?? m.model_name ?? m.display_name,
    display_name: m.display_name,
    model_type: m.model_type,
    is_available: m.is_available,
    is_deep_thinking: m.is_deep_thinking,
    unavailable_reasons: m.unavailable_reasons,
  }));
}

async function main() {
  const suPassword = readEnvValue(ENV_FILE, "NEXENT_SUPER_ADMIN_PASSWORD");
  const taPassword = readEnvValue(TA_ENV_FILE, "NEXENT_TENANT_PASSWORD");
  if (!taPassword && !suPassword) throw new Error("no password found");
  const loginEmail = taPassword
    ? "seasight.acceptance@nexent.com"
    : "suadmin@nexent.com";
  const loginPassword = taPassword || suPassword;

  const login = await api("/api/user/signin", {
    method: "POST",
    body: { email: loginEmail, password: loginPassword },
  });
  console.log("SIGNIN", login.status, loginEmail);
  const token = login.json?.data?.session?.access_token;
  if (!token) throw new Error("no access token");

  for (const [label, pathname, summarizer] of [
    ["AGENTS", "/api/agent/list", summarizeAgents],
    ["PUBLISHED", "/api/agent/published_list", summarizeAgents],
    ["MODEL_LLM", "/api/model/llm_list", summarizeModels],
    ["MODELS", "/api/model/list", summarizeModels],
    ["TOOLS", "/api/tool/list", (v) => {
      const list = Array.isArray(v) ? v : v?.data ?? [];
      return {
        count: list.length,
        names: list
          .map((t) => t.name ?? t.origin_name)
          .filter(Boolean)
          .slice(0, 40),
      };
    }],
    ["SKILLS", "/api/skills", (v) => {
      const list = v?.skills ?? (Array.isArray(v) ? v : []);
      return list.map((s) => ({
        skill_id: s.skill_id,
        name: s.name,
        tool_ids: s.tool_ids,
      }));
    }],
  ]) {
    const res = await api(pathname, { token });
    let value = res.json;
    if (res.json?.data && Object.keys(res.json).length === 1) {
      value = res.json.data;
    }
    const summary = summarizer ? summarizer(value) : redact(value);
    console.log(`--- ${label} ${res.status} ---`);
    console.log(JSON.stringify(summary, null, 2).slice(0, 12000));
  }

  const b = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--no-sandbox"],
  });
  const ctx = await b.newContext({
    baseURL: WEB_BASE,
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
  });
  const pageLogin = await ctx.request.post("/api/user/signin", {
    data: { email: loginEmail, password: loginPassword },
  });
  console.log("WEB_SIGNIN", pageLogin.status());
  const pg = await ctx.newPage();
  await pg.goto("/zh/newchat", { waitUntil: "networkidle" });
  await pg.waitForTimeout(2500);
  const bodyText = await pg.locator("body").innerText();
  console.log("--- NEWCHAT BODY SAMPLE ---");
  console.log(bodyText.slice(0, 5000));
  await pg.screenshot({
    path: path.join(__dirname, "evidence", "probe-newchat.png"),
    fullPage: false,
  });
  console.log("saved probe-newchat.png");
  await b.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
