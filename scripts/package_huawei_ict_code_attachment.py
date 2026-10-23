#!/usr/bin/env python3
"""Build the Huawei ICT innovation-track CODE ATTACHMENT zip.

The official design-document template marks the complete code as a mandatory
separate attachment (“完整代码文件请作为单独附件（必选）”). This script stages
the real repository trees (source only — no secrets, no models/datasets, no
build outputs, no internal competition-strategy docs), runs a secret scan and
an unregistered-claim check over the staged tree, and writes
``dist/huawei-ict-code-attachment.zip``.

Exit code is non-zero if any staged-file check trips; it never produces a
silently incomplete package.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "dist" / "huawei-ict-code-attachment"
ZIP_PATH = ROOT / "dist" / "huawei-ict-code-attachment.zip"

# 顶层：目录树（整体复制，递归）与单文件。
TREES: tuple[str, ...] = (
    "backend",
    "frontend/src",
    "frontend/public",
    "edge",
    "ml/configs",
    "ml/scripts",
    "integrations/nexent/mcp_server",
    "integrations/nexent/skills",
    "scripts",
    "deploy",
    "docs/code-wiki",
    "verify/arm_chain_e2e",
)
FILES: tuple[str, ...] = (
    "Makefile",
    "README.md",
    "LICENSE",
    "pytest.ini",
    "conftest.py",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    ".env.example",
    "backend/requirements.txt",
    "backend/alembic.ini",
    "frontend/package.json",
    "frontend/vite.config.js",
    "frontend/index.html",
    "frontend/nginx.conf",
    "integrations/nexent/README.md",
    "integrations/nexent/.env.example",
    "docs/architecture.md",
    "docs/api.md",
    "docs/mqtt-topics.md",
    "docs/deployment.md",
    "docs/development.md",
    "docs/decisions.md",
    "docs/perception-data-protocol.md",
    "docs/device-interface.md",
)

# 整体排除的目录名（任意层级命中即跳过）。
EXCLUDED_DIR_NAMES = {
    "__pycache__", "node_modules", ".venv", ".venv-analysis", ".pytest_cache",
    ".git", "dist", "build", "artifacts", "models", "weights", "datasets",
    "runs", ".idea", ".vscode", ".work", "_work", "tmp", "__macosx",
}
EXCLUDED_FILE_SUFFIXES = {
    ".pt", ".onnx", ".pth", ".weights", ".ckpt", ".zip", ".mp4", ".png", ".jpg",
    ".jpeg", ".pdf", ".docx", ".pptx", ".xlsx", ".sqlite3", ".db", ".log",
}
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DeepSeek/OpenAI style key", re.compile(r"\bsk-[0-9a-zA-Z]{16,}")),
    ("AWS style access key", re.compile(r"\bAKIA[0-9A-Z]{12,}")),
    ("Huawei AK/SK assignment", re.compile(r"\b(?:ak|sk)_?(?:id|key)\s*[=:]\s*['\"]?[A-Za-z0-9]{16,}")),
    ("Bearer token literal", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("password assignment", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[=:]\s*['\"](?!<DEPLOYMENT-SECRET>)[^'\"\s]{6,}['\"]")),
)
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini",
                 ".cfg", ".example", ".env", ".vue", ".ts", ".js", ".mjs", ".cjs",
                 ".sql", ".html", ".css", ".sh", ".service", ".conf"}


def iter_stage_files() -> list[Path]:
    files: list[Path] = []
    for tree in TREES:
        source = ROOT / tree
        if not source.is_dir():
            raise SystemExit(f"FAIL: missing tree: {tree}")
        for p in source.rglob("*"):
            if not p.is_file():
                continue
            if any(part in EXCLUDED_DIR_NAMES for part in p.relative_to(source).parts[:-1]):
                continue
            if p.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
                continue
            if p.name in {".env", ".env.production", "secrets.yaml"} or p.name.startswith(".acceptance"):
                continue
            files.append(p)
    for rel in FILES:
        p = ROOT / rel
        if not p.is_file():
            raise SystemExit(f"FAIL: missing file: {rel}")
        files.append(p)
    return files


def sanitize(text: str) -> str:
    """Packaging-time secret templating: demo device credentials in the repo
    become <DEPLOYMENT-SECRET> placeholders in the attachment copy. Repo
    originals are never modified."""
    return re.sub(
        r"(?i)\b(password|passwd|pwd)\s*([=:])\s*(['\"])[^'\"\s]{6,}(['\"])",
        r"\1\2\3<DEPLOYMENT-SECRET>\4",
        text,
    )


def stage(files: list[Path]) -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    for p in files:
        rel = p.relative_to(ROOT)
        dest = STAGE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() in TEXT_SUFFIXES:
            try:
                dest.write_text(sanitize(p.read_text(encoding="utf-8", errors="ignore")), encoding="utf-8")
            except (OSError, UnicodeError):
                shutil.copy2(p, dest)
        else:
            shutil.copy2(p, dest)
    # .gitignore 复制为模板参考（若无则跳过）
    gitignore = ROOT / ".gitignore"
    if gitignore.is_file():
        shutil.copy2(gitignore, STAGE / ".gitignore")


def scan_secrets() -> None:
    hits: list[str] = []
    for p in STAGE.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                hits.append(f"{p.relative_to(STAGE).as_posix()}: {label}: {m.group(0)[:24]}...")
    if hits:
        raise SystemExit("FAIL: secret scan tripped:\n  " + "\n  ".join(hits[:20]))
    print("[scan] secret scan clean")


def scan_claims() -> None:
    """宣称门禁复扫（只扫暂存树，避免整仓扫描的既有豁免差异）。"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "check_claims.py"), "--root", str(STAGE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-8:])
        raise SystemExit(f"FAIL: claims gate on staged tree:\n{tail}")
    print("[scan] claims gate clean (staged tree)")


def make_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                archive.write(p, p.relative_to(STAGE.parent).as_posix())
    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    count = sum(1 for p in STAGE.rglob("*") if p.is_file())
    print(f"[zip] dist/{ZIP_PATH.name} ({size_mb:.2f} MB, {count} files)")


def main() -> None:
    files = iter_stage_files()
    print(f"[stage] {len(files)} source files")
    stage(files)
    scan_secrets()
    scan_claims()
    make_zip()
    print("OK: code attachment ready")


if __name__ == "__main__":
    main()
