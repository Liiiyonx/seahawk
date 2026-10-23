# 作业台（机械臂控制台）前后端同步计划

> 目标文件：`edge/grasp/web/server.py`（API）、`edge/grasp/web/static/index.html`（界面）、
> `edge/grasp/vision/*`（库层）、`edge/grasp/tools/*`（CLI，改为共用库层）。
> 计划日期：2026-10-18

## Context（为什么做这件事）

本次会话把机械臂感知链路做了一次实质升级，但这些能力**全部留在后端与 CLI**，作业台界面一个字没动，导致「现场泳池采集 → 标注 → 微调 → 部署」这条流程从界面上走就是错的：

| 已落地的后端能力 | 作业台现状 | 后果 |
|---|---|---|
| `Dataset.build(group_splits=True)` 按采集组整组切 train/val | 单会话下拉，走逐帧洗牌 | 现场是视频流，**同组相邻帧会同时进 train 与 val** → 指标虚高 |
| `--mix-dataset-yaml` 底料 replay 混采 | 无入口 | 每条训练只吃泳池帧 → 重演**灾难性遗忘**（实测 TACO val 0.397 → 0.014） |
| `Dataset.mark_background` 会话级背景负样本 | 只能一帧一帧标 | 空池/臂体入画这类纯负样本被当成「尚未标注」**整组剔除** |
| `passes(min_precision)` 精确率门禁 | 只有 mAP50 门禁 | 放行的可能是 mAP 高但误抓多的模型，与「误抓代价高」的核心诉求相反 |
| 部署链路（cv2.dnn）扫描 `verify_pool_model.py` | 只有 ultralytics 口径的 mAP50 | 两条推理链的 P/R **实测差很大**（同模型召回 0.776 vs 0.908），操作员看不到真正上线的那条 |

另外发现两个必须一起修的缺陷：

1. **`/api/frames` 只回最近 60 帧（`server.py` L1180），而标注台与训练卡的会话下拉是从这 60 帧反推的**（`index.html` L1015-1022）→ **早于 60 帧的会话在界面上根本不存在**，等于采完的旧组无法标注、无法进训练。这直接卡住按组分批采集的流程。
2. **训练/导出尺寸不一致**：`config.yaml` 的 `vision.input_size` 是 640，`Detector` 按 640 做 letterbox，但作业台走的 `vision/train.py` 里 `lan` 档按 `TIERS` 的 416 **训练并导出 ONNX**（L106、L145）→ 在作业台里「训练完 → 部署 → 推理」必然 `cv2.dnn` 维度不匹配。这正是 `config.yaml` L82-85 警告过的那类失败。

预期结果：操作员只靠界面就能正确完成「按组采集 → 标注（含整组标背景）→ 整组切分 + 混采微调 → 看部署链路真实工作点 → 带精确率门禁部署」。

## 关键约束（先看，决定顺序）

- **页面↔路由契约测试存在**：`edge/grasp/tests/test_console_manual_api.py` L479-543 会正则提取页面上所有 `api('...')` 调用，并比对后端真实路由与方法。**新端点必须先于前端落地**，否则立刻红。
- **`api()` 契约**（`index.html` L788-802）：`'GET'` → GET；`undefined` → **POST 空体**；对象 → POST JSON。只读查询必须显式写 `'GET'`。
- **`AppState.start_job` 的 `_runner` 只 `except Exception`**（`server.py` L304-314）。`SystemExit` 属 `BaseException`，不会被捕获：`finally` 会复位 `running`，但 `stage` 停在 `starting`、`error` 为空、日志无内容 → **「任务看着起了、永远不动、也不说为什么」**。混采失败路径必须改成普通 `Exception`。
- **单一作业槽**：训练/采集/标定/扫描互斥（既有 409 行为），不做并发。
- 现有 `edge/grasp/tests`（4 个文件）+ `ml/tests` 共 **131 项**必须保持全绿。
- 前端是**手写单文件、无构建步骤**，改动要贴合既有类名与文案风格。

## 实施步骤

按阶段推进，每阶段结束跑一次测试，避免半更新契约。

### A. 库层：把「一份实现」落到 `vision/`（供 CLI 与控制台共用）

| # | 改动 | 要点 |
|---|---|---|
| A1 | 新增 `edge/grasp/vision/mix.py` | 把 `finetune_pool.py` L80-142 的混采逻辑搬入并导出 `mix_datasets(primary, extras, out_dir) -> dict`。**两处修正**：① 抛 `MixError(RuntimeError)` 取代 `SystemExit`（见上文约束）；② 返回值由 `Path` 改为摘要 dict（`data_yaml/train/val/extras/names`），库层不 print |
| A2 | 新增 `edge/grasp/vision/metrics.py` | 合并重复实现：`eval_robustness.py` 的 `_iou`/`match`/`load_gt`（L65-137）与 `verify_pool_model.py` 的 `_iou_at_least`/`_load_yolo_gt`（L47-60、L179-189）。导出 `SCAN_FLOOR`、`iou`、`iou_at_least`、`match`、`load_yolo_gt`、`scan_rows(...)`（统一输出 `conf/tp/fp/fp_buoy/fp_background/fn/precision/recall/f1/hit_frames` 超集） |
| A3 | 新增 `edge/grasp/vision/sweep.py` | 承载部署链路扫描：`load_deployment_detector(cfg, model_path)`、`collect_raw(det, img_dir, lbl_dir, limit)`、`run_deployment_sweep(cfg, ...) -> dict`。**必须每次新建 `Detector`，绝不复用作业台长驻实例** —— 扫描要把 `conf_threshold` 压到 0.05，复用会让实时画面叠加与抓取闭环按 0.05 乱抓，异常时还把错误阈值永久留在长驻对象上 |
| A4 | `vision/evaluate.py` `passes()` 加第 4 个参数 `min_precision=0.0` | 唯一门禁实现（CLI / 训练后门禁 / 部署门禁三处共用）。**只加带默认值的位置参数、不重排**，保持既有行为 |
| A5 | `vision/train.py`：训练与导出尺寸统一到 `vision.input_size` | 抽出纯函数 `imgsz_for(cfg, tier) -> (train_imgsz, export_imgsz)`；`_export_onnx` 用 `export_imgsz`；`out` 透出两个尺寸；export 回调文案写明两个值。**修掉 416 导出缺陷** |
| A6 | `vision/dataset.py`：加 `describe_sessions()` 与 `unmark_background(session)` | `describe_sessions` 每项含 `session/frames/labeled/background/background_note/marked_at/usable`；`usable` = 背景会话取 `frames`，否则取 `labeled`（与 `labeled_frames` L173-182 同一语义，**语义只在 dataset 定义一次**）。会话枚举以**磁盘**为准，不用内存 `self.sessions`（跨进程采的组不在里面） |
| A7 | 三个 CLI 工具改为调用库层 | `finetune_pool.py` 删 L80-142、改用 `mix_datasets`+`catch MixError`（保留 `return 2` 退出码语义）、门禁改用 `passes(..., min_precision)`；`verify_pool_model.py` 退化为薄壳，删自身 `_iou_at_least`/`_load_yolo_gt`，**去掉 tools→tools 的横向 import**；`eval_robustness.py` 删重复 IoU/匹配，保留其独有价值（误检归因、彩色注入） |

已 grep 全仓确认：**没有任何测试或脚本引用** `_mix_datasets` / `match` / `_iou_at_least`，搬迁无外部破坏面。

### B. 后端 API（先于前端）

| # | 端点/字段 | 要点 |
|---|---|---|
| B1 | `GET /api/sessions` | `{"count", "sessions": [...]}`。独立端点、**不挂进 1 Hz 的 `/api/status`**（`describe_sessions` 要逐帧读标签文件，每秒全盘扫不可接受） |
| B2 | `POST /api/background` | body `{session, note, background}`；`background=false` 撤销。**会话不存在必须 404** —— 否则 `mark_background` 的 `mkdir(parents=True)` 会照单全收地凭空建出会话目录。响应回带该会话最新统计，界面点完立刻可见 |
| B3 | `GET /api/frames?limit=` | 默认 60（保持既有行为与「全部会话」总览的性能意图），**按会话查时传 0 不截断**；响应加 `returned`/`limit`，把截断这件事显性化 |
| B4 | `TrainBody` 扩展 | 加 `sessions: list[str]`（与既有 `session` 二选一，同时非空 → 400）、`group_splits: bool`、`mix_dataset_yaml: list[str]`、`min_map50`、`min_precision`。**校验全部在起作业之前**（避免十几分钟训练后才失败）。`group_splits=True` 且只解析出 1 个会话 → 400 并说明「整组切分至少 2 个采集单元」，**不静默降级** |
| B5 | `_job_train` 重写 + 拆出 `_compose_dataset` | `_compose_dataset(job, sessions, group_splits, mix_yamls)` 做纯数据操作（不依赖 ultralytics，本机可单测），把 `stats` 摊进 `Job.detail` 并记日志（train/val/**背景帧**/类别分布/整组切分的 val 单元/混采来源）。`_job_train` 训完即评估：报留出集 P/R + 门禁结论；**混采时额外再量一次未混的泳池域 val**（否则「换域到底行不行」会被合并 val 平均掉）。门禁**不阻塞产物落盘**，拦在部署那一步 |
| B6 | `DeployBody` 加 `min_precision`；`/api/evaluate` 门禁参数化 | `min_precision` 默认 **0.0（不卡）**，既有部署行为与测试口径不变；`/api/evaluate` 改为 `body: EvalBody \| None = None`（空请求体仍要 200，前端现写法不许改），把原硬编码的 0.5 挪到字段默认值 |
| B7 | `GET/POST /api/sweep` + `_job_sweep` + `AppState.last_sweep` | 走 Job（11 档 × 全量 val 的 cv2.dnn 前向，不能挂 HTTP 请求）；`GET` 只回上次结果（页面刷新后仍可见，**不落盘** —— 与 `tuning.json` 里「生效中的调参」职责不同）。后端硬失败当且仅当检测后端不是 onnx/ncnn：扫的就是部署链路，退化成 mock/ultralytics 没有意义 |

### C. 前端 `index.html`

| # | 区块 | 改动 |
|---|---|---|
| C1 | CSS（`label.fld` 之后） | 新增 `.sesslist`（可滚动会话清单）与 `.tbl`（扫描表）；只用已确认存在的变量：`--panel-border`/`--bg-panel-2`/`--text-main`/`--separator`/`--bg-active`/`--c-primary`/`--c-warn`/`--radius` |
| C2 | 标注台（L465-486） | 追加「背景说明输入 + 标为背景负样本/取消标记按钮 + 状态行」。状态行三态：「未选择会话」／「本会话 40 帧 · 已标注 12 · 可用样本 12」／「… · 背景负样本 · 可用 40」。**把「采了多少帧」与「多少帧进训练」的差别摆到操作员眼前** |
| C3 | 训练任务（L488-527） | ① 会话改**复选框清单**（不勾=全部，语义显式；且每项就地显示 `帧数 · 可用`），配「全选/清空/刷新会话」；② 新增「按采集组整组切分」复选框（**默认不勾**，与 CLI 一致，绝不替用户改口径；当勾选 ≥2 个会话时在提示行持续提醒「现场视频流请勾整组切分，否则相邻帧泄漏、指标虚高」）；③ 新增「混采底料 yaml」输入（逗号/换行分隔）；④ 新增「本次口径」回显行。删掉原单值 `#train-session` |
| C4 | 部署与回滚（L528-547） | 加「精确率门禁」输入（空=不卡），与 mAP50 门禁**同一处定义、训练/评估/部署三处共用**；新增「部署链路扫描（cv2.dnn）」按钮 + 结果表（`conf/TP/FP/FN/P/R/F1/命中帧`，标出 F1 最优行与当前工作点行）+ 进度条/日志；hint 里写清「评估走 ultralytics、扫描走现场真正跑的 cv2.dnn 那条路，两者不是一回事」 |
| C5 | JS | 新增 `loadSessions/renderSessionSelect/renderSessions/renderSessionState/toggleBackground/runSweep/loadSweep/renderSweep/recountSession`；改 `loadFrames`（会话下拉不再从帧反推；选中会话时 `limit=0`；空态说明只载入最近 60 帧）、`startTrain`（提交 sessions/group_splits/mix/门禁）、`doDeploy`、`deployFromPath`、`showEval`、`renderJob`（train 完成时回显组装统计与泳池域/混采两套指标；采集完成时刷新会话；新增 sweep 分支）。启动时补 `loadSessions()`、`loadSweep()` |

**顺序硬约束**：C3 删 `#train-session` 与 C5 重写 `loadFrames()` **必须同批完成**。`loadFrames()` 在启动时被调用，若仍写已删除的 DOM，抛出的 `TypeError` 无人捕获，会让页面「活着但什么都不更新」。

### D. 测试（沿用既有 fixture 风格）

新 fixture 比现有版本多一条纪律：**把 `cfg["data"]["root"]` 也指到 tmp**，否则测试会读写仓库里的 `edge/grasp/data`（与现有「不污染现场数据」的注释同一条理由）。

| 新文件 | 覆盖 |
|---|---|
| `tests/test_console_dataset_api.py` | `/api/sessions` 列出**全部**会话（含 >60 帧的旧会话）；`usable` 反映标注数而非帧数；背景标记/撤销对 `usable` 的影响与标记文件存在性；未知会话 404；`/api/frames?session=X&limit=0` 不截断；页面含新控件 |
| `tests/test_console_train_api.py` | 契约层（不需要 ultralytics）：未知档位 400、`session`+`sessions` 同时非空 400、单会话 + group_splits 400、mix 路径不存在 400；数据层（直接调 `_compose_dataset`）：多会话整组切分的 `Job.detail`/日志、混采摘要与那条 ⚠ 警示、**混采类名超集抛 `MixError` 且断言不是 `SystemExit`**（锁住 A1 那个缺陷）、跨文件「只有一份实现」的守卫断言 |
| `tests/test_vision_metrics.py` | `iou`/`iou_at_least` 临界值、`match` 贪心与「两个 pred 争一个 gt」、`load_yolo_gt` 跳过非法行、`scan_rows` 各指标与手算一致 |
| `tests/test_vision_mix.py` | 混采**只写清单不拷文件**（断言输出目录无图片/标签）、train.txt 行数 = 两集之和、类名子集违反抛 `MixError`、`images_of` 支持目录与 .txt 清单两种 spec |
| `tests/test_vision_train_export.py` | `imgsz_for`：config 有 `input_size=640` → `(640, 640)`；删掉该键 → 落到档位 `(416, 416)`。源码守卫：`train.py` 不再有按档位分叉的尺寸分支，且 `_export_onnx` 第三参是 `export_imgsz`。 |

## 验证方式（端到端）

```powershell
# 1) 库层与接口契约
python -m pytest edge/grasp/tests -q                    # 既有 4 个文件必须全绿
python -m pytest edge/grasp/tests ml/tests -q           # 总数不得低于 131

# 2) 新增测试
python -m pytest edge/grasp/tests/test_console_dataset_api.py edge/grasp/tests/test_console_train_api.py -q
python -m pytest edge/grasp/tests/test_vision_metrics.py edge/grasp/tests/test_vision_mix.py `
                 edge/grasp/tests/test_vision_train_export.py -q

# 3) CLI 行为不变（搬迁后逐字比对输出）
python edge/grasp/tools/verify_pool_model.py --limit 40
python edge/grasp/tools/finetune_pool.py --help

# 4) 界面手工验收（mock 起作业台；扫描在 mock 下会"按设计失败并给理由"，这也是验收点）
python -m grasp.web.server --mock
#   打开 http://127.0.0.1:8090
#   · 标注台：会话下拉含 >60 帧的旧会话；点「标为背景负样本」后状态行变为「可用 = 帧数」
#   · 训练任务：勾 2 个会话时提示行出现整组切分提醒；提交后日志有「数据集组装 / 整组切分 / 混采（replay）」行
#   · 部署与回滚：填精确率门禁后「评估当前模型」按同一口径判定；点扫描出表（真机/有 ONNX 时）
```

## 明确不做（本轮留白）

- 训练 epoch 覆盖、按类门禁、混采清单上的扫描（Phase 2，可用 `mix.images_of` + `/images/`→`/labels/` 推导）。
- `last_sweep` 落盘（重启后重扫即可，只是一份证据快照）。
- 采集页的组名关键词提示（CLI `capture_pool.py` 已有，界面侧不是本轮缺口）。
