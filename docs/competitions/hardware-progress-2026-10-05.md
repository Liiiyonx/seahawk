# 硬件（机械臂）接入进度总览

> 截至 2026-10-05 10:15。当前进度：**P0 软件链路已就绪，只差真机示教与网络模式切换。**
> 本文是唯一权威口径，硬件相关的结论都以此处为准。

---

## 一、一句话现状

**机械臂是活的，ROS 控制栈在跑，我们这边该写的代码都写完了。**
剩两件必须人做的事：**示教一个抓取姿态**、**树莓派改 STA 模式**。

---

## 二、进度看板

| # | 事项 | 状态 | 证据 |
|---|---|---|---|
| 1 | 树莓派连通性 | ✅ 已实测 | SSH 通，192.168.149.1 |
| 2 | 板载串口存在 | ✅ 已实测 | `/dev/ttyAMA0`、`/dev/ttyS0` 均在 |
| 3 | 厂商 SDK 部署 | ✅ 已完成 | `~/ros_robot_controller_sdk.py`（24,966 B） |
| 4 | ROS 依赖齐全 | ✅ 已实测 | rospy / sensor_msgs / control_msgs / trajectory_msgs 全 OK |
| 5 | **机械臂活着** | ✅ **已实测** | `/joint_states` 以 **20 Hz** 发布 6 关节角度 |
| 6 | ROS 控制接口 | ✅ 已实测 | `/arm_controller/follow_joint_trajectory`、`/gripper_controller` |
| 7 | 新驱动 `RosArmDriver` | ✅ 代码完成 | `edge/arm_bridge/ros_driver.py`，12 项测试通过 |
| 8 | 驱动惰性注册 | ✅ 已完成 | `build_arm_driver` 按需 import，开发机无 ROS 也能跑 |
| 9 | 舵机遥测全链路 | ✅ 代码完成 | 驱动→MQTT→`t_track.servo_telemetry`→REST→页面面板 |
| 10 | 页面舵机遥测面板 | ✅ 已实测渲染 | 探针 18/18 通过，见 `arm-console-telemetry.png` |
| 11 | 执行后端面板 | ✅ 四驱动齐备 | 仿真 / HTTP / **ROS 控制栈** / 直连串口 |
| 12 | bridge 部署脚本 | ✅ 就绪，**未实跑** | `scripts/deploy_bridge_to_pi.py` |
| 13 | **真机抓取姿态示教** | ❌ **未做** | `pick_rad` 现等于 `home_rad`，直接跑会抓空 |
| 14 | **树莓派 STA 模式** | ❌ **未做** | 现在是纯 AP，不能出网 → 访问不了平台 |
| 15 | 树莓派装 mosquitto | ❌ 未做 | bridge 要连 broker 才能上平台 |
| 16 | NoMachine 客户端 | ❌ 未装 | 资料包内有安装包 |

**14 / 16 项完成**，缺的 3 项里有 2 项必须人做。

---

## 三、已确认的硬件事实（实测，非推测）

### 树莓派侧

| 项 | 值 |
|---|---|
| 型号 | Raspberry Pi 4 Model B Rev 1.4，Ubuntu 18.04.6，kernel 5.4.0 |
| 板载 UART | `/dev/ttyAMA0`（`uart-pl011`，PL011 rev2）、`/dev/ttyS0`（16550） |
| Python 依赖 | pyserial 3.5 / RPi.GPIO 0.6.5 / smbus2 全有 |
| 串口占用 | `/dev/ttyS0` 被厂商 `hiwonder_servo_manager`（ROS 节点）持有 |
| 厂商程序 | `armpi_fpv_bringup` 在跑（roslaunch PID 2085） |
| 逆运动学 | `~/armpi_fpv/src/armpi_fpv_kinematics/`（几何法，已封装） |
| 预置动作组 | `~/ArmPi_PC_Software/ActionGroups/*.d6a`（01.Hiwonder / grab-forward / wave） |

### 机械臂本体

- **6 自由度**：`joint1..joint5` + `r_joint`（机械爪）
- **home 位（厂商标定）**：

| 关节 | 弧度 | 角度 |
|---|---|---|
| joint1 基座旋转 | 0.0 | 0.00° |
| joint2 大臂 | 0.5236 | **30.00°** |
| joint3 小臂 | -1.3614 | **-78.00°** |
| joint4 腕 pitch | -1.7593 | **-100.80°** |
| joint5 腕 roll | 0.0 | 0.00° |
| r_joint 机械爪 | -1.7802 | **-102.00°** |

全是整数度的整数倍 → 厂商标定过，不是随机值。

---

## 四、踩过的三次坑（别再犯）

### 坑 1：用 `ls /dev/ttyUSB*` 判断串口存在

**错。** 板载 UART 是 `ttyAMA0`/`ttyS0`，**根本没有 ttyUSB* 节点**。
总线舵机走板载串口、不经 USB 转串口，所以"无 ttyUSB"完全正常。
据此误判成"舵机串口不存在"，白查一轮。

**正确判据**：`test -e /dev/ttyAMA0` 或 `ls /dev/tty*` 全量列。

### 坑 2：把 8080 静态网页的 topic 列表当运行时证据

`rosnode list` / `rostopic list` 均为空，那网页只是静态清单。
**要看运行时，不要看目录或网页。**

### 坑 3：双通道都超时 → 误判"硬件没接"

★ **本轮最重要的一次。**

`bus_servo_read_id` 在两条通道上都超时，我据此判断"硬件侧有问题"。
实际上是 **`hiwonder_servo_manager` 已经占用了 `/dev/ttyS0`** ——
我们另开一个 `Board()` 物理上收不到回包（半双工总线必须独占）。
**双通道都超时恰恰是"被别人占了"的特征。**

**正确做法**：诊断"设备无响应"前先 `fuser -v /dev/ttyS0` 确认是否被占。
`scripts/check_arm_hardware.py` 现在第一条就是这个。

---

## 五、两条对接路径的取舍

| | 方案 A · ROS 控制栈（**推荐**） | 方案 B · 直连串口 |
|---|---|---|
| 实现 | `ros_driver.py`（已完成） | `HiwonderBusServoArmDriver`（早已有） |
| 占用 | **与厂商程序共存** | **互斥**，须先停厂商节点 |
| 位置语义 | 弧度（有物理意义） | 脉宽 0–1000（无量纲） |
| 机械爪 | `/gripper_controller` 独立控制 | 序列里的一组舵机 |
| 逆运动学 | 厂商已封装，可直接用 | 需自己做 |
| 平台侧改动 | **无**（同一份 `ArmDriver` 协议） | 无 |
| 配置 | `backend: ros_arm_control` | `backend: hiwonder_bus_servo` + `sudo systemctl stop armpi_fpv_bringup` |

**「执行端可替换层」因方案 A 有了真实例证**：驱动实现从"直连串口"
换成"ROS action"，平台侧派单逻辑、状态机、证据链**一行不改**。

---

## 六、下一步（按顺序）

### 立刻可做（等你操作）

1. **重连热点** → 跑 `deploy_bridge_to_pi.py`（只读，不驱动机械臂）
2. **装 NoMachine 客户端** → 资料包 `远程桌面控制/nomachine_8.4.2_10_x64.exe`
3. **树莓派改 STA 模式** → 这是**访问不了平台的根因**，最关键
4. **树莓派装 mosquitto** → bridge 连 broker 用

### 必须人工（我做不了）

5. **示教抓取姿态**：在机械臂旁手动摆好抓取姿态，把 6 个关节角填进
   `edge/arm_bridge/config.yaml` 的 `pick_rad`
   （现在等于 `home_rad`，直接跑会抓空）

### 可选加分

6. 评估 `~/Ai_FPV/WasteSorting.py`（厂商预置的垃圾分拣玩法，与业务对口）
   —— 但那是**厂商预置玩法**，我们尚未接入，口径上要说清
7. 用预置动作组做演示兜底（来不及示教时）

---

## 七、相关文件

| 文件 | 用途 |
|---|---|
| `edge/arm_bridge/ros_driver.py` | ROS 控制栈驱动（方案 A） |
| `edge/arm_bridge/drivers.py` | 驱动协议与注册表 |
| `edge/arm_bridge/config.yaml` | 驱动配置（含 ros_arm_control 示例） |
| `scripts/deploy_bridge_to_pi.py` | 一键部署 + 只读验证 |
| `scripts/deploy_arm_sdk.py` | SDK 部署 + 双通道诊断 |
| `scripts/check_arm_hardware.py` | **串口占用与硬件线索（先跑这个）** |
| `scripts/probe_ros_control.py` | 读 `/joint_states` |
| `docs/competitions/arm-integration-correction-2026-10-05.md` | 方案修正记录 |
| `docs/competitions/pi-bridge-deployment-2026-10-05.md` | 树莓派部署手册 |
| `artifacts/raspberry-pi-probe.md` | 树莓派实测数据 |
