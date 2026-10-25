# OCEANS 2027 Aberdeen 投稿包

> **2027-01-15** 摘要/论文截止（按届时需交全文准备！），通知 2027-03，终稿 2027-05-24，会议 2027-06-21~24 阿伯丁。
> 投稿门户 2026-10-01 已开放。Track 主投 Environmental Challenges and Solutions；备选 Digital Innovation in Oceans。

## 文件

| 文件 | 作用 |
| --- | --- |
| `main.tex` | 论文全文英文初稿（IEEEtran，检测数字全部来自 public-floatwaste-benchmark.md） |
| `outline.md` | 骨架+口径红线（中文） |
| `../PLAN.md` | 双轨总计划 |

## 编译

Overleaf：IEEEtran 模板自带。上传 `main.tex`，pdfLaTeX 编译两遍。目标 6~8 页（当前初稿约 6 页文字+表，加参考文献约 7 页）。

## 提交前 checklist

- [ ] **补参考文献**：main.tex 尾部 TODO 列了清单（监测网络、WasteShark/Clearbot、YOLO-World、YOLO11、MCP 规范、SC-FloatWaste 的 Zenodo DOI 10.5281/zenodo.21934286）
- [ ] **补作者信息**：作者列表/单位/邮箱（OCEANS 单盲，实名）
- [ ] 加图：Fig.1 三级闭环架构图、Fig.2 决策管线时序图（可从 `scripts/make_huawei_track3_polish_figures.py` 的示意图改英文版）
- [ ] 数字复核：全部检测数字回 `docs/competitions/public-floatwaste-benchmark.md`（唯一事实源）
- [ ] 口径红线自查（outline.md「写作红线」四条：不写国内首个/不写现场实测/本地测试集为空如实声明/76%时序指标不得混用）
- [ ] OCEANS 门户注册（IEEE账户）+ 提交；格式按门户要求（IEEE PDF eXpress 合规）
- [ ] 如录用：注册费 + 英国签证（学生签约3周，6月开会，4月内办）
