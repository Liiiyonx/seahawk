# 真机到货：接入与首跑操作手册

> 目标：把树莓派（ArmPiFPV）接进演示网络，让机械臂能被平台派单驱动。
> 依据：`edge/arm_bridge/drivers.py`（ArmDriver 协议 + 三个已注册实现）、
> `docs/competitions/arm-replaceable-layer-demo-script.md`（90 秒演示脚本）。
>
> ★ 全程守住口径：真机 + 仿真海面 = **E2 受控实验**。
> 不说"现场验证""已部署"，不说"坐标级抓取"。

## 当前状态（2026-10-05 00:30 实测）

| 项 | 值 |
|---|---|
| 本机 WLAN | 已连接 **HW-6AF67543**（树莓派 AP），本机 IP **192.168.149.249** |
| 树莓派 IP | **192.168.149.1** |
| SSH | 22 开（`ubuntu` / `hiwonder`） |
| NoMachine NX | 4000 开 |
| ROS 图像话题服务 | 8080 开（`ROS Image Topic List`） |
| **NoMachine Web Player** | **4080 关** → 社区版不开 Web Player |
| RDP / VNC / HTTP | 3389 / 5900 / 80 全关 |

**★ 跳转档位已定为 B（`nx://` 协议唤起）** —— 详见
`arm-hardware-probe-2026-10-05.md`（含 8080 暴露的 ROS 话题清单，
那是真机能力的直接证据）。

⚠️ **当前最大风险：电脑连的是树莓派 AP，这个网段没有外网出口，
访问不了 ECS 上的平台。** 必须尽快改 STA 模式，见第 2 步。

## 第 1 步 · 决定网络方案（最关键，先定这个）

树莓派默认是 **AP 直连模式**（自己开热点 `192.168.149.1`）。这个模式有个致命问题：
**演示电脑连了它就没网，访问不了 ECS 上的平台。**

| 方案 | 树莓派 | 演示电脑 | 优点 | 代价 |
|---|---|---|---|---|
| **A. STA 接入演示网（推荐）** | 改 STA，连现场路由器/热点 | 只连这一个网 | 平台在 ECS（公网）+ 真机在本地，电脑只连一个网 | 需改树莓派配置 |
| B. 双机 | 一台连热点跑平台本地版（docker compose） | 另一台放仿真台 | 网络最差时的兜底 | 要多一台电脑、跑本地全栈 |

**建议 A。** 下面按A 写步骤。

## 第 2 步 · 树莓派改 STA 模式

在树莓派上（HDMI + 键盘，或临时用 AP 模式 ssh 进去）：

```bash
# 1) 生成一份演示网配置
sudo raspi-config      # Network Options → SSID / Password 填现场 WiFi
# 或直接写文件：
sudo tee /etc/wpa_supplicant/wpa_supplicant.conf > /dev/null <<'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant group=sudo
update_config=1
country=CN
network={
    ssid="<现场WiFi 名>"
    psk="<现场 WiFi 密码>"
    key_mgmt=WPA-PSK
}
EOF

# 2) 关闭 AP 直连，启用STA
sudo systemctl stop dhcpcd
sudo systemctl disable dhcpcd
sudo systemctl restart networking

# 3) 确认拿到演示网 IP
ip addr show wlan0 | grep 'inet '
ip route | grep default
```

记下 `wlan0` 的 IP —— 后面填进 `VITE_ARM_CONSOLE_URL`。

> ★ 若要保留 AP 直连作为备用（推荐，现场网络出问题时能救命）：
> 在 `wpa_supplicant.conf` 里**同时**保留一个 `network={...}` 块即可，
> STA 优先连、连不上再回落到 AP。不要 `systemctl disable dhcpcd` 后就没兜底了。

## 第 3 步 · 三种跳转方式探测（决定走哪一档）

按 C → A → B 顺序试，谁通用谁。

```bash
# 在演示电脑上（换成第 2 步拿到的 IP）
PI=192.168.1.<树莓派IP>

# 档 C：Web 上位机？树莓派上查有没有 web 控制台
ssh ubuntu@$PI 'ls ~/Desktop /opt 2>/dev/null | head -30'

# 档 A：NoMachine Web Player（社区版是否开放 4080 待实测）
curl -s -o /dev/null -w "4080=%{http_code}\n" http://$PI:4080/
ssh ubuntu@$PI 'systemctl status nomachine --no-pager | head -5'
ssh ubuntu@$PI 'ss -tlnp | grep -E "4080|4000"'

# 档 B：NoMachine 客户端（演示机预装）
# 资料包里有 nomachine_8.4.2_10_x64.exe
```

结论填进 `frontend/.env.local`：

```bash
# 三档共用这一个键，组件按协议自动判断接入方式
VITE_ARM_CONSOLE_URL=http://<树莓派IP>:4080
# 若走协议唤起：VITE_ARM_CONSOLE_URL=nx://<树莓派IP>
VITE_ARM_CONSOLE_LABEL=ArmPiFPV 仿真台
VITE_ARM_DRIVER_BACKEND=hiwonder_bus_servo
```

改完**必须重新构建**前端，否则 env 不会生效：
```bash
cd frontend && npm run build
```

## 第 4 步 · 桥接层真机首跑

```bash
# 1) 平台侧：MQTT broker 要与树莓派同网可达
#    树莓派上
ssh ubuntu@$PI 'systemctl status mosquitto --no-pager | head -3'

# 2) 桥接层：先验证驱动能被注册表解析
python edge/arm_bridge/main.py --check-driver --driver hiwonder_bus_servo

# 3) 首跑：先 dry-run 验证协议闭环，再切真机
python edge/arm_bridge/main.py --driver simulated          # 第1 轮
python edge/arm_bridge/main.py --driver hiwonder_bus_servo # 第 2 轮
```

**首跑顺序**：

1. 确认舵机供电、机械臂处于**零位**（厂商说明书的安全位）
2. **用自带示教工具记录动作序列**（别手抄，工具会直接输出驱动能吃的格式）：

   ```bash
   # 在树莓派上跑（需要厂商的 ros_robot_controller_sdk.py 放在同目录）
   python3 edge/arm_bridge/tools/teach_hiwonder_sequence.py \
     --device /dev/ttyUSB0 --servo-ids 1 2 3 4 5 6 --output pick_sequence.json
   # 交互式：把机械臂摆到某个姿态 → 回车记录该姿态→ 摆下一个 → 回车 → q 保存
   ```

   首次只录 **3-5 个姿态**，别一上来就长序列 —— 序列越长，一次跑偏的破坏面越大。

3. 把输出接进配置（`pick_sequence_file` 比内联 `pick_sequence` 更可靠，格式不会抄错）：

   ```yaml
   driver:
     backend: "hiwonder_bus_servo"
     hiwonder_bus_servo:
       device: "/dev/ttyUSB0"
       pick_sequence_file: "pick_sequence.json"
   ```

4. 低优先级工单触发，观察 progress 回传
5. 确认 `emergency_stop` 真的有效（先单独测，不要在带负载时试）

> ★ `positions` 是 **0..1000 的舵机位置**，不是 GPS 坐标。
> 逆运动学源码没取回之前，绝不能说"坐标级抓取"。

## 第 5 步 · 抓可替换层证据（全场最硬的一块）

两轮跑同一个工单类型，把 MQTT 报文并排：

```bash
# 订阅（先起，再在平台派两轮单）
mosquitto_sub -h <broker> -t 'seahawk/arm/#' -v | tee /tmp/arm-compare.log
```

验收标准：**两轮报文逐字段一致，只有执行端不同。**
提前录屏存档——现场 broker/网络出问题时直接切录屏，口径不变（仍是 E2）。

## 第 6 步 · 页面核验

`ArmSimConsole` 的"执行后端"面板应显示：
- 三种驱动并列，`hiwonder_bus_servo`（真机那款）被高亮
- 状态标签显示「**树莓派可达**」（绿色）；不可达会变红并给排障指引

本地核验：
```bash
cd frontend
npm run build
node ./node_modules/vite/bin/vite.js preview --port 5199
node scripts/probe-arm-console.mjs   # 8 项断言
```

## 演示前 24 小时检查表

- [ ] 树莓派已 STA 接入演示网，IP 记在纸上（断电重启后可能变）
- [ ] AP 热点已保留为备用（现场网络炸了能救命）
- [ ] NoMachine 客户端已装演示机
- [ ] 平台 `VITE_ARM_CONSOLE_URL` 已指向正确地址，且**已重新 build**
- [ ] 机械臂零位复位、供电稳定、舵机无异响
- [ ] 应急停止已实测有效
- [ ] 真机演示录屏已存档
- [ ] 90 秒脚本彩排一遍（含第 4 段报文并排）

## 故障速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面显示「未检测到树莓派」 | 电脑与真机不同网 | 查第 2 步；确认树莓派拿到的是演示网 IP 而非 192.168.149.x |
| 电脑连了真机后访问不了平台 | 还在 AP 直连模式 | 必须改 STA，见第 2 步 |
| 4080 不通 | 社区版可能不开web player | 改走档 B（`nx://`），或树莓派上装 NoMachine 企业版 |
| NoMachine 客户端连上但黑屏 | X11 会话未启动 | 树莓派上`sudo systemctl start nomachine`，确认是图形会话 |
| 派单但机械臂不动 | 驱动没切 / MQTT 不通 | `--check-driver` 验证注册；查 broker 连通性 |
| 机械臂动作错乱 | 舵机方向/限位 | 重新示教并核对 `pick_sequence` 的 0..1000 范围 |
