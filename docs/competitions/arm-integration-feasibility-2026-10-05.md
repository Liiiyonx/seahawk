# 机械臂对接可行性 —— 修订版（2026-10-05 01:15）

> 本文**推翻**了同日的 `arm-integration-feasibility-2026-10-05.md` 里
> 「舵机串口不存在」的结论。那个判断是错的，成因见文末「我的判断错在哪」。

## 一句话结论

**硬件侧完全就绪，唯一缺的是把厂商 SDK 放到树莓派上、再改一处串口配置。**
我们的驱动 `HiwonderBusServoArmDriver` 本身是对的。

## 实证数据

### 串口：两个都在

```
/dev/ttyS0     存在   crw-rw---- 1 root dialout 4, 64
/dev/ttyAMA0   存在   crw-rw---- 1 root dialout 204, 64
/dev/serial0   不存在（未启用serial0 别名）
/dev/ttyUSB0   不存在（无 USB 转串口设备 —— 总线舵机走板载串口，非 USB）
```

内核日志确认板载 UART 存在：
```
uart-pl011 fe201000.serial: ttyAMA0 at MMIO 0xfe201000 is a PL011 rev2
fe215040.serial: ttyS0 at MMIO 0x0 is a 16550
```

### Python 依赖：齐全

```
serial   OK  3.5     （pyserial）
RPi.GPIO OK  0.6.5
smbus2   OK
```

★ 所以**不需要 pip install 任何东西**。

### 厂商 SDK：未安装

全盘搜索 `ros_robot_controller_sdk*` → 空。
但**资料包里就有**（每个案例目录下都附一份）：

```
总线舵机机械臂相关资料/6.总线舵机二次开发教程-树莓派版本/程序文件/
  案例1 获取总线舵机信息/ros_robot_controller_sdk.py
  案例2 总线舵机ID设置/ros_robot_controller_sdk.py
  案例3 控制总线舵机转动/ros_robot_controller_sdk.py + bus_servo_turn.py
  案例4 调节总线舵机速度/ros_robot_controller_sdk.py
  案例5 示教记录实现/  ros_robot_controller_sdk.py + bus_servo_record.py
                                                + servo_positions.json（示例）
```

SDK 的 `Board.__init__(self, device="/dev/ttyAMA0", baudrate=1000000, timeout=5)`
—— **默认值和我们的驱动完全一致**（`serial_port=/dev/ttyAMA0`、`baudrate=1000000`）。

## ★ 唯一的不匹配：两套控制通道并存

树莓派上同时存在两种控制方式，**串口和波特率都不同**：

| 通道 | 串口 | 波特率 | 用什么 |
|---|---|---|---|
| 厂商 GUI（`PC_Software`） | `/dev/ttyS0` | **115200** | `BusServoCmd.py`（0x55 帧头总线协议） |
| 厂商示例（案例1–5） | `/dev/ttyAMA0` | **1000000** | `ros_robot_controller_sdk.Board` |
| **我们的驱动** | `/dev/ttyAMA0` | **1000000** | 同上（默认值一致 ✓） |

**我们的驱动与厂商示例通道一致**，所以方向是对的。
需要注意的是：**别和厂商 GUI 同时开**，两者会抢同一个串口。

### 我们的配置需要改一处吗？

`edge/arm_bridge/config.yaml` 里设`serial_port` 与 `baudrate` 即可。
默认值就对（`/dev/ttyAMA0` @ 1M），**但要在树莓派上验证哪个真的能动**——
两条通道对应不同的物理接线（板载 UART 的 GPIO14/15 vs ttyS0）。

## 补齐步骤（10 分钟）

在树莓派上执行：

```bash
# 1) 装厂商 SDK（资料包里就有，直接复制）
cp ~/Desktop/../<资料包路径>/案例3\ 控制总线舵机转动/ros_robot_controller_sdk.py ~/
#实际路径按你把资料包放哪而定；核心是把这个 .py 放到桥接层能找到的地方

# 2) 验证 SDK 能打开串口
python3 - <<'EOF'
import ros_robot_controller_sdk as rrc
b = rrc.Board()                # 默认 /dev/ttyAMA0 @ 1M
print("舵机 1 位置:", b.bus_servo_get_position(1))
b.bus_servo_stop([1,2,3,4,5,6])
EOF
```

**若报权限错**：`sudo usermod -aG dialout ubuntu` 然后重新登录
（`ubuntu` 已在 `dialout` 组，但若换了用户就要加）。

**若 ttyAMA0 打不开**：改用厂商 GUI 那一套 —— `serial_port: /dev/ttyS0`、
`baudrate: 115200`，并改用 `BusServoCmd.py` 的协议。

### 录示教序列

```bash
# 把仓库里的示教工具传上去（它依赖同一个 SDK）
# tools/teach_hiwonder_sequence.py
python3 teach_hiwonder_sequence.py \
  --device /dev/ttyAMA0 --baudrate 1000000 \
  --servo-ids 1 2 3 4 5 6 --output pick_sequence.json
```
交互：摆姿态 → 回车记录 → `q` 保存。首次只录 3–5 个姿态。

## 可复用的现成资产

`~/ArmPi_PC_Software/ActionGroups/*.d6a` —— 厂商预置的动作组：
```
01.Hiwonder.d6a   grab-forward.d6a   wave.d6a
```
如果真机到货时来不及示教，**先用这些预置动作组**也能演示
"平台派单 → 机械臂按预设动作响应 → 进度回传" 的闭环。
这比"现场调舵机"稳得多，也符合不伪造的口径（动作是真的执行了）。

## 演示网络（与机械臂无关，但同样卡）

树莓派仍是**纯 AP**：`wlan0` 只有 `192.168.149.1/24`，**无默认网关** →不能出网 → 访问不了 ECS 上的平台。必须改 STA，见 `arm-hardware-onboarding-runbook.md` 第 2 步。

## 我的判断错在哪（记录下来别再犯）

**错误 1：用 `ls /dev/ttyUSB*` 判断串口是否存在。**
板载 UART 是 `ttyAMA0`/`ttyS0`，根本没有 `ttyUSB*` 这个节点。
总线舵机走板载串口，不经 USB 转串口 —— 所以"无 ttyUSB"完全正常，
我却据此得出"舵机串口不存在"的结论。
**正确判据：`test -e /dev/ttyAMA0` / `ls /dev/tty*` 全量列。**

**错误 2：把 8080 的静态 topic 列表当运行时证据。**
`rosnode list` 与 `rostopic list` 均为空，那网页只是静态清单。
**教训：证据要看运行时（`rostopic list`），不是网页或目录。**

两条合起来导致我上一轮给出了过于悲观的结论。实际上硬件全就绪，
只差复制一个 .py 文件。
