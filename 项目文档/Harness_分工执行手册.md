# 探海灵眸 Harness 分工执行手册

> 版本：1.0  
> 日期：2026-09-18  
> 上位基线：`项目文档/探海灵眸_项目计划书.md`  
> 用途：把总控计划书转换为 DeepSeek Harness 可执行、可验收、可追责的分工任务

## 1. 总控职责

Harness 总控会话负责：

1. 读取并遵守上位计划书和本执行手册。
2. 冻结共享接口，不允许子代理自行改名、改状态或扩张职责。
3. 按波次启动子代理，检查每个子代理的改动边界和测试证据。
4. 汇总冲突，统一修改共享注册文件，完成最终回归。
5. 对没有文件清单、测试结果、边界说明、风险和未完成事项的输出判定为“未完成”。

总控不得用“已完成”替代证据。任何工作包只有同时具备以下材料才算完成：

- 修改文件清单。
- 实际执行命令。
- 原始测试结果。
- 未完成事项和风险。
- 与上位计划书一致的证据等级。

## 2. 全局硬约束

- 工作目录固定为 `C:\Users\Liii\Desktop\seahawk`。
- 所有共享接口以本手册和上位计划书为准，子代理不得自行变更。
- 不允许回滚不属于自己的改动。
- 禁止 `git reset --hard`、`git checkout --` 和其他破坏性回滚。
- 禁止把规划、模拟、合成数据或 MD5 stub 写成真实部署、真实订单、真实海域结果。
- 禁止把 OpenCV 写成 YOLO、视觉大模型或已训练模型。
- 禁止把静态 Agent 目录写成在线智能体协同。
- 未安装依赖时，先证明缺失，再补依赖并复跑测试。
- 每个工作包只能修改其“允许文件”；需要修改共享文件时，向总控提出集成请求。
- 并行子代理不得编辑同一文件。冲突修改必须由总控串行完成。
- 测试不能只跑新增单测。涉及共享行为时，必须追加相应回归测试。
- Windows 控制台统一使用 UTF-8 输出；子进程显式设置 `encoding="utf-8"`。
- 工作包结束时必须保留原始命令和可复核输出。

## 3. 冻结的 Agent 运行契约

### 3.1 运行状态

状态值固定为：

```text
created
planning
waiting_policy
waiting_approval
executing
observing
verifying
succeeded
failed
cancelled
expired
```

终态固定为 `succeeded`、`failed`、`cancelled`、`expired`。终态不得再次迁移。

### 3.2 步骤类型

步骤类型固定为：

```text
plan
policy
approval_request
tool_call
observation
verification
replan
terminal
```

每次重规划必须新增 `replan` 和后续计划步骤，不得覆盖历史步骤。

### 3.3 结构化错误码

错误码固定为：

```text
no_robot_available
tool_timeout
tool_failed
policy_denied
approval_rejected
approval_timeout
task_conflict
invalid_tool_input
invalid_tool_output
max_steps_exceeded
run_expired
internal_error
```

### 3.4 ID 前缀

```text
run_id      run_
step_id     stp_
approval_id apr_
memory_id   mem_
```

ID 由可注入的 ID 工厂生成，测试中必须可确定复现。

### 3.5 工具定义

每个工具至少声明：

```text
name
version
description
input_schema
output_schema
risk_level
timeout_ms
idempotent
allowed_roles
```

风险级别固定为：

```text
read_only
write
device_command
sensitive
```

工具调用必须经过：

```text
参数 Schema 校验
-> 角色与策略守卫
-> 幂等检查
-> 超时控制
-> 执行
-> 输出 Schema 校验
-> 审计和轨迹
```

### 3.6 最小公开 Python 接口

模块位置固定为 `backend/app/services/agents/`。命名允许按既有工程风格调整，但语义不得变化：

```text
AgentRuntime
AgentRun
AgentRunRequest
AgentRunResult
AgentStep
AgentStatus
AgentStepType
ToolRegistry
ToolDefinition
ToolContext
ToolResult
PolicyGuard
PolicyDecision
MemoryStore
RunRepository
ApprovalRepository
AgentError
```

运行时必须可注入：

```text
tool_registry
policy_guard
memory_store
run_repository
approval_repository
clock
id_factory
runtime_config
```

核心入口语义：

```text
AgentRuntime.run(request) -> AgentRunResult
AgentRuntime.cancel(run_id, actor, reason) -> AgentRunResult
AgentRuntime.resume(run_id) -> AgentRunResult
AgentRuntime.status() -> RuntimeStatus
```

首版必须提供内存适配器，使 Agent 内核不依赖数据库、Redis、MQTT、外网或大模型即可测试。

### 3.7 数据表

表名和核心字段固定为：

```text
t_agent_run
  id, run_id, trigger_type, objective, status, policy_version,
  started_at, finished_at, termination_reason, trace_id,
  created_at, updated_at

t_agent_step
  id, step_id, run_id, step_no, step_type, decision_summary,
  tool_name, tool_version, input_hash, output_hash,
  status, latency_ms, error_code, created_at

t_agent_memory
  id, memory_id, memory_type, scope_type, scope_id,
  content, confidence, source_type, source_id,
  valid_from, valid_to, created_at

t_agent_approval
  id, approval_id, run_id, requested_action, risk_level,
  requested_by, decided_by, decision, reason,
  requested_at, decided_at
```

- `run_id`、`step_id`、`memory_id`、`approval_id` 必须有唯一约束。
- `t_agent_step.run_id` 关联 `t_agent_run.run_id`。
- `t_agent_approval.run_id` 关联 `t_agent_run.run_id`。
- `t_agent_step` 必须有 `(run_id, step_no)` 唯一约束。
- 不保存模型私有思维链，只保存决策摘要、工具输入摘要、输出摘要和业务理由。

### 3.8 API 冻结

前缀固定为 `/api/v1/agents`：

```text
GET  /runtime/status
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/steps
POST /runs
POST /runs/{run_id}/cancel
GET  /tools
GET  /approvals
POST /approvals/{approval_id}/decide
GET  /evals/latest
```

现有 `GET /api/v1/ai/agents` 暂时保留兼容，但只能返回真实定义和真实运行状态。没有运行数据时必须返回 `idle` 或 `unavailable`，不得写死 `running`。

## 4. 第一波可并行工作包

第一波最多同时启动 5 个子代理。

### WP-00 基线修复

目标：建立可复现的软件基线。

允许修改：

```text
scripts/check_contract_drift.py
scripts/selftest_contract_drift.py
scripts/selftest_result.txt
backend/requirements-ai.txt
README.md
.gitignore
```

执行要求：

1. 在 `.venv-analysis` 中安装锁定版本的 Pillow。
2. 修复两个契约脚本及自证脚本在 Windows GBK 控制台下的 Unicode 输出问题。
3. 从仓库根目录执行全量测试：

```powershell
.\.venv-analysis\Scripts\python.exe -m pytest -q
```

4. 预期结果：无 failed；允许 1 项 skipped，但必须说明原因。当前收集基线为 335 项。
5. 执行：

```powershell
.\.venv-analysis\Scripts\python.exe scripts\check_contract_drift.py
.\.venv-analysis\Scripts\python.exe scripts\selftest_contract_drift.py
```

6. 如仓库无 `.git`，初始化 Git，保存当前真实基线提交；不得添加远程，不得推送。
7. README 只更新可复核的测试事实和当前能力口径，不替 WP-08 改写商业内容。

禁止事项：

- 不删除或绕开失败测试。
- 不把 `xfail` 当作修复。
- 不宣称真实海域、硬件或客户验证。

验收：

- 全量测试无失败。
- 两个契约脚本退出码为 0。
- Git 基线提交存在且工作区可复现。
- 报告包含原始测试尾部、Python 版本、命令和提交哈希。

### WP-01 Agent 内核

目标：实现不依赖外部模型和基础设施的确定性 Agent Runtime。

允许新增：

```text
backend/app/services/agents/**
backend/tests/test_agent_runtime.py
backend/tests/test_agent_tools.py
backend/tests/test_agent_policy.py
```

允许修改：

```text
backend/app/services/__init__.py
```

不得修改：

```text
backend/app/api/**
backend/app/models/**
backend/app/schemas/**
backend/alembic/**
backend/db/**
frontend/**
```

实现范围：

- `AgentRuntime`
- `AgentRun`、`AgentStep`、运行状态机
- 可注入 `ToolRegistry`、`PolicyGuard`、`MemoryStore`
- 内存仓储
- 超时、重试上限、最大步数、幂等
- 观察、验证、重规划和安全终止
- 审批暂停、拒绝、超时
- 结构化解密预算，不保存私有思维链

测试至少覆盖：

1. 正常派单闭环。
2. 无机器人。
3. 工具超时。
4. 策略拒绝。
5. 审批拒绝。
6. 达到最大步数。
7. 重复触发幂等。
8. 轨迹顺序和终态完整性。
9. 输出 Schema 错误。
10. 模型不可用时规则模式继续工作。

验收命令：

```powershell
backend\..\.venv-analysis\Scripts\python.exe -m pytest backend\tests\test_agent_runtime.py backend\tests\test_agent_tools.py backend\tests\test_agent_policy.py -q
```

### WP-02 Agent 数据与迁移

目标：为 Run、Step、Memory、Approval 建立 ORM、初始 SQL 和 Alembic 增量迁移。

允许新增：

```text
backend/app/models/agent.py
backend/alembic/versions/*_agent_runtime.py
backend/tests/test_agent_models.py
```

允许修改：

```text
backend/app/models/__init__.py
backend/db/init/01_schema.sql
```

不得修改：

```text
backend/app/api/**
backend/app/services/agents/**
backend/app/schemas/**
frontend/**
```

实现要求：

- 严格遵守冻结表名、字段名和唯一约束。
- ORM 可被 Alembic 导入。
- 初始 SQL 在全新数据库可重复执行。
- Alembic 迁移可从 baseline 升级。
- 迁移降级不能删除既有业务表。

验收：

```powershell
backend\..\.venv-analysis\Scripts\python.exe -m pytest backend\tests\test_agent_models.py -q
```

如果本机没有可用 PostgreSQL/PostGIS，必须做 AST 和 SQL 静态验证，并明确标记“未执行真实数据库迁移”，不能宣称迁移已完成。

### WP-06 感知评测

目标：把 OpenCV 感知结果、时序校验和数据集隔离变成可复现实验。

允许新增：

```text
ml/datasets/manifests/**
ml/scripts/evaluate_opencv.py
ml/tests/**
edge/detector/test_metrics.py
```

允许修改：

```text
ml/scripts/check_dataset.py
ml/configs/seasight.yaml
edge/detector/README.md
```

不得修改：

```text
backend/app/**
frontend/**
backend/db/**
```

实现要求：

- 训练、验证、独立测试、现场盲测必须物理或逻辑隔离。
- 输出 JSON 必须包含命令、日期、代码版本、样本量、分母、类别指标和 confounder 分层。
- 合成数据、准真实数据和真实数据必须带 `evidence_level`。
- 当前 OpenCV 只能称为 OpenCV 传统视觉；不得称 YOLO 或视觉模型。
- `76%` 抑制率必须复现并指出它只针对时序链路。
- 数据集为空时明确输出 `not_evaluated`，不能生成虚假精度。

验收：

```powershell
backend\..\.venv-analysis\Scripts\python.exe -m pytest edge\detector\test_metrics.py -q
backend\..\.venv-analysis\Scripts\python.exe ml\scripts\evaluate_opencv.py --config ml\configs\seasight.yaml --output artifacts\metrics\opencv_latest.json
```

### WP-08 商业与材料纪律

目标：修订商业材料和证据台账，使数字有来源、日期和证据等级。

允许新增：

```text
项目文档/商业证据台账.md
项目文档/用户访谈模板.md
项目文档/供应商询价模板.md
```

允许修改：

```text
docs/business-model.md
docs/product-readiness.md
```

不得修改：

```text
README.md
源码
数据库
```

实现要求：

- 每个数字标注 `E0` 至 `E4`、来源、日期、负责人、复核状态。
- 测算价格、目标价格、客户成交价严格区分。
- 增加 TAM/SAM/SOM、单位经济性和敏感性的假设台账。
- 写清用户、购买者、预算方、操作员和验收方。
- 列出需要真实获取的证据和访谈问题，不得编造访谈结论。

验收：

- Markdown 中不存在无来源商业数字。
- “已成交”“已签约”“已回款”等词只出现在带凭证说明的条目中。
- 附表可直接用于团队填写真实证据。

## 5. 第二波工作包

WP-00、WP-01、WP-02 完成并通过总控审查后启动。

### WP-03 API 与权限

允许新增：

```text
backend/app/api/v1/agents.py
backend/app/schemas/agent.py
backend/tests/test_agent_api.py
```

允许修改：

```text
backend/app/api/v1/__init__.py
backend/app/api/v1/ai.py
backend/app/schemas/__init__.py
```

要求：

- 严格实现冻结 API。
- `GET /ai/agents` 接入真实 Runtime 状态。
- 查看权限、写权限、审批权限和审计必须测试。
- 所有响应使用现有 `ApiResponse` 信封和错误码风格。

### WP-04 前端控制台

只有在 WP-03 的 OpenAPI 或契约测试通过后启动。

允许修改：

```text
frontend/src/views/AgentsView.vue
frontend/src/api/index.js
frontend/src/stores/realtime.js
frontend/src/router/index.js
```

要求：

- 删除写死的“6 个智能体在线”。
- 展示真实 Runtime、Run、Step、审批、工具、错误和回放。
- 明确区分 loading、empty、unavailable、degraded、failed。
- 桌面和移动端均不重叠、不溢出。
- 前端无法连接后端时显示真实错误，不展示伪造数据。

### WP-05 Agent 评测系统

只有在 WP-01 内核接口冻结后启动。

允许新增：

```text
backend/tests/agent_evals/**
scripts/run_agent_evals.py
artifacts/agent_evals/**
```

要求：

- 固定场景集和期望结果。
- 一键执行并输出 JSON。
- 指标包含成功率、策略违规率、工具调用正确率、无效循环率、恢复成功率、P95 决策耗时。
- 评测不得访问真实模型、网络或真实设备。
- 每次输出必须包含代码版本和配置哈希。

### WP-07 数据完整性

允许修改：

```text
backend/app/services/report.py
backend/app/api/v1/stats.py
backend/app/schemas/__init__.py
backend/tests/test_report_aggregate.py
backend/tests/test_data_integrity.py
```

要求：

- 解决 `coverage_area` 固定为 0 的假指标问题。
- 没有可靠来源时返回 `not_available` 或 `null`，不得估数冒充实测。
- 每个指标有口径、分母、时间窗和数据来源。

### WP-09 集成验收

由总控执行，不交给单点开发子代理。

要求：

- 完成全量测试、契约脚本和前端构建。
- 运行 Agent 正常、失败、审批、取消、超时和重规划演示。
- 核对 README、架构文档、软件设计、商业材料和计划书数字一致。
- 生成最终证据包和已知限制清单。
- 只有所有 E1/E2 结果可复现，才允许进入比赛材料定稿。

## 6. Harness 分派消息格式

每次派给子代理的消息必须包含：

```text
【工作包】WP-XX
【目标】
【上位文件】项目文档/探海灵眸_项目计划书.md
【执行手册】项目文档/Harness_分工执行手册.md
【允许文件】
【禁止文件】
【冻结接口】
【实现要求】
【验收命令】
【输出格式】
```

输出格式固定为：

```text
状态：完成 / 部分完成 / 阻塞
修改文件：
实现内容：
关键设计：
执行的测试：
测试结果：
未完成事项：
风险与假设：
需要总控决策：
```

## 7. 总控启动顺序

1. 启动 WP-00、WP-01、WP-02、WP-06、WP-08。
2. 等待第一波全部返回，不允许在接口未稳定时启动 WP-03、WP-04、WP-05。
3. 总控逐项验证测试证据，解决冲突并冻结 OpenAPI。
4. 启动 WP-03、WP-05、WP-07。
5. WP-03 通过后启动 WP-04。
6. 全部完成后启动 WP-09，执行全量回归和演示剧本。
7. 任何一轮发现契约漂移，冻结后续开发并先修契约。

## 8. 完成判定

项目只有在以下条件同时成立时，才可改写为“达到国奖候选工程基线”：

- 全量测试无失败。
- Agent Runtime 可离线运行并产生完整轨迹。
- API、数据库、前端和评测口径一致。
- 感知指标有真实分母和证据等级。
- 商业数字全部可追溯。
- 演示主链路和故障链路均可现场复现。

本手册是工程分派约束，不是获奖承诺。真实国奖还需要真实数据、设备、用户、现场验证、商业证据和稳定答辩表现。
