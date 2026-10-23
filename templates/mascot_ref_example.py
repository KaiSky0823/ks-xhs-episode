#!/usr/bin/env python3
"""渲染吉祥物参考图（?怪 + !怪，当集色板，纸色底），给 gen_art.py --image 用。

用法（任何目录都能跑）：
  python3 $KIT/templates/mascot_ref_example.py --paper '#C2F8DC' --ink '#1B2530' --accent '#2B4A8B' -o 第N集-XX/生图/ref
  → <目录>/mascots.html、mascots.png（2160×2880）、mascots_ref.png（裁中间一块缩到 900×600，当参考图）

颜色：--paper = 当集纸色（measure_bg.py 实测值）；--ink = ?怪 身体色和眼睛描边；--accent = !怪 身体色（当集色块色）。
提示词里描述两个角色的颜色名要和这里一致（templates/art_prompt.md 的参考图句）。
吉祥物画法在 templates/mascots.py；换账号：换成自己的角色函数。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mascots as M                              # noqa: E402

SHOT = HERE.parent / "scripts" / "shot.js"


def hexcolor(s):
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", s):
        raise argparse.ArgumentTypeError(f"要写成 #RRGGBB：{s!r}")
    return s.upper()


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--paper", type=hexcolor, required=True, help="当集纸色（measure_bg.py 实测）")
ap.add_argument("--ink", type=hexcolor, required=True, help="?怪 颜色（当集 INK）")
ap.add_argument("--accent", type=hexcolor, required=True, help="!怪 颜色（当集色块色）")
ap.add_argument("-o", "--out", required=True, help="输出目录，例如 第N集-XX/生图/ref")
a = ap.parse_args()

q = M.qm2(40, 40, 1.0, M.Q_EYES, "wide", ink=a.ink, paper=a.paper)                       # ?怪：睁圆的眼睛
e = M.em2(380, 40, 1.0, M.E_EYES, "wide", ink=a.ink, accent=a.accent, paper=a.paper)      # !怪
svg = f'<svg viewBox="0 0 760 520" xmlns="http://www.w3.org/2000/svg" width="760" height="520"><rect width="760" height="520" fill="{a.paper}"/>{q}{e}</svg>'
html = (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;width:1080px;height:1440px;background:{a.paper}}}'
        f'svg{{position:absolute;left:160px;top:400px;width:760px}}</style></head><body>{svg}</body></html>')
out = Path(a.out).resolve()
out.mkdir(parents=True, exist_ok=True)
(out / "mascots.html").write_text(html, encoding="utf8")
subprocess.run(["node", str(SHOT), str(out / "mascots.html"), str(out / "mascots.png")], check=True)
from PIL import Image                             # noqa: E402
Image.open(out / "mascots.png").convert("RGB").crop((200, 700, 2000, 1900)).resize((900, 600)).save(out / "mascots_ref.png")
print("参考图：", out / "mascots_ref.png")
