#!/usr/bin/env python3
"""账号吉祥物 ?怪 / !怪 的 SVG 画法（第 33~37 集同一套），颜色全部是参数，不依赖任何一集的目录。

  ?怪 = qm2(...)：问号身体 + 圆点 + 两条腿。身体色默认 = ink
  !怪 = em2(...)：感叹号身体 + 圆点 + 两条腿。身体色默认 = accent（当集色块色，可替换）
  eyes(...)：两只眼睛，mode 见 EYE_MODES

坐标系：每个角色在自己的 0~400 × 0~480 局部坐标里画，(tx, ty) 平移、s 缩放。
脚底中心：?怪 Q_FEET=(196, 464)，!怪 E_FEET=(200, 454)。默认眼睛位置 Q_EYES / E_EYES。
换账号：换成你自己的角色函数，保持「颜色是参数」这一条。
来源：账号原有吉祥物绘制函数；保持既有几何结构不变，颜色作为参数传入。
"""

Q_FEET, E_FEET = (196, 464), (200, 454)
Q_EYES = [(158, 126), (222, 122)]
E_EYES = [(178, 152), (234, 152)]
EYE_MODES = ('open', 'wide', 'stern', 'happy', 'down', 'up', 'side', 'sideL', 'closed', 'squint')


def eyes(pts, mode, *, ink, paper):
    """眼白固定 #fff；描边和瞳孔用 ink；闭眼 / 笑眼 / 眯眼的线用 paper（画在深色身体上）。"""
    out = []
    for idx, (x, y) in enumerate(pts):
        if mode == 'stern':
            out.append(f'<circle cx="{x}" cy="{y}" r="28" fill="#fff" stroke="{ink}" stroke-width="3.4"/><circle cx="{x}" cy="{y+4}" r="10.5" fill="{ink}"/>')
            sg = 1 if idx == 0 else -1
            out.append(f'<path d="M{x-24*sg} {y-44} L{x+16*sg} {y-30}" stroke="{paper}" stroke-width="9" stroke-linecap="round"/>')
        elif mode == 'happy':
            out.append(f'<path d="M{x-20} {y+6} Q{x} {y-12} {x+20} {y+6}" stroke="{paper}" stroke-width="8" fill="none" stroke-linecap="round"/>')
        elif mode == 'wide':
            out.append(f'<circle cx="{x}" cy="{y}" r="31" fill="#fff" stroke="{ink}" stroke-width="3.4"/><circle cx="{x}" cy="{y-2}" r="6" fill="{ink}"/>')
        elif mode == 'down':
            out.append(f'<circle cx="{x}" cy="{y}" r="28" fill="#fff" stroke="{ink}" stroke-width="3.4"/><circle cx="{x-2}" cy="{y+14}" r="10.5" fill="{ink}"/>')
        elif mode == 'up':
            out.append(f'<circle cx="{x}" cy="{y}" r="28" fill="#fff" stroke="{ink}" stroke-width="3.4"/><circle cx="{x-2}" cy="{y-14}" r="10.5" fill="{ink}"/>')
        elif mode == 'side':
            out.append(f'<circle cx="{x}" cy="{y}" r="28" fill="#fff" stroke="{ink}" stroke-width="3.4"/><circle cx="{x+14}" cy="{y+3}" r="10.5" fill="{ink}"/>')
        elif mode == 'sideL':
            out.append(f'<circle cx="{x}" cy="{y}" r="28" fill="#fff" stroke="{ink}" stroke-width="3.4"/><circle cx="{x-14}" cy="{y+3}" r="10.5" fill="{ink}"/>')
        elif mode == 'closed':
            out.append(f'<path d="M{x-19} {y-2} Q{x} {y+12} {x+19} {y-2}" stroke="{paper}" stroke-width="8" fill="none" stroke-linecap="round"/>')
        elif mode == 'squint':
            out.append(f'<path d="M{x-20} {y-6} L{x+20} {y+4}" stroke="{paper}" stroke-width="8" stroke-linecap="round"/>')
        else:   # 'open'：带高光
            out.append(f'<circle cx="{x}" cy="{y}" r="28" fill="#fff" stroke="{ink}" stroke-width="3.4"/><circle cx="{x-5}" cy="{y+6}" r="10.5" fill="{ink}"/><circle cx="{x-9}" cy="{y+2}" r="3.4" fill="#fff"/>')
    return ''.join(out)


def qm2(tx, ty, s, eye_pts=Q_EYES, mode='open', *, ink, paper, color=None, extra='', legs=True):
    """?怪。color = 身体色（默认 ink）；extra = 额外 SVG（嘴、腮红、道具），画在局部坐标里。"""
    color = color or ink
    lg = (f'<g stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round"><path d="M176 378 L166 442"/><path d="M218 378 L230 442"/></g>'
          f'<g fill="{color}"><ellipse cx="154" cy="452" rx="28" ry="12"/><ellipse cx="242" cy="452" rx="28" ry="12"/></g>') if legs else ''
    return (f'<g transform="translate({tx:.1f},{ty:.1f}) scale({s})">{lg}'
            f'<path d="M116 148 C 116 76, 258 76, 258 150 C 258 208, 196 218, 196 288" fill="none" stroke="{color}" stroke-width="68" stroke-linecap="round"/>'
            f'<circle cx="196" cy="352" r="35" fill="{color}"/>{eyes(eye_pts, mode, ink=ink, paper=paper)}{extra}</g>')


def em2(tx, ty, s, eye_pts=E_EYES, mode='open', *, ink, accent, paper, color=None, extra='', legs=True, pop=False, halo=None):
    """!怪。color = 身体色（默认 accent）；pop=True 一只脚向后翘起；halo = 身体外描边色（叠在别的东西上时用）。"""
    color = color or accent
    if pop:   # 一只脚向后翘起（亲吻时的经典小动作）
        lg = (f'<g stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round"><path d="M180 384 L172 432"/><path d="M220 384 L262 410"/></g>'
              f'<g fill="{color}"><ellipse cx="160" cy="442" rx="27" ry="12"/><ellipse cx="280" cy="418" rx="26" ry="11" transform="rotate(24 280 418)"/></g>')
    elif legs:
        lg = (f'<g stroke="{color}" stroke-width="12" fill="none" stroke-linecap="round"><path d="M180 384 L172 432"/><path d="M220 384 L228 432"/></g>'
              f'<g fill="{color}"><ellipse cx="160" cy="442" rx="27" ry="12"/><ellipse cx="240" cy="442" rx="27" ry="12"/></g>')
    else:
        lg = ''
    return (f'<g transform="translate({tx:.1f},{ty:.1f}) scale({s})">{lg}'
            f'<path d="M158 104 C 158 86, 242 86, 242 104 L 224 288 C 224 302, 176 302, 176 288 Z" fill="{color}" stroke="{halo}" stroke-width="{7 if halo else 0}" paint-order="stroke"/>'
            f'<circle cx="200" cy="352" r="36" fill="{color}"/>{eyes(eye_pts, mode, ink=ink, paper=paper)}{extra}</g>')
