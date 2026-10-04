# VPC 内模型中转 · 手把手执行单（R-NX-08 · A 方案）

> 为什么要做：华为 AgentArts 的**私网环境**（Skill 必需）没有公网出口，
> 沙箱直连 `api.deepseek.com` 必然 60 秒超时 → 智能体永远出不了回答。
> 解法：在 VPC 内的 ECS 上跑一个 OpenAI 兼容中转，把模型"搬进 VPC"。
>
> 根因取证：`artifacts/nexent-platform-acceptance/evidence/agentarts-hosted-qa-2026-10-02/root-cause-model-unreachable.md`
> 背景细节：`huawei-agentarts-vpc-target-runbook.md` 第 13.7 节

**全程约 10 分钟。你只需要动第 1~5 步；第 6 步之后全是我的活。**

---

## 0. 现在的状态（开工前对照）

| 对象 | 现状 |
| --- | --- |
| 区域 | **CN 西南-贵阳一（cn-southwest-2）** —— 控制台右上角先确认是这个 |
| ECS `seasight-mcp-host` | **Running**（`1.95.120.238` 公网 / `192.168.0.65` 私网，Ubuntu 22.04，FlexusX） |
| 安全组 `seasight-mcp-sg` | 入方向 4 条：同 SG All(IPv4/IPv6)、TCP:22←`183.251.1.x`、TCP:8100←`192.168.0.x`。**没有 8080** |
| AgentArts 智能体 | `seasight-governance-agent-vpc`（私网环境 + 5 Skill），运行时就绪 |
| 卡点 | 模型调用 60s 超时（私网无公网出口） |

---

## 第 1 步：安全组放行 8080（约 1 分钟）

**目标**：让 AgentArts 沙箱能访问 ECS 的 8080。

1. 浏览器打开（这个路由自动化/手动都稳）：
   ```
   https://console.huaweicloud.com/vpc/?region=cn-southwest-2#/vpc/secGroups/list
   ```
2. 列表中点击 **`seasight-mcp-sg`**（ID 以 `bdaadfa2-3a11-4f27-836b-c52100d54f97` 开头）→ 进入详情。
3. 切到 **`Inbound Rules`（入方向规则）** 页签 → 右上/下方点 **`Add Rule`（添加规则）**。
4. 表格里会出现一行空白表单，逐列填：

   | 列 | 填什么 | 备注 |
   | --- | --- | --- |
   | **Priority**（优先级） | `1` | ⚠️ 这一格显示的是灰字示例 `1-10`，**必须自己敲 1**，否则 OK 是灰的 |
   | Status | 默认 `Enabled` | 不用动 |
   | **Action** | `Allow` | 默认就是 |
   | **Type** | `IPv4` | 默认就是 |
   | **Protocol & Port** | 协议选 **`Protocols / TCP (Custom ports)`**，端口框填 **`8080`** | 端口框的示例文字是 `Example: 22 or 22,24 or 22-30` |
   | **Source** | 左侧下拉选 **`IP address`**，右侧框填 **`192.168.0.0/16`** | ⚠️ 源**不能空**，空着 OK 永远点不动 |
   | Description | `AgentArts VPC model relay`（可选） | |
   | Operation | 保持那行，不要删 | |

5. 点右下角 **`OK`**。
6. **成功判据**：规则列表变成 **5 条**，新那条显示 `Allow | IPv4 | TCP: 8080 | 192.168.0.0/16`。
   （页面上方 "Total Records" 会从 4 变成 5。）

> 出错怎么办
> - OK 一直是灰的 → 回头看 Priority 和 Source 是不是真的填进去了（这两格最容易漏）。
> - 弹出提示 `The rule already exists` → 说明已经加过了，直接下一步。
> - 提示权限不足 → 你的账号可能没有 VPC 写权限，告诉我，我换方案（用 8100 端口复用或走 MaaS）。

---

## 第 2 步：登录 ECS 的终端（约 2 分钟）

**目标**：拿到一个能粘命令的 Linux shell。

1. 打开：
   ```
   https://console.huaweicloud.com/ecm/?region=cn-southwest-2#/ecs/manager/vmList
   ```
2. 列表里只有一台：**`seasight-mcp-host`**（FlexusX）。把鼠标悬停到该行，点 **`Remote Login`（远程登录）**；
   或点实例名进详情页，右上角也有 **远程登录**。  
   → 会弹出一个浏览器内的 noVNC 终端窗口（可能是新标签页）。
3. 输入系统账号密码登录：
   - 用户名通常是 **`root`** 或 **`ubuntu`**（谁在建机时设置的用谁）
   - 如果密码不记得了 → 关掉窗口，回到列表，点该行 **更多 / More → 重置密码（Reset Password）**，
     **需要先把 ECS 关机**（Stop），重置后再 Start，用新密码登录。
     *（重置密码不影响机器上的数据，但会改变原有登录方式，你自己确认可以再做。）*
4. **成功判据**：终端里出现类似
   ```
   Welcome to Ubuntu 22.04.x LTS
   root@seasight-mcp-host:~#
   ```

> 备选：修好 SSH 就不用 VNC 了
> 那条 `TCP:22` 的白名单源是 `183.251.1.x`，而你现在的宽带出口 IP 是 `183.251.183.232`
> （**IP 变了**，所以 SSH 现在也不通）。把那条规则的源改成 `183.251.183.232/32`，
> 之后在你电脑的终端里 `ssh ubuntu@1.95.120.238` 就能直连，粘命令比 VNC 舒服得多。
> VNC 也能用，只是长文本粘贴偶尔会掉字符 —— 粘贴后**回车前先看一眼命令是否完整**。

---

## 第 3 步：确认 DeepSeek Key（约 30 秒）

**目标**：知道中转要转发去哪、用什么身份。

在 ECS 终端里执行：

```bash
sudo mkdir -p /opt/seasight/model-relay && sudo chmod 700 /opt/seasight/model-relay

# 看看这台机器上现有的 Oceanus 环境里有没有现成的 Key
sudo grep -rhoE 'DEEPSEEK[A-Z_]*KEY=sk-[A-Za-z0-9]+' /opt/seasight /root /home 2>/dev/null | head -3
```

- **打印出 `DEEPSEEK_API_KEY=sk-…`** → 记下 `sk-…` 那串，第 4 步直接用，不用另找。
- **什么都没打印** → 用你自己的 DeepSeek Key（在 platform.deepseek.com 的 API Keys 页），`sk-` 开头。

---

## 第 4 步：写入中转脚本（约 1 分钟）

**目标**：把 `relay.py` 落到 ECS 上（纯标准库，**不需要 pip / 不需要联网装包**）。

整段复制 → 粘到终端 → 回车（它会提示 `PYEOF` 结束，粘贴完就能回车）：

```bash
sudo tee /opt/seasight/model-relay/relay.py >/dev/null <<'PYEOF'
#!/usr/bin/env python3
# AgentArts VPC 内模型中转（OpenAI 兼容），仅用标准库
import json, os, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UP  = os.environ.get("UPSTREAM_BASE", "https://api.deepseek.com/v1").rstrip("/")
KEY = os.environ.get("UPSTREAM_KEY", "")
TOK = os.environ.get("RELAY_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _j(self, c, o):
        b = json.dumps(o).encode()
        self.send_response(c); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            return self._j(200, {"object": "list", "data": [{"id": "deepseek-chat", "object": "model"}]})
        self._j(200, {"status": "ok", "upstream": UP})
    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._j(404, {"error": {"message": "only /v1/chat/completions"}})
        if TOK and self.headers.get("Authorization", "").strip() != "Bearer " + TOK:
            return self._j(401, {"error": {"message": "bad relay token"}})
        n = int(self.headers.get("Content-Length") or 0)
        pl = json.loads(self.rfile.read(n) or b"{}")
        req = urllib.request.Request(UP + "/chat/completions", data=json.dumps(pl).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY,
                     "Accept": "text/event-stream" if pl.get("stream") else "application/json"}, method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            return self._j(e.code, {"error": {"message": e.read().decode("utf-8", "ignore")[:1500]}})
        except Exception as e:
            return self._j(504, {"error": {"message": "upstream unreachable: %s" % e}})
        if pl.get("stream"):
            self.send_response(r.status); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close"); self.end_headers()
            for line in r:
                self.wfile.write(line); self.wfile.flush()
            return
        b = r.read(); self.send_response(r.status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

print("[relay] port=%s upstream=%s" % (PORT, UP), file=sys.stderr)
ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
PYEOF

python3 -c "import ast,sys; ast.parse(open('/opt/seasight/model-relay/relay.py').read()); print('语法 OK')"
```

- **成功判据**：最后一行打印 `语法 OK`。
- 报 `SyntaxError` → 说明粘贴掉字符了，重新粘贴第 4 步整段。

再写配置文件（**把两个 `<...>` 换成实际值**；`RELAY_TOKEN` 自己起一个强口令）：

```bash
sudo tee /opt/seasight/model-relay/relay.env >/dev/null <<'ENVEOF'
UPSTREAM_BASE=https://api.deepseek.com/v1
UPSTREAM_KEY=<第3步拿到的 sk-…>
RELAY_TOKEN=<自定强口令，例：sk-seasight-relay-8f3ac1d94b7e>
ENVEOF
sudo chmod 600 /opt/seasight/model-relay/relay.env
sudo grep -c . /opt/seasight/model-relay/relay.env
```

- **成功判据**：打印 `3`（三行都写进去了）。

---

## 第 5 步：起成系统服务（约 1 分钟）

**目标**：中转常驻，开机自启、崩了自动重启。

```bash
sudo tee /etc/systemd/system/agentarts-model-relay.service >/dev/null <<'UNITEOF'
[Unit]
Description=AgentArts VPC model relay
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=/opt/seasight/model-relay/relay.env
ExecStart=/usr/bin/python3 /opt/seasight/model-relay/relay.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNITEOF

sudo systemctl daemon-reload
sudo systemctl enable --now agentarts-model-relay
sudo systemctl status agentarts-model-relay --no-pager | head -8
```

- **成功判据**：状态里出现 **`Active: active (running)`**，并且有一行 `[relay] port=8080 upstream=…`。

**然后做两条自测（必须都过）：**

```bash
# ① 服务活着
curl -s http://127.0.0.1:8080/v1/models; echo

# ② 能真的调到 DeepSeek（关键！）
source /opt/seasight/model-relay/relay.env
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $RELAY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"只回复 pong"}],"max_tokens":8}'; echo
```

- ① 期望：`{"object": "list", "data": [{"id": "deepseek-chat", ...}]}`
- ② 期望：一段 JSON，`choices` 里有 `"content":"pong"` 之类

> ② 报错的三种情况
> | 现象 | 原因 | 怎么办 |
> | --- | --- | --- |
> | `upstream unreachable` / 一直卡住后超时 | **ECS 自己也出不了公网** | 告诉我，换 B 方案（MaaS 内网端点） |
> | `401` / `Authentication Fails` | DeepSeek Key 错或欠费 | 换一个有效 Key，改 `relay.env` 后 `sudo systemctl restart agentarts-model-relay` |
> | `bad relay token` | 你请求头里的 token 和 `relay.env` 不一致 | 检查 `$RELAY_TOKEN` 是否 source 成功 |

---

## 第 6 步：把下面两样发我，剩下全归我

1. `RELAY_TOKEN` 的值（或者你直接说"填好了，值我私存" —— 那我改控制台时你把它填进密钥框就行）
2. 第 5 步 ①② 两条命令的**完整输出**

---

## 附：我随后会做（你不用管，但你可以核对）

1. 控制台「托管与运行 > 模型」→ 编辑 `deepseek-provider` → **Base_url 改成 `http://192.168.0.65:8080/v1`**
   （出站身份保持：位置 `标头` / 参数名 `Authorization` / 前缀 `Bearer` / 密钥值 = `RELAY_TOKEN`）；
2. 若运行时环境变量没跟着刷新（runtime 的 `model_config` 是**发布版本时固化**的），
   我会把智能体**发一个新版本**让它重新生成运行时；
3. 用官方 WebSocket 协议复跑问答，采集：
   - 问题原文
   - **MCP 工具调用轨迹**（`knowledge_search` / `knowledge_list_assets` / `knowledge_decision_evidence` 等）
   - 最终答案（含资产版本级引用；证据不足时必须写 `not_evaluated`）
   - 平台侧运行时日志（`模型调用完成 status=success`）
4. 把 `hosted-skill-qa-2026-10-02.yaml` 的 `platform_qa_completed` / `live_skill_qa_completed`
   置为 `true`，回填 README、提交清单、评分复审，复跑 `check_claims.py`；
5. 收尾：把 defaultgw 公网访问关掉、确认 ECS/日志是否停掉省余额。

---

## 附：安全与费用约定

- `RELAY_TOKEN`、DeepSeek Key **只留在** ECS 的 `/opt/seasight/model-relay/relay.env`（600 权限）
  和你本机 `D:\VeriCall_data\secrets\`。**不进仓库、不写文档、不贴聊天**。
- 中转只监听 ECS 的 8080，安全组只放行 VPC 网段 `192.168.0.0/16`，**不对公网开放**。
- ECS 按小时计费（≈¥0.5–1/h），余额 ¥9.47：**跑完就告诉我，我把它停掉**；
  如果今天不做了，也先停掉再关页面。
