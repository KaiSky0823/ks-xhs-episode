#!/usr/bin/env python3
"""用 Seedream 5.0 生成「插画主体」（人物 / 动物 / 吉祥物演戏），不是底图。底图用 gen_bg.py。

和 gen_bg.py 的区别：
  - 模型默认 flash（约 12–28 秒/张，便宜）；道具、姿势反复画错时换 pro（约 50–65 秒/张）。
  - 图用 `response_format: b64_json` 直接拿，**不走 TOS 下载**（TOS 下载经常 TLS 超时，所以用 b64_json）。
  - Pro / Flash 不支持组图，请求体里不带 sequential_image_generation。
  - 提示词写进文件再传 @路径，别在 shell 里内联中文（shell 会吞/拆字符）。
  - 每次调用都把提示词、模型、参考图、尝试记录、耗时、实际尺寸写进 <out>/<name>.json，成败都留痕。
  - 拿回来的不是 PNG、截断、解不开：exit 1，json 写 error，原始字节留在 <name>.raw（不写成 .png）。
  - <out>/<name>.png 已存在时直接报错（不覆盖已付费的旧图），换个名字。

用法（在放各集目录的那一层执行；KIT = 本 skill 目录）：
  python3 $KIT/scripts/gen_art.py c3_a @第N集-XX/生图/prompt_c3.txt --out 第N集-XX/生图/raw --model flash --size 2048x2048
  先设置环境变量 `ARK_API_KEY` 提供 API key；脚本不会打印或持久化 key。
  --out 默认是当前目录下的 raw/；在 skill 目录里跑会把图写进 skill 仓库，脚本会警告。

模型 id（2026-10-22 实测都能调通）：
  flash  doubao-seedream-5-0-flash-260915   最大约 462 万像素（2048×2048、1536×1536 可以，2160×2880 不行）
  pro    doubao-seedream-5-0-pro-260628     同上；按张计价更贵，想省用 1536×1536
  lite   doubao-seedream-5-0-lite-260128    即将下线；底图默认用 gen_bg.py --engine flash
--image 参考图（URL 或本地文件，可多次传）：吉祥物参考图已实测（见 references/12 第三节）；
  注意 6 次里 3 次清楚保持、2 次部分漂移、1 次失败，要逐张看；两张以上参考图未测。
成本：网络中断（IncompleteRead 等）后脚本会重发，上一次可能已经计费，stderr 会提示；json 的 attempts 记了几次。
"""
import argparse, base64, io, json, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path

ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODELS = {"flash": "doubao-seedream-5-0-flash-260915", "pro": "doubao-seedream-5-0-pro-260628", "lite": "doubao-seedream-5-0-lite-260128"}
PNG = b"\x89PNG\r\n\x1a\n"
KIT = Path(__file__).resolve().parents[1]


def api_key() -> str:
    return os.getenv("ARK_API_KEY", "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="输出文件名（不带后缀），例如 c3_a")
    ap.add_argument("prompt", help="提示词文本，或 @文件路径")
    ap.add_argument("--out", default="raw", help="输出目录（默认 ./raw；建议写 第N集-XX/生图/raw）")
    ap.add_argument("--size", default="2048x2048")
    ap.add_argument("--model", default="flash", help="flash / pro / lite，或完整模型 id")
    ap.add_argument("--image", action="append", default=[],
                    help="参考图（URL 或本地文件，可多次传）。吉祥物参考图已实测，造型会漂移，要逐张看")
    a = ap.parse_args()

    out = Path(a.out)
    if out.resolve().is_relative_to(KIT):      # 典型情况：在 skill 根目录跑、--out 用默认的 raw
        print(f"⚠ 图会写进 skill 目录 {out.resolve()}（skill 是 git 仓库）。建议在放各集目录的那一层跑，--out 第N集-XX/生图/raw", file=sys.stderr)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"ERR 建不了输出目录 {out}：{e}（还没调用 API）", file=sys.stderr); return 2
    if not os.access(out, os.W_OK):
        print(f"ERR 输出目录不可写：{out}（还没调用 API）", file=sys.stderr); return 2
    png_path, json_path = out / f"{a.name}.png", out / f"{a.name}.json"
    if png_path.exists():
        print(f"ERR {png_path} 已存在，不覆盖已付费的旧图。换个名字（例如 {a.name}_2）。", file=sys.stderr); return 2

    model = MODELS.get(a.model, a.model)
    rec = {"name": a.name, "model": model, "size": a.size, "refs": a.image, "n_ref": len(a.image),
           "time": time.strftime("%Y-%m-%d %H:%M:%S")}

    def fail(msg, code=1, raw=None):
        rec["error"] = msg
        if raw is not None:
            (out / f"{a.name}.raw").write_bytes(raw); rec["raw_kept"] = f"{a.name}.raw"
        json_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print("ERR", msg[:300], file=sys.stderr); return code

    # ── 参数检查先于调用（失败也留 json，不花钱）──
    if a.prompt.startswith("@"):
        pf = Path(a.prompt[1:])
        if not pf.is_file():
            return fail(f"提示词文件不存在：{pf}", 2)
        prompt = pf.read_text(encoding="utf8").strip()
        rec["prompt_file"] = str(pf)
    else:
        prompt = a.prompt
    rec["prompt"] = prompt
    if not prompt:
        return fail("提示词是空的", 2)
    imgs = []
    for p in a.image:
        if p.startswith("http"):
            imgs.append(p); continue
        if not Path(p).is_file():
            return fail(f"参考图不存在：{p}", 2)
        b = Path(p).read_bytes()
        kind = "png" if b[:8] == PNG else "jpeg" if b[:3] == b"\xff\xd8\xff" else None
        if kind is None:
            return fail(f"参考图不是 PNG / JPEG：{p}", 2)
        imgs.append(f"data:image/{kind};base64," + base64.b64encode(b).decode())
    key = api_key()
    if not key:
        return fail("没有 ARK_API_KEY：请先在当前环境设置该变量。", 2)

    body = {"model": model, "prompt": prompt, "size": a.size, "n": 1, "watermark": False,
            "response_format": "b64_json", "output_format": "png"}
    if model == MODELS["lite"]:
        body["sequential_image_generation"] = "disabled"
    if imgs:
        body["image"] = imgs if len(imgs) > 1 else imgs[0]
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})

    t0 = time.time(); data = None; rec["attempts"] = []
    for attempt in range(3):               # 大响应偶尔 IncompleteRead / 连接重置
        if attempt:
            print("  ⚠ 上一次请求可能已经生成并计费（尤其是 IncompleteRead），重发会再算一张", file=sys.stderr)
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.loads(r.read())
            rec["attempts"].append("ok"); break
        except urllib.error.HTTPError as e:
            rec["attempts"].append(f"HTTP {e.code}")
            rec["secs"] = round(time.time() - t0, 1)
            return fail(f"{e.code} {e.read().decode(errors='replace')[:600]}")
        except Exception as e:
            rec["attempts"].append(f"{type(e).__name__}: {e}")
            print(f"重试 {attempt + 1}/3：{type(e).__name__}: {e}", file=sys.stderr); time.sleep(3)
    rec["secs"] = round(time.time() - t0, 1)
    if data is None:
        return fail("3 次重试都失败：" + rec["attempts"][-1])
    rec["usage"] = data.get("usage")
    try:
        img = base64.b64decode(data["data"][0]["b64_json"])
    except Exception:
        return fail("响应里没有图片：" + json.dumps(data, ensure_ascii=False)[:600])
    rec["bytes"] = len(img)

    # ── 落盘前验：必须是能完整解码的 PNG ──
    if img[:8] != PNG:
        return fail(f"返回的不是 PNG（魔数 {img[:8].hex()}）", raw=img)
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(img)); im.load()
    except Exception as e:
        return fail(f"图解不开（可能截断）：{type(e).__name__}: {e}", raw=img)
    rec["got_size"] = f"{im.width}x{im.height}"
    if rec["got_size"] != a.size:
        print(f"⚠ 请求 {a.size}，实际回 {rec['got_size']}", file=sys.stderr)

    png_path.write_bytes(img)
    json_path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK", png_path, rec["got_size"], rec["secs"], "s", rec["usage"]); return 0


if __name__ == "__main__":
    sys.exit(main())
