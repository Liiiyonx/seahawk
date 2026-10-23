#!/usr/bin/env python3
"""Assemble the Huawei ICT track-3 submission package.

Rebuilds both Word documents from their Markdown sources, stages the
submission tree under ``dist/huawei-ict-track3-submission/`` following the
structure in ``docs/competitions/huawei-ict-track3-submission-checklist.md``,
runs a secret scan over the staged files, and writes a ZIP next to it.

The output directory lives under ``dist/`` which is gitignored: the package is
a build artifact, not a source file. Exit code is non-zero if any expected
source file is missing or the secret scan trips.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "dist" / "huawei-ict-track3-submission"
ZIP_PATH = ROOT / "dist" / "huawei-ict-track3-submission.zip"

# Drafts that must be rendered to DOCX before staging.
DOC_BUILDERS = (
    "scripts/build_huawei_track3_docx.py",
    "scripts/build_huawei_track3_agent_docx.py",
)

# (source, destination) pairs, destination relative to the staging root.
FILES: tuple[tuple[str, str], ...] = (
    ("项目文档/华为ICT赛道三_开发设计文档.docx", "01_开发设计文档.docx"),
    ("项目文档/华为ICT赛道三_Nexent智能体设计说明.docx", "02_Nexent智能体设计说明.docx"),
    ("docs/competitions/huawei-ict-track3-attachment-guide.md", "03_附送文件说明.md"),
    (
        "artifacts/knowledge-qa-trace/01-检索结果-本体图检索与引用.png",
        "04_示例问答截图/R-KN-04_01-检索结果-本体图检索与引用.png",
    ),
    (
        "artifacts/knowledge-qa-trace/02-决策证据链-资产版本引用.png",
        "04_示例问答截图/R-KN-04_02-决策证据链-资产版本引用.png",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/nexent-console-home.png",
        "04_示例问答截图/R-NX-09_01-nexent-console-home.png",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/nexent-console-newchat.png",
        "04_示例问答截图/R-NX-09_02-nexent-console-newchat.png",
    ),
    ("artifacts/evolution-demo/latest.json", "05_证据包/R-KN-01_latest.json"),
    ("artifacts/ontology-eval/latest.json", "05_证据包/R-KN-02_ontology-eval.json"),
    (
        "artifacts/ontology-eval/incremental-latest.json",
        "05_证据包/R-KN-03_incremental-eval.json",
    ),
    (
        "artifacts/knowledge-qa-trace/latest.json",
        "05_证据包/R-KN-04_knowledge-qa-trace.json",
    ),
    ("artifacts/open-data-eval/latest.json", "05_证据包/R-OD-01_open-data-eval.json"),
    (
        "artifacts/open-data-eval/corpus/manifest.json",
        "05_证据包/open-data-eval_corpus_manifest.json",
    ),
    (
        "artifacts/nexent-platform-acceptance/recheck-2026-09-29.yaml",
        "05_证据包/R-NX-03_recheck.yaml",
    ),
    (
        "artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml",
        "05_证据包/R-NX-04_agent-create.yaml",
    ),
    (
        "artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml",
        "05_证据包/R-NX-05_hosted.yaml",
    ),
    (
        "artifacts/nexent-platform-acceptance/hosted-agent-2026-09-29.yaml",
        "05_证据包/R-NX-06_hosted-agent.yaml",
    ),
    (
        "artifacts/nexent-platform-acceptance/hosted-2026-09-30-target-blocked.yaml",
        "05_证据包/R-NX-07_blocked.yaml",
    ),
    (
        "artifacts/nexent-platform-acceptance/recheck-2026-09-30-llm-qa.yaml",
        "05_证据包/R-NX-09_recheck.yaml",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/agent-run-sse.txt",
        "05_证据包/evidence/llm-qa-2026-09-30/agent-run-sse.txt",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/agent-run-events.json",
        "05_证据包/evidence/llm-qa-2026-09-30/agent-run-events.json",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/agent-run-tools.json",
        "05_证据包/evidence/llm-qa-2026-09-30/agent-run-tools.json",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/agent-run-summary.json",
        "05_证据包/evidence/llm-qa-2026-09-30/agent-run-summary.json",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/agent-publish.json",
        "05_证据包/evidence/llm-qa-2026-09-30/agent-publish.json",
    ),
    (
        "artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/agent-versions.json",
        "05_证据包/evidence/llm-qa-2026-09-30/agent-versions.json",
    ),
    ("artifacts/skill-migration/evidence/latest.json", "05_证据包/R-MG-01_skill-migration.json"),
    ("docs/competitions/standard-code-mapping.md", "06_标准映射表.md"),
    ("artifacts/nexent-mcp-openapi.json", "artifacts/nexent-mcp-openapi.json"),
)

# Whole directories copied recursively: (source dir, destination dir).
TREES: tuple[tuple[str, str], ...] = (
    ("integrations/nexent/mcp_server", "integrations/nexent/mcp_server"),
    ("integrations/nexent/skills", "integrations/nexent/skills"),
)

# Extra single files that belong under integrations/ but sit outside the trees.
EXTRA_INTEGRATION_FILES: tuple[str, ...] = (
    "integrations/nexent/README.md",
    "integrations/nexent/.env.example",
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DeepSeek/OpenAI style key", re.compile(r"\bsk-[0-9a-zA-Z]{16,}")),
    ("AWS style access key", re.compile(r"\bAKIA[0-9A-Z]{12,}")),
    ("Huawei AK/SK assignment", re.compile(r"\b(?:ak|sk)_?(?:id|key)\s*[=:]\s*['\"]?[A-Za-z0-9]{16,}")),
    ("Bearer token literal", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("password assignment", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[=:]\s*['\"][^'\"\s]{6,}['\"]")),
)

TEXT_SUFFIXES = {".json", ".yaml", ".yml", ".md", ".txt", ".py", ".example", ".env", ".toml"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def build_documents() -> None:
    for script in DOC_BUILDERS:
        result = subprocess.run(
            [sys.executable, script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"FAIL: {script} exited {result.returncode}\n{result.stderr}")
        print(f"[build] {script} ok")


def stage_tree() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    missing: list[str] = []
    for source_rel, dest_rel in FILES:
        source = ROOT / source_rel
        if not source.is_file():
            missing.append(source_rel)
            continue
        dest = STAGE / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    for source_rel, dest_rel in TREES:
        source = ROOT / source_rel
        if not source.is_dir():
            missing.append(source_rel)
            continue
        shutil.copytree(source, STAGE / dest_rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    for source_rel in EXTRA_INTEGRATION_FILES:
        source = ROOT / source_rel
        if not source.is_file():
            missing.append(source_rel)
            continue
        dest = STAGE / source_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    if missing:
        raise SystemExit("FAIL: missing source files:\n  " + "\n  ".join(missing))

    staged = sum(1 for path in STAGE.rglob("*") if path.is_file())
    print(f"[stage] {staged} files staged at dist/{STAGE.name}/")


def scan_secrets() -> None:
    hits: list[str] = []
    for path in STAGE.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                hits.append(f"{path.relative_to(STAGE).as_posix()}: {label}: {match.group(0)[:24]}...")
    if hits:
        raise SystemExit("FAIL: secret scan tripped:\n  " + "\n  ".join(hits[:20]))
    print("[scan] secret scan clean")


def make_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(STAGE.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(STAGE.parent).as_posix())
    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"[zip] {rel(ZIP_PATH)} ({size_mb:.2f} MB)")


def main() -> None:
    build_documents()
    stage_tree()
    scan_secrets()
    make_zip()
    print("OK: submission package ready")


if __name__ == "__main__":
    main()
