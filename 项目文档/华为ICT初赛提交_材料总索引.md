# 华为 ICT 赛道三 · 初赛提交材料总索引

> 更新:2026-10-24(commit a4e0176,包 54 entries / 30.39 MB,门禁 exit 0)
> 用法:提交时按官方入口逐项上传;本索引是唯一入口地图。

---

## 一、直接提交的东西(按官方材料清单对应)

| 官方要求 | 文件在哪 | 说明 |
| --- | --- | --- |
| 开发设计文档(官方模板六节) | `dist/huawei-ict-track3-submission/01_开发设计文档.docx` | 已含 R-NX-08 完成/LLM 通道/问答工作台/开源;同源副本 `项目文档/华为ICT赛道三_开发设计文档.docx` |
| 智能体整体设计说明(材料2) | `dist/huawei-ict-track3-submission/02_Nexent智能体设计说明.docx` | 同源副本 `项目文档/华为ICT赛道三_Nexent智能体设计说明.docx` |
| 随附文件说明(json/知识库/MCP) | `dist/huawei-ict-track3-submission/03_附送文件说明.md` | 四类随附文件逐项说明+证据等级 |
| 示例问答截图 | `dist/huawei-ict-track3-submission/04_示例问答截图/`(8 张) | 本地 Nexent 控制台 2 张 + 知识域多跳 4 张 + **前端问答工作台 2 张(新)** |
| 证据包 | `dist/huawei-ict-track3-submission/05_证据包/`(26 项) | 全部登记号产物:R-NX-01~09/R-KN-01~06/R-LLM-01/02/R-OD-01~03/R-MG-01 |
| 标准映射表 | `dist/huawei-ict-track3-submission/06_标准映射表.md` | 标准体系对齐 |
| 演示视频 | `dist/huawei-ict-track3-submission/07_演示视频/探海灵眸Oceanus_演示视频.mp4` | 10-11 录制;**未含问答工作台与托管平台画面,建议重录** |
| 代码附件(MCP/Skills) | `dist/huawei-ict-track3-submission/integrations/` + `artifacts/` | MCP 服务端+5 个 SKILL.md |
| 整包 zip | `dist/huawei-ict-track3-submission.zip` | 54 entries / 30.39 MB;SHA256 见 `artifacts/huawei-track3-submission/latest.json` |
| 开源地址(入围硬条件) | https://github.com/Liiiyonx/seasight (commit f84e5c2) | 已过全部隐私门禁 |

## 二、底稿与维护链(改材料时改这里,不要改 docx)

```
docs/competitions/huawei-ict-track3-design-doc.md        ← 材料1 底稿
docs/competitions/huawei-ict-track3-agent-design.md      ← 材料2 底稿
docs/competitions/huawei-ict-track3-attachment-guide.md  ← 材料3 底稿
docs/competitions/huawei-ict-track3-submission-checklist.md ← 提交清单 v2.0
scripts/package_huawei_track3_submission.py              ← 一键重建整包
artifacts/huawei-track3-submission/latest.json           ← 包指纹(时间/条目/SHA256)
```

**改任何底稿后**:`python scripts/package_huawei_track3_submission.py` → 重建 docx+整包;宣称门禁 `python scripts/check_claims.py --root .` 必须 exit 0。

## 三、支撑材料(不随包提交,答辩/兜底用)

| 位置 | 内容 |
| --- | --- |
| `项目文档/真实数据获取/` | 话术×3 + 知情同意函 + 需求与脱敏说明(**待你发给联系人**) |
| `项目文档/商业证据台账.md`、`外部证据*.md` | 连江赛真实访谈/询价台账 |
| `artifacts/nexent-platform-acceptance/` | R-NX 全部原始登记(yaml+截图) |
| `docs/competitions/huawei-ict-track3-scoring-review.md` | 评委自评 v3.7(81/100)+答辩 Q&A 风险清单 |
| `docs/competitions/huawei-agentarts-vpc-target-runbook.md` | 托管平台修复全记录(§13.8-13.10) |

## 四、提交前人工待办(唯一剩下的)

1. **报名确认**(3 学生 + 1 指导教师,按学校/省通知截止)——最优先
2. **演示视频决策**:沿用 10-11 版,或重录(动线脚本找 AI 助手要)
3. **数据话术今天发出**(见 §三 第一行)
4. 向两个主办方确认连江赛/华为赛材料独立性(书面留痕)
