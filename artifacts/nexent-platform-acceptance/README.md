# Nexent 平台侧验收操作清单

> 本目录存放真实 Nexent 平台注册、Skills 导入和一次工具调用的验收证据。
> 协议级验收（`artifacts/nexent-acceptance/latest.json`）不能替代本目录证据。

## 完成判据

1. 在本地 Nexent（或官方托管平台）注册 SeaSight Domain Cognition MCP（`/mcp`）。
2. 导入 `integrations/nexent/skills/` 下 5 个 `SKILL.md`。
3. 由 Nexent 侧发起一次只读 MCP 工具调用，返回成功。
4. 留存界面截图与 JSON 响应并填写 `latest.yaml`（模板见 `latest.yaml.template`）。

## 本地已就绪部分

- MCP Server：Streamable HTTP，`http://127.0.0.1:8100/mcp`（已在监听）。
- 入站鉴权：`SEASIGHT_MCP_SERVER_TOKEN` 已配置，Nexent 请求需带
  `Authorization: Bearer <token>`。
- 出站账号：`nexent_viewer`（viewer 只读角色）已配置，MCP 通过
  `/api/v1/auth/login` 获取并自动刷新令牌。
- 工具面：默认只读 21 个工具；开启写入后共 32 个。平台侧只读验收不需要开启写入。

## 平台侧步骤（需要真实 Nexent 平台）

1. 从华为 ICT 大赛官方材料或赛题说明获取目标 Nexent 平台地址、版本号和可用账号。
2. 登录平台，进入 MCP / 连接管理页。
3. 新建 MCP 连接：
   - 名称：`SeaSight Domain Cognition MCP`
   - 传输：`streamable-http`
   - URL：Nexent 与 MCP 同宿主机时用 `http://host.docker.internal:8100/mcp`；
     跨主机时用受 VPN/防火墙保护的 HTTPS 地址，且 `SEASIGHT_MCP_PUBLIC_URL`
     必须与实际域名一致。
   - Header：`Authorization: Bearer <SEASIGHT_MCP_SERVER_TOKEN>`
4. 确认工具面加载成功，记录实际工具数量。
5. 分别导入 `integrations/nexent/skills/` 下 5 个 `SKILL.md`：
   `policy-evidence-qa`、`marine-event-assessment`、`cross-document-decision`、
   `dispatch-work-order-orchestration`、`decision-trace-audit`。
6. 在 Nexent 内发起一次只读调用（例如 `knowledge_list_assets`），或直接运行
   `policy-evidence-qa` Skill，确认返回成功。
7. 截图：MCP 注册界面、工具面加载界面、Skills 导入完成界面；工具调用
   轨迹可留存 JSON 响应。
8. 复制 `latest.yaml.template` 为 `latest.yaml`，填写实际值；复核人签字。
9. 更新 `docs/competitions/huawei-tech-matrix.md` 和华为参赛材料中
   “待平台侧验收”的状态，并注明“平台侧验收，不是海域验证，不代表感知精度”。

## 口径

平台侧验收只证明 SeaSight MCP 能在该 Nexent 版本上完成注册、Skills 导入和
被调用。它不等于海域部署验证、现场治理效果或任何感知精度证据。

## 复验记录

- `latest.yaml`：2026-09-28 首次本地平台侧验收（登记号 R-NX-02）。
- `recheck-2026-09-29.yaml`：2026-09-29 本地官方源码部署复验（登记号
  R-NX-03），以官方内置 `suadmin@nexent.com` + 租户管理员
  `seasight.acceptance@nexent.com` 登录，由 Nexent 配置服务
  `POST /tool/validate` 读取 DB 中 MCP 注册记录与授权令牌后真实调用
  `knowledge_list_assets` 返回 200。工具轨迹见
  `evidence/recheck-2026-09-29-tool-call.json`。灌入知识域演示数据后再次
  调用同一入口返回非空资产列表，轨迹见
  `evidence/recheck-2026-09-29-with-data.json`（total=4），界面截图见
  `evidence/recheck-2026-09-29-*.png`。
- `agent-create-2026-09-29.yaml`：2026-09-29 Agent 配置证据（登记号
  R-NX-04），在本地官方源码部署中创建并发布
  `seasight-governance-decision-agent`，绑定 5 个 Skill 与 SeaSight
  Domain Cognition MCP 全部 21 个只读工具，发布版本 v2，导出 ZIP，
  `GET /api/agent/call_relationship/1` 返回 21 个 MCP 工具。探针执行记录与
  截图见 `evidence/agent-run-*`。未配置 LLM，未跑通完整问答；这是本地
  官方源码部署证据，不是华为托管平台验收，也不代表海域验证或感知精度。
- `recheck-2026-09-30.yaml`：2026-09-30 本地 MCP 端点复验（登记号
  R-NX-03B），在 `mcp 1.30.0` / 协议 `2025-11-25` 下完成初始化、21 个
  只读工具加载，并真实调用 `knowledge_list_assets`（total=4）、
  `dashboard_get`、`agent_runtime_status`；轨迹见
  `evidence/recheck-2026-09-30/`。本记录只代表**本地 MCP 端点复验**，
  不是华为 AgentArts 托管平台验收，不是完整 Skill 问答，也不代表
  海域验证或感知精度。

### 华为托管平台验收记录（2026-09-29，登记号 R-NX-05）

华为 AgentArts（智果智能体平台，区域 cn-southwest-2）公测申请已于 2026-09-29
审批通过，账号 `hid_b7bcgi-i88yqw0x` 的控制台已解锁。托管平台 MCP 详情页已确认：

- 名称：`SeaSight Domain Cognition MCP`，状态：`部署成功`；
- 工具列表加载 **21 个只读工具**，从 `knowledge_list_assets` 到
  `agent_list_approvals`；界面截图与清洗后 JSON 见
  `evidence/hosted-2026-09-29-mcp-tools-21.png` 与
  `evidence/hosted-2026-09-29-mcp-tools-21.json`；
- 对同一公网 MCP 端点（`https://layout-louise-islands-biblical.trycloudflare.com/mcp`）
  用 MCP 客户端完成 initialize → tools/list → `knowledge_list_assets` 真实只读
  调用，返回 200、total=4、非空资产列表，轨迹见
  `evidence/hosted-2026-09-29-tunnel-tools.json` 与
  `evidence/hosted-2026-09-29-tool-call.json`；
- 结构化验收记录见 `hosted-2026-09-29.yaml`。

如实边界：托管控制台的“调试”按钮未观察到调用输出；托管平台（AgentArts）Skill 页面暂无数据，需
用户在控制台手动完成（源目录为 `integrations/nexent/skills/` 下 5 个
`SKILL.md`）。本记录只证明华为托管平台完成 MCP 注册、工具面加载，并可由公网
端点真实调用；**不是海域部署验证，不代表感知精度**。

### 华为托管平台 Agent 创建记录（2026-09-29，登记号 R-NX-06）

华为 AgentArts 已创建 Agent `seasight-governance-decision-agent`（ID
`fdeccb8f-c35e-459b-8413-26f72a37edf3`），配置
`deepseek-provider/deepseek-chat` 模型，写入诚实系统提示词（只许基于知识库
作答、资产版本级引用、证据不足标 `not_evaluated`、不得把时序误报抑制率当
识别精度）。控制台编辑页明确提示公网环境不支持 Skill（Skill 绑定按钮
disabled，环境 `environment-ypflemxw` 标注公网访问），结构化记录见
`hosted-agent-2026-09-29.yaml`。

如实边界：本记录仅证明 Agent 创建、模型配置与公网环境 Skill 限制；完整
Skill 问答需私网环境 + 私网可访问 MCP endpoint 后验收。**不是海域部署验证，
不代表感知精度，也不代表托管平台已跑通完整 Skill 问答。**

以上记录中，R-NX-02/R-NX-03/R-NX-03B/R-NX-04 代表**本地部署或本地 MCP
端点复验**，R-NX-05 代表**华为托管平台（AgentArts）MCP 注册与公网端点
调用**，R-NX-06 代表**华为托管平台 Agent 创建与模型配置**；均不等于
海域验证或感知精度。

### 华为托管平台完整 Skill 问答（2026-09-30，登记号 R-NX-07：blocked）

2026-09-30 复核华为 AgentArts（区域 `cn-southwest-2`，账号
`hid_b7bcgi-i88yqw0x`）：Agent
`seasight-governance-decision-agent`、MCP `SeaSight Domain Cognition MCP`
（21 个只读工具）与 5 个 Skill 均已就绪，并新建了私网环境
`environment-seasight-vpc-verify`（ID
`8be4cf0c-1de3-46f9-a5cd-90224ca0a378`）与网关 `seasight-vpc-gateway`
（ID `0fe1d7fc-776f-4292-bbc9-5b3b885d1423`）。

**阻断原因**：华为云账号欠费（控制台提示“您的账号已欠费，无法正常购买和
使用按需计费云服务”），私网网关“创建 Target”按钮为原生 disabled，当前
Target 数 `0/10`。因此私网 Target 未建立、未与 Agent 绑定，Agent 启用 VPC
网络模式时报 `AgentArts.03002206`（“配置 skill 时需要开启 VPC 网络模式”）。
该错误码当前根因是 Target 未绑定，不是代码或协议失败。结构化记录与截图见
`hosted-2026-09-30-target-blocked.yaml` 与
`evidence/hosted-2026-09-30-private-gateway-target-blocked.png`。

**如实边界**：托管平台完整 Skill 问答尚未跑通，`live_skill_qa_completed: false`，
不得写成“托管平台已验收”。`127.0.0.1` 与已失效的临时隧道均不能被华为云
端访问，MCP 服务端 Token 属敏感数据，写入第三方平台前需用户明确确认范围。

**充值解除欠费后的五步**：

1. 重新进入私网环境与网关页面，确认“创建 Target”恢复可用。
2. 创建 Target，并把私网可访问的 SeaSight MCP endpoint 配为网络目标。
3. 确认该 endpoint 可由华为云端环境实际访问（不得用 `127.0.0.1` 或临时隧道）。
4. 将 Target 绑定到 `seasight-governance-decision-agent`，启用 VPC 网络模式。
5. 保存并发布 Agent 新版本，运行一次完整 Skill 问答，保存平台内截图与调用轨迹。
