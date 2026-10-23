#!/usr/bin/env python3
"""把生图主体调进当集色板，输出透明底 PNG：去背景 → k-means 聚类 → 每个聚类吸到最近的色板色。

为什么要这一步：Seedream 提示词里写 hex 色号不可靠（会冲淡、会串色，既有主体样本曾出现色相串到头发），
所以颜色全部交给后处理；后处理之后，人物和代码画的吉祥物、字块、底图才在同一套色里。

用法：python3 scripts/art_grade.py 生图/raw/c3_a.png 生图/graded/c3_a_graded.png \\
        --palette "INK=#1B2530,朱红=#D8402C,靛蓝=#2B4A8B,草黄=#E6B450,肤=#F7C9A8,白=#FFFFFF,灰绿=#8E9C93" \\
        [--mix 0.9] [--mix-small 0.3] [--k 16] [--tol 16] [--no-holes]

palette 怎么写：
  - 必须含一个白（眼白、高光），否则眼白会被吸成纸色或沙色。
  - 动物 / 有色道具的固有色要加进 palette（例如 棕=#7A5235）；不加，棕色袋熊会被吸成灰黑，脚本会打 ΔE 警告。
  - 同一色板色可以给多个深浅（朱红深=#A8301F）。换集时按当集色板改 --palette，别改脚本。
mix=1 是硬吸附（纯色块，半色调网点会糊成一片）；mix=0 是原图；默认 0.9。
小聚类（面积 < 前景 1%：眼线、嘴、腮红）用 --mix-small（默认 0.3），表情不会被抹成一片 INK。
  深色身体上的深色眼线（?怪 闭眼）常和轮廓线落在同一个大聚类里，小聚类保护管不到：
  给 palette 加一个更深的 INK（例如 INK深=#070D18）（在细线表情样本中这样闭眼、腮红、嘴都保住；默认 --k 已是 16）。
  默认 k=16 是保真与运行成本的折中；仍需看细线、mask与色板是否齐全。

背景识别：从四条边泛洪，和边缘中位色差在 --tol（Lab ΔE）以内、与四边连通的块算背景；
另外，被主体围出来、颜色接近背景的块（面积 > 1500 px，「内部洞」，例如两腿之间）默认也抠掉。
  危险：主体里大片接近背景色的区域（浅色长袍、纸白衬衫、与背景同色系的肤色）也会被当成内部洞抠空。
  **人物半身 / 特写一律加 --no-holes**（10-22 夜实测：背景是浅杏色时，脸和手里近背景色的块被抠成洞，合成后底下的光晕色从脸上透出来，脸变黄，12 张里 6 张出现；加了之后干净）。
  只有「两腿之间要抠」的全身动物才不加。
  内部洞总面积 > 前景 1% 时脚本会警告，并存一张 <out>_mask.png（洋红 = 被当成内部洞抠掉的地方）。
  这时看 mask：抠错了就加 --no-holes（只去掉与四边连通的背景），或者让提示词用主体不会出现的纯色背景。
"""
import argparse
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HOLE_MIN = 1500       # 内部洞最小面积（px），更小的斑点当成主体里的细节
SMALL = 0.01          # 小聚类 / 内部洞警告线：前景面积的 1%
DE_WARN = 20


def die(msg):
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(2)


def parse_palette(s):
    out = {}
    for kv in s.split(","):
        if not kv.strip():
            continue
        if "=" not in kv:
            die(f"--palette 每项要写成 名字=#RRGGBB，这一项不对：{kv.strip()!r}")
        k, v = (x.strip() for x in kv.split("=", 1))
        if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", v):
            die(f"{k} 的色值 {v!r} 不是 6 位 hex（#RRGGBB）")
        out[k] = "#" + v.lstrip("#").upper()
    if not out:
        die("--palette 是空的")
    if not any(min(hex2rgb(v)) >= 240 for v in out.values()):
        print("⚠ palette 里没有白（R、G、B 都 ≥ 240）：眼白、高光会被吸成别的颜色。加一个 白=#FFFFFF", file=sys.stderr)
    return out


def hex2rgb(h): h = h.strip().lstrip("#"); return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
def to_lab(rgb): return cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
def from_lab(lab): return np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB) * 255, 0, 255).astype(np.uint8)


def bg_masks(rgb, tol):
    """返回 (与四边连通的背景, 内部洞)。内部洞 = 颜色接近背景、不碰四边、面积 > HOLE_MIN 的块。"""
    lab = to_lab(rgb)
    edge = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]); bg = np.median(edge, axis=0)
    near = (np.linalg.norm(lab - bg, axis=2) < tol).astype(np.uint8)
    n, lbl, st, _ = cv2.connectedComponentsWithStats(near, connectivity=4)
    border = np.unique(np.concatenate([lbl[0], lbl[-1], lbl[:, 0], lbl[:, -1]]))
    border = border[border != 0]
    outer = np.isin(lbl, border)
    holes_ids = [i for i in np.where(st[:, cv2.CC_STAT_AREA] > HOLE_MIN)[0] if i != 0 and i not in set(border)]
    holes = np.isin(lbl, holes_ids)
    return outer, holes


def grade(src, palette, mix=0.9, k=12, tol=16, seed=0, mix_small=0.3, no_holes=False, mask_out=None):
    from sklearn.cluster import KMeans
    rgb = np.array(Image.open(src).convert("RGB")); lab = to_lab(rgb)
    outer, holes = bg_masks(rgb, tol)
    subject = int((~outer).sum())
    hole_px = int(holes.sum())
    if hole_px and subject:
        share = hole_px / subject
        print(f"  内部洞：{hole_px} px，占前景 {share:.1%}" + ("（--no-holes：保留）" if no_holes else "（已抠掉）"))
        if share > SMALL:
            print(f"⚠ 内部有 {hole_px} px（前景的 {share:.1%}）被当成背景抠掉" + ("" if not no_holes else "的候选，已按 --no-holes 保留")
                  + "。检查 mask 图：抠错了（衣服、身体）就加 --no-holes；该抠（两腿之间的背景）就不用管", file=sys.stderr)
            if mask_out:
                prev = (rgb * .35 + 255 * .65).astype(np.uint8)
                prev[~outer] = rgb[~outer]
                prev[holes] = (255, 0, 255)
                Image.fromarray(prev).save(mask_out); print(f"  mask 预览（洋红 = 内部洞）：{mask_out}")
    remove = outer if no_holes else (outer | holes)
    alpha = cv2.GaussianBlur((~remove).astype(np.float32), (0, 0), 1.2)

    names = list(palette)
    pal = np.array([hex2rgb(h) for h in palette.values()], dtype=np.uint8); pal_lab = to_lab(pal.reshape(-1, 1, 3)).reshape(-1, 3)
    fg = alpha > 0.5; px = lab[fg]
    if len(px) < max(k, 100):
        die(f"前景只有 {len(px)} px（< k={k}）：背景识别把主体也当背景了。调 --tol，或检查提示词有没有要求纯色背景")
    idx = np.random.RandomState(seed).choice(len(px), min(60000, len(px)), replace=False)
    km = KMeans(n_clusters=k, n_init=3, random_state=seed).fit(px[idx]); lbl = km.predict(px); cen = km.cluster_centers_
    d2 = ((cen[:, None, :] - pal_lab[None]) ** 2).sum(2)
    near = np.argmin(d2, axis=1); de = np.sqrt(d2[np.arange(k), near])
    share = np.bincount(lbl, minlength=k) / len(lbl)
    mixes = np.where(share < SMALL, mix_small, mix)

    print(f"  聚类 → 色板（ΔE76；占前景 < {SMALL:.0%} 的小聚类用 mix {mix_small:g}，其余 mix {mix:g}）：")
    for i in np.argsort(-share):
        c_rgb = from_lab(cen[i].reshape(1, 1, 3)).reshape(3)
        flag = "  ⚠" if de[i] > DE_WARN else ""
        print(f"    #{i:<2} {'#%02X%02X%02X' % tuple(c_rgb)}  占 {share[i]:6.1%}  → {names[near[i]]:<6} ΔE {de[i]:5.1f}  mix {mixes[i]:.2g}{flag}")
    for i in np.where(de > DE_WARN)[0]:
        c_rgb = from_lab(cen[i].reshape(1, 1, 3)).reshape(3)
        print(f"⚠ 聚类 #{i}（{'#%02X%02X%02X' % tuple(c_rgb)}，占前景 {share[i]:.1%}）色板里没有近似色，被吸成了 {names[near[i]]}"
              f"（ΔE {de[i]:.0f}）：给 --palette 加当集动物色，或降低 --mix", file=sys.stderr)

    snapped = pal_lab[near][lbl]
    m = mixes[lbl][:, None]
    new = px * (1 - m) + snapped * m
    out = lab.copy(); out[fg] = new
    return Image.fromarray(np.dstack([from_lab(out), (alpha * 255).astype(np.uint8)]), "RGBA")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("out", help="输出路径，必须是 .png（透明底）")
    ap.add_argument("--palette", required=True, help='"名字=#RRGGBB,名字=#RRGGBB,…"，要含一个白')
    ap.add_argument("--mix", type=float, default=0.9)
    ap.add_argument("--mix-small", type=float, default=0.3, help="小聚类（< 前景 1%%）的 mix，默认 0.3；0 = 不吸附")
    ap.add_argument("--k", type=int, default=16); ap.add_argument("--tol", type=float, default=16)
    ap.add_argument("--no-holes", action="store_true", help="只去掉与四边连通的背景，不抠内部洞")
    a = ap.parse_args()
    out = Path(a.out)
    if out.suffix.lower() != ".png":
        die(f"输出要是 .png（透明底存不进 {out.suffix or '无后缀'}）：{out}")
    src = Path(a.src)
    if not src.is_file():
        die(f"找不到源图：{src}")
    try:
        Image.open(src).verify()
    except Exception as e:
        die(f"源图读不了：{src}（{type(e).__name__}: {e}）")
    pal = parse_palette(a.palette)
    out.parent.mkdir(parents=True, exist_ok=True)
    grade(src, pal, a.mix, a.k, a.tol, mix_small=a.mix_small, no_holes=a.no_holes,
          mask_out=out.with_name(out.stem + "_mask.png")).save(out)
    print("saved", out)
