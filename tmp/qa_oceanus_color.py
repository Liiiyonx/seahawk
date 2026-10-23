from pathlib import Path

import fitz
from PIL import Image, ImageDraw


PDF = Path(
    r"C:\Users\Liii\Desktop\seahawk\output\pdf"
    r"\探海灵眸Oceanus_系统设计报告_参赛优化版.pdf"
)
QA = Path(r"C:\Users\Liii\Desktop\seahawk\tmp\oceanus-color-qa")


def main() -> None:
    QA.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF)
    colors: dict[int, int] = {}
    nonblack: list[tuple[int, int, str]] = []
    footer_offsets: list[float] = []
    image_pages: list[int] = []

    for index, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        image.save(QA / f"page-{index + 1:02d}.png", optimize=True)

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") == 1:
                image_pages.append(index + 1)
            for line in block.get("lines", []):
                for span in line["spans"]:
                    color = int(span.get("color", -1))
                    text = span.get("text", "")
                    colors[color] = colors.get(color, 0) + len(text)
                    if color != 0 and text.strip():
                        nonblack.append((index + 1, color, text[:80]))

        if index == 0:
            continue
        candidates: list[tuple[float, float, float, float]] = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"]).strip()
                if "2026" in text and line["bbox"][1] > page.rect.height * 0.88:
                    candidates.append(line["bbox"])
        if candidates:
            bbox = max(candidates, key=lambda item: item[1])
            footer_offsets.append(((bbox[0] + bbox[2]) / 2) - page.rect.width / 2)

    thumbs: list[tuple[str, Image.Image]] = []
    for path in sorted(QA.glob("page-*.png")):
        with Image.open(path) as source:
            thumbnail = source.copy()
            thumbnail.thumbnail((248, 351))
            thumbs.append((path.name, thumbnail))

    for group in range(0, len(thumbs), 9):
        sheet = Image.new("RGB", (3 * 260, 3 * 375), "white")
        draw = ImageDraw.Draw(sheet)
        for position, (name, image) in enumerate(thumbs[group : group + 9]):
            x = (position % 3) * 260 + 6
            y = (position // 3) * 375 + 18
            sheet.paste(image, (x, y))
            draw.text((x, 2 + (position // 3) * 375), name, fill="black")
        sheet.save(QA / f"contact-{group // 9 + 1}.jpg", quality=92)

    print("PAGES", len(doc))
    print("TEXT_COLORS", colors)
    print("NONBLACK_TEXT", nonblack[:20], "COUNT", len(nonblack))
    print("FOOTER_BLOCKS", len(footer_offsets))
    print(
        "FOOTER_OFFSET_MAX_PT",
        max(abs(value) for value in footer_offsets) if footer_offsets else "NA",
    )
    print("IMAGE_BLOCKS", len(image_pages), "UNIQUE_PAGES", sorted(set(image_pages)))
    print("QA_DIR", QA)


if __name__ == "__main__":
    main()
