#!/usr/bin/env python3
"""Quick LaTeX sanity lint for the two paper drafts."""
import re
from pathlib import Path

for fp in (r"C:\Users\Liii\Desktop\seahawk\papers\pakdd2027\main.tex",
           r"C:\Users\Liii\Desktop\seahawk\papers\oceans2027\main.tex"):
    src = Path(fp).read_text(encoding="utf-8")
    issues = []
    body_lines = []
    for i, ln in enumerate(src.splitlines(), 1):
        clean = re.sub(r"(?<!\\)%.*$", "", ln)  # strip comments
        body_lines.append((i, clean))
    body = "\n".join(c for _, c in body_lines)
    begins = re.findall(r"\\begin\{(\w+\*?)\}", body)
    ends = re.findall(r"\\end\{(\w+\*?)\}", body)
    if sorted(begins) != sorted(ends):
        issues.append(f"env mismatch: begin={sorted(begins)} end={sorted(ends)}")
    depth = 0
    for i, c in body_lines:
        if re.search(r"\\begin\{tabular", c):
            depth += 1
        if re.search(r"\\end\{tabular", c):
            depth -= 1
        for ch in c:
            if ord(ch) > 127:
                issues.append(f"line {i}: non-ascii {ch!r} :: {c.strip()[:70]}")
                break
        if depth == 0:
            for m in re.finditer(r"(?<!\\)[&_]", c):
                issues.append(f"line {i}: raw {m.group()!r} outside tabular :: {c.strip()[:70]}")
    # brace balance
    if body.count("{") != body.count("}"):
        issues.append(f"brace imbalance: {{={body.count('{')} }}={body.count('}')}")
    print("====", Path(fp).parent.name, "====")
    print("\n".join(issues) if issues else "CLEAN")
