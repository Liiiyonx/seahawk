# Oceanus × 昇腾 Atlas / ModelArts 接入说明

> 版本：1.0 ｜ 日期：2026-09-27
> 配套材料：`docs/competitions/huawei-tech-matrix.md`（纽带矩阵）
> 配套门禁：`python scripts/check_claims.py --root .`（必须退出码 0）
>
> **本文性质：方案级说明。以下内容为基于本仓库现有架构推导出的接入路径，
> 未在昇腾硬件或 ModelArts 在线服务上实测，不构成"已适配"结论。**
> 每一节开头的 `【方案级 · 未实测】` 标记即为此意，请勿在答辩中省略。

---

## 第一部分：昇腾 Atlas 接入

### 0. 为什么这条路径是"配置与运行时"问题，而不是"改代码"问题

本仓库的检测推理服务是独立进程，不把加速卡写死：

- 入口：`backend/app/services/ai/server.py`（FastAPI，暴露 `/infer/detect`、`/infer/health`、`/infer/reload`）。
- 后端探测：服务启动时调用 `onnxruntime.get_available_providers()`，
  按 `TensorrtExecutionProvider` → `CUDAExecutionProvider` → `CPUExecutionProvider`
  的顺序挑选可用项装配 `InferenceSession`，并把实际选中的 provider 写进 `/infer/health`。
- 失败姿态：模型文件不存在或加载抛错时，服务降级为 `stub` 模式并**继续启动**，
  平台侧仍可独立联调，不会因为算法侧没就绪而全线不可用。

因此"换成昇腾"在代码层的动作 = **换一个带 CANN 执行提供者的 onnxruntime 运行时**。
这是本文其它部分成立的前提。

### 1. 【方案级 · 未实测】ONNX 权重 → om 模型（ATC）

前置：先在本仓库产出 ONNX。本仓库已有导出脚本 `ml/scripts/export_onnx.py`，
其导出参数与 ATC 的要求是对齐的：

| 导出参数 | 本仓库取值 | 对昇腾的意义 |
| --- | --- | --- |
| `dynamic` | `False`（固定 batch=1） | ATC 需要静态输入形状，动态轴会增加转换与调试成本 |
| `opset` | `17` | 需与 CANN 版本支持的算子集对齐后再定 |
| `simplify` | `True` | 减少图算子种类，降低算子不支持的概率 |
| `half` | `False` | FP16 交给下游工具；避免 ONNX 侧提前半精度化带来算子兼容问题 |
| `imgsz` | `640` | 与 `AI_INPUT_SIZE` 环境变量一致 |

导出与自检：

```bash
# 导出 ONNX（固定 batch=1 / opset17 / simplify）
python ml/scripts/export_onnx.py --weights runs/seasight/stage2/weights/best.pt

# 只验证已导出的 ONNX 能否正常推理（检查输出形状、opset 兼容性）
python ml/scripts/export_onnx.py --verify model.onnx
```

ATC 转换示例（**方案级命令，未在本机执行**）：

```bash
# ★ 方案级示例：ONNX → om（--framework=5 表示输入为 ONNX）
atc --model=best.onnx \
    --framework=5 \
    --output=best_ascend \
    --input_format=NCHW \
    --input_shape="images:1,3,640,640" \
    --soc_version=<目标 Atlas 型号，须与实机一致> \
    --log=error
```

需要提前说明的两个风险点（诚实起见，不做"肯定能转"的表述）：

1. **检测头算子**。YOLO 系列的 DFL 结构在跨平台转换中是已知的敏感点。
   本仓库在 `ml/scripts/export_onnx.py` 里已经记录过同类问题：RK3588 平台必须使用
   瑞芯微维护的 ultralytics 分支，否则 DFL 张量布局与 `rknn-toolkit2` 期望不一致，
   会报错或产出错误结果。**昇腾 ATC 是否需要类似处理，本仓库没有验证过**，
   应作为转换过程的第一项风险登记。
2. **`soc_version` 必须与实机一致**，写错会产出无法加载的 om，且报错信息不直接指向根因。

### 2. 【方案级 · 未实测】运行时装载 CANN 执行提供者

昇腾侧需要的是**华为发布的、带 CANN EP 的 onnxruntime 构建**（`CANNExecutionProvider`）。
装载方式是"同代码、不同运行时"，不需要改动仓库里的业务代码：

```python
# 【方案级示例】把 CANN 并入后端偏好列表
import onnxruntime as ort

preferred = [
    p for p in (
        "CANNExecutionProvider",        # ← 昇腾新增项，置于首位
        "TensorrtExecutionProvider",
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    )
    if p in ort.get_available_providers()
]
session = ort.InferenceSession("best_ascend.om", providers=preferred or None)
```

与现状的差异说明：

- 仓库当前代码的偏好列表是**三项**（TensorRT / CUDA / CPU），没有 `CANNExecutionProvider`。
  接入时需要把 CANN 加进该列表——**这是一处一行级的改动**，但必须在有昇腾实机的环境里
  连同环境变量、`LD_LIBRARY_PATH` 与 om 模型一起验证，不能在 x86 上"先改后不管"。
- `/infer/health` 会返回实际生效的 provider，可作为"是否真的走上了 CANN"的现场判据
  （返回 CPU 就说明没走上，不要口头声称走上）。

### 3. 【方案级 · 未实测】Atlas 边缘盒部署拓扑

```text
  岸边摄像头（RTSP）
        │
        ▼
 ┌──────────────────────── Atlas 边缘盒 ────────────────────────┐
 │  边缘感知进程：edge/main.py                                   │
 │    取流 → 检测（CvDetector / WorldDetector）→ 时序校验         │
 │    → 上报节流 → MQTT 发布                                     │
 │                                                              │
 │  （可选）本地推理服务：AI 服务 + om 模型 + CANN EP             │
 └───────────────────────────────┬──────────────────────────────┘
                                 │ MQTT（与平台同一套主题）
                                 ▼
                    中心侧 Oceanus 平台（容器编排）
```

要点：

- **边缘侧不感知"用的是哪种检测后端"**。`edge/main.py` 的输出契约是
  `[{class, confidence, bbox}]`，下游时序校验、上报节流、MQTT 主题均不区分设备。
  这正是把昇腾接入做成"换运行时"而不是"换系统"的根据。
- **推荐分两步走**：先让边缘盒的 AI 服务以 `CPUExecutionProvider` 跑通端到端，
  再替换为 `CANNExecutionProvider` 并做同一组输入的前后对比。
  这样任何一步出问题都能定位到"是环境问题还是模型问题"。
- **协议适配**：若采用华为云 IoT / ROMA 等接入方式替代自建 EMQX，
  边缘到中心的这一段需要另做网关映射；本仓库当前使用的是自建 EMQX，
  这部分属于**未评估范围**，不在本文承诺之内。

---

## 第二部分：ModelArts 接入

### 1. 【方案级 · 未实测】配置示例

本仓库的规划器是 OpenAI Chat Completions 兼容客户端
（`backend/app/services/agents/model_adapter.py` 的 `OpenAICompatibleModelClient`），
因此"指向 ModelArts 在线服务"是一个纯配置动作。`backend/.env`（或部署环境的对应变量）：

```dotenv
# ---- Agent 模型适配器 ----
AGENT_MODEL_ADAPTER_ENABLED=true

# 指向 ModelArts 在线服务（OpenAI 兼容形态）的推理地址
AGENT_MODEL_BASE_URL=https://<modelarts-在线服务地址>/v1

# 该服务的鉴权密钥（不要提交到版本库；生产环境走密钥管理）
AGENT_MODEL_API_KEY=<在此填入>

# 服务上部署的模型名（ModelArts 侧的服务名 / model 字段）
AGENT_MODEL_NAME=<在此填入>

# 超时与步数护栏（按 ModelArts 实例的实际响应延迟调，不要照抄）
AGENT_MODEL_ADAPTER_TIMEOUT_MS=5000
AGENT_MODEL_ADAPTER_MAX_STEPS=10
AGENT_MODEL_MAX_OUTPUT_TOKENS=1024
```

> 变量名以仓库 `.env.example` 内已登记的键为准；上面各项与之一一对应。
> 未登记的新增键应先补进 `.env.example` 再使用。

### 2. 护栏：模型不可用时回落规则模式（**这一条是已实现、有测试的事实**）

与前面两节的"方案级"不同，这一节描述的是仓库里已经存在的确定性行为：

- 规划器返回值 `ModelPlanProposal` 中，`source` 取 `"model"` 或 `"rule_fallback"`；
- 触发回落的四类原因：模型不可用 / 超时 / 输出不合 schema / 输出越权；
- 回落时附带结构化 `fallback_reason`，可观测、可审计，不是静默降级；
- 该行为由 `backend/tests/test_agent_model_adapter.py` 覆盖。

**现场演示价值**：把 `AGENT_MODEL_BASE_URL` 指向一个不可达地址，
系统仍然给出派单方案（走规则规划器），并明确标注回落原因。
这比口头解释"我们有降级"更有说服力，且**不需要连上 ModelArts**也能演示。

### 3. 最小验证路径（将来真正接入时按此执行）

1. 在 ModelArts 上部署一个可用的在线服务，取得推理地址与服务密钥。
2. 按 §1 填写 `AGENT_MODEL_*` 变量，保持 `AGENT_MODEL_ADAPTER_ENABLED=true`。
3. 先跑 `backend/tests/test_agent_model_adapter.py`，确认客户端侧无回归。
4. 跑一次独立冒烟，确认端点真实接受 Chat Completions 请求：

   ```bash
   make modelarts-smoke
   ```

   成功时输出 `artifacts/modelarts-real-call/latest.json`，其中 `source="model"`、
   含日期、模型名与延迟；未配置或调用失败时写 `not_configured` / 失败状态并
   非零退出，不会伪造成功记录。
5. 触发一次真实规划请求，检查返回的 `source` 是否为 `"model"`（而不是 `rule_fallback`）。
   若为回落，读 `fallback_reason` 判断是地址、密钥、模型名还是输出格式问题。
6. 把第 4 步的 `latest.json` 与第 5 步的规划结果作为真实证据登记到证据台账，
   在此之前，本文所有 ModelArts 相关表述都应保持"配置级兼容 / 待验证"口径。

---

## 附：本文与"三维度"的对应关系

| 材料要回答的问题 | 对应章节 | 口径 |
| --- | --- | --- |
| 昇腾跑过吗？ | 第一部分 §0–§3 | 未实测；架构就绪，接入路径与风险点已列明 |
| 换成华为云行不行？ | 第二部分 §1–§3 | 协议兼容、配置可切；回落行为已实现且有测试 |
| 华为什么技术真用了？ | `huawei-tech-matrix.md` §二第 1 行 | Nexent 实线（已集成，已通过协议级验收） |
