#!/usr/bin/env python3
"""测底图的实测均色与 CIE L*，并对已用纸色算 ΔE76，输出可直接填进 build 脚本的 PAPER 值。

用法：python3 scripts/measure_bg.py 素材/tex_xxx.png [--min-de 8] [--ep N]

为什么要测：底图是生成的，实际底色和 prompt 里写的标称色**总是有偏差**（生成时会冲淡色号或产生色偏）。build 脚本里的 PAPER 必须用实测值，
否则 SVG 主体里用 PAPER 填充的部分（翅膀、纸色描边）会和底图差一点点，纹理线浮出来。

取样区：去掉右上四分之一（网点区），其余四分之三每个像素算一次。

三道检查（任一不过 exit 1）：
  ① L* > 92（DNA 规则 1）
  ② 新色对已用纸色的最小 ΔE76 ≥ --min-de（默认 8）；复用须显式给
     --reuse-paper 已登记色号和 --reuse-reason，且实测色须接近该色号（ΔE ≤ 4）。
     两条通道都必须能读取已用色板；复测已登记的底图时用 --ep N 排除那一集自己。
  ③ 文件能读、是图片（读不了 exit 2）
另外打印网点团最左 CSS x（顶部 30% 高度里，暗像素 < 128 占比 > 2% 的最左一列，换算成 1080 宽画布）。
答案图标题色块右端不要越过这个 x。
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

KIT = Path(__file__).resolve().parents[1]
PALETTE_MD = KIT / 'references' / '08-视觉规范.md'


def lstar(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(x)) for x in rgb)
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    f = y ** (1 / 3) if y > 0.008856 else 7.787 * y + 16 / 116
    return 116 * f - 16


def lab(hexv):
    """#RRGGBB → CIELAB（D65）。"""
    h = hexv.lstrip('#')
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))


def de76(a, b):
    return sum((x - y) ** 2 for x, y in zip(lab(a), lab(b))) ** .5


def paper_region(im):
    """im: H×W×3 数组。返回去掉右上四分之一（网点区）后的像素，每个像素只算一次。"""
    h, w = im.shape[:2]
    mask = np.ones((h, w), bool)
    mask[:h // 2, w // 2:] = False
    return im[mask]


def paper_color(im):
    """返回 (hex, L*)。"""
    m = paper_region(im.astype(float)).mean(0)
    return '#%02X%02X%02X' % tuple(m.round().astype(int)), lstar(m)


def dot_left_css(im, canvas_w=1080):
    """网点团最左的 CSS x：顶部 30% 高度里，暗像素（灰度 < 128）占比 > 2% 的最左一列。找不到返回 None。"""
    h, w = im.shape[:2]
    g = np.asarray(Image.fromarray(im.astype(np.uint8)).convert('L'))[: int(h * .3)]
    cols = np.where((g < 128).mean(0) > .02)[0]
    return None if len(cols) == 0 else round(cols[0] * canvas_w / w)


def used_papers(md=PALETTE_MD):
    """从 08「已验证可用的其它色板」表解析纸色；名称不依赖「系」后缀。"""
    out, in_table = [], False
    for line in Path(md).read_text(encoding='utf-8').splitlines():
        if line.startswith('### 已验证可用的其它色板'):
            in_table = True
            continue
        if in_table and line.startswith('## '):
            in_table = False
        if not in_table or not line.startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 7:
            continue
        m = re.search(r'#[0-9A-Fa-f]{6}', cells[1])
        if not m:
            continue
        name, used_in = cells[0], cells[-1]
        eps = [(e.start(), e.group(1)) for e in re.finditer(r'第\s*(\d+)\s*集', used_in)]
        first = eps[0][1] if eps else '?'
        out.append((f'第 {first} 集 {name}·标称', m.group(0).upper(), first))
        for t in re.finditer(r'实测\s*`?(#[0-9A-Fa-f]{6})', used_in):
            if re.search(r'首张|首次', used_in[max(0, t.start() - 8):t.start()]):
                continue
            ep = ([e for pos, e in eps if pos < t.start()] or [first])[-1]
            out.append((f'第 {ep} 集 {name}·实测', t.group(1).upper(), ep))
    seen = set()
    return [u for u in out if not (u[1] in seen or seen.add(u[1]))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('image', help='底图 PNG')
    ap.add_argument('--min-de', type=float, default=8.0,
                    help='新色对已用纸色的最小 ΔE76（默认 8；不可设为 0 来跳过）')
    ap.add_argument('--reuse-paper', help='明确复用的已登记纸色 #RRGGBB；只豁免新色 ΔE 下限')
    ap.add_argument('--reuse-reason', help='复用理由：本集采用的不同强调色和构图，写入当集方案')
    ap.add_argument('--ep', help='当集集数：复测已登记的底图时，排除色板表里这一集自己的纸色')
    ap.add_argument('--palette-md', default=str(PALETTE_MD), help='色板表所在文件（默认 references/08-视觉规范.md）')
    a = ap.parse_args()
    if a.min_de <= 0 or (a.reuse_paper and not a.reuse_reason) or (a.reuse_reason and not a.reuse_paper):
        ap.error('--min-de 必须 > 0；复用必须同时填写 --reuse-paper 与 --reuse-reason')

    p = Path(a.image)
    if not p.is_file():
        print(f'✗ 找不到底图：{p}', file=sys.stderr)
        return 2
    try:
        im = np.asarray(Image.open(p).convert('RGB'))
    except Exception as e:
        print(f'✗ 读不了这张图：{p}\n  {type(e).__name__}: {e}', file=sys.stderr)
        return 2
    h, w = im.shape[:2]
    hexv, L = paper_color(im)
    x = dot_left_css(im)
    print(f'{p.name}  {w}×{h}')
    print(f'  实测均色 {hexv}   CIE L* = {L:.1f}')
    print(f'  网点团最左 CSS x = {x if x is not None else "（没找到暗网点）"}   答案图标题色块右端别越过它')
    bad = False
    if L <= 92:
        print(f'  ✗ L* {L:.1f} ≤ 92，不合 DNA 规则 1（底色 CIE L* > 92）。提示词写「极浅、接近白色」重生。')
        bad = True

    try:
        all_used = used_papers(a.palette_md)
    except (OSError, UnicodeError) as e:
        print(f'✗ 读不了色板表 {a.palette_md}：{e}', file=sys.stderr)
        return 2
    if not all_used:
        print(f'✗ 在 {a.palette_md} 里解析不到任何已用纸色（表格式变了？）。', file=sys.stderr)
        return 2
    used = [u for u in all_used if u[2] != a.ep]
    if not used:
        print('✗ 排除当集后没有可比较的历史纸色。', file=sys.stderr)
        return 2
    near = sorted((de76(hexv, v), k, v) for k, v, _ in used)
    print(f'  对已用纸色（{len(used)} 个，标称 + 实测）的 ΔE76，最近 3 个：')
    for d, k, v in near[:3]:
        print(f'    ΔE {d:5.1f}  {v}  {k}')
    d0, k0, _ = near[0]
    if a.reuse_paper:
        target = a.reuse_paper.upper()
        if not re.fullmatch(r'#[0-9A-F]{6}', target) or target not in {v for _, v, _ in all_used}:
            print(f'  ✗ 复用目标 {target} 不是已登记的纸色。')
            bad = True
        elif lstar(tuple(int(target[j:j + 2], 16) for j in (1, 3, 5))) <= 92 or de76(hexv, target) > 4:
            print(f'  ✗ 复用目标 {target} 不够亮，或实测纸色与目标 ΔE {de76(hexv, target):.1f} > 4。')
            bad = True
        else:
            print(f'  ✓ 显式复用 {target}；理由：{a.reuse_reason}。当集方案和发布色板表登记，另换强调色与构图。')
    elif d0 < a.min_de:
        print(f'  ✗ 最小 ΔE {d0:.1f} < {a.min_de:g}：贴近{k0.split("·")[0]}，重生。'
              + ('（ΔE < 1 像是在复测已登记的底图：加 --ep <那一集的集数>）' if d0 < 1 else ''))
        bad = True
    if bad:
        return 1
    print(f'  ✓ 合规。把 PAPER 写成 {hexv}（不是 prompt 里那个标称色）。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
