# -*- coding: utf-8 -*-
"""连江材料同步 · 路演 PPT HTML 更新（2026-10-11）。

改动：
  1. SeaSight → Oceanus（标题/封面/竞品表头/页眉/CSS 注释）
  2. 23/23 → 27/27（s10 两处 + s16 计数器）
  3. 误报抑制 76% → 42–76%（s2/s9/s10/s16 四处，含口径脚注）
  4. s10 左卡新增：SC-FloatWaste 公开基准 + 真实世界证据（访谈/询价/软著）
  5. s10 平台截图替换为当前版本监测大屏（1920×395 条带）
输出：源文件/探海灵眸Oceanus_国创路演_动效版.html
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

SRC = Path(r"C:\Users\Liii\Desktop\连江县创新创业大赛\源文件\探海灵眸SeaSight_国创路演_动效版.html")
DST = Path(r"C:\Users\Liii\Desktop\连江县创新创业大赛\源文件\探海灵眸Oceanus_国创路演_动效版.html")
BANNER = Path(r"C:\Users\Liii\AppData\Local\Temp\lj_shots\dashboard_banner_final.jpg")


def sub_once(src: str, old: str, new: str, expect: int = 1) -> str:
    n = src.count(old)
    assert n == expect, f"目标出现 {n} 次（期望 {expect}）：{old[:60]!r}"
    return src.replace(old, new)


def main() -> None:
    html = SRC.read_text(encoding="utf-8")

    # 1) SeaSight → Oceanus
    html = sub_once(html, "<title>探海灵眸 SeaSight · 海漂垃圾智能治理系统</title>",
                    "<title>探海灵眸 Oceanus · 海漂垃圾智能治理系统</title>")
    html = sub_once(html, "SeaSight · 统一深色设计系统", "Oceanus · 统一深色设计系统")
    html = sub_once(html, 'color:var(--cyan)">SeaSight</div>', 'color:var(--cyan)">Oceanus</div>')
    html = sub_once(html, "探海灵眸 SeaSight</div>", "探海灵眸 Oceanus</div>")
    html = sub_once(html, '<span class="brand">SeaSight · 探海灵眸</span>',
                    '<span class="brand">Oceanus · 探海灵眸</span>')

    # 2) 23/23 → 27/27（s10 两处）+ s16 计数器
    html = sub_once(html, 'font-size:26px;font-weight:800">23/23</div>',
                    'font-size:26px;font-weight:800">27/27</div>')
    html = sub_once(html, 'font-size:34px;font-weight:800;margin-top:2px">23/23</div>',
                    'font-size:34px;font-weight:800;margin-top:2px">27/27</div>')
    html = sub_once(html, 'data-count="23">0</span><span class="cap mut">/ 23</span>',
                    'data-count="27">0</span><span class="cap mut">/ 27</span>')

    # 3) 误报抑制 76% → 42–76%（四处）
    # s2 四数卡
    html = sub_once(html, '<span class="kpi num c1" data-count="76">0</span><span class="lbl c1 num" style="font-size:18px">%</span>',
                    '<span class="kpi num c1">42–76</span><span class="lbl c1 num" style="font-size:18px">%</span>')
    # s9 KPI 卡
    html = sub_once(html, '<span class="kpi num gd" style="font-size:52px" data-count="76">0</span>',
                    '<span class="kpi num gd" style="font-size:52px">42–76</span>')
    html = sub_once(
        html,
        "多帧关联确认，过滤光影晃动、海浪泡沫等干扰，误报被实时抑制而非事后人工筛除。",
        "多帧关联确认，过滤光影晃动、海浪泡沫等干扰；实测抑制率区间 42%–76%（非识别精度），"
        "误报被实时抑制而非事后人工筛除。",
    )
    # s10 卡
    html = sub_once(html, 'font-weight:800;margin-top:2px">76%</div>',
                    'font-weight:800;margin-top:2px">42–76%</div>')
    # s10 口径脚注
    html = sub_once(html, "——76% 是时序误报抑制率，不是识别精度；",
                    "——42%–76% 是时序误报抑制率区间，不是识别精度；")
    # s16 计数器 + 脚注
    html = sub_once(html, '"font-size:27px;font-weight:800" data-count="76">0</span><span class="cap mut">%</span>',
                    '"font-size:27px;font-weight:800">42–76</span><span class="cap mut">%</span>')
    html = sub_once(html, "76% 为时序误报抑制率而非识别精度",
                    "42%–76% 为时序误报抑制率区间（非识别精度）")

    # 4) s10 左卡新增证据段
    anchor = ('覆盖状态机全部迁移路径、9 类工具契约的权限与超时约束、异常回滚与幂等性验证。'
              '这不是演示脚本，而是可复跑的测试集。</div>')
    new_block = anchor + (
        '\n      <div class="cap mut" style="margin-top:10px;line-height:1.65">'
        '公开基准独立评测：SC-FloatWaste（400 图 / 1,490 框）监督微调 mAP50 0.514 · '
        '零样本开放词汇 0.116（第三方公开数据集，非现场验证）。<br>'
        '真实世界证据：连江县海渔局访谈完成（记录存档）；5 类核心部件 13 家供应商 '
        '15 份询价（含 2 份盖章报价单）；软件著作权登记申请中。</div>'
    )
    html = sub_once(html, anchor, new_block)

    # 5) s10 平台截图替换（旧登录页截图 → 当前监测大屏条带）
    b64 = base64.b64encode(BANNER.read_bytes()).decode("ascii")
    old_img = re.search(r'<img src="data:image/jpeg;base64,[^"]+" alt="SeaSight 管理平台">', html)
    assert old_img, "未找到旧平台截图"
    html = html.replace(
        old_img.group(0),
        f'<img src="data:image/jpeg;base64,{b64}" alt="Oceanus 治理平台">',
    )

    # 终检：不应残留旧文案
    for bad in ("SeaSight", '"76%"', "data-count=\"76\"", ">23/23<", "/ 23<"):
        assert bad not in html, f"残留：{bad}"

    DST.write_text(html, encoding="utf-8")
    print("[OK] 已生成:", DST.name, f"({DST.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()