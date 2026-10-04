# 树莓派（ArmPiFPV）信息采集记录

- 采集时间：2026-10-05 01:00
- 目标：`ubuntu@192.168.149.1`
- 方式：SSH 只读探测，**未修改任何配置**

---

## 系统与网络

> 为什么问：系统版本、架构（决定能否直接跑厂商 arm 二进制）

```
ubuntu
Linux ubuntu 5.4.0-1047-raspi #52~18.04.1-Ubuntu SMP PREEMPT Wed Nov 24 12:29:36 UTC 2021 aarch64 aarch64 aarch64 GNU/Linux
NAME="Ubuntu"
VERSION="18.04.6 LTS (Bionic Beaver)"
```

## ★ STA 模式现状（决定演示网络方案）

> 为什么问：★ 关键：是否已配 STA。有 network={ssid=...} 才是STA；只有本机热点配置则是 AP

```
无 wpa_supplicant.conf（可能仍是 AP 直连模式）
```

## 网络接口与地址

> 为什么问：wlan0 有没有拿到演示网 IP；有无默认网关（决定能否出网访问平台）

```
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    inet 127.0.0.1/8 scope host lo
3: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    inet 192.168.149.1/24 brd 192.168.149.255 scope global wlan0
--- routes ---
192.168.149.0/24 dev wlan0 proto kernel scope link src 192.168.149.1
```

## ★ 舵机串口（决定 HiwonderBusServoArmDriver 能否直接用）

> 为什么问：★ 关键：有 ttyUSB/ttyACM 才说明舵机走串口；没有则必须改走 ROS 服务

```
无 USB/ACM 串口设备
```

## ★ 厂商 SDK 是否在位

> 为什么问：★ 关键：SDK 在则示教工具能直接跑；不在则要先从厂商资料补齐

```
ModuleNotFoundError: No module named 'ros_robot_controller_sdk'
```

## ★ ROS 栈详情

> 为什么问：★ 关键：判断舵机控制走ros service 还是 topic —— 这决定桥接层要不要改

```
--- nodes ---
--- topics ---
```

## ★舵机控制接口（最关键的一问）

> 为什么问：★★ 最关键：真机怎么被指挥？平台桥接层要按这个接口写

```
未发现舵机相关 topic/service
```

## MQTT（平台闭环的另一半）

> 为什么问：★ 关键：树莓派上是否有 broker；平台桥接层要连它

```
inactive
未监听 MQTT 端口
```

## NoMachine

> 为什么问：版本（社区版无 Web Player，需记录以便评委问起时解释）

```
nomachine 7.1.3-2
```

## 桌面环境（决定 NoMachine 里能不能看到 GUI）

> 为什么问：★ 关键：X11 会话是否在跑 —— 没跑则 NoMachine 连上也是黑屏

```
DISPLAY/desktop:
Xreset
Xreset.d
Xresources
   Loaded: loaded (/etc/init.d/lightdm; generated)
   Active: active (exited) since Sat 2022-02-12 12:38:46 UTC; 32min ago
   Loaded: loaded (/lib/systemd/system/gdm.service; static; vendor preset: enabled)
   Active: active (running) since Sat 2022-02-12 12:38:46 UTC; 32min ago
ubuntu   :0           2022-02-12 12:38 (:0)
```

## 候选 Web 上位机 / 厂商应用

> 为什么问：最终确认 C 档（原生 Web 上位机）是否存在

```
/home/ubuntu/Desktop:
LAB_TOOL.desktop
New File
New File.txt
PC_Software.desktop
rpi_packages
yolov5-master
yolov5-master.zip

/opt/create_ap/:
LICENSE
Makefile
README.md
bash_completion
create_ap
create_ap.conf
create_ap.openrc
create_ap.service
howto

/opt/pigpio/:
cgi

/opt/ros/:
melodic
--- 桌面应用 ---
NoMachine-base-unity.desktop
NoMachine-base-xfce.desktop
NoMachine-base.desktop
NoMachine-nxr.desktop
NoMachine-nxs.desktop
NoMachine-nxv.desktop
NoMachine-nxw.desktop
NoMachine-status-unity.desktop
NoMachine-status-xfce.desktop
NoMachine-status.desktop
PyCrust.desktop
Thunar-bulk-rename.desktop
Thunar-folder-handler.desktop
Thunar.desktop
XRCed.desktop
```

## 磁盘与运行时长（评估稳定性）

> 为什么问：磁盘余量不足会导致录屏/抓图失败

```
/dev/mmcblk0p2   29G   14G   15G  47% /
 13:11:27 up 33 min,  1 user,  load average: 0.69, 0.58, 0.57
```


---

## 采集结果的判读

拿到这份输出后，按下面三条分支决定桥接层要不要改：

**分支 1 —— 有串口 + 有 SDK + 无 ROS 舵机话题**
最理想。现有 `HiwonderBusServoArmDriver` 不用改，直接跑
`tools/teach_hiwonder_sequence.py` 示教即可。

**分支 2 —— 舵机走 ROS service/topic（当前 8080 的迹象指向这个）**
**需要改桥接层**。`HiwonderBusServoArmDriver` 假设的是串口直连，
对 ROS 话题是瞎的。要么新增一个 `RosArmDriver` 实现同一份 ArmDriver
协议（仍满足"可替换层"的口径），要么在 ROS 侧写一个节点把话题转成串口。
★ 这正是"可替换层"的价值现场：换一个执行端，平台一行代码不动。

**分支 3 —— 两者都有但不确定**
先跑示教工具录一段短序列验证真机能动；动不了再按分支 2 走。

无论哪个分支，**首次真机跑一律用 3–5 个姿态的短序列**，
别一上来就长序列 —— 跑偏时物理损害与工作量都是成倍的。
