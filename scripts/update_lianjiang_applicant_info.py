# -*- coding: utf-8 -*-
r"""按《李涌翔.xlsx》更新报名表中申报人信息（2026-10-11）。

改动：
- Sheet1 F15 主要申报人简介：+学业排名、OPC技术部部长、软著3项、论文2篇、3项新获奖
- Sheet1 F16 行高修复（内容不变，原被截断只显示2行）
- Sheet2 F5 申报人代表性奖项荣誉：+教育信息技术大赛初赛一等奖（晋级国赛）、OAIC前20%
- Sheet2 F6 行高修复（内容不变，末尾代码仓库URL被截断）
- Sheet2 B19/B20：软著3项条目 + 暂无专利顺延
文件名：scripts/update_lianjiang_applicant_info.py
"""
import math
import openpyxl

XLSX = r"C:\Users\Liii\Desktop\连江县创新创业大赛\报名表_探海灵眸_初稿.xlsx"

NEW_F15 = (
    "李涌翔，男，汉族，2005年11月出生，籍贯福建龙岩，福州理工学院计算与信息科学学院智能科学与技术专业2025级本科生"
    "（2025-09至2029-06），学号2501133021，专业综合测评排名3/47，学业测评排名16。现担任班级副班长、OPC协会技术部部长"
    "（2026.03至今），兼任计信学院体育部干事、FIT学生体育部校队中心干事和校田径队投掷组组长。担任大学生创新创业训练计划项目"
    "（BlindGuard）负责人，参与福建省中青年科研项目《异构传感器模式的非结构化道路检测识别》，负责负障碍物危险等级划分与目标"
    "识别检测模块开发；已提交3项软件著作权登记申请（探海灵眸 Oceanus、聆心、BlindGuard），2篇第一作者论文在投ICASSP 2027。"
    "曾获2026海峡两岸（福州）青少年AI交流活动·AI Agent应用创新挑战赛（大学组）一等奖、闽都×火山杯Agent创新大赛荣誉奖、"
    "2026第三届教育信息技术应用创新大赛初赛一等奖（晋级国赛，队长）、OAIC智能体软件工厂黑客松全球前20%，以及军训标兵、"
    "院三好学生、校运会接力冠军等荣誉。在本项目中担任项目负责人，负责总体方案、软件平台、机械臂对接和对外材料口径；本项目"
    "软件部分（后端、Agent Runtime、前端、边缘感知、机械臂桥接层、集成验收）由本人独立完成，代码仓库 "
    "https://github.com/Liiiyonx/seahawk。"
)

NEW_F5 = (
    "2026海峡两岸（福州）青少年AI交流活动·AI Agent应用创新挑战赛（大学组）一等奖；闽都×火山杯Agent创新大赛"
    "（AI原生治理赛道）荣誉奖；2026第三届教育信息技术应用创新大赛初赛一等奖（晋级国赛，队长）；OAIC智能体软件工厂"
    "黑客松全球前20%；大学生创新创业训练计划项目（BlindGuard）负责人。"
)

NEW_B19 = (
    "5. 软件著作权 3 项（探海灵眸 Oceanus、聆心、BlindGuard），已完成鉴别材料制作并提交中国版权保护中心登记申请"
    "（BlindGuard 与王振源共同完成）"
)
NEW_B20 = "6. 暂无授权专利（待申报）"


def calc_height(text: str, col_units: float, per_line: float = 15.0, margin: float = 12.0) -> float:
    """按『全角=2单位/半角=1单位』估算折行数 → 行高（留 margin 余量）"""
    w = sum(2 if ord(ch) > 0x2E00 else 1 for ch in text)
    lines = math.ceil(w / col_units)
    return lines * per_line + margin, lines


def main() -> None:
    wb = openpyxl.load_workbook(XLSX)
    ws1 = wb["1.报名表"]
    ws2 = wb["2.项目申报书"]

    assert ws1["F15"].value.startswith("李涌翔，男，汉族"), "F15 内容不符合预期"
    assert ws2["F5"].value.startswith("2026海峡两岸"), "F5 内容不符合预期"
    assert ws2["B19"].value.startswith("5. 暂无授权专利"), "B19 内容不符合预期"

    # --- 写入新内容 ---
    ws1["F15"] = NEW_F15
    ws2["F5"] = NEW_F5
    ws2["B19"] = NEW_B19
    ws2["B20"] = NEW_B20

    # --- 行高（F:H 列宽 sheet1=42.85 / sheet2=47.1 单位）---
    h15, n15 = calc_height(NEW_F15, 42.85)
    h16, n16 = calc_height(ws1["F16"].value, 42.85)
    h5, n5 = calc_height(NEW_F5, 47.1)
    h6, n6 = calc_height(ws2["F6"].value, 47.1)
    print("F15: %d字 → %d行 → %.0fpt" % (len(NEW_F15), n15, h15))
    print("F16: %d字 → %d行 → %.0fpt" % (len(ws1["F16"].value), n16, h16))
    print("F5 : %d字 → %d行 → %.0fpt" % (len(NEW_F5), n5, h5))
    print("F6 : %d字 → %d行 → %.0fpt" % (len(ws2["F6"].value), n6, h6))
    assert h15 <= 409, "F15 行高超 Excel 上限 409pt，需精简文本"
    ws1.row_dimensions[15].height = h15
    ws1.row_dimensions[16].height = max(h16, 40)   # 修复截断
    ws2.row_dimensions[5].height = max(h5, 79)
    ws2.row_dimensions[6].height = max(h6, 99)     # 修复截断

    wb.save(XLSX)
    print("[OK] 已保存:", XLSX)

    # --- 读回验证 ---
    wb2 = openpyxl.load_workbook(XLSX)
    print("读回 F15 前40字:", wb2["1.报名表"]["F15"].value[:40])
    print("读回 F5  前40字:", wb2["2.项目申报书"]["F5"].value[:40])
    print("读回 B19 前40字:", wb2["2.项目申报书"]["B19"].value[:40])
    print("读回 B20     :", wb2["2.项目申报书"]["B20"].value)
    print("行高: sheet1-15=%s 16=%s | sheet2-5=%s 6=%s" % (
        wb2["1.报名表"].row_dimensions[15].height, wb2["1.报名表"].row_dimensions[16].height,
        wb2["2.项目申报书"].row_dimensions[5].height, wb2["2.项目申报书"].row_dimensions[6].height))


if __name__ == "__main__":
    main()