# 真机对接可行性评估（2026-10-05 01:00 采集）

> 数据来源：`scripts/probe_raspberry_pi.py` SSH 只读采集，原始输出
> `artifacts/raspberry-pi-probe.md`。**未修改树莓派任何配置。**

## 一句话结论

**舵机控制接口在树莓派上找不到**——串口、厂商 SDK、ROS 舵机话题三者皆无。
现有 `HiwonderBusServoArmDriver` 直接用会失败，且失败原因不是配置问题。
**必须先弄清机械臂怎么被指挥**，才能谈对接。

## 设备事实

| 项 | 值 |
|---|---|
| 主机名 / 系统 | `ubuntu`，Ubuntu 18.04.6 LTS，kernel 5.4.0-1047-raspi |
| 架构 | **aarch64** |
| 磁盘 | 29G，已用 14G（47%），余15G |
| 运行时长 | 33 分钟 |
| 桌面 | GDM running，lightdm exited，**有 X11 会话**（`ubuntu :0`） |
| NoMachine | **7.1.3-2** |
| `/opt` 内容 | `create_ap`（热点）、`pigpio`、`ros/melodic` |
| 桌面目录 | `LAB_TOOL.desktop`、`PC_Software.desktop`、`rpi_packages`、`yolov5-master` |

## 三个致命缺口

### ① 舵机串口：不存在

```
$ ls -l /dev/ttyUSB* /dev/ttyACM*
无 USB/ACM 串口设备
```

`HiwonderBusServoArmDriver` 默认走 `/dev/ttyAMA0`（Pi 板载 UART）。
**没有 `/dev/ttyUSB*` 也没有 `/dev/ttyACM*`** ——要么舵机没接，
要么它走板载 UART（但 `/dev/ttyAMA0` 是蓝牙串口，通常被占用）。

### ② 厂商 SDK：不在

```
$ python3 -c "import ros_robot_controller_sdk"
ModuleNotFoundError: No module named 'ros_robot_controller_sdk'
```

`tools/teach_hiwonder_sequence.py` **依赖这个 SDK**，所以示教工具现在跑不了。

### ③ ROS 舵机话题：无

```
$ rosnode list        → 空
$ rostopic list       → 空
$ rostopic list | grep -iE "servo|joint|arm|gripper"  → 未发现
```

**但 `/opt/ros/melodic` 存在**。8080 那个 `ROS Image Topic List`
页面列出的`/object_sorting` 等话题，是某个**只在需要时启动的节点**
发布的历史残留或预置清单，**当前没有节点在跑**。

> ★ 这修正了我上一轮的判断：8080 的topic 列表**不能**当作
> "真机具备分拣能力"的证据。它是静态页面，不是运行时状态。
> 那个页面甚至可能只是某个演示脚本的输出。
> **口径必须收紧：目前没有任何证据表明真机已具备分拣能力。**

## 其他发现

**NoMachine 7.1.3-2（旧版）** —— 与资料包里的 `8.4.2` 不一致。
7.x 同样不提供 Web Player，所以走 `nx://` 的结论不变。
★ 演示机装客户端时注意版本差异。

**树莓派是纯 AP 模式**：
- 无 `wpa_supplicant.conf` → **完全没有 STA 配置**
- `wlan0` 只有 `192.168.149.1/24`，**无默认网关** → 不能出网
- `/opt/create_ap` 证实是 create_ap 做的热点

**树莓派上没有 MQTT broker**（`inactive`、未监听 1883）。
平台的闭环依赖它，这个也要装。

**aarch64 架构** —— 若厂商提供 arm 二进制工具，注意是对应 aarch64 的。

## 桥接层怎么办：三条分支

### 分支 1 · 舵机根本没接（最可能）

现象与证据吻合：没有串口设备、没有 SDK、机械臂没通电或没接线。
**这是硬件问题，不是软件问题。** 先确认：
- 机械臂供电是否正常（指示灯）
- 舵机线是否插在树莓派上
- 厂商给的驱动板是否接了

接上后重跑本脚本，应能看到 `/dev/ttyUSB0`。

### 分支 2 · 走板载 UART

若舵机接在 GPIO14/15（板载 UART），设备是 `/dev/ttyAMA0` 或 `/dev/serial0`。
需在 `config.yaml` 里改 `serial_port`，并确认蓝牙未占用（改
`/boot/config.txt` 里的 `dtoverlay=disable-bt`）。

### 分支 3 · 真机由厂商自己的程序驱动

桌面有 `LAB_TOOL.desktop`、`PC_Software.desktop` —— 很可能就是厂商的
上位机。机械臂可能已经被厂商程序接管，接口不对外暴露。
**这种情况不要试图接管它**，而是：
- 用厂商程序做示教与动作回放（它的示教界面通常更可靠）
- 我们只负责"派单 → 通知操作员 → 记录结果"，机械臂动作由厂商程序执行

★ **这个分支反而可能是答辩上最诚实也最省事的方案**：
我们证明了"平台不依赖执行端"，而不是"我们驱动了执行端"。
口径：平台侧调度与证据链完整，机械臂执行由厂商工具承担。

## 立刻要做的三件事（按顺序）

1. **确认机械臂硬件状态** —— 通电？接线？厂商程序能打开吗？
   这一条不确认，后面都是空谈。
2. **改 STA 模式** —— 树莓派现在无网关、不能出网，访问不了平台。
   同时在树莓派装 mosquitto（闭环的另一半）。
3. **重新采集** —— 硬件接好后重跑 `probe_raspberry_pi.py`，
   看串口是否出现、SDK 是否需要补。

## 我已经做的准备

`HiwonderBusServoArmDriver._new_board()` 的错误提示已改：
现在**先检查串口是否存在**，报出实际存在的 `/dev/ttyUSB*` 列表，
并明确提示"若真机走 ROS 而非UART，平台需要一个实现同一ArmDriver
协议的 RosArmDriver"。避免现场拿到"SDK unavailable"这种指向错误的提示。

桥接层 20 项测试全部通过。
