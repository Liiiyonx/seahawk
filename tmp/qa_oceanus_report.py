from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageDraw


PDF = Path(
    r"C:\Users\Liii\Desktop\seahawk\output\pdf"
    r"\探海灵眸Oceanus_系统设计报告_参赛优化版.pdf"
)
QA = Path(r"C:\Users\Liii\Desktop\seahawk\tmp\oceanus-report-final-qa")


def main() -> None:
    QA.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF)
    ratios = []
    footer_offsets = []

    for index, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        image.save(QA / f"page-{index + 1:02d}.png", optimize=True)

        arr = np.asarray(image, dtype=np.int16)
        colored = (arr.max(axis=2) - arr.min(axis=2)) > 5
        ratios.append(float(colored.mean()) * 100)

        if index == 0:
            continue
        candidates = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"]).strip()
                if "2026" in text and line["bbox"][1] > page.rect.height * 0.88:
                    candidates.append((text, line["bbox"]))
        if candidates:
            _, bbox = max(candidates, key=lambda item: item[1][1])
            center = (bbox[0] + bbox[2]) / 2
            footer_offsets.append(center - page.rect.width / 2)

    print("PAGES", len(doc))
    print("COLOR_MAX_PERCENT", f"{max(ratios):.6f}")
    print(
        "COLOR_PAGES",
        [(index + 1, round(value, 6)) for index, value in enumerate(ratios) if value > 0.0005],
    )
    print("FOOTER_BLOCKS", len(footer_offsets))
    print(
        "FOOTER_OFFSET_MAX_PT",
        f"{max(abs(value) for value in footer_offsets):.3f}" if footer_offsets else "NA",
    )
    print(
        "FOOTER_OFFSET_AVG_PT",
        f"{sum(footer_offsets) / len(footer_offsets):.3f}" if footer_offsets else "NA",
    )

    thumbs = []
    for path in sorted(QA.glob("page-*.png")):
        with Image.open(path) as source:
            image = source.copy()
            image.thumbnail((248, 351))
            thumbs.append((path.name, image))

    for group in range(0, len(thumbs), 9):
        sheet = Image.new("RGB", (3 * 260, 3 * 375), "white")
        draw = ImageDraw.Draw(sheet)
        for position, (name, image) in enumerate(thumbs[group : group + 9]):
            x = (position % 3) * 260 + 6
            y = (position // 3) * 375 + 18
            sheet.paste(image, (x, y))
            draw.text((x, 2 + (position // 3) * 375), name, fill="black")
        sheet.save(QA / f"contact-{group // 9 + 1}.jpg", quality=92)
    print("QA_DIR", QA)


if __name__ == "__main__":
    main()
