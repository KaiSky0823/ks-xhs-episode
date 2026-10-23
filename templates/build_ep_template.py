#!/usr/bin/env python3
"""一集四张图的骨架 —— 每集复制一份到当集目录改，别改这个模板本身。

    cp $KIT/templates/build_ep_template.py 第N集-XX/build_epN.py      # KIT = 本 skill 目录

为什么不做成配置驱动的通用生成器：cover/answer 的版式是固定的，但 diagram 和 egg
每集都要按内容重新构图（示例的「两只鸡尾对尾」换个选题就完全不适用）。
强行抽象会变成一个没人看得懂的模板引擎。每集一个脚本、几何常量写在注释里，
是目前最省事也最不容易错的做法。

改之前先读 references/08-视觉规范.md。这里的常量都是它的实例化，不是可以随便调的旋钮。

★ 几何常量必须是算出来的，不是试出来的 ★
每个 left/top 旁边写清楚它从哪来。示例的图示改了六版，前三版都是拍脑袋调数字，
一版比一版糟 —— 直到把 rect 量出来才找到真正的原因。
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / '素材'
# 生成的模板脚本如果被 import，不应在 skill 根目录意外创建空 素材/。

# ── 当集配置：只改这一段 ─────────────────────────────────
#
# 底图：同一集四张图共用一张（series 感来自纸纹/网点/污渍完全一致）。
#       换色板才生新的，见 DNA §7 和 scripts/gen_bg.py。
BG = OUT / 'tex_<当集>.png'

# 底图自检 —— 因为实测出过事：示例的底图绕过了 gen_bg.py，
# 落盘是个「名字叫 .png 的 JPEG」，gen_bg.py 的魔数自验根本没机会跑。
# 光靠「记得用 gen_bg.py」这条纪律拦不住，所以在这儿再设一道闸。
# JPEG 会在纸纹/网点这种高频内容上出块状伪影（DNA §7）。
def check_bg(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f'✗ 找不到底图：{path}\n  先改上面的 BG 文件名，再用 scripts/gen_bg.py 生成并 measure_bg.py 实测。')
    head = path.read_bytes()[:8]
    if head != b'\x89PNG\r\n\x1a\n':
        raise SystemExit(
            f'✗ 底图不是真 PNG：{path}\n'
            f'  魔数 = {head.hex()}（PNG 应为 89504e470d0a1a0a，ffd8ff 开头是 JPEG）\n'
            f'  多半是绕过了 scripts/gen_bg.py 直接生的 —— 用它重生一张。')
    from PIL import Image
    w, h = Image.open(path).size
    if abs(w / h - 0.75) > 1e-6:
        raise SystemExit(f'✗ 底图比例 {w}×{h} = {w/h:.4f} ≠ 0.75：'
                         f'{path}\n  background:cover 会居中裁切，右上角的网点会被裁出画面且不报错。')
    if w < 2160:
        raise SystemExit(f'✗ 底图 {w}×{h} 小于物理像素 2160×2880：{path}\n'
                         f'  放大 1.286× 实测高频细节只剩 38%。')

check_bg(BG)

# 色板：从 DNA §1 的「已验证可用的其它色板」里取，集与集之间轮换。
# PAPER 用【底图实测均色】，不是色板标称值 —— 差一点点，SVG 的纹线就会浮起来。
#   python3 $KIT/scripts/measure_bg.py 素材/tex_xxx.png      （用它输出的 hex；别用整图均值，会把网点算进去）
INK, ACCENT, ACCENT2, PAPER = '#1C1A17', '#C8322A', '#1B4D8F', '#FBF4E4'

# 主角：生物 / 人物走生图（references/12，放进下面的 art_frame()），几何 / 图示走 SVG。
# SVG 颜色跟着当集色板走，位置像素级可控；画法见 08-视觉规范.md §6。同一集里跨图复用同一个 SVG，这是 series 感的来源。
def load_svg(name: str) -> str:
    """读当集 SVG。缺文件时给可操作的报错，而不是裸 traceback。

    占位文件在 templates/svg示例/主角占位.svg —— 复制一份到 素材/svg/ 就能先跑通流程，
    之后换成你自己的角色（画法见 08-视觉规范.md §6）。
    """
    f = OUT / 'svg' / name
    if not f.exists():
        raise SystemExit(
            f'✗ 找不到 SVG：{f}\n'
            f'  这一集的角色 / 图示零件要自己画，放到 {OUT / "svg"}/ 下。\n'
            f'  想先跑通流程：\n'
            f'    mkdir -p "{OUT / "svg"}"\n'
            f'    cp <skill>/templates/svg示例/主角占位.svg "{f}"\n'
            f'  画法见 references/08-视觉规范.md §6（强调色必须落在主体上）。')
    t = f.read_text(encoding='utf-8')
    # 占位 SVG 里的色标占位符替换成当集色板
    return (t.replace('__INK__', INK).replace('__PAPER__', PAPER)
             .replace('__ACCENT__', ACCENT))


HERO = load_svg('<主角>.svg')      # ← 改成你的文件名，例如 'M_蚊子.svg'

# 生图主体（可选）：art_grade.py 出的透明底 PNG。代码主角 / 纯图示卡设 None；需要主体生图时显式填写 graded 结果路径。
ART = None                           # 例：HERE / '生图' / 'graded' / '<名字>_graded.png'

# 封面生图主体（可选，08 §4b「生图封面」，按题可选版）：有就用生图封面布局；没有就设 None，封面保持四段式 + SVG 主角。
# 生图封面布局：大字两行在上、大框在中、吉祥物站框下沿外两角、底线一行小字；尺寸规格见 08 §4b。
COVER_ART = None                     # 例：HERE / '生图' / 'graded' / '<名字>_graded.png'
COVER_FIT = 'face'                   # 封面框里的构图档，见 art_frame() 的 fit
COVER_EYES = ('side', 'wide')        # ?怪 / !怪 的代码眼型（templates/mascots.py 的 EYE_MODES），眼睛朝框里看；不需吉祥物时 COVER_EYES=None

# 封面生图版要用 templates/mascots.py 画吉祥物。脚本复制到当集目录后靠 $KIT（本 skill 目录）找它。
KIT = Path(os.environ.get('KIT') or Path.home() / '.claude' / 'skills' / 'ks-xhs-episode')


# ── 生图主体放进框（08 §7b、12 §七）────────────────────────
def paper_light(paper: str, white: float = 0.65) -> str:
    """框内底色 = 纸色与白按 white 比例混合（sRGB 逐通道）：c' = c + (255 - c) × white。默认 0.65 为一种已测试的浅化值，可根据当集视觉目标调整。"""
    rgb = [int(paper.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    return '#%02X%02X%02X' % tuple(round(c + (255 - c) * white) for c in rgb)


FRAME_BW, FRAME_RX, FRAME_SHADOW = 10, 26, 14   # 描边 10 / 圆角 26 / 下右硬阴影 14（08 §7b）


def _check_png(png):
    if not Path(png).exists():
        raise SystemExit(f'✗ 生图主体不存在：{png}\n  先跑 scripts/gen_art.py 和 scripts/art_grade.py；不用生图就把 ART / COVER_ART 设成 None')


def alpha_box(png):
    """原图里主体的内容带 (x0, y0, x1, y1)：alpha > 40 的外框（和 make_cover_C.py 同一个阈值）。"""
    from PIL import Image
    box = Image.open(png).convert('RGBA').getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox()
    if not box:
        raise SystemExit(f'✗ {png} 整张是透明的：art_grade.py 把主体也抠掉了，先看它的 *_mask.png')
    return box


def outline_css(color: str, px: float = 7) -> str:
    """纸色外描边（08 §5b「同色剪影必须描边分离」的同一个写法，blur 必须为 0）。"""
    return (f'filter: drop-shadow({px}px 0 0 {color}) drop-shadow(-{px}px 0 0 {color}) '
            f'drop-shadow(0 {px}px 0 {color}) drop-shadow(0 -{px}px 0 {color});')


def art_frame(png: Path, x: float, y: float, w: float, h: float, *, fit: str = 'face', content_box=None,
              focus: float = 0.41, bleed: float = None, scale: float = 1.0, foot_gap: float = 34,
              pad: float = 29, trim: bool = False, scene: str = '', outline: str = None, overlay: str = ''):
    """生图主体放进圆角框，返回 (html, pt)。x/y/w/h 是框外沿的画布坐标（CSS px，含描边）。

    fit = 构图档（和 templates/art_prompt.md ③ 的构图五选一一一对应）：
      'face'    人物半身（默认）：主体宽 = 框内宽 × scale，原图高度的 focus 处落在框中线（08 §7b：0.40~0.42）。
                ★ focus 是按「人脸在原图上部、半身像」设计的 ★：人脸以外的东西（肚脐、马桶、罐口）落不到中线附近，
                别拿它摆非人脸主体，改用下面几档。给了 bleed 就改成「底边超出框内下沿 bleed px」。
                trim=True 先裁到内容带再算宽度和 focus：主体更大；同一个 focus 数值在裁切前后不等价，出图后看人脸位置再调。
                两种都保证原图矩形底边落在框外（被框裁掉），按 focus 算出来底边会露出时自动下移并警告。
      'waist'   人物到腰（要露出腰腹或手里物件）：不用 focus。按内容带缩放，让「内容顶 → 原图底边」装进框
                （上留 pad，底边超出框内下沿 bleed，默认 24px）；内容带左右居中。
      'full'    全身（动物、昆虫、吉祥物、坐着或走路的人）：内容带缩进框内（左右 pad），脚踩框内、离框内下沿 foot_gap。
      'object'  物件静物：内容带整件放进框里，上下左右都留 pad，居中。
      'closeup' 局部特写（手、脚、物件一角）：内容带铺满框（按长边裁），居中；原图被裁断的那条边一定落在框外。
    content_box=(x0, y0, x1, y1)：原图像素里实测的内容带；不给就用 alpha_box() 自动量（waist / full / object / closeup 用）。
      旧写法「只传 content_box、不传 fit」照旧按 'full' 摆。
    scene：场景层（框内坐标的 HTML 或绝对定位的 SVG），画在主体下面、纸纹下面。夜空、水下、泳池、厕所、道路
      这类环境由代码画在这里，生图只出主体（12 §一：场景走代码）。深色场景铺满框时，框内底色由它决定（08 §7b 例外）。
    outline：给主体加外描边的颜色（一般传 PAPER）。深色主体放在深色场景上必须加，否则糊成一团（08 §5b）。
    纸纹：同一张底图按画布坐标对齐后 multiply 0.45，框内外纹理连续。
    overlay：标注 / 箭头层（框内坐标，HTML 或绝对定位的 SVG），放在纹理之上、不参与 multiply。
    pt(ix, iy)：原图像素 → 画布坐标，画框外的箭头指向主体时用（先在原图里量目标点）。
    """
    from PIL import Image
    _check_png(png)
    iw0, ih0 = Image.open(png).size
    bw = FRAME_BW
    fw, fh = w - 2 * bw, h - 2 * bw                      # 框内尺寸
    if content_box is not None and fit == 'face':
        fit = 'full'                                      # 兼容旧调用
    if fit == 'face':
        # trim=True：先按 alpha_box 裁到内容带再算宽度和 focus；默认按整张原图算
        x0, y0, x1, y1 = alpha_box(png) if trim else (0, 0, iw0, ih0)
        cw, ch = x1 - x0, y1 - y0
        s = fw * scale / cw
        left = (fw - cw * s) / 2 - x0 * s
        top = (fh - y1 * s + bleed) if bleed is not None else (fh / 2 - focus * ch * s - y0 * s)
        if top + y1 * s < fh + 2:
            print(f'⚠ art_frame：按 focus={focus} 放，主体底边会露在框里，已下移到框外（主体整体下移 '
                  f'{fh + 2 - top - y1 * s:.0f}px）', file=sys.stderr)
            top = fh + 2 - y1 * s
    elif fit in ('waist', 'full', 'object', 'closeup'):
        x0, y0, x1, y1 = content_box if content_box is not None else alpha_box(png)
        cw, ch = x1 - x0, y1 - y0
        if fit == 'waist':
            b = 24 if bleed is None else bleed
            s = min(fw * scale / cw, (fh - pad + b) / (ih0 - y0))
            top = fh + b - ih0 * s
        elif fit == 'full':
            s = min((fw - 2 * pad) / cw, (fh - pad - foot_gap) / ch) * scale
            top = fh - foot_gap - y1 * s
        elif fit == 'object':
            s = min((fw - 2 * pad) / cw, (fh - 2 * pad) / ch) * scale
            top = (fh - ch * s) / 2 - y0 * s
        else:   # closeup
            s = max(fw / cw, fh / ch) * scale
            top = (fh - ch * s) / 2 - y0 * s
        left = (fw - cw * s) / 2 - x0 * s
    else:
        raise SystemExit(f"✗ art_frame：fit 只能是 face / waist / full / object / closeup，收到 {fit!r}")
    sc = f'<div class="scene" style="position:absolute; inset:0;">{scene}</div>' if scene else ''
    ol = outline_css(outline) if outline else ''
    html = (f'<div class="frame" style="position:absolute; left:{x}px; top:{y}px; width:{w}px; height:{h}px; '
            f'border:{bw}px solid {INK}; border-radius:{FRAME_RX}px; box-shadow:{FRAME_SHADOW}px {FRAME_SHADOW}px 0 {INK}; '
            f'background:{paper_light(PAPER)}; overflow:hidden;">{sc}'
            f'<img class="art" src="file://{Path(png).resolve()}" style="position:absolute; left:{left:.1f}px; top:{top:.1f}px; width:{iw0 * s:.1f}px; {ol}">'
            f'<div class="tex" style="position:absolute; inset:0; background:url(\'file://{BG}\') no-repeat; '
            f'background-size:1080px 1440px; background-position:-{x + bw}px -{y + bw}px; '
            f'mix-blend-mode:multiply; opacity:.45; pointer-events:none;"></div>'
            f'<div class="ann" style="position:absolute; inset:0;">{overlay}</div></div>')

    def pt(ix, iy):
        return x + bw + left + ix * s, y + bw + top + iy * s
    return html, pt


def art_sprite(png: Path, x: float, y: float, w: float, *, outline: str = None):
    """生图主体缩小复用，不带框（路径图起点的小虫、彩蛋里给它戴帽子），返回 (html, pt)。

    x / y / w：主体内容带（alpha_box 量出的外框）左上角的画布坐标和宽度，CSS px。
    纸纹：同 art_frame，底图按画布坐标对齐后 multiply 0.45，只作用在主体的不透明部分（用主体自己的 alpha 当遮罩），
      所以周围的纸面不会被叠深。遮罩必须内联成 data URI：file:// 的 mask-image 在 Chrome 里加载失败且不报错，
      纸纹层会整个消失（2026-10-22 试做实测，像素差 0）。
    outline：同 art_frame，叠在深色块或别的角色上时传 PAPER。
    pt(ix, iy)：原图像素 → 画布坐标（往虫头上叠代码画的帽子时，先在原图里量帽子该落的点）。
    """
    import base64
    import io
    from PIL import Image
    _check_png(png)
    im = Image.open(png).convert('RGBA')
    iw0, ih0 = im.size
    x0, y0, x1, y1 = alpha_box(png)
    s = w / (x1 - x0)
    left, top = x - x0 * s, y - y0 * s
    src = f'file://{Path(png).resolve()}'
    box = f'position:absolute; left:{left:.1f}px; top:{top:.1f}px; width:{iw0 * s:.1f}px; height:{ih0 * s:.1f}px;'
    mk = Image.new('LA', im.size, 255)
    mk.putalpha(im.getchannel('A'))
    mk = mk.resize((max(1, round(iw0 * s * 2)), max(1, round(ih0 * s * 2))), Image.LANCZOS)   # 按 2x 出图的像素
    buf = io.BytesIO()
    mk.save(buf, 'PNG')
    uri = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    mask = f"-webkit-mask-image:url('{uri}'); -webkit-mask-size:100% 100%; mask-image:url('{uri}'); mask-size:100% 100%;"
    ol = outline_css(outline) if outline else ''
    html = (f'<img class="sprite" src="{src}" style="{box} {ol}">'
            f'<div class="sprite-tex" style="{box} background:url(\'file://{BG}\') no-repeat; background-size:1080px 1440px; '
            f'background-position:{-left:.1f}px {-top:.1f}px; mix-blend-mode:multiply; opacity:.45; pointer-events:none; {mask}"></div>')

    def pt(ix, iy):
        return left + ix * s, top + iy * s
    return html, pt


def cover_mascots(foot_y: float, q_cx: float = 168, e_cx: float = 914, s: float = 0.42, tilt: float = 6) -> str:
    """生图封面的两只吉祥物（08 §4b 的可选布局几何）：?怪 在左、!怪 在右，脚底中心落在 (cx, foot_y)，
    缩放 s，分别外倾 ±tilt 度，眼型 COVER_EYES。返回一个铺满画布的绝对定位 SVG。"""
    sys.path[:0] = [str(HERE), str(KIT / 'templates')]
    try:
        import mascots as M
    except ImportError:
        raise SystemExit(f'✗ 找不到 templates/mascots.py：设环境变量 KIT=<本 skill 目录>（现在是 {KIT}）')
    q = M.qm2(q_cx - M.Q_FEET[0] * s, foot_y - M.Q_FEET[1] * s, s, M.Q_EYES, COVER_EYES[0], ink=INK, paper=PAPER)
    e = M.em2(e_cx - M.E_FEET[0] * s, foot_y - M.E_FEET[1] * s, s, M.E_EYES, COVER_EYES[1], ink=INK, accent=ACCENT2, paper=PAPER)
    return (f'<svg class="mascots" viewBox="0 0 1080 1440" style="position:absolute; left:0; top:0; width:1080px; height:1440px; pointer-events:none;">'
            f'<g transform="rotate({tilt} {q_cx} {foot_y})">{q}</g><g transform="rotate({-tilt} {e_cx} {foot_y})">{e}</g></svg>')


# 派生角色（可选）：从同一个 SVG 血统派生，两个角色才一眼是同一套画法。
# ★ 派生必须改几何，不能改注释 ★ —— 示例写过
#   s.replace('<!-- 肉垂', '<!-- 肉垂（母鸡更小）')，只改注释不改 path，是个假修改。
# 改之前先读原 SVG 把坐标算清楚（头在哪、半径多少、某个 y 上的半宽是多少）。
def derive(svg: str) -> str:
    i, j = svg.index('<!-- <起点注释>'), svg.index('<!-- <终点注释>')
    return svg[:i] + '''<!-- 替换成新几何 -->
  ''' + svg[j:]

# 去掉某个部件（图示里常用：两个角色并排时，去掉一侧的大尾羽才看得见接触点）
def strip_part(svg: str, start: str, end: str) -> str:
    return svg[:svg.index(start)] + svg[svg.index(end):]


# 四张图共用的头部：画布、底图、字体。别改。
BASE = f'''  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 1080px; height: 1440px; overflow: hidden; }}
  body {{ position: relative; background: url('file://{BG}') center/cover;
         font-family: "Noto Sans CJK SC", "Hiragino Sans GB", sans-serif; color: {INK}; }}
'''


# ── ① 首图：钩子 ─────────────────────────────────────────
# 四段式：场景锚点 / 动作描述 / 设问引导 / 反常结果（见 references/03-四张图.md、04-文案.md）
# 角度是几何硬约束不是审美偏好：一行旋转 θ 吃掉的垂直空间 = 行高 + 行宽 × sinθ
#   短行（2–4 字）敢给 ±14~20°，长行（5 字以上）只能 ±3~7°。见 DNA §3。
# 四段式，每段的字数上限是几何算出来的，别超：
#   r1 场景锚点 ≤7字 · r2 动作描述 ≤6字 · r3 设问引导 ≤7字 · r4 反常结果 ≤6字
#   超了会撑破画布，门禁 R1/R3 会拦。想写长的就把字号调小、角度调平。
# （写在 Python 注释里，不写成多行 HTML 注释：去 AI 味闸按行读 HTML，多行注释里的「--」会被当成破折号）
COVER = f'''<style>
{BASE}
  .r {{ position: absolute; font-weight: 900; letter-spacing: -.045em;
       white-space: nowrap; transform-origin: left center; }}
  .r1 {{ top: 142px;  left: 66px; font-size: 98px;  transform: rotate(-16deg); }}   /* 旋转 -16° 会把行顶往上抬约 64px，top 给小了会越界（门禁 R3）*/
  .r2 {{ top: 330px;  left: 84px; font-size: 128px; transform: rotate(5deg); }}
  .r3 {{ top: 640px;  left: 70px; font-size: 98px;  transform: rotate(-15deg); }}
  .r4 {{ top: 1010px; left: 56px; font-size: 96px;  transform: rotate(6deg); }}
  .ac {{ color: {ACCENT}; }}
  /* 色块只给第 4 段（反常结果）。错版影是首图最强的风格标记 */
  .blk {{ background: {ACCENT2}; color: {PAPER}; padding: 4px 20px 14px;
         box-shadow: 8px 8px 0 {ACCENT}; margin: 0 6px; }}
  /* 主角 320~400px：只适用于代码主角；生图封面布局见 08 §4b */
  .hero {{ position: absolute; right: 28px; top: 450px; width: 400px; }}
  .hero svg {{ width: 100%; display: block; }}
</style>

<div class="r r1"><生活瞬间 / 主题词></div>
<div class="r r2"><span class="ac"><核心话题></span><简短设问></div>
<div class="r r3"><情绪钩子></div>
<div class="r r4"><反常识结论></div>

<div class="hero">{HERO}</div>
'''

# ── ① 首图 · 生图封面变体（COVER_ART 不是 None 时替换上面的 COVER）────────
# 此布局为按题可选版式；尺寸和文字层级见 references/08-视觉规范.md §4b，采用前应做缩略图冷读。
# 大字 r1：left 56 / top 98 / 80px / -3°；r2：top 232 / 104px / +3°，话题词进色块。
# 框：外沿 x 91 / y 457 / 898×650，圆角 26；按目标画面调整框形与尺寸。
# 吉祥物：代码角色可放在框下沿外两角，尺寸与眼型按账号视觉设定。
# 底线：left / right 56、bottom 70；上边线 5px INK；40px 一行。
if COVER_ART:
    CV_X, CV_Y, CV_W, CV_H = 91, 457, 898, 650
    CV_PIC, _cv_pt = art_frame(COVER_ART, CV_X, CV_Y, CV_W, CV_H, fit=COVER_FIT, focus=0.40, trim=True)
    COVER = f'''<style>
{BASE}
  .r {{ position: absolute; left: 56px; font-weight: 900; letter-spacing: -.05em;
       white-space: nowrap; transform-origin: left center; }}
  .r1 {{ top: 98px; font-size: 80px; transform: rotate(-3deg); }}
  .r2 {{ top: 232px; font-size: 104px; transform: rotate(3deg); }}
  .r2 span {{ background: {ACCENT}; color: #fff; padding: 2px 24px 15px; margin: 0 10px;
             box-shadow: 9px 9px 0 {INK}; }}
  .foot {{ position: absolute; left: 56px; right: 56px; bottom: 70px; border-top: 5px solid {INK};
          padding-top: 18px; font-size: 40px; font-weight: 900; line-height: 1.35; letter-spacing: -.03em; }}
  .foot em {{ font-style: normal; color: {ACCENT}; }}
</style>

<div class="r r1"><场景一句 ≤12 字></div>
<div class="r r2"><span><话题词></span><设问></div>
{CV_PIC}
{cover_mascots(1258) if COVER_EYES else ''}
<div class="foot"><底线一行小字，和画面意思一致><em><重点></em></div>
'''


# ── ② 答案图 ─────────────────────────────────────────────
# 文字块按 references/03-四张图.md「每张卡的文字块」：hd / lead / 图 / t1 /（note）/ src /（final）。
# ★ 标题 ≤ 8 字 ★ —— 色块右端别越过底图网点团最左 x（gen_bg.py / measure_bg.py 打印的那个数），门禁拦不住这条。见 DNA §5。
# 间距（03）：t1 = 372 + 图高 + 18（框有 14px 硬阴影，再加 14）；src = t1 + 45 × 正文行数 + 24；
#             有限定框时 note = t1 + 45 × 正文行数 + 20，src = note + 框高 + 20。第一次用先出图量一遍，别信公式。
PIC_Y, PIC_H = 372, 620
if ART:     # 生图主体进框。fit 按构图档选：人物半身 'face'（默认 focus）/ 到腰 'waist' / 全身生物·吉祥物 'full' / 物件 'object' / 局部 'closeup'
            # 深色场景（夜空、水下）：scene=<框内坐标的 SVG>，深色主体再加 outline=PAPER（08 §7b 例外）
            # 横框 968×620 装不下竖向构图（人脸 + 肚脐同框、1.5 米高的水雾），要么改竖框，要么改代码画
    PIC, _pt = art_frame(ART, 56, PIC_Y, 968, PIC_H)
    T1_Y = PIC_Y + PIC_H + FRAME_SHADOW + 18
else:       # 没有生图：SVG 主角居中
    PIC = f'<div class="pic sv" style="left:290px; width:500px;">{HERO}</div>'
    T1_Y = PIC_Y + 500 + 18
SRC_Y = T1_Y + 45 * 2 + 24        # t1 写两行

ANSWER = f'''<style>
{BASE}
  .sv svg {{ width: 100%; display: block; }}
  .hd {{ position: absolute; top: 92px; left: 56px; font-size: 76px; font-weight: 900;
        letter-spacing: -.045em; white-space: nowrap; transform: rotate(-3deg); transform-origin: left center; }}
  .hd span {{ background: {ACCENT2}; color: {PAPER}; padding: 2px 22px 15px; box-shadow: 9px 9px 0 {ACCENT}; }}
  /* 导语两行；人物第一次出现要有名字 */
  .lead {{ position: absolute; left: 56px; right: 56px; top: 242px; font-size: 40px; font-weight: 900;
          line-height: 1.4; letter-spacing: -.03em; }}
  .lead em {{ font-style: normal; color: {ACCENT}; }}
  .pic {{ position: absolute; top: {PIC_Y}px; }}
  /* 正文 ≥27px：1080 图缩到手机 390 宽是 2.77 倍，27px → 约 9.7px。限定默认并进正文，不带标签 */
  .txt {{ position: absolute; left: 56px; right: 56px; font-size: 29px; font-weight: 800; line-height: 1.55; }}
  .txt b {{ color: {ACCENT}; }}
  .t1 {{ top: {T1_Y}px; }}
  /* 限定框：整集最多 1 张用（ai_flavor_check C1）；健康类安全提醒写 class="note safety" 豁免 */
  .note {{ position: absolute; left: 56px; right: 56px; border: 5px solid {INK}; background: {PAPER};
          padding: 14px 24px 16px; box-shadow: 10px 10px 0 {ACCENT2}; font-size: 27px; font-weight: 800; line-height: 1.5; }}
  /* 来源行：一行，只留「作者 年份」，用 · 隔开（C2）。期刊、卷期放发布文案的出处表 */
  .src {{ position: absolute; left: 56px; right: 56px; top: {SRC_Y}px; font-size: 24px; font-weight: 700;
         line-height: 1.45; opacity: .78; white-space: nowrap; }}
  /* DNA 规定数字用 Noto Serif SC：正文里的硬数字写成 <span class="num">64.5%</span> */
  .num {{ font-family: "Noto Serif SC", serif; font-weight: 900; color: {ACCENT}; }}
</style>

<div class="hd"><span><标题 ≤8 字></span></div>
<div class="lead"><导语第一行><br><em><导语第二行></em></div>
{PIC}
<div class="txt t1"><正文一两句人话，限定并进这里；硬数据写成 <span class="num">XX%</span>></div>
<!-- 限定框（可选，整集最多 1 个）：写成 div、class 用 note，放最要紧的那条限定；健康安全提醒用 note safety。没有就不写 -->
<div class="src"><作者 年份 · 作者 年份></div>
<!-- 收尾句默认不写；要写就是一个具体事实或一个能做的动作（div、class 用 final），见 03-四张图.md -->
'''


# ── ③ 机制图示 ───────────────────────────────────────────
# 模块图示把空间 / 动作关系画出来，而不是只用文字描述。
# 复用 ① / ② 的生图主体当小图标（路径起点的小虫、彩蛋里给它戴帽子）：html, pt = art_sprite(ART, x, y, 宽度)，不带框。
#
# ★ 同姿势的侧面剪影不能纵向叠 ★
#   示例要画「A 踩到 B 背上」，试了三版都失败：下面那只的头天然落在上面那只
#   身体的正下方，整个被吃掉只剩一坨黑圆。加纸色描边也只救回头颈。
#   → 改成【并排示意】（一只水平翻转，两者身体后端相对），接触点标在正中。
#     写实的那一步用副标题一行字补上。图示要说清「怎么发生」，不是还原姿势。
#
# ★ 两个同色剪影挨着必须描边分离 ★（下面 .lower 的 filter，blur 必须为 0）
DIAGRAM = f'''<style>
{BASE}
  .hd {{ position: absolute; top: 92px; left: 56px; font-weight: 900; font-size: 104px;
        letter-spacing: -.04em; white-space: nowrap; transform: rotate(-3deg);
        transform-origin: left center; }}
  .hd span {{ background: {ACCENT2}; color: {PAPER}; padding: 2px 22px 15px;
             box-shadow: 9px 9px 0 {ACCENT}; }}
  .lead {{ position: absolute; top: 268px; left: 62px; font-size: 34px; opacity: .8;
         font-weight: 700; }}

  /* 两个角色并排。坐标必须算出来并写清楚，例（示例实测）：
       两只都 430px（scale 1.075），top 同为 480 → 身体中心同在 y=800。
       左侧翻转后身体 x 146~370；右侧身体 x 410~634、喙尖 748。
       两身体后端间隙 370~410 → 接触点 x=390。
       标签起于 x=790 > 748，才不会被角色的突出部件压住。 */
  .left  {{ position: absolute; left: 30px;  top: 480px; width: 430px;
           transform: scaleX(-1); }}
  .right {{ position: absolute; left: 320px; top: 480px; width: 430px; }}
  .left svg, .right svg {{ width: 100%; display: block; }}
  /* 需要叠压时给下层描一圈纸色外轮廓，否则两个 INK 剪影糊成一坨 */
  .lower {{ filter: drop-shadow(7px 0 0 {PAPER}) drop-shadow(-7px 0 0 {PAPER})
                    drop-shadow(0 7px 0 {PAPER}) drop-shadow(0 -7px 0 {PAPER}); }}

  /* 接触点：圆圈 + 引线 + 标签。引线走形体外侧绕出去，不穿过任何东西 */
  .dot {{ position: absolute; left: 350px; top: 812px; width: 80px; height: 80px;
         border: 7px solid {ACCENT}; border-radius: 50%; }}
  .lead {{ position: absolute; left: 370px; top: 884px; width: 420px; height: 160px; }}
  .tag {{ position: absolute; left: 790px; top: 952px; font-weight: 900; font-size: 46px;
         color: {ACCENT}; line-height: 1.45; }}
  .tag small {{ display: block; font-size: 27px; color: {INK}; opacity: .78;
               font-weight: 700; margin-top: 14px; line-height: 1.55; }}

  /* 底栏说明（可选）。叫 caption 不叫 note：note 是「整集最多 1 个」的限定框，ai_flavor_check C1 会计数 */
  .caption {{ position: absolute; left: 56px; right: 56px; bottom: 96px;
          border-top: 4px solid {INK}; padding-top: 20px;
          font-size: 30px; font-weight: 700; line-height: 1.5; }}
  .caption em {{ font-style: normal; color: {ACCENT}; }}
</style>

<div class="hd"><span><它是这么发生的></span></div>
<div class="lead"><写实那一步用这行字补上></div>

<div class="left">{HERO}</div>
<div class="right">{HERO}</div>

<div class="dot"></div>
<svg class="lead" viewBox="0 0 420 160" fill="none">
  <path d="M20 8 L20 126 L412 126" stroke="{ACCENT}" stroke-width="5"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>
<div class="tag"><机制的名字><small><两行大白话解释<br>第二行></small></div>

<!-- <div class="caption"><底栏一句说明，可选></div> -->
<!-- 收尾句默认不写；要写就是一个具体事实或一个能做的动作，不许对仗和破折号，见 03-四张图.md -->
'''
# ⚠️ 如果要画「有多快 / 有多大」这类数据条：刻度必须真的等分。
#    示例第一版用 space-between 把「眨一次眼 ≈ 0.3 秒」顶在条的正中央，
#    等于暗示 0.3 秒 = 半程（应该在 3% 处）。门禁只管几何不管语义，测不到这种错。
#    要么放真刻度（0/5/10），要么别放。


# ── ④ 彩蛋图 ─────────────────────────────────────────────
# 一条能独立成立的反常识，压在最后。
# ★ 彩蛋做成图之后，正文里原来那句必须删 ★ —— 留着既重复又提前剧透。
#   正文改成把人往最后一张带（示例：「最后一张更离谱，跟我早饭有关」）。
EGG = f'''<style>
{BASE}
  .r {{ position: absolute; font-weight: 900; letter-spacing: -.045em;
       white-space: nowrap; transform-origin: left center; }}
  .r1 {{ top: 190px; left: 62px; font-size: 92px;  transform: rotate(-12deg); }}
  .r2 {{ top: 372px; left: 76px; font-size: 118px; transform: rotate(4deg); }}
  .blk {{ background: {ACCENT}; color: {PAPER}; padding: 4px 22px 15px;
         box-shadow: 9px 9px 0 {INK}; }}

  /* 对照示意：一排「有的」+ 一个被划掉的「没有的」。用画的说，不用字说。 */
  .grp {{ position: absolute; left: 0; right: 0; top: 620px; height: 500px; }}
  .u {{ position: absolute; width: 238px; }}
  .u svg {{ width: 100%; display: block; }}
  .u1 {{ left: 30px;  top: 118px; }}     /* 高低错落，别排成一条直线 */
  .u2 {{ left: 262px; top: 88px; }}
  .u3 {{ left: 494px; top: 122px; }}
  /* 划掉的那个：右移到不和左边最后一个的突出部件重叠的位置 */
  .cross {{ position: absolute; left: 748px; top: 52px; width: 310px; }}
  .cross .c {{ width: 310px; opacity: .35; }}
  .cross .c svg {{ width: 100%; display: block; }}
  .xmark {{ position: absolute; left: 0; top: 22px; width: 310px; height: 310px; }}
  /* 标签要压在最低那个的底边以下：238px 宽 → 高 286px，最低那个底边 = top + 286 */
  .lbl {{ position: absolute; top: 418px; font-size: 27px; font-weight: 800; opacity: .8; }}
  .lbl1 {{ left: 78px; }}
  .lbl2 {{ left: 754px; color: {ACCENT}; opacity: 1; }}

  .foot {{ position: absolute; left: 56px; right: 56px; bottom: 96px;
          border-top: 5px solid {INK}; padding-top: 24px;
          font-size: 36px; font-weight: 900; line-height: 1.45; }}
  .foot em {{ font-style: normal; color: {ACCENT}; }}
  .foot small {{ display: block; font-size: 27px; font-weight: 700;
                opacity: .74; margin-top: 12px; }}
</style>

<div class="r r1"><所以你那个……></div>
<div class="r r2"><span class="blk"><反常结论></span></div>

<div class="grp">
  <div class="u u1">{HERO}</div>
  <div class="u u2">{HERO}</div>
  <div class="u u3">{HERO}</div>
  <div class="cross">
    <div class="c">{HERO}</div>
    <svg class="xmark" viewBox="0 0 310 310" fill="none">
      <path d="M40 40 L270 270 M270 40 L40 270" stroke="{ACCENT}"
            stroke-width="20" stroke-linecap="round"/>
    </svg>
  </div>
  <div class="lbl lbl1"><左边这些是什么></div>
  <div class="lbl lbl2"><一个都没有></div>
</div>

<!-- foot = 03 文字块里的 final（收尾句）。ai_flavor_check 认 class="foot" / "final"，门禁 R2 认 .foot -->
<div class="foot">
  <收尾句：一个具体事实 / 一个具体邀请 / 整块删掉，见 03-四张图.md；不许对仗和格言>
  <small><可选：补一句日常里的落点。></small>
</div>
'''


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    # 文件名是硬约定：shot.js 只对 素材/ 下的 [1-4]_*.html 跑去 AI 味闸
    names = [('1_cover', COVER), ('2_answer', ANSWER), ('3_mechanism', DIAGRAM), ('4_egg', EGG)]
    for name, html in names:
        (OUT / f'{name}.html').write_text(html, encoding='utf-8')
    print(f'生成 {OUT}/' + ' '.join(f'{n}.html' for n, _ in names))
    print()
    print('接着跑（四张各一遍，exit 1 就是不合格，不要肉眼放行；KIT = 本 skill 目录）：')
    for n, _ in names:
        print(f'  node $KIT/scripts/social-card-qa.mjs {OUT}/{n}.html')
    for n, _ in names:
        print(f'  node $KIT/scripts/shot.js {OUT}/{n}.html {OUT}/{n}.png 1080 1440')
