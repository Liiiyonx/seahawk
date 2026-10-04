# MoveIt 课程笔记 · 第1课 URDF模型简介与入门 + 第2课 ROS机械臂URDF模型说明

> 来源：`C:\Users\Liii\Desktop\Movelt文档\第1课URDF模型简介与入门.pdf`（10 页，全覆盖）
> `C:\Users\Liii\Desktop\Movelt文档\第2课 ROS机械臂URDF模型说明.pdf`（5 页，全覆盖）
> 提取方式：PyMuPDF 逐页文本 + 内嵌截图 OCR/人工转录（课件正文代码块全部为图片，已逐张转录）。
> 课件环境：ROS **Melodic** + Ubuntu 18.04(bionic) + NoMachine 远程桌面 + Vim。

---

## 第1课 URDF 模型简介与入门

### 1. URDF 模型简介

- URDF = **U**nified **R**obot **D**escription **F**ormat，基于 **XML** 规范的机器人结构描述格式。
- 目标：提供一种**尽可能通用**的机器人描述规范。
- 核心概念：
  - **连杆（link）** = 有质量的**刚性物体**。
  - **关节（joint）** = 连接并**限制两个连杆之间相对运动**的机构。
- 多个连杆通过关节相互连接又相互限制 → 构成机器人运动模型。
- URDF 文档描述的内容：这一系列**关节与连杆的相对关系、惯性属性、几何特点、碰撞模型**。

### 2. xacro 模型与 URDF 模型比较

| | URDF | xacro |
|---|---|---|
| 定位 | 简单的机器人模型描述文件 | URDF 的**拓展形式**，本质上两者一样 |
| 优点 | 结构明了、容易理解 | 可用更高级的方式简洁化描述文件，提升代码**复用性** |
| 缺点 | 描述复杂结构时文件**冗长**，无法简洁描述 | —— |
| 典型场景 | 单一简单结构 | 人形机器人双腿：URDF 需把单腿完整描述两遍；xacro 只需描述单腿一次然后**复用** |

### 3. 安装 URDF 依赖（仅了解）

> **注意（原文）**：机器人与虚拟机内**已安装好** URDF 模型与 Xacro 模型，用户**无需重复安装**，本节仅作了解。

1) 更新安装包信息

```bash
sudo apt update
```

2) 安装 URDF 依赖（出现下图即安装成功，实际安装包列表包含 `ros-melodic-urdf`、`ros-melodic-roslaunch`、`ros-melodic-rosparam`、`ros-melodic-rosmaster`、`libpcl-dev` 等）

```bash
sudo apt-get install ros-melodic-urdf
```

3) 安装 xacro（安装成功标志：出现 `Setting up ros-melodic-xacro (1.13.17-1bionic.20220214.135922) ...`）

```bash
sudo apt-get install ros-melodic-xacro
```

### 4. URDF 模型基本语法

#### 4.1 XML 基础语法

**元素**（名字可自定义，必须成对闭合）：

```xml
<元素>
</元素>
```

**属性**（被包含在元素内部，定义元素的性质和参数）：

```xml
<元素 属性_1 = "属性值1" 属性_2 = "属性值2">
</元素>
```

**注释**（不影响其他属性和元素）：

```xml
<!-- 注释内容 -->
```

#### 4.2 连杆

连杆在 URDF 中以 **`<link>`** 标签表示，描述机器人某个刚体部分的**外观和物理属性**。

三个主要子标签：

| 标签 | 作用 |
|---|---|
| `<visual>` | 描述 link 部分的外观参数，如尺寸、颜色、形状等 |
| `<inertial>` | 描述 link 的惯性参数，主要用于机器人**动力学**运算部分 |
| `<collision>` | 描述 link 的碰撞属性 |

**link 标签结构骨架**（课件 p3 截图原样）：

```xml
<link name="<link_name>">
    <inertial>……</inertial>
    <visual>……</visual>
    <collision>……</collision>
</link>
```

各标签的子标签说明：

| 标签 | 作用 |
|---|---|
| `origin` | 对连杆位姿的描述。内部两个参数：`xyz` 描述连杆在仿真地图中的**位姿**，`rpy` 描述连杆在仿真地图中的**姿态** |
| `mess` | 描述连杆的**质量**（注：课件表格原文拼写为 `mess`，实际 URDF 标签为 **`mass`**） |
| `inertia` | 描述连杆的惯性。由于惯性矩阵的**对称性**，需填入六个参数 `ixx, ixy, ixz, iyy, iyz, izz` 作为属性。**这些参数需要通过计算得到** |
| `geometry` | 描述连杆的形状。用 **`mesh`** 参数加载纹理文件，用 **`filename`** 参数加载纹理的路径地址。另有三个子标签：**`box`（矩形）、`cylinder`（圆柱）、`sphere`（球）** |
| `material` | 描述连杆的**材质**，参数 **`name` 为必填项**。通过子标签 `color` 可调节颜色和透明度 |

#### 4.3 关节

关节在 URDF 中以 **`<joint>`** 标签表示，描述机器人关节的**运动学和动力学属性，以及运动的位置和速度限制**。

**六种关节类型**（按运动形式分类，完整覆盖 URDF 规范）：

| 类型和说明 | 标签 |
|---|---|
| 旋转关节：可以围绕单轴**无限旋转** | `continuous` |
| 旋转关节：类似于 continuous，但是**有旋转的角度限制** | `revolute` |
| 滑动关节：沿某一轴线移动的关节，**带有位置极限** | `prismatic` |
| 平面关节：允许在平面正交方向上平移或者旋转 | `planar` |
| 浮动关节：允许进行平移、旋转运动 | `floating` |
| 固定关节：不允许运动的特殊关节 | `fixed` |

**joint 标签涉及的主要标签**：

- `<parent_link>`：父连杆
- `<child_link>`：子连杆
- `<calibration>`：用于校准关节角度
- `<dynamics>`：描述运动的一些物理属性
- `<limit>`：描述运动的一些极限值

**joint 标签结构骨架**（课件 p5 截图原样）：

```xml
<joint name="name_of_joint">
    <parent link="link1">
    <child link="link2">
    <calibration>……</calibration>
    <dynamics damping ....../>
    <limit effort ....../>
</joint>
```

> ⚠️ 注意：上面 `parent`/`child` 那两行课件截图里**结尾的 `>` 缺失**（截图本身如此），实际代码必须写成自闭合的 `<parent link="..."/>`。见下方 4.6 完整代码。

子标签说明：

| 标签 | 作用 |
|---|---|
| `origin` | 对**父连杆**位姿的描述。内部两个参数：`xyz` 描述连杆在仿真地图中的位姿，`rpy` 描述连杆在仿真地图中的姿态 |
| `axis` | 设置子连杆对父连杆的 **XYZ 三轴中任意一轴做转动** |
| `limit` | 限制子连杆。`lower`/`upper` 属性限制**旋转的弧度范围**；`effort` 属性限制**转动过程中的受力范围（正负 value，单位牛/N）**；`velocity` 属性限制转动时的速度（**单位为米/秒 m/s**，旋转关节时实际按弧度/秒理解） |
| `mimic` | 描述该关节**与其他关节的关系**（用于耦合关节，如双指夹爪两指同步开合） |
| `safety_controller` | 描述安全控制器参数，用于**保护机器人关节运动** |

#### 4.4 robot 标签

完整的机器人**最顶层的标签**，`<link>` 标签和 `<joint>` 标签**必须包含在 `<robot>` 内**（课件 p6 原样）：

```xml
<robot name="name_of_robot">
    <link>……</link>
    <link>……</link>

    <joint>……</joint>
    <joint>……</joint>
</robot>
```

#### 4.5 gazebo 标签

配合 **gazebo 仿真器**使用，可设置一些仿真参数：引入 gazebo 插件、gazebo 物理属性设置等。示例（课件 p6 截图原样）：

```xml
<gazebo reference="link1">
    <material>Gazebo/Black</material>
</gazebo>
```

> `reference` 指向要配置的 link 名称；`Gazebo/Black` 是 Gazebo 内置材质名。

#### 4.6 编写简单的 URDF 模型

**步骤一：设置机器人模型名称**

模型开头设置名字，模型最后输入 `</robot>` 表示编写完成：

```xml
<?xml version="1.0"?>
<robot name="pan_tilt">
```

**步骤二：设置连杆**

1. 编写第一个连杆，用**缩进**表示此连杆属于此模型内；结尾输入 `</link>` 表示连杆编写完成。
2. 编写连杆描述部分，用缩进表示此描述用于此连杆内；开头 `<visual>`，结束 `</visual>`。
3. `<geometry>` 描述连杆形状，结束 `</geometry>`，内部缩进表示对外形的具体描述：

```xml
<geometry>
    <cylinder length="0.01" radius="0.2" />
</geometry>
```

> `length="0.01"` 表示连杆**长度为 0.01 米**，`radius="0.2"` 表示**半径为 0.2 米**，整体是一个圆柱体。

4. `<origin>` 描述连杆位置：

```xml
<origin rpy="0 0 0" xyz="0 0 0" />
```

> `rpy` 为连杆角度，`xyz` 为连杆坐标位置。此处表示连杆在坐标系中的位置为**原点**。

5. `<material>` 描述连杆颜色（开头 `<material>`，结束 `</material>`）：

```xml
<material name="yellow">
    <color rgba="1 1 0 1" />
</material>
```

> `rgba="1 1 0 1"` 为设置颜色阈值（R=G=1、G=1、B=0、Alpha=1）→ **黄色**。

**步骤三：设置关节**

1. 编写关节，缩进表示属于此模型；设置名称和类型；结尾 `</joint>`：

```xml
<joint name="pan_joint" type="revolute">
```

> **注意**：关节类型可前往「4.3 关节」学习。

2. 编写关节连接连杆描述，设置 `parent` 和 `child`：

```xml
<parent link="base_link" />
<child link="pan_link" />
```

> **关键理解**：当关节转动的时候，会**以父连杆为支点，转动子连杆**。

3. `<origin>` 描述关节位置：

```xml
<origin xyz="0 0 0.1" />
```

> `xyz` 为关节的坐标位置，表示关节在坐标系的具体位置为 x=0、y=0、z=0.1。

4. `<axis>` 描述关节姿态（转轴）：

```xml
<axis xyz="0 0 1" />
```

5. `<limit>` 限制关节运动。示例含义：**最大力不超过 300 牛，转动弧度上限 3.14、下限 -3.14**：

```xml
<limit effort="300" velocity="0.1" lower="-3.14" upper="3.14" />
```

> 公式：`effort="关节的力度（牛）"`、`velocity="关节运动的速度"`、`lower="弧度下限"`、`upper="弧度上限"`。

6. `<dynamics>` 描述关节位动力学：

```xml
<dynamics damping="50" friction="1" />
```

> `damping="阻尼值"`、`friction="摩擦力"`。

**完整代码（课件 p10 全部代码，共 62 行，原样抄录）**：

```xml
<?xml version="1.0"?>
<robot name="pan_tilt">

    <!-- 定义base_link -->
    <!-- visual标签描述了连杆的具体环境的外观，包括几何体geometry（圆柱形cylinder）等 -->
    <link name="base_link">
        <visual>
            <geometry>
                <cylinder length="0.01" radius="0.2" />
            </geometry>
            <origin rpy="0 0 0" xyz="0 0 0" />
            <material name="yellow">
                <color rgba="1 1 0 1" />
            </material>
        </visual>
    </link>

    <!-- 定义了关节pan_joint，以及关节类型：旋转轴（有限制） -->
    <!-- 旋转轴连接的两个刚体分别是base_link和pan_link -->
    <joint name="pan_joint" type="revolute">
        <parent link="base_link" />
        <child link="pan_link" />
        <origin xyz="0 0 0.1" />
        <axis xyz="0 0 1" />
        <limit effort="300" velocity="0.1" lower="-3.14" upper="3.14" />
        <dynamics damping="50" friction="1" />
    </joint>

    <link name="pan_link">
        <visual>
            <geometry>
                <cylinder length="0.4" radius="0.04" />
            </geometry>
            <origin rpy="0 0 0" xyz="0 0 0.09" />
            <material name="red">
                <color rgba="0 0 1 1" />
            </material>
        </visual>
    </link>

    <joint name="tilt_joint" type="continuous">
        <parent link="pan_link" />
        <child link="tilt_link" />
        <origin xyz="0 0 0.2" />
        <axis xyz="0 0 1" />
        <limit effort="300" velocity="0.1" lower="-4.64" upper="-1.5" />
        <dynamics damping="50" friction="1" />
    </joint>

    <link name="tilt_link">
        <visual>
            <geometry>
                <cylinder length="0.4" radius="0.04" />
            </geometry>
            <origin rpy="0 1.5 0" xyz="0 0 0" />
            <material name="green">
                <color rgba="1 0 0 1" />
            </material>
        </visual>
    </link>

</robot>
```

**该示例的结构串讲（复习用）**：

- 3 个 link：`base_link`（底盘，黄色圆柱，长 0.01/半径 0.2）、`pan_link`（红色圆柱，长 0.4/半径 0.04）、`tilt_link`（绿色圆柱，长 0.4/半径 0.04）。
- 2 个 joint：
  - `pan_joint` = `revolute`（**有限制**），`parent=base_link`、`child=pan_link`，`origin xyz=0 0 0.1`，`axis=0 0 1`，`limit lower=-3.14 upper=3.14`。
  - `tilt_joint` = `continuous`（**旋转轴**），`parent=pan_link`、`child=tilt_link`，`origin xyz=0 0 0.2`，`axis=0 0 1`，`limit lower=-4.64 upper=-1.5`。
- 串联关系：`base_link --pan_joint--> pan_link --tilt_joint--> tilt_link`。

---

## 第2课 ROS 机械臂 URDF 模型说明

> **开篇注意事项（原文）**：在输入指令时需要**严格区分大小写**，且可使用 **Tab 键**补齐关键词。

### 1. 准备工作

- 为了能够读懂 URDF 模型，URDF 模型相关语法可查看 **「第9章机械臂运动规划及MoveIt仿真课程\第2课ROS机械臂URDF模型说明」**（即本课件是MoveIt 课程序列里的第 1、2 课，属于配套前置材料）。
- 本节对**机械臂模型代码和部件模型**进行简要解析。

### 2. 查看机械臂模型代码

操作步骤：

1) 启动机械臂，将其连接至远程控制软件 **NoMachine**。
2) 双击系统桌面的图标，打开命令行终端。
3) 进入启动程序目录：

```bash
roscd armpi_fpv/urdf/
```

> 实际终端提示符显示当前路径为 `~/armpi_fpv/src/armpi_fpv/urdf`，即源码空间下的 `armpi_fpv/urdf`。

4) 打开仿真模型文件：

```bash
vim armpi_fpv.urdf
```

**文件路径 / 配套信息汇总**：

| 项 | 值 |
|---|---|
| 演示包名 | **`armpi_fpv`** |
| URDF 目录 | `armpi_fpv/urdf/`（绝对展开：`~/armpi_fpv/src/armpi_fpv/urdf/`） |
| URDF 文件 | **`armpi_fpv.urdf`** |
| 网格资源目录 | `package://armpi_fpv/meshes/`（`.STL` 文件，大小写敏感） |
| 机器人名 | `armpi_fpv` |
| 编辑器 | `vim`（可用 Tab 补齐） |
| 远程桌面 | NoMachine |

代码中调用了**多个 urdf 模型**（mesh 资源）来组成完整的机械臂，各标签含义：

| 标签 | 说明 |
|---|---|
| `material` | 颜色 |
| `inertial` | 惯性、转动惯量，**使 Gazebo 物理引擎正常工作** |
| `base_link` | 机械臂主体模型 |
| `robot` | 总体名称，**凡是 URDF 文件**（顶层必须有） |
| `joint` | 可活动的机械部件，例如轴 |

### 3. 机械臂主体模型简要解析

#### 3.1 机械臂各关节参数

- 机械臂在全代码中定义了 **6 个连杆（Link1~Link5 大致相同 + 1 个）**，**每个连杆代表一个关节**。由于 Link~Link5 定义**大致相同，仅模型与初始位置不同**，故以 Link 为例说明。
- 每个 link 的固定三段式写法：
  1. **惯性 `<inertial>`**：定义产生惯性的初始位置（关键字 `origin`）、定义质量（关键字 **`mass`**）、定义惯性属性（关键字 `inertia`）。
  2. **`<visual>` 描述外观**：位置为原点（关键字 `origin`）、引入相关模型（关键字 `geometry`）、定义颜色（关键字 `material`）。
  3. **碰撞属性 `<collision>`**：产生碰撞的初始位置（关键字 `origin`）以及碰撞位置的模型（关键字 `geometry`）、定义颜色（关键字 `material`，此处为**灰色**）。

**`base_link` 完整代码（课件 p2/p3 截图，行号 1–43 原样）**：

```xml
<?xml version="1.0" encoding="utf-8"?>
<robot
    name="armpi_fpv">
    <link
        name="base_link">
        <inertial>
            <origin
                xyz="-4.934E-05 -0.068274 0.014557"
                rpy="0 0 0" />
            <mass
                value="0.15937" />
            <inertia
                ixx="0.00050053"
                ixy="-5.0613E-10"
                ixz="7.3399E-11"
                iyy="0.00019115"
                iyz="1.8631E-06"
                izz="0.0006778" />
        </inertial>
        <visual>
            <origin
                xyz="0 0 0"
                rpy="0 0 0" />
            <geometry>
                <mesh
                    filename="package://armpi_fpv/meshes/base_link.STL" />
            </geometry>
            <material
                name="">
                <color
                    rgba="0.79216 0.81961 0.93333 1" />
            </material>
        </visual>
        <collision>
            <origin
                xyz="0 0 0"
                rpy="0 0 0" />
            <geometry>
                <mesh
                    filename="package://armpi_fpv/meshes/base_link.STL" />
            </geometry>
        </collision>
    </link>
```

**base_link 参数表**：

| 项 | 值 |
|---|---|
| inertial origin | `xyz="-4.934E-05 -0.068274 0.014557"` `rpy="0 0 0"` |
| mass | `0.15937`（kg） |
| inertia | `ixx=0.00050053`、`ixy=-5.0613E-10`、`ixz=7.3399E-11`、`iyy=0.00019115`、`iyz=1.8631E-06`、`izz=0.0006778` |
| visual origin | `xyz="0 0 0"` `rpy="0 0 0"` |
| geometry | `mesh filename="package://armpi_fpv/meshes/base_link.STL"` |
| material | `name=""`（空名）+ `color rgba="0.79216 0.81961 0.93333 1"`（浅蓝白色） |
| collision origin | `xyz="0 0 0"` `rpy="0 0 0"`，geometry 同为 `base_link.STL`（**与 visual 用同一个 mesh**） |

#### 3.2 摄像头模型参数

摄像头模型被定义在连杆 **`camera_link`**（截图行号 276–315）。写法与 `base_link` 完全同构：`<inertial>`（origin/mass/inertia）→ `<visual>`（origin/geometry/material，颜色为**灰色**）→ `<collision>`（origin/geometry）。

```xml
    <link
        name="camera_link">
        <inertial>
            <origin
                xyz="0.00033180290572122 0.00895390425891458 -0.00555358926723143"
                rpy="0 0 0" />
            <mass
                value="0.013338478094918" />
            <inertia
                ixx="1.98496727909256E-06"
                ixy="-1.22022751315402E-08"
                ixz="4.4141438189008E-08"
                iyy="2.36163896904187E-06"
                iyz="1.54197231994083E-07"
                izz="3.25714605613889E-06" />
        </inertial>
        <visual>
            <origin
                xyz="0 0 0"
                rpy="0 0 0" />
            <geometry>
                <mesh
                    filename="package://armpi_fpv/meshes/camera_link.STL" />
            </geometry>
            <material
                name="">
                <color
                    rgba="0.792156862745098 0.819607843137255 0.933333333333333 1" />
            </material>
        </visual>
        <collision>
            <origin
                xyz="0 0 0"
                rpy="0 0 0" />
            <geometry>
                <mesh
                    filename="package://armpi_fpv/meshes/camera_link.STL" />
            </geometry>
        </collision>
    </link>
```

**camera_link 参数**：

| 项 | 值 |
|---|---|
| inertial origin | `xyz="0.00033180290572122 0.00895390425891458 -0.00555358926723143"`（精度到小数点后 14 位，CAD 导出） |
| mass | `0.013338478094918` |
| inertia | `ixx=1.98496727909256E-06`、`ixy=-1.22022751315402E-08`、`ixz=4.4141438189008E-08`、`iyy=2.36163896904187E-06`、`iyz=1.54197231994083E-07`、`izz=3.25714605613889E-06` |
| geometry | `package://armpi_fpv/meshes/camera_link.STL` |
| material color | `rgba="0.792156862745098 0.819607843137255 0.933333333333333 1"`（灰色） |

> 从截图行号可推断：`camera_link` 出现在文件约 276 行，`gripper_base` 在约 396 行，文件总长 **400+ 行**，`base_link` 是第一个 link。

#### 3.3 夹持器（爪子）参数

夹持器模型被定义在连杆 **`gripper_base`**（截图行号 396–434），三段式写法同上，颜色为**灰色**。

```xml
    <link
        name="gripper_base">
        <inertial>
            <origin
                xyz="0.00312 0.01432 0.03101"
                rpy="0 0 0" />
            <mass
                value="0.0176105871345009" />
            <inertia
                ixx="1.5708815504179E-06"
                ixy="2.51402116906045E-08"
                ixz="-2.26426177315553E-08"
                iyy="4.1275256554833E-06"
                iyz="-5.90507564364135E-10"
                izz="3.26180194932723E-06" />
        </inertial>
        <visual>
            <origin
                xyz="0 0 0"
                rpy="0 0 0" />
            <geometry>
                <mesh
                    filename="package://armpi_fpv/meshes/gripper_base.STL" />
            </geometry>
            <material
                name="">
                <color
                    rgba="0.792156862745098 0.819607843137255 0.933333333333333 1" />
            </material>
        </visual>
        <collision>
            <origin
                xyz="0 0 0"
                rpy="0 0 0" />
            <geometry>
                <mesh
                    filename="package://armpi_fpv/meshes/gripper_base.STL" />
            </geometry>
        </collision>
    </link>
```

**gripper_base 参数**：

| 项 | 值 |
|---|---|
| inertial origin | `xyz="0.00312 0.01432 0.03101"` |
| mass | `0.0176105871345009` |
| inertia | `ixx=1.5708815504179E-06`、`ixy=2.51402116906045E-08`、`ixz=-2.26426177315553E-08`、`iyy=4.1275256554833E-06`、`iyz=-5.90507564364135E-10`、`izz=3.26180194932723E-06` |
| geometry | `package://armpi_fpv/meshes/gripper_base.STL` |

---

## 跨课程汇总：坑、注意事项、报错与解法

### A. 课件明确写出的注意事项

1. **无需安装依赖**：虚拟机内 URDF 与 Xacro 已装好，重复 `apt-get install` 无必要（第1课 §3）。
2. **命令严格区分大小写**，用 **Tab** 补齐（第2课开篇）。ROS 里写错大小写典型症状：`Package 'xxx' not found` / `Invalid <param> / command not found`。
3. **关节类型写错是最常见错误**：第1课 §4.6 特意提示「关节类型可以前往 4.2/4.3 关节进行学习」（课件原文写"4.2关节"，但关节实际在 **4.3** 节，课件笔误）。
4. **关节转动方向**：以**父连杆为支点**转动子连杆。`parent`/`child` 写反 → 模型反向或直接报错。
5. **`material` 的 `name` 属性为必填项**（第1课 §4.2 表格原文强调）。第2课实际模型里写成 `name=""` 空值也能加载，但自建模型建议给有意义的名字（配合 `reference` 复用材质）。
6. **`inertia` 六个参数需要通过计算得到**，不能瞎填；惯量矩阵必须**对称**（ixy=iyx、ixz=izx、iyz=izy）。
7. **惯性参数缺失或全零 → Gazebo 物理引擎不工作**，机械臂会瘫软/乱飘（第2课表格：`inertial` = 惯性、转动惯量，使 Gazebo 物理引擎正常工作）。
8. **复杂模型禁用纯 URDF 手写**：会冗长；改用 xacro 复用（宏 + `${...}` 参数 + `xacro:include`）。
9. **joint 骨架截图里 `parent`/`child` 缺尾部 `>`**：属课件截图排版问题，实际必须自闭合，否则 XML 解析失败。

### B. 实际复用时容易踩的坑（基于课件语义的正确写法）

1. **文件名/包名大小写**：`armpi_fpv`、`armpi_fpv.urdf`、`meshes/base_link.STL` 全部大小写敏感；Linux 下 `armpi_FPV` 会直接找不到。URDF 里 mesh 路径推荐用 `package://包名/相对路径`，可随工作空间迁移。
2. **`origin` 的语义在 link 和 joint 里不同**：link 的 `origin` 是**自身几何体相对自身坐标系**的偏移；joint 的 `origin` 是**子连杆关节坐标系相对父连杆坐标系**的位姿（平移 xyz + 姿态 rpy）。
3. **rpy 是固定轴角（roll-pitch-yaw）**，顺序为「绕 X 轴 roll → 绕 Y 轴 pitch → 绕 Z 轴 yaw」，单位 rad；不是欧拉角的其他顺序，混用会导致姿态错乱。
4. **axis 必须是单位向量**：`0 0 1` = 绕 Z 轴。`0 0 0` 或非单位向量是无效轴。
5. **`continuous` 关节不认 lower/upper**：第1课示例里 `tilt_joint` 虽为 `continuous` 却仍写了 `limit lower/upper`，实际 continuous 无角度限位，`lower/upper` 会被忽略；给 continuous 写 `limit` 只会让 `effort`/`velocity` 生效。
6. **`limit` 对 `continuous`/`fixed` 非必需，对 `revolute`/`prismatic` 必需**：缺 `limit` 的 revolute 在 ROS 解析/控制时会报 `Joint 'xxx' has no limits`，MoveIt 里会判为 invalid。
7. **单位不要混**：`origin xyz` 与 `geometry` 尺寸单位是 **米**；`effort` 是 **N**；`velocity` 课件写 **m/s**（对旋转关节实际语义为 rad/s）；`mass` kg；`inertia` kg·m²。
8. **惯量数量级**：手写 URDF 时惯量填 0 或填错数量级（例如把 kg·m² 写成 1e6）→ Gazebo 里模型抖动/爆炸；`ixx/iyy/izz` 应满足三角不等式。
9. **Mimic 用法**：`<mimic joint="另一个关节名" multiplier="系数" offset="偏置"/>`，公式 `q = multiplier * q_ref + offset`。夹爪两指常用 `multiplier="1" offset="0"` 或 `-1`。若 `mimic` 引用了不存在的关节名，加载会报 `Joint 'x' mimic joint 'y' not found`。
10. **一个连杆只能有一个父关节**：URDF 是树形结构，同一 link 被两个 joint 作为 child → 解析/运动学异常。
11. **`gazebo` 标签必须放在 `<robot>` 内**（与 link 同级），且 `reference` 名字要与 `<link name=...>` 完全一致。
12. **`<collision>` 建议用简单几何体（box/cylinder/sphere）而不是 mesh**：mesh 碰撞检测开销大，是 URDF 加载慢和 Gazebo 卡顿的常见原因；第2课示例里 collision 直接复用了 STL（能跑但偏重）。
13. **visual 与 collision 分离的意义**：visual 走高精模型好看，collision 走低模保性能，二者 `origin` 可以不同（碰撞体常做简化/膨胀）。
14. **vim 里粘贴大段代码注意自动缩进**：URDF 靠缩进表达层级，粘贴时缩进错乱虽不影响 XML 解析（XML 不依赖缩进），但极难阅读；建议写完用 `:set paste` 再粘贴。

### C. 关键概念速查表

| 概念 | 一句话 |
|---|---|
| link | 有质量的刚体，含 visual（外观）/ inertial（惯性）/ collision（碰撞） |
| joint | 限制两连杆相对运动，含 parent_link/child_link、origin、axis、limit、dynamics、mimic、safety_controller、calibration |
| 运动学树 | 每个 joint 连接 parent→child，形成树；root link 无父关节 |
| origin | 位姿变换：xyz 平移(m) + rpy 姿态(rad) |
| axis | 转动轴单位向量（xyz 三轴取一） |
| limit | effort(N) / velocity(m/s 或 rad/s) / lower / upper(rad 或 m) |
| dynamics | damping 阻尼 / friction 摩擦力 |
| mimic | 关节耦合，q = multiplier × q_ref + offset |
| calibration | 关节角度校准参考值 |
| safety_controller | 关节运动安全保护参数 |
| inertial | mass 质量 + inertia(ixx,ixy,ixz,iyy,iyz,izz) 六参数对称惯量张量 |
| geometry | box / cylinder / sphere / mesh(filename) |
| material | name(必填) + color rgba="R G B A"（0~1） |
| robot | 顶层标签，name 为机器人名，所有 link/joint 的父容器 |
| gazebo | 仿真器专用扩展标签，reference 指向 link |

### D. 常用命令速查（本课件出现的）

```bash
# 更新 & 安装（虚拟机已装，备用）
sudo apt update
sudo apt-get install ros-melodic-urdf
sudo apt-get install ros-melodic-xacro

# 查看 armpi_fpv 的 URDF
roscd armpi_fpv/urdf/
vim armpi_fpv.urdf
```

> 备注：本课件为纯 URDF 语法课，**未出现** xacro 宏写法、rviz 启动命令、`check_urdf` / `urdf_to_graphiz` 校验命令、以及 SLAM gmapping 启动命令。若需要这些，属于后续课次（第 4~10 课 / 配套第9章课程）内容。
