#!/usr/bin/env python3
"""事后上色：把一张「近白纸面 + 深色网点」的底图，精确换成指定的纸色和网点色。

用法：
  python3 scripts/tint_bg.py 原图.png --paper '#C2F8DC' -o 素材/tex_<名>.png [--dot '#0F4F2C']
  （一般不用单独调：gen_bg.py --paper '#RRGGBB' 会在出图后自动调它）

为什么要有它（2026-10-22 实测）：
  Flash 底图要写「极浅、接近白色」才能 L* > 92，但这样出来的纸**色相基本丢了**（实测 L* 95~96，偏白灰）；
  写出色相的版本又出到 L* ≈ 80，过不了 DNA 规则 1。纸色空位又只剩一小块（pick_paper.py 可查），
  不能靠「碰运气让模型出某个色」。所以改成：**先在 pick_paper.py 里挑好目标色，让模型只负责出质感**
  （纸纤维、折痕、网点），颜色由本脚本落到目标 hex。输出偏差须实测，纸纹和折痕保留情况须看图。

做法（双色映射，只看亮度）：
  亮度 L* → t = (纸面中位 L* − 像素 L*) / (纸面中位 L* − 网点最深 L*)，输出 = 纸色 + t × (网点色 − 纸色)（Lab 空间线性）。
  纸面中位数取去掉右上四分之一后的中位 L*（和 measure_bg 同一取样区）。
  网点色默认 = 纸色色相、L* 20、色度 × 1.6（「比纸面深很多的同色系深色」）；想指定就传 --dot。
  原图的色相被丢弃，所以原图里写什么色都无所谓；但原图的清晰度（拉普拉斯约为 lite 的 71~78%）不会变好。

落盘后自检（任一不过 exit 1）：纸色与目标 ΔE ≤ 2；L* > 92；输出 .png、尺寸与原图一致。
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from measure_bg import de76, paper_color, paper_region  # noqa: E402

MIN_L = 92


def srgb2lab(rgb):
    c = np.asarray(rgb, float) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)
    return np.stack([116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))], -1)


def lab2srgb(lab):
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    inv = lambda t: np.where(t ** 3 > 0.008856, t ** 3, (t - 16 / 116) / 7.787)
    X, Y, Z = inv(fx) * 0.95047, inv(fy), inv(fz) * 1.08883
    lin = np.stack([3.2406 * X - 1.5372 * Y - 0.4986 * Z,
                    -0.9689 * X + 1.8758 * Y + 0.0415 * Z,
                    0.0557 * X - 0.2040 * Y + 1.0570 * Z], -1)
    c = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.clip(lin, 1e-9, None) ** (1 / 2.4) - 0.055)
    return np.clip(c * 255, 0, 255)


def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def _hex(s):
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", s):
        raise argparse.ArgumentTypeError("要写成 #RRGGBB")
    return s.upper()


def tint_array(arr, paper_hex, dot_hex=None):
    """arr：H×W×3 uint8。返回 (上色后的 uint8 数组, 原图纸面中位 L*, 原图网点最深 L*)。"""
    lab = srgb2lab(arr.astype(float))
    Ls = lab[..., 0]
    H, W = Ls.shape
    mask = np.ones((H, W), bool)
    mask[:H // 2, W // 2:] = False                  # 去掉右上四分之一（网点区）
    Lref = float(np.median(Ls[mask]))
    Ldark = float(np.percentile(Ls, 0.5))
    if Lref - Ldark < 30:
        raise SystemExit(f"✗ 原图纸面 L* {Lref:.1f} 和最深处 L* {Ldark:.1f} 差不到 30：没有明显的深色网点，没法做双色映射。"
                         f"\n  检查原图是不是出灰了或网点太淡。")
    p = srgb2lab(hex2rgb(paper_hex)[None])[0]
    if dot_hex:
        d = srgb2lab(hex2rgb(dot_hex)[None])[0]
    else:
        d = np.array([20.0, p[1] * 1.6, p[2] * 1.6])
    t = np.clip((Lref - Ls) / (Lref - Ldark), -0.2, 1.0)[..., None]
    out = p[None, None, :] + t * (d - p)[None, None, :]
    return lab2srgb(out).round().astype(np.uint8), Lref, Ldark


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="原底图（近白纸面 + 深色网点，右上角）")
    ap.add_argument("--paper", required=True, type=_hex, help="目标纸色 #RRGGBB（先用 pick_paper.py 挑）")
    ap.add_argument("--dot", type=_hex, help="目标网点色 #RRGGBB（默认：同色相、L* 20、色度 ×1.6）")
    ap.add_argument("-o", "--out", required=True, help="输出 .png")
    a = ap.parse_args()

    src, out = Path(a.src), Path(a.out)
    if out.suffix.lower() != ".png":
        print(f"✗ 输出必须是 .png（当前 {out.suffix}）", file=sys.stderr)
        return 2
    try:
        arr = np.asarray(Image.open(src).convert("RGB"))
    except Exception as e:
        print(f"✗ 读不了原图 {src}：{type(e).__name__}: {e}", file=sys.stderr)
        return 2
    res, Lref, Ldark = tint_array(arr, a.paper, a.dot)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(res).save(out)

    hexv, L = paper_color(res)
    de = de76(hexv, a.paper)
    print(f"✓ {out}  {res.shape[1]}×{res.shape[0]}")
    print(f"  原图纸面 L* {Lref:.1f}，最深 L* {Ldark:.1f}；目标 {a.paper} → 实测 {hexv}  L* {L:.1f}  ΔE {de:.1f}")
    bad = []
    if de > 2:
        bad.append(f"实测纸色离目标 ΔE {de:.1f} > 2")
    if L <= MIN_L:
        bad.append(f"目标纸色 L* {L:.1f} ≤ {MIN_L}（DNA 规则 1），换一个更浅的")
    if bad:
        print("✗ " + "；".join(bad), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
