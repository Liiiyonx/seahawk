# PAKDD 2027 论文骨架（Applied Data Science Track）

> 截稿 **2026-11-20 AoE**。Springer LNCS 模板，**12页含参考文献**，双盲。
> 源材料：`artifacts/knowledge-retrieval-eval/`（**eval_306_snapshot.json = 论文唯一数字源（冻结快照）**、bm25_ablation.json、significance.json、benchmark.json）、`scripts/build_retrieval_benchmark.py`、`scripts/run_retrieval_eval.py`、`scripts/run_bm25_ablation.py`、`scripts/compute_significance.py`、`scripts/ontology_evidence_audit.py`、`backend/app/services/knowledge*.py`。

## ⚠️ 数据快照纪律（2026-10-26 起生效）

- 论文所有主表数字取自 **`eval_306_snapshot.json`**（冻结自 latest.json 2026-10-25T16:32Z 运行，本体 ont_20261025131815，27资产/306题）。检索配置仍在迭代（v3 标题加权已进生产 HybridIndex），**表格一律引用冻结快照，正文注明配置版本**。
- **v1（15资产/190题）与 v2（27资产/306题）不可互比**（语料与题集都变了，yaml 已登记）。
- single2 存在跨轮波动（0.01~0.11，嵌入缓存批间差异，yaml honest_note 已登记）——论文以相对关系与显著性为准，不强调绝对值小数点。
- 拒答池仅 5 题，如实声明为限制。

## 工作标题（三选一）

1. **Ask the Regulations: A Type-Stratified Study of Hybrid Retrieval over Small Domain Corpora with Evidence-Audited Ontologies**
2. Small Corpus, Hard Questions: Benchmarking Lexical, Dense, and Graph-Expanded Retrieval for Regulatory QA
3. No Single Retriever Wins: Type-Stratified Evaluation and Routing over a Small Regulatory Corpus

v2 结果后推荐 **#1 或 #3**：新叙事核心是"没有全能配置、按题型路由 + 证据审计本体"。

## 摘要草稿（EN，按 306 快照重写）

> Retrieval-augmented systems deployed in regulated domains face a reality rarely discussed in benchmark papers: the corpus is small and grows organically, queries fall into sharply different types, and every answer must be traceable to authoritative text. We study this regime on a corpus of 27 Chinese marine-dumping regulatory documents from the national environmental authority. We first construct a domain ontology (100 nodes, 200 relations) in which every LLM-extracted node and relation must cite its supporting passage, and we audit the evidence chain: 96% of node names and 85% of relations are fully traceable to cited source text, and 89.9% of citations verify verbatim. Second, we build a 306-question type-stratified benchmark (title-lookup, entity/content, multi-hop, refusal) with deterministic gold answers. Third, we compare six retrieval configurations and find that **no single configuration wins across query types**: plain BM25 is significantly best on title queries; graph-expanded lexical retrieval is decisively best on multi-hop queries (47.5% vs 7.5% hit@5, p<1e-5); and dense retrieval with a cross-encoder reranker — often assumed superior — is significantly worst on this corpus of near-duplicate regulatory documents. An oracle that routes each query type to its best configuration bounds the achievable gain. On abstention, score thresholds that cleanly separate answerable from unanswerable queries under one configuration fail or invert under others, cautioning against score-based refusal in small-corpus deployments. We release the benchmark, audit tooling, and all configurations.

（中文大意：小领域语料下按题型分层评测六配置；本体证据审计 96%/85%/89.9%；核心发现=没有全能配置（标题型BM25显著最好/多跳图扩展显著最好/稠密+精排在近同构公文语料上显著最差）；oracle 路由给出上限；拒答阈值跨配置脆弱。）

## 贡献点（Introduction 末尾列条）

1. **Evidence-audit framework**：LLM 抽取本体的"证据可回溯"度量与审计流程（27文档上：引用逐字可回溯 89.9%（302/336）、关系端点可回溯 90%、关系完全可回溯 85%（170/200）、节点名可回溯 96%）。
2. **Type-stratified benchmark**：306题、四题型（title 81 / entity-content 100 / multi-hop 120 / refusal 5）、确定性金标准（零模型调用构建）、语料增长模拟（v1 15资产 → v2 27资产，记录难度漂移）。
3. **Controlled comparison with significance**：六配置 × 题型 + 逐题配对 Wilcoxon（`significance.json`）。核心发现：**没有全能配置**——图扩展在多跳上 +40pt（47.5% vs 7.5%，p=3.3e-06）但在标题型上显著**低于**纯 BM25（p=0.015）；稠密+cross-encoder 精排全面显著最差（近同构公文语料负结果，反驳"稠密精排默认更强"的直觉）。
4. **Routing upper bound & abstention fragility**：oracle 路由（多跳走图扩展、其余走混合）单跳全面不损失且多跳保持最强；拒答分数阈值仅在图扩展词法配置下可分（67.5 vs 46.5），在纯 BM25 下**反转**（拒答题分反而更高 9.0→13.7）、在稠密下重叠——基于分数的拒答在小语料部署不可靠。
5. 开源：基准、六个配置、审计与显著性工具（匿名链接）。

## 章节与页数预算（12页含refs）

| 节 | 内容 | 页 |
| --- | --- | --- |
| 1 Introduction | 小语料监管域 regime 三现实（小语料/异型查询/可追溯）；四贡献 | 1.5 |
| 2 Related Work | hybrid retrieval / KG-augmented RAG / domain ontology construction / retrieval abstention / query routing | 1 |
| 3 Corpus & Audited Ontology | 语料27份（生态环境部两专栏公开文件+演示资产）；抽取协议（每节点/关系必须引用）；审计定义与结果表；诚实边界（非专家金标准） | 2 |
| 4 Benchmark | 四题型设计动机与确定性构造（build_retrieval_benchmark.py：模板固定、gold 取自本体/资产表、零模型调用）；构成表；v1→v2 语料增长与难度漂移记录 | 1.5 |
| 5 Retrieval Configurations | bm25（字符二元切分、无图）/ 词法+图（生产 /knowledge/search，标题x6/正文x1.5/标准号x2 + hop_depth=1 图扩展）/ dense（BGE-M3, pool 30）+ rerank（bge-reranker-v2-m3, top-20）/ RRF混合（k=60）/ 标题加权混合v3 / oracle路由 | 1.5 |
| 6 Results | 主表（6配置×3题型，冻结快照）；Wilcoxon 显著性矩阵；分型分析（图扩展多跳+40pt、BM25标题型反超、稠密退化机理=近同构公告稀释标题信号） | 2.5 |
| 7 Routing & Abstention | oracle 路由上限；拒答阈值跨配置脆弱性（可分/反转/重叠三态） | 1 |
| 8 Discussion & Limitations | 单领域/单语言；拒答池5题；single2 跨轮波动；oracle 需真实路由器（未来工作：题型分类器） | 0.5 |
| 9 Conclusion | — | 0.25 |
| References | ~20-25条 | 1 |

## 主结果表（数字=eval_306_snapshot.json，已核对）

**Table 3 主结果**（hit@5 / MRR；**加粗=该列显著最优**；完整版+显著性矩阵在 `main_table.md`）：

| Config | title hit@5 / MRR | content hit@5 / MRR | multihop hit@5 / MRR |
| --- | --- | --- | --- |
| BM25（无图） | **0.457** / 0.302 | 0.180 / 0.164 | 0.075 / 0.135 |
| Lexical+graph（生产） | 0.432 / 0.254 | 0.310 / 0.229 | **0.475** / 0.469 |
| Dense+rerank（BGE-M3+V2-M3） | 0.222 / 0.138 | 0.190 / 0.091 | 0.458 / 0.267 |
| RRF hybrid | 0.432 / 0.284 | 0.380 / 0.186 | 0.458 / 0.198 |
| Hybrid v3（标题加权稠密） | 0.444 / 0.278 | **0.410** / 0.186 | 0.458 / 0.198 |
| Oracle routing | 0.444 / 0.278 | **0.410** / 0.186 | **0.475** / 0.469 |

关键显著性（Wilcoxon 符号秩，逐题倒数排名配对，双侧）：
- 多跳：baseline vs bm25 p=3.3e-06（图扩展+40pt 成立）；baseline vs hybrid_rrf p=2.3e-10（RRF 在多跳上反而**伤害**图扩展——融合被稠密噪声污染，值得一提）
- 标题型：bm25 vs baseline p=0.0148（纯词法显著更好）；所有配置 vs twostage 均 p<0.002
- 内容型：hybrid_v3 vs baseline p=0.299（不显著——best 配置间差距在噪声内，支持"需更大语料/题量"的诚实表述）

**Table 4 拒答三态**：lexical+graph **可分**（single_min 67.5 > refuse_max 46.5）；BM25 **反转**（9.0 < 13.7，拒答题分更高）；dense **重叠**（0.0008 / 0.0031）。结论升级：分数阈值拒答不仅"不可靠"而是"跨配置行为不一致"，部署建议=证据覆盖判定（现有 QA 层设计一致）。

**Figure 1** 审计流程图；**Figure 2** 拒答分数分布三态图（可分/反转/重叠一图讲完）。

## 双盲注意事项

- 匿名：学校/队名/仓库/姓名/GitHub 全部去除；致谢段删掉。
- 代码与数据：anonymous.4open.science 或 Zenodo 匿名链接，提交前建好。
- 语料为生态环境部公开文件，保留官方出处（公开文件引用不破坏匿名）。

## W1 实验清单（2026-10-26 全部完成 ✅）

1. ✅ 306题重跑（评测运行 ~4h 因 MaaS 429 退避；全部留缓存可复算；快照冻结为 eval_306_snapshot.json）
2. ✅ BM25 纯词法消融（`scripts/run_bm25_ablation.py` → bm25_ablation.json）
3. ✅ Wilcoxon 显著性（`scripts/compute_significance.py` → significance.json + main_table.md）
4. ✅ 本体证据审计 27 文档重跑（`scripts/ontology_evidence_audit.py` → artifacts/ontology-evidence-audit/latest.json：引用 89.9% / 端点 90% / 关系 85% / 节点 96%）

剩余写作期任务：英文化全文（按本骨架）、匿名化、匿名仓库、11-16 前内审、**11-18 前提交**（留2天缓冲）。
