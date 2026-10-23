import subprocess
exe=r"C:\Users\Liii\AppData\Local\OpenAI\Codex\bin\2e5e00daee91c61d\codex.exe"
p="C:/Users/Liii/Desktop/seahawk/scripts/lj_extract_sections.py"
lines=[
    "from pathlib import Path",
    "",
    "cases = [",
    "    (",
    "        r\'C:\Users\Liii\Desktop\连江县创新创业大赛\源文件\探海灵眸Oceanus_国创路演_动效版.html\',",
    "        \'<section class=\"slide dk\" id=\"s10\"\',",
    "    ),",
    "    (",
    "        r\'C:\Users\Liii\Desktop\连江县创新创业大赛\路演PPT_国奖优化版\探海灵眸Oceanus_路演PPT_国奖版.html\',",
    "        \'<section class=\"slide\" data-label=\"验证证据\">\',",
    "    ),",
    "]",
    "",
    "for path, start_marker in cases:",
    "    f = Path(path)",
    "    s = f.read_text(encoding=\"utf-8\")",
    "    start = s.index(start_marker)",
    "    end = s.index(\"</section>\", start) + len(\"</section>\")",
    "    print(\"=\" * 90)",
    "    print(f.name)",
    "    print(s[start:end])",
]
n=chr(10)
patch="*** Begin Patch"+n+"*** Add File: "+p+n+"".join("+"+ln+n for ln in lines)+"*** End Patch"
r=subprocess.run([exe,"--codex-run-as-apply-patch",patch],capture_output=True,text=True)
print(r.returncode); print(r.stdout); print(r.stderr)