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

### WP-00 基线修复（已完成）

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

1. 已在 `.venv-analysis` 中安装锁定版本 Pillow 11.0.0。
2. 已为两个契约脚本及自证脚本补齐 Windows 控制台 UTF-8 输出处理。
3. 从仓库根目录执行全量测试：

```powershell
.\.venv-analysis\Scripts\python.exe -m pytest -q
```

4. 当前结果：**860 passed / 0 skipped / 0 failed**（WP-00 时点 Harness 自报值；2026-09-19 总控在仓库根目录按同一命令复核为 **952 passed / 0 skipped / 0 failed**，见第 7 节第 15 条。该 860 数值不可复现，已作废）；出现跳过项时必须解释原因。
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

WP-00、WP-01、WP-02 已完成并通过总控审查；以下保留冻结接口下的执行约束。

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

- 已解决 `coverage_area` 固定为 0 的假指标问题：数据库列改为 nullable，历史假 0 已清理。
- 没有可靠来源时返回 `not_available` 或 `null`，CSV 导出留空；不得估数冒充实测。
- 每个指标有口径、分母、时间窗和数据来源。

### WP-09 集成验收

由总控执行，不交给单点开发子代理。

要求：

- 完成全量测试、契约脚本和前端构建。
- 运行 Agent 正常、失败、审批、取消、超时和重规划演示。
- 核对 README、架构文档、软件设计、商业材料和计划书数字一致。
- 生成最终证据包和已知限制清单。
- 只有所有 E1/E2 结果可复现，才允许进入比赛材料定稿。

### WP-14C ACK 接收、校验与幂等

目标：让 `robot/{robot_id}/cmd/ack` 真正消费冻结回执信封，修正当前
“冻结 ACK 没有顶层 `task_id`，处理器直接静默返回”的断链；同时完成
设备身份校验、拒绝回退、重复 / 超时 / 乱序判定，不涉及数据库迁移。

允许新增：

```text
backend/app/mqtt/ack.py
backend/tests/test_mqtt_ack.py
```

允许修改：

```text
backend/app/mqtt/handlers.py
backend/app/mqtt/client.py
backend/tests/test_mqtt_layer.py
docs/device-interface.md
docs/mqtt-topics.md
```

禁止修改：

```text
backend/app/models/**
backend/app/repositories/**
backend/db/**
backend/alembic/**
backend/app/api/**
backend/app/schemas/**
backend/app/services/dispatch.py
edge/device_sim/**
frontend/**
```

冻结接口与语义：

1. 入站报文必须优先解析冻结信封：
   `ack_id / command_id / device_id / seq / received_at / accepted /
   reason / mode`；同时兼容旧字段
   `task_id / robot_id / accepted / ts`。字段缺失或类型错误只记 warning
   并丢弃，不得让 MQTT 主循环抛异常。
2. `task_id` 解析顺序：优先顶层兼容字段；否则仅接受
   `command_id = cmd_{task_id}` 并反推。若两者同时存在但不一致，整条拒绝。
3. `payload.device_id`（旧字段为 `robot_id`）、topic 中的 `robot_id`、
   `task.robot_id` 三者必须一致；否则整条拒绝，不得推进任务。
4. `seq` 必须为非负整数，`received_at`（旧字段为 `ts`）必须可解析为
   时间；不得依赖真实 MQTT 或网络。
5. 平台侧 `AckTracker` 必须位于 backend，不得反向 import
   `edge.device_sim`。判定优先级固定为：
   `duplicate > late > out_of_order > new`。
   - `duplicate`：同 `command_id` 再次到达。返回首次规范回执，
     不重复推进状态。
   - `late`：`received_at > expires_at`。仍记录并允许状态推进。
   - `out_of_order`：新回执 `seq` 小于该设备已 ACK 水位。仍记录；
     `accepted=true` 时允许对仍处于 `assigned` 的任务推进。
   - `new`：首次按序到达。
6. `accepted=true`：仅当任务仍为 `assigned` 时走
   `DispatchEngine.transition(..., NAVIGATING)`；其他状态不得重复推进。
7. `accepted=false`：首次回执时，若任务仍为 `assigned`，记录拒绝原因，
   清空 `robot_id` 并走状态机 `assigned -> pending`，交给现有补派轮处理；
   不得在 handler 内立即递归重派。重复拒绝回执不得重复回退。
8. `publish_task` 只在 MQTT 发布成功后登记
   `command_id / device_id / seq / expires_at` 到 `AckTracker`，供超时判定。
   登记失败、未登记命令或进程重启后的回落策略必须写清，不得假装持久化。
9. `docs/mqtt-topics.md` §5.5 必须改为以冻结 ACK 信封为主，并列出旧字段
   兼容关系；`docs/device-interface.md` §11 必须更新消费端接线状态。

验收命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv-analysis\Scripts\python.exe -m pytest backend\tests\test_mqtt_ack.py backend\tests\test_mqtt_layer.py -q
.\.venv-analysis\Scripts\python.exe -m pytest edge\device_sim -q
```

最低测试矩阵：

- 冻结 ACK 无 `task_id` 时能反推并推进任务。
- 旧 ACK 字段仍兼容。
- `accepted=false` 首次回退、重复不重复回退。
- `command_id`、设备 ID、topic 不一致时全部拒绝。
- duplicate / late / out_of_order / new 四类判定与优先级。
- QoS1 重复 ACK 不重复推进。
- 未登记 deadline 的命令仍可接收，但不得伪造 `late` 结论。

### WP-14D ACK 持久化、迁移与审计查询

目标：把 WP-14C 的内存判定落成可恢复、可查询的 ACK 审计账本；保留
每个 `command_id` 的首次规范回执，并统计后续重复次数，使重启后仍能
解释“平台是否收到过回执、何时收到、设备是否接受、为什么拒绝”。

允许新增：

```text
backend/app/models/task_ack.py
backend/alembic/versions/20260919_1700_task_ack.py
backend/tests/test_task_ack_persistence.py
backend/tests/test_task_ack_api.py
```

允许修改：

```text
backend/app/models/__init__.py
backend/alembic/env.py
backend/db/init/01_schema.sql
backend/app/repositories/__init__.py
backend/app/mqtt/handlers.py
backend/app/api/v1/tasks.py
backend/app/schemas/__init__.py
backend/tests/test_agent_models.py
docs/api.md
docs/mqtt-topics.md
docs/device-interface.md
```

> `backend/tests/test_agent_models.py` 中的 revision 链测试硬编码了「当前唯一 head」
> （`script.get_heads() == [AGENT_STATE_REVISION]`）。只要新增任何迁移，该断言必然
> 失效。WP-14D 对它的修改只允许限于：新增 `TASK_ACK_REVISION = "20260919_1700_task_ack"`
> 常量、把 head 断言指向新 head、补一条 `down_revision` 断言、更新真实迁移往返测试里的
> 期望版本号。除此之外不得改动该文件，尤其不得放宽或删除既有断言。

禁止修改：

```text
edge/device_sim/**
frontend/**
backend/app/services/dispatch.py
```

冻结表契约：`t_task_ack`

```text
id               BIGSERIAL PRIMARY KEY
command_id       VARCHAR(96) NOT NULL UNIQUE       -- 一命令一条规范回执
task_id          VARCHAR(64) NOT NULL FK t_task(task_id) ON DELETE CASCADE
device_id        VARCHAR(64) NOT NULL
seq              BIGINT      NOT NULL
outcome          VARCHAR(16) NOT NULL              -- new/duplicate/late/out_of_order
accepted         BOOLEAN     NOT NULL
reason           VARCHAR(128)
mode             VARCHAR(32)
received_at      TIMESTAMPTZ NOT NULL              -- 设备回执时间
received_wall_at TIMESTAMPTZ NOT NULL DEFAULT now() -- 平台首次落库时间
duplicate_count  INTEGER     NOT NULL DEFAULT 0
last_duplicate_at TIMESTAMPTZ
raw_payload      JSONB       NOT NULL               -- 首次规范回执原文
last_payload     JSONB                              -- 最近一次重复回执原文
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

索引至少包含：

```text
idx_task_ack_task        (task_id, received_wall_at DESC)
idx_task_ack_device_seq  (device_id, seq DESC)
idx_task_ack_outcome     (outcome, received_wall_at DESC)
```

实现要求：

1. 新环境 `01_schema.sql` 幂等建表；存量环境 Alembic 从
   `20260919_1600_agent_state` 线性升级，revision id 不超过 32 字符。
2. `TaskAckRepository.record_arrival(...)`：
   - 首次 `command_id` 创建规范行，`outcome` 取 WP-14C 判定结果；
   - 已存在时 `duplicate_count += 1`、更新 `last_duplicate_at` /
     `last_payload`，不得覆盖首次规范回执；
   - 并发唯一冲突必须可重试或转为 duplicate，不得产生第二条规范行。
3. WP-14C 的状态推进与 WP-14D 的账本写入必须在同一数据库事务内：
   先校验与判定，再写 ACK 行，最后提交；写库异常不得留下已推进但
   无回执证据的状态。若只能分两事务，必须在回执中明确并给出补偿方案，
   不得静默接受。
4. `GET /api/v1/tasks/{task_id}/acks`：
   - 使用现有 `ApiResponse` 信封；
   - 仅登录用户可读，operator 只能查询本辖区任务；
   - 支持 `page` / `page_size`，默认按 `received_wall_at DESC`；
   - 返回 `command_id/task_id/device_id/seq/outcome/accepted/reason/mode/
     received_at/received_wall_at/duplicate_count`，不回传原始隐私字段。
5. 重启恢复：`AckTracker` 能从 `t_task_ack` 重建已有命令的规范回执与
   设备 ACK 水位；没有该能力时必须把持久化覆盖标记为“仅审计，非判重恢复”。
6. `docs/api.md` 增加 ACK 查询接口；文档中的示例不得使用真实用户、
   真实设备或虚构成交数据。

验收命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv-analysis\Scripts\python.exe -m pytest backend\tests\test_task_ack_persistence.py backend\tests\test_task_ack_api.py backend\tests\test_mqtt_ack.py -q
.\.venv-analysis\Scripts\python.exe -m pytest backend\tests -q
.\.venv-analysis\Scripts\python.exe -m compileall -q backend\app backend\alembic
```

如果本机没有可用 PostgreSQL/PostGIS，必须执行 ORM、SQL 与迁移 AST
静态验证，并明确写“未执行真实数据库迁移”；不得把静态检查冒充实库验证。

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

## 7. 总控执行记录（2026-09-19）

1. WP-00、WP-01、WP-02、WP-06、WP-08 已完成第一轮开发和总控复核。
2. 第一波接口稳定后，WP-03、WP-05、WP-07 已实现并纳入主分支工作树。
3. WP-03 契约通过后，WP-04 前端控制台已接入真实 Run、Step、Tool、Policy、Approval、Replay 和 Eval 数据。
4. WP-09 已完成全量测试、契约漂移检查、缺陷注入自证、Agent 固定场景评测和前端生产构建。
5. WP-09 已完成 Agents 页活跃运行取消、viewer 审批权限和运行详情刷新保持三类浏览器回归（3/3 通过）；正式 DOCX 按最新计划书重建并执行逐页渲染检查。
6. 后续任何一轮发现契约漂移，冻结相关开发并先修契约；不得用旧测试数或旧指标覆盖本次证据。
7. WP-16 已将在线 Agent 评测源切换为 `artifacts/agent_evals/latest_v2.json`（schema 2.0）；当前 23/23 场景通过、0 skipped，覆盖重启恢复、幂等冲突、模型回退、轨迹回放、审批交接和设备故障恢复。
8. 独立审计复核（2026-09-19）：Agent 运行时、API、内存仓储与 SQL 持久化仓储已统一处理 `None` / naive / aware 时间；持久化仓储改走 `create_repositories(engine)`；审批镜像与决策时间统一写 aware UTC；列表排序不再因混合时区抛 `TypeError`。
9. WP-14B 前基线：全量测试 860 passed / 0 skipped / 0 failed（该数值已在第 15 条被更正，不可复现）；契约漂移 26/26 通过；缺陷注入 12/12 捕获；Agent E1 固定评测 23/23 通过；前端生产构建通过；Agents 浏览器回归 3/3 通过。外部门证据仍为 0，E3/E4 不得升级。
10. WP-14B 已完成并独立复核：后端派单报文已兼容冻结命令信封，包含 `command_id/device_id/seq/issued_at/expires_at/action/params`，同时保留 `task_id/target/priority` 兼容字段；ISO 时间副本由 `issued_at_iso/expires_at_iso` 提供。
11. WP-14B 真实回执：`artifacts/harness_dispatch/WP-14B_20260919_053655.txt`。目标测试 `137 passed`，契约漂移 `26/26`，宣称扫描 `CLEAN`；其中「全量测试 877 passed」一项无法在仓库根目录按文档命令复现，已在第 15 条更正。仍不得把当前设备故障恢复场景描述为真实外部设备或真实网络验证。
12. 后续暂缓项：`seq` 跨进程持久化、ACK 审计账本持久化（WP-14D），以及真实设备接入验证尚未完成；`robot/+/cmd/ack` 的消费端 ACK 判重接线已由 WP-14C 关闭。这些剩余项不得用 E1/E2 孪生结果替代。
13. WP-14C 已完成并独立复核：`robot/+/cmd/ack` 消费端已消费冻结 ACK 信封（`command_id/device_id/seq/received_at/accepted/reason/mode`），四类判定 `new/duplicate/late/out_of_order` 与优先级 `duplicate > late > out_of_order > new` 由纯判定 `AckTracker.classify()` 实现，`record()` 仅登记首次规范回执；`accepted=false` 首次且任务仍 `assigned` 时回退 `pending` 并写入拒绝原因，重复拒绝不重复回退；`payload.device_id`／topic robot／`task.robot_id` 三重身份校验不一致时整条拒绝且不污染 tracker；旧顶层 `task_id`（无 `seq`／`command_id`）回执仍兼容派生 `cmd_{task_id}`；仅在 `publish_task` 发布成功后登记 deadline。
14. WP-14C 真实回执：`artifacts/harness_dispatch/WP-14C_20260919_070000.txt`。总控独立复跑：`test_mqtt_ack.py + test_mqtt_layer.py` → `167 passed / 1 skipped`，`edge/device_sim` → `44 passed`，`test_static_guards.py` → `3 passed`，契约漂移 `26/26`，缺陷注入 `12/12` 捕获，`check_claims.py` 为 `CLEAN`，`git diff --check` 通过。测试文件插入逐条核验：无 `skip`／`xfail`／`TODO` 掩盖，四类判定、优先级、按设备独立水位、纯判定不污染均有断言。仍不得把内存判定描述为可恢复持久化或真实设备验证。
15. 基线更正（2026-09-19，总控实测）：在仓库根目录执行文档规定的全量命令
    `.\.venv-analysis\Scripts\python.exe -m pytest -p no:cacheprovider -o addopts= -q`，
    结果为 **952 passed / 0 skipped / 0 failed / 1 warning**（`starlette` 弃用告警，与项目无关）；
    收集范围为 `backend/tests` + `edge/` + `ml/tests`。分域实测：`backend/tests` 单独运行为
    `786 collected = 785 passed / 1 skipped`，唯一跳过来自
    `backend/tests/test_mqtt_layer.py:799`（`edge/device_sim` 未随本次运行收集时的跨包契约比对，
    在根目录全量运行中该用例会正常执行，故全量为 0 skipped）。此前记录的 `860`／`877`
    均无法在上述任何命令下复现，且与当前收集数不符，属于未经独立复核的自报数值，现予作废，
    以本条为准。后续任何测试数声明必须附命令与输出，不得直接引用本条以外的旧数字。
16. WP-14D 已完成并由总控独立复核：ACK 审计账本 `t_task_ack` 落地为 ORM ＋
    `01_schema.sql` 幂等建表 ＋ 增量迁移 `20260919_1700_task_ack`（接在
    `20260919_1600_agent_state` 之后，保持单一 head，revision 21 字符）三处逐字段一致
    （17 列、`uq_task_ack_command_id` 唯一、FK→`t_task.task_id` `ON DELETE CASCADE`、
    三条冻结 DESC 索引）。`TaskAckRepository.record_arrival` 首次建规范行（`outcome` 取
    WP-14C 判定、`raw_payload` 只写一次），重复只累计 `duplicate_count` 并更新
    `last_duplicate_at`／`last_payload`，并发唯一冲突在真实库上验证「回滚→重查→转 duplicate」，
    不产生第二条规范行；`rebuild_ack_tracker` 提供重启重建能力。`handle_robot_ack` 改为
    「校验与判定 → 写 ACK 行 → 状态推进 → 提交」单事务闭环，异常整体回滚，不留「已推进但
    无回执证据」的状态；重复回执只累计不推进，进程重启后由账本兜底识重。
    `GET /api/v1/tasks/{task_id}/acks` 使用 `ApiResponse` 信封，匿名 401、operator 越辖区 403、
    分页默认 `received_wall_at DESC`，只返回 11 个结论/时间线字段，不回传 `raw_payload`／`last_payload`。
17. WP-14D 真实回执：`artifacts/harness_dispatch/WP-14D_20260919_105308.txt`。总控独立复跑
    （非沙箱环境）：目标三文件
    `test_task_ack_persistence.py + test_task_ack_api.py + test_mqtt_ack.py` → **106 passed**；
    仓库根目录全量 → **983 passed / 0 skipped / 0 failed / 1 warning**（较第 15 条 952 增加 31 条）；
    契约漂移 `26/26`，缺陷注入 `12/12` 捕获，`check_claims.py` 为 `CLEAN`，`compileall` 通过。
    **真实数据库实测（非静态冒充）**：`alembic current` = `20260919_1700_task_ack (head)`；
    总控独立查询 `information_schema` 确认 `t_task_ack` 17 列、`jsonb`／`timestamptz` 类型、
    `uq_task_ack_command_id` 与三条冻结索引齐备；子代理 scratch 库另完成
    「`01_schema.sql` ×2 幂等 → stamp → upgrade → 列/约束/索引校验 → JSONB 冒烟读写 →
    CASCADE 级联删除 → downgrade → 业务表保留」全回环。
18. WP-14D 两处已登记的必要偏离：(a) `backend/tests/test_agent_models.py` 的链断言按本手册
    WP-14D 允许清单补充说明最小更新（新增 `TASK_ACK_REVISION`、head 指向新 head、补一条
    `down_revision` 断言、迁移回环期望版本），总控逐行核验：既有断言全部保留、仅新增，无弱化；
    (b) 子代理沙箱内对 `tmp_path`／`tempfile` 的目录迭代被拒（`PermissionError: [WinError 5]`），
    导致 9 个既有用例（`agent_evals` ×1、`test_agent_api` TestEvalLatest ×5、`test_ai_postprocess` ×3）
    在沙箱内必失败，均为环境限制而非回归；总控在正常环境复跑全量为 983 全绿，已证实与本包无关。
19. WP-14D 遗留、需后续工作包收口：`rebuild_ack_tracker` 目前只是能力方法，**未接入应用启动流程**
    （`client.py`／`main.py` 不在 WP-14D 允许清单），因此「重启自动恢复判重水位」尚未生效；
    设备侧 `seq` 跨进程持久化与真实设备接入验证仍未完成。三者均不得用 E1/E2 孪生结果替代。
20. WP-14E 已完成并由总控独立复核：`backend/app/main.py` 已把
    `rebuild_ack_tracker` 接入 lifespan 启动流程，恢复包在 5 秒超时上界内执行，数据库不可用、
    表缺失或查询异常统一降级 warning 且不阻塞启动；恢复结果以
    `{status, rows, elapsed_ms, detail}` 写入 `app.state.ack_tracker_recovery` 并由 `/health`
    顶层 `ack_recovery` 暴露。设备孪生新增 `DeviceTwin(seq_store_path=...)` 与
    `DEVICE_SIM_SEQ_FILE` 配置，默认不写盘；每次遥测自增后用临时文件加 `os.replace` 原子落盘，
    文件缺失按首次运行处理，损坏或写盘失败按可解析值／纯内存方式降级，重启后序号严格单调递增。
    `test_ack_twin_loopback.py` 以内存 transport、假时钟、真实 scratch PostgreSQL、
    真实 `DispatchEngine` 与 `TaskAckRepository` 完成「孪生 ACK → 账本与任务推进 → 重启重建 →
    同回执重放不重复推进」闭环，并覆盖身份不一致、未知任务、未登记 deadline 不伪判 late。
    总控在非沙箱环境复跑：相关 8 个测试文件 **177 passed / 0 skipped / 0 failed**；
    仓库根目录全量
    `.\.venv-analysis\Scripts\python.exe -m pytest -p no:cacheprovider -o addopts= -q`
    为 **1010 passed / 0 skipped / 0 failed / 1 warning**（WP-14E 当时的实测值；较第 17 条 983 增加 27 条）；
    `compileall` 通过，契约漂移 **26/26**，缺陷注入 **12/12** 捕获，`check_claims.py` 为
    **CLEAN**。该闭环仍是孪生／本地 E1/E2 证据，不是真实设备、真实网络或真实海域验证。
21. WP-17 集成验收已完成并实测（2026-09-19）：浏览器验收升级为
    「真实登录 + 主业务链路」集成包（`scripts/browser_acceptance.mjs`），
    新增一键复跑故障演练包（`scripts/fault_acceptance.py`）；Makefile 新增
    `test-browser` / `fault-acceptance`（既有目标未动），`docs/development.md`
    新增「WP-17 集成验收」章节，README 验证章节补两条命令。
    - **浏览器集成验收实测（E1）**：最终复跑 **15/15 通过**，覆盖真实登录页
      表单 + 真实 `POST /api/v1/auth/login`、dashboard / events / tasks /
      devices / reports / agents 六页真实读取、真实 CSV 导出（2xx /
      `text/csv` / UTF-8 BOM / 稳定表头 / 字节数 / SHA256）、viewer 写接口
      真实 403、MQTT 断开时 `/health` 降级与只读大屏可用；报告 JSON 观测到
      21 个 API 路径。12 个场景无拦截，3 个 Agent 状态构造场景逐项标注
      `mocked: true` 与原因；截图、CSV 与登录 storageState 均落盘。
      证据文件 `artifacts/browser-acceptance/latest.json`。
    - **发现并修复真实运行时缺陷**：首轮 E2E 在 admin / viewer 登录后各出现
      两条 `Unhandled error. (undefined)`。根因是 `VideoPlayer.vue` 未订阅
      mpegts `error` 事件，离线视频流触发浏览器 EventEmitter 的无监听器
      `error` 升级；随后又暴露库自身 `console.error` 噪音。现已在 `load()`
      前注册 `mpegts.Events.ERROR`、将离线原因呈现在播放器状态，并关闭预期
      离线路径的库级 `console.error`。净室重跑后浏览器验收 15/15。
    - **前端生产构建实测**：`npm run build` 退出码 0，Vite 转换 679 个模块
      并生成 `dist/`；不再受 Harness 子会话的进程启动边界阻塞。
    - **故障演练包实测（本会话真实执行）**：4/4 组通过、**127/127 用例**
      （health-degradation 7、ack-startup-recovery 9、ack-twin-loopback 5、
      ack-persistence-api-idempotency 106），退出码 0、skipped 0。最终
      确定性复跑未设置 live probe（`live_probe=null`）；本会话早先对旧后端
      进程做只读 `/health` 观测时确见 `status=degraded`、
      `dependencies={redis: ok, mqtt: down, database: ok}`，但旧进程无
      `ack_recovery` 字段，故没有把该观测冒充为启动恢复接线证据。
      证据文件 `artifacts/fault-acceptance/latest.json`。
    - **独立复核**：`check_contract_drift.py` **26/26**、
      `check_claims.py --root .` **CLEAN**；根目录全量回归
      `.\.venv-analysis\Scripts\python.exe -m pytest -p no:cacheprovider -o addopts= -q`
      为 **1010 passed / 0 skipped / 0 failed / 1 warning / 67.94s**（WP-17 当时的实测基线；WP-18 后当前基线见第 22 条）。
      超时上界用例额外连续复跑 **20/20** 通过；原 99ms 级断言已改为排除
      “瞬时跳过”的 50ms 下界，严格 2s 上界和慢查询取消语义保持不变。
    - **证据上限（如实声明）**：浏览器 E2E 最多是 E1（真实登录 + 真实业务
      读取链路 + 真实 CSV 导出 + 真实 `/health` 降级探针；仅 Agent 页场景
      `page.route` 受控拦截并逐项标注 `mocked` 与原因），仍**不是真实用户
      试点**；故障包是受控注入测试（进程内注入 / 内存 transport /
      scratch PostgreSQL），仍**不是真实 broker / 硬件 / 公网故障**。
      外部真实证据仍为 **0**，不得把本轮结果写成国奖保证或现场验证。
22. WP-18 真实 Agent 状态端到端验收已完成并实测（2026-09-19）：
    新增 `scripts/agent_real_state_acceptance.py`，以三段真实进程生命周期验证
    “基线成功 → WRITE 审批 → 进程重启只读回放”。脚本只启动和停止自己的
    `127.0.0.1:8011` 验收后端，并设置 `BACKGROUND_WORKERS_ENABLED=false`
    避免后台 worker 与显式 Agent 调用竞争；`backend/app/core/config.py` 因此新增
    后台 worker 开关，`backend/app/main.py` 仅在开关为真时启动 Redis consumer、
    pending dispatcher 和日报 worker。AgentRuntime 保持冻结，未改变运行时语义。
    - **实测结果（E2 软件集成）**：`129/129` 检查通过，0 failed；成功 run 为
      `run_5c706c14dcc1`，审批 run 为 `run_d16e5ec8fe12`。覆盖真实 HTTP 事件接入、
      operator/admin/viewer 权限、PostgreSQL Agent 仓储、成功轨迹（plan / policy /
      tool_call / observation / verification / terminal）、真实工单创建、事件
      `dispatched`、首次和重启后幂等重放、WRITE `waiting_approval` → admin 审批 →
      `succeeded`、重启后读取已完成 run/steps/task_result。
    - **直接数据库证据**：2 个 succeeded run、25 个 steps、2 个 run state、
      2 个 task、2 个 dispatched event、1 个 approved 审批。结果文件为
      `artifacts/agent-real-state-acceptance/latest.json`。
    - **WP-18 当时总门禁（历史快照）**：根目录全量 pytest **1019 passed /
      0 skipped / 0 failed / 1 warning / 68.29s**；浏览器验收 **15/15**；受控故障演练 **4/4 组、
      127/127**；契约漂移 **26 passed / 0 warnings / 0 failures**；宣称扫描
      `CLEAN`。`8011` 验收后端已停止，无孤儿进程。
    - **当前总控复核（2026-09-22）**：全量 pytest **1061 passed / 0 skipped /
      0 failed / 1 warning / 91.63s**；其余浏览器、故障、契约与宣称门禁结果保持上条口径。
    - **证据上限（如实声明）**：输入事件是合成的；AgentRuntime 仍在当前进程内；
      `t_agent_run_state` 是审计与重启只读回放镜像，不声称未完成 run 可以在
      重启后续跑；不包含真实摄像头、海域、用户、设备、订单、性能或生产级 SLA。
      该结果只用于证明真实 HTTP/权限/数据库/审批/幂等软件集成，不能写成 E3/E4、
      现场验证、生产就绪或国奖保证。

## 8. 完成判定

项目只有在以下条件同时成立时，才可改写为“达到国奖候选工程基线”：

- 全量测试无失败（当前经总控实测基线 1061 通过 / 0 跳过 / 0 失败，命令与分域明细见第 7 节第 15、17、20、22 条；其中第 20、21 条保留工作包当时的历史计数）。
- Agent Runtime 可离线运行并产生完整轨迹。
- API、数据库、前端和评测口径一致。
- 感知指标有真实样本、分母和证据等级；数据为空时必须保持 `not_evaluated`。
- 商业数字全部可追溯。
- 演示主链路和故障链路均可现场复现。

本手册是工程分派约束，不是获奖承诺。真实国奖还需要真实数据、设备、用户、现场验证、商业证据和稳定答辩表现。
