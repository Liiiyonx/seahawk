/*
 * Configure a real LLM on the local official-source Nexent deployment and run a
 * complete Skill Q&A through /api/agent/run, capturing the SSE tool trace.
 *
 * Honesty scope: this is a LOCAL Nexent v2.6.1 (official source deploy) record.
 * It is NOT the Huawei AgentArts hosted-platform acceptance (R-NX-08) and it is
 * not海域验证 or感知精度 evidence.
 *
 * Usage:
 *   $env:DEEPSEEK_API_KEY="<key>"; node artifacts/nexent-platform-acceptance/probe-agent-llm-qa.cjs [--ask-only]
 */
const path = require("path");
const fs = require("fs");

const BASE = "http://127.0.0.1:5010";
const RUNTIME_BASE = "http://127.0.0.1:5014";
const ENV_FILE = "C:/Users/Liii/nexent/deploy/env/.env";
const TA_ENV_FILE = "C:/Users/Liii/nexent/deploy/env/.acceptance-admin.env";
const EVIDENCE_DIR = path.join(__dirname, "evidence", "llm-qa-2026-09-30");
const MODEL_NAME = process.env.SEASIGHT_LLM_MODEL || "deepseek-v4-pro";
// Nexent requires the agent name to be a valid Python identifier (hyphens are
// rejected at run time); the human-facing label lives in display_name.
const AGENT_NAME = "seasight_governance_decision_agent";
const AGENT_DISPLAY_NAME = "SeaSight 治理决策智能体";
// Name used by the first local publish before the Python-identifier fix.
const LEGACY_AGENT_NAME = "seasight-governance-decision-agent";
const QUESTION =
  process.env.SEASIGHT_QA_QUESTION ||
  "连江县海漂垃圾治理中，岸基监控发现疑似漏油事件，请按照现有政策给出评估与处置建议，并给出证据链。";

const ASK_ONLY = process.argv.includes("--ask-only");
// Re-derive the summary from an already-captured agent-run-sse.txt without
// spending another LLM run (useful after editing the parser).
const FROM_SSE = process.argv.includes("--from-sse");

function readEnvValue(file, name) {
  const text = fs.readFileSync(file, "utf8");
  const match = text.match(new RegExp(`^${name}=(.*)$`, "m"));
  return match ? match[1].trim() : "";
}

function redact(value, depth = 0) {
  if (value == null || typeof value === "string" || typeof value === "number") return value;
  if (Array.isArray(value)) return value.slice(0, 500).map((v) => redact(v, depth + 1));
  if (typeof value === "object" && depth < 8) {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = /key|token|secret|password|authorization/i.test(k) ? "<redacted>" : redact(v, depth + 1);
    }
    return out;
  }
  return String(value);
}

function writeJson(filename, value) {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  fs.writeFileSync(path.join(EVIDENCE_DIR, filename), JSON.stringify(value, null, 2), "utf8");
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
    json = { raw: text.slice(0, 2000) };
  }
  return { status: res.status, json, text };
}

// The DB record may still carry the legacy hyphenated name, so resolve by
// identifier first and fall back to the display name.
function resolveAgent(agentList) {
  return (
    agentList.find((a) => a.name === AGENT_NAME) ||
    agentList.find((a) => a.name === LEGACY_AGENT_NAME) ||
    agentList.find((a) => a.display_name === AGENT_DISPLAY_NAME)
  );
}

function normalizeList(value) {
  if (Array.isArray(value)) return value;
  return value?.data ?? value?.items ?? value?.remote_mcp_server_list ?? value?.tools ?? value?.skills ?? [];
}

async function signIn() {
  const suPassword = readEnvValue(ENV_FILE, "NEXENT_SUPER_ADMIN_PASSWORD");
  const taPassword = readEnvValue(TA_ENV_FILE, "NEXENT_TENANT_PASSWORD");
  const email = taPassword ? "seasight.acceptance@nexent.com" : "suadmin@nexent.com";
  const password = taPassword || suPassword;
  const login = await api("/api/user/signin", { method: "POST", body: { email, password } });
  const token = login.json?.data?.session?.access_token;
  if (!token) throw new Error(`signin failed: ${login.status} ${login.text.slice(0, 300)}`);
  console.log("SIGNIN", login.status, email);
  return { token, email };
}

async function ensureModel(token) {
  const listBefore = normalizeList((await api("/api/model/list", { token })).json);
  const existing = listBefore.find((m) => m.model_name === MODEL_NAME);
  if (existing) {
    console.log("MODEL_EXISTS", existing.model_id, existing.model_name);
    return existing;
  }
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) throw new Error("DEEPSEEK_API_KEY not set and no existing model record");
  const created = await api("/api/model/create", {
    method: "POST",
    token,
    body: {
      model_factory: "DeepSeek",
      model_name: MODEL_NAME,
      model_type: "llm",
      api_key: apiKey,
      base_url: "https://api.deepseek.com/v1",
      display_name: `${MODEL_NAME} (SeaSight 验收)`,
      max_tokens: 65536,
      connect_status: "connected",
    },
  });
  console.log("MODEL_CREATE", created.status, created.text.slice(0, 400));
  if (created.status >= 400) throw new Error("model create failed");
  const listAfter = normalizeList((await api("/api/model/list", { token })).json);
  const record = listAfter.find((m) => m.model_name === MODEL_NAME);
  if (!record) throw new Error("created model not found in list");
  console.log("MODEL_READY", record.model_id, record.model_name);
  return record;
}

async function bindModelToAgent(token, modelId) {
  const mcpList = normalizeList((await api("/api/mcp/list", { token })).json);
  const mcpRecord =
    mcpList.find((m) => m.remote_mcp_server_name === "SeaSight Domain Cognition MCP") || mcpList[0];
  const mcpId = mcpRecord?.mcp_id ?? mcpRecord?.id;
  const mcpTools = normalizeList((await api(`/api/mcp/tools?mcp_id=${mcpId}`, { token })).json);
  await api("/api/tool/scan_tool", { token });
  const toolCatalog = normalizeList((await api("/api/tool/list", { token })).json);
  const enabledToolIds = [];
  for (const tool of toolCatalog) {
    if (
      tool.source === "mcp" &&
      tool.origin_name &&
      mcpTools.some((t) => t.origin_name === tool.origin_name || t.name === tool.origin_name)
    ) {
      enabledToolIds.push(tool.tool_id);
    }
  }
  const skills = normalizeList((await api("/api/skills", { token })).json);
  const skillsById = Object.fromEntries(skills.map((s) => [s.name, s.skill_id]));
  const wanted = [
    "policy-evidence-qa",
    "marine-event-assessment",
    "cross-document-decision",
    "dispatch-work-order-orchestration",
    "decision-trace-audit",
  ];
  const enabledSkillIds = wanted.map((n) => skillsById[n]).filter((id) => id != null);
  console.log("BINDINGS", "tools=", enabledToolIds.length, "skills=", enabledSkillIds.length, "mcpTools=", mcpTools.length);

  const agentList = normalizeList((await api("/api/agent/list", { token })).json);
  const existing = resolveAgent(agentList);
  if (!existing) throw new Error(`${AGENT_NAME} not found`);
  const body = {
    agent_id: existing.agent_id,
    name: AGENT_NAME,
    display_name: AGENT_DISPLAY_NAME,
    description:
      "基于 Nexent 的县域海洋治理决策智能体：政策证据问答、事件研判、跨文档决策、工单编排、决策轨迹审计；通过 SeaSight Domain Cognition MCP 使用只读知识域与运行证据工具面。",
    author: "liyongxiang",
    model_ids: [modelId],
    model_id: modelId,
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
  const updated = await api("/api/agent/update", { method: "POST", token, body });
  writeJson("agent-update.json", redact(updated.json));
  console.log("AGENT_UPDATE", updated.status, updated.text.slice(0, 400));
  if (updated.status >= 400) throw new Error("agent update failed");

  const published = await api(`/api/agent/${existing.agent_id}/publish`, {
    method: "POST",
    token,
    body: {
      version_name: "v0.2.0-seasight-governance-llm",
      release_note:
        "接入 DeepSeek LLM 后的完整 Skill 问答版本：5 个 Skill + SeaSight Domain Cognition MCP 只读工具面，用于 Nexent 平台内完整问答验收。",
    },
  });
  writeJson("agent-publish.json", redact(published.json));
  console.log("AGENT_PUBLISH", published.status, published.text.slice(0, 400));
  const versions = await api(`/api/agent/${existing.agent_id}/versions`, { token });
  writeJson("agent-versions.json", redact(versions.json));
  return { agentId: existing.agent_id, mcpId, mcpToolCount: mcpTools.length, enabledToolIds, enabledSkillIds };
}

async function ask(token, agentId, question) {
  const res = await fetch(`${RUNTIME_BASE}/agent/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, Accept: "text/event-stream" },
    body: JSON.stringify({
      query: question,
      agent_id: agentId,
      conversation_id: null,
      is_debug: true,
      history: [],
    }),
  });
  console.log("AGENT_RUN", res.status, res.headers.get("content-type"));
  if (!res.ok) {
    const text = await res.text();
    writeJson("agent-run-error.json", { status: res.status, body: text.slice(0, 4000) });
    throw new Error(`agent run failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const events = [];
  const raw = [];
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    raw.push(chunk);
    buffer += chunk;
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        events.push(JSON.parse(payload));
      } catch {
        events.push({ unparsed: payload.slice(0, 500) });
      }
    }
  }
  fs.writeFileSync(path.join(EVIDENCE_DIR, "agent-run-sse.txt"), raw.join(""), "utf8");
  writeEventFiles(events);
  return { events, raw: raw.join("") };
}

// The thinking / model_output stream fragments dominate the file size, so the
// compacted JSON keeps their counts and drops the bodies; agent-run-sse.txt
// remains the untouched full-fidelity record.
function writeEventFiles(events) {
  const compact = compactEvents(events);
  writeJson("agent-run-events.json", {
    event_type_counts: compact.counts,
    note:
      "model_output_* / *_thinking events are high-volume stream fragments; the full unfiltered stream is in agent-run-sse.txt.",
    events: redact(compact.kept),
  });
  writeJson(
    "agent-run-tools.json",
    redact(compact.kept.filter((e) => e.type === "tool" || e.type === "parse")),
  );
}

// Nexent runtime SSE: `tool` carries tool_name/tool_arguments/tool_call_id,
// `parse` carries the agent-authored code block, `step_count` marks a loop
// step, and `final_answer` (last one wins) carries the user-visible reply.
function compactEvents(events) {
  const counts = {};
  const kept = [];
  for (const e of events) {
    const type = String(e.type || "unknown");
    counts[type] = (counts[type] || 0) + 1;
    if (type.includes("thinking") || type.includes("model_output")) continue;
    kept.push(e);
  }
  return { counts, kept };
}

function summarize(events) {
  const toolCalls = [];
  const agentCodeBlocks = [];
  let finalAnswer = "";
  let stepCount = 0;
  for (const e of events) {
    const type = String(e.type || "");
    if (type === "tool") {
      toolCalls.push({
        tool_name: e.tool_name,
        tool_arguments: e.tool_arguments,
        tool_call_id: e.tool_call_id,
      });
    } else if (type === "parse") {
      agentCodeBlocks.push(String(e.content || "").slice(0, 4000));
    } else if (type === "step_count") {
      stepCount += 1;
    } else if (type === "final_answer") {
      finalAnswer = String(e.content || "");
    }
  }
  const uniqueTools = [...new Set(toolCalls.map((t) => t.tool_name).filter(Boolean))];
  return {
    step_count: stepCount,
    tool_calls: toolCalls,
    unique_tools: uniqueTools,
    agent_code_blocks: agentCodeBlocks,
    run_error: finalAnswer.startsWith("Run Agent Error") ? finalAnswer : null,
    final_answer: finalAnswer,
  };
}

function readEventsFromSseFile() {
  const text = fs.readFileSync(path.join(EVIDENCE_DIR, "agent-run-sse.txt"), "utf8");
  const events = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      events.push(JSON.parse(payload));
    } catch {
      events.push({ unparsed: payload.slice(0, 500) });
    }
  }
  return events;
}

function writeSummary({ events, summary, email, agentId, model }) {
  writeJson("agent-run-summary.json", {
    date: new Date().toISOString(),
    platform: "local-official-source",
    platform_version: "Nexent v2.6.1",
    operator_accounts: email ? [email] : [],
    agent_id: agentId,
    agent_name: AGENT_NAME,
    agent_display_name: AGENT_DISPLAY_NAME,
    model: MODEL_NAME,
    model_id: model.model_id,
    question: QUESTION,
    conversation_id: null,
    conversation_id_note:
      "本地 Nexent runtime 的 /agent/run (is_debug=true) SSE 未返回 conversation_id 字段。",
    event_type_counts: compactEvents(events).counts,
    event_count: events.length,
    step_count: summary.step_count,
    tool_call_count: summary.tool_calls.length,
    tool_calls: summary.tool_calls,
    unique_tools: summary.unique_tools,
    agent_code_blocks: summary.agent_code_blocks,
    run_error: summary.run_error,
    final_answer: summary.final_answer,
    note:
      "本地官方源码部署 Nexent 内的完整 Skill 问答：真实 LLM + MCP 工具调用轨迹。非华为 AgentArts 托管平台验收，非海域验证，非感知精度。",
  });
  console.log(
    "QA_DONE",
    "events=", events.length,
    "steps=", summary.step_count,
    "tool_calls=", summary.tool_calls.length,
    "tools=", summary.unique_tools.join(","),
    "run_error=", summary.run_error ? "YES" : "no"
  );
  console.log("ANSWER:", summary.final_answer.slice(0, 600));
}

async function main() {
  if (FROM_SSE) {
    const events = readEventsFromSseFile();
    console.log("FROM_SSE", "events=", events.length);
    writeEventFiles(events);
    writeSummary({
      events,
      summary: summarize(events),
      // The capture run was executed with this tenant admin account.
      email: process.env.SEASIGHT_OPERATOR || "seasight.acceptance@nexent.com",
      agentId: Number(process.env.SEASIGHT_AGENT_ID || 1),
      model: { model_id: Number(process.env.SEASIGHT_MODEL_ID || 1) },
    });
    return;
  }
  const { token, email } = await signIn();
  const model = await ensureModel(token);
  let agentId;
  if (!ASK_ONLY) {
    const binding = await bindModelToAgent(token, model.model_id);
    agentId = binding.agentId;
  } else {
    const agentList = normalizeList((await api("/api/agent/list", { token })).json);
    agentId = resolveAgent(agentList)?.agent_id;
  }
  const { events } = await ask(token, agentId, QUESTION);
  writeSummary({ events, summary: summarize(events), email, agentId, model });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
