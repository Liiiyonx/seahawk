# 证据入库（evidence-inbox）

> 配套政策：《docs/evidence-claim-policy.md》
> 配套工具：`scripts/evidence_registry.py`（登记表）、`scripts/check_claims.py`（扫描器）
> 本目录存放**待复核的外部证据登记条目**（YAML）。已复核并入登记表的证据进入
> `scripts/evidence_registry.py` 内嵌登记表；本目录只是入库通道，不是唯一事实源。

---

## 1. 入库流程

```text
1. 取得真实证据原件/记录（访谈记录、询价单、政策原文、现场记录、合同回款凭证）
   ↓
2. 复制 intake_template.yaml 为新文件：docs/evidence-inbox/YYYY-MM-DD-主题.yaml
   （不要直接修改 intake_template.yaml，它只是模板）
   ↓
3. 填写 8 个必填字段 + 选填 rule/matches/notes（字段口径见第 3 节）
   ↓
4. 本地校验：
      .\.venv-analysis\Scripts\python.exe scripts\evidence_registry.py --registry docs\evidence-inbox\YYYY-MM-DD-主题.yaml --validate
   校验失败（缺字段 / 非法等级 / 非法来源类型 / id 重复）必须修到通过
   ↓
5. 提交给总控：总控复核原件、核对等级与口径后，把条目并入
   scripts/evidence_registry.py 的登记表（可同时配置 rule/matches 豁免锚点）
   ↓
6. 总控运行扫描验证：
      .\.venv-analysis\Scripts\python.exe scripts\check_claims.py --root .
   确认退出码 0 后，材料修改才由总控执行
```

## 2. 谁可以入库

任何团队成员都可以提交条目，但**只有总控复核后条目才生效**。提交时必须自证：

- 证据原件可复现（文件路径、链接、单据编号可打开核对）。
- 等级没有虚标：E3 必须对应真实设备/真实海域/真实用户验证；E4 必须对应合同、回款、验收或复购凭证。
- 来源类型从受控集合中选择，不得自造类型。

## 3. 字段口径（与 evidence_registry.py 的 EvidenceRecord 严格对齐）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 唯一编号。推荐前缀：F-（外部公开事实）、C-（内部测算）、R-（纪律/口径）、EV-（新入库条目） |
| `claim` | 是 | 宣称原文或事实描述，写清楚口径与边界 |
| `evidence_level` | 是 | E0 / E1 / E2 / E3 / E4（定义见政策文档第 1 节） |
| `source_type` | 是 | 受控集合：`public_fact`、`internal_calculation`、`interview`、`inquiry`、`policy_document`、`contract`、`receipt`、`acceptance`、`test_report`、`field_record`、`assumption`、`other` |
| `source_ref` | 是 | 可复核来源（文件路径 / 链接 / 单据编号），不得写“无” |
| `captured_at` | 是 | 证据获取或形成日期，格式 YYYY-MM-DD |
| `review_status` | 是 | 待复核 / 复核中 / 已复核 |
| `owner` | 是 | 责任人 |
| `rule` | 否 | 豁免哪条红线（`check_claims.py` 的 rule_id），如 `seventy_six_as_accuracy` |
| `matches` | 否 | 豁免锚点子串列表：claim 之外的等价表述，命中即豁免 |
| `notes` | 否 | 口径、边界或待办说明 |

`rule` / `matches` 的用途示例：登记记录 `R-76-01` 声明「76% 只是时序链路误报抑制率」，`check_claims.py` 遇到含「时序链路误报抑制率」的行即豁免 `seventy_six_as_accuracy`，76% 不再被当作识别精度；**扫描器允许登记豁免，不靠关键词一刀切。**

## 4. 校验与红线自检

- 校验命令见第 1 节第 4 步；通过后退出码为 0。
- 新条目写入本目录后会被 `check_claims.py --root .` 扫描（`.yaml` 在扫描范围）。
  提交的条目文本请保持干净：数字带来源或自限措辞，成交措辞带凭证编号。
- 自测门禁：任何改动登记表或扫描器后运行
  `.\.venv-analysis\Scripts\python.exe scripts\selftest_evidence_gate.py`，
  必须 SELFTEST PASS。

## 5. 目录约定

- `intake_template.yaml`：模板，勿改。
- `YYYY-MM-DD-主题.yaml`：待复核条目，由总控复核后并入登记表；已并入的条目由总控决定归档。
- 证据原件（扫描件、录音、截图）不强制入库本目录，但 `source_ref` 必须指向其可访问位置。
