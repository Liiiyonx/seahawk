const path = require("path");
const fs = require("fs");
const { chromium } = require(
  "C:/Users/Liii/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright-core"
);

const BASE = "http://127.0.0.1:5010";
const WEB_BASE = "http://localhost:3000";
const ENV_FILE = "C:/Users/Liii/nexent/deploy/env/.env";
const TA_ENV_FILE = "C:/Users/Liii/nexent/deploy/env/.acceptance-admin.env";
const EVIDENCE_DIR = path.join(__dirname, "evidence");

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
    return value.slice(0, 200).map((v) => redact(v, depth + 1));
  }
  if (typeof value === "object" && depth < 6) {
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

function writeJson(filename, value) {
  const file = path.join(EVIDENCE_DIR, filename);
  fs.writeFileSync(file, JSON.stringify(value, null, 2), "utf8");
  console.log("saved", filename);
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
  return { status: res.status, json, text };
}

function normalizeList(value) {
  if (Array.isArray(value)) return value;
  return (
    value?.remote_mcp_server_list ??
    value?.tools ??
    value?.data ??
    value?.items ??
    value?.skills ??
    []
  );
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

  const mcpListRes = await api("/api/mcp/list", { token });
  const mcpList = normalizeList(mcpListRes.json);
  writeJson("agent-run-mcp-list.json", redact(mcpListRes.json));
  const mcpRecord =
    mcpList.find((m) => m.remote_mcp_server_name === "SeaSight Domain Cognition MCP") ||
    mcpList[0];
  const mcpId = mcpRecord?.mcp_id ?? mcpRecord?.id;
  console.log("MCP_LIST", mcpListRes.status, "id=", mcpId, "name=", mcpRecord?.remote_mcp_server_name);

  const mcpToolsRes = await api(`/api/mcp/tools?mcp_id=${mcpId}`, { token });
  const mcpTools = normalizeList(mcpToolsRes.json);
  writeJson("agent-run-mcp-tools.json", redact(mcpToolsRes.json));
  console.log("MCP_TOOLS", mcpToolsRes.status, "count=", mcpTools.length);

  const scanRes = await api("/api/tool/scan_tool", { token });
  console.log("TOOL_SCAN", scanRes.status);

  const toolCatalogRes = await api("/api/tool/list", { token });
  const toolCatalog = normalizeList(toolCatalogRes.json);
  writeJson("agent-run-tool-catalog.json", redact(toolCatalogRes.json));
  const mcpToolIds = {};
  const selectableMcpTools = [];
  for (const tool of toolCatalog) {
    if (
      tool.source === "mcp" &&
      tool.origin_name &&
      mcpTools.some((t) => t.origin_name === tool.origin_name || t.name === tool.origin_name)
    ) {
      mcpToolIds[tool.origin_name] = tool.tool_id;
      selectableMcpTools.push({
        tool_id: tool.tool_id,
        name: tool.name,
        origin_name: tool.origin_name,
        is_available: tool.is_available,
        is_user_selectable: tool.is_user_selectable,
      });
    }
  }
  console.log("TOOL_CATALOG", toolCatalogRes.status, "count=", toolCatalog.length, "mcpMapped=", selectableMcpTools.length);

  const skillsRes = await api("/api/skills", { token });
  const skills = normalizeList(skillsRes.json);
  writeJson("agent-run-skills.json", redact(skillsRes.json));
  const skillsById = Object.fromEntries(
    skills.map((s) => [s.name, s.skill_id])
  );
  console.log("SKILLS", skillsRes.status, "count=", skills.length);

  const wantedSkills = [
    "policy-evidence-qa",
    "marine-event-assessment",
    "cross-document-decision",
    "dispatch-work-order-orchestration",
    "decision-trace-audit",
  ];
  const enabledSkillIds = wantedSkills
    .map((name) => skillsById[name])
    .filter((id) => id != null);
  const enabledToolIds = Object.values(mcpToolIds);

  const agentBody = {
    agent_id: null,
    name: "seasight-governance-decision-agent",
    display_name: "SeaSight 治理决策智能体",
    description:
      "基于 Nexent 的县域海洋治理决策智能体：政策证据问答、事件研判、跨文档决策、工单编排、决策轨迹审计；通过 SeaSight Domain Cognition MCP 使用只读知识域与运行证据工具面。",
    author: "liyongxiang",
    model_ids: [],
    max_steps: 15,
    is_main_agent: true,
    provide_run_summary: true,
    enable_context_manager: true,
    prompt_template_id: 0,
    prompt_template_name: "system_default",
    duty_prompt:
      "你是 SeaSight 治理决策智能体。优先使用已绑定 MCP 工具检索资产、事件、工单和决策证据；未取得工具结果时明确说明证据缺口，不得虚构政策依据、工单、机器人标识或执行结果。",
    constraint_prompt:
      "只读证据域默认不允许写入；任何派单或审批结论必须保留可追溯的证据链；感知精度未评测（not_evaluated），不得将误报抑制率表述为识别精度。",
    greeting_message:
      "你好，我是 SeaSight 治理决策智能体，可以基于知识资产、事件与工单数据做政策证据问答、事件研判和跨文档决策溯源。",
    example_questions: [
      "某乡镇出现海漂垃圾事件，依据现有台账和治理方案，应给出什么处置建议？",
      "哪些政策条款支持本次跨文档决策？",
      "这条决策证据链是否完整、可复现？",
    ],
    enabled_tool_ids: enabledToolIds,
    enabled_skill_ids: enabledSkillIds,
    skill_instances: enabledSkillIds.map((skill_id) => ({
      skill_id,
      enabled: true,
      config_values: {},
    })),
  };

  const agentListBefore = normalizeList((await api("/api/agent/list", { token })).json);
  const existingAgent = agentListBefore.find(
    (a) => a.name === agentBody.name
  );
  if (existingAgent) {
    agentBody.agent_id = existingAgent.agent_id;
    console.log("EXISTING_AGENT", existingAgent.agent_id);
  }

  const updateRes = await api("/api/agent/update", {
    method: "POST",
    token,
    body: agentBody,
  });
  writeJson("agent-run-update.json", redact(updateRes.json));
  console.log("AGENT_UPDATE", updateRes.status, JSON.stringify(redact(updateRes.json)).slice(0, 1200));
  if (updateRes.status >= 400) {
    console.error("agent update failed, stopping before publish");
    process.exit(2);
  }

  const agentListRes = await api("/api/agent/list", { token });
  const agentList = normalizeList(agentListRes.json);
  writeJson("agent-run-list.json", redact(agentListRes.json));
  const createdAgent =
    agentList.find((a) => a.name === agentBody.name) ||
    agentList.find((a) => a.agent_id === agentBody.agent_id) ||
    agentList[agentList.length - 1];
  const agentId = createdAgent?.agent_id;
  console.log("AGENT_LIST", agentListRes.status, "count=", agentList.length, "agentId=", agentId);
  if (!agentId) throw new Error("created agent not found in list");

  const publishRes = await api(`/api/agent/${agentId}/publish`, {
    method: "POST",
    token,
    body: {
      version_name: "v0.1.0-seasight-governance",
      release_note:
        "SeaSight 治理决策智能体初版：绑定 5 个 Skill 与 SeaSight Domain Cognition MCP 工具面。未配置 LLM 模型，完整问答与示例对话待模型端点接入后补验。",
    },
  });
  writeJson("agent-run-publish.json", redact(publishRes.json));
  console.log("AGENT_PUBLISH", publishRes.status, JSON.stringify(redact(publishRes.json)).slice(0, 1200));

  const versionsRes = await api(`/api/agent/${agentId}/versions`, { token });
  writeJson("agent-run-versions.json", redact(versionsRes.json));
  console.log("AGENT_VERSIONS", versionsRes.status);

  const relationshipRes = await api(`/api/agent/call_relationship/${agentId}`, { token });
  writeJson("agent-run-call-relationship.json", redact(relationshipRes.json));
  console.log("AGENT_CALL_RELATIONSHIP", relationshipRes.status, JSON.stringify(redact(relationshipRes.json)).slice(0, 1200));

  const exportRes = await fetch(`${BASE}/api/agent/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ agent_id: agentId }),
  });
  const exportContentType = exportRes.headers.get("content-type") || "";
  const exportBuffer = Buffer.from(await exportRes.arrayBuffer());
  if (exportContentType.includes("zip")) {
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, "agent-run-export.zip"),
      exportBuffer
    );
    writeJson("agent-run-export-manifest.json", {
      status: exportRes.status,
      content_type: exportContentType,
      bytes: exportBuffer.length,
      agent_id: agentId,
      note: "导出物为 ZIP，含 Agent 配置与绑定 Skills；未配置 LLM，不含模型问答运行记录。",
    });
    console.log("AGENT_EXPORT", exportRes.status, "zip bytes=", exportBuffer.length);
  } else {
    let json;
    try {
      json = JSON.parse(exportBuffer.toString("utf8"));
    } catch {
      json = { raw: exportBuffer.toString("utf8").slice(0, 500) };
    }
    writeJson("agent-run-export.json", redact(json));
    console.log("AGENT_EXPORT", exportRes.status, "json saved");
  }

  writeJson("agent-run-summary.json", {
    date: new Date().toISOString(),
    platform: "local-official-source",
    platform_version: "Nexent v2.6.1",
    operator_accounts: [loginEmail],
    agent_id: agentId,
    agent_name: agentBody.name,
    agent_display_name: agentBody.display_name,
    mcp_id: mcpId,
    mcp_tool_count: mcpTools.length,
    selected_mcp_tool_count: selectableMcpTools.length,
    selected_skill_count: enabledSkillIds.length,
    model_ids: [],
    llm_status: "not_configured",
    published: publishRes.status < 400,
    note: "本地官方源码部署的 Agent 配置、工具/Skill 绑定、发布、调用关系与导出证据；未配置 LLM，未跑通完整问答，非华为托管平台复验，不代表海域验证或感知精度。",
  });

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
  await pg.goto(`/zh/agents?agent_id=${agentId}&from=agent-space&tab=mine`, {
    waitUntil: "networkidle",
  });
  await pg.waitForTimeout(3500);
  await pg.screenshot({
    path: path.join(EVIDENCE_DIR, "agent-run-detail.png"),
    fullPage: false,
  });
  console.log("saved agent-run-detail.png");

  await pg.goto("/zh/agent-space?tab=mine", { waitUntil: "networkidle" });
  await pg.waitForTimeout(3000);
  await pg.screenshot({
    path: path.join(EVIDENCE_DIR, "agent-run-space.png"),
    fullPage: false,
  });
  console.log("saved agent-run-space.png");
  await b.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
