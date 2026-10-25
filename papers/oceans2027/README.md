# OCEANS 2027 Aberdeen 投稿包

> **2027-01-15** 摘要/论文截止（按届时需交全文准备！），通知 2027-03，终稿 2027-05-24，会议 2027-06-21~24 阿伯丁。
> 投稿门户 2026-10-01 已开放。Track 主投 Environmental Challenges and Solutions；备选 Digital Innovation in Oceans。

## 文件

| 文件 | 作用 |
| --- | --- |
| `main.tex` | 论文全文英文**定稿级**（TikZ 双图、MCP 21工具真实清单表、QA引用层+部署现状小节、10条真实参考文献、4位小数与事实源逐字对齐） |
| `main.pdf` | **本地编译：5页，0错误/0溢出/0警告**（MiKTeX 25.12 实测） |
| `../verify_numbers.py` | 检测数字对账：论文中每个检测数字与 `public-floatwaste-benchmark.md` 逐字核对通过 |

> 2026-10-26 极致化完成：补齐参考文献（YOLO-World CVPR'24、YOLO11、SC-FloatWaste Zenodo DOI、MCP、WasteShark/Clearbot、Gall&Thompson 2015 等10条，全部真实可查）；两张 TikZ 矢量图纯代码生成（Fig.1 三级闭环、Fig.2 决策管线含守卫拦截/审批/审计回放路径）；MCP 工具表按 `integrations/nexent/mcp_server/server.py` 源码逐条核实（知识7+证据链2+事件2+工单3+看板1+运行时6=21）；主结果表升为 table* 全宽。版心几何扫描通过。

## 编译

本机已装 MiKTeX：

```bash
cd papers/oceans2027
pdflatex -interaction=nonstopmode main.tex && pdflatex -interaction=nonstopmode main.tex
```

当前 4 页（IEEE 双栏很紧凑）；OCEANS 常规 6~8 页，后续加现场试验/更多讨论自然长到 5~6 页，无须注水。

## 提交前 checklist

- [x] ~~补参考文献~~（2026-10-26 已补齐 10 条）
- [ ] **补作者信息**：合作者名单/邮箱（OCEANS 单盲实名；tex 内 \todo 标记处）
- [x] ~~加图~~（TikZ Fig.1/Fig.2 已入 tex，矢量无需图片文件）
- [ ] 数字复核：全部检测数字回 `docs/competitions/public-floatwaste-benchmark.md`（唯一事实源）
- [ ] 口径红线自查（outline.md「写作红线」四条：不写国内首个/不写现场实测/本地测试集为空如实声明/76%时序指标不得混用）
- [ ] OCEANS 门户注册（IEEE账户）+ 提交；格式按门户要求（IEEE PDF eXpress 合规）
- [ ] 如录用：注册费 + 英国签证（学生签约3周，6月开会，4月内办）
