# PAKDD 2027 投稿包（Applied Data Science Track）

> 截稿 **2026-11-20 AoE**。LNCS 模板 12页含参考文献，双盲。
> 会议：2027-06-29~07-02 惠灵顿。入口 https://pakdd2027.org（EasyChair 投稿）。

## 文件

| 文件 | 作用 |
| --- | --- |
| `main.tex` | 论文全文英文初稿（含全部真实数字表格与文内引用） |
| `outline.md` | 骨架+数字口径+叙事（中文，写作参考） |
| `../PLAN.md` | 双轨总计划 |

## 编译（本机无 LaTeX，用 Overleaf）

1. Overleaf 新建项目 → 上传 `main.tex`。
2. 菜单 Setting → Compiler `pdfLaTeX`。
3. LNCS 作者工具：Springer 官网下载 `llncs.zip`，把 `llncs.cls`（和 `splncs04.bst`）一起上传。Overleaf 也常自带（New Project → Article → 模板搜 "LNCS"）。
4. 编译两遍出交叉引用。页数目标 ≤12（当前初稿约10~11页，有余量）。

## 提交前 checklist（按 PLAN.md 时间线，11-16 内审 / 11-18 前提交）

- [ ] 数字复核：正文每个数字回 `eval_306_snapshot.json` / `bm25_ablation.json` / `significance.json` / `ontology-evidence-audit/latest.json`
- [ ] 显著性表 `Table 4` 的 p 值核对 `significance.json`
- [ ] 建匿名仓库（anonymous.4open.science），替换 main.tex 脚注占位链接；仓库内容=benchmark.json + 4个脚本 + 快照（去掉任何身份信息、`.env`、中文路径）
- [ ] 双盲自查：无校名/队名/人名/GitHub/致谢；`git log` 类信息不带入
- [ ] 英文母语化润色一轮（重点：Abstract、Intro、F2 段）
- [ ] EasyChair 注册 + 提交（留2天缓冲）
- [ ] 作者顺序与单位信息（录用后填，投稿时保持匿名）

## 叙事一句话

小语料监管域没有全能检索配置：标题型 BM25 显著最好、多跳图扩展 +40pt 显著最好、稠密+精排在近同构公文上显著最差；oracle 路由给上限；分数阈值拒答跨配置三态（可分/反转/重叠）。
