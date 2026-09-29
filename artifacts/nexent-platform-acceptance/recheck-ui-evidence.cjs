const path = require("path");
const { chromium } = require(
  "C:/Users/Liii/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core"
);
const OUT_DIR = path.join(__dirname, "evidence");
const BASE_URL = "http://localhost:3000";
const SU_PASSWORD = process.env.NEXENT_SU_PASSWORD || "";
const TA_PASSWORD = process.env.NEXENT_TENANT_PASSWORD || "";
const STAMP = "recheck-2026-09-29";

async function main() {
  if (!SU_PASSWORD) throw new Error("NEXENT_SU_PASSWORD is required");
  if (!TA_PASSWORD) throw new Error("NEXENT_TENANT_PASSWORD is required");
  const b = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--no-sandbox"],
  });

  const ctxSu = await b.newContext({
    baseURL: BASE_URL,
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
  });
  const suLogin = await ctxSu.request.post("/api/user/signin", {
    data: { email: "suadmin@nexent.com", password: SU_PASSWORD },
  });
  if (!suLogin.ok()) throw new Error("SU signin: " + suLogin.status());

  const pgSu = await ctxSu.newPage();
  await pgSu.goto("/zh/resource-manage", { waitUntil: "networkidle" });
  await pgSu.getByText("SeaSight Acceptance").first().waitFor({
    state: "visible",
    timeout: 30000,
  });
  await pgSu.getByText("SeaSight Acceptance").first().click();
  await pgSu.waitForTimeout(1500);
  const mcpTab = pgSu.getByRole("tab", { name: "MCP", exact: true }).first();
  await mcpTab.waitFor({ state: "visible", timeout: 20000 });
  await mcpTab.click();
  await pgSu.getByText("SeaSight Domain Cognition MCP").first().waitFor({
    state: "visible",
    timeout: 30000,
  });
  await pgSu.waitForTimeout(1500);
  await pgSu.screenshot({
    path: path.join(OUT_DIR, `${STAMP}-mcp-registered.png`),
    fullPage: false,
  });
  console.log(`saved ${STAMP}-mcp-registered.png`);

  const ctxTa = await b.newContext({
    baseURL: BASE_URL,
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
  });
  const taLogin = await ctxTa.request.post("/api/user/signin", {
    data: {
      email: "seasight.acceptance@nexent.com",
      password: TA_PASSWORD,
    },
  });
  if (!taLogin.ok()) throw new Error("tenant signin: " + taLogin.status());
  const pgTa = await ctxTa.newPage();
  await pgTa.goto("/zh/mcp-space?tab=mine", { waitUntil: "networkidle" });
  await pgTa.waitForTimeout(3000);
  await pgTa.getByText("SeaSight Domain Cognition MCP").first().waitFor({
    state: "visible",
    timeout: 30000,
  });
  await pgTa.locator("button").filter({ hasText: "编辑" }).first().click();
  await pgTa.waitForTimeout(2500);
  await pgTa.locator("button").filter({ hasText: "查看工具" }).first().click();
  await pgTa.waitForTimeout(4000);
  await pgTa.screenshot({
    path: path.join(OUT_DIR, `${STAMP}-mcp-tools-21.png`),
    fullPage: false,
  });
  console.log(`saved ${STAMP}-mcp-tools-21.png`);
  await pgTa.close();
  await ctxTa.close();

  const skillsTab = pgSu.getByRole("tab", { name: "Skills", exact: true }).first();
  await skillsTab.waitFor({ state: "visible", timeout: 20000 });
  await skillsTab.click();
  await pgSu.getByText("policy-evidence-qa").first().waitFor({
    state: "visible",
    timeout: 30000,
  });
  await pgSu.waitForTimeout(1500);
  await pgSu.screenshot({
    path: path.join(OUT_DIR, `${STAMP}-skills-imported.png`),
    fullPage: false,
  });
  console.log(`saved ${STAMP}-skills-imported.png`);

  await pgSu.close();
  await ctxSu.close();
  await b.close();
  console.log("UI_RECHECK_OK");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
