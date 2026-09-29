# 华为 ICT 大赛 创新赛道三 · 提交材料打包清单

> 版本：1.4 ｜ 日期：2026-09-29
> 依据：赛道三初赛/决赛需提交材料清单
> 上位口径：《docs/competitions/huawei-ict-track3-scoring-review.md》（评委自评）、
> 《docs/competitions/huawei-ict-track3-design-doc.md》（开发设计文档底稿）、
> 《docs/competitions/huawei-ict-track3-compliance.md》（官方赛题对照）

## 一、材料总览

| # | 材料 | 要求 | 当前状态 | 下一步 |
| --- | --- | --- | --- | --- |
| 1 | 开发设计文档 Word | 项目概述、整体方案设计、知识图谱构建方案、智能体构建方案、原始数据说明、数据处理说明 | Word 已生成：`项目文档/华为ICT赛道三_开发设计文档.docx` | 排版复核 |
| 2 | Nexent 平台智能体整体设计思路与详细说明 | 模型、工具、知识库、调用关系图、调试迭代经验、示例问答截图 | 六项内容底稿已覆盖；调用关系图/Agent 配置已在本地产物落盘（R-NX-04）；华为托管平台 MCP 注册、21 工具与公网端点调用已登记（R-NX-05）；Agent 创建与 DeepSeek 模型配置已登记（R-NX-06）；示例问答轨迹截图已采集（R-KN-04，本地知识域前端：问题→检索→决策→证据链，2 张截图 + API JSON） | 成册；托管平台 Skills 导入与调试截图待私网环境就绪后完成（公网环境不支持 Skill） |
| 3 | json / 知识库 / MCP 文件说明 | 随设计说明同步提交 | 文件已存在 | 按本文 §三 整理说明 |
| 4 | 答辩 PPT（决赛） | 项目设计、关键代码、知识库扩展、自定义工具、数据处理 | 未启动 | 决赛阶段再做 |
| 5 | 附加分：多行业模板轻量化迁移适配验证 | 至少一个非海洋行业配置跑通 | 已完成 E1 演示级：`artifacts/skill-migration/`（R-MG-01，海洋/医疗/政务三领域，检索命中 3/3） | 决赛补真实行业配置 |
| 6 | 附加分：真实脱敏行业数据集效果评测 | 真实脱敏数据 + 评测结果 | 公开开放数据替代评测已完成（R-OD-01，E1，非真实脱敏） | 真实脱敏数据仍待外部来源；提交材料明确标注替代边界 |

## 二、材料 1：开发设计文档 Word

底稿：`docs/competitions/huawei-ict-track3-design-doc.md`，已覆盖赛题要求六节：

1. 项目概述：项目名称、一句话定位、目标用户、业务痛点、赛题定位；
2. 整体方案设计：总体架构、技术栈、安全与权限边界；
3. 知识图谱构建方案：资产模型、低资源半自动本体构建、持续更新与标准对齐、算法边界；
4. 智能体构建方案：模型信息、工具信息、知识库信息、调用关系图、检索-推理双驱动、Skill 模板、调试迭代经验；
5. 原始数据说明：当前演示数据清单、真实行业数据状态；
6. 数据处理说明：登记、版本化、本体处理、检索与决策。

已转 Word：`项目文档/华为ICT赛道三_开发设计文档.docx`（由
`scripts/build_huawei_track3_docx.py` 生成）。转 Word 时保留诚实口径：
本地平台侧验收与华为托管平台 MCP 注册/公网端点调用不等于托管平台完整 Skill
问答；演示数据不等于真实脱敏行业数据；`not_evaluated` 保持原样。

## 三、材料 3：随附文件说明

### 3.1 MCP 相关

| 文件 | 说明 |
| --- | --- |
| `integrations/nexent/mcp_server/server.py` | SeaSight Domain Cognition MCP 实现 |
| `integrations/nexent/mcp_server/requirements.txt` | MCP 运行依赖 |
| `integrations/nexent/.env.example` | 环境变量模板（不含真实密钥） |
| `integrations/nexent/README.md` | 接入说明、安全边界、工具清单 |
| `artifacts/nexent-mcp-openapi.json` | MCP 接口描述 |

### 3.2 Skills

| 文件 | 说明 |
| --- | --- |
| `integrations/nexent/skills/policy-evidence-qa/SKILL.md` | 政策证据问答 |
| `integrations/nexent/skills/marine-event-assessment/SKILL.md` | 事件研判 |
| `integrations/nexent/skills/cross-document-decision/SKILL.md` | 跨文档决策 |
| `integrations/nexent/skills/dispatch-work-order-orchestration/SKILL.md` | 工单编排 |
| `integrations/nexent/skills/decision-trace-audit/SKILL.md` | 决策轨迹审计 |

### 3.3 知识库与验收证据

| 文件 | 说明 |
| --- | --- |
| `artifacts/evolution-demo/latest.json` | R-KN-01 知识进化闭环完整请求/响应 |
| `artifacts/ontology-eval/latest.json` | R-KN-02 本体候选抽取确定性评测结果 |
| `artifacts/ontology-eval/incremental-latest.json` | R-KN-03 本体全量重抽 vs 增量追加对比（节省 66.8%，E1 相对对比） |
| `artifacts/skill-migration/evidence/latest.json` | R-MG-01 多行业模板轻量化迁移验证（三领域检索命中 3/3） |
| `artifacts/skill-migration/skill-migration-mapping.md` | R-MG-01 模板→领域角色映射与变更点说明 |
| `artifacts/knowledge-qa-trace/latest.json` | R-KN-04 示例问答轨迹 API JSON（问题→检索→决策→证据链；hop=0 直接资产引用，非多跳） |
| `artifacts/knowledge-qa-trace/01-检索结果-本体图检索与引用.png` | R-KN-04 示例问答截图：检索结果与引用 |
| `artifacts/knowledge-qa-trace/02-决策证据链-资产版本引用.png` | R-KN-04 示例问答截图：决策证据链与资产版本引用 |
| `artifacts/open-data-eval/latest.json` | R-OD-01 生态环境部公开开放通知本体抽取评测（E1，非真实脱敏） |
| `artifacts/open-data-eval/corpus/manifest.json` | R-OD-01 公开数据来源清单（来源 URL、SHA256、字数） |
| `artifacts/nexent-platform-acceptance/recheck-2026-09-29.yaml` | R-NX-03 平台侧复验记录 |
| `artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml` | R-NX-04 Agent 配置/发布/调用关系记录 |
| `artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml` | R-NX-05 华为托管平台 MCP 注册、21 工具加载与公网端点调用记录 |
| `artifacts/nexent-platform-acceptance/hosted-agent-2026-09-29.yaml` | R-NX-06 华为托管平台 Agent 创建、DeepSeek 模型配置与公网环境 Skill 限制记录 |
| `artifacts/nexent-platform-acceptance/evidence/recheck-2026-09-29-with-data.json` | 灌数据后工具调用返回 total=4 |
| `artifacts/nexent-platform-acceptance/evidence/recheck-2026-09-29-tool-call.json` | 单次工具调用轨迹 |
| `artifacts/nexent-platform-acceptance/evidence/hosted-2026-09-29-mcp-tools-21.png/json` | 托管平台 MCP 详情页 21 工具清单 |
| `artifacts/nexent-platform-acceptance/evidence/hosted-2026-09-29-tunnel-tools.json` | 公网端点 MCP 初始化与工具列表 |
| `artifacts/nexent-platform-acceptance/evidence/hosted-2026-09-29-tool-call.json` | 公网端点真实只读调用返回 total=4 |
| `artifacts/nexent-platform-acceptance/evidence/agent-run-*.json` | Agent 创建、绑定、发布、版本、调用关系接口真实返回 |
| `artifacts/nexent-platform-acceptance/evidence/agent-run-export.zip` | Agent 配置与绑定 Skills 导出物 |
| `artifacts/nexent-platform-acceptance/evidence/*.png` | MCP 注册、工具面、Skills 导入、审批墙截图 |

随附说明需注明：以上为本地官方源码部署复验证据与华为托管平台（AgentArts）
MCP 注册/公网端点调用证据（R-NX-05，2026-09-29）；托管平台已创建 Agent 并配置 DeepSeek 模型（R-NX-06）；
公网环境不支持 Skill（平台 UI 明确提示），完整 Skill 问答需私网环境 + 私网可访问 MCP endpoint。

### 3.4 标准体系映射

| 文件 | 说明 |
| --- | --- |
| `docs/competitions/standard-code-mapping.md` | `standard_codes` 到规范名称、条款、来源状态的映射表；未取得原文的规范写“待获取真实规范条款” |

## 四、示例问答轨迹截图（材料 2）

当前状态：已采集 R-KN-04（本地知识域前端：问题 → 检索 → 决策 → 证据链，
2 张截图 + API JSON）。该轨迹为 `hop_count=0` 的直接资产引用检索，不表述为
多跳路径问答。华为托管平台已创建 Agent 并配置 DeepSeek 模型（R-NX-06），
但公网环境不支持 Skill（平台 UI 明确提示），托管平台/Nexent 控制台完整
Skill 问答截图需私网环境 + 私网可访问 MCP endpoint 就绪后采集。

目标（Nexent 平台内示例问答）：至少一组“问题 → 检索 → 答案 → 引用”完整
对话截图，运行 `policy-evidence-qa` 或 `cross-document-decision` Skill。

前置条件：

- 本地 Nexent 已注册 SeaSight MCP 并导入 5 个 Skills（见 R-NX-02/R-NX-03）；
- 本地官方源码部署已创建并发布 Agent，绑定 5 个 Skill 与 21 个 MCP 工具
  （见 R-NX-04）；
- 后端已灌入知识域演示数据（total=4）；
- 有可用的只读出站账号 `nexent_viewer`。

采集步骤：

1. 在 Nexent 中打开 `policy-evidence-qa` Skill，输入示例问题；
2. 截图：Skill 调用前界面、检索工具调用轨迹、最终答案与引用；
3. 截图保存到 `artifacts/nexent-platform-acceptance/evidence/qa-*.png`；
4. 把截图路径登记进设计说明文档和本清单；
5. 若本地环境不可用，记录为待办，不写“已采集”。

## 五、打包结构建议

```text
huawei-ict-track3-submission/
  01_开发设计文档.docx
  02_Nexent智能体设计说明.docx
  03_附送文件说明.md
  04_示例问答截图/
    R-KN-04_01-检索结果-本体图检索与引用.png
    R-KN-04_02-决策证据链-资产版本引用.png
    qa-policy-evidence-01.png
    qa-cross-document-01.png
  05_证据包/
    R-KN-01_latest.json
    R-KN-02_ontology-eval.json
    R-KN-03_incremental-eval.json
    R-KN-04_knowledge-qa-trace.json
    R-OD-01_open-data-eval.json
    open-data-eval_corpus_manifest.json
    R-NX-03_recheck.yaml
    R-NX-04_agent-create.yaml
    R-MG-01_skill-migration.json
    evidence/
  06_标准映射表.md
  integrations/nexent/        # MCP 与 Skills 源码
  artifacts/nexent-mcp-openapi.json
```

提交前必须：

- [ ] `python scripts/check_claims.py --root .` 退出码 0；
- [ ] 公开仓库隐私扫描通过（若提交到 GitCode/GitHub）；
- [ ] 材料中不出现未脱敏真实数据、真实联系方式和未公开证据；
- [ ] 托管平台完整 Skill 问答截图若未完成，材料中明确写“托管平台完整
      Skill 问答待私网环境 + 私网可访问 MCP endpoint 就绪后补充”（公网
      环境不支持 Skill）。
- [ ] 公开开放数据替代评测（R-OD-01）在材料中标注“非真实脱敏行业数据”。

## 六、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-09-29 | 建立提交材料打包清单、随附文件说明与截图采集步骤 | WP-15 |
| 2026-09-29 | 登记 R-KN-02 本体评测产物、标准映射表、开发设计文档 Word 路径 | WP-15 |
| 2026-09-29 | 登记 R-NX-04 Agent 配置/发布/调用关系/导出证据，更新材料 2 状态为“缺问答截图” | WP-15 |
| 2026-09-29 | 登记 R-NX-05 华为托管平台 MCP 注册、21 工具加载与公网端点真实只读调用证据 | WP-15 |
| 2026-09-29 | 登记 R-KN-03 增量维护对比、R-MG-01 多行业迁移验证，更新材料 5 状态与打包结构 | WP-15 |
| 2026-09-29 | 登记 R-KN-04 示例问答轨迹（本地知识域前端，hop=0 直接引用，非多跳），更新材料 2 状态与打包结构 | WP-15 + liyongxiang |
| 2026-09-29 | 登记 R-OD-01 公开开放数据替代评测（生态环境部 8 份公开通知，E1，非真实脱敏），更新材料 6 状态 | WP-15 + liyongxiang |
| 2026-09-29 | 登记 R-NX-06 华为托管平台 Agent 创建、DeepSeek 模型配置与公网环境 Skill 限制，更新材料 2/3.3/四/五/提交前检查 | WP-15 + liyongxiang |
