# ★ 对接方案重大修正（2026-10-05 02:00）

> 本文**推翻**了同日凌晨两份文档里「舵机没回包 → 硬件没接」的结论。
> 真机是活的，ROS 控制栈正在运行。是我诊断方法错了。

## 一句话结论

**机械臂已被厂商 ROS 栈控制，`/joint_states` 在正常发布 6 个关节的实时角度。**
对接应该走 **ROS action/topic**，而不是自己抢 `/dev/ttyS0` 直连串口。

## 实测证据

```json
{
  "joint_names": ["joint1","joint2","joint3","joint4","joint5","r_joint"],
  "positions":   [0.0, 0.5236, -1.3614, -1.7593, 0.0, -1.7802],
  "velocities":  [0, 0, 0, 0, 0, 0],
  "efforts":     [0, 0, 0, 0, 0, 0]
}
```

换算成角度：

| 关节 | 弧度 | 角度 | 推测含义 |
|---|---|---|---|
| joint1 | 0.0000 | 0.00° | 基座旋转 |
| joint2 | 0.5236 | **30.00°** | 大臂 |
| joint3 | -1.3614 | **-78.00°** | 小臂 |
| joint4 | -1.7593 | **-100.80°** | 腕 pitch |
| joint5 | 0.0000 | 0.00° | 腕roll |
| r_joint | -1.7802 | **-102.00°** | 机械爪开合 |

**全是整数度的整数倍**（30 / 78 / 100.8 / 102）→ 这是厂商标定的home 位，
不是随机值。说明厂商程序已经标定过这只手。

## 厂商 ROS 控制接口（实测存在）

```
/arm_controller/follow_joint_trajectory/{goal,result,feedback,cancel}
/arm_controller/state
/arm_controller/command
/gripper_controller/...            （机械爪独立控制器）
/joint_states（话题，正常发布）
/hiwonder_servo_manager/...        （厂商自己的舵机管理节点）
/rosbridge_websocket               （浏览器桥，说明厂商有 Web 控制台）
```

`/hiwonder_servo_manager` 节点持有 `/dev/ttyS0`（PID 8534）——
**它才是舵机的正确持有者**。我们的驱动去抢那个串口，抢不到也读不到。

## 我错在哪

**诊断方法错了，不是硬件问题。** 时间线：

1. `deploy_arm_sdk.py` 读 `bus_servo_read_id` 超时 → 我判断"舵机没回包"
2. 双通道都试过 → 我判断"不是通道选错，是硬件"
3. ★ **漏了关键一步**：没先问「厂商程序自己读到舵机了吗」

第1 步的超时是**必然的**，因为 `hiwonder_servo_manager` 已经把串口拿走了。
我们另开一个 `Board()` 即使能 open，物理上也收不到回包（半双工总线被占）。
**双通道都超时恰恰是"被别人占了"的特征，我却解读成"硬件没接"。**

**教训**：
- 诊断"设备无响应"前，先确认**是不是被别人占着**。
  `fuser -v /dev/ttyAMA0 /dev/ttyS0` 一条命令就能看出来，我晚了一步。
- 厂商设备已被封装成ROS 控制栈时，**不要绕过它自己接硬件**。
  绕过 = 与它抢总线 = 必然失败。

## 修正后的对接方案

### 方案 A（推荐）·走 ROS action —— 复用厂商控制栈

平台侧新增一个 `RosArmDriver`（实现同一份 `ArmDriver` 协议）：

```
platform MQTT → arm_bridge → ROS action client
  → /arm_controller/follow_joint_trajectory/goal
  → 订阅 /joint_states 拿反馈
  → progress 回传平台
```

**优势**：
- 不抢串口，与厂商程序和平共存
- 关节角是**弧度**（有物理意义），比 0–1000 脉宽值更可解释
- `/gripper_controller` 单独控制机械爪
- 逆运动学已在厂商节点里（`armpi_fpv_kinematics`），可直接用末端坐标

**「可替换层」口径反而更强**：
驱动的实现从"直连串口"换成"ROS action"，`ArmDriver` 协议与平台侧**一行不改**
——这正是我们一直强调的"执行端可替换"，现在有了真实例证。

### 方案 B · 停掉厂商节点后直连串口

```bash
sudo systemctl stop armpi_fpv_bringup   # 或 kill 8534 / roslaunch 2085
```
之后 `ttyS0` 释放，我们的 `HiwonderBusServoArmDriver` 可直连。

**代价**：失去 ROS 的逆运动学与动作组，且与厂商 GUI 互斥。
**不推荐** —— 方案 A 更好。

## 下一个动作（方案 A）

1. 读 `/arm_controller/follow_joint_trajectory` 的 action 定义（关节数、容差）
2. 读厂商 URDF（在 `armpi_fpv` 描述目录），拿到关节限位
3. 实现 `RosArmDriver`，复用现有 `ArmDriver` 协议
4. 用 `/joint_states` 做舵机遥测的数据源 —— 比串口读电压更直接

## 相关文件

- `scripts/probe_ros_control.py` — 读 joint_states 与控制器（本次用的）
- `scripts/probe_ros_servo.py` — 问厂商节点的 service/topic
- `scripts/check_arm_hardware.py` — 串口占用与硬件线索
- `scripts/deploy_arm_sdk.py` — SDK 部署与双通道诊断
