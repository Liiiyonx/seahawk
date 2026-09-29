/**
 * Provision the SeaSight Acceptance tenant with a tenant admin, the SeaSight
 * Domain Cognition MCP, and the five custom Skills.
 *
 * Run with:
 *   node _setup-acceptance-tenant.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..", "..");
const BASE = process.env.NEXENT_API_URL || "http://127.0.0.1:5010";
const SU_EMAIL = "suadmin@nexent.com";
const SU_PASSWORD = process.env.NEXENT_SU_PASSWORD || "";
const TENANT_ID = "c75733f1-25ad-4cb5-ac7d-2504bf815051";
const ADMIN_EMAIL = "seasight.acceptance@nexent.com";
const ADMIN_PASSWORD = process.env.NEXENT_ADMIN_PASSWORD || "";
const INVITE_CODE = "SEASIGHT-ACCEPTANCE-2026";
const MCP_NAME = "SeaSight Domain Cognition MCP";
const MCP_URL = "http://host.docker.internal:8100/mcp";
const MCP_TOKEN = "Bearer <MCP_TOKEN>";
const SKILL_NAMES = [
  "policy-evidence-qa",
  "marine-event-assessment",
  "cross-document-decision",
  "dispatch-work-order-orchestration",
  "decision-trace-audit",
];

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
    throw new Error(`${method} ${pathname} -> ${res.status} non-JSON: ${text}`);
  }
  if (!res.ok) {
    throw new Error(`${method} ${pathname} -> ${res.status}: ${JSON.stringify(json)}`);
  }
  return json;
}

async function main() {
  if (!SU_PASSWORD) throw new Error("NEXENT_SU_PASSWORD is required");
  if (!ADMIN_PASSWORD) throw new Error("NEXENT_ADMIN_PASSWORD is required");
  const suLogin = await api("/api/user/signin", {
    method: "POST",
    body: { email: SU_EMAIL, password: SU_PASSWORD },
  });
  const suToken = suLogin.data.session.access_token;
  console.log("SU_LOGIN_OK", suLogin.data.user.email);

  const tenantList = await api("/api/tenants/tenant-list", {
    method: "POST",
    token: suToken,
    body: { page: 1, page_size: 50 },
  });
  const target = tenantList.data.find((t) => t.tenant_id === TENANT_ID);
  if (!target) {
    throw new Error(`Tenant ${TENANT_ID} not found`);
  }
  console.log("TENANT_FOUND", target.tenant_name, target.default_group_id);

  let invite;
  try {
    invite = await api("/api/invitations", {
      method: "POST",
      token: suToken,
      body: {
        tenant_id: TENANT_ID,
        code_type: "ADMIN_INVITE",
        invitation_code: INVITE_CODE,
        capacity: 1,
      },
    });
  } catch (err) {
    if (String(err).includes("already exists")) {
      const invites = await api("/api/invitations/list", {
        method: "POST",
        token: suToken,
        body: { tenant_id: TENANT_ID, page: 1, page_size: 50 },
      });
      const existing = invites.data.items.find(
        (i) => i.invitation_code === INVITE_CODE
      );
      if (!existing) throw err;
      invite = { data: existing };
    } else {
      throw err;
    }
  }
  console.log("INVITE_OK", invite.data.invitation_code, invite.data.code_type);

  try {
    const signup = await api("/api/user/signup", {
      method: "POST",
      body: {
        email: ADMIN_EMAIL,
        password: ADMIN_PASSWORD,
        invite_code: INVITE_CODE,
        auto_login: true,
      },
    });
    console.log("ADMIN_SIGNUP_OK", signup.data?.user?.email || ADMIN_EMAIL);
  } catch (err) {
    if (!String(err).includes("EMAIL_ALREADY_EXISTS")) throw err;
    console.log("ADMIN_ALREADY_EXISTS");
  }

  const adminLogin = await api("/api/user/signin", {
    method: "POST",
    body: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  const adminToken = adminLogin.data.session.access_token;
  console.log(
    "ADMIN_LOGIN_OK",
    adminLogin.data.user.email,
    adminLogin.data.user.role
  );

  const userInfo = await api("/api/user/current_user_info", {
    token: adminToken,
  });
  console.log("ADMIN_TENANT_OK", userInfo.data.user.tenant_id);
  if (userInfo.data.user.tenant_id !== TENANT_ID) {
    throw new Error("Admin is not in the SeaSight Acceptance tenant");
  }

  try {
    const mcp = await api("/api/mcp/add", {
      method: "POST",
      token: adminToken,
      body: {
        name: MCP_NAME,
        server_url: MCP_URL,
        description: "SeaSight domain cognition MCP (platform-side read-only acceptance)",
        tags: ["seasight", "marine-governance", "readonly"],
        authorization_token: MCP_TOKEN,
        enabled: true,
        ingroup_permission: "READ_ONLY",
      },
    });
    console.log("MCP_ADD_OK", JSON.stringify(mcp));
  } catch (err) {
    if (!String(err).includes("already exists")) throw err;
    console.log("MCP_ALREADY_EXISTS");
  }

  const skillsDir = path.join(ROOT, "integrations", "nexent", "skills");
  for (const name of SKILL_NAMES) {
    const skillFile = path.join(skillsDir, name, "SKILL.md");
    const raw = fs.readFileSync(skillFile, "utf8");
    const match = raw.match(/^---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---\n/);
    if (!match) throw new Error(`Cannot parse front matter in ${skillFile}`);
    try {
      const skill = await api("/api/skills", {
        method: "POST",
        token: adminToken,
        body: {
          name: match[1],
          description: match[2],
          content: raw.slice(match[0].length),
          source: "custom",
        },
      });
      console.log("SKILL_ADD_OK", skill.name || match[1]);
    } catch (err) {
      if (!String(err).includes("already exists")) throw err;
      console.log("SKILL_ALREADY_EXISTS", name);
    }
  }

  const mcpList = await api(`/api/mcp/list?tenant_id=${TENANT_ID}`, {
    token: adminToken,
  });
  const registered = mcpList.remote_mcp_server_list.filter(
    (m) => m.remote_mcp_server_name === MCP_NAME
  );
  if (registered.length !== 1) {
    throw new Error(`Expected 1 SeaSight MCP in tenant, got ${registered.length}`);
  }
  console.log(
    "MCP_LIST_OK",
    registered[0].remote_mcp_server_name,
    registered[0].registry_json?._toolNames?.length || 0,
    "tools"
  );

  const skillList = await api(`/api/skills?tenant_id=${TENANT_ID}`, {
    token: adminToken,
  });
  const present = SKILL_NAMES.filter((name) =>
    skillList.skills.some((s) => s.name === name)
  );
  if (present.length !== SKILL_NAMES.length) {
    throw new Error(
      `Expected ${SKILL_NAMES.length} skills, got ${present.length}: ${present.join(",")}`
    );
  }
  console.log("SKILLS_LIST_OK", present.join(","));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
