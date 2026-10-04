# 厂商资料精读报告（2026-10-05）

> 来源：`C:\Users\Liii\Desktop\树莓派总线舵机机械臂和麦轮底盘相关资料\`
> 与 `C:\Users\Liii\Desktop\Movelt文档\`，共 39 份 PDF。
> 文本化产物在 `artifacts/vendor-docs/`，转换脚本 `scripts/pdf_to_text.py`。
> ★ 本文结论均来自文档原文与代码示例，不是推测。

## 一、资料包里混了两家厂商的协议（最容易踩的坑）

**树莓派上装的是幻尔（Hiwonder）ArmPi FPV**，舵机走**幻尔 LOBOT 二进制协议**：

```
SDK 帧格式：0xAA 0x55 Length Function ID Data Checksum
```

但**底盘资料里的「总线舵机介绍」是杭州众灵（ZL-robot）的产品**，用的是
**完全不同的 ASCII 协议**：

```
#000P1500T1000!        控制舵机（ID 3 位、PWM 4 位、Time 4 位，单位 ms）
#000PID!               读取 ID
#000PRTV!              读温度电压，返回 #000T28.1V7.4!
#000PULK! / #000PULR!  释放/恢复扭力
```

**两套协议不兼容。** 我们的 `HiwonderBusServoArmDriver` 走的是幻尔 SDK
（`ros_robot_controller_sdk.py`），**与资料包里的机械臂部分一致**，
但如果照着底盘那份「总线舵机介绍」写代码会完全跑不通。

**判断依据**：看 `案例1–5` 里的 `ros_robot_controller_sdk.py` —— 帧头是
`0xAA 0x55`，这是幻尔格式。

## 二、串口与通道（实测已在树莓派上验证）

| 项 | 值 |
|---|---|
| 板载 UART | `/dev/ttyAMA0`（内核 `uart-pl011`，PL011 rev2）、`/dev/ttyS0`（16550） |
| 树莓派型号 | Pi 4 Model B Rev 1.4，aarch64 |
| 幻尔 SDK 默认 | `device="/dev/ttyAMA0", baudrate=1000000` |
| 众灵 ASCII 协议 | 115200 |
| 厂商 GUI `ArmPi_PC_Software` | `/dev/ttyS0` @ 115200 |
| Python 依赖 | pyserial 3.5 / RPi.GPIO 0.6.5 / smbus2 **均已装** |
| 供电 | 7.4V 2200mAh 锂电池接扩展板，**舵机功耗由扩展板供电，不由树莓派供电** |

`enable_uart=1` 已在 `/boot/firmware/config.txt` 启用（Pi4 用 firmware 目录）。

**两套控制通道并存，别同时开**（抢同一串口）：
- 厂商 GUI → `/dev/ttyS0` @115200
- 厂商示例 + 我们的驱动 → `/dev/ttyAMA0` @1000000

## 三、发现并修复的两个真实缺陷

### 缺陷 1 · 厂商示教 JSON 格式不兼容（会直接报错）

厂商示教程序 `案例5 示教记录实现/bus_servo_record.py` 写出的是**扁平位置列表**：

```json
[1000, 940]
```

那是**单个舵机**的位置序列（程序用 `bus_servo_read_id()[0]` 取第一个舵机）。
而我们的 `_load_sequence_file` 只接受 `{"duration":…, "positions":[…]}` 格式，
直接喂进去会抛 `ValueError`。

**已修**：加载时识别「全数字列表」并自动转成单舵机 step。
新增测试 `test_hiwonder_vendor_format.py` 覆盖（10 项）。

### 缺陷 2 ·电池遥测永远读不到（静默失败）

`Board.get_battery()` 是**非阻塞**的：只从已收到的队列里取，队列空即返回 `None`。
原实现只调一次 → 永远读不到 → `battery` 恒为构造初值。
这是典型的「声明了却没实现」，不报错、不告警。

**已修**：加重试（6 次 ×50ms），并把控制板电压粗略换算为百分比。
新增测试验证「前几次 None、重试后拿到真实电压」。

### 顺手补齐：舵机遥测（证据链价值）

我们原本只用了 SDK 三个方法（`set_position` / `stop` / `enable_torque`），
**丢掉了最有价值的一批**：

| SDK 方法 | 用途 |
|---|---|
| `bus_servo_read_vin` | 舵机电压 |
| `bus_servo_read_temp` | 舵机温度 |
| `bus_servo_read_position` | 舵机位置回读 |

这些是「**机械臂真的动了**」的硬证据 —— progress 报文是平台自报，
而这些数字来自舵机本身。答辩被问「怎么证明真机执行了」，
拿这个出来比架构图有说服力。

已给 `ArmStatus` 加 `servos` 字段，逐舵机回读，单个失败不影响其余
（总线回读是异步队列，单次调用常赶不上回包）。

## 四、树莓派上的完整玩法清单（资料证实）

`~/ArmPi_PC_Software/ActionGroups/` 有预置动作组：
`01.Hiwonder.d6a` / `grab-forward.d6a` / `wave.d6a`
—— **来不及示教时可直接用它们演示闭环**，动作是真执行的。

`~/Ai_FPV/` 里有 AI 视觉玩法源码，含 **`WasteSorting.py`（垃圾分拣）**、
AprilTag 识别/追踪、色块识别追踪、手势识别等。
`~/armpi_fpv/src/` 下有 ROS 节点：`object_sorting`（智能分拣）、
`object_pallezting`（智能码垛）、`object_tracking`（色块追踪）、
`face_detect`、`warehouse`、`asr_control`。

ROS 玩法通过 **service** 控制（不是 topic）：
```bash
rosservice call /object_pallezting/enter "{}"
rosservice call /object_pallezting/set_running "data: true"
```

**口径价值**：`WasteSorting.py`（垃圾分拣）与我们的业务高度对口 ——
但要诚实说明它是**厂商预置玩法**，我们尚未把它接进平台调度。

## 五、逆运动学已在树莓派上封装好

路径：`/home/ubuntu/armpi_fpv/src/armpi_fpv_kinematics/kinematics/`
用法（来自第4课）：

```python
from ArmIK import ArmMoveIK
AK = ArmMoveIK()
AK.setPitchRangeMoving((x, y, z), 俯仰角, 俯仰下限, 俯仰上限, 舵机时间ms)
```

- 采用**几何法**（解一元二次方程），不是迭代解算 —— 速度快
- 去掉底座云台旋转关节，在二维平面分析
- 这意味着**从末端坐标反解关节角是可行的**

★ 这修正了我们之前的口径：`pick_sequence` 用示教位置而非坐标，
是因为当时**没有**逆运动学。实际上树莓派上已封装好了——
只是我们还没接。这是 P2 改进项，不是技术障碍。

## 六、MoveIt 资料（VMware 里的 Ubuntu 镜像）

9 份课件：URDF 入门 / URDF 模型说明 / MoveIt 注意事项 / 随机移动 /
运动学设计 / 笛卡尔路径 / 碰撞检测 / 场景设计 / 轨迹规划。

维持既有判断：**MoveIt 留在 VMware 里，不进主演示线**。
理由（与之前一致，现在有文档支撑）：它是纯软件仿真，不碰真机；
演示价值低于「两轮驱动切换+ 报文一致」。

但它有个新用途：**作为「我们精读过厂商技术栈」的举证材料**。
若评委追问运动规划/碰撞检测怎么做，可以当场打开。

## 七、远程桌面（厂商教程印证了我的判断）

`第1课 远程工具安装与连接.pdf` 明确：

- **AP 直连模式**：树莓派开热点，**不能联通外部网络**
- **STA 局域网模式**：树莓派主动连指定热点，**可联通外部网络**

教程给的连接参数：`192.168.149.1`，账号 `ubuntu`，密码 `hiwonder`。
教程里配的是 `nomachine_7.1.3_1.exe` —— **与树莓派上的 7.1.3-2 同版本**，
而资料包远程桌面目录里放的是 `8.4.2`。两者都可用，7.x 无 Web Player。

★ 教程还提示：AP 模式下搜不到热点时，改 5G 频段（`第1课开发环境搭建
  → 3.频段修改方法`）。我们本机 Wi-Fi 6E 支持 5G，实际连上了，无需处理。

## 八、待办（按优先级）

1. **P0** 树莓派改 STA 模式 —— AP 模式不能出网，访问不了平台
2. **P0** 装 NoMachine 客户端（资料包内 `nomachine_8.4.2_10_x64.exe`）
3. **P0** 复制幻尔 SDK 到树莓派，验证 `bus_servo_read_position(1)` 有返回
4. **P1** 录一段 3–5 姿态示教序列（或直接用预置动作组）
5. **P2** 把树莓派已有的逆运动学接进驱动，支持按坐标派单
6. **P2** 评估能否调用 `WasteSorting.py` 做真正的垃圾分拣
