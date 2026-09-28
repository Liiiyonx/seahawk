# 四项扣分点 · 收口计划（2026-09-27 深夜核实）

> 逐条核实过，**没有一条是猜的**：每条都给出仓库里的证据位置。
> 明确区分：**【已做】= 本轮已完成并有验证证据；【只能你做】= 需要真人/真资源，工具替代不了。**

---

## 总览

| # | 扣分点 | 是否存在 | 状态 | 谁能做 |
| --- | --- | --- | --- | --- |
| 1 | 真实精度数字 | ✅ 存在 | 管线已就绪，**只缺数据** | 采集只能你做；SOP 我已写好 |
| 2 | 真实验证证据 | ✅ 存在 | 模板齐备，**只欠执行** | 访谈/意向函只能你做 |
| 3 | 华为实线加粗 | ✅ 存在 | 全仓无凭据/无硬件，**方案级未实测** | 实跑只能你做；runbook 我已写好 |
| 4 | 演示时 500 报错 | ✅ 存在 | **【已做】已修复并验证** | 已闭环 |

---

## 1. 真实精度数字（两赛共扣 4–6 分）

**核实**：`ml/configs/seasight.yaml` 的 `stats` 全 0（train/val/background/instances 均为 0），
`ml/datasets/manifests/` 只有模板。**"0 张标注"属实。**

**不造假的判断是对的**：评测脚本 `ml/scripts/evaluate_opencv.py` 带清单门禁，
数据未就绪时输出 `not_evaluated`（退出码 0）而不是编数字——这正是评审认可的点。

**【只能你做】采集 + 标注**。最小可辩护规模（独立测试集，**不参与任何训练**）：

| 项 | 建议量 | 说明 |
| --- | --- | --- |
| 每类目标 | ≥ 30 张含该类的图 | 低于 30 的单类 P/R 置信区间过宽，评审会质疑 |
| 四类合计 | ≥ 120 张 | foam / plastic / fishing_gear / other |
| 背景图（无目标） | ≥ 20 张 | 用来算误报，缺这批就只能报 P/R 不能报 FP 率 |
| 拍摄条件 | ≥ 2 个点位 × 2 种光照 | 否则"光照/背景"分层做不了 |

**【已做】采集后的机械路径**（照抄即可，全仓库现成工具）：

```text
① 拍照/收集 → ml/datasets/seasight/<批次>/images/
② 标注（anylabeling / labelimg 任一，导出 COCO）
③ 转 SeaSight COCO-like JSON（schema 见 docs/perception-data-protocol.md）：
   python ml/scripts/convert_annotations.py validate --input <dataset.json> \
     --images-root ml/datasets/seasight/<批次> --verify-dimensions
④ 复制 ml/datasets/manifests/template_manifest.yaml → test_<日期>_<地点>.yaml
   填 status: ready、data_type: real、evidence_level: E3、location 指向上面目录
⑤ 出数：
   python ml/scripts/evaluate_opencv.py --config ml/configs/seasight.yaml
⑥ 产物落 artifacts/metrics/opencv_latest.json，README 里"not_evaluated"改为真实数字
```

⚠️ 第 ⑥ 步之后 README/材料里所有"未评测"的表述都要同步改，否则 `check_claims` 会拦。

---

## 2. 真实验证证据（约 5 分）

**核实**：`docs/product-readiness.md` 的 PR-A1～PR-E2 **全部"待获取/待填"**；
模板本体在 `项目文档/`（用户访谈模板.md / 供应商询价模板.md / 现场验证记录模板.md）。
入库流程 `docs/evidence-inbox/README.md` 已写清 6 步（含校验命令）。

**【只能你做】** 访谈、实地、意向函是**真人的动作**，任何工具都不能替代——
代写一份"意向函"就是造假，直接违反本仓库 `docs/evidence-claim-policy.md`。

**【已做】最高性价比排序**（按"扣分权重 ÷ 执行成本"，详见下节讲稿同目录）：

| 优先 | 对应 PR | 动作 | 拿回什么就算数 |
| --- | --- | --- | --- |
| ① | PR-C2 | 给乡镇海渔站/海渔局打一个电话 | 一段会议纪要或微信记录截图（E3 起点，先入库再升级） |
| ② | PR-A1 | 线下/视频访谈 1 人，用《用户访谈模板》2.1–2.4 | 一份填完的模板 + 录音（E3） |
| ③ | PR-D1 | 去一趟码头/渔排，按《现场验证记录模板》 | 照片 + 坐标 + 填完的模板 |
| ④ | PR-B1 | 向 1 家供应商询价（微信即可） | 盖章/书面报价（E3 起点） |

拿回后 5 分钟入库：复制 `docs/evidence-inbox/intake_template.yaml` →
`docs/evidence-inbox/2026-09-28-<主题>.yaml`，填 8 个字段
（id / claim / evidence_level / source_type / source_ref / captured_at / review_status / owner），
然后：

```bash
.\.venv-analysis\Scripts\python.exe scripts\evidence_registry.py \
  --registry docs\evidence-inbox\2026-09-28-<主题>.yaml --validate
.\.venv-analysis\Scripts\python.exe scripts\check_claims.py --root .
```

---

## 3. 华为实线加粗（ICT 约 1–2 分）

**核实**：全仓无任何华为云凭据/CLI（`MODELARTS|HUAWEI|ASCEND|ACCESS_KEY` 仅命中 MinIO 无关项），
本机无昇腾硬件。`docs/competitions/huawei-ascend-modelarts.md` 的 ATC / CANN / ModelArts
三段全部标注**【方案级 · 未实测】**——这是诚实的，但确实拿不到"实线"分。

**【只能你做】** 需要**任一**：ModelArts 免费试用的华为云账号，或一台 Atlas 边缘盒。

**【已做】拿到资源后的 30 分钟实跑清单**（把"方案级"升级成"实测级"，每步都有可出示的产物）：

```text
A. ModelArts 路线（有账号即可，无需硬件）
  1. 控制台建 Notebook（CPU 规格就够，ascend 可选）→ 产物：环境截图
  2. 上传 yolov8s-worldv2.pt + edge/detector/ 四个文件
  3. 跑 docs/competitions/huawei-ascend-modelarts.md 第二部分的最小验证脚本
     → 产物：终端输出截图（含 device 信息）
  4. 把实测结果回填进该文档，把【方案级·未实测】改为【实测】+ 日期 + 截图路径
     → 这一步才产生"实线"

B. Atlas 路线（有硬件）
  1. 按该文档第一部分跑 ATC：onnx → om
     → 产物：ATC 成功日志（这一条就足以把"昇腾适配"从方案级变实测级）
  2. 运行时装载 CANNExecutionProvider，跑通一次推理
     → 产物：推理输出 + 耗时
  3. 同样回填文档

★ 关键：产物必须回填文档并改标注，否则跑了也等于没跑。
```

---

## 4. 演示时 500 报错 —— 【已做】已修复并验证

**核实（修复前）**：`/vision-compare` 页面上有一条**用户可见的红色横幅**
"服务异常，请稍后重试"。来源不是本页——本页只请求静态 JSON
（`demo/vision-channel-compare.json`）；横幅来自 `App.vue` 的全局错误条，
由外壳 30 秒兜底轮询（stats/devices/robots/events，共 7 个接口）失败触发，
**在每个页面都会渲染**。

**【已做】修复**：全局错误条改为只在**消费 realtime 数据的页面**显示
（7 个路由打 `meta.realtime` 标记，`App.vue` 按 `route.meta?.realtime` 判定）。
**没有隐藏任何状态**：右下角字幕仍显示「实时已断开 / 未自检」，
大屏等消费页在后端不可用时照常显示错误条。验证：

| 页面 | 后端不可用时 | 应该 | 实测 |
| --- | --- | --- | --- |
| `/vision-compare` | 不挂横幅 | 不挂 | ✅ `visibleBadTexts: []` |
| `/dashboard` | 照常挂横幅 | 照常挂 | ✅ 仍显示 |

渲染核验全绿（两列画布、口径说明、字幕追加段均正常）。

**录制配方**：

- **录 `/vision-compare`**：后端起不起都行——页面不依赖后端。
  现在画面上不会再有红色横幅；只剩 DevTools 里能看到网络报错，
  所以**录制时不开 DevTools** 即可。右下角字幕的「实时已断开 · 未自检」是
  项目"不伪造状态"纪律的一部分，**建议保留**，它本身是加分项。
- **录大屏/事件中心等消费页**：必须把后端起起来（见下）。
- **要彻底零报错（可选）**：本机起全栈。注意 `docker compose up -d` 在本机
  拉镜像会被拒（registry 不可达），需走镜像源。本地已有可用镜像：
  `docker.m.daocloud.io/postgres:15-alpine`、`docker.m.daocloud.io/redis:alpine`、
  `quay.m.daocloud.io/minio/minio:RELEASE.2023-12-20T01-00-02Z`（缺 emqx）。
  但 compose 里写的是 `postgis/postgis:14-3.3`（PostGIS 是硬依赖，普通 postgres 不含），
  直接换名会踩坑——所以**更省事的是在已有全栈的机器上录**，或用远程后端
  （改 `frontend/.env.local` 的 `VITE_BACKEND_URL` 后重新 build）。

---

## 结论

- **4 号已闭环**（本机可复现验证）。
- **1/2/3 三条的"最后一公里"都是真人动作**（采集标注 / 访谈函件 / 华为资源实跑），
  任何 Agent 都不能替代——替代即造假。
- 我能做的部分（SOP、优先级、实跑清单、口径对齐）已全部落在本文档，
  照抄即可执行。
