# 真机接入探测记录（2026-10-05 00:30）

## 结论：走**档 B（nx:// 协议唤起）**

三档探测结果：

| 档 | 检查项 | 结果 | 判定 |
|---|---|---|---|
| **C** ArmPiFPV Web 上位机 | 树莓派是否有 Web 上位机 | **8080 开放但是 ROS 图像话题列表**（`ROS Image Topic List`），不是控制台 | ❌ 不是 Web 上位机 |
| **A** NoMachine Web Player | 4080 端口 | **关闭** | ❌ 社区版未开放 Web Player |
| **B** nx:// 协议唤起 | 4000 端口 | **开放**（NX 二进制协议，不响应 HTTP —— 符合预期） | ✅ **可��** |

**A 档被否掉的原因要记住**：NoMachine 社区版不开Web Player（4080 根本不监听）。
演示机必须预装 NoMachine 客户端才能用。

## 现场探测到的真实信息

```
本机 WLAN SSID   : HW-6AF67543           （树莓派 AP 直连模式）
本机 WLAN IP    : 192.168.149.249
树莓派 IP        : 192.168.149.1
SSH              : 22开（需密码 ubuntu/hiwonder，本机无 sshpass 无法非交互登录）
NoMachine NX     : 4000 开
ROS 图像话题服务 : 8080 开
NoMachine Web    : 4080 关
RDP              : 3389 关
VNC              : 5900 关
HTTP             : 80 关
```

### 8080 暴露的 ROS 话题（重要发现）

`ROS Image Topic List` 页面列出：

```
/usb_cam/image_raw                  (Snapshot)
/lab_config_manager/image_result    (Snapshot)
/out/image_result                   (Snapshot)
/face_detect/image_result           (Snapshot)
/in/image_result                    (Snapshot)
/object_sorting/image_result        (Snapshot)
/object_tracking/image_result       (Snapshot)
/object_pallezting/image_result     (Snapshot)
/exchange/image_result              (Snapshot)
```

**这些话题名直接印证了机械臂的实际能力**：
- `object_sorting` / `object_pallezting`（分拣 / 放置）—— 对应「抓取并归置垃圾」
- `object_tracking` —— 目标跟踪
- `exchange` —— 交接动作
- `usb_cam/image_raw` —— 单目相机原始画面（对应 ArmPiFPV 的相机）

★ **口径价值**：`object_sorting` 这个话题名比任何文档描述都更有说服力 ——
它证明真机上跑的是**分拣**逻辑，不是"假装动一下"。
答辩时若被问"你们真机真的能分拣吗"，可以直接指着这个话题回答。

**但也要诚实**：这些是 ROS 侧的能力证据，**不等于**我们的平台已经能驱动它。
平台侧要接的是 `edge/arm_bridge` 的 MQTT 契约，两者尚未对接（见下方缺口）。

## 当前缺口（按优先级）

### 1. 演示电脑会失去平台访问（最高优先级，必须解决）

现在电脑连的是树莓派 AP（`192.168.149.x`），**这个网段没有外网出口**，
所以现在**访问不了 ECS 上的平台**。答辩时这等于致命伤。

必须把树莓派改 STA 模式接入演示网，让两者同网且能出网。

### 2. 平台侧桥接层尚未与真机对接

`edge/arm_bridge/drivers.py` 的 `HiwonderBusServoArmDriver` 假设
总线舵机走`ros_robot_controller_sdk.py`（厂商SDK，走串口 `/dev/ttyUSB*`）。
但从 8080 看到真机实际跑的是 ROS 话题栈。

**两者是否一致需要你在树莓派上确认**（见下）。

### 3. 还没有示教序列

首次真机跑之前必须录一个 3-5 姿态的短序列：

```bash
# 在树莓派上（旁边需有厂商 ros_robot_controller_sdk.py）
python3 edge/arm_bridge/tools/teach_hiwonder_sequence.py \
  --device /dev/ttyUSB0 --servo-ids 1 2 3 4 5 6 --output pick_sequence.json
```

★ 记下`positions` 是 **0..1000 的舵机位置**，不是 GPS 坐标。

## 下一步需要的操作（需你在树莓派上执行）

我够不到树莓派（SSH 要密码且本机无 sshpass）。请在树莓派上跑这段，
把输出贴回来 —— 我据此决定桥接层要不要改：

```bash
# ①ROS 栈到底在跑什么
rosnode list 2>/dev/null || echo "无 rosnode"
rostopic list 2>/dev/null | head -20
rosversion -d 2>/dev/null

# ② 舵机是走串口还是 ROS 服务？（决定 HiwonderBusServoArmDriver 能否直接用）
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
ls ~/ros_robot_controller_sdk.py 2>/dev/null && echo "厂商SDK 在家目录" || echo "SDK 不在家目录"

# ③ NoMachine 版本（确认社区版情况）
dpkg -l | grep -i nomachine || systemctl status nomachine --no-pager | head -3

# ④ 有没有 Web 上位机（最终确认 C 档）
ls ~/Desktop /opt 2>/dev/null | head -20

# ⑤ 舵机串口是否在位
python3 -c "import serial; s=serial.Serial('/dev/ttyUSB0',1000000); print('串口 OK'); s.close()" 2>&1 | tail -2
```

## 演示配置（暂定，待 STA 改造后填入真 IP）

```bash
# frontend/.env.local
# ★ 走档 B：nx:// 协议唤起（本机实测 4080 关闭，Web Player 不可用）
VITE_ARM_CONSOLE_URL=nx://192.168.149.1
VITE_ARM_CONSOLE_LABEL=ArmPiFPV 仿真台
VITE_ARM_DRIVER_BACKEND=hiwonder_bus_servo
```

改完**必须重新构建**：`cd frontend && npm run build`
（env 是构建期注入的，不 build 不生效）。

演示机需预装 `nomachine_8.4.2_10_x64.exe`（资料包里有）。
