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

```
10-26 ─── 11-09 ────────── 11-20 ───────────── 12月 ────── 01-15 ──── 03月
  │         │               │                   │           │          │
  开始PAKDD  华为ICT报名截止   PAKDD全文截稿        写OCEANS     OCEANS截稿   OCEANS通知
  补实验     (唯一红色待办!)   (目标11-18前交)      全文初稿
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

## 2. PAKDD 投稿前必须补的实验（W1任务）

1. **在306题新版基准上重跑全部评测**——`latest.json` 目前是旧190题版（45+60+80+5），`benchmark.json` 已重建为306题（81+100+120+5），论文数字必须统一到新版。入口：`scripts/run_retrieval_eval.py`。
2. **补干净消融**——现在的 "baseline" 是生产系统（含本体图扩展），审稿人会问图扩展本身的贡献。需加一行 **纯词法（BM25，无图扩展）** 作对照，形成：BM25 / BM25+图 / 稠密两阶段 / RRF混合 四行主表。
3. **显著性检验**——按题配对做 Wilcoxon 符号秩或 bootstrap（逐题 rank 已在 per_item 里，现成）。
4. **本体证据审计重跑+落档**——`scripts/ontology_evidence_audit.py`（未提交）在20份语料/100节点/200关系当前版本上重跑，把 89.9%/85%/96% 口径的当前值写进 artifacts 并提交脚本。
5. **双盲匿名化**——去掉福州理工学院/潮汐守望/GitHub Liiiyonx/seasight 等一切身份信息，代码链接用匿名仓库（如 Zenodo匿名/anonymous.4open.science）。

## 3. 写作纪律（两篇通用）

- 所有数字回到事实源：`artifacts/knowledge-retrieval-eval/latest.json`（PAKDD）、`docs/competitions/public-floatwaste-benchmark.md`（OCEANS感知部分），与比赛材料同口径。
- 检测精度只能写"第三方公开基准独立评测"，禁止"现场验证/实测精度"。
- 负结果如实写（拒答分数不可分离、连江本地测试集为空）——这是卖点不是短板。
- 英文写作，术语统一：auditable governance agent / evidence-audited ontology / type-stratified benchmark / score-based abstention。

## 4. 风险与兜底

- PAKDD被拒 → 转投：CCKS 2027（约5月截稿，最对口）、NLPCC 2027（约6月）、ARR（滚动）。改投时按审稿意见补强即可。
- OCEANS被拒 → 转投：OCEANS 2027亚太场（如有）、IGARSS 2028、Ocean & Coastal Management（期刊）。
- 两篇都不影响华为ICT比赛（11-9报名、后续评审）——论文反而可写进材料3知识产权/成果栏（如实标注"在投"）。
