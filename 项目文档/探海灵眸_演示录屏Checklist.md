# 探海灵眸 · 演示录屏 Checklist（审批高光 · 两个主镜头 + 执行端加分镜头）

> 配套方案：《探海灵眸_智能体优化与演示视频方案.docx》第四节 P0。
> 目标：**两个主镜头都能在 2 分钟内稳定复现**，且失败时能立刻定位到是哪一环没就位。

---

## 0. 开录前 60 秒：五层自检（顺序不能颠倒）

| # | 命令 | 期望 | 这一层在防什么 |
|---|---|---|---|
| ① | `make check-demo-approval` | 三环全绿、退出码 0 | 静态链路：`.env` 开关、compose 透传、approver 账号来源 |
| ② | `make demo-approval-up` | 容器起来 | 把本地 `.env` 的开关置 true 并启动服务（**仓库默认的 `.env.example` / `config.py` 保持保守不变**） |
| ③ | `make bootstrap-demo-users` | 打印 4 个账号 created/updated | 确保 approver 真的在库里（见下面「已踩过的坑」第 1 条） |
| ④ | `make demo-approval-check` | `require_approval_for_write = True` | 向**内核**确认真会拦 WRITE，而不是只看环境变量写没写 |
| ⑤ | `docker logs seasight-backend --since 2m \| grep 后台任务` | 「后台任务已按配置关闭（BACKGROUND_WORKERS_ENABLED=false）」 | 补派竞速：30 秒定时器抢在审批放行前为高优先级 `new` 事件建单 → run 6007（见「已踩过的坑」第 6 条） |

> ①②③④⑤ 都需要 Docker，①也可以在没有 Docker 时单独跑（纯静态）。
> 收工恢复默认策略：`make demo-approval-down`（只把 `.env` 里那一个键关掉，其余配置不动）。

### 开关的真源只有一处

`本地 .env` → `AGENT_REQUIRE_APPROVAL_FOR_WRITE`。

switches 分散在两处是演示事故的常见来源（"我明明关了它还在拦"）。所以：

- **`.env.example` 与 `config.py` 永远保持保守**（默认不要求审批 = 与生产策略一致）；
- 演示开关只写在**本地 `.env`**（已在 `.gitignore` 里排除）；
- 不再使用 compose 叠加层 —— 那会让同一个开关有两个真源。

⚠️ 一个必须知道的副作用：**从仓库根启动的任何进程都会读到这个 `.env`**，
包括 `pytest`、`scripts/*.py`。所以开着它跑测试或辅助脚本时，
默认策略就是"WRITE 需要审批"。本轮已在开启状态下跑通全量后端测试（见 §6），
但你若自己加脚本，记得它拿到的不是仓库默认值。
如果你只想让容器开着、不影响本机其它命令，用一次性环境变量起容器：
`AGENT_REQUIRE_APPROVAL_FOR_WRITE=false docker compose up -d --force-recreate backend`。

---

## 1. 镜头 A：审批流（约 60–90 秒，全片最高光）

### 操作序列

| 步 | 操作 | 画面预期 | 解说要点 |
|---|---|---|---|
| A1 | 用 `operator / operator123456` 登录 | 顶栏显示「乡镇操作员 · 马鼻镇」 | 「值班操作员登录」 |
| A2 | 顶栏进**智能体控制台**（`/agents`），点「启动运行」，`event_id` 固定填 **`evt_demo_0015`**（塑料类·马鼻镇·new），模式选**单智能体** | run 列表新增一条 | 「操作员发起事件处置」 |
| A3 | 该 run 立刻停在**等待审批** | 状态徽标 = 等待审批；审批队列出现 1 条待决项，风险级别标「写入」 | **核心台词**：「高风险动作必须人批准，智能体不敢私自建单」 |
| A4 | 确认此时**工单看板里没有新工单**、事件仍是 `new` | 工单列表无新增 | 「它停住了 —— 没批准之前什么都没发生」 |
| A5 | 换 `approver / approver123456` 登录（**用第二个人/第二台设备**，手机也行） | 顶栏显示「值班审批员」 | 「由第二个人放行」 |
| A6 | 进控制台 → 审批队列 → 点「批准」 | run 从 等待审批 → 执行中 → 成功；工单看板出现新工单 | 「批准之后才真正建单」 |
| A7 | 回 run 详情，点「▶ 回放轨迹」 | 逐步点亮：计划 → 策略校验 → 审批请求 → 工具调用 … | 「每一步都有哈希，可逐条复核」 |

### 验收口径

- A3 之后**必须**能看到待审批项；看不到说明开关没生效 → 回 §0 重跑 ①②④。
- A4 的「没有新工单」是这条镜头最有说服力的一帧，**别剪掉**。
- A6 只有 `admin` 或 `approver` 能批；`operator` 点会 403（这本身就是权限分层的证据，可留作彩蛋）。
- **事件选择（彩排实测，2026-10-06）**：固定用 `evt_demo_0015`。勿用 `evt_demo_0006` —— 它绑着种子工单 `tsk_demo_0003`（collecting），run 会报 6007。0015 是塑料类，不在补派定时器的高优先级（泡沫/渔具）范围里，worker 开着也安全；且每次演示跑完后要把它重置回 `new`（见 §7 清理命令）。

---

## 2. 镜头 B：研判门禁（约 40–60 秒，备用加分）

### 操作序列

| 步 | 操作 | 画面预期 | 解说要点 |
|---|---|---|---|
| B1 | 造一个**没有证据图**（`evidence_url` 为空）或置信度低于 0.5 的事件 | 事件中心出现该事件 | 「有人报了一个证据不足的疑似事件」 |
| B2 | 控制台 → 启动运行 → 模式选**多角色协同** | 轨迹里出现「事件研判 Agent」角色徽标 | 「这次交给两个角色协同」 |
| B3 | **（彩排新增，必须）** 换 approver 批准该 run 的审批项（同 A5/A6，用第二设备）—— 多角色计划同样含 WRITE 工具，run 会**先停在等待审批**，不再是直接研判终止 | run 从 等待审批 → 执行中 | 「研判归研判，真要写单的权限照样捏在人手里」 |
| B4 | 观察轨迹前两步 | `policy.lookup`（检索政策依据）→ `analysis.assess`（给出研判结论） | 「先查依据，再下结论」 |
| B5 | run **安全终止**，不建单 | 终止原因策略拒绝；**工单看板无新增**；事件仍是 `new` | **核心台词**：「证据不足，它会主动拦住不该自动派的单」 |
| B6 | （可选）用**证据充分**的事件跑一次多角色模式 | 两步研判 → 四步派单全跑完 | 「证据够了，它才动手」 |

> B 镜头与 A 镜头可以同场录制：调 A 用单智能体，调 B 用多角色协同，观众能直接对比两种模式。

---

## 3. 六个已踩过的坑（照着躲）

1. **`02_seed.sql` 会 `TRUNCATE TABLE t_user`，而老版本里只有 3 个账号、没有 approver。**
   所以「先 `make db-init`、再 `make bootstrap-demo-users`」这个顺序不能反；
   反过来跑的话 approver 会被清掉，表现为**审批队列永远空着**。
   → 本轮已把 approver 补进 `02_seed.sql`（哈希 passlib 现算并自验过），两条路都能备齐账号。
2. **容器不读仓库根 `.env`。** `docker-compose.yml` 里 backend 的挂载是 `./backend:/app`，
   pydantic 从 cwd（`/app`）读 `.env`，读不到仓库根的 `.env`；
   根 `.env` 只被 compose 用于 `${VAR}` 变量插值。
   → 所以本轮给 compose 的 `environment:` 补了 `AGENT_*` / `ASSISTANT_*` 透传（此前一个都没透传）。
3. **裸机 `make dev-backend` 读的是 `backend/.env`，不是仓库根 `.env`**
   （因为它是 `cd backend && uvicorn ...`）。走裸机演示时用环境变量覆盖：
   ```bash
   AGENT_REQUIRE_APPROVAL_FOR_WRITE=true make dev-backend
   ```
   环境变量优先级高于 `.env` 文件，这样不额外多出一个凭据文件。
4. **`evt_demo_0006` 是 6007 陷阱（A 镜头事件选择）。**
   种子工单 `tsk_demo_0003`（collecting）绑定了它，run 对它建单会报 6007 业务冲突。
   → A 镜头固定用 `evt_demo_0015`（塑料类 0.82 · 马鼻镇），塑料类不在补派定时器的
   高优先级（泡沫/渔具）范围里，worker 开不开都安全；2026-10-06 彩排 A1→A7 全通。
   每次跑完把 0015 重置回 `new`（§7 命令）。
5. **多角色 run 也含 WRITE 工具，会先挂审批（B 镜头流程变化）。**
   原脚本「多角色 → 直接 policy_denied 安全终止」已不成立：run 会先停在等待审批。
   → 正式演示在 B2→B4 之间必须加 approver 批准一步（B3，同 A5/A6 用第二设备），
   批准后 run 继续并按预期 policy_denied 终止、不建单；单人演示时可全程用 admin（可自批）。
6. **30 秒定时补派会抢跑建单（已根治）。**
   `pending_dispatcher` 每 30 秒为高优先级（泡沫/渔具类）`new` 事件自动建单，
   会在 approver 批准之前把事件消费掉 → Agent run 报 6007。
   彩排实测：`evt_demo_0016` 重置为 new 后 3 分钟内即被抢建占位工单。
   → 已把 `BACKGROUND_WORKERS_ENABLED` 透传进 compose（默认 true，行为不变），
   并在本地 `.env` 置 false（2026-10-06 20:19 起 backend 已带此配置重建）。
   三个镜头不受影响：A/C 的建单走 run 内同步路径、仿真 ACK 走 MQTT handler，
   都不依赖后台 worker。录完恢复：删掉 `.env` 里那一行 →
   `docker compose up -d --force-recreate backend`。

---

## 4. 录屏规格（与方案第六节一致）

- 两个版本：**2 分钟快剪**（只保留镜头 A 的 A3→A6 + 收尾）用于提交；**8 分钟完整版**用于答辩现场。
- 决策过程绝不快进：回放默认 **1.5 秒/步**，现场如需更慢按「慢速 2s」。
- OBS 固定 1920×1080；演示推流用 `make demo`（3 秒冷却）。
- 右下角口径字幕：顶栏点「口径」打开（或访问时带 `?demo=1`）。
  字幕里的「规则模式」会自己拉一次 runtime/status 自检；自检不过会标「未自检」——**这是设计，不是 bug**。
- 手机镜头拍 A5/A6：窄屏下审批按钮已做成整行、触控高度 ≥44px。

---

## 5. 一句话口径（被问到就这样答）

- **「这个审批是真的会拦吗？」** → 不是展示开关。开关打开后，`task.create_or_merge` 属 WRITE 风险，
  策略守卫会为它创建审批单并把 run 挂起到 `waiting_approval`：**事件不改状态、工单不落库**，
  只有 `admin`/`approver` 批准后才继续。A4 那一帧就是证据。
- **「为什么恢复成功率只有 0.33？」** → 分母 3 个里有 2 个是「故意要求它别恢复」的安全用例
  （重规划预算耗尽、无进展死循环），它们失败才算通过。在「设计中允许恢复」的场景里是 1/1。
  详见方案文档 7.3 节。
- **「工具调用正确率为什么不是 100%？」** → 新增的场景里有一处**按预期被研判门禁拦下**的工具步骤，
  它必须落 `failed` 才算测出东西来（与既有「安全终止」类场景同一口径，不是调不通）。
  88/89，分子分母都在评测产物里可查。
- **「现在测了多少场景？」** → 27 个（原 23 + 本轮新增 4：多角色研判门禁 2 个、跨 run 经验闭环 2 个），
  `sample_size=27`、`skipped_count=0`、27/27 通过。详见方案文档 7.5 节。

---

## 6. 镜头 C：软硬结合 · 可插拔执行端（加分镜头，条件具备再录）

> 只有当你现场确实完成过“真实机械臂在仿真海面或受控环境里拾取目标，并经 MQTT 回传平台”后，才把这段作为镜头 C；否则现场只讲规划，并打开 ArmPiFPV 自带仿真台 / 厂商上位机演示，不能把厂商仿真画面剪成真机验证。

### 操作序列

| 步 | 操作 | 画面预期 | 解说要点 |
|---|---|---|---|
| C1 | 用受控测试事件触发岸基摄像头“发现” | 事件中心出现事件，口径字幕标注“合成/受控测试事件” | 「岸基摄像头发现问题」 |
| C2 | 控制台启动 Agent run，自动派单 | 计划 → 工具调用 → 工单生成 → MQTT 下发 | 「自动派单」 |
| C3 | 机械臂执行端收到指令并 ACK | 平台显示任务已下发、ACK 成功 | 「同一套任务与 MQTT 契约，执行端可插拔」 |
| C4 | 机械臂在模拟海面拾取目标 | 拾取动作完成，平台收到作业结果与影像回传 | 「验证的是拾取这个关键物理动作」 |
| C5 | 讲解执行末端选型 | 无人机、水面机器人、机械臂对比 | 「环境受限的不是系统，而是飞行器；执行器不够用就换一个」 |

### 验收口径

- 必须能看到 ACK、拾取动作和回传闭环，缺一环不算镜头 C。
- 解说与字幕必须写“仿真海面 / 受控环境（E1/E2）”。
- 本镜头不构成现场验收；当前没有真实海域拾取记录，岸基摄像头发现只描述为“受控测试事件触发”，不报告识别精度。

---

## 7. 演示前后：数据库清理与重置命令（2026-10-06 彩排后固化）

**当前就位状态（清理已完成，开录前用 ① 复核即可）**：
`evt_demo_0015`、`evt_demo_0016` 均为 `new` 且无活跃工单；彩排残留的 4 条工单
（A/C 各 1 条 + 竞速占位 2 条）及其轨迹、ACK 已删；种子工单保留（看板有历史感）；
run 历史与审批记录保留（无待决审批项）；`tsk_demo_0002` 保持 **cancelled**（勿恢复，
否则镜头 C 对 `evt_demo_0016` 建单会 6007）。

① **开录前 30 秒复核**（两个事件都应 `new`、`pending_approvals` 应为 0）：

```bash
docker exec seasight-postgres psql -U seasight -d seasight -c \
  "SELECT event_id,status FROM t_event WHERE event_id IN ('evt_demo_0015','evt_demo_0016');"
curl -s localhost:18000/api/v1/agents/runtime/status
```

② **每次镜头 A/C 跑完后**（把事件还给下一次录制；种子工单 `tsk_demo_*` 不动）：

```bash
docker exec seasight-postgres psql -U seasight -d seasight -v ON_ERROR_STOP=1 -c "
BEGIN;
DELETE FROM t_task_ack WHERE task_id IN (
  SELECT task_id FROM t_task
   WHERE event_id IN ('evt_demo_0015','evt_demo_0016') AND task_id NOT LIKE 'tsk_demo_%');
DELETE FROM t_track WHERE task_id IN (
  SELECT task_id FROM t_task
   WHERE event_id IN ('evt_demo_0015','evt_demo_0016') AND task_id NOT LIKE 'tsk_demo_%');
DELETE FROM t_task
 WHERE event_id IN ('evt_demo_0015','evt_demo_0016') AND task_id NOT LIKE 'tsk_demo_%';
UPDATE t_event SET status='new' WHERE event_id IN ('evt_demo_0015','evt_demo_0016');
COMMIT;"
```

> 跑 ② 前提是 §0 第 ⑤ 层已过（worker 关闭），否则 `evt_demo_0016`（泡沫类）
> 会在 30 秒内被定时补派重新消费。镜头 B 不建单，无需重置。
