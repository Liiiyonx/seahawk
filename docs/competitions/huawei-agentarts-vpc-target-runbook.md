# 华为 AgentArts 私网 Target 与完整 Skill 问答 Runbook

> 版本：1.0 ｜ 日期：2026-09-30
> 适用登记号：R-NX-07（blocked，历史记录）→ R-NX-08（充值并完成后的新记录）
> 适用赛题：华为 ICT 大赛 创新赛道三
> 上位口径：《docs/evidence-claim-policy.md》《docs/competitions/huawei-ict-track3-compliance.md》
> 配套模板：`artifacts/nexent-platform-acceptance/hosted-skill-qa.template.yaml`

## 一、这份手册解决什么

R-NX-07 已经确认：华为 AgentArts 里的 Agent、MCP、5 个 Skill、私网环境和网关都已存在，但华为云账号欠费使“创建 Target”按钮禁用，私网 Target 数仍为 `0/10`，因此完整 Skill 问答没有跑通。

本手册用于欠费解除后，按固定顺序完成：

```text
充值解除欠费
  → 确认创建 Target 恢复可用
  → 部署华为云 VPC 内可达的 SeaSight MCP endpoint
  → 创建并调测 MCP Target
  → 绑定 Agent 并启用 VPC 网络模式
  → 保存并发布 Agent 新版本
  → 跑一次完整 Skill 问答
  → 采集平台内截图与调用轨迹
  → 登记 R-NX-08
```

本文只描述**平台侧可运行性验收**。它不证明海域现场验证，不证明感知精度，也不把演示数据写成真实脱敏行业数据。

## 二、当前对象与固定参数

| 对象 | 值 |
| --- | --- |
| 区域 | `cn-southwest-2` |
| AgentArts 账号 | `hid_b7bcgi-i88yqw0x` |
| Agent | `seasight-governance-decision-agent` |
| Agent ID | `fdeccb8f-c35e-459b-8413-26f72a37edf3` |
| MCP | `SeaSight Domain Cognition MCP` |
| MCP service ID | `ef30db1926c748fab10f30f86c42e2b8` |
| MCP 工具面 | 21 个只读工具 |
| 私网环境 | `environment-seasight-vpc-verify` |
| 私网环境 ID | `8be4cf0c-1de3-46f9-a5cd-90224ca0a378` |
| 网关 | `seasight-vpc-gateway` |
| 网关 ID | `0fe1d7fc-776f-4292-bbc9-5b3b885d1423` |
| 网关出网网络 | VPC `vpc-seasight`、子网 `subnet-6ccf`、安全组 `default` |
| 当前网关 MCP 版本 | `2025-03-26`（在平台支持范围内） |
| 已导入 Skills | `policy-evidence-qa`、`marine-event-assessment`、`cross-document-decision`、`dispatch-work-order-orchestration`、`decision-trace-audit` |

控制台入口：

- 私网环境列表：<https://console.huaweicloud.com/agentarts/?region=cn-southwest-2#/home/managed-agents/environment>
- Agent 编辑：<https://console.huaweicloud.com/agentarts/?region=cn-southwest-2#/home/managed-agents/agent/edit?id=fdeccb8f-c35e-459b-8413-26f72a37edf3>
- MCP 详情：<https://console.huaweicloud.com/agentarts/?region=cn-southwest-2#/home/agent-center/mcp-service/detail?id=ef30db1926c748fab10f30f86c42e2b8&type=service&resource=custom>

## 三、充值后的第一步：只做健康复核

先不要直接重配 Agent。按下列顺序确认基础设施状态：

1. 进入华为云费用中心，确认不再显示欠费或受限提示；等待状态同步完成。
2. 打开私网环境页面，确认 `environment-seasight-vpc-verify` 和
   `seasight-vpc-gateway` 仍是可用状态。
3. 进入网关详情，确认“创建 Target”按钮已恢复；若仍禁用，先不要继续，记录截图和错误码。
4. 确认 Target 数仍为 `0/10`。若已有历史 Target，先判断是否残留、是否在线，避免重复创建。
5. 确认 Agent 仍绑定 DeepSeek 模型、21 个 MCP 工具和 5 个 Skill。

此步只做复核，不改配置。任何状态与 R-NX-07 不一致的地方都要先截图留证。

## 四、私网 endpoint 方案：先选部署位置，再创建 Target

AgentArts 私网 Target 只能访问华为云 VPC 内实际可达的地址。`127.0.0.1`、用户电脑上的 Docker 地址、已失效的临时公网隧道都不行。

### 方案 A：华为云 ECS + Docker Compose（本次推荐）

在同一个区域、同一个 VPC 中创建一台 ECS，部署 SeaSight 生产栈和 `nexent-mcp` 服务。

适用条件：

- ECS 位于 `vpc-seasight`，最好使用 `subnet-6ccf`；
- MCP 容器监听 8100；
- ECS 安全组只允许 VPC 内的网关来源访问 8100；
- Target 地址为 `http://<ECS 私网 IP>:8100/mcp`；
- 若控制台要求 HTTPS，则不要直接暴露明文端口，改用方案 B。

优点：路径最短，数据不出 VPC，便于现场演示和截图；缺点：需要支付 ECS、磁盘和可能的内网 ELB 费用。

### 方案 B：ECS + 内网 ELB/Nginx + 私网 DNS（需要 HTTPS 时）

在方案 A 前面加一层内网负载均衡或 Nginx，使用平台信任的证书，Target 地址写成：

```text
https://<私网域名>/mcp
```

要求：

- 私网 DNS 在网关可解析；
- 证书链路被平台信任；
- ELB/Nginx 只做转发，不改变 `/mcp` 的请求路径和 `Authorization` 头；
- 不要用跳过证书校验的方式绕过问题。

### 方案 C：CCE 或已有内网服务

如果 SeaSight 已经部署在 CCE、内网服务器或通过云专线/VPN 可达的地址，可以直接复用现有 endpoint，但必须先证明：

1. 从 `vpc-seasight` 内能访问该地址；
2. 路径是 `/mcp`，不是 `/sse`、`/inference/` 或其他路径；
3. 网关能携带 `Authorization: Bearer <token>`；
4. 网络策略、安全组、防火墙均允许目标端口。

### 方案 D：公网隧道（不作为提交验收）

临时 trycloudflare 等隧道只适合早期连通性试验。它不稳定、不可审计，也可能在提交时失效。**不能把通过临时隧道跑通写成华为私网验收**，不能作为 R-NX-08 的 endpoint。

### 方案选择结论

| 场景 | 选择 |
| --- | --- |
| 只是完成一次大赛平台验收 | 方案 A，尽量复用已有 ECS |
| 控制台或网关强制 HTTPS | 方案 B |
| 已有 CCE/内网服务 | 方案 C，先做 VPC 内连通性探测 |
| 只有本地 Docker | 先部署到 VPC 内，不要用方案 D 交差 |

## 五、在 ECS 上部署 MCP endpoint

以下命令在 ECS 的 Linux shell 中执行。仓库路径按实际部署目录替换。

### 5.1 准备环境变量

```bash
cd <seahawk-repo>
python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
```

把生成值写入 `.env.production` 的 `SEASIGHT_MCP_SERVER_TOKEN`。不要提交 `.env.production`，不要把真实令牌发到聊天、文档或截图里。

关键变量：

```dotenv
SEASIGHT_API_BASE_URL=http://backend:8000/api/v1
SEASIGHT_API_USERNAME=nexent_viewer
SEASIGHT_API_PASSWORD=<least-privilege-password>
SEASIGHT_MCP_ALLOW_WRITES=false
SEASIGHT_MCP_SERVER_TOKEN=<at-least-32-random-characters>
SEASIGHT_MCP_PUBLIC_URL=http://<ECS私网IP>:8100/mcp
NEXENT_MCP_BIND_ADDR=0.0.0.0
NEXENT_MCP_PORT=8100
```

说明：

- `SEASIGHT_API_USERNAME/PASSWORD` 是 MCP 到 SeaSight 后端的出站账号，推荐使用专用只读账号 `nexent_viewer`；
- `SEASIGHT_MCP_SERVER_TOKEN` 是 AgentArts 网关到 MCP 的入站令牌，二者不要复用；
- `NEXENT_MCP_BIND_ADDR=0.0.0.0` 只意味着容器绑定私网网卡，真正的外网暴露仍由安全组禁止；
- 如果 ECS 上还部署前端，按实际域名调整 `SEASIGHT_MCP_PUBLIC_URL`。

### 5.2 启动服务

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

至少确认 `backend` 与 `nexent-mcp` 为 healthy/running。若 backend 未健康，先解决
数据库、Redis、EMQX 或依赖容器问题，不要继续创建 Target。

### 5.3 在 ECS 本机验证 MCP

在另一台同一 VPC 的 ECS 或 ECS 本机执行：

```bash
curl -i http://<ECS私网IP>:8100/mcp \
  -H "Authorization: Bearer <SEASIGHT_MCP_SERVER_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"vpc-probe","version":"1.0"}}}'
```

预期不是 `401`、`404` 或连接超时，而是 MCP 初始化响应。若本机 curl 都不通，平台侧一定不通。

### 5.4 安全组规则

在 ECS 安全组中添加入方向规则：

- 协议：TCP；
- 端口：`8100`；
- 来源：优先填写网关所在 VPC/子网 CIDR 或平台文档指定的网关来源；
- 禁止：`0.0.0.0/0` 对公网开放。

如果无法确定网关源地址，先用同 VPC 的临时探测机验证，再从网关连通性测试结果中确认来源；不要为了省事直接开放全网。

## 六、创建并调测 Target

官方文档中的字段含义已经核对，创建时优先按以下配置填写。控制台文案可能随版本微调，**以实际页面字段为准，但不能改变协议、类型和路径语义**。

| 字段 | 填写值 | 说明 |
| --- | --- | --- |
| Target 名称 | `seasight-mcp-vpc-target` | 便于与 MCP 服务区分 |
| 协议 | `MCP` | 不是 REST API |
| Target 类型 | `MCP` | 与本项目 Streamable HTTP MCP 一致 |
| 传输方式 | `Streamable HTTP` | 不要选 SSE |
| MCP 地址 | `http://<ECS私网IP>:8100/mcp` | 若要求 HTTPS 则改为方案 B 的私网域名 |
| MCP 版本 | `2025-03-26` | 与现有网关版本一致；平台支持 2025-03-26 / 2025-06-18 / 2025-11-25 |
| 超时 | 30 秒或平台最大值 | MCP server 默认 30 秒 |
| 出站认证 | `API Key` | 对应 SeaSight MCP 服务端的 Bearer 鉴权 |
| 认证位置 | `标头` / Header | 不要选 Query 或 Body |
| 参数名 | `Authorization` | 若控制台自动带前缀，确认最终请求头为 `Authorization: Bearer ...` |
| 前缀 | `Bearer` | 注意 Bearer 后有一个空格 |
| 密钥值 | `<SEASIGHT_MCP_SERVER_TOKEN>` | 只填服务端入站令牌，不填 SeaSight 后端账号密码 |

创建后：

1. 等待状态先变为“就绪可用”；
2. 点击调测/连通性检测，触发平台探测；
3. 探测成功后状态应变为“在线”；
4. 记录 Target ID、创建时间、状态和探测结果；
5. 截图时遮住密钥值，只保留认证类型、位置和参数名。

### 若页面要求“添加 MCP 服务器”而不是 Target

这是同一件事的不同 UI 文案。关键不变：

- 类型必须归属 MCP；
- 地址必须以 `/mcp` 结尾；
- 必须能携带 `Authorization: Bearer <token>`；
- 不能用 REST API 的 OpenAPI 导入替代 MCP Target。

## 七、绑定 Agent 并启用 VPC 网络模式

Target 在线后再操作 Agent：

1. 打开 Agent 编辑页，确认 Agent ID 为
   `fdeccb8f-c35e-459b-8413-26f72a37edf3`。
2. 在运行环境/网络选择处切换到私网环境
   `environment-seasight-vpc-verify`，启用 VPC 网络模式。
3. 在工具/MCP 配置中确认 `SeaSight Domain Cognition MCP` 已选中，工具面为
   21 个只读工具。
4. 在 Skill 配置中选中已导入的 5 个 Skill。
5. 检查模型仍是 `deepseek-provider/deepseek-chat`，系统提示词仍保留
   “只基于知识库作答、证据不足写 `not_evaluated`、不得把 76% 写成识别精度”的边界。
6. 保存为新版本并发布。记录版本号、发布时间和发布结果截图。

如果启 VPC 网络模式时报 `AgentArts.03002206`，先回到网关确认 Target 是否已在线并已绑定到该 Agent；该错误码在 R-NX-07 中的根因就是 Target 未建立。

## 八、跑完整 Skill 问答

推荐采用 `policy-evidence-qa` 或 `cross-document-decision`，先用一个低风险、只读、可验证的问题：

```text
连江县海漂垃圾治理中，岸基监控发现疑似漏油事件，请按照现有政策给出评估与处置建议，并给出证据链。
```

操作与取证要求：

1. 在平台对话界面输入问题，确认实际触发 Skill，而不是只返回普通模型闲聊。
2. 截图一：问题已发送，界面显示 Skill/Agent 正在执行。
3. 截图二：工具调用轨迹，能看到 MCP 工具名和至少一次 `knowledge_search`、
   `knowledge_list_assets` 或 `knowledge_decision_evidence` 调用。
4. 截图三：最终答案，包含资产版本或引用信息；若证据不足，答案必须明确写
   `not_evaluated`，不能编造精度或现场结论。
5. 截图四：Agent 版本/环境状态，证明运行在私网环境且 Target 在线。
6. 若平台提供任务运行 ID、调用轨迹导出或 JSON 下载，一并保存。
7. 若在 VPC 内可访问该 endpoint，可在 ECS 上运行：

```bash
SEASIGHT_MCP_PUBLIC_URL=http://<ECS私网IP>:8100/mcp \
SEASIGHT_MCP_SERVER_TOKEN=<token> \
python artifacts/nexent-platform-acceptance/hosted_tunnel_acceptance.py \
  --url http://<ECS私网IP>:8100/mcp \
  --evidence-prefix hosted-2026-XX-XX-vpc \
  --acceptance-id R-NX-08
```

这个脚本只补充 endpoint 级 JSON 证据，不能替代平台内 Skill 问答截图。

## 九、证据清单

完成后至少保存：

| 证据 | 文件建议 | 必须说明 |
| --- | --- | --- |
| 欠费解除后的环境/网关状态 | `hosted-vpc-environment-online.png` | 不出现密钥、账号敏感信息 |
| Target 详情 | `hosted-vpc-target-detail.png` | 显示 MCP / Streamable HTTP / `/mcp` / 在线状态 |
| Target 调测结果 | `hosted-vpc-target-probe.png` | 显示探测成功 |
| Agent VPC 环境绑定 | `hosted-vpc-agent-environment.png` | 显示私网环境与 21 工具 |
| Skills 绑定 | `hosted-vpc-agent-skills.png` | 显示 5 个 Skill |
| Agent 发布记录 | `hosted-vpc-agent-publish.png` | 显示新版本号和发布时间 |
| Skill 问答问题 | `hosted-vpc-skill-qa-question.png` | 原始问题 |
| 工具轨迹 | `hosted-vpc-skill-qa-trace.png` | 至少一个 MCP 工具调用 |
| 最终答案与引用 | `hosted-vpc-skill-qa-answer.png` | 引用/证据不足标注 |
| 结构化登记 | `hosted-skill-qa-2026-XX-XX.yaml` | 由模板填写 |
| endpoint JSON（可选） | `hosted-2026-XX-XX-vpc-tunnel-tools.json` 等 | 不写令牌 |

截图和 YAML 中不得出现：

- 真实 `SEASIGHT_MCP_SERVER_TOKEN`；
- SeaSight 后端账号密码；
- 华为云 AK/SK；
- 未脱敏的个人联系方式；
- 把演示数据描述成真实脱敏数据的文字。

## 十、失败排查

| 现象 | 优先检查 | 处理 |
| --- | --- | --- |
| “创建 Target”仍禁用 | 账号是否仍欠费、区域是否正确 | 先解决欠费；确认 `cn-southwest-2`，不要换错区域 |
| Target 创建成功但探测失败 | 安全组、子网路由、地址、路径 | 从同 VPC ECS curl；确认 `/mcp`；放行 TCP 8100 但只限 VPC 来源 |
| `401 Unauthorized` | 入站令牌、认证位置、Bearer 前缀 | 核对 `SEASIGHT_MCP_SERVER_TOKEN`；确认最终请求头是 `Authorization: Bearer <token>` |
| `404` 或 `405` | 路径或传输方式 | 用 `/mcp`；不要填 `/sse`、`/inference/` 或根路径 |
| 连接超时 | ECS 未监听、安全组、VPC 不通 | 检查 `docker compose ps`、`ss -lntp`、私网 IP 和安全组 |
| `AgentArts.03002206` | VPC 网络模式或 Target 绑定 | 先让 Target 在线并绑定 Agent，再启用 VPC；不要只改 Skill |
| 工具数不是 21 | `SEASIGHT_MCP_ALLOW_WRITES` 或服务未重启 | 确认 `false`，重启 `nexent-mcp` 后重新探测 |
| MCP 工具调用失败 | MCP 到后端的出站账号 | 检查 `SEASIGHT_API_BASE_URL`、`nexent_viewer` 账号、后端健康状态 |
| HTTPS 证书错误 | 私网证书链、DNS | 使用平台信任的证书和私网 DNS；不要跳过校验 |
| Agent 发布失败 | 模型、Skill、工具、VPC 配置未保存完整 | 查看页面错误码；逐个确认模型、5 Skill、21 工具和 Target 状态 |

## 十一、完成后要更新什么

R-NX-07 保留为历史阻断记录，不删除、不覆盖。全部跑通后新建 **R-NX-08**：

1. 复制 `hosted-skill-qa.template.yaml` 为
   `artifacts/nexent-platform-acceptance/hosted-skill-qa-2026-XX-XX.yaml`；
2. 填写 Target ID、环境 ID、Agent 版本、问题、工具轨迹、截图路径和
   `live_skill_qa_completed: true`；
3. 更新 `artifacts/nexent-platform-acceptance/README.md` 的复验记录；
4. 更新 `docs/competitions/huawei-ict-track3-submission-checklist.md` 的材料 2/3.3/示例问答章节；
5. 更新 `docs/competitions/huawei-ict-track3-scoring-review.md` 的 2.1、缺口表、行动表、问答口径和变更记录；
6. 重新运行：

```powershell
python scripts/check_claims.py --root .
git diff --check
```

7. 只有平台内完整 Skill 问答确实跑通后，才把评分文档中的
   “托管平台完整 Skill 问答待补”改成“已完成平台侧验收”。

## 十二、诚实边界

完成后可以表述：

> 在华为 AgentArts 私网环境中，SeaSight Domain Cognition MCP 通过 VPC Target 与 Agent 完成绑定，基于 5 个 Skill 和 21 个只读 MCP 工具跑通了一次完整 Skill 问答，并保存了平台内截图与调用轨迹。

不能表述：

- “华为认证”“生产级验收”“商业 SLA”；
- “真实海域验证”“现场治理效果”；
- 不得把 76% 表述为识别准确率，也不得宣称识别精度已提升；
- “真实脱敏行业数据评测已完成”；
- 把演示数据、公网隧道或本地复验写成托管平台验收。

## 十三、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-09-30 | 建立充值后 VPC Target、完整 Skill 问答与 R-NX-08 登记 runbook | WP-15 + liyongxiang |
