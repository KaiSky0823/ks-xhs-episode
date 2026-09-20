#!/usr/bin/env python3
"""一集四张图的骨架 —— 每集复制一份到当集目录改，别改这个模板本身。

    cp build_template.py 第N集-XX/build_epN.py

为什么不做成配置驱动的通用生成器：cover/answer 的版式是固定的，但 diagram 和 egg
每集都要按内容重新构图（第 2 集的「两只鸡尾对尾」换个选题就完全不适用）。
强行抽象会变成一个没人看得懂的模板引擎。每集一个脚本、几何常量写在注释里，
是目前最省事也最不容易错的做法。

改之前先读 KAI_VISUAL_DNA.md。这里的常量都是它的实例化，不是可以随便调的旋钮。

★ 几何常量必须是算出来的，不是试出来的 ★
每个 left/top 旁边写清楚它从哪来。第 2 集的图示改了六版，前三版都是拍脑袋调数字，
一版比一版糟 —— 直到把 rect 量出来才找到真正的原因。
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / '素材'
# mkdir 挪进 __main__：模块顶层建目录会让「import 一下」就在 kit 根长出空 素材/（mini 2026-09-03 定位到的）

# ── 当集配置：只改这一段 ─────────────────────────────────
#
# 底图：同一集四张图共用一张（series 感来自纸纹/网点/污渍完全一致）。
#       换色板才生新的，见 DNA §7 和 scripts/gen_bg.py。
BG = OUT / 'tex_<当集>.png'

# 底图自检 —— 因为实测出过事：第 2 集的底图绕过了 gen_bg.py，
# 落盘是个「名字叫 .png 的 JPEG」，gen_bg.py 的魔数自验根本没机会跑。
# 光靠「记得用 gen_bg.py」这条纪律拦不住，所以在这儿再设一道闸。
# JPEG 会在纸纹/网点这种高频内容上出块状伪影（DNA §7）。
def check_bg(path: Path) -> None:
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
#   python3 -c "from PIL import Image; im=Image.open('底图.png').convert('RGB'); \
#               print('#%02X%02X%02X' % tuple(sum(c)//len(c) for c in zip(*im.getdata())))"
INK, ACCENT, ACCENT2, PAPER = '#1C1A17', '#C8322A', '#1B4D8F', '#FBF4E4'

# 主角 SVG：SVG，不是生图。颜色跟着当集色板走，位置像素级可控。
# 画法见 DNA §6。同一集里跨图复用同一个 SVG，这是 series 感的来源。
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


# 派生角色（可选）：从同一个 SVG 血统派生，两个角色才一眼是同一套画法。
# ★ 派生必须改几何，不能改注释 ★ —— 第 2 集写过
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
# 四段式：场景锚点 / 动作描述 / 设问引导 / 反常结果（见 copy-template.md）
# 角度是几何硬约束不是审美偏好：一行旋转 θ 吃掉的垂直空间 = 行高 + 行宽 × sinθ
#   短行（2–4 字）敢给 ±14~20°，长行（5 字以上）只能 ±3~7°。见 DNA §3。
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
  /* 主角 320~400px。再大会不和谐 —— Kai 原话「太大会有点不和谐视觉」 */
  .hero {{ position: absolute; right: 28px; top: 450px; width: 400px; }}
  .hero svg {{ width: 100%; display: block; }}
</style>

<!-- 四段式，每段的字数上限是几何算出来的，别超：
     r1 场景锚点 ≤7字 · r2 动作描述 ≤6字 · r3 设问引导 ≤7字 · r4 反常结果 ≤6字
     超了会撑破画布，门禁 R1/R3 会拦。想写长的就把字号调小、角度调平。-->
<div class="r r1">洗手时泼它</div>
<div class="r r2">泼了<span class="ac">七八次</span></div>
<div class="r r3">一次都没中</div>
<div class="r r4">居然<span class="blk">不是手慢</span>？</div>

<div class="hero">{HERO}</div>
'''


# ── ② 答案图 ─────────────────────────────────────────────
# 信息密度比首图高一档（覆盖率 54% 左右），靠「分区 + 区间留白」撑开，不是把字堆满。
# ★ 标题 ≤ 8 字 ★ —— 9 字时色块右端会压在右上角的网点上，门禁拦不住这条。见 DNA §5。
ANSWER = f'''<style>
{BASE}
  .hd {{ position: absolute; top: 96px; left: 56px; font-weight: 900; font-size: 118px;
        letter-spacing: -.04em; white-space: nowrap; transform: rotate(-3deg);
        transform-origin: left center; }}
  .hd span {{ background: {ACCENT2}; color: {PAPER}; padding: 2px 24px 16px;
             box-shadow: 9px 9px 0 {ACCENT}; }}

  .keys {{ position: absolute; left: 56px; top: 384px; width: 570px; }}
  .row {{ padding: 24px 0; border-top: 2.5px solid {INK}; }}
  .row:last-child {{ border-bottom: 2.5px solid {INK}; }}
  .num {{ display: inline-flex; width: 40px; height: 40px; border-radius: 50%;
         background: {ACCENT}; color: {PAPER}; font-weight: 900; font-size: 24px;
         align-items: center; justify-content: center; margin-right: 12px;
         vertical-align: 6px; }}
  .row .t {{ display: inline; font-size: 40px; font-weight: 900; line-height: 1.3;
            letter-spacing: -.02em; }}
  .row .t em {{ font-style: normal; color: {ACCENT}; }}
  /* 正文 ≥27px：1080 图缩到手机 390 宽是 2.77 倍，27px → 约 9.7px */
  .row .d {{ font-size: 27px; line-height: 1.55; opacity: .76; margin: 10px 0 0 52px; }}

  .hero {{ position: absolute; right: 26px; top: 430px; width: 400px; }}
  .hero svg {{ width: 100%; display: block; }}

  /* 结论区：一个硬数据 + 它的反面，两格对照 */
  .foot {{ position: absolute; left: 56px; right: 56px; bottom: 84px;
          border-top: 5px solid {INK}; padding-top: 26px;
          display: grid; grid-template-columns: 1fr 1.1fr; gap: 34px; }}
  .cell {{ border-left: 2.5px solid {INK}; padding-left: 24px; }}
  .cell:first-child {{ border-left: 0; padding-left: 0; }}
  /* DNA 规定数字用 Noto Serif SC */
  .cell .v {{ font-family: "Noto Serif SC", serif; font-weight: 900;
             font-size: 76px; line-height: 1; letter-spacing: -.03em; }}
  .cell .v small {{ font-size: 30px; }}
  .cell.hi .v {{ color: {ACCENT}; }}
  .cell .n {{ font-size: 25px; letter-spacing: .04em; opacity: .74; margin-top: 12px; }}
</style>

<div class="hd"><span><标题 ≤8 字></span></div>

<div class="keys">
  <div class="row">
    <span class="num">1</span><div class="t"><要点一，关键词用 <em>这个</em>></div>
    <div class="d"><一句展开></div>
  </div>
  <div class="row">
    <span class="num">2</span><div class="t"><要点二></div>
    <div class="d"><一句展开></div>
  </div>
  <div class="row">
    <span class="num">3</span><div class="t"><要点三></div>
    <div class="d"><一句展开></div>
  </div>
</div>

<div class="hero">{HERO}</div>

<div class="foot">
  <div class="cell hi"><div class="v">约 XX<small>%</small></div><div class="n"><这个数字是什么></div></div>
  <div class="cell"><div class="v">剩下 X<small>%</small></div><div class="n"><反面></div></div>
</div>
'''


# ── ③ 机制图示 ───────────────────────────────────────────
# 把空间/动作关系【画出来】，不写成字。这张是 Angel 反馈里点名要的。
#
# ★ 同姿势的侧面剪影不能纵向叠 ★
#   第 2 集要画「A 踩到 B 背上」，试了三版都失败：下面那只的头天然落在上面那只
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
  .sub {{ position: absolute; top: 268px; left: 62px; font-size: 34px; opacity: .8;
         font-weight: 700; }}

  /* 两个角色并排。坐标必须算出来并写清楚，例（第 2 集实测）：
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

  .note {{ position: absolute; left: 56px; right: 56px; bottom: 96px;
          border-top: 4px solid {INK}; padding-top: 20px;
          font-size: 30px; font-weight: 700; line-height: 1.5; }}
  .note em {{ font-style: normal; color: {ACCENT}; }}
</style>

<div class="hd"><span><它是这么发生的></span></div>
<div class="sub"><写实那一步用这行字补上></div>

<div class="left">{HERO}</div>
<div class="right">{HERO}</div>

<div class="dot"></div>
<svg class="lead" viewBox="0 0 420 160" fill="none">
  <path d="M20 8 L20 126 L412 126" stroke="{ACCENT}" stroke-width="5"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>
<div class="tag"><机制的名字><small><两行大白话解释<br>第二行></small></div>

<div class="note"><一句收口>，<em><关键词></em>——<所以叫什么>。</div>
'''
# ⚠️ 如果要画「有多快 / 有多大」这类数据条：刻度必须真的等分。
#    第 2 集第一版用 space-between 把「眨一次眼 ≈ 0.3 秒」顶在条的正中央，
#    等于暗示 0.3 秒 = 半程（应该在 3% 处）。门禁只管几何不管语义，测不到这种错。
#    要么放真刻度（0/5/10），要么别放。


# ── ④ 彩蛋图 ─────────────────────────────────────────────
# 一条能独立成立的反常识，压在最后。
# ★ 彩蛋做成图之后，正文里原来那句必须删 ★ —— 留着既重复又提前剧透。
#   正文改成把人往最后一张带（第 2 集：「最后一张更离谱，跟我早饭有关」）。
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

<div class="foot">
  <一句收口>，<em><关键词></em>。
  <small><补一句日常里的落点。></small>
</div>
'''


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    for name, html in [('cover', COVER), ('answer', ANSWER),
                       ('diagram', DIAGRAM), ('egg', EGG)]:
        (OUT / f'{name}.html').write_text(html, encoding='utf-8')
    print(f'生成 {OUT}/cover.html answer.html diagram.html egg.html')
    print()
    print('接着跑（四张各一遍，exit 1 就是不合格，不要肉眼放行）：')
    print(f'  node $KIT/scripts/social-card-qa.mjs {OUT}/<name>.html')
    print(f'  node $KIT/scripts/shot.js {OUT}/<name>.html {OUT}/<name>.png 1080 1440')
