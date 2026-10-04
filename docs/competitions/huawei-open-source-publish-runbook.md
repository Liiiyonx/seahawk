# 华为 ICT 赛道三：开源发布操作手册

> 适用仓库：探海灵眸 SeaSight
> 目标平台：GitCode / GitHub（新建公开仓库）
> 最近更新：2026-09-30
> 关联工具：`scripts/build_public_release.py`、`scripts/check_public_repo_privacy.py`

---

## 0. 一句话原则

**公开仓库必须是“重新初始化的脱敏快照”，不得直接推送本私有仓库的历史。**

私有仓库历史中包含验收证据索引、本机绝对路径、比赛材料与个人联系信息；
即使后续 commit 删除，历史里仍然可被检出。这里采用“新目录 + `git init` +
首个干净 commit”的方式发布，从根上避免历史泄漏。

---

## 1. 发布前门禁（每次发布都必须重跑）

在私有仓库根目录执行：

```powershell
python scripts/build_public_release.py
```

成功时输出应当包含：

- `[build-public-release] 快照已生成`
- `本机路径/生产地址命中：0 个文件`
- `敏感验收证据路径：0 个文件`
- `[build-public-release] 全部检查通过，可进入 git init / push 步骤`

说明：

- 私有仓库上直接运行 `python scripts/check_public_repo_privacy.py` 仍会 `exit 1`，
  因为验收证据目录本来就保留在私有库中；**判定以快照扫描为准**。
- 构建脚本还会额外扫描身份证号、Nexent 验收账号、私钥块与疑似 API Key。
- 快照默认输出到 `dist/public-release/seasight/`。
- 演示账号（`admin123456` / `operator123456` / `approver123456` /
  `viewer123456`）属于种子数据，扫描器只给提示；发布前需人工确认它们
  不是任何真实环境凭据。

---

## 2. 快照内容与排除项

### 2.1 进入快照

- 核心代码：`backend/`、`frontend/`、`edge/`、`ml/`、`integrations/`、
  `deploy/`、`scripts/`、`docs/`（技术部分）
- 根目录：`README.md`、`LICENSE`、`Makefile`、`docker-compose*.yml`、
  `.env*.example`、`.gitignore`、`pytest.ini`
- 前端演示资产：`frontend/public/demo/`（4 张 WebP + 配套 JSON）

### 2.2 明确排除

- `artifacts/`：验收截图、JSON 报告、日志与线程存档
- `项目文档/`：比赛材料、商业证据台账、联系人信息
- `outputs/`：赛事材料初稿
- `docs/competitions/`：赛道策略、评审自评、提交清单
- `docs/evidence-inbox/`：内部证据入库通道
- `scripts/generate_lianjiang_drafts.py`：含联系人电话、邮箱与身份证号
- 华为赛道三打包/Word 构建脚本、`evidence_registry.py`、`check_claims.py`
- 根目录调试截图与 `mcp_test_script.py`

### 2.3 自动脱敏改写

| 文件 | 处理 |
| --- | --- |
| `README.md` | 移除指向私有比赛文档与 `artifacts/` 的断链，改指公开技术文档 |
| `docs/agent-program-wave3.md` | 固定工作目录改为“仓库根目录” |
| `scripts/knowledge_qa_trace_capture.mjs` | 移除本机 Playwright/Chrome 绝对路径，改为环境变量与包名解析 |
| `Makefile` | 移除对未发布证据脚本的调用；修掉本机 venv 绝对路径 |

---

## 3. 创建公开仓库并推送

以下命令在 **快照目录** 执行，不要回到私有仓库目录执行。

```powershell
cd dist/public-release/seasight
git init
git checkout -b main
git add .
git -c user.name="<你的提交者名称>" -c user.email="<你的提交邮箱>" commit -m "Initial public release: SeaSight"
```

先在 GitCode 或 GitHub 上创建一个**空仓库**：

- 不要勾选自动生成 README / .gitignore / LICENSE
- 仓库可见性设为 Public
- 记下仓库地址，例如：
  - `https://github.com/<account>/seasight.git`
  - `https://gitcode.com/<account>/seasight.git`

然后添加远程并推送：

```powershell
git remote add origin <空仓库地址>
git push -u origin main
```

> 禁止使用 `git push --mirror`；禁止把私有仓库的 `origin` 直接挂到公开仓库；
> 禁止在私有仓库上添加公开仓库 remote 后直接 push。

---

## 4. 推送后验收

### 4.1 本地复核

```powershell
# 逐文件校验 manifest（PowerShell 示例）
$dest = Get-Location
Get-Content MANIFEST.sha256 | ForEach-Object {
    $hash, $rel = $_ -split '  ', 2
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $rel).Hash.ToLower()
    if ($actual -ne $hash) { throw "哈希不一致：$rel" }
}
"manifest OK"

# 再次运行隐私扫描
python scripts/check_public_repo_privacy.py
```

### 4.2 页面复核

- 仓库首页能看到 README、LICENSE 与顶层目录。
- 文件树中不存在 `artifacts/`、`项目文档/`、`outputs/`、
  `docs/competitions/`。
- 搜索以下字符串应为 0 命中：
  - `C:\Users\`
  - `8.153.151.13`
  - `suadmin@nexent.com`
  - `seasight.acceptance@nexent.com`
- `frontend/public/demo/` 下 4 张 WebP 与 5 个 JSON 均在。

### 4.3 克隆复核

```powershell
cd $env:TEMP
git clone <公开仓库地址> seasight-public-check
cd seasight-public-check
python scripts/check_public_repo_privacy.py
```

如果本机到 GitHub 的连接不稳定，`git clone` 会长时间挂起（实测 2 分钟仅拉取
24 KB）。此时不要反复重试，改用下面两条只读接口复核，结论等价：

```powershell
# 1. 远端 HEAD
git ls-remote https://github.com/Liiiyonx/seasight.git

# 2. 远端文件树与本地快照逐项比对 blob 哈希
curl.exe -sS -H "Accept: application/vnd.github+json" -o $env:TEMP\tree.json `
  "https://api.github.com/repos/Liiiyonx/seasight/git/trees/main?recursive=1"
$tree = (Get-Content $env:TEMP\tree.json -Raw | ConvertFrom-Json).tree
$remote = $tree | Where-Object type -eq 'blob' |`
  ForEach-Object { "$($_.sha)  $($_.path)" } | Sort-Object
$local = git -C <本地快照目录> ls-tree -r HEAD | ForEach-Object {
  $p = $_ -split "`t", 2; "$(($p[0] -split '\s+')[2])  $($p[1])" } | Sort-Object
Compare-Object $local $remote   # 无输出即为一致
```

`raw.githubusercontent.com` 在本机网络下可能被重置，单文件下载失败不影响结论：
Git Trees API 返回的 blob SHA 与本地 `git hash-object` 同源，逐项一致即证明
远端文件内容未被改动。

---

## 5. 后续更新流程

公开仓库与私有仓库**不是双向同步关系**。任何更新都按以下流程：

1. 在私有仓库完成开发、测试与提交。
2. 重跑 `python scripts/build_public_release.py`。
3. 进入新快照目录，`git init`，生成新的首个 commit 或延续公开仓库的
   独立历史。
4. 推送前再次执行第 3 节与第 4 节检查。
5. 将公开仓库地址、发布时间、`MANIFEST.sha256` 的 SHA256 记录回私有仓库。

如果公开仓库需要保留连续历史，可在快照目录把公开仓库 clone 下来，
将快照文件覆盖到 clone 工作区后提交；**仍然不得引入私有仓库历史**。

---

## 6. 常见问题

### Q1：为什么不能直接在私有仓库执行 `git filter-repo` 后推公开？

可以做，但风险高于重建快照：过滤器规则一旦遗漏，敏感对象仍可能残留；
重建快照的允许清单更小、更可复核，也更容易向评委解释发布边界。

### Q2：公开快照里为什么没有验收报告？

验收报告包含账号、截图与机器环境信息，属于私有证据，不作为开源代码发布。
README 中的验收结论保留诚实口径；完整证据留在私有仓库供赛事审查。

### Q3：演示账号密码要不要删？

这些是登录页展示的种子数据，不对应真实环境。发布前需确认目标部署环境
已改掉默认密码；扫描器会保留“演示种子数据提示”，不自动放行。

### Q4：推送失败或发现漏项怎么办？

立即停止推送流程，修复私有仓库源文件或排除清单，重新构建快照后再推送。
若已推送，先删除公开仓库中的敏感文件并重写公开仓库历史；不要只提交一次
“删除”commit 掩盖，因为旧 commit 仍可访问。

---

## 7. 发布记录

### 7.1 首次公开（已执行）

```text
平台：GitHub
仓库地址：https://github.com/Liiiyonx/seasight
可见性：Public（MIT）
默认分支：main
发布时间：2026-09-30 20:34（北京时间）
发布人：李涌翔
快照生成时间：2026-09-30，dist/public-release/seasight
快照文件数：345 个 Git 文件（MANIFEST.sha256 收录 344 个，自身不计入）
初始提交：bba0fd91bc39d2fe6719022f739b3139e4ee0c81（父提交 0 个）
MANIFEST.sha256 的 SHA256：d62dc3bb3edaad1dda89c6fbc2bd78663d9dcbc93087112fbc6b6d3ba4fccd44
隐私扫描结果：exit 0
额外敏感内容扫描：通过（本机路径 0、生产地址 0、敏感验收证据 0）
备注：GitHub 仓库 size 字段暂时显示 0 KB，属统计延迟，以 blob 哈希复核对齐为准。
```

本次远程复核过程与结论：

- `git ls-remote` 返回 `bba0fd9...`，与本地快照 HEAD 一致。
- GitHub Git Trees API 返回 345 个 blob（`truncated=false`），与本地
  `git ls-tree -r HEAD` 逐项比对 blob SHA，0 处差异。
- 本地 `MANIFEST.sha256` 逐项校验 344 个文件，0 处不一致。
- 公开仓库不包含 `artifacts/`、`项目文档/`、`outputs/`、`docs/competitions/`。
- 首次公开是全新初始提交（父提交 0 个），未携带私有仓库历史。

隐私扫描保留的 2 项提示（均为演示种子数据，非生产凭据，部署前需处理）：

- `backend/db/init/02_seed.sql`：演示账号哈希。
- `deploy/emqx/bootstrap.csv`：EMQX 引导数据。

### 7.2 记录模板（后续每次发布复制填写）

```text
平台：
仓库地址：
发布时间：
发布人：
快照生成时间：
快照文件数：
MANIFEST.sha256 的 SHA256：
隐私扫描结果：exit 0
额外敏感内容扫描：通过
备注：
```
