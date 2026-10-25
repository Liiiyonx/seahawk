# PAKDD 2027 论文骨架（Applied Data Science Track）

> 截稿 **2026-11-20 AoE**。Springer LNCS 模板，**12页含参考文献**，双盲。
> **状态：全文定稿（main.tex，11页编译0错），本文档保留作叙事与口径速查。**

## ⚠️ 数字口径（2026-10-26 id 冲突更正后）

- **一切数字以 `eval_306_snapshot.json`（更正后冻结快照）+ `bm25_ablation.json` + `significance.json` + `routing_eval.json` 为准**；`verify_numbers.py` 77 项对账机器背书。
- 旧 v1（190题）与污染期 v2/v3 数字全部作废（`ID_COLLISION_CORRECTION_20261026.md`），论文已删除漂移表。
- 拒答池 5 题，如实声明为限制。

## 工作标题（已定）

**Ask the Regulations: A Type-Stratified Study of Hybrid Retrieval over Small Domain Corpora with Evidence-Audited Ontologies**

## 核心叙事（更正后最终版）

小语料监管域 regime（20 份生态环境部公开文件 + 7 运行资产 / 306 题四题型 / 证据审计本体）：

1. **证据审计本体**（§3）：引用逐字可回溯 89.9%（302/336）、关系端点 90%、关系完全可回溯 85%、节点名 96%；确定性字符串核验，无模型无金标。
2. **无单一配置全能**（§6，F1）：BM25 称霸标题型（hit@1 **.901**，vs 图扩展 p=4.8e-8）；图扩展称霸实体（**.930**）与多跳（**.983**）；每个专家在对方地盘显著掉分。
3. **稠密+精排全题型显著最差**（F2）：近同构公文语料稀释判别词，cross-encoder 只能重排稠密 top-20；标题型 h@1=h@3=h@5=.481（金标要么第一要么不在候选窗）。
4. **融合是最强单系统但到不了专家**（F3）：RRF 把标题型 hit@1 .519→.815（保住多跳 .983），但显著低于两个专家——差距正是路由要吃的空间。
5. **两系统规则路由器 = oracle**（§7）：标题覆盖（字符二元重合≥0.5）→BM25，其余→图扩展；73/81 标题型正确路由；**显著优于全部单一配置（p<0.005），与逐题型 oracle 无显著差异（p=0.10）**——这个 regime 的自适应检索=两个索引+一个字符串信号。
6. **拒答无配置可分**（§7/Fig.1）：词法零分地板重叠（4 道可答题 0 分）/ BM25 反转 / 稠密低尾重叠；生产 QA 层按证据覆盖拒答。
7. **部署 regime 会让基准老化**（F4）：语料随系统建设有机生长，题型分层报告让漂移可见。

## 论文最终结构（main.tex 实际）

| 节 | 内容 | 表/图 |
| --- | --- | --- |
| 1 Intro | 3 RQ + 6 贡献 | — |
| 2 Related | hybrid/KG-RAG/LLM构建与可验证/拒答（17条文献） | — |
| 3 Corpus & Audit | 27资产；强制引用协议；确定性审计 | T1 审计 |
| 4 Benchmark | 四题型确定性构造；真题表 | T2 构成, T3 例题 |
| 5 Configs | BM25/词法图/稠密精排/RRF/TB/规则路由 | T4 配置 |
| 6 Results | 主表+Wilcoxon矩阵；F1-F4 | T5 主表, T6 显著性 |
| 7 Router & Abstention | 路由器≈oracle；拒答三态 | T7 拒答, F1 分数分布图 |
| 8-9 | Limitations / Conclusion + 可复现声明（含 id bug 披露） | — |

## 双盲注意事项

- 匿名：学校/队名/仓库/姓名/GitHub 全部去除；代码与数据走匿名链接。
- `artifact_anon.zip` 已按更正后产物重建+身份扫描通过，上传 anonymous.4open.science 后替换 main.tex 脚注。

## 提交前剩余

1. 上传匿名包 → 替换 main.tex 脚注占位链接
2. 英文通读终审（重点 Abstract/Intro/F1-F3）
3. EasyChair 注册+提交（11-18 前留缓冲）
4. 录用后填作者信息
