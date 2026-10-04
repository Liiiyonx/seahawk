# 树莓派部署 bridge：实测记录与操作手册

> 记录时间：2026-10-05 02:00（SSH 实测）
> 配套脚本：`scripts/deploy_bridge_to_pi.py`（一键部署 + 只读验证）

## 一、树莓派侧实测结果（全部已确认）

| 检查项 | 结果 |
|---|---|
| 系统 | Ubuntu 18.04.6，kernel 5.4.0-1047-raspi，aarch64 |
| 型号 | Raspberry Pi 4 Model B Rev 1.4 |
| **rospy** | ✓ OK |
| **sensor_msgs.msg** | ✓ OK |
| **control_msgs.msg** | ✓ OK |
| **trajectory_msgs.msg** | ✓ OK |
| Python 依赖 | pyserial 3.5 / RPi.GPIO 0.6.5 / smbus2 全有 |
| `/joint_states` | ✓ **正在以 20Hz 发布** |
| 关节 | `joint1..joint5` + `r_joint`（机械爪）= 6 自由度 |
| 串口 `/dev/ttyAMA0` | 存在（内核 `uart-pl011`，PL011 rev2） |
| 串口 `/dev/ttyS0` | 存在（16550） |
| **`/dev/ttyS0` 被占** | 厂商 `hiwonder_servo_manager`（PID 8534） |
| `armpi_fpv_bringup` | 在跑（roslaunch PID 2085） |
| mosquitto | **inactive**（1883 未监听） |
| paho-mqtt | **缺**（部署脚本会自动装） |
| 磁盘 | 29G，已用 14G（47%） |

## 二、home 位（厂商标定值，实测）

```json
{"positions": [0.0, 0.5236, -1.3614, -1.7593, 0.0, -1.7802]}
```

| 关节 | 弧度 | 角度 |
|---|---|---|
| joint1（基座旋转） | 0.0 | 0.00° |
| joint2（大臂） | 0.5236 | **30.00°** |
| joint3（小臂） | -1.3614 | **-78.00°** |
| joint4（腕pitch） | -1.7593 | **-100.80°** |
| joint5（腕 roll） | 0.0 | 0.00° |
| r_joint（机械爪） | -1.7802 | **-102.00°** |

**全是整数度的整数倍** → 厂商标定过的 home 位，不是随机值。

## 三、部署步骤

```bash
# 前提：电脑连上树莓派 AP 热点（HW-6AF67543），树莓派 IP 192.168.149.1
export PI_PASSWORD=hiwonder

# 部署 + 只读验证（★ 不下发任何运动指令）
python scripts/deploy_bridge_to_pi.py --host 192.168.149.1 --backend ros_arm_control
```

脚本做四件事：
1. 上传 10 个文件到 `~/seasight_bridge/`
2. 装 `paho-mqtt`（树莓派上没有）
3. 把 `config.yaml` 的 `driver.backend` 改成指定值
4. 跑一次 `status()`，打印关节遥测

## 四、★ 首次真机动作必须人工盯着

`--allow-motion` 会**真实驱动机械臂**。首次不要加。

正确顺序：
1. 先只跑 `status()`，确认能读到 6 个关节角
2. 确认读到的角与上面的 home 位一致（不一致说明连的不是这台机械臂）
3. **人工示教**一个抓取姿态，把关节角填进 `config.yaml` 的 `pick_rad`
4. 现场有人盯着，再跑 `pick()`

★ `pick_rad` 目前等于 `home_rad`，直接跑会抓空。

## 五、闭环比对演示（可替换层证据）

平台侧的 `driver.backend` 一字段切换，桥接层与平台**一行不改**：

```bash
# 第 1 轮：仿真
python edge/arm_bridge/main.py --driver simulated
# 平台派单 → 工单走完 pending→assigned→navigating→collecting→done

# 第 2 轮：真机（同一套派单操作）
python edge/arm_bridge/main.py --driver ros_arm_control
# 机械臂按示教姿态动作，/joint_states 回传真实关节角
```

**报文逐字段一致，只有执行端不同** —— 这是「可替代层」最硬的证据。
提前录屏存档，现场网络出问题就切录屏。

## 六、待办

| 事项 | 优先级 | 说明 |
|---|---|---|
| **示教抓取姿态** | **P0** | 必须人工做，我没法代做 |
| 树莓派装 mosquitto | P0 | bridge 要连broker 才能上平台 |
| 树莓派改 STA 模式 | P0 | 现在是纯 AP，不能出网 → 访问不了平台 |
| 装 NoMachine 客户端 | P0 | 资料包内有 `nomachine_8.4.2_10_x64.exe` |
| 评估 `WasteSorting.py` | P1 | 厂商预置的垃圾分拣玩法，与业务对口 |
| 动作组兜底 | P1 | `~/ArmPi_PC_Software/ActionGroups/*.d6a` |

## 七、一个查法上的坑（我自己踩了）

查action server 是否存在时，我用 `rosservice list | grep
follow_joint_trajectory` 得到 0，就以为 action server 没起来。

**错的** —— action 的 goal/result/feedback 都是**话题**，不是 service。
正确查法：

```bash
rostopic list | grep follow_joint_trajectory
# 会看到 /arm_controller/follow_joint_trajectory/{goal,result,feedback,cancel,status}
#      /gripper_controller/follow_joint_trajectory/...
```

★ 查 ROS 接口类型前先确认它属于service 还是 topic/action，
   否则会得出"接口不存在"的错误结论。
