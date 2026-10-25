# PAKDD 2027 投稿包（Applied Data Science Track）

> 截稿 **2026-11-20 AoE**。LNCS 模板 12页含参考文献，双盲。
> 会议：2027-06-29~07-02 惠灵顿。入口 https://pakdd2027.org（EasyChair 投稿）。

## 文件

| 文件 | 作用 |
| --- | --- |
| `main.tex` | 论文全文英文**定稿**（真实例题表、主结果/显著性、规则路由器、拒答三态图，id 更正后数字） |
| `main.pdf` | **本地编译：11页（≤12限额），0错误/0溢出/0未定义引用**（MiKTeX 25.12 实测） |
| `artifact_anon/` + `artifact_anon.zip` | **匿名产物包（id 更正后产物重建，含路由评测与更正说明；身份扫描通过）** |
| `../verify_numbers.py` | **自动数字对账：77 项检查全通过**（主表逐格、路由、审计、拒答、显著性 p 值、检测数字） |
| `outline.md` | 骨架+数字口径+叙事（中文，写作参考） |
| `../PLAN.md` | 双轨总计划 |

> 2026-10-26 极致化完成：MiKTeX（winget 安装）本地编译验证通过；新增 Table 7 语料难度漂移表（v1 190题/15资产 vs v2 306题/27资产，三处反转现象）；新增 Fig.1 拒答三态 pgfplots 图（对数轴真实分数区间：可分/反转/重叠一图呈现）；全部 overfull 修复；页面版心几何扫描 10 页全部一致无越界。

## 编译

本机已装 MiKTeX（`%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe`）：

```bash
cd papers/pakdd2027
pdflatex -interaction=nonstopmode main.tex && pdflatex -interaction=nonstopmode main.tex
```

Overleaf 同样可编（llncs.cls 会上传或用模板库）。页数余量：当前 10/12 页，还有 2 页空间可加相关工作的 domain benchmark 讨论或 case study。

## 提交前 checklist（按 PLAN.md 时间线，11-16 内审 / 11-18 前提交）

- [ ] 数字复核：正文每个数字回 `eval_306_snapshot.json` / `bm25_ablation.json` / `significance.json` / `ontology-evidence-audit/latest.json`
- [ ] 显著性表 `Table 5` 的 p 值核对 `significance.json`
- [x] ~~建匿名仓库~~（`artifact_anon.zip` 已组装+身份扫描通过；只剩上传到 anonymous.4open.science 并替换 main.tex 脚注占位链接）
- [ ] 双盲自查：无校名/队名/人名/GitHub/致谢；`git log` 类信息不带入
- [ ] 英文母语化润色一轮（重点：Abstract、Intro、F2 段）
- [ ] EasyChair 注册 + 提交（留2天缓冲）
- [ ] 作者顺序与单位信息（录用后填，投稿时保持匿名）

## 叙事一句话

小语料监管域没有全能检索配置：标题型 BM25 显著最好、多跳图扩展 +40pt 显著最好、稠密+精排在近同构公文上显著最差；oracle 路由给上限；分数阈值拒答跨配置三态（可分/反转/重叠）。
