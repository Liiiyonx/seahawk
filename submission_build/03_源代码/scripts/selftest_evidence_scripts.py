#!/usr/bin/env python
"""华为 ICT 证据脚本自测：未配置时绝不伪造成功。

验证两个新增脚本的 not_configured 语义：
- `scripts/knowledge_evolution_demo.py`：未提供账号/token 时退出码 2，
  JSON 报告 status=not_configured，不写 verified。
- `scripts/modelarts_smoke.py`：未配置 base_url/model 时退出码 2，
  JSON 报告 status=not_configured，不写 source=model。

两条路径都跑真实子进程，输出写入系统临时目录，不落仓库。
所有断言失败都会以非 0 退出码结束并打印具体失败原因。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent

EXIT_NOT_CONFIGURED = 2


def _run(script: str, args: list[str], env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    # Explicitly neutralize config that may exist in the caller environment.
    for key in (
        "SEASIGHT_API_BASE_URL",
        "SEASIGHT_API_USERNAME",
        "SEASIGHT_API_PASSWORD",
        "AGENT_MODEL_BASE_URL",
        "AGENT_MODEL_API_KEY",
        "AGENT_MODEL_NAME",
    ):
        env[key] = ""
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(Path("scripts") / script), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _assert(cond: bool, msg: str, failures: list[str]) -> None:
    if not cond:
        failures.append(msg)


def _test_knowledge_evolution(tmp: Path, failures: list[str]) -> None:
    report = tmp / "evolution-latest.json"
    proc = _run(
        "knowledge_evolution_demo.py",
        ["--output", str(report)],
        {},
    )
    _assert(
        proc.returncode == EXIT_NOT_CONFIGURED,
        f"knowledge-evolution: not_configured 退出码应为 {EXIT_NOT_CONFIGURED}，实际 {proc.returncode}",
        failures,
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    _assert(data.get("status") == "not_configured", "knowledge-evolution: status 应为 not_configured", failures)
    _assert(data.get("status") != "verified", "knowledge-evolution: 未配置时不得写 verified", failures)
    print(
        f"  knowledge-evolution: 退出码 {proc.returncode}，"
        f"status={data.get('status')}，未写 verified"
    )


def _test_modelarts_smoke(tmp: Path, failures: list[str]) -> None:
    report = tmp / "modelarts-latest.json"
    proc = _run(
        "modelarts_smoke.py",
        ["--output", str(report)],
        {},
    )
    _assert(
        proc.returncode == EXIT_NOT_CONFIGURED,
        f"modelarts-smoke: not_configured 退出码应为 {EXIT_NOT_CONFIGURED}，实际 {proc.returncode}",
        failures,
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    _assert(data.get("status") == "not_configured", "modelarts-smoke: status 应为 not_configured", failures)
    _assert(data.get("source") is None, "modelarts-smoke: 未配置时 source 必须为空", failures)
    print(
        f"  modelarts-smoke: 退出码 {proc.returncode}，"
        f"status={data.get('status')}，source={data.get('source')}"
    )


def main() -> int:
    print("== 华为 ICT 证据脚本自测（not_configured 不伪造成功）==")
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ev-scripts-") as td:
        tmp = Path(td)
        _test_knowledge_evolution(tmp, failures)
        _test_modelarts_smoke(tmp, failures)
    if failures:
        print("\nFAIL", file=sys.stderr)
        for msg in failures:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    print("SELFTEST PASS —— 两个脚本在未配置路径均稳定退出码 2，不伪造成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
