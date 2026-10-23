# 探海灵眸 · ArmPi 真机部署清单

> 一句话结论：**代码层面已经全部接好**。这份源码（幻尔 ArmPi 固件）与
> seahawk `edge/grasp/arm_io.py` 的协议契约完全吻合（话题名、舵机 ID 映射、
> 夹爪脉宽口径、IK 复用），缺的只是**物理部署 + 在线标定**。按本清单顺序做完，
> 即可走通「平台派单 → 识别 → 拾取 → 入槽 → 回传」的真机闭环。
>
> 证据口径：真机械臂 + 受控实验 = **E2**；`ok`（夹到了）与 `placed`（放进料槽）
> 必须分开验收；`review_result` 默认 `recheck`，人工核对后才改 `confirmed`。

---

## 〇、先看这里：已有一键自动化入口（2026-10-16 起）

本文档下面的阶段 1~4 是**手工逐步**流程，排障和首次摸底时仍然有效。
但「让机械臂自己一直捡」这件事已经固化成脚本，**不需要再手打那一串命令**：

```powershell
# 开发机：打包 + 部署 + 只读验证（默认不动机械臂）
python scripts\deploy_autopick_to_pi.py --host 192.168.149.1

# 确认验证通过、工作区无遮挡、有人在场，才真正开跑
python scripts\deploy_autopick_to_pi.py --host 192.168.149.1 --apply
```

```bash
# 板上：只做前置检查（排障第一条，什么都不启动）
bash edge/grasp/deploy/run_autopick.sh --check
# 板上：前台跑一次，看全部输出
bash edge/grasp/deploy/run_autopick.sh
```

它替你把阶段 1 的**三组 launch 启动**、话题就绪等待、阶段 3 的自检，
以及阶段 4 的常驻自捡全都串好了，并且在停止时按 launch 名回收厂商节点
（避免「串口被上一次的节点占着」这个高频故障）。

> ⚠️ 一个**必须知道的旧坑**：`oceanus-arm-autopick.service` 原先直接
> `ExecStart=python3 -m grasp.supervisor`，而 supervisor 不含 ROS 接入启动 ——
> 板子重启后没人起厂商节点，服务会按前置条件干净退出（exit 2），
> 现象是「服务 failed、机械臂一动不动」。该单元现已改为调用
> `run_autopick.sh`，重装即生效：
> `sudo bash edge/grasp/deploy/systemd/install.sh --repo <仓库根> --broker <平台IP> --mode autopick`
>
> 完整手册（退出码语义 / 首次跑通清单 / 排障对照表）见
> **`edge/grasp/deploy/README.md`**。

---

## 一、总体架构（先看清数据流）

```
开发机（Windows，跑平台栈）
  ├─ frontend  http://localhost:5173
  ├─ backend   http://localhost:18000
  ├─ EMQX      mqtt://localhost:1883      ← 板子要连这里，注意开放局域网
  └─ (可选) 桥接层演示（simulated，不碰真机）

树莓派（ArmPi 板载，Ubuntu 18.04 + ROS Melodic）
  ├─ ROS: hiwonder_servo_manager（持 /dev/ttyS0 舵机总线）
  ├─ ROS: usb_cam（发布 /usb_cam/image_raw）
  ├─ edge/grasp 作业台（FastAPI :8090）
  │     ├─ 9 点标定 / 放置点示教 / 采集 / 部署
  │     └─ arm_io：话题收发 + 复用厂商 ArmIK 现算脉宽
  └─ arm_bridge（oceanus_vision 驱动）← 订阅平台派单、回传 progress
        （与 grasp supervisor 互斥：**同一时刻只能跑一个**）
```

关键约束（决定了所有后续步骤）：

1. **rospy 只在树莓派上存在**（Windows 开发机没有）。所以 `arm_io` 的
   `mock=false` 真机路径、`--driver oceanus_vision`，都必须在**板载环境**里运行。
2. **厂商 `start_functions.launch` 绝对不能启动**。它会把
   object_sorting / object_tracking / warehouse 等 `required=true` 节点全拉起来，
   直接抢走相机和控制权 —— 这是"机械臂不动"最常见的死因。
3. **桥接层与 supervisor 互斥**：两者都会驱动同一台机械臂。

---

## 二、阶段 0 · 前置核对表

动手前逐项确认，任一为「否」都先解决：

| # | 核对项 | 完成标准 / 备注 |
|---|--------|----------------|
| 0.1 | 树莓派系统 | Ubuntu 18.04（hostname=`ubuntu`），ROS Melodic |
| 0.2 | 源码就位 | `/home/ubuntu/armpi_fpv`（**去掉"ArmPi FPV源码"目录层**） |
| 0.3 | 编译产物 | `catkin_make` 通过，`devel/setup.bash` 存在（kinematics 的 .so 由此产出） |
| 0.4 | 板载串口 | `/dev/ttyS0`，115200，仅 `hiwonder_servo_manager` 持有（他人直连会抢总线） |
| 0.5 | USB 摄像头 | `/dev/video0` 自检出图（`cheese` 或 `avconv`） |
| 0.6 | 网络互通 | 板子与开发机同一局域网，双向 ping 通；开发机能 SSH 上板 |
| 0.7 | EMQX 可达 | 板上 `telnet <开发机IP> 1883` 能连（Docker 需映射端口到 0.0.0.0） |
| 0.8 | 平台账号 | `robot_device` 的密码与平台 EMQX 实际一致（两个 config 的 `mqtt.username/password`） |
| 0.9 | 模型已就位 | `edge/grasp/models/active/best.onnx` 就位（作业台「4 · 部署与回滚」） |

> 若板载 Python 不是 3.7+，作业台 / 桥接层的依赖（dataclass、`from __future__` 等）
> 可能装不上 —— 先 `python3 --version` 核对。

---

## 三、阶段 1 · 板上启动三组 launch

SSH 上板，依次启动（每步都验证通过再继续）：

```bash
ssh ubuntu@<板子IP>
sudo chmod 666 /dev/ttyS0   # 预防权限问题（按需）

source /opt/ros/melodic/setup.bash
source /home/ubuntu/armpi_fpv/devel/setup.bash

# 1) 依赖：config / web_video_server / rosbridge
roslaunch armpi_fpv_bringup start_dependence.launch &

# 2) 相机：usb_cam → /usb_cam/image_raw
roslaunch armpi_fpv_bringup start_camera.launch &

# 3) 舵机控制器：hiwonder_servo_manager（参数用 hiwonder_servo_controller.yaml）
roslaunch hiwonder_servo_controllers controller_manager.launch &
```

> 若厂商 `start.launch` 与 `controller_manager.launch` 内容重复，二选一即可，
> 以板上实际能初始化舵机队列的那个为准（主要看有没有起到
> `hiwonder_servo_manager` 节点）。

**逐项验证（前提：不启动 start_functions.launch）：**

```bash
rostopic hz /usb_cam/image_raw                       # 相机帧率 ≈ 10Hz
rostopic echo /servo_controllers/port_id_1/servo_states   # 应有 6 条舵机状态
rostopic echo /joint_states                          # 6 关节角（弧度）
```

预期 `servo_states` 字段：`voltage / position / goal / error`。舵机 ID 1..6
喂电正常、`voltage` 为**毫伏**（约 7400+）。

**自检舵机通电**（安全动作，先慢后快）：

```bash
# 在板上单独 Python 验证总线可用（ID1 夹爪慢动 200↔400，别超过工作区）
# 或用作业台「手动点动」面板试拉一个舵机
```

> 📌 全景确认完这步，"板子已经被 ROS 站住"就算成立，后续任何程序都不要
> 再直连 `/dev/ttyS0`。

---

## 四、阶段 2 · edge/grasp 部署到板

```bash
# 开发机打包（排除 .git / .venv / data / 模型太大可只带 active 目录）
cd C:\Users\Liii\Desktop\seahawk\edge

# 方案 A：rsync / scp 整个 edge 到板
scp -r grasp ubuntu@<板子IP>:/home/ubuntu/oceanus_edge/
```

板上安装运行时依赖（**推理不需要 ultralytics**）：

```bash
cd /home/ubuntu/oceanus_edge
python3 -m pip install -r grasp/requirements.txt   # 缺的单独补
python3 -m pip install ultralytics                 # 仅训练档；推理可跳过
```

核对 `edge/grasp/config.yaml` 真机项：

| 键 | 真机取值 | 说明 |
|----|---------|------|
| `web.mock` | `false` | 真机模式 |
| `arm.usb_camera` | `null`（留空） | 走 `/usb_cam/image_raw` 话题 |
| `arm.plane_z` | 负数（如 `-0.08`） | 船/台面：甲板高于水面则为负 |
| `vision.input_size` | 先 416，实测 Pi4 帧率 | 640 在 Pi4 上视觉伺服 ~4Hz 需现场复核 |
| `agent.grasp_pitch` | `-175` | `-65` 是待命位角度，拿来抓会压不住 |
| `mqtt.host` | 开发机 IP | 板子连平台 EMQX（生产部署时再改账号） |

启动作业台（真机模式）：

```bash
cd /home/ubuntu/oceanus_edge
python3 -m grasp.web.server            # http://<板子IP>:8090
```

浏览器打开 `http://<板子IP>:8090`：应能看到**真摄像头画面**（非合成背景），
「手动点动」能驱动舵机。

---

## 五、阶段 3 · 9 点标定 + 放置点示教（真机必需）

> 作业台演示标定（RMSE 恰为 0）**不会落盘**，真机必须按下面重跑。

1. 在作业台「5 · 9 点标定」页，把可检测目标（袋/球）放到工作平面上
   9 个已知网格点，系统记录像素中心 → 保存 `calibration.json`。
2. RMSE 应为非 0 的毫米量级（几 mm 正常，几十 mm 就要重来）。
3. **平面高度**：如实填写 `plane_z`（水面在臂座安装面之下的负值）。
4. **放置点示教**：「手动点动」把臂摆到料槽口上方 → 点
   「用当前姿态作放置点」→ 保存。未设置放置点，闭环会**拒绝开工**。

完成后在板上跑一次只读自检，全部必需项必须 ✓：

```bash
cd /home/ubuntu/oceanus_edge
python3 grasp/tools/precheck.py                # 真机模式（先 source 厂商空间）
```

退出码 0 才允许进下一步。

---

## 六、阶段 4 · 桥接层接平台派单

板上启动（**与 supervisor 绝对不能同时跑**）：

```bash
cd /home/ubuntu/oceanus_edge
python3 -m arm_bridge.main \
  --config arm_bridge/config.yaml \
  --driver oceanus_vision
```

`arm_bridge/config.yaml` 真机项核对：

| 键 | 真机取值 |
|----|---------|
| `driver.backend` | 命令行 `--driver oceanus_vision` 覆盖（默认值故意不改） |
| `mqtt.host` | 开发机 IP |
| `oceanus_vision.mock` | `false` |
| `oceanus_vision.config_path` | `null`（默认读 grasp/config.yaml） |

验收信号（平台侧）：

1. 平台派单 → 桥接层 ACK（`accepted=true, mode=navigating`）。
2. 板上摄像头检测到袋 → `collecting` → `done`，`progress: 1.0`。
3. 遥测 `marine/+/RBT-ARM-01/telemetry` 更新。

---

## 七、阶段 5 · 真机现场验收（口径固定）

| 验收项 | 判定 | 备注 |
|--------|------|------|
| `ok` | 夹爪回读停滞 → 夹到东西 | 不是"看见它动了" |
| `placed` | 松爪回位后，镜头确认袋子**在料槽里** | 与 `ok` 分开报 |
| 全链路 | 派单 → 识别 → 拾取 → 入槽 → 回传 done | 录像 + 前后照片 + MQTT 日志 |

证据包等级标注 **E2（受控实验）**，演示措辞「本镜头不构成现场验收」。

---

## 八、坑位清单（按出现频率排序）

1. **启动过 `start_functions.launch`** → 相机与控制权被厂商功能节点抢走，
   表现为"识别有框但机械臂不动"。只跑三组（依赖 / 相机 / 舵机控制器）。
2. **直连 `/dev/ttyS0` 抢总线** → 半双工必须独占。不要跑厂商 `bus_servo_control`
   直连脚本（Ai_FPV 那套），否则和 ROS 节点打架。
3. **`planes_z` 填正/留空** → 爪子压不到水面目标，永远"差一点"。船上填负值。
4. **`grasp_pitch=-65`** → 待命位的角度不是抓取角度，会斜着压不住袋。用 `-175`。
5. **用 640 输入上 Pi4** → 视觉伺服掉到 ~4Hz 以下。实测帧率，不保就回退 416。
6. **没设放置点** → 闭环直接拒绝开工（这是特性不是 bug：**不能假装放好了**）。
7. **桥接层与 supervisor 同跑** → 两台驱动机器臂互抢。互斥。
8. **多进程占摄像头** → 同一颗摄像头一次只能被一个进程用（Windows 上
   `isOpened()=True` 但 `read()` 不出帧是静默失败）。作业台与桥接层不要同时开。
9. **夹爪脉宽方向** → **脉宽越大越闭**：夹 450 / 松 75（厂商 in.py 口径）。
10. **ROS 没 source 就启动** → `arm_io` 会明确报 `ros_error` 而不是崩掉，
    作业台仍打开；按提示 source 后重启即可。

---

## 九、还剩的收尾事项（截至 2026-10-16）

- [ ] 5 条彩排工单确认清理（当前处于演示环境，无真实执行端）
- [ ] 确认板子到手时间 / 是否已能开机 SSH
- [ ] 决定真机首调是「只跑 supervisor 常驻自捡」还是「平台派单驱动」
      （两次验收跑同一套 9 点标定即可）

---

## 十、一步到位的真实含义

当以上全部走完，「**做作业端 + 真机械臂**」的演示能力是：

1. 平台 Web 点「派单」→ EMQX → 桥接层 ACK；
2. 板上视觉逐帧检测塑料袋（ONNX）→ 9 点标定映射世界坐标 → 厂商 IK 现算
   四关节脉宽 → 话题下发给 `hiwonder_servo_manager` → 总线舵机运动；
3. 夹爪自适应渐闭（回读停滞判夹住 = `ok`）→ 抬升 → 走近料槽 → 松爪落袋
   （=`placed`）→ 回位；
4. 回传 `progress done` + 遥测 + 前后照片证据，平台工单闭环。

每一步现在都有对应的既有代码与测试；**没有一步需要从零开发**。
