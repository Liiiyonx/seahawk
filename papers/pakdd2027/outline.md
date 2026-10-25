# PAKDD 2027 论文骨架（Applied Data Science Track）

> 截稿 **2026-11-20 AoE**。Springer LNCS 模板，**12页含参考文献**，双盲。
> 源材料：`artifacts/knowledge-retrieval-eval/`（benchmark.json / latest.json / rerank_cache.json）、`scripts/build_retrieval_benchmark.py`、`scripts/run_retrieval_eval.py`、`scripts/ontology_evidence_audit.py`、`backend/app/services/knowledge*.py`。

## 工作标题（三选一）

1. **Ask the Regulations: A Type-Stratified Study of Hybrid Retrieval over Small Domain Corpora with Evidence-Audited Ontologies**
2. Small Corpus, Hard Questions: Benchmarking Lexical, Dense, and Graph-Expanded Retrieval for Regulatory QA
3. An Evidence-Audited Domain Ontology and a Type-Stratified Benchmark for Retrieval over Regulatory Corpora

推荐 #1：问题导向、卖点全在标题里（小语料、分型基准、证据审计本体）。

## 摘要草稿（EN，写作用）

> Retrieval-augmented systems deployed in regulated domains face a reality rarely discussed in benchmark papers: the corpus is small (tens of documents), queries fall into sharply different types, and every answer must be traceable to authoritative text. We study this regime on a corpus of 20 Chinese marine-dumping regulatory documents from the national environmental authority. We first construct a domain ontology (100 nodes, 200 relations) in which every node and relation extracted by an LLM must cite its supporting passage, and we audit this evidence chain, finding 96% of nodes and 85% of relations fully traceable. Second, we build a 306-question type-stratified benchmark (title-lookup, entity/content, multi-hop, and refusal queries) with frozen gold answers. Third, we conduct a controlled comparison of four retrieval configurations: lexical (BM25), lexical with ontology-graph expansion, two-stage dense retrieval (BGE-M3 + reranker), and their RRF hybrid. Graph expansion is the only configuration reaching 100% hit@5 on multi-hop queries; the two-stage dense pipeline improves content queries by +33 points hit@5; the hybrid recovers most of both. We further report a negative result: no score threshold separates answerable from unanswerable queries on a corpus of this scale, challenging score-based abstention. We release the benchmark, audit tooling, and configurations.

（中文大意：小领域语料下，按查询类型分层评测词法/图扩展/稠密/混合四配置；本体每条知识带证据引用并审计；报告拒答阈值不可分离的负结果；开源基准与审计工具。）

## 贡献点（Introduction 末尾列条）

1. **Evidence-audit framework**：LLM 抽取本体的"证据可回溯"度量与审计流程（节点96%/关系85%可回溯，引用率89.9%——数字以重跑后为准）。
2. **Type-stratified benchmark**：306题、四题型（title 81 / entity-content 100 / multi-hop 120 / refusal 5）、冻结gold、构造过程透明可复现。
3. **Controlled comparison**：四种检索配置 × 题型分层的对照实验（含 BM25 纯词法消融——待补），揭示小语料 regime 下没有全能配置、图扩展是多跳护城河（100% hit@5）、稠密+reranker 是内容题冠军（+33pt）。
4. **Negative result on abstention**：分数阈值在小语料上无法分离可答/拒答（`separated: false`），对 RAG 拒答实践提出警示。
5. 开源：基准、评测脚本、审计脚本、配置（匿名链接）。

## 章节与页数预算（12页含refs）

| 节 | 内容 | 页 |
| --- | --- | --- |
| 1 Introduction | 小语料监管域regime的三个现实；四贡献 | 1.5 |
| 2 Related Work | hybrid retrieval / KG-augmented RAG / domain ontology construction / retrieval abstention | 1 |
| 3 Corpus & Audited Ontology | 语料20份；抽取协议（每节点/关系必须引用）；审计定义（cite rate / node traceability / relation traceability）；审计结果表 | 2 |
| 4 Benchmark | 四题型设计动机与构造流程（build_retrieval_benchmark.py 的规则，含为什么不用随机切分）；构成表；冻结与复现 | 1.5 |
| 5 Retrieval Configurations | BM25 / +graph expansion / dense(BGE-M3, pool 30) + rerank(bge-reranker-v2-m3, 20) / RRF；chunk 800 | 1 |
| 6 Results | 主表（4配置×4题型×hit@1/3/5/MRR）；分型分析；显著性 | 2.5 |
| 7 Abstention Analysis | 分数分布重叠图；cutoff 不可行的定量论证 | 1 |
| 8 Discussion & Limitations | 单领域/单语言；语料规模；5题refuse偏少（如实声明）；对部署者的选型建议 | 0.5 |
| 9 Conclusion | — | 0.25 |
| References | ~20-25条 | 1 |

## 表格设计（论文核心资产）

**Table 1 语料与本体统计**：documents 20 / chunks / nodes 100 / relations 200 / citation rate / node traceability / relation traceability。

**Table 2 基准构成**：题型 × 数量 × 示例（脱敏示例1条/题型）。

**Table 3 主结果**（数字=当前190题版，**投稿前必须换成306版重跑+加BM25行+显著性标记**）：

| Config | title hit@5 | content hit@5 | multihop hit@5 | MRR(内容) | MRR(多跳) |
| --- | --- | --- | --- | --- | --- |
| BM25 (纯词法, **待补**) | – | – | – | – | – |
| BM25 + graph | 0.711 | 0.533 | **1.000** | 0.416 | 0.772 |
| Dense+Rerank | 0.644 | **0.867** | 0.700 | 0.498 | 0.716 |
| RRF hybrid | 0.711 | 0.633 | **1.000** | 0.478 | 0.764 |

**Table 4 拒答分析**：single_min_top1 vs refuse_max_top1（词法37.5/49.5；稠密0.0035/0.0079——注意稠密绝对值虽小但同样 `separated:false`，重叠是本质）。

**Figure 1** 系统/审计流程图；**Figure 2** 各题型分数分布重叠图（拒答分析用）。

## 双盲注意事项

- 匿名：学校/队名/仓库/姓名/GitHub 全部去除；致谢段删掉。
- 代码与数据：anonymous.4open.science 或 Zenodo 匿名链接，提交前建好。
- 引用自家比赛材料/软著的表述全部删除。
- ⚠️ 基准题目文本来自生态环境部公开文件，属公有语料引用，保留出处（官方文件引用不算破坏匿名）。

## W1 实验清单（冻结数字前必须完成）

1. 306题重跑四配置 → 新 `latest.json`（注意 commit 未提交的 benchmark 改动）。
2. 补 BM25 纯词法（无图扩展）行。
3. Wilcoxon 符号秩（逐题配对，per_item 已有 rank 数据）。
4. `ontology_evidence_audit.py` 在当前语料上重跑落档。
