#!/usr/bin/env python
"""WP-15 证据门禁自测：证明 check_claims.py 真的会红、真的会豁免（不空转）。

两类夹具（写入系统临时目录，不落仓库、不影响 `check_claims --root .`）：
- violations/：10 条故意越级宣称（覆盖 10 条红线规则各 1 条）。
  断言：每条规则都被捕获为 red_line；扫描退出码必须为 1（有未登记红线时非 0）。
- clean/：合法带来源宣称（台账编号引用、登记豁免命中、自限措辞、凭证编号）。
  断言：零 red_line；且必须产生 >=7 次"已豁免"记录（证明豁免机制真实生效，
  而不是规则没触发）；扫描退出码必须为 0。

额外断言（防空转）：
- 登记表完整性：8 个必填字段、E0-E4 等级集合、12 个来源类型受控集合。
- 外部 YAML 入库：`load_registry(外部 intake yaml)` 合并且校验通过；
  缺必填字段的条目必须抛 `RegistryError`。
- `check_claims.main` 对不存在的根目录返回 2（参数错误稳定退出码）。
- 端到端子进程复跑两类夹具目录，退出码分别为 1 与 0。

所有断言失败都会以非 0 退出码结束并打印具体失败原因。
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import check_claims  # noqa: E402
import evidence_registry  # noqa: E402
from evidence_registry import (  # noqa: E402
    EVIDENCE_LEVELS,
    REQUIRED_FIELDS,
    SOURCE_TYPES,
    Registry,
    RegistryError,
    load_registry,
)

# ---------------------------------------------------------------------------
# 夹具一：故意越级宣称（每一行必须命中且只服务其目标规则）
# ---------------------------------------------------------------------------
VIOLATIONS = [
    "我们已签约 3 个客户，合同金额 120 万元。",          # banned_trade_claim
    "公司预计年营收 500 万元。",                        # unsourced_business_number
    "仿真测试在真实海域完成验证。",                      # sim_as_real
    "coverage_area = 0",                              # coverage_area_zero
    "识别准确率达到 76%。",                            # seventy_six_as_accuracy
    "Agent 内存实现是生产级高可用。",                    # agent_memory_as_prod
    "OpenCV 已经达到 YOLO 精度。",                     # opencv_as_model
    "MD5 输出被当作推理结果。",                         # md5_as_model
    "6 个智能体在线协同运行。",                         # static_agents_online
    "我们已完成现场验证，证据等级 E3。",                 # unregistered_evidence_level
]
EXPECTED_VIOLATION_RULES = {
    "banned_trade_claim",
    "unsourced_business_number",
    "sim_as_real",
    "coverage_area_zero",
    "seventy_six_as_accuracy",
    "agent_memory_as_prod",
    "opencv_as_model",
    "md5_as_model",
    "static_agents_online",
    "unregistered_evidence_level",
}

# ---------------------------------------------------------------------------
# 夹具二：合法带来源宣称（必须零红线，且豁免机制真实触发 >=7 次）
# ---------------------------------------------------------------------------
CLEAN_LINES = [
    # 台账编号引用（registry:cites_registered 豁免无来源数字）
    "依据台账 F-01，2023 年 1—10 月连江清理 2.92 万吨。",
    "试点硬件投入约 10.1 万元（台账 C-15，E0 测算）。",
    # 登记记录命中（registry:exempt 豁免 76% 红线）
    "76% 是时序链路误报抑制率，不是识别精度。",
    # 自限措辞（self_limiting 豁免 coverage_area 红线）
    "历史迁移中 coverage_area = 0 属于回退，不算新指标。",
    # 自限措辞（self_limiting 豁免 Agent 内存红线）
    "Agent Runtime 为 E1 本地确定性内存实现，不是生产级分布式。",
    # 自限措辞（self_limiting 豁免 OpenCV 红线）
    "OpenCV 传统视觉代码不是 YOLO，接口预留 YOLO。",
    # 登记记录命中（registry:exempt 豁免 sim_as_real 红线）
    "合成仿真不代表真实海域验证（已登记 R-SIM-01）。",
    # 否定范围声明（无真实对象 → 不是把仿真冒充真实）
    "确定性仿真无真实用户、设备或现场数据。",
    # 自限措辞（self_limiting 豁免成交措辞红线）
    "已签约表述仅出现在带凭证的台账条目中，全项目禁止无凭证使用。",
    # 凭证编号（_VOUCHER_RE 命中 → 该行根本不触发红线）
    "已部署项目凭证：合同编号 HT-2026-001。",
]
MIN_EXEMPTED_EXPECTED = 7


def _check(cond: bool, msg: str, failures: list[str]) -> None:
    if not cond:
        failures.append(msg)


def _write_fixture_dir(tmp: Path, lines: list[str]) -> Path:
    d = tmp / ("violations" if lines is VIOLATIONS else "clean")
    d.mkdir(parents=True, exist_ok=True)
    (d / "fixture.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def _scan_dir(root: Path) -> tuple[check_claims.ScanResult, int]:
    """in-process 扫描：返回详细结果与 main() 的退出码。"""
    registry = Registry(load_registry())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = check_claims.main(["--root", str(root)])
    result = check_claims.scan_root(root, registry)
    return result, code


def _test_violations(tmp: Path, failures: list[str]) -> None:
    d = _write_fixture_dir(tmp, VIOLATIONS)
    result, code = _scan_dir(d)
    red_rules = {f.rule_id for f in result.red_lines}
    missing = EXPECTED_VIOLATION_RULES - red_rules
    _check(
        not missing,
        f"violations: 未被捕获的规则 {sorted(missing)}（红线命中 {sorted(red_rules)}）",
        failures,
    )
    _check(
        len(result.red_lines) >= len(EXPECTED_VIOLATION_RULES),
        f"violations: 红线数量不足 {len(result.red_lines)} < {len(EXPECTED_VIOLATION_RULES)}",
        failures,
    )
    _check(code == 1, f"violations: 退出码应为 1，实际 {code}", failures)
    print(f"  violations: {len(result.red_lines)} 条红线命中"
          f" {len(red_rules)} 条规则，退出码 {code}")


def _test_clean(tmp: Path, failures: list[str]) -> None:
    d = _write_fixture_dir(tmp, CLEAN_LINES)
    result, code = _scan_dir(d)
    _check(len(result.red_lines) == 0, f"clean: 存在误报红线 {result.red_lines}", failures)
    _check(
        len(result.exempted) >= MIN_EXEMPTED_EXPECTED,
        f"clean: 豁免记录 {len(result.exempted)} < {MIN_EXEMPTED_EXPECTED}"
        "（豁免机制未真实触发，禁止空转通过）",
        failures,
    )
    _check(code == 0, f"clean: 退出码应为 0，实际 {code}", failures)
    print(f"  clean: 0 条红线，{len(result.exempted)} 次已豁免，退出码 {code}")


def _test_registry(failures: list[str]) -> None:
    required = set(REQUIRED_FIELDS)
    expected_fields = {
        "id", "claim", "evidence_level", "source_type",
        "source_ref", "captured_at", "review_status", "owner",
    }
    _check(
        required == expected_fields,
        f"registry: REQUIRED_FIELDS 与规格不一致 {sorted(required)}",
        failures,
    )
    _check(
        set(EVIDENCE_LEVELS) == {"E0", "E1", "E2", "E3", "E4"},
        f"registry: EVIDENCE_LEVELS 应含 E0-E4，实际 {sorted(EVIDENCE_LEVELS)}",
        failures,
    )
    expected_types = {
        "public_fact", "internal_calculation", "interview", "inquiry",
        "policy_document", "contract", "receipt", "acceptance",
        "test_report", "field_record", "assumption", "other",
    }
    _check(
        set(SOURCE_TYPES) == expected_types,
        f"registry: SOURCE_TYPES 与规格不一致 {sorted(set(SOURCE_TYPES))}",
        failures,
    )
    records = load_registry()
    _check(len(records) >= 55, f"registry: 默认登记表条数异常 {len(records)}", failures)
    print(f"  registry: 默认登记表 {len(records)} 条；字段/等级/来源类型校验通过")


def _test_external_yaml(tmp: Path, failures: list[str]) -> None:
    good = tmp / "intake_good.yaml"
    good.write_text(
        "schema_version: 1\n"
        "intake_entries:\n"
        "  - id: EV-9001\n"
        "    claim: 外部登记测试条目\n"
        "    evidence_level: E1\n"
        "    source_type: test_report\n"
        "    source_ref: 临时测试\n"
        '    captured_at: "2026-09-19"\n'
        "    review_status: 待复核\n"
        "    owner: selftest\n",
        encoding="utf-8",
    )
    merged = load_registry(good)
    _check(
        any(r.id == "EV-9001" for r in merged),
        "external-yaml: 外部条目未并入登记表",
        failures,
    )

    bad = tmp / "intake_bad.yaml"
    bad.write_text(
        "schema_version: 1\n"
        "intake_entries:\n"
        "  - id: EV-9002\n"
        "    claim: 缺 owner 字段的非法条目\n"
        "    evidence_level: E1\n"
        "    source_type: test_report\n"
        "    source_ref: 临时测试\n"
        '    captured_at: "2026-09-19"\n'
        "    review_status: 待复核\n",
        encoding="utf-8",
    )
    try:
        load_registry(bad)
    except RegistryError:
        pass
    else:
        _check(False, "external-yaml: 缺必填字段的条目未抛 RegistryError", failures)
    print("  external-yaml: 合法入库合并通过；缺字段条目被拒绝")


def _test_bad_root(failures: list[str]) -> None:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = check_claims.main(["--root", str(Path(tempfile.gettempdir()) / "no-such-dir-xyz")])
    _check(code == 2, f"bad-root: 退出码应为 2，实际 {code}", failures)
    print("  bad-root: 不存在根目录返回稳定退出码 2")


def _test_subprocess(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="egt-") as td:
        tmp = Path(td)
        vdir = _write_fixture_dir(tmp, VIOLATIONS)
        cdir = _write_fixture_dir(tmp, CLEAN_LINES)
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        r1 = subprocess.run(
            [sys.executable, "scripts/check_claims.py", "--root", str(vdir)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", env=env,
        )
        r2 = subprocess.run(
            [sys.executable, "scripts/check_claims.py", "--root", str(cdir)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", env=env,
        )
        _check(r1.returncode == 1, f"subprocess: violations 退出码应为 1，实际 {r1.returncode}", failures)
        _check(r2.returncode == 0, f"subprocess: clean 退出码应为 0，实际 {r2.returncode}", failures)
        print(f"  subprocess: violations → {r1.returncode}；clean → {r2.returncode}")


def main() -> int:
    failures: list[str] = []
    print("== WP-15 证据门禁自测（selftest_evidence_gate.py）==")
    with tempfile.TemporaryDirectory(prefix="egt-") as td:
        tmp = Path(td)
        _test_violations(tmp, failures)
        _test_clean(tmp, failures)
        _test_registry(failures)
        _test_external_yaml(tmp, failures)
        _test_bad_root(failures)
    _test_subprocess(failures)

    print("")
    if failures:
        print("SELFTEST FAIL")
        for f in failures:
            print(f"  [FAIL] {f}")
        return 1
    print("SELFTEST PASS —— 越级宣称全部被捕获；带来源宣称全部豁免；退出码语义正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
