# 跳转现状诊断（2026-10-05 01:05）

## 一句话回答：**还不能跳转。缺的是本机客户端，一件东西。**

## 两端状态

### 树莓派侧（服务端）—— 全部就绪 ✓

| 检查 | 结果 |
|---|---|
| `nxserver` 守护进程 | ✓ `2425 /usr/NX/bin/nxserver.bin --daemon` |
| `nxd` 监听 | ✓ `pid 4428`，监听 `0.0.0.0:4000` 与 `[::]:4000` |
| X11 桌面会话 | ✓ `ubuntu :0`（2022-02-12 起在线） |
| 主机名 | `ubuntu` |
| 版本 | 7.1.3-2 |
| 认证配置 | `/etc/NX/nxserver` 无自定义用户 → 走系统账户认证 |

**服务端没有任何问题。** 之前测到的 8080 是 ROS 静态页，与跳转无关。

### 本机侧（客户端）—— 缺失 ✗

| 检查 | 结果 |
|---|---|
| `C:\Program Files\NoMachine` | **不存在** |
| `~/AppData/Roaming/Nomachine` | **不存在** |
| `nx://` 协议注册 | 无（`reg.exe` 被沙箱策略拦，但无安装目录已可判定） |
| 安装包 | 本机与仓库内均**未找到** |

## 结论

`nx://` 协议唤起的前提是**本机注册了 `nx://` 协议处理器**，
而这个处理器由 NoMachine 客户端安装时注册。没装客户端 →
点按钮**没有任何反应**（不会报错、不会跳转）。

所以现状是：树莓派准备好了，本机没准备好。**只差装一个软件。**

## 补齐步骤

### 1. 装客户端（必须做，我做不了——需要你交互安装）

下载 NoMachine for Windows：

- 官网 `https://www.nomachine.com/download/download-clients`
- 资料包内应有 `nomachine_8.4.2_10_x64.exe`（★ 树莓派装的是 7.1.3，
  客户端 8.x 向后兼容连 7.x 服务端；若连接异常，改用 7.1.3 同版本客户端）

安装时保持默认即可（协议注册是安装程序自动做的）。
★ 注意：树莓派跑 aarch64，NoMachine 的**服务端**才是树莓派上那个
7.1.3；你装的是 Windows 客户端，架构不相关。

### 2. 验证协议已注册

装完后在浏览器里手动试一次（不经过我们的页面）：

```
nx://192.168.149.1
```

粘到地址栏回车 —— 能唤起 NoMachine 登录框就说明协议注册成功。

### 3. 配置平台环境变量

```bash
# frontend/.env.local
VITE_ARM_CONSOLE_URL=nx://192.168.149.1
VITE_ARM_CONSOLE_LABEL=ArmPiFPV 仿真台
VITE_ARM_DRIVER_BACKEND=simulated
```

### 4. **必须重新构建**（这一步最容易漏）

```bash
cd frontend && npm run build
```

`VITE_*` 是**构建期注入**的，不 build 不生效。
生产环境要重新构建镜像并重启容器。

### 5. 登录凭据

```
协议 / 主机：192.168.149.1（或主机名 ubuntu）
端口：4000（NoMachine 默认）
用户名：ubuntu
密码：hiwonder
```

## 装好之后的验收

```bash
cd frontend
npm run build
# 启动预览
node ./node_modules/vite/bin/vite.js preview --port 5199
# 打开仿真台页 → 应显示「nx 协议」绿标 + 跳转目标 nx://192.168.149.1
```

页面上点「打开仿真台」应唤起 NoMachine 客户端并弹出登录框。

## 现场兜底（务必提前准备）

NoMachine 客户端崩了/协议没注册，页面点了没反应时：
**直接用客户端手动连**（不走网页）。把这个信息抄在纸上备用：

```
NoMachine → New connection
  Host: 192.168.149.1
  Port: 4000
  Protocol: NX
  用户名: ubuntu
  密码:   hiwonder
```

平台的「复制连接信息」按钮已经把前三行带上了（主机地址会随
`VITE_ARM_CONSOLE_URL` 一起填对），但**端口 4000 与协议类型
需要人工补** —— 建议在演示机上把这张连接配置预先建好，
NoMachine 会保存，网页唤起时直接命中。

## 另一个待解决的问题（与跳转无关但同样卡演示）

树莓派现在是**纯 AP 模式，无默认网关、不能出网**。所以：

- 电脑连了它→ **访问不了 ECS 上的平台**
- 演示时必须在树莓派上改 STA 模式接进演示网

详见 `arm-hardware-onboarding-runbook.md` 第 2 步。
**这一步比装客户端更关键** —— 不改 STA，装好客户端也只能看树莓派
桌面，平台大屏会打不开。
