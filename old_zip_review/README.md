# 探海灵眸 Oceanus —— 提交包说明

> 本压缩包为 2026 年海峡大学生人工智能创意大赛作品提交包。
> **包内所有文件已完成匿名化处理，不含学校、专业班级、指导老师与队员姓名等信息。**

## 目录结构

```
01_作品介绍/
    01_研究报告.docx              问题提出 → 解决方案 → 应用价值
    02_系统设计文档.docx          架构 / 模块划分 / 接口定义 / 数据结构
    03_作品介绍PPT.pptx           现场路演用
02_设计文档/
    项目README.md                 项目总览与快速开始
    architecture.md               架构说明
    device-interface.md           设备接口定义
    software-design.md            软件设计
    mqtt-topics.md                MQTT 主题契约
    perception-data-protocol.md   感知数据协议
03_源代码/
    backend/    后端服务（FastAPI + 智能体内核 + 业务模块 + 测试）
    edge/       边缘侧（设备仿真、驱动桥接）
    ml/         感知与模型工程（检测器、评测、ONNX 导出）
    integrations/  外部平台集成
    frontend/src/  前端业务控制台
    scripts/    验证与打包脚本
04_演示材料/
    演示视频分镜脚本.md
    演示视频录制清单.md
    演示视频.mp4                 （由参赛队录制后放入）
05_加分项举证/
    agent_evals_latest_v2.json   智能体固定场景评测结果
    agent_real_state_acceptance_latest.json  软件集成验收结果
    opencv_latest.json           感知评测结果（当前为 not_evaluated）
    ontology_eval_latest.json    本体评测结果
    knowledge_qa_trace_latest.json  检索问答轨迹
06_提交说明/
    提交清单与自检表.md
```

## 复现步骤

```bash
# 1. 基础设施
docker compose -f docker-compose.prod.yml up -d postgres redis emqx minio

# 2. 后端服务
cd backend && pip install -r requirements.txt && python run_server.py

# 3. 自动化测试
python -m pytest -q

# 4. 智能体固定场景评测
python scripts/run_agent_evals.py
```

## 能力边界说明

本作品对自身能力采用 E0-E4 证据分级表述，不做越级宣称：

- 软件闭环与智能体内核：**E1**（自动化测试 + 固定场景评测）
- 真实 HTTP / 鉴权 / 数据库 / 审批 / 幂等集成：**E2**
- 检测精度：**未评测**（独立测试集未放行，评测输出 `not_evaluated`）
- 昇腾硬件推理：**方案级设计**，未在目标硬件实测
- 真实海域与商业验证：**未取得**

时序链路误报抑制率约 76% 的口径为「被时序环节过滤的检测数 ÷ 输入检测总数」，
**不是识别精度或召回率**。

---
生成信息：文本文件 316 个，二进制文件 15 个，
脱敏文件 27 个。
