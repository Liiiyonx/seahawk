from __future__ import annotations

import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def slide_texts(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for name in names:
            root = ET.fromstring(archive.read(name))
            result[Path(name).stem] = [
                node.text or "" for node in root.findall(".//a:t", NS)
            ]
    return result


def main(left: str, right: str) -> None:
    left_text = slide_texts(Path(left))
    right_text = slide_texts(Path(right))
    differences = []

    for slide, texts in left_text.items():
        if right_text.get(slide) != texts:
            differences.append(slide)

    print(f"Slides compared: {len(left_text)}")
    print(f"Text differences: {len(differences)}")
    for slide in differences:
        print(slide)

    if differences or set(left_text) != set(right_text):
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
