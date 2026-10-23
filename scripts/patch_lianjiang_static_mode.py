# -*- coding: utf-8 -*-
"""为路演 HTML 增加 static=1 静态导出模式（供 PPT 导出渲染）。

背景：无头浏览器下 rAF（计数器动画）不推进，导出页会停在 0；
static=1 时直接把计数器/进度条置为终值，并跳过导航浮层。
"""
from __future__ import annotations

from pathlib import Path

F = Path(r"C:\Users\Liii\Desktop\连江县创新创业大赛\源文件\探海灵眸Oceanus_国创路演_动效版.html")


def sub_once(src: str, old: str, new: str) -> str:
    n = src.count(old)
    assert n == 1, f"目标出现 {n} 次（期望 1）：{old[:80]!r}"
    return src.replace(old, new)


def main() -> None:
    html = F.read_text(encoding="utf-8")

    html = sub_once(
        html,
        "  var idx=0, N=slides.length;",
        "  var idx=0, N=slides.length;\n"
        "  /* static=1：静态导出模式（PPT 导出渲染用；无头环境下 rAF 不推进） */\n"
        "  var STATIC=location.search.indexOf('static=1')>=0;",
    )

    html = sub_once(
        html,
        "    navShow(3100);\n"
        "    /* fire animations */\n"
        "    setTimeout(function(){ sl.querySelectorAll('[data-count]').forEach(countUp); },340);\n"
        "    setTimeout(function(){ sl.querySelectorAll('.bar').forEach(function(b){ b.style.width=getComputedStyle(b).getPropertyValue('--w'); }); },380);\n"
        "    if(sl.id==='s8') setTimeout(smPlay,520);",
        "    if(!STATIC) navShow(3100);\n"
        "    /* fire animations */\n"
        "    if(STATIC){\n"
        "      sl.querySelectorAll('[data-count]').forEach(function(e){\n"
        "        var to=parseFloat(e.dataset.count),dec=parseInt(e.dataset.dec||'0',10),pre=e.dataset.prefix||'';\n"
        "        e.textContent=pre+(dec?to.toFixed(dec):Math.round(to).toLocaleString('en-US'));\n"
        "      });\n"
        "      sl.querySelectorAll('.bar').forEach(function(b){ b.style.transition='none'; b.style.width=getComputedStyle(b).getPropertyValue('--w'); });\n"
        "    } else {\n"
        "      setTimeout(function(){ sl.querySelectorAll('[data-count]').forEach(countUp); },340);\n"
        "      setTimeout(function(){ sl.querySelectorAll('.bar').forEach(function(b){ b.style.width=getComputedStyle(b).getPropertyValue('--w'); }); },380);\n"
        "    }\n"
        "    if(sl.id==='s8') setTimeout(smPlay,STATIC?300:520);",
    )

    F.write_text(html, encoding="utf-8")
    print("[OK] static 模式已注入")


if __name__ == "__main__":
    main()