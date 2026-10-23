# -*- coding: utf-8 -*-
"""渲染《情况说明》PDF 验证签名嵌入效果"""
import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader

PDF = r"C:\Users\Liii\Desktop\连江县创新创业大赛\证明材料\情况说明_未设经营实体无出资_李涌翔.pdf"

txt = "".join(p.extract_text() or "" for p in PdfReader(PDF).pages)
for key in ["李涌翔", "情况说明", "2026 年 10 月", "申报人"]:
    print("文本含 %s: %s" % (key, key in txt))

pdf = pdfium.PdfDocument(PDF)
print("页数:", len(pdf))
page = pdf[0]
img = page.render(scale=2.0).to_pil()
print("页面渲染尺寸:", img.size)
img.save(r"C:\Users\Liii\AppData\Local\Temp\funding_note_full.png")
w, h = img.size
crop = img.crop((0, int(h * 0.60), w, h))
crop = crop.resize((int(crop.width * 1.4), int(crop.height * 1.4)), Image.LANCZOS)
crop.save(r"C:\Users\Liii\AppData\Local\Temp\funding_note_bottom.png")
print("saved full + bottom")