# 第4课 MoveIt 注意事项与控制 / 第5课 MoveIt 随机移动 —— 学习笔记

> 来源：`第4课 MoveIt注意事项与控制.pdf`（8 页，全覆盖）、`第5课 MoveIt随机移动.pdf`（6 页，全覆盖）。
> 关键事实：**这两课是纯 RViz GUI 操作课，全程没有 Python 脚本、没有 MoveGroupInterface 代码、没有控制器 YAML 配置**。
> 唯一的命令行是 `roslaunch armpi_fpv_moveit_config demo.launch`。
> 笔记中凡标「【补充】」的段落是我补的 MoveIt 通用知识（课件里没有），其余均为课件原文。

---

# 第4课 MoveIt 注意事项与控制

## 1. 注意事项

- 开始前，确保机械臂周围有足够的活动空间；执行玩法期间与机械臂保持一定距离，**避免对人体产生误伤**。
- 本节用 MoveIt 规划路径，并**同时控制仿真模型和真实机械臂**按路径移动到指定位置。

## 2. 启动 MoveIt 工具和控制机械臂

> 注意：输入指令时需**严格区分大小写**，可用 `Tab` 键补齐关键词。

1) 机械臂开机，按第3课《MoveIt 配置》下的「环境搭建及建立连接」，把机械臂与虚拟机建立连接。
2) 双击虚拟机桌面上的终端图标，打开命令行终端。
3) 新开一个终端，输入：

```bash
roslaunch armpi_fpv_moveit_config demo.launch
```

- 包名：`armpi_fpv_moveit_config`，launch 文件：`demo.launch`（一个 launch 同时起 RViz + MoveIt 调试面板 + 仿真模型）。
- 界面三区编号：**①RVIZ 工具栏　②MoveIt 调试区　③仿真模型调节区**。

## 3. 控制说明

1) 在 MoveIt 调试区点击 **Planning** 页签。

   MotionPlanning 面板结构（后续所有课共用）：

   | 区域 | 控件 | 说明 |
   |---|---|---|
   | Commands | `Plan` / `Execute` / `Plan & Execute` / `Stop` / `Time: x.xxx` / `Clear octomap` | 规划与执行、耗时、清除八叉树占据栅格 |
   | Query | **Planning Group** / Start State / **Goal State** | 选择关节组（规划组）、起点、目标 |
   | Path Constraints | `None` | 路径约束（笛卡尔路径下拉在此） |
   | Options | Planning Time (s) `5.0` | 规划器求解超时（秒） |
   | Options | Planning Attempts `10` | 采样/尝试次数上限 |
   | Options | Velocity Scaling `1.00` | 速度缩放（轨迹执行时间倍率） |
   | Options | Accel. Scaling `1.00` | 加速度缩放 |
   | 勾选项 | Use Cartesian Path | 勾上 = **笛卡尔空间**规划；不勾 = **关节空间**规划 |
   | 勾选项 | **Collision-aware IK**（默认已勾） | 碰撞感知逆解 |
   | 勾选项 | Approx IK Solutions | 允许近似 IK 解（更快，可能不精确） |
   | 勾选项 | External Comm. | 外部通信（Time 参数面板 / 轨迹外部控制） |
   | 勾选项 | Replanning | 允许执行中重规划 |
   | 勾选项 | Sensor Positioning | 传感器定位 |

   页签栏还有：`Context` / `Planning` / `Manipulation` / `Scene Objects` / `Stored Scenes` / `Stored States` / `Status` / `Joints`。

2) 在**仿真模型调节区（③）**拖动红绿蓝三色箭头调整末端姿态。以机械臂为第一视角：
   - **绿 = X 轴**，正方向为机械臂**左方**
   - **红 = Y 轴**，正方向为机械臂**前边**
   - **蓝 = Z 轴**，正方向为机械臂**上方**

3) 除整体箭头外，也可单独调关节：点击调试区**右边的三角标志**（面板右侧 `▶`），找到并点击 **Joints** 页签。
4) 在 **Joints** 面板（`Group joints of goal state`）拖动对应关节滑杆单独调角度。示例数值：
   - 初始：joint1 `-6°`、joint2 `10°`、joint3 `14°`、joint4 `30°`、joint5 `30°`
   - 调整后：joint1 `-14°`、joint3 `-75°`、joint4 `33°`、joint5 `30°`
   - 面板底部还有 `Nullspace exploration:`（零空间探索）
5) **状态颜色语义（重要）**：
   - **橙色 = 可执行**（已规划出无碰撞路径）
   - **红色 = 不可执行**（新位置与机械臂其他部分或场景物体碰撞），必须重新调整到无碰撞状态，否则**无法执行该动作**
6) 规划路径：回到 **Planning** 页签点 `Plan` → 仿真模型演示从原位置到新规划位置的移动路径（绿色带箭头轨迹）。
7) 点 `Execute` → 仿真模型和机械臂**都**执行规划好的运动。
   （截图里 Goal State 为 `home`，`Plan` 后 Time: 0.253，状态显示 `Executed`）
8) 点 `Plan & Execute` → 机械臂**先演示**新规划的移动路径，**再执行**动作（一次点击完成规划+执行）。
9) 关闭：终端按 `Ctrl+C`。**若关闭失败，请反复尝试。**

---

# 第5课 MoveIt 随机移动

## 1. 注意事项

- 同第4课：确保活动空间充足、保持距离避免误伤。
- 本节用 MoveIt 规划路径，控制仿真模型和真实机械臂移动到**随机位置**。

## 2. 启动相关服务

> 注意：指令严格区分大小写，可用 `Tab` 补齐。

```bash
roslaunch armpi_fpv_moveit_config demo.launch
```

- 步骤同第4课：开机 → 连虚拟机 → 开终端 → 执行 launch。
- 界面三区：①RVIZ 工具栏　②MoveIt 调试区　③仿真模型调节区。

## 3. 随机移动

1) MoveIt 调试区点 **Planning** 页签。
2) 仿真模型调节区三色箭头（以机器人为第一视角）：绿 = X（正方向左方）、红 = Y（正方向前方）、蓝 = Z（正方向上方）。
3) 在 **Query** 区点 **Planning Group** 下拉菜单，选择要控制的关节组（舵机组）。下拉里有两个：**`arm`** 和 **`gripper`**，本课以 `arm` 为例。
4) 点 **Goal State** 下拉菜单，选择目标位置。
5) **Goal State 下拉参数含义（7 项）**：

   | 参数 | 含义 |
   |---|---|
   | `<random valid>` | 有效的随机位置，**不会发生碰撞** |
   | `<random>` | 随机位置，**可能随机到发生碰撞**的情况 |
   | `<current>` | 当前位置 |
   | `<same as start>` | 与开始位置相同 |
   | `<previous>` | 上一个目标位置 |
   | `home` | 程序默认设置的位置（home 位姿） |
   | `p1` | 程序默认设置的位置（预设点 p1） |

   - 前 5 项带尖括号 `<>`，是 MoveIt 的**动态目标**（每次取用会重新采样/回溯到当前状态）；`home`、`p1` 是 SRDF 里定义的**具名状态**。
   - Start State 也用同一套语法（`<current>` 等），可做「从某处到某处」的随机移动。
6) 为避免随机到碰撞位置，选 **`<random valid>`**；**每次选择都会随机一个新目标位置**，并立刻在仿真模型上显示出来。
7) 点 **`Plan & Execute`** → 仿真模型演示新规划路径，机械臂同时执行动作。
   - **温馨提示：实际表现上软件可能会相对慢一些，这是正常现象！**（RViz 播放 + 真机串口通信延迟）
8) 关闭：终端 `Ctrl+C`，失败则反复尝试。

---

# 配套资产速查

| 项 | 值 |
|---|---|
| MoveIt 配置包 | `armpi_fpv_moveit_config` |
| 启动文件 | `demo.launch` |
| 启动命令 | `roslaunch armpi_fpv_moveit_config demo.launch` |
| 规划组 | `arm`、`gripper`（示例均用 `arm`） |
| 关节 | `joint1` ~ `joint5`（5 个，角度单位 °） |
| 具名目标 | `home`、`p1` |
| 动态目标 | `<random valid>`、`<random>`、`<current>`、`<same as start>`、`<previous>` |
| 场景物体 | 货架（shelf，绿色），第4课碰撞演示用 |
| Options 默认值 | Planning Time 5.0 s / Attempts 10 / Velocity Scaling 1.00 / Accel. Scaling 1.00 / Collision-aware IK 已勾 |
| 依赖前置 | 第3课《MoveIt 配置》→ 环境搭建及建立连接 |

# 坑与注意事项汇总

1. **大小写敏感**：`roslaunch`、`armpi_fpv_moveit_config`、`demo.launch`、`Plan & Execute` 必须严格照抄，用 `Tab` 补齐。
2. **`Ctrl+C` 关不掉是常态**：课件明确要求「若关闭失败，请反复尝试」——连按直到 RViz 与 move_group 进程退出，否则端口被占，下一次 `demo.launch` 起不来。
3. **红色目标态 = 规划会被拒绝**：末端与其他臂段/货架碰撞时 Execute 无效，必须先拖回橙色/无碰撞态。「看起来能动」≠「能执行」。
4. **规划组选错**：Planning Group 若停在 `gripper`，Goal State 的 `home`/`p1` 语义完全不同；先确认下拉里选中的是 `arm`。
5. **`<random>` 会随机到碰撞位**：演示随机运动必须用 `<random valid>`，否则规划直接失败（Execute 灰掉）。
6. **速度偏慢属正常**，不是故障（真机串口 + RViz 渲染叠加）。
7. **调姿态优先用关节滑杆**：三色箭头是笛卡尔拖动，容易误碰红色；用 `Joints` 面板精确到度。
8. `Clear octomap` 用于清理残留的八叉树占据数据；场景被「误判碰撞」时可先清一次再规划。

# 【补充】GUI 操作对应的 MoveIt 编程接口（课件未给，附复用参考）

> 以下非课件内容，是把第4/5课的 GUI 动作翻译成代码，方便你复用。

## 笛卡尔 vs 关节空间（第4课 `Use Cartesian Path` 勾选项）

```python
import sys
import rospy
from moveit_msgs.msg import RobotState
from moveit_msgs import moveit_commander

moveit_commander.roscpp_initialize(sys.argv)
rospy.init_node("lesson4_cartesian", anonymous=True)

robot = moveit_commander.RobotCommander()
scene = moveit_commander.PlanningSceneInterface()
group = moveit_commander.MoveGroupCommander("arm")     # 对应 GUI 的 Planning Group = arm

# 关节空间目标（GUI：拖 Joints 滑杆 / Goal State 选 home、p1）
group.set_pose_target(robot.get_current_pose())        # 或
joint_goal = [0.0, -0.26, 1.22, 0.57, 0.52]            # 弧度
group.set_joint_value_target(joint_goal)

# 笛卡尔空间目标（GUI：勾 Use Cartesian Path + 拖三色箭头）
# waypoints 为沿直线的路点，步长越小越贴近直线
start = group.get_current_pose().pose
target = start.copy(); target.position.z -= 0.10      # 沿 Z 下移 10cm
group.set_pose_target(target, eef_link="gripper_link")  # 需与 SRDF/EEF 名一致

# 时间参数 = GUI 的 Velocity/Accel Scaling
group.set_max_velocity_scaling_factor(1.0)
group.set_max_acceleration_scaling_factor(1.0)
# 规划超时 = GUI 的 Planning Time (s)
group.set_planning_time(5.0)

plan = group.plan()                 # == GUI 的 Plan（只规划不执行）
ret = group.execute()               # == GUI 的 Execute（真机执行）
```

## 随机目标（第5课 `<random valid>` / `<random>`）

```python
# <random valid>：MoveIt 内部自带拒绝采样，落在无碰撞位形空间
group.set_random_goal()                    # 等价于 GUI 选 <random valid>
# <random>：纯随机采样，可能自碰撞/与场景碰撞
import random
random.uniform(-3.05, 3.05) for _ in range(len(group.get_active_joints()))
group.set_joint_value_target(random_joints)

# <same as start> / <current> / <previous>
group.set_pose_target(group.get_current_pose())              # <same as start>
group.set_pose_target(start_state_pose)                      # <current>
# <previous>：自己缓存上一次的目标 Pose 再 set_pose_target

# 每次重新随机：重复调用 set_random_goal() + plan() + execute()
```

## execute / wait_for_visualization / wait_for_kinematic_state

```python
plan = group.plan()                 # 规划
group.execute()                    # 执行（真机+仿真同步走）
group.clear_pose_targets()         # 清目标；GUI 的 Clear octomap 是另一回事

# 想让 RViz 播放完整轨迹再动真机（= GUI 的 Plan 然后 Execute）：
group.execute(plan=plan)           # 用已规划轨迹执行
rospy.sleep(1.0)                   # 留时间给 RViz 播放

# MoveGroupAction 版（带 server，可设 allow_replan/num_planning_attempts）
action = moveit_commander.MoveGroupAction("arm", "gripper")
goal = moveit_commander.MoveGroupAction.Goal()
goal.request.group_name = "arm"
goal.request.allowed_start_states.append(RobotState())
goal.request.goal_constraints = [group.get_pose_constraint("home", 0.05)]
goal.planning_options.plan_only = True      # 只规划 == GUI 的 Plan
goal.planning_options.planning_time = 5.0
goal.planning_options.replan_attempts = 10  # == GUI 的 Planning Attempts
action.send_goal(goal)                      # == GUI 的 Execute / Plan & Execute
```

## 对应关系速查（GUI ↔ API）

| GUI | API |
|---|---|
| Planning Group `arm` | `MoveGroupCommander("arm")` |
| Joints 滑杆 | `set_joint_value_target([...])` |
| 三色箭头拖动 / Use Cartesian Path | `set_pose_target(pose, eef_link)` |
| Plan | `group.plan()` |
| Execute | `group.execute()` |
| Plan & Execute | `group.execute(plan=group.plan())` |
| Stop | `group.stop()`（或 MoveGroupAction 的 `action.cancel_goal()`） |
| Velocity / Accel Scaling | `set_max_velocity_scaling_factor()` / `set_max_acceleration_scaling_factor()` |
| Planning Time / Attempts | `set_planning_time()` / MoveGroupAction `replan_attempts` |
| Collision-aware IK | `group.set_planner_id("RRTConnect")` 或 SRDF 里 `disable_collisions`（IK 碰撞感知需 SRDF 允许该组合） |
| `<random valid>` | `group.set_random_goal()` |
| `<current>` / `<same as start>` | `get_current_pose()` |
| `home` / `p1` | `group.set_pose_target(group.get_named_target("home"))` |
| Path Constraints 下拉 | `MoveItConstraints(PositionConstraint/JointConstraint/OrientationConstraint)` |

## 常见报错与解法（补充）

| 现象 | 原因 | 解法 |
|---|---|---|
| `Unable to identify any set of joints that can be treated as a chain` / 规划失败但目标可动 | 逆解不在关节限位内 | 调小目标幅度；勾 `Approx IK Solutions`；放宽 SRDF 限位 |
| `ompl_planner` 报 `OMPL couldn't find a path` | 采样不足或空间狭窄 | 加大 Planning Time(5→10s)、Attempts(10→30)；`Clear octomap`；调换目标 |
| `start state is in collision` | 起始位姿已碰撞（八叉树残留） | `Clear octomap`；把机械臂拖回非碰撞位；重建场景 |
| 真机不动、只有 RViz 动 | `follow_joint_trajectory` 控制器未加载/未激活 | 检查 `rosrun armpi_fpv_moveit_config check_robot_map` 与 MoveIt 控制器配置，`joint_trajectory_controller` 需为 `FollowJointTrajectory` |
| `Unable to acquire client lock` / 反复起不来 | 上一次 `demo.launch` 未退干净 | 反复 `Ctrl+C`；必要时 `rosnode kill /move_group`、清残留进程 |
| 规划成功但真机抖动/超力 | 速度/加速度过大 | Velocity / Accel Scaling 降到 0.3~0.5 |
| MoveGroupInterface 需用 ASCII 名称 | 中文关节名 | URDF/SRDF 关节名保持 ASCII，URDF `name` 不要用中文 |
