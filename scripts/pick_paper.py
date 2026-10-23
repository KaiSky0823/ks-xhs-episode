#!/usr/bin/env python3
"""挑下一集的纸色：列出「L* > 92、离所有已用纸色 ΔE76 ≥ 阈值」的还没用过的颜色，并告诉你还剩多少空位。

用法：
  python3 scripts/pick_paper.py                      # 默认：ΔE ≥ 8，色度 ≥ 6，列 12 个互相也拉开的候选
  python3 scripts/pick_paper.py --min-de 6 --n 20
  python3 scripts/pick_paper.py --hue 120-200        # 只看色相角 120°~200°（绿到青）的候选

输出每个候选：hex、L*、色度 C*、色相角 h（0 红粉 / 90 黄 / 180 青绿 / 270 蓝紫）、离最近已用纸色的 ΔE 和是哪一集。
拿到 hex 之后：gen_bg.py --paper '#RRGGBB' 出底图（模型只出质感，颜色由 tint_bg.py 落到这个 hex）。

已用纸色从 references/08-视觉规范.md的色板表解析，和 measure_bg.py 同一份。
空位是**有限的**（见运行输出：默认条件下能再放几个，一目了然）；
优先挑合格新色并登记。没有新色时推荐一款色板表中的浅旧纸色，
另换强调色和构图，在当集方案、发布登记中写明复用；measure_bg.py 须显式声明复用。
"""
import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure_bg as mb  # noqa: E402
from tint_bg import srgb2lab  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-de", type=float, default=8, help="离已用纸色的最小 ΔE76（默认 8，同 measure_bg）")
    ap.add_argument("--min-l", type=float, default=92.5, help="L* 下限（默认 92.5，DNA 规则 1 是 > 92）")
    ap.add_argument("--min-chroma", type=float, default=6, help="色度下限（默认 6；太低就是白纸，看不出色相）")
    ap.add_argument("--max-chroma", type=float, default=24, help="色度上限（默认 24，保持浅纸观感；更高就是荧光色，不再是「浅纸」）")
    ap.add_argument("--hue", help="色相角范围 lo-hi，例如 120-200")
    ap.add_argument("--n", type=int, default=12, help="最多列几个（默认 12）")
    ap.add_argument("--palette-md", default=str(mb.PALETTE_MD))
    a = ap.parse_args()
    if a.min_de <= 0 or a.n <= 0:
        ap.error('--min-de 和 --n 必须 > 0')

    try:
        used = mb.used_papers(Path(a.palette_md))
    except Exception as e:
        print(f"✗ 读不了色板表 {a.palette_md}：{e}", file=sys.stderr)
        return 2
    if not used:
        print("✗ 色板表里解析不到已用纸色", file=sys.stderr)
        return 2
    names, labs = [], []
    seen = set()
    for name, hexv, _ in used:
        if hexv in seen:
            continue
        seen.add(hexv)
        names.append(name)
        labs.append(mb.lab(hexv))
    U = np.array(labs)

    g = np.arange(176, 256, 2)
    R, G, B = np.meshgrid(g, g, g, indexing="ij")
    rgb = np.stack([R.ravel(), G.ravel(), B.ravel()], 1)
    lab = srgb2lab(rgb)
    C = np.hypot(lab[:, 1], lab[:, 2])
    H = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360
    m = (lab[:, 0] >= a.min_l) & (lab[:, 0] <= 98.5) & (C >= a.min_chroma) & (C <= a.max_chroma)
    if a.hue:
        lo, hi = (float(x) for x in a.hue.split("-"))
        m &= (H >= lo) & (H <= hi)
    cand, crgb, cC, cH = lab[m], rgb[m], C[m], H[m]
    dist = np.sqrt(((cand[:, None, :] - U[None, :, :]) ** 2).sum(2))
    dmin, near = dist.min(1), dist.argmin(1)
    ok = np.where(dmin >= a.min_de)[0]
    order = ok[np.argsort(-dmin[ok])]

    sel = []                                   # 贪心：从最远的开始，候选之间也要拉开
    for i in order:
        if all(np.linalg.norm(cand[i] - cand[j]) >= a.min_de for j in sel):
            sel.append(i)
    print(f"已用不同纸色 {len(U)} 个。L* ≥ {a.min_l}、色度 {a.min_chroma}~{a.max_chroma}、离已用纸色 ΔE ≥ {a.min_de}"
          f"{'、色相 ' + a.hue if a.hue else ''}：满足的色点 {len(ok)} 个，"
          f"按「互相也 ≥ {a.min_de}」最多还能再放 {len(sel)} 个新纸色。")
    if not sel:
        if a.hue:
            print('当前色相范围没有合格新色；先去掉 --hue 查全部新色，再考虑复用。')
            return 1
        reusable = [(name, hx) for name, hx, _ in used if mb.lstar(tuple(int(hx[j:j + 2], 16) for j in (1, 3, 5))) > 92]
        if not reusable:
            print('没有合格新色，也没有 L* > 92 的已登记旧纸色；停止选色。', file=sys.stderr)
            return 1
        name, hx = reusable[-1]  # 最近登记的合格旧色；仍要按题材核对强调色与构图
        print(f'没有合格新色；可考虑复用 {hx}（{name}），另换强调色和构图，并登记复用。')
        print(f"生成：python3 scripts/gen_bg.py --paper '{hx}' -o 素材/tex_<名>.png")
        print(f"实测：python3 scripts/measure_bg.py 素材/tex_<名>.png --reuse-paper '{hx}' --reuse-reason '写明本集强调色与构图区别'")
        return 0
    print(f"\n{'hex':8} {'L*':>5} {'C*':>5} {'h°':>4}  最近已用（ΔE）")
    for i in sel[:a.n]:
        hx = "#%02X%02X%02X" % tuple(crgb[i])
        print(f"{hx:8} {cand[i][0]:5.1f} {cC[i]:5.1f} {cH[i]:4.0f}  {names[near[i]]}（{dmin[i]:.1f}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
