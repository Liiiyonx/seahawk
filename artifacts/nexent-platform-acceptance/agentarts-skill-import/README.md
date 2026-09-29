# AgentArts Skill 导入包

> 用途：在华为 AgentArts（智果智能体平台）控制台手动导入 SeaSight 的 5 个
> Nexent Skill 模板。
>
> 边界：本包只证明「Skill 模板已按平台要求打包」。导入完成与否以控制台实际
> 状态和截图为准。平台侧验收不等于海域部署验证，也不代表感知精度或现场治理
> 效果。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `seahawk-agentarts-skills-5.zip` | 批量导入包，内含 5 个 Skill 目录，每目录一个 `SKILL.md` |
| `<skill-name>.zip` | 单个 Skill 导入包，内含 `<skill-name>/SKILL.md` |
| `<skill-name>.SKILL.md` | 原始文件副本，供平台只接受单文件上传时使用 |

批量包解压后的结构：

```text
cross-document-decision/SKILL.md
decision-trace-audit/SKILL.md
dispatch-work-order-orchestration/SKILL.md
marine-event-assessment/SKILL.md
policy-evidence-qa/SKILL.md
```

## 5 个 Skill

| 目录名 | 中文名 | 作用 |
| --- | --- | --- |
| `policy-evidence-qa` | 政策证据问答 | 从已登记的政策/标准资产作答，逐条给出资产版本级引用 |
| `marine-event-assessment` | 事件研判 | 用事件事实 + 治理资产 + 决策证据做可审计研判 |
| `cross-document-decision` | 跨文档决策 | 本体引导的多跳推理，输出逐跳路径与证据缺口 |
| `dispatch-work-order-orchestration` | 工单编排 | 事件→Agent 运行→人工审批→工单核验，执行端可替换 |
| `decision-trace-audit` | 决策轨迹审计 | 校验结论能否由不可变证据与执行步骤复现 |

## 导入步骤

1. 登录 AgentArts，进入 `智能体中心 → Skill 库`。
2. 点右上角「导入」。
3. 优先上传 `seahawk-agentarts-skills-5.zip`；若平台只支持单个上传，则逐个上传
   5 个 `<skill-name>.zip`；若只接受单个文件，则上传 `<skill-name>.SKILL.md`。
4. 导入后核对 5 条记录的 `name` 与 `description` 是否被正确解析。
5. 截图留存 Skill 库列表（应显示 5 条）。

`name` 与 `description` 取自每个 `SKILL.md` 的 YAML front matter，平台解析
失败时才需要手工填写。

## 导入后仍需完成

Skill 导入只是平台侧编排证据的一部分。完整链条还包含：

1. 在 AgentArts 注册 `SeaSight Domain Cognition MCP`（已完成，见
   `../hosted-2026-09-29.yaml`，登记号 R-NX-05）。
2. 创建 Agent，绑定该 MCP 的只读工具与上述 5 个 Skill。
3. 采集一次完整问答截图（问题 → 检索 → 多跳路径 → 带引用回答）。

第 2、3 步需要平台侧配置 LLM；未配置时应在材料中如实写明，不得以工具调用
结果冒充问答能力。

## 维护

源文件位于 `integrations/nexent/skills/`。修改源文件后应重新生成本目录的
打包产物，保持提交件与代码一致。
