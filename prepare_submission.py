from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader, PdfWriter
from pptx import Presentation


DESKTOP = Path(r"C:\Users\Liii\Desktop")
WORKSPACE = DESKTOP / "seahawk"
BUILD = WORKSPACE / "submission_build"

COMPETITION = DESKTOP / "2026年海峡大学生人工智能创意大赛"
OFFICIAL_NAME = "福州理工学院－探海灵眸Oceanus－李涌翔－18259099729"
FINAL_DIR = COMPETITION / OFFICIAL_NAME

PPT_SOURCE = (
    COMPETITION
    / "提交材料"
    / "探海灵眸Oceanus_作品介绍PPT_2026海峡大赛_极致终版.pptx"
)
TECH_DOC_SOURCE = COMPETITION / "提交材料" / "探海灵眸Oceanus_技术文档_2026海峡大赛.docx"
REPORT_SOURCE = (
    DESKTOP
    / "探海灵眸Oceanus-提交材料"
    / "探海灵眸Oceanus_系统设计报告_参赛优化版.pdf"
)
VIDEO_SOURCE = DESKTOP / "科创赛道-探海灵眸-18259099729" / "演示视频_探海灵眸.mp4"
EVIDENCE_ROOT = DESKTOP / "科创赛道-探海灵眸-18259099729" / "佐证材料"
SOURCE_ROOT = WORKSPACE / "old_zip_review" / "03_源代码"


def reset_build() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "01_作品介绍").mkdir(parents=True)
    (BUILD / "02_演示材料").mkdir(parents=True)
    (BUILD / "03_源代码").mkdir(parents=True)
    (BUILD / "04_加分项举证").mkdir(parents=True)


def clear_docx_metadata(doc: Document) -> None:
    props = doc.core_properties
    props.author = ""
    props.last_modified_by = ""
    props.title = ""
    props.subject = ""
    props.keywords = ""
    props.comments = ""
    props.category = ""
    props.content_status = ""
    props.identifier = ""
    props.language = ""
    props.version = ""


def clear_pdf_metadata(path: Path) -> None:
    temp_path = path.with_suffix(".sanitized.pdf")
    reader = PdfReader(path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Author": "",
            "/Title": "",
            "/Subject": "",
            "/Keywords": "",
        }
    )
    writer.xmp_metadata = None
    writer.write(temp_path)
    os.replace(temp_path, path)


def replace_in_paragraph(paragraph, old: str, new: str) -> bool:
    changed = False
    for run in paragraph.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)
            changed = True
    if changed:
        return True
    combined = paragraph.text
    if old not in combined:
        return False
    replaced = combined.replace(old, new)
    if paragraph.runs:
        paragraph.runs[0].text = replaced
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(replaced)
    return True


def replace_docx_text(doc: Document, old: str, new: str) -> None:
    for paragraph in doc.paragraphs:
        replace_in_paragraph(paragraph, old, new)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_in_paragraph(paragraph, old, new)


def set_exact_cell_text(table, row: int, col: int, text: str) -> None:
    paragraph = table.rows[row].cells[col].paragraphs[0]
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def remove_empty_page_break_before_heading(doc: Document, heading: str) -> None:
    paragraphs = doc.paragraphs
    for index, paragraph in enumerate(paragraphs):
        if paragraph.text.strip() != heading or index == 0:
            continue
        previous = paragraphs[index - 1]
        if previous.text.strip():
            continue
        page_breaks = [
            node
            for node in previous._p.xpath(".//w:br")
            if node.get(qn("w:type")) == "page"
        ]
        if page_breaks:
            previous._p.getparent().remove(previous._p)
        return


def prepare_ppt() -> None:
    prs = Presentation(PPT_SOURCE)

    slide14 = prs.slides[13]
    slide15 = prs.slides[14]

    for shape in slide14.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        if shape.text == "感知精度":
            shape.text_frame.paragraphs[0].runs[0].text = "现场感知精度"
        elif shape.text == "not_evaluated":
            shape.text_frame.paragraphs[0].runs[0].text = "未验证"
        elif shape.text == "独立测试集未放行，不做任何精度数字宣称。":
            shape.text_frame.paragraphs[0].runs[0].text = (
                "公开基准已有独立评测，连江现场与本设备实测未开展，不宣称现场精度。"
            )

    for shape in slide15.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        if shape.text == "独立测试集感知精度":
            shape.text_frame.paragraphs[0].runs[0].text = "公开基准独立评测"

    props = prs.core_properties
    props.author = ""
    props.last_modified_by = ""
    props.title = ""
    props.subject = ""
    props.keywords = ""
    props.comments = ""
    props.category = ""
    props.content_status = ""
    props.identifier = ""
    props.language = ""
    props.version = ""
    prs.save(BUILD / "01_作品介绍" / "探海灵眸Oceanus_作品介绍PPT_匿名版.pptx")


def prepare_technical_doc() -> None:
    doc = Document(TECH_DOC_SOURCE)
    table14 = doc.tables[14]
    set_exact_cell_text(table14, 7, 0, "公开基准评测")
    set_exact_cell_text(table14, 7, 1, "evaluate_public_litter.py")
    set_exact_cell_text(
        table14,
        7,
        2,
        "SC-FloatWaste 独立测试集 mAP50 0.5135；不代表现场或本设备精度",
    )

    table15 = doc.tables[15]
    set_exact_cell_text(table15, 1, 0, "现场感知精度未验证")
    set_exact_cell_text(table15, 1, 1, "公开基准已评测；连江现场与本设备实测未开展")
    set_exact_cell_text(table15, 1, 2, "公开基准结果不能替代现场设备精度")
    set_exact_cell_text(table15, 1, 3, "采集本地验证集，按区域、光照与潮汐分层评测")

    remove_empty_page_break_before_heading(doc, "5. 智能体工具契约")
    clear_docx_metadata(doc)
    doc.save(BUILD / "01_作品介绍" / "探海灵眸Oceanus_技术文档_匿名版.docx")


def prepare_evidence_docs() -> None:
    evidence = BUILD / "04_加分项举证"

    interview_src = EVIDENCE_ROOT / "02_用户访谈-连江县海渔局" / "访谈纪要_连江县海渔局.docx"
    interview_out_dir = evidence / "02_真实用户访谈"
    interview_out_dir.mkdir(parents=True)
    doc = Document(interview_src)
    replace_docx_text(doc, "；访谈人：李涌翔（项目负责人）", "；访谈记录已匿名化")
    clear_docx_metadata(doc)
    doc.save(interview_out_dir / "访谈纪要_连江县海渔局_匿名版.docx")
    for image in sorted((interview_src.parent).glob("访谈*.png")):
        shutil.copy2(image, interview_out_dir / image.name)

    quote_src = EVIDENCE_ROOT / "03_供应商询价调研-浙江蓝舶游艇科技公司"
    quote_out = evidence / "03_供应商询价"
    quote_out.mkdir(parents=True)
    doc = Document(quote_src / "00_供应商询价汇总表.docx")
    replace_docx_text(doc, " · 采集人：李涌翔", "")
    replace_docx_text(
        doc,
        "• 询价 15 份原始记录（微信 / 平台截图与 PDF）均存于本目录，可溯源、可复核；其中询价13、询价15 为供应商盖章报价单。",
        "• 汇总表依据 15 份前期询价记录整理；本次提交附浙江蓝舶整船方案盖章报价单，用于核查船体、推进器与电池组合价。表中其他价格为调研摘录，不作为成交承诺。",
    )
    replace_docx_text(doc, "；客户单位：福州理工学院", "")
    clear_docx_metadata(doc)
    doc.save(quote_out / "供应商询价调研摘要_匿名版.docx")
    quote_image = (
        quote_src
        / "01_整船打包方案（浙江蓝舶）"
        / "询价13_船体推进电池报价单_浙江蓝舶游艇_2026.10.10.png"
    )
    shutil.copy2(quote_image, quote_out / quote_image.name)

    detection_src = EVIDENCE_ROOT / "04_检测效果图"
    detection_out = evidence / "04_检测效果"
    detection_out.mkdir(parents=True)
    doc = Document(detection_src / "00_检测效果说明.docx")
    replace_docx_text(doc, " · 采集人：李涌翔", "")
    clear_docx_metadata(doc)
    doc.save(detection_out / "检测效果说明_匿名版.docx")
    for name in (
        "01_监测大屏截图.png",
        "02_机械臂拾取作业.png",
        "03_机械臂受控拾取实拍.mp4",
        "04_水面多目标检测.jpg",
        "05_岸滩多目标检测.jpg",
        "06_岸滩泡沫塑料检测.jpg",
    ):
        shutil.copy2(detection_src / name, detection_out / name)

    eval_src = EVIDENCE_ROOT / "05_评测与验证"
    eval_out = evidence / "05_评测与验证"
    report_out = eval_out / "原始报告"
    report_out.mkdir(parents=True)
    doc = Document(eval_src / "00_系统评测与验证佐证.docx")
    replace_docx_text(doc, "2026 校级选拔辅助材料", "参赛辅助材料")
    clear_docx_metadata(doc)
    doc.save(eval_out / "系统评测与验证佐证_匿名版.docx")

    path_replacements = (
        (
            r"C:\Users\Liii\Desktop\seahawk\.venv-analysis\Scripts\python.exe",
            "python",
        ),
        (r"C:\Users\Liii\Desktop\seahawk", "."),
        (r"D:\seahawk-work", "artifacts/models"),
        (r"C:\Users\Liii", "<LOCAL_PATH>"),
        (r"D:\\", "<LOCAL_DRIVE>\\"),
    )

    def sanitize_value(value):
        if isinstance(value, dict):
            return {key: sanitize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [sanitize_value(item) for item in value]
        if isinstance(value, str):
            text = value
            for old, new in path_replacements:
                text = text.replace(old, new)
            return text
        return value

    for source in sorted((eval_src / "原始报告").glob("*.json")):
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        clean = sanitize_value(data)
        (report_out / source.name).write_text(
            json.dumps(clean, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    copyright_src = EVIDENCE_ROOT / "01_知识产权-软著"
    copyright_out = evidence / "01_软件著作权申请材料"
    copyright_out.mkdir(parents=True)
    program_names = {
        "01_海洋环境治理智能体（Oceanus主平台）": "海洋环境治理智能体_源程序鉴别材料.pdf",
        "02_海漂垃圾边缘智能感知": "海漂垃圾边缘智能感知_源程序鉴别材料.pdf",
        "03_智能体决策与审批": "智能体决策与审批_源程序鉴别材料.pdf",
        "04_三维数字沙盘": "三维数字沙盘_源程序鉴别材料.pdf",
        "05_机械臂控制": "机械臂控制_源程序鉴别材料.pdf",
    }
    for folder, output_name in program_names.items():
        matches = list((copyright_src / folder).glob("*程序鉴别材料*.pdf"))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one program PDF in {folder}, found {len(matches)}")
        shutil.copy2(matches[0], copyright_out / output_name)
        clear_pdf_metadata(copyright_out / output_name)


def copy_source() -> None:
    destination = BUILD / "03_源代码"
    excluded_dirs = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "node_modules",
        "artifacts",
        "runs",
        "dist",
        "coverage",
        ".git",
    }
    excluded_names = {
        ".env",
        ".edge_state.json",
        "simulator_state.json",
        "generate_lianjiang_drafts.py",
        "build_public_release.py",
        "build_strait_ai_pptx.py",
        "check_public_repo_privacy.py",
        "precommit_scan.py",
        "package_strait_ai_submission.py",
        "package_huawei_track3_submission.py",
        "build_huawei_track3_agent_docx.py",
        "build_huawei_track3_docx.py",
    }
    excluded_suffixes = {
        ".pt",
        ".onnx",
        ".pth",
        ".ckpt",
        ".pkl",
        ".zip",
        ".mp4",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".log",
        ".pid",
        ".pyc",
    }

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            path = Path(directory) / name
            if name in excluded_dirs or name in excluded_names:
                ignored.add(name)
                continue
            if name.startswith(".env") and name != ".env.example":
                ignored.add(name)
                continue
            if path.is_file() and path.suffix.lower() in excluded_suffixes:
                ignored.add(name)
        return ignored

    for folder in ("backend", "edge", "ml", "integrations", "scripts"):
        shutil.copytree(SOURCE_ROOT / folder, destination / folder, ignore=ignore)
    shutil.copytree(
        SOURCE_ROOT / "frontend" / "src",
        destination / "frontend" / "src",
        ignore=ignore,
    )
    shutil.copy2(SOURCE_ROOT / "frontend" / "package.json", destination / "frontend" / "package.json")
    shutil.copy2(SOURCE_ROOT / ".env.example", destination / ".env.example")
    shutil.copy2(SOURCE_ROOT / "docker-compose.prod.yml", destination / "docker-compose.prod.yml")
    shutil.copy2(SOURCE_ROOT / "Makefile", destination / "Makefile")


def write_readmes() -> None:
    root_readme = """# 探海灵眸 Oceanus 参赛提交包

## 目录

- `01_作品介绍/`：作品介绍 PPT、系统设计报告、技术文档。
- `02_演示材料/`：作品演示视频。
- `03_源代码/`：核心后端、边缘端、感知、前端与验证脚本。
- `04_加分项举证/`：软件著作权申请材料、真实用户访谈、供应商询价、检测效果与评测报告。

## 口径说明

- 公开基准指标来自第三方数据集 SC-FloatWaste 的独立测试集，不代表连江现场、本项目设备或真实海域实测精度。
- 软件著作权材料为申请过程中的源程序鉴别材料，不代表已经取得登记证书。
- 用户访谈用于证明真实需求线索；供应商报价用于成本调研，不构成合同、订单、回款或成交承诺。
- 源码包已排除密钥、运行状态、模型权重、数据集和大体积运行产物，保留 `.env.example` 占位配置。
"""
    (BUILD / "README.md").write_text(root_readme, encoding="utf-8")

    copyright_readme = """# 软件著作权申请材料说明

本目录仅保留 5 项软件的源程序鉴别材料，用于证明软件形成过程与代码归属。

这些 PDF 是软件著作权登记申请过程中的鉴别材料，不代表已经取得软件著作权登记证书。软件说明书未放入本提交包，因为其中含学校名称。
"""
    (BUILD / "04_加分项举证" / "01_软件著作权申请材料" / "README.md").write_text(
        copyright_readme, encoding="utf-8"
    )

    source_readme = """# 源代码说明

本目录保留核心业务、边缘端、感知工程、前端页面与验证脚本，供技术评审阅读。

已排除真实 `.env`、运行状态、模型权重、数据集、缓存和大体积运行产物。`.env.example` 仅含占位配置。复现步骤见提交包根目录 `README.md`。
"""
    (BUILD / "03_源代码" / "README.md").write_text(source_readme, encoding="utf-8")


def main() -> None:
    reset_build()
    prepare_ppt()
    prepare_technical_doc()
    shutil.copy2(REPORT_SOURCE, BUILD / "01_作品介绍" / "探海灵眸Oceanus_系统设计报告.pdf")
    shutil.copy2(VIDEO_SOURCE, BUILD / "02_演示材料" / "探海灵眸Oceanus_演示视频.mp4")
    prepare_evidence_docs()
    copy_source()
    write_readmes()
    print(BUILD)


if __name__ == "__main__":
    main()
