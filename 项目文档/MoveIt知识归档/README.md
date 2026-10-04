# MoveIt 知识归档（凡点 armpi_fpv 课件 1-10 课）

> 用途：机械臂运动学 / MoveIt 仿真的**背景知识与避坑清单**。真机接入路径见
> 《机械臂与底盘资料适用性清单》与《探海灵眸_机械臂对接准备》。
> 归档日期：2026-10-04 ｜ 来源：`C:\Users\Liii\Desktop\Movelt文档\`（9 份 PDF，逐页精读）
> 分课笔记：本目录 01~04 四份 ｜ 索引：本文件

---

## 0. 先读这一段：三个前提

**1. 第3课《MoveIt 配置》不在源目录里。** 现有 PDF 是第 1、2、4、5、6、7、8、9、10 课。
第3课是第4~10课的硬前置，内容包括：

| 缺失内容 | 归属 | 为什么重要 |
| --- | --- | --- |
| `kinematics.yaml`（KDL / IKFast 求解器） | 第3课 | 决定 IK 能否收敛、笛卡尔路径能否走通 |
| SRDF（规划组 `arm` / `gripper`、具名姿态 `home`/`p1`、禁碰组合） | 第3课 | 决定 RViz 下拉框里有什么 |
| `collision_matrix.yaml`（ACM 允许碰撞矩阵） | 第3课 / 第8课 | 决定自碰撞检测行为 |
| 环境搭建及真机连接流程 | 第3课 | 第4~10课每一课的硬前置 |

真机到货后若要重新配置，**从树莓派 `/home/ubuntu/armpi_fpv/` 复制出厂配置**，
不要从零重建。

**2. 课件性质与文件名给人的印象不符。** 第 4/5/7/8/9/10 课全是 **RViz GUI 鼠标
操作课**，不是代码课。全套课程只有一条命令：

```bash
roslaunch armpi_fpv_moveit_config demo.launch
```

零 Python 脚本、零 YAML 配置代码。真正有代码/公式的只有第 1、2 课（URDF）和
第6课（DH 运动学）。**不要按"MoveIt 编程课"的预期去找脚本**。

**3. 课件本身有笔误，照抄会踩坑。**

| 位置 | 课件写法 | 正确写法 |
| --- | --- | --- |
| 第6课 DH 参数表 | 连杆长度与连杆扭转符号**都写成 `α_(i-1)`** | 连杆长度 `a_(i-1)`、连杆扭转 `α_(i-1)`、偏移 `d_i`、转角 `θ_i` |
| 第6课 `θ_i` 定义 | "绕 `Z_(i-1)` 旋转" | 标准 DH 为绕 **`Z_i`** |
| 第1课 `<inertial>` 表格 | `mess` | 实际标签是 **`mass`** |
| 第1课 `tilt_joint` | 声明 `continuous` 却写了 `lower/upper` | `continuous` 无角度限位，`lower/upper` 被忽略 |
| 第1课 joint 骨架截图 | `<parent link="link1">` 缺尾部 `>` | 必须自闭合 `<parent link="link1"/>` |

---

## 1. 分课笔记索引

| 文件 | 覆盖课次 | 内容要点 |
| --- | --- | --- |
| [01-URDF与机械臂模型.md](01-URDF与机械臂模型.md) | 第1、2课 | URDF 语法全套、`pan_tilt` 完整 62 行代码、`armpi_fpv.urdf` 三段式逐段解析（`base_link`/`camera_link`/`gripper_base` 全部惯性参数） |
| [02-MoveIt面板与随机移动.md](02-MoveIt面板与随机移动.md) | 第4、5课 | RViz 三区布局、Planning 面板全部控件、颜色语义、Goal State 七种取值、GUI↔MoveGroupInterface 对照表 |
| [03-运动学与笛卡尔路径.md](03-运动学与笛卡尔路径.md) | 第6、7课 | DH 四参数几何意义、坐标系确定四步法、几何法逆解 `a/b/c` 二次方程、笛卡尔路径原理与失败排查 |
| [04-碰撞检测场景与轨迹规划.md](04-碰撞检测场景与轨迹规划.md) | 第8、9、10课 | ACM 允许碰撞矩阵、场景对象三类型、五种规划器、Scene Objects 面板、规划管线、时间参数化、26 条报错解法 |

---

## 2. 核心资产速查

| 项 | 值 |
| --- | --- |
| 机械臂包 | `armpi_fpv` |
| URDF | `armpi_fpv/urdf/armpi_fpv.urdf`（400+ 行，6 连杆） |
| mesh 资源 | `package://armpi_fpv/meshes/*.STL`（**大小写敏感**） |
| MoveIt 配置包 | `armpi_fpv_moveit_config` |
| 启动文件 | `demo.launch` |
| 规划组 | `arm`（5 关节 `joint1`~`joint5`）、`gripper` |
| 具名目标 | `home`、`p1` |
| 动态目标 | `<random valid>`、`<random>`、`<current>`、`<same as start>`、`<previous>` |
| Options 默认值 | Planning Time 5.0s ／ Attempts 10 ／ Velocity 1.00 ／ Accel 1.00 |
| RViz 三色轴 | 绿=X(左) 红=Y(前) 蓝=Z(上) —— **是显示配色，不是 FLU 语义** |
| 状态颜色 | 橙色=可执行；红色=碰撞不可执行 |

### RViz 面板结构

```
① RVIZ 工具栏   Display 树 / Robot Description
② MoveIt 调试区  MotionPlanning 面板
   页签: Context | Planning | Manipulation | Scene Objects
        | Stored Scenes | Stored States | Status | Joints
   Commands: Plan / Execute / Plan & Execute / Stop / Clear octomap
   Query:    Planning Group / Start State / Goal State
   Options:  Use Cartesian Path / Collision-aware IK / Approx IK Solutions
             External Comm. / Replanning / Sensor Positioning
   Path Constraints: None
③ 仿真模型调节区  三色拖动箭头（末端位姿）
```

---

## 3. 十大坑（浓缩版）

1. **大小写敏感**：`roslaunch`、`armpi_fpv_moveit_config`、`demo.launch`、`.STL` 全部照抄，用 Tab 补齐。写错典型症状 `Package 'xxx' not found`。
2. **`Ctrl+C` 关不掉是常态**，课件明确"若关闭失败，请反复尝试"；不关干净会占端口，下次 `demo.launch` 起不来。
3. **红色目标态 = 规划被拒**，必须拖回橙色才能 Execute。
4. **`<random>` 会随机到碰撞位**，演示随机运动必须用 `<random valid>`。
5. **改 YAML 必须重启 launch**，RViz 不热加载。
6. **第9课拖完物体要点 `Publish`**，否则场景不更新。
7. **第10课必须把天线向后弯折**（该课独有操作，避障）。
8. **第8课模型默认生成在视图底部**，第9课在场景中心 —— 位置不同是正常的，不是 bug。
9. **ACM 里的 `1` 表示"跳过检测"**（反直觉），不是"必须检测"。
10. **两套颜色语义别混**：三色箭头=轴向显示；橙/红=可执行性。

---

## 4. 概念要点

### URDF（第1、2课）

- **link** = 有质量的刚体，三段式：`<inertial>`（origin/mass/inertia）＋
  `<visual>`（origin/geometry/material）＋ `<collision>`（origin/geometry）。
- **joint** 六种类型：`revolute`(有限位)、`continuous`(无限位)、`prismatic`、
  `planar`、`floating`、`fixed`。子标签：`<parent_link>`/`<child_link>`、
  `<origin>`、`<axis>`、`<limit>`(effort/velocity/lower/upper)、`<dynamics>`、
  `<mimic>`、`<safety_controller>`、`<calibration>`。
- **`<origin>` 在 link 与 joint 中语义不同**：
  - link 里 = 几何体相对自身坐标系的偏移
  - joint 里 = 子连杆关节坐标系相对父连杆坐标系的位姿
- **`<axis>` 必须是单位向量**，`0 0 0` 无效。
- **`rpy`** 是固定轴角：绕 X roll → 绕 Y pitch → 绕 Z yaw，单位 rad。
- **惯量矩阵必须对称**：`ixy=iyx`、`ixz=izx`、`iyz=izy`，且 `ixx/iyy/izz` 满足三角不等式。
  惯量全零或数量级错（把 kg·m² 写成 1e6）→ Gazebo 里模型抖动或爆炸。
- **惯性参数缺失 → Gazebo 物理引擎不工作**，机械臂瘫软乱飘。
- **`<collision>` 建议用简单几何体而非 mesh**：mesh 碰撞开销大，是 URDF 加载慢
  和 Gazebo 卡顿的常见原因。课件示例 collision 直接复用了 STL（能跑但偏重）。
- **mimic 公式**：`q = multiplier × q_ref + offset`。夹爪两指常用
  `multiplier="1" offset="0"` 或 `-1`。
- **单位**：`origin xyz` 与 geometry 尺寸 = 米；`effort` = N；`velocity` 课件写
  m/s（旋转关节实际语义为 rad/s）；`mass` = kg；`inertia` = kg·m²。
- **URDF 是树形结构**：一个连杆只能有一个父关节。

### 运动学（第6课）

- **DH 四参数**（记物理含义比记字母可靠，课件符号有笔误）：
  - link length：两关节轴之间的**公共法线长度**
  - link twist：一个关节轴相对另一个**绕公共法线**旋转的角度
  - link offset：相邻两条公共法线**沿关节轴**的距离
  - joint angle：两条公共法线**绕关节轴**的转角
- **DH 体系两条铁律**：`axis` → z 轴；`common normal` → x 轴（从本关节指向下一关节）。
- **⚠️ URDF 不遵循 DH 约定**。URDF 里每个 joint 坐标系是独立指定
  `<origin xyz rpy>` 的，不强制"z=axis、x=common normal"。MoveIt / KDL 实际用
  URDF 语义，**第6课的 DH 法则不能照搬进 URDF** —— 只需保证 `<axis>` 与 joint
  原点 z 轴一致。
- **FK** 唯一解、计算廉价，是实时控制内环。
- **IK** 多解（肘上/下、腕翻转，最多约 4 组），可能无解，是规划器每步都调用、
  最易失败的环节。几何法解 `sin θ1 = (-b ± √(b²-4ac)) / 2a`，**± 号就是多解来源**。
  MoveIt 实际用数值法：KDL 或 IKFast（离线生成 C++ 插件，快一个数量级）。
- **三类坐标系颜色全课统一**：绿=X，红=Y，蓝=Z，锥体位置为原点。
  基座坐标系（原点=底部舵机）／关节坐标系（原点=粉色锥体）／工具坐标系（原点=锥体）。

### 笛卡尔路径（第7课）

- **关节空间插值**：各轴互不关心其他轴，末端在两点间是**任意曲线**。
- **笛卡尔路径**：事先给定目标点或路径 → 运动学计算得关节层轨迹。
  要求**末端轨迹形状是直线或圆弧**时必须用它。
- **实现原理**：`compute_cartesian_path` 在末端笛卡尔空间按 `max_step`（如 0.01m）
  离散 N 个位姿点，每步**重新解 IK** 拼成关节序列，再交给时间参数化生成时间轨迹。
- **⚠️ 任一中间点 IK 失败或超限位，整条路径失败** —— 这是 "Plan & Execute 失败"
  最常见的原因。
- **常见失败根因**：该 IK 求解器不支持笛卡尔路径（KDL 支持有限，改 IKFast 或
  TRAC_IK）→ 中途某点无解 → 两次求解的关节解不连续出现**跳变**（保留上次 IK 解
  作 seed / warm start 解决）→ 笛卡尔直线穿过障碍物。

### 碰撞与规划（第8、10课）

- **规划管线**：request → adapter → manager → planner（ompl/chomp/stomp/sbpl/pilz）
  → controller → 时间参数化。
- **时间参数化算法**：TOTG（时间最优、 jerk 有界）、ISP（迭代分段多项式）、
  IPTP、**Ruckig**（jerk 限幅，1.0 版本起进入 MoveIt 2 时间参数化）。
- **RViz 控件 ↔ API 对照**：`Use Cartesian Path` → `path_type = CartesianPath`；
  `Collision-aware IK` → `avoid_collisions = true`；`Approx IK Solutions` →
  `approximate_ik`；`Velocity/Accel Scaling` → `execute_path(time_scaling)`。

---

## 5. 与本项目（探海灵眸）的接口

**这份归档的定位是背景知识，不是接入路径。** 真机接入走总线舵机 SDK，路线见
《机械臂与底盘资料适用性清单》。对应关系：

| 本归档内容 | 与项目的关系 |
| --- | --- |
| 第2课 `armpi_fpv.urdf` 六连杆结构 | 解释真机 6 个舵机的连杆拓扑；`joint1`~`joint5` + 夹爪 |
| 第6课 DH / 逆运动学 | **仅理论参考**。真机 IK 源码（`armpi_fpv_kinematics`）未随资料提供，到货后从树莓派 `/home/ubuntu/armpi_fpv/` 复制。**不要凭 PDF 公式自行重写并声称可用** |
| 第7课笛卡尔路径 | 与项目当前"示教序列回放"路线**不同**。真机走 `pick_sequence` 位置序列，末端走直线需 IK 支撑，属到货后可选增强 |
| 第5课 `pick_sequence` 相关舵机编号 | 课件第8课「机械爪位置自适应」：2 号舵机平行、1 号舵机夹取、3/4/5 号定位 —— 与清单结论一致 |
| MoveIt 仿真本身 | 《适用性清单》结论仍成立：**仅背景了解**，出厂已配好，重新配置有覆盖风险，比赛演示价值低。虚拟机在真机上的作用是 NoMachine 看日志 / 复制源码 |

---

## 6. 读笔记的方法

课件正文里的代码与公式**全部是内嵌图片**，PDF 文本层抽不到。精读时已把
57 页中约 50 张图渲染后逐张转录，因此笔记里的代码和参数表是完整的。

若要重新精读：Read 工具直读 PDF 会报 `Cannot display content of binary file`，
须用 PyMuPDF 逐页抽文本；公式页与代码页必须渲染成 PNG（150dpi 足够）再读图。
