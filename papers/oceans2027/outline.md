# OCEANS 2027 Aberdeen 论文骨架（系统论文）

> 截稿 **2027-01-15**（门户已开放；惯例届时交完整论文，别赌只交摘要）。通知2027-03，终稿2027-05-24。IEEE 双栏模板，惯例6~8页，以投稿门户为准。
> Track 主投：**Environmental Challenges and Solutions**（海洋污染）；备选 Digital Innovation in Oceans（AI）。
> 源材料：README.md、`backend/app/services/agents/runtime.py` + `policy.py`、`edge/detector/world_detector.py`、`docs/competitions/public-floatwaste-benchmark.md`、`integrations/nexent/`、`backend/app/services/knowledge.py`。

## 工作标题（二选一）

1. **Oceanus: An Auditable LLM Governance Agent for Marine Debris Response in Aquaculture Zones**
2. From Seeing to Accountability: A Governance Agent System for Marine Debris Management with Policy Guards, Human Approval, and Decision Evidence Chains

推荐 #1（系统命名+定位清晰）；#2 更学术但偏长。

## 一句话定位（Abstract 主线）

把海漂垃圾治理的瓶颈从"看得见"（检测）挪到"可追责、可复核"（决策）：一个 LLM 治理智能体，其每次决策经过策略守卫拦截、人工审批门、证据链留痕与审计回放，且全部知识与工具经 MCP 标准协议可被外部智能体调用。

## 摘要要素（写作用清单）

- 背景：养殖区海漂垃圾；现有方案（监控网络/清洁机器人）止步于感知或单机作业，决策仍靠人工。
- 系统：感知（岸基摄像头+边缘双通道检测）→ 治理智能体（规划→工具调用→策略守卫→人工审批→派单）→ 执行（MQTT 水面机器人，三仓分拣）→ 审计回放。
- 三个技术特征：①开放词汇零样本检测通道（现场加词，不重训不重启）；②决策证据链（每次决策绑定知识资产版本+本体版本+策略版本）；③MCP 标准化工具暴露（21只读工具，跨智能体可调用）。
- 评测：检测通道在第三方公开基准 SC-FloatWaste 官方 val 独立测试集（400图/3区域）上的隔离评测；治理闭环的运行时演示（策略守卫拦截/审批/审计日志）。
- 诚实边界：精度为公开基准独立评测而非现场实测；机器人端为可替换作业端。

## 章节与页数预算（按8页）

| 节 | 内容 | 页 |
| --- | --- | --- |
| 1 Introduction | 治理缺口：看得见≠管得住；贡献列表（3点） | 1 |
| 2 Related Work | 监控网络体系（福州2020等）/清洁机器人（WasteShark, Clearbot）/LLM agents in environmental mgmt | 0.75 |
| 3 System Architecture | 感知-决策-执行三级闭环总图；五软件子系统简表；技术栈一段带过 | 1 |
| 4 Auditable Decision Pipeline | 规划→工具调用→策略守卫→人工审批→派单→审计回放，配时序图；策略守卫的规则示例 | 1.5 |
| 5 Perception Channels & Evaluation | OpenCV背景建模（主）/YOLO-World开放词汇（现场加词）/YOLO11有监督对照；SC-FloatWaste隔离评测协议+数字表（数字取 public-floatwaste-benchmark.md §评测，禁止现场口径） | 1.5 |
| 6 Knowledge & Interoperability | 多跳检索+决策证据链（简写，深度留给PAKDD篇）；MCP 21工具与外部智能体调用 | 1 |
| 7 Limitations | 无现场实海验证；公开基准≠本地精度；审批流程尚未在真实政务环境运行 | 0.5 |
| 8 Conclusion | — | 0.25 |

## 表格/图设计

- **Fig.1** 三级闭环总架构图（可从华为材料四张示意图的生成器 `scripts/make_huawei_track3_polish_figures.py` 改英文版）。
- **Fig.2** 决策管线时序图（守卫拦截→审批→执行→审计回放）。
- **Table 1** 与现有方案对比（README 竞品表英文化：WasteShark/Clearbot vs 本系统，维度=形态/决策/新类别/依据/成本）。
- **Table 2** 检测评测表：三通道 × SC-FloatWaste test（400图，Indonesia/NSW/Hobart三区域）指标；正文必须复述隔离设计（官方train/val不相交+确定性取样+PROVENANCE）。
- **Table 3** MCP 工具面摘要（知识检索/事件/工单三类，21只读）。

## 写作红线（继承比赛材料口径）

1. 不写"国内首个"——用"差异化叙事"（决策层增量，感知层不称王）。
2. 检测数字只写"第三方公开基准独立评测"，不写现场/实测。
3. 连江本地测试集为空，如实声明（Limitations 里反而加分）。
4. 与 PAKDD 篇分工：本篇知识部分只作为"决策证据链"组件简述，检索实证细节引用将来的 PAKDD 论文（先挂 arXiv 即可互引）。

## 里程碑

- 11月下旬（PAKDD 交稿后）：Fig.1/2 英文化 + §3/4 初稿
- 12月中：§5 检测评测表定稿 + §6 + 全文合稿
- 12月底：内审一轮（语言+口径自查，对照本文件红线）
- 01-05 前：IEEE PDF eXpress 合规检查，**01-10 前提交**（预留5天缓冲）
- 03月录用后：注册费+英国签证规划（学生签证周期约3周，预留）
