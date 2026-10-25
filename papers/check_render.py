#!/usr/bin/env python3
"""Programmatic page-geometry check for rendered paper pages.

For each PNG: find the bounding box of non-white ink; report how close ink
gets to each page edge as a fraction of page size. Flag pages whose ink
extends beyond typical safe margins. Also detect suspicious fully-blank pages.
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("PIL missing"); sys.exit(2)

def scan(root: Path):
    for png in sorted(root.glob("page*.png"), key=lambda p: int(p.stem[4:])):
        im = Image.open(png).convert("L")
        w, h = im.size
        # ink = pixels darker than 200
        bw = im.point(lambda x: 255 if x < 200 else 0)
        bbox = bw.getbbox()
        if bbox is None:
            print(f"{png.name}: BLANK PAGE  <-- flag")
            continue
        l, t, r, b = bbox
        print(f"{png.name}: {w}x{h}  ink L{l/w:.3f} T{t/h:.3f} R{1-r/w:.3f} B{1-b/h:.3f}"
              + ("  <-- RIGHT-EDGE TIGHT" if r/w > 0.965 else "")
              + ("  <-- LEFT-EDGE TIGHT" if l/w < 0.02 else "")
              + ("  <-- BLANK-ISH" if (r-l)*(b-t) < 0.02*w*h else ""))

for paper in ("pakdd2027", "oceans2027"):
    print(f"==== {paper} ====")
    scan(Path(rf"C:\Users\Liii\Desktop\seahawk\papers\render") / paper)

if __name__ == "__main__":
    pass
