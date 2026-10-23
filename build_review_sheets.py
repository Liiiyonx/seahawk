from __future__ import annotations

import argparse
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


def image_contact_sheet(
    paths: list[Path], output: Path, columns: int = 4, cell_width: int = 420, cell_height: int = 650
) -> None:
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((cell_width - 18, cell_height - 48))
        column, row = index % columns, index // columns
        x = column * cell_width + (cell_width - image.width) // 2
        y = row * cell_height + 36 + (cell_height - 48 - image.height) // 2
        sheet.paste(image, (x, y))
        draw.text((column * cell_width + 8, row * cell_height + 8), f"{index + 1:02d}", fill="black")
    sheet.save(output)
    print(f"{output} {sheet.size}")


def pdf_contact_sheet(
    pdf_path: Path, output: Path, columns: int = 4, cell_width: int = 480, cell_height: int = 300
) -> None:
    document = fitz.open(pdf_path)
    rows = (len(document) + columns - 1) // columns
    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), "#dddddd")
    draw = ImageDraw.Draw(sheet)
    for index, page in enumerate(document):
        scale = min((cell_width - 16) / page.rect.width, (cell_height - 38) / page.rect.height)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        column, row = index % columns, index // columns
        x = column * cell_width + (cell_width - image.width) // 2
        y = row * cell_height + 30 + (cell_height - 38 - image.height) // 2
        sheet.paste(image, (x, y))
        draw.text((column * cell_width + 8, row * cell_height + 8), f"SLIDE {index + 1:02d}", fill="black")
    sheet.save(output)
    print(f"{output} {sheet.size}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    images_parser = subparsers.add_parser("images")
    images_parser.add_argument("output", type=Path)
    images_parser.add_argument("inputs", nargs="+", type=Path)
    images_parser.add_argument("--columns", type=int, default=4)
    images_parser.add_argument("--cell-width", type=int, default=420)
    images_parser.add_argument("--cell-height", type=int, default=650)

    pdf_parser = subparsers.add_parser("pdf")
    pdf_parser.add_argument("input", type=Path)
    pdf_parser.add_argument("output", type=Path)
    pdf_parser.add_argument("--columns", type=int, default=4)

    args = parser.parse_args()
    if args.command == "images":
        image_contact_sheet(
            args.inputs,
            args.output,
            columns=args.columns,
            cell_width=args.cell_width,
            cell_height=args.cell_height,
        )
    else:
        pdf_contact_sheet(args.input, args.output, columns=args.columns)


if __name__ == "__main__":
    main()
