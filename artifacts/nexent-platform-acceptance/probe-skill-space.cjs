const path = require("path");
const { chromium } = require(
  "C:/Users/Liii/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core"
);
const BASE_URL = "http://localhost:3000";
const SU_PASSWORD = process.env.NEXENT_SU_PASSWORD || "";
const TA_PASSWORD = process.env.NEXENT_TENANT_PASSWORD || "";

async function main() {
  const loginEmail = TA_PASSWORD
    ? "seasight.acceptance@nexent.com"
    : "suadmin@nexent.com";
  const loginPassword = TA_PASSWORD || SU_PASSWORD;
  if (!loginPassword) throw new Error("tenant or SU password is required");
  const b = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--no-sandbox"],
  });
  const ctx = await b.newContext({
    baseURL: BASE_URL,
    viewport: { width: 1440, height: 900 },
    locale: "zh-CN",
  });
  const login = await ctx.request.post("/api/user/signin", {
    data: { email: loginEmail, password: loginPassword },
  });
  console.log("signin", login.status(), loginEmail);
  if (!login.ok()) throw new Error("signin failed: " + login.status());

  const pg = await ctx.newPage();
  await pg.goto("/zh/skill-space?tab=mine", { waitUntil: "networkidle" });
  await pg.waitForTimeout(3000);

  const card = pg.getByText("policy-evidence-qa").first();
  await card.waitFor({ state: "visible", timeout: 30000 });
  console.log("found policy-evidence-qa card");

  const cardArticle = card.locator("xpath=ancestor::article[1]");
  const editButton = cardArticle
    .getByRole("button", { name: /编辑/i })
    .first();
  await editButton.waitFor({ state: "visible", timeout: 10000 });
  await editButton.click();
  await pg.waitForTimeout(5000);

  const bodyText = await pg.locator("body").innerText();
  console.log("--- BODY TEXT SAMPLE ---");
  console.log(bodyText.slice(0, 8000));

  await pg.screenshot({
    path: path.join(__dirname, "evidence", "probe-skill-build-modal.png"),
    fullPage: false,
  });
  console.log("saved probe-skill-build-modal.png");
  await b.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
