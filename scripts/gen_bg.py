#!/usr/bin/env python3
"""生成小红书竖版「纯质感底图」—— 分层架构的视觉层。

底图只负责质感：纸纹、半色调网点飞溅、褪色渍、折痕。
**不画任何主体，也不写任何文字** —— 主体由 SVG 画（颜色能跟配色走、位置像素级可控），
文字由 HTML 排版（中文永不出错）。

用法：
  python3 scripts/gen_bg.py -o assets/tex_blush.png \\
      "极浅裸粉色纸面，纸浆纤维清晰，轻微折痕与泛旧"

  # 换色系时才需要跑；同一系列的首图和答案图必须共用同一张底图。

────────────────────────────────────────────────────────────────────────
为什么每个参数都是写死的（都是实测换来的，别改）
────────────────────────────────────────────────────────────────────────

--size 2160x2880   HTML 画布 1080×1440 CSS px，shot.js 用 deviceScaleFactor:2
                   → 输出 2160×2880 物理像素。底图必须按**物理**像素出。
                   实测：1680×2240 的底图被放大 1.286×，拉普拉斯方差从 64.3 掉到
                   24.3（**只剩 38%**）。纸纹和网点全是高频细节，放大后
                   「从印刷变成打印机脏了」，而且只在全尺寸暴露、缩略图看不出来。

比例必须 0.75      2160/2880 = 1080/1440 = 0.75。CSS 是 `background: url() center/cover`，
                   `cover` 的语义是「铺满并裁掉多余」。比例一旦不等于 0.75，
                   两侧会被居中裁掉 —— **钉在右上角的网点会被直接裁出画面，且不报任何错**，
                   底图只是看起来「变干净了」。所以下面有一条硬断言。

--model 5.0-lite   +
--no-fallback      不是为了避免 400，是为了**堵死静默降级成 JPEG**。
                   实测机制（mac mini 侧读 ark_image.py 源码确认）：
                     降级到 4.5 时脚本会自动摘掉 output_format
                     → 请求成功(200) → 服务端默认返回 JPEG
                     → 字节写进你给的 .png → 「名字叫 .png 的 JPEG」
                     → exit code 仍是 0，只有 stderr 一行提示
                   JPEG 压缩对网点这种高频内容会出块状伪影，垫在文字层下面会脏。
                   （--model 一给，fallback 链长度就是 1，--no-fallback 其实是 no-op，
                     但保留它把「不要降级」这个意图写在命令行上。）

两个后端         mac mini 有 ark_image.py，MacBook 没有。
                   2026-08-23 按 mini 的建议「别自己写 HTTP，用 ark_image.py」改造后，
                   本脚本在 **MacBook 上就没有后端了** —— 而这一点当时没人注意到。
                   后果：第 2 集在 MacBook 生底图时只能绕开本脚本，用 kaiswords/imagen
                   那条路（它的 generate() 不传 output_format，服务端默认返回 JPEG），
                   于是底图成了「名字叫 .png 的 JPEG」，本脚本的魔数自验根本没机会跑。
                   → 现在两台都能跑：探测到 ark_image.py 就走它，否则走内置 HTTP 后端。
                     两条路落到**同一套落盘自验**，规格保证不依赖走的是哪条。

--out 绝对路径     ark_image.py 对绝对路径原样使用、父目录自动建。
                   ⚠️ 相对路径有静默陷阱：它走 `default_media_dir() / p.name`，
                   `.name` 只取 basename —— `--out sub/dir/x.png` 会把 `sub/dir/`
                   **静默丢掉**。所以本脚本一律转成绝对路径再传。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ── 后端 A：ark_image.py（mac mini）。探测不到就自动走后端 B，不再直接报错。
# 若你的环境里已有一个封装好的生图 CLI，把它的路径放进 ARK_IMAGE_CLI 环境变量，
# 本脚本会优先调它；没有就走下面的后端 B（直连 HTTP）。两条路落到同一套落盘自验。
ARK_IMAGE = Path(os.environ.get("ARK_IMAGE_CLI", "/nonexistent/ark_image.py"))

# ── 后端 B：直连 ARK（MacBook）。需要环境变量 ARK_API_KEY。
#    刻意不复用 kaiswords/imagen/seedream.py —— 它的 generate() 不传 output_format
#    （服务端默认就回 JPEG），而且 config.from_env() 的 SEEDREAM_MODEL 默认值是 4.0，
#    两条都会把我们要的规格悄悄改掉。这里的 body 全部写死。
ARK_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

MODEL = "doubao-seedream-5-0-lite-260128"
SIZE = "2160x2880"
EXPECT_RATIO = 0.75          # 2160/2880，必须和 HTML 画布 1080/1440 精确相同
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# 每次都追加。少了这三句，模型会自作主张加字、加虫、把网点撒得到处都是。
CONSTRAINTS = (
    "只在画面右上角有一片半色调网点飞溅，网点颗粒清晰锐利。"
    "画面左侧、中部、下部保持完全干净的空白纸面，没有任何网点、色斑或痕迹。"
    "整张图不含任何文字、汉字、字母、数字、标点、logo、水印，"
    "也不含任何昆虫、动物、人物、器物或可辨认的主体图形——只要纸张本身和印刷痕迹。"
)


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(1)


def gen_direct(prompt: str, out: Path) -> None:
    """后端 B：直连 ARK。参数全部写死，output_format 是这里的重点。"""
    import json
    import os
    import urllib.error
    import urllib.request

    key = os.getenv("ARK_API_KEY", "").strip()
    if not key:
        die("没有后端可用。\n"
            f"  没有可用的生图 CLI（ARK_IMAGE_CLI 未设或指向不存在的文件），\n"
            "  直连 ARK 又缺 ARK_API_KEY。\n"
            "  → 在 shell 里 export ARK_API_KEY=... 后重跑。\n"
            "  ⚠️ 不要改用 kaiswords/imagen 绕过本脚本：它不传 output_format，\n"
            "     拿回来的是 JPEG，而底图必须是 PNG（纸纹网点会出块状伪影）。")

    body = {
        "model": MODEL,
        "prompt": prompt,
        "size": SIZE,
        "n": 1,
        "watermark": False,
        "response_format": "url",
        "output_format": "png",          # ← 少了这行就是 JPEG。整个脚本的存在意义
        "sequential_image_generation": "disabled",
    }
    req = urllib.request.Request(
        ARK_ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        die(f"ARK 返回 {e.code}：{e.read().decode(errors='replace')[:400]}")
    except Exception as e:
        die(f"请求 ARK 失败：{type(e).__name__}: {e}")

    try:
        url = data["data"][0]["url"]
    except (KeyError, IndexError):
        die(f"响应里没有图片 URL：{json.dumps(data)[:400]}")

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            out.write_bytes(r.read())
    except Exception as e:
        die(f"图生成了但下载失败：{type(e).__name__}: {e}\n  URL（24h 有效）：{url}")


def main() -> int:
    ap = argparse.ArgumentParser(description="生成无主体、无文字的纯质感底图")
    ap.add_argument("prompt", help="只描述纸张质感与颜色，不要描述主体、文字或网点位置")
    ap.add_argument("-o", "--out", required=True, help="输出路径（会转成绝对路径）")
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()   # 一律绝对路径，避开 basename 陷阱
    if out.suffix.lower() != ".png":
        die(f"底图必须是 .png（当前 {out.suffix}）。\n"
            f"  纸纹和网点是高频内容，JPEG 会出块状伪影，垫在文字层下面会脏。")

    prompt = f"复古丝网印刷用的空白纸张扫描件。{args.prompt}\n{CONSTRAINTS}"

    backend = "ark_image.py" if ARK_IMAGE.exists() else "直连 ARK"
    # flush：stdout 被重定向/管道接走时是块缓冲的，不 flush 这行会排到
    # 子进程输出**之后**才出现，读日志时因果颠倒。
    print(f"→ {MODEL}  {SIZE}  [{backend}]  → {out}", flush=True)

    if ARK_IMAGE.exists():
        cmd = [
            sys.executable, str(ARK_IMAGE),  # 用 sys.executable，不用字符串 "python3"
            "--prompt", prompt,
            "--out", str(out),
            "--size", SIZE,
            "--model", MODEL,
            "--no-fallback",
        ]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            die(f"ark_image.py 退出码 {r.returncode}")
    else:
        gen_direct(prompt, out)

    # ── 落盘后自己验，不只信 exit code ──────────────────────────────
    # ark_image.py 有魔数防护，但它是 stderr 一行提示、exit code 仍为 0，
    # 在 subprocess 调用里极容易被忽略。这里把"应该没问题"变成"不对就炸"。
    if not out.exists():
        die(f"退出码是 0，但文件不存在：{out}")

    with open(out, "rb") as f:
        if f.read(8) != PNG_MAGIC:
            die(f"落盘的不是真 PNG（后缀 ≠ 真实格式）：{out}\n"
                f"  多半是降级到了 4.5 —— 它不认 output_format，服务端默认返回 JPEG。")

    try:
        from PIL import Image
    except ImportError:
        die("需要 Pillow 做尺寸/比例校验：pip install pillow")

    # 单独包住读图：原先它和 import 共用一个 `except ImportError`，
    # 图截断/损坏时会裸抛 traceback，而不是走 die() 给出可读的失败原因。
    try:
        with Image.open(out) as im:
            im.load()                 # 真正解码，否则截断的图要到用的时候才炸
            w, h = im.size
            fmt = im.format
    except Exception as e:
        die(f"魔数是 PNG，但图读不出来（可能截断或损坏）：{out}\n"
            f"  {type(e).__name__}: {e}")

    ratio = w / h
    if abs(ratio - EXPECT_RATIO) > 0.001:
        die(f"比例 {w}×{h} = {ratio:.4f}，应为 {EXPECT_RATIO}。\n"
            f"  CSS 用的是 background:cover，比例不符会居中裁切，\n"
            f"  **钉在右上角的网点会被裁出画面，而且不报任何错**。")

    print(f"✓ {w}×{h}  {fmt}  {out.stat().st_size // 1024} KB")
    print(f"  与 HTML 输出 1:1（画布 1080×1440 × deviceScaleFactor 2 = 2160×2880），零放大")
    print()
    print("⚠️ 人眼确认两件事，脚本查不了：")
    print("   ① 图里确实没有文字笔画（即使 prompt 明令零文字，模型偶尔还是会画）")
    print("   ② 底色和 build.py 里的 PAPER 一致（不一致的话 SVG 主体的纹理线会浮出来）")
    print(f"MEDIA:{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
