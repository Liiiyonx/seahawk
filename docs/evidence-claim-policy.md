# 探海灵眸 SeaSight 证据分级与宣称纪律（WP-15）

> 版本：1.0
> 日期：2026-09-19
> 上位口径：《项目文档/探海灵眸_项目计划书.md》§1、《项目文档/商业证据台账.md》§0
> 配套工具：`scripts/evidence_registry.py`（登记表）、`scripts/check_claims.py`（宣称扫描器）、`scripts/selftest_evidence_gate.py`（自测）
> 证据等级：本门禁工具为 **E1**（有代码、自动化自测与固定夹具，通过 selftest_evidence_gate.py 验证）
> 用途：把 E0-E4 纪律变成可执行检查。本文定义证据分级、禁止表述清单与豁免登记流程；扫描器按本文口径检查计划书、README、答辩材料和代码注释。

---

## 0. 一句话纪律

任何对外宣称必须能落到一条证据：**数字要有来源或台账编号，能力要有证据等级，等级不允许越级**。拿不出证据的表述，一律先登记、再使用。

---

## 1. 证据分级（E0-E4，冻结口径，与计划书 §1、台账 §0 一致）

| 级别 | 含义 | 可对外使用的表述 |
| --- | --- | --- |
| E0 | 只有想法、文档或接口草案 | “规划中”“拟建设”“测算” |
| E1 | 有代码、单元测试或确定性仿真 | “已实现，已通过软件测试” |
| E2 | 多模块软件联调，使用合成数据或模拟设备 | “已完成合成环境闭环验证” |
| E3 | 真实设备、真实海域或真实用户参与验证 | “已完成现场验证” |
| E4 | 有合同、订单、回款、验收报告或复购 | “已形成商业验证” |

套用规则：

- **甲类（内部测算/承诺类）**：成本测算、定价、营收、回报、TAM/SAM/SOM、单位经济性直接套用上表能力等级。当前项目处于原型阶段，全部为 E0，无任何 E3/E4。
- **乙类（外部公开事实类）**：数字本体是外部发布的事实，不是本项目能力证据。E 级表示「团队对该数字的核验程度」：E1＝已内部引用但未留存原文；E3＝已核对官方原文/访谈确认；E4＝持有官方书面文件。当前全部为 E1，复核状态待复核。
- 乙类数字只能表述为“公开报道/政府信息显示……（来源××，引用日期××）”，不得表述为“本项目已达 E3/E4”。
- 等级定义表本身属于政策文本，不构成能力宣称（登记记录 R-EV-01 豁免）。

---

## 2. 禁止表述清单（红线规则，共 10 条）

以下每条红线由 `check_claims.py` 逐行检查；命中即产生 **red_line**，除非被第 3 节的豁免机制放行。

| 规则 id | 名称 | 红线内容 |
| --- | --- | --- |
| `banned_trade_claim` | 无凭证成交/部署宣称 | 禁止使用“已成交 / 已签约 / 已回款 / 已部署 / 客户付费”，除非同行带凭证编号（合同编号、发票号、回款单号、流水号、协议号等）或登记说明（台账 §8）。 |
| `unsourced_business_number` | 无来源商业数字 | 商业数字（金额、吨量、市场规模）必须带来源、台账编号（F-/C-/T-/S-/E-/G-/R-）、证据等级或“测算/假设/目标”等自限措辞。 |
| `sim_as_real` | 合成/模拟/规划冒充真实 | 禁止把合成、模拟、仿真、规划写成真实海域、真实客户、真船、现场验收。示例：禁止写“仿真测试已完成真实海域验收”，应写“仿真测试不等于真实海域验证（R-SIM-01）”。 |
| `coverage_area_zero` | coverage_area 无来源写 0 | 无可靠来源时 `coverage_area` 必须为 NULL 或留空，禁止写 0；写 0 只允许出现在说明“禁止写 0 / 历史回退 / 迁移”的上下文中（台账 R-CA-01）。 |
| `seventy_six_as_accuracy` | 76% 冒充识别精度 | 76% 只能表述为**时序链路误报抑制率**（被过滤检测数 / 输入检测数），禁止写成识别精度、召回率或准确率（登记记录 R-76-01）。 |
| `agent_memory_as_prod` | E1 Agent 冒充生产级 | Agent Runtime 默认仍为 E1 进程内确定性内存实现，可选 SQL 持久化仓储也仅为 E1；两者均禁止写成生产级、高可用或分布式（登记记录 R-AG-01）。 |
| `opencv_as_model` | OpenCV 冒充训练模型 | 当前检测为 OpenCV 传统视觉（背景建模＋颜色/形状规则），禁止写成 YOLO、视觉大模型或已训练模型（登记记录 R-OP-01）。 |
| `md5_as_model` | MD5 冒充模型输出 | 禁止把 MD5 伪结果写成推理/模型输出/检测框。 |
| `static_agents_online` | 静态智能体冒充在线 | 禁止把静态/写死的智能体状态写成在线协同运行。 |
| `unregistered_evidence_level` | 未登记 E3/E4 越级宣称 | 禁止宣称“已完成现场验证 / 商业验证 / 已达 E3 / E4”，除非被已登记证据记录豁免或命中自限措辞（目标、待获取、定义、不代表等）。 |

扫描器**不**对以下情况误报（已内建豁免）：

- 等级定义表、口径说明、政策文本（登记记录 R-EV-01 等）。
- 规划中的待办清单、目标等级（如“待获取”“目标 E3”“[ ]”未勾选项）。
- 明确否定句（“不是”“不等于”“不代表”“不以……替代”“禁止”“不得”）。
- 对比表述（“OpenCV 方案 vs YOLO 方案”“接口预留”“冷启动”）。
- 引用已登记编号的行（F-01、C-15、R-SIM-01 等视为有来源）。
- 带凭证编号的成交表述（如“合同编号 HT-2026-001”）。

---

## 3. 豁免登记流程（从 E0 升 E3/E4 的唯一合法路径）

纪律不是“禁止进步”，而是“先登记、再宣称”。任何想把一条宣称从红线变成合规表述的动作，都必须走以下流程：

```text
1. 取得真实证据（访谈记录 / 询价单 / 政策原文 / 现场记录 / 合同回款凭证）
   ↓
2. 按 docs/evidence-inbox/intake_template.yaml 填写登记条目
   （复制模板为新文件：docs/evidence-inbox/YYYY-MM-DD-主题.yaml）
   ↓
3. 本地校验：python scripts/evidence_registry.py --registry <文件> --validate
   ↓
4. 总控复核原件与等级，将条目并入 scripts/evidence_registry.py 的登记表
   （可给条目配 rule/matches，实现“该规则下豁免某类表述”）
   ↓
5. 扫描验证：python scripts/check_claims.py --root .   （必须退出码 0）
   ↓
6. 需要修改计划书 / README / 答辩材料时，由总控执行修改（本文档只扫描和报告）
```

登记表字段（与 `evidence_registry.py` 的 `EvidenceRecord` 对齐）：

```text
id             必填，如 F-01 / C-15 / R-76-01 / EV-2026-001
claim          必填，宣称原文或事实描述
evidence_level 必填，E0/E1/E2/E3/E4
source_type    必填，受控集合：public_fact / internal_calculation / interview /
               inquiry / policy_document / contract / receipt / acceptance /
               test_report / field_record / assumption / other
source_ref     必填，可复核的来源指向（文件路径、链接、单据编号）
captured_at    必填，证据获取/形成日期
review_status  必填，待复核 / 复核中 / 已复核
owner          必填，责任人
rule           选填，豁免哪条红线规则（check_claims.py 的 rule_id）
matches        选填，命中特征子串（claim 之外等价表述的豁免锚点）
notes          选填，口径说明
```

升级红线：**任何 E 级上调都必须附新证据**。甲类 E0→E3 需询价单/试点数据；E3→E4 需合同、回款、验收或复购凭证；乙类 E1→E3 需官方原文或访谈记录。没有新证据不得上调。

---

## 4. 扫描与退出码

`check_claims.py` 是只读扫描器，不修改任何文件：

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv-analysis\Scripts\python.exe scripts\check_claims.py --root .          # 人类可读摘要
.\.venv-analysis\Scripts\python.exe scripts\check_claims.py --root . --json    # 机器可读 JSON
.\.venv-analysis\Scripts\python.exe scripts\check_claims.py --root docs --registry docs\evidence-inbox\xxx.yaml
```

| 退出码 | 含义 |
| --- | --- |
| 0 | 无未登记红线（CLEAN），可进入集成 |
| 1 | 存在未登记红线（RED LINE），材料需修正或证据需登记 |
| 2 | 参数/读取/登记表错误（根目录不存在、登记表校验失败） |

CI 或人工检查以退出码为准；JSON 输出含 `summary.red_lines`、`summary.clean`、`findings[]`（rule_id / severity / file / line / snippet / exempted_by）与 `registry` 摘要，可直接作为门禁凭证。

---

## 5. 责任与维护

- **唯一事实源**：《项目文档/商业证据台账.md》。登记表（`evidence_registry.py`）是其机器镜像，两者不一致时以台账为准，由总控同步。
- **只扫不改**：本门禁发现红线后，材料文件（计划书、README、答辩材料、DOCX）由总控决定修改方式；脚本侧只负责报告，不越权改材料。
- **自测**：每次改动扫描器或登记表后运行 `selftest_evidence_gate.py`，确保“故意违规必被捕获、带来源宣称必被豁免”两类行为不回退。
- **纪律红线**：登记表只登记真实来源；禁止凭空补数、把测算写成成交、把外部转述写成一手核实。

---

## 6. 变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-09-19 | v1.0 建立：证据分级、10 条红线清单、豁免登记流程、退出码语义 | WP-15 |
