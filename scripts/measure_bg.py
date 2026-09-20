#!/usr/bin/env python3
"""测底图的实测均色与 CIE L*，输出可直接填进 build 脚本的 PAPER 值。

用法：python3 scripts/measure_bg.py 素材/tex_xxx.png

为什么要测：底图是生成的，实际底色和 prompt 里写的标称色**总是有偏差**（实测九集，
偏差 1~4 个 L* 单位）。build 脚本里的 PAPER 必须用实测值，否则 SVG 主体里
用 PAPER 填充的部分（翅膀、纸色描边）会和底图差一点点，纹理线浮出来。

避开右上网点区取样：只统计左半 + 下半。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def lstar(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in rgb)
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    f = y ** (1 / 3) if y > 0.008856 else 7.787 * y + 16 / 116
    return 116 * f - 16


def main() -> int:
    if len(sys.argv) < 2:
        print('用法：python3 scripts/measure_bg.py <底图.png>', file=sys.stderr)
        return 2
    p = Path(sys.argv[1])
    im = np.asarray(Image.open(p).convert('RGB')).astype(float)
    h, w, _ = im.shape
    region = np.concatenate([im[:, :w // 2].reshape(-1, 3), im[h // 2:, :].reshape(-1, 3)])
    m = region.mean(0)
    hexv = '#%02X%02X%02X' % tuple(m.round().astype(int))
    L = lstar(m)
    print(f'{p.name}  {w}×{h}')
    print(f'  实测均色 {hexv}   CIE L* = {L:.1f}')
    if L <= 92:
        print(f'  ✗ L* {L:.1f} ≤ 92，不合 DNA 规则 1（底色 CIE L* > 92）。换更浅的纸重生。')
        return 1
    print(f'  ✓ 合规。把 PAPER 写成 {hexv}（不是 prompt 里那个标称色）。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
