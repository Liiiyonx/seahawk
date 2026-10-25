# 双轨论文作战计划（PAKDD 2027 + OCEANS 2027 Aberdeen）

> 制定日期：2026-10-26。两篇论文内容不重叠，无一稿多投风险。
> PAKDD = 方向A（检索实证研究）；OCEANS = 方向B（治理智能体系统）。

## 0. 已核实的会议硬信息

| 项 | PAKDD 2027 | OCEANS 2027 Aberdeen |
| --- | --- | --- |
| 截稿 | **2026-11-20（AoE，≈北京时间11-21 20:00）** | **2027-01-15（摘要/论文提交）**，通知2027-03，终稿2027-05-24 |
| 会议 | 2027-06-29 ~ 07-02，新西兰惠灵顿 | 2027-06-21 ~ 24，英国阿伯丁 |
| 格式 | Springer LNCS/LNAI 模板，**12页含参考文献** | IEEE 双栏模板（惯例6~8页，以投稿门户为准，门户已开放） |
| 审稿 | **双盲** | 单盲（OCEANS惯例） |
| Track | **Applied Data Science（应用track）** | 六个本地track，主投 "Environmental Challenges and Solutions"（海洋污染），备选 "Digital Innovation in Oceans"（AI） |
| 录用率参考 | 全会历史15%~30%，应用track通常友好 | OCEANS惯例约40%~50%，系统+应用论文友好 |

⚠️ OCEANS 注意：1月15日虽叫 "abstract deadline"，OCEANS 惯例是**届时需提交完整论文**，摘要只是登记——按"1月中旬前完成全文"规划，不要赌。

## 1. 时间线（倒排）

> **进度（2026-10-26 终版 v2·含重大更正）**：
> ⚠️ **发现并修复基准 id 冲突事故**（306题仅22个唯一id→逐题分析全被污染，v1/v2/v3 旧数字全部作废；
> 详见 `artifacts/knowledge-retrieval-eval/ID_COLLISION_CORRECTION_20261026.md`，yaml 已追加更正段，
> 华为比赛材料若引用旧检索数字需按此更新）。
> 修复+全量重跑后：**新叙事**——无单一配置全能（BM25 标题型 hit@1 .901 称霸 / 图扩展实体 .930+多跳 .983 称霸 /
> 稠密+精排全题型显著垫底）+ **两系统规则路由器**（标题覆盖≥0.5→BM25，其余→图扩展）显著胜过所有单一配置
> 且与逐题型 oracle 无显著差异（p=0.10）+ 拒答无任何配置可分。
> PAKDD `main.pdf` **11页/0错误/0溢出**，`verify_numbers.py` **77 项对账全过**；OCEANS `main.pdf` 5页全绿（数字不受影响）。
> 匿名包 `artifact_anon.zip` 已按更正后产物重建+扫描通过。
> 剩余**用户侧**：通读润色终审、OCEANS 合作者名单/邮箱、上传匿名仓库替换脚注链接、
> EasyChair/OCEANS 门户注册提交、**华为材料数字口径更新**、11-09 华为ICT报名（红色待办）。

```
10-26 ─── 11-09 ────────── 11-20 ───────────── 12月 ────── 01-15 ──── 03月
  │         │               │                   │           │          │
  实验+初稿✅  华为ICT报名截止   PAKDD全文截稿        OCEANS补refs    OCEANS截稿   OCEANS通知
  (已完成)   (唯一红色待办!)   (目标11-18前交)    /图/作者信息
```

### PAKDD 冲刺（10-26 → 11-20，25天）
- **W1（10/26~11/01）补实验、冻结数字**（见 §2 缺口清单，这是唯一可能翻车的环节）
- **W2（11/02~11/08）英文全文初稿**（骨架已备好：`pakdd2027/outline.md`）
- **W3（11/09~11/15）打磨**；11/09前后几天同时处理华为ICT报名确认，写作让路
- **11/16~11/20 格式检查+双盲匿名化，至少提前2天提交**

### OCEANS（11月下旬 → 01-15，时间充裕）
- 11月下旬~12月：按 `oceans2027/outline.md` 写全文（PAKDD投稿后立即开始）
- 01月上旬：内审、格式、提交
- 03月出结果后：如录用，规划英国行程（签证周期）；PAKDD如录用同步规划新西兰签证

## 2. PAKDD 投稿前必须补的实验（W1任务）——✅ 全部完成（2026-10-26）

1. ✅ **306题重跑**——已由并行会话完成（MaaS 429 退避导致约4小时，全部留缓存可复算）。**论文数字唯一源=冻结快照 `artifacts/knowledge-retrieval-eval/eval_306_snapshot.json`**（本体 ont_20261025131815，27资产/306题）。旧190题结果备份于 `latest_190_20261025.json`；v1/v2 两轮已并列登记在 R-KN-07_benchmark.yaml，**不可互比**。
2. ✅ **纯BM25消融**——`scripts/run_bm25_ablation.py` → `bm25_ablation.json`（多跳 7.5% vs 图扩展 47.5%；标题型 45.7% 反超基线 43.2%）。
3. ✅ **显著性检验**——`scripts/compute_significance.py` → `significance.json` + `main_table.md`（Wilcoxon 符号秩、逐题倒数排名配对、双侧；图扩展多跳 p=3.3e-06，BM25 标题型 p=0.015 显著最优）。
4. ✅ **本体证据审计**——27文档重跑 → `artifacts/ontology-evidence-audit/latest.json`：引用逐字可回溯 89.9%（302/336）、关系端点 90%、关系完全可回溯 85%（170/200）、节点名 96%。

**叙事变化（重要）**：新基准难得多，旧故事（多跳100%、稠密+33pt）在 v2 上不成立。新故事更强也更诚实：**没有全能配置**（标题型BM25显著最好 / 多跳图扩展+40pt显著 / 稠密+精排在近同构公文上显著最差）+ oracle 路由上限 + 拒答阈值跨配置三态（可分/反转/重叠）。详见 `pakdd2027/outline.md`（已按新数字重写）。
注意：并行会话仍在迭代检索配置（v3 标题加权已进生产 HybridIndex）；论文表格一律引用冻结快照，不追新数字。华为比赛材料引用的是 v1 数字，yaml 保留两轮口径，无冲突。

## 3. 写作纪律（两篇通用）

- 所有数字回到事实源：`artifacts/knowledge-retrieval-eval/latest.json`（PAKDD）、`docs/competitions/public-floatwaste-benchmark.md`（OCEANS感知部分），与比赛材料同口径。
- 检测精度只能写"第三方公开基准独立评测"，禁止"现场验证/实测精度"。
- 负结果如实写（拒答分数不可分离、连江本地测试集为空）——这是卖点不是短板。
- 英文写作，术语统一：auditable governance agent / evidence-audited ontology / type-stratified benchmark / score-based abstention。

## 4. 风险与兜底

- PAKDD被拒 → 转投：CCKS 2027（约5月截稿，最对口）、NLPCC 2027（约6月）、ARR（滚动）。改投时按审稿意见补强即可。
- OCEANS被拒 → 转投：OCEANS 2027亚太场（如有）、IGARSS 2028、Ocean & Coastal Management（期刊）。
- 两篇都不影响华为ICT比赛（11-9报名、后续评审）——论文反而可写进材料3知识产权/成果栏（如实标注"在投"）。
