#!/usr/bin/env python3
"""生成小红书竖版「纯质感底图」—— 分层架构的视觉层。

底图只负责质感：纸纹、半色调网点飞溅、褪色渍、折痕。
**不画任何主体，也不写任何文字** —— 主体由代码 SVG 画，或用 gen_art.py 生图（见 references/12），
文字由 HTML 排版（中文永不出错）。

用法（在放各集目录的那一层执行；KIT = 本 skill 目录）：
  python3 $KIT/scripts/gen_bg.py -o 第N集-XX/素材/tex_<名>.png \\
      "极浅、接近白色的青瓷绿纸面，只带一点绿调，纸浆纤维清晰，轻微折痕；右上角的半色调网点是浓重、粗大的深墨绿色"

  # 换色系时才需要跑；同一集四张图共用同一张底图。
  # 提示词只走参数；不要描述主体和文字。网点颜色口径：比纸面深很多的同色系深色（约束段会追加这句，提示词别写别的色相）。

落盘后脚本自己验（任一不过 exit 1，不出「看起来成功」的图）：
  - 魔数是 PNG、能完整解码（截断 / 坏图 → 原始字节留在 <out>.raw，不丢已付费的图）
  - 服务端回的尺寸 = 请求尺寸（Flash 1856×2480；不对就停，不拉伸）
  - 最终尺寸 = 2160×2880，比例 0.75
  - 纸色 L* > 92（DNA 规则 1；测法和 measure_bg.py 一样：去掉右上四分之一）。
    不过就把图改名成 <名>_rejected_L<xx>.png，免得被当成定稿底图用
另外打印：纸色实测 hex、网点团最左 CSS x（答案图标题色块右端以它为准，不再用固定的 714）。
每次调用都写 <out>.json：prompt、model、size、secs、usage、attempts、结果。
对已用纸色的 ΔE 由 measure_bg.py 查，出图后接着跑它。

────────────────────────────────────────────────────────────────────────
引擎一：flash（默认，2026-10-22 起）
────────────────────────────────────────────────────────────────────────
模型 doubao-seedream-5-0-flash-260915，请求 1856×2480（3:4，约 460 万像素，Flash 上限约 462 万，
出不了 2160×2880），`response_format: b64_json` 直接拿图（不走 TOS 下载，那个域名的 TLS 握手经常被卡），
再用 Lanczos 放大 1.16× 到 2160×2880。
  清晰度：合规底图放大后约为 lite 的 70% 到 80%（拉普拉斯方差，三张合规 Flash 底图样本实测
  71%~78%；这个指标受网点多少影响，只能粗看）。
  提示词：Flash 上旧写法（「极浅的…纸面」+ 淡网点）出灰白、网点淡而小的纸，**必须写「极浅、接近白色」
  的纸面和「浓重 / 粗大 / 深色」的网点**。约束段已经替你加了这两句。
  已知问题：网点团比 lite 大、更往左（实测最左 x 479~614，lite 约 666），所以脚本打印实测 x。
  ★推荐用法（2026-10-22）：加 `--paper '#RRGGBB'`。先用 pick_paper.py 挑好目标纸色，模型只负责出质感
  （近白纸纤维 + 折痕 + 深色网点，提示词不写颜色），出图后 tint_bg.py 把纸色和网点色**精确落到目标 hex**
  （输出仍须实测纸色、检查纸纹与折痕）。原图另存为 <名>_src.png（再换一个颜色不用重新付费）。
  这样绕开了「Flash 要么色相丢光、要么 L* 掉到 80」的老问题。不加 --paper 时仍是旧行为（靠提示词碰色，易失败）。

────────────────────────────────────────────────────────────────────────
引擎二：lite（`--engine lite`，即将下线）
────────────────────────────────────────────────────────────────────────
模型 doubao-seedream-5-0-lite-260128，原生 2160×2880（零放大）。官方模型列表（2026-10-21）标为「即将下线」，无日期。
请求体：`response_format: b64_json`、`output_format: png`、`sequential_image_generation: disabled`，
和 flash 共用重试和取 key（旧版走 url + TOS 下载，本机实测下载被重置，图生成了、费用扣了、图没拿到）。
  为什么按物理像素出：HTML 画布 1080×1440 CSS px，shot.js 用 deviceScaleFactor 2 → 2160×2880。
  低分辨率底图放大会损失高频纹理，不能只看缩略图。
  为什么比例必须 0.75：CSS 是 `background: url() center/cover`，比例不对会居中裁切，
  **钉在右上角的网点会被直接裁出画面，且不报任何错**。
  为什么必须 PNG：服务端默认回 JPEG，JPEG 在网点这种高频内容上出块状伪影；`output_format: png` 是关键参数。
可选后端：设环境变量 ARK_IMAGE_CLI（指向符合本脚本约定的可选 CLI）时，lite 引擎会委托该程序生成；未设置则使用直连 API。两条路共用同一套落盘自验。

API key：通过环境变量 `ARK_API_KEY` 提供；脚本不会打印或持久化 key。
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_bg import dot_left_css, paper_color   # noqa: E402  测纸色 / 网点 x 和 measure_bg 用同一套算法

ARK_IMAGE = Path(os.environ.get("ARK_IMAGE_CLI", "/nonexistent/ark_image.py"))
ARK_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

MODEL = "doubao-seedream-5-0-lite-260128"
SIZE = "2160x2880"
FLASH_MODEL = "doubao-seedream-5-0-flash-260915"
FLASH_SIZE = "1856x2480"          # 3:4，约 460 万像素，Flash 的上限
FINAL_SIZE = (2160, 2880)
EXPECT_RATIO = 0.75               # 2160/2880，必须和 HTML 画布 1080/1440 精确相同
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MIN_L = 92                        # DNA 规则 1

# 每次都追加。少了这几句，模型会自作主张加字、加虫、把网点撒得到处都是。
DOT_COLOR = "网点颜色是比纸面深很多的同色系深色。"     # 口径和 07 / 08 一致；提示词里写网点颜色也写同色系的深色，别写别的色相
CONSTRAINTS = (
    "只在画面右上角有一片半色调网点飞溅，网点颗粒清晰锐利。" + DOT_COLOR +
    "画面左侧、中部、下部保持完全干净的空白纸面，没有任何网点、色斑或痕迹。"
    "整张图不含任何文字、汉字、字母、数字、标点、logo、水印，"
    "也不含任何昆虫、动物、人物、器物或可辨认的主体图形——只要纸张本身和印刷痕迹。"
)
# Flash 专用：纸面要写「极浅、接近白色」，网点要写「浓重、粗大」，否则出灰纸、淡而小的网点。
CONSTRAINTS_FLASH = (
    "纸面整体极浅、接近白色，只带一点色调。"
    "右上角有一大团浓重的半色调网点飞溅，网点颗粒粗大、清晰锐利，中心最密、向外逐渐变稀并散成细小的点。" + DOT_COLOR +
    "画面左侧、中部、下部保持完全干净的空白浅色纸面，没有任何网点、色斑或痕迹。"
    "整张图不含任何文字、汉字、字母、数字、标点、logo、水印，"
    "也不含任何昆虫、动物、人物、器物或可辨认的主体图形——只要纸张本身和印刷痕迹。"
)

# --paper 模式：颜色交给 tint_bg.py，所以提示词只要质感，并明说不要色相（色相会被丢掉，写了反而干扰明度）
DEFAULT_TEXTURE = "纸浆纤维清晰，有几道细细的折痕。"
CONSTRAINTS_FLASH_TINT = (
    "极浅的白色纸面，几乎没有颜色（只带极淡的灰调），整体明度很高；纸面铺满整个画面，四边没有纸边、桌面、阴影或背景。"
    "右上角有一大团浓重的深色半色调网点飞溅，网点颗粒粗大、清晰锐利、颜色接近墨黑色，中心最密、向外逐渐变稀并散成细小的点。"
    "画面左侧、中部、下部保持完全干净的空白浅色纸面，没有任何网点、色斑或痕迹。"
    "整张图不含任何文字、汉字、字母、数字、标点、logo、水印，"
    "也不含任何昆虫、动物、人物、器物或可辨认的主体图形——只要纸张本身和印刷痕迹。"
)

REC: dict = {}          # 本次调用的留痕，写进 <out>.json
OUT: Path | None = None


def _write_rec() -> None:
    if OUT is not None and REC:
        try:
            OUT.with_suffix(".json").write_text(json.dumps(REC, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            print(f"⚠ 留痕 json 没写成：{e}", file=sys.stderr)


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    if REC:
        REC.setdefault("error", msg.splitlines()[0])
        _write_rec()
    raise SystemExit(1)


def _ark_key() -> str:
    k = os.getenv("ARK_API_KEY", "").strip()
    if not k:
        die("没有 ARK_API_KEY：请先在当前环境设置该变量。")
    return k


def _keep_raw(raw: bytes) -> Path:
    p = OUT.with_suffix(".raw")
    p.write_bytes(raw)
    return p


def call_b64(body: dict) -> bytes:
    """POST 到 ARK，b64_json 取图；网络错误重试 3 次（大响应偶尔 IncompleteRead / 连接重置）。"""
    req = urllib.request.Request(ARK_ENDPOINT, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {_ark_key()}"})
    t0 = time.time()
    data = None
    attempts = REC.setdefault("attempts", [])
    for i in range(3):
        if i:
            print("  ⚠ 上一次请求可能已经生成并计费（尤其是 IncompleteRead），重发会再算一张", file=sys.stderr)
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.loads(r.read())
            attempts.append("ok")
            break
        except urllib.error.HTTPError as e:
            attempts.append(f"HTTP {e.code}")
            die(f"ARK 返回 {e.code}：{e.read().decode(errors='replace')[:400]}")
        except Exception as e:
            attempts.append(f"{type(e).__name__}: {e}")
            print(f"重试 {i + 1}/3：{type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(3)
    REC["secs"] = round(time.time() - t0, 1)
    if data is None:
        die("3 次重试都失败：" + attempts[-1])
    REC["usage"] = data.get("usage")
    try:
        return base64.b64decode(data["data"][0]["b64_json"])
    except Exception:
        die(f"响应里没有图片：{json.dumps(data, ensure_ascii=False)[:400]}")


def decode(raw: bytes):
    """校验魔数并完整解码；失败时原始字节落到 <out>.raw 再 die。"""
    from PIL import Image
    if raw[:8] != PNG_MAGIC:
        die(f"返回的不是 PNG（魔数 {raw[:8].hex()}）。原始字节已留在 {_keep_raw(raw)}")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        return im
    except Exception as e:
        die(f"图解不开（可能截断）：{type(e).__name__}: {e}\n  原始字节已留在 {_keep_raw(raw)}")


def gen_flash(prompt: str, out: Path) -> None:
    """Flash：b64_json 直取 → 尺寸必须等于请求 → Lanczos 放大到 2160×2880。"""
    from PIL import Image
    body = {"model": FLASH_MODEL, "prompt": prompt, "size": FLASH_SIZE, "n": 1, "watermark": False,
            "response_format": "b64_json", "output_format": "png"}      # Flash 不支持组图，不带 sequential_image_generation
    raw = call_b64(body)
    im = decode(raw)
    REC["got_size"] = f"{im.width}x{im.height}"
    want = tuple(int(x) for x in FLASH_SIZE.split("x"))
    if im.size != want:
        die(f"Flash 回的是 {im.width}×{im.height}，请求的是 {FLASH_SIZE}：不放大，免得拉伸变形 / 糊。\n"
            f"  原始字节已留在 {_keep_raw(raw)}")
    try:
        im.convert("RGB").resize(FINAL_SIZE, Image.LANCZOS).save(out, "PNG")
    except Exception as e:
        die(f"写不了 {out}：{type(e).__name__}: {e}\n  原始字节已留在 {_keep_raw(raw)}")
    print(f"  Flash 原图 {im.width}×{im.height} → Lanczos 放大 1.16× 到 {FINAL_SIZE[0]}×{FINAL_SIZE[1]}"
          f"（清晰度约为 lite 的 70% 到 80%）", flush=True)


def gen_lite(prompt: str, out: Path) -> None:
    """lite：原生 2160×2880，b64_json 直取（不走 TOS 下载）。"""
    body = {"model": MODEL, "prompt": prompt, "size": SIZE, "n": 1, "watermark": False,
            "response_format": "b64_json",
            "output_format": "png",          # ← 少了这行就是 JPEG
            "sequential_image_generation": "disabled"}
    raw = call_b64(body)
    im = decode(raw)
    REC["got_size"] = f"{im.width}x{im.height}"
    try:
        out.write_bytes(raw)
    except OSError as e:
        die(f"写不了 {out}：{e}\n  原始字节已留在 {_keep_raw(raw)}")


def gen_ark_cli(prompt: str, out: Path) -> None:
    cmd = [sys.executable, str(ARK_IMAGE), "--prompt", prompt, "--out", str(out),
           "--size", SIZE, "--model", MODEL, "--no-fallback"]
    t0 = time.time()
    r = subprocess.run(cmd)
    REC["secs"] = round(time.time() - t0, 1)
    if r.returncode != 0:
        die(f"ark_image.py 退出码 {r.returncode}")


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["flash", "lite"], default="flash", help="flash（默认）/ lite（即将下线）")
    ap.add_argument("--paper", metavar="#RRGGBB", help="目标纸色（先用 pick_paper.py 挑）。给了就走「质感 + 事后上色」，仅 flash 引擎；提示词可省略")
    ap.add_argument("prompt", nargs="?", default=None, help="纸色与质感：写「极浅、接近白色的 X 色纸面」和网点颜色（「浓重、粗大的深 X 色」）；不要写主体和文字")
    ap.add_argument("-o", "--out", required=True, help="输出 .png 路径，例如 第N集-XX/素材/tex_<名>.png")
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()   # 一律绝对路径，避开 ark_image.py 的 basename 陷阱
    if out.suffix.lower() != ".png":
        die(f"底图必须是 .png（当前 {out.suffix}）。\n"
            f"  纸纹和网点是高频内容，JPEG 会出块状伪影，垫在文字层下面会脏。")
    try:                                          # 付费之前先确认能写
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        die(f"建不了输出目录 {out.parent}：{e}")
    if not os.access(out.parent, os.W_OK):
        die(f"输出目录不可写：{out.parent}（还没调用 API，没花钱）")
    try:
        from PIL import Image
    except ImportError:
        die("需要 Pillow：pip install -r requirements.txt")

    if args.paper:
        if args.engine != "flash":
            die("--paper 只支持 flash 引擎（lite 引擎请直接在提示词里写颜色）")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", args.paper):
            die(f"--paper 要写成 #RRGGBB（收到 {args.paper!r}）")
        args.paper = args.paper.upper()
        args.prompt = args.prompt or DEFAULT_TEXTURE
        cons = CONSTRAINTS_FLASH_TINT
    else:
        if not args.prompt:
            die("缺提示词：不加 --paper 时要写纸色与质感（见 -h）")
        cons = CONSTRAINTS_FLASH if args.engine == "flash" else CONSTRAINTS
    prompt = f"复古丝网印刷用的空白纸张扫描件。{args.prompt}\n{cons}"
    flash = args.engine == "flash"
    backend = "Flash 直连 b64" if flash else ("ark_image.py" if ARK_IMAGE.exists() else "lite 直连 b64")
    OUT = out
    REC.update({"engine": args.engine, "backend": backend, "model": FLASH_MODEL if flash else MODEL,
                "size": FLASH_SIZE if flash else SIZE, "user_prompt": args.prompt, "prompt": prompt,
                "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    # flush：stdout 被重定向/管道接走时是块缓冲的，不 flush 这行会排到子进程输出之后，读日志时因果颠倒。
    print(f"→ {REC['model']}  {REC['size']}  [{backend}]  → {out}", flush=True)

    if flash:
        gen_flash(prompt, out)
    elif ARK_IMAGE.exists():
        gen_ark_cli(prompt, out)
    else:
        gen_lite(prompt, out)

    # ── 落盘后自己验，不只信 exit code ──────────────────────────────
    if not out.exists():
        die(f"退出码是 0，但文件不存在：{out}")
    with open(out, "rb") as f:
        if f.read(8) != PNG_MAGIC:
            die(f"落盘的不是真 PNG（后缀 ≠ 真实格式）：{out}\n"
                f"  lite 走 ark_image.py 时多半是降级到了 4.5 —— 它不认 output_format，服务端默认回 JPEG。")
    try:
        with Image.open(out) as im:
            im.load()                 # 真正解码，否则截断的图要到用的时候才炸
            w, h = im.size
            arr = np.asarray(im.convert("RGB"))
    except Exception as e:
        die(f"魔数是 PNG，但图读不出来（可能截断或损坏）：{out}\n  {type(e).__name__}: {e}")

    if abs(w / h - EXPECT_RATIO) > 0.001:
        die(f"比例 {w}×{h} = {w / h:.4f}，应为 {EXPECT_RATIO}。\n"
            f"  CSS 用的是 background:cover，比例不符会居中裁切，**钉在右上角的网点会被裁出画面，而且不报任何错**。")
    if (w, h) != FINAL_SIZE:
        die(f"尺寸 {w}×{h} ≠ {FINAL_SIZE[0]}×{FINAL_SIZE[1]}（shot.js 出图的物理像素）。低于它要放大，高频细节会掉。")

    if args.paper:                                # 事后上色：原图另存，out 换成上色后的
        from tint_bg import tint_array
        src_copy = out.with_name(f"{out.stem}_src{out.suffix}")
        try:
            arr, Lref, Ldark = tint_array(arr, args.paper)
        except SystemExit as e:
            out.replace(src_copy)
            die(f"{e}\n  已付费的原图留在 {src_copy.name}，不要当底图用。")
        out.replace(src_copy)
        Image.fromarray(arr).save(out)
        REC.update({"paper_target": args.paper, "src_kept": str(src_copy),
                    "src_paper_L": round(Lref, 1), "src_dot_L": round(Ldark, 1)})
        print(f"  事后上色：原图纸面 L* {Lref:.1f} / 网点最深 L* {Ldark:.1f} → 目标 {args.paper}；原图另存 {src_copy.name}")

    hexv, L = paper_color(arr)
    x = dot_left_css(arr)
    REC.update({"final_size": f"{w}x{h}", "paper": hexv, "L": round(L, 1), "dot_left_css": x})
    if L <= MIN_L:
        bad = out.with_name(f"{out.stem}_rejected_L{L:.0f}{out.suffix}")
        out.replace(bad)
        REC["rejected_as"] = str(bad)
        die(f"纸色 {hexv} L* {L:.1f} ≤ {MIN_L}（DNA 规则 1）：提示词写「极浅、接近白色」重生。\n"
            f"  这张已改名为 {bad.name}，不要拿来用。")
    REC["status"] = "ok"
    _write_rec()

    print(f"✓ {w}×{h}  PNG  {out.stat().st_size // 1024} KB")
    print(f"  纸色实测 {hexv}  L* {L:.1f}（> {MIN_L} ✓）")
    print(f"  网点团最左 CSS x = {x if x is not None else '（没找到暗网点，人眼看一下网点是不是太淡）'}"
          f"    ← 08 规则「答案图标题色块不越过 x≈714」以此为准")
    print(f"  留痕：{out.with_suffix('.json')}")
    print()
    print("⚠️ 接着做三件事，脚本查不了或没查：")
    print(f"   ① python3 {Path(__file__).resolve().parent / 'measure_bg.py'} {out}   （对已用纸色算 ΔE，贴近旧集就重生）")
    print("   ② 人眼确认图里没有文字笔画（即使 prompt 明令零文字，模型偶尔还是会画）")
    print("   ③ build 脚本里的 PAPER 写成上面的实测 hex（不一致的话 SVG 主体的纹理线会浮出来）")
    print(f"MEDIA:{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
