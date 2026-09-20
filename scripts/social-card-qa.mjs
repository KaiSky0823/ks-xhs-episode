#!/usr/bin/env node
/**
 * social-card-qa —— 出图前的几何硬门禁。
 *
 * 用法：
 *   node assets/social-card-qa.mjs <html> [--width 1080] [--height 1440] [--json]
 *
 * exit 0 = 全部通过（可能有 WARN）；exit 1 = 有 FAIL，不要交付。
 *
 * 为什么要它：肉眼验收会漏几何问题。实测漏过的：中文 line-height<1 导致相邻行字形
 * 互相碾压、inline-block 的 padding 撑破行框压到上一行、标注跑出画布右边被裁、
 * 画面 40% 是无内容空白。这些都是可测量的，不该靠"感觉"。
 *
 * 规则：R1 溢出 · R2 底部碰撞 · R3 越界 · R4 行墨迹碾压 · R5 最小字号
 *       R6 字体降级 · R7 模板变量泄漏 · R8 内容覆盖率
 * R1/R2/R3 的思路参考了 op7418/guizang-social-card-skill（AGPL-3.0），代码为独立实现、
 * 未复制其源码。R4/R7/R8 是本机自加（都是实测踩过的坑）。
 */

import { chromium } from 'playwright';
import path from 'node:path';
import process from 'node:process';


// 阈值。R1/R2/R3/R4 是几何容差；R5/R8 是经验值，见各自注释。
const T = {
  overflow: 4,        // 内容超出画布多少像素算溢出
  collision: 6,       // 与底部固定元素重叠多少像素算碰撞
  outOfBounds: 4,     // 元素越过画布边界多少像素算越界
  lineOverlap: 2,     // 相邻行「墨迹」重叠多少像素算碾压（不是行盒重叠，见 R4）
  minFont: 16,        // 低于此在手机上不可读（1080 图缩到 390 宽 = 2.77 倍缩小）
  bodyFont: 24,       // 低于此正文吃力，WARN。页眉页脚/标注类小字本来就该小，别定太高否则刷屏
  minCoverage: 0.35,  // 内容覆盖率低于此画面显空，WARN。经验值，非实测标定
};

const BOTTOM_FIXED = ['.signature', '.source-line', '.foot', 'footer'];

const args = process.argv.slice(2);
const htmlPath = args.find(a => !a.startsWith('--'));
const flag = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
};

if (!htmlPath) {
  console.error('Usage: node social-card-qa.mjs <html> [--width 1080] [--height 1440] [--json]');
  process.exit(2);
}

const W = parseInt(flag('width', '1080'), 10);
const H = parseInt(flag('height', '1440'), 10);
const asJson = args.includes('--json');

// 优先用系统装的 Chrome。playwright 自带的 chromium 放在 ~/Library/Caches/ms-playwright，
// 这台机器上那个目录会被周期性清掉（实测装好后又消失，capture.js 一度也因此完全跑不了），
// 依赖它等于让工具随机失效。系统 Chrome 不在缓存目录里，稳定得多。
const browser = await chromium.launch({ channel: 'chrome' }).catch(async e => {
  console.error('系统 Chrome 启动失败，回落到 playwright 自带 chromium：' + e.message.split('\n')[0]);
  return chromium.launch();
});
const page = await browser.newPage({ viewport: { width: W, height: H } });
await page.goto('file://' + path.resolve(htmlPath), { waitUntil: 'networkidle' });

// 等字体真的就绪，而不是睡一个定时器。字体没就绪时测出来的行框全是错的。
await page.evaluate(() => document.fonts.ready);

const report = await page.evaluate(
  ({ W, H, T, BOTTOM_FIXED }) => {
    const fails = [];
    const warns = [];
    const px = n => Math.round(n * 10) / 10;

    // 只看"自己直接持有文本"的元素，避免把祖先容器算成一个巨大文本块
    const textEls = [...document.querySelectorAll('body *')].filter(el => {
      if (!el.childNodes.length) return false;
      const own = [...el.childNodes]
        .filter(n => n.nodeType === 3)
        .map(n => n.textContent.trim())
        .join('');
      if (!own) return false;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });

    // 累计元素及其祖先的旋转角（弧度）。倾斜排版常把 rotate 加在父容器上，
    // 只看元素自身的 transform 会漏掉。
    const rotOf = el => {
      let rad = 0;
      for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
        const t = getComputedStyle(n).transform;
        const m = /matrix\(([^)]+)\)/.exec(t || '');
        if (m) {
          const [a, b] = m[1].split(',').map(Number);
          rad += Math.abs(Math.atan2(b, a));
        }
      }
      return rad;
    };

    // getClientRects() 返回的是"行盒片段"，同一行里换个 inline 元素/字号就会多出一个 rect。
    // 直接按 top 排序比较相邻项，会把「0.05」和「秒」当成两行误报重叠。
    // 所以先按垂直位置聚成真正的行。
    // 聚类判据用「top 差 < 行高的 40%」，不用「中心点落在已有行跨度内」——后者对
    // 带 padding 的 inline-block 太宽容，会把撑破行盒的那一行并进上一行，直接漏报（实测漏过）。
    // 元素被旋转时，同一行里相隔 D 像素的两个片段 top 天然差 D×sinθ，
    // 不把这一项加进容差，倾斜排版会被整片误报成"行重叠"（实测误报过 98.6px）。
    const linesOf = (el, lh) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      let rects = [...range.getClientRects()]
        .filter(r => r.width > 1 && r.height > 1)
        .sort((a, b) => a.top - b.top);
      // getClientRects 会把块级子元素（如 <small>、<div>）的**外框**也算一个 rect，
      // 它纵向包住自己内部的行 —— 直接排序比较会把「外框」和「它的第一行」当成
      // 相邻两行，报出根本不存在的碾压（实测误报 18px）。
      // 凡是纵向完整包含另一个 rect 的，都是容器外框，剔掉。
      rects = rects.filter((r, i) =>
        !rects.some((o, j) => j !== i && o.top >= r.top - 0.5 && o.bottom <= r.bottom + 0.5
                              && (o.bottom - o.top) < (r.bottom - r.top) - 1));
      const tol = Math.max(4, (lh || 0) * 0.4 + el.getBoundingClientRect().width * Math.sin(rotOf(el)));
      const lines = [];
      for (const r of rects) {
        const cur = lines[lines.length - 1];
        if (cur && Math.abs(r.top - cur.firstTop) < tol) {
          cur.top = Math.min(cur.top, r.top);
          cur.bottom = Math.max(cur.bottom, r.bottom);
          cur.left = Math.min(cur.left, r.left);
          cur.right = Math.max(cur.right, r.right);
        } else {
          lines.push({ top: r.top, bottom: r.bottom, left: r.left, right: r.right, firstTop: r.top });
        }
      }
      return lines;
    };

    const label = el => {
      const t = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 18);
      const cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : '';
      return `${el.tagName.toLowerCase()}${cls} "${t}"`;
    };

    // ---- R7 模板变量泄漏（放最前：泄漏了后面测什么都没意义）----
    // 必须查整份文档而不是只查 body：big_template 的 {{BG_IMAGE}} 就写在 <style> 里，
    // 只查 body.innerHTML 会让这条规则对真实模板完全失效（阴性对照实测漏报过）。
    const leaked = [...new Set(document.documentElement.outerHTML.match(/\{\{[A-Z_]+\}\}/g) || [])];
    // {{LOGO}} 是 capture.js 在截图时注入的，所以在截图前跑 QA 时它必然还在。
    // 只提醒，不拦——否则「先验证再出图」这个更自然的顺序永远过不了。
    const pendingLogo = leaked.includes('{{LOGO}}');
    const realLeaks = leaked.filter(v => v !== '{{LOGO}}');
    if (realLeaks.length) {
      fails.push({ rule: 'R7', msg: `模板变量未替换，会渲染成字面量或让样式静默失效: ${realLeaks.join(', ')}`, fix: '逐个替换；不用的填 none / 空字符串' });
    }
    if (pendingLogo) {
      warns.push({ rule: 'R7', msg: '{{LOGO}} 尚未替换（capture.js 会在截图时注入）。若截图后仍在，才是真问题' });
    }

    // ---- R1 内容溢出画布 ----
    const se = document.scrollingElement || document.documentElement;
    const over = Math.max(se.scrollHeight - H, document.body.scrollHeight - H);
    if (over > T.overflow) {
      fails.push({ rule: 'R1', msg: `内容比画布高 ${px(over)}px`, fix: '减字号 / 减行数 / 收 padding。不要靠 overflow:hidden 藏掉' });
    }
    const overX = Math.max(se.scrollWidth - W, document.body.scrollWidth - W);
    if (overX > T.overflow) {
      fails.push({ rule: 'R1', msg: `内容比画布宽 ${px(overX)}px`, fix: '同上，横向' });
    }

    // ---- R2 与底部固定元素碰撞 ----
    for (const sel of BOTTOM_FIXED) {
      for (const fixed of document.querySelectorAll(sel)) {
        const fr = fixed.getBoundingClientRect();
        if (fr.height === 0) continue;
        for (const el of textEls) {
          if (fixed.contains(el) || el.contains(fixed)) continue;
          const r = el.getBoundingClientRect();
          const vOverlap = Math.min(r.bottom, fr.bottom) - Math.max(r.top, fr.top);
          const hOverlap = Math.min(r.right, fr.right) - Math.max(r.left, fr.left);
          if (vOverlap > T.collision && hOverlap > 0) {
            fails.push({ rule: 'R2', msg: `${label(el)} 压住 ${sel} ${px(vOverlap)}px`, fix: '给主内容留出底部空间，或把底部元素改成 flex margin-top:auto' });
          }
        }
      }
    }

    // ---- R3 越出画布边界 ----
    for (const el of textEls) {
      const r = el.getBoundingClientRect();
      const out = [];
      if (r.left < -T.outOfBounds) out.push(`左 ${px(-r.left)}px`);
      if (r.top < -T.outOfBounds) out.push(`上 ${px(-r.top)}px`);
      if (r.right > W + T.outOfBounds) out.push(`右 ${px(r.right - W)}px`);
      if (r.bottom > H + T.outOfBounds) out.push(`下 ${px(r.bottom - H)}px`);
      if (out.length) {
        fails.push({ rule: 'R3', msg: `${label(el)} 越界（${out.join(' / ')}）`, fix: '收窄宽度或改定位。越界部分会被直接裁掉' });
      }
    }

    // ---- R4 相邻行墨迹碾压 ----
    // 不能直接比 inline box 是否重叠。实测：Noto Serif SC 114px 的行盒高 164px（1.44em），
    // 而 line-height 只有 118.6px —— 行盒天然重叠 45px，视觉上却完全没事，
    // 因为汉字墨迹只占 em 的约 0.88，盒子里上下都是空白。
    // 所以用 canvas TextMetrics 实测这个字体这个字号下的真实墨迹高度，
    // 只有「墨迹」真的压上去才算失败。
    const ctx = document.createElement('canvas').getContext('2d');
    const inkSlack = el => {
      const cs = getComputedStyle(el);
      ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
      const m = ctx.measureText((el.textContent || '').trim().slice(0, 24) || '汉');
      const ink = m.actualBoundingBoxAscent + m.actualBoundingBoxDescent;
      const box = m.fontBoundingBoxAscent + m.fontBoundingBoxDescent;
      const fs = parseFloat(cs.fontSize);
      return {
        fs,
        lh: cs.lineHeight === 'normal' ? fs * 1.2 : parseFloat(cs.lineHeight),
        // 行盒里上下留白总量。测不到就退回一个保守值，宁可漏报也别刷屏误报。
        slack: ink > 0 && box > ink ? box - ink : fs * 0.4,
      };
    };

    // R4a 纯文本多行之间的碾压
    for (const el of textEls) {
      const { fs, lh, slack } = inkSlack(el);
      const lines = linesOf(el, lh);
      if (lines.length < 2) continue;
      for (let i = 0; i + 1 < lines.length; i++) {
        const a = lines[i], b = lines[i + 1];
        const boxOverlap = a.bottom - b.top;
        const h = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const inkOverlap = boxOverlap - slack;
        if (inkOverlap > T.lineOverlap && h > 0) {
          fails.push({
            rule: 'R4',
            msg: `${label(el)} 第 ${i + 1}/${i + 2} 行墨迹重叠 ${px(inkOverlap)}px（行盒重叠 ${px(boxOverlap)}px，留白 ${px(slack)}px）`,
            fix: `当前 line-height/font-size = ${(lh / fs).toFixed(2)}；这个字体在这个字号下至少需要 ${(1 + (T.lineOverlap - slack + boxOverlap) / fs).toFixed(2)} 左右`,
          });
          break;
        }
      }
    }

    // R4b 不透明背景块遮住了别人的墨迹。
    // R4a 只看同一元素内的行间碾压，抓不到「display:inline 的 padding 溢出行盒、
    // 用自己的底色盖住上一行」——阴性对照实测漏过这个，而它正是实战里最常见的一种。
    // 关键在于这类块是不透明的：它盖住什么就真的看不见什么，比墨迹相碰更严重。
    const alphaOf = bg => {
      const m = /rgba?\(([^)]+)\)/.exec(bg);
      if (!m) return 0;
      const p = m[1].split(',').map(Number);
      return p.length > 3 ? p[3] : 1;
    };
    const opaqueBlocks = [...document.querySelectorAll('body *')].filter(el => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      if (cs.position === 'absolute' || cs.position === 'fixed') return false; // 绝对定位的叠放是设计意图
      if (alphaOf(cs.backgroundColor) <= 0.5) return false;
      const r = el.getBoundingClientRect();
      return r.width > 4 && r.height > 4;
    });
    // 逐「行墨迹」比，而不是逐元素比：要抓的那个 case 里，黑块是被它盖住的那段文本的
    // 子元素（<span class=stamp> 在 <div> 里），按元素比会被父子关系整个排除掉。
    const inkLines = [];
    for (const el of textEls) {
      const { slack, lh } = inkSlack(el);
      for (const ln of linesOf(el, lh)) {
        inkLines.push({ el, top: ln.top + slack / 2, bottom: ln.bottom - slack / 2, left: ln.left, right: ln.right });
      }
    }
    for (const blk of opaqueBlocks) {
      const br = blk.getBoundingClientRect();
      const blkArea = Math.max(1, br.width * br.height);
      for (const L of inkLines) {
        // 祖先容器的背景画在后代文字之下，不构成遮挡。
        // 反过来（blk 是这段文本的后代）恰恰是要抓的，不能排除。
        if (blk.contains(L.el)) continue;
        const v = Math.min(br.bottom, L.bottom) - Math.max(br.top, L.top);
        const h = Math.min(br.right, L.right) - Math.max(br.left, L.left);
        // R4b 的垂直阈值比 R4a 宽，用「占该行墨迹高度的比例」而不是固定像素：
        // display:inline 的元素 padding 不参与行高计算，背景本来就会溢出行盒几像素，
        // 那是排版常态不是缺陷。要抓的是「盖掉一大块」，不是「边缘蹭到」。
        // 实测标定：真 bug（inline + padding-top 70px）重叠 76.7px = 墨迹高的 79%；
        // 正常色块（padding-top 4px）重叠 10.7px = 11%。取 15% 把两者干净分开。
        const inkH = Math.max(1, L.bottom - L.top);
        if (v <= Math.max(T.lineOverlap, inkH * 0.15) || h <= T.lineOverlap) continue;
        // blk 是这段文本的后代时（<span class=hl> 在 <div> 里）：
        // 盖住【自己所在那一行】是正常排版 —— 那一行里色块内的字本来就画在它上面、通常反白；
        // 压到【别的行】才是要抓的（带 padding 的 inline-block 撑破行盒压上一行）。
        // 判据用位置，不用面积比：原来那条 `重叠面积/blk面积 > 0.7` 有系统性偏差 ——
        // 色块的垂直 padding 让分母偏大，而墨迹高度只有 0.88em，比值天然到不了 0.7
        // （实测 0.59），豁免永远不生效，正常的行内色块全被误报。
        if (L.el.contains(blk)) {
          const blkMidY = (br.top + br.bottom) / 2;
          if (blkMidY >= L.top - 2 && blkMidY <= L.bottom + 2) continue;
        }
        if ((v * h) / blkArea > 0.7) continue;
        fails.push({
          rule: 'R4',
          msg: `${label(blk)} 的不透明底色盖住 ${label(L.el)} 某一行的墨迹 ${px(v)}×${px(h)}px`,
          fix: 'display:inline 的元素 padding 不参与行高计算，背景会直接溢出压到相邻行——改 inline-block（padding 会撑开行）、减小 padding，或抬高 line-height',
        });
        break;
      }
    }

    // R4c 两个纯文字元素互相交叠。
    // R4b 只管"不透明底色盖住谁"，两行都是透明背景的纯文字时它一无所知——
    // 而倾斜排版最容易出的就是这种：两行反向大角度一撞，字直接插进彼此的字缝里
    // （实测 +19° 的「苍蝇」和 -17° 的「凭什么」撞在一起，前一版门禁完全没报）。
    //
    // 精度说明：这里用轴对齐矩形(AABB)近似，看重叠面积占较小元素的比例。
    // AABB 对倾斜元素会系统性高估：上一行 AABB 的底边极值点（右下角）和下一行
    // AABB 的顶边极值点（右上角）落在不同的 x 上，矩形相交并不等于字形相交。
    // 所以分两档，别用一个阈值既当尺又当闸：
    //   > 45%  = 字确实插进去了，FAIL（实测 67%/73% 两例肉眼可见插字）
    //   20-45% = 排得偏挤，WARN 提示但不拦（实测 28% 那例只是紧，没真撞）
    const OVERLAP_FAIL = 0.45;
    const OVERLAP_WARN = 0.20;
    for (let i = 0; i < textEls.length; i++) {
      for (let j = i + 1; j < textEls.length; j++) {
        const A = textEls[i], B = textEls[j];
        if (A.contains(B) || B.contains(A)) continue;
        const ra = A.getBoundingClientRect(), rb = B.getBoundingClientRect();
        const sa = inkSlack(A).slack, sb = inkSlack(B).slack;
        // 收成墨迹范围再比
        const ia = { l: ra.left, r: ra.right, t: ra.top + sa / 2, b: ra.bottom - sa / 2 };
        const ib = { l: rb.left, r: rb.right, t: rb.top + sb / 2, b: rb.bottom - sb / 2 };
        const w = Math.min(ia.r, ib.r) - Math.max(ia.l, ib.l);
        const h = Math.min(ia.b, ib.b) - Math.max(ia.t, ib.t);
        if (w <= 0 || h <= 0) continue;
        const areaA = Math.max(1, (ia.r - ia.l) * (ia.b - ia.t));
        const areaB = Math.max(1, (ib.r - ib.l) * (ib.b - ib.t));
        const ratio = (w * h) / Math.min(areaA, areaB);
        if (ratio <= OVERLAP_WARN) continue;
        const item = {
          rule: 'R4',
          msg: `${label(A)} 与 ${label(B)} 交叠（重叠 ${px(w)}×${px(h)}px，占较小一方 ${(ratio * 100).toFixed(0)}%）`,
          fix: '拉开垂直间距，或让两行水平错开，或减小其中一行的倾斜角',
        };
        if (ratio > OVERLAP_FAIL) fails.push(item); else warns.push(item);
      }
    }

    // ---- R5 最小字号 ----
    // FAIL 逐条列（应该很少）；WARN 汇总成一条，否则页眉页脚一堆小字会把真问题刷没。
    const smalls = [];
    for (const el of textEls) {
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < T.minFont) {
        fails.push({ rule: 'R5', msg: `${label(el)} 字号 ${px(fs)}px < ${T.minFont}px`, fix: `1080px 图在手机上缩到约 390px（2.77×），${px(fs)}px 会变成 ${px(fs / 2.77)}px` });
      } else if (fs < T.bodyFont) {
        smalls.push(px(fs));
      }
    }
    if (smalls.length) {
      warns.push({ rule: 'R5', msg: `${smalls.length} 个元素字号在 ${Math.min(...smalls)}–${Math.max(...smalls)}px（< ${T.bodyFont}px）。页眉/标注类小字正常，正文别落在这一档` });
    }

    // ---- R6 字体是否真加载（不是悄悄 fallback）----
    const wanted = new Set();
    for (const el of textEls) {
      for (const f of getComputedStyle(el).fontFamily.split(',')) {
        const name = f.trim().replace(/^['"]|['"]$/g, '');
        if (name && !/^(serif|sans-serif|monospace|cursive|system-ui|-apple-system)$/i.test(name)) {
          wanted.add(name);
          break; // 只查每个元素的首选字体
        }
      }
    }
    const missing = [...wanted].filter(n => !document.fonts.check(`16px "${n}"`));
    if (missing.length) {
      warns.push({ rule: 'R6', msg: `首选字体不可用，已静默降级: ${missing.join(', ')}`, fix: '装到 ~/Library/Fonts 或改 font-family。降级后字形/字宽全变，排版白调' });
    }

    // ---- R8 内容覆盖率（量化"画面显空"）----
    const CELL = 30;
    const cols = Math.ceil(W / CELL), rows = Math.ceil(H / CELL);
    const grid = new Uint8Array(cols * rows);
    const mark = r => {
      const c0 = Math.max(0, Math.floor(r.left / CELL)), c1 = Math.min(cols - 1, Math.floor((r.right - 1) / CELL));
      const r0 = Math.max(0, Math.floor(r.top / CELL)), r1 = Math.min(rows - 1, Math.floor((r.bottom - 1) / CELL));
      for (let y = r0; y <= r1; y++) for (let x = c0; x <= c1; x++) grid[y * cols + x] = 1;
    };
    for (const el of textEls) mark(el.getBoundingClientRect());
    // 量 SVG 时必须下探到图形元素本身。拿 <svg> 容器的 bounding rect 会把
    // 一个几乎全空的全宽画布算成实心内容（实测把大留白构图误判成 100% 覆盖）。
    for (const el of document.querySelectorAll('img, svg circle, svg rect, svg path, svg ellipse, svg line, svg polygon, svg text')) {
      const r = el.getBoundingClientRect();
      if (r.width > 8 && r.height > 8) mark(r);
    }
    const coverage = grid.reduce((a, b) => a + b, 0) / grid.length;
    if (coverage < T.minCoverage) {
      warns.push({ rule: 'R8', msg: `内容只覆盖画面 ${(coverage * 100).toFixed(0)}%（< ${T.minCoverage * 100}%），大概率显空`, fix: '加信息层（数据/标注/编号/分割线）或放大主体。注意这是经验阈值，克制型极简构图可以豁免' });
    }

    return { fails, warns, coverage: Math.round(coverage * 100) };
  },
  { W, H, T, BOTTOM_FIXED }
);

await browser.close();

if (asJson) {
  console.log(JSON.stringify(report, null, 2));
} else {
  const { fails, warns, coverage } = report;
  console.log(`\n${path.basename(htmlPath)}  ${W}×${H}  内容覆盖 ${coverage}%`);
  console.log('─'.repeat(72));
  for (const f of fails) console.log(`FAIL [${f.rule}] ${f.msg}\n     → ${f.fix}`);
  for (const w of warns) console.log(`WARN [${w.rule}] ${w.msg}${w.fix ? `\n     → ${w.fix}` : ''}`);
  if (!fails.length && !warns.length) console.log('全部通过。');
  console.log('─'.repeat(72));
  console.log(`${fails.length} FAIL · ${warns.length} WARN`);
  console.log('规则: R1溢出 R2底部碰撞 R3越界 R4行墨迹碾压 R5最小字号 R6字体降级 R7模板变量 R8内容覆盖率\n');
}

process.exit(report.fails.length ? 1 : 0);
