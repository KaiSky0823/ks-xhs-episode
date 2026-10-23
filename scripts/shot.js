#!/usr/bin/env node
// 用系统 Chrome 渲染 HTML → PNG（绕过缺失的 playwright chromium 二进制）
const path = require('path');
const { chromium } = require('playwright');   // 需 npm i playwright（不必 install 浏览器，用系统 Chrome）

// 去 AI 味闸前置：定稿卡（素材/ 下的 1_*.html … 4_*.html）出图前必须先过 ai_flavor_check.py，
// 过不了就不出图。这样「忘了跑闸」变成不可能。预览用 SKIP_FLAVOR_GATE=1，预览图不得交付。
// fail-closed：html 在 素材/ 下（或者要输出到 素材/[1-4]_*.png）却不叫 [1-4]_*.html，直接报错，
// 不再静默放行（模板一度写出 cover.html，闸一次都没跑，见审计 B-01 / C-21）。
const CARD = /^[1-4]_.*\.html$/;
function flavorGate(html, out) {
  const fs = require('fs');
  const abs = path.resolve(html);
  const outAbs = path.resolve(out);
  const htmlInSucai = path.basename(path.dirname(abs)) === '素材';
  const outIsFinal = path.basename(path.dirname(outAbs)) === '素材' && /^[1-4]_.*\.png$/.test(path.basename(outAbs));
  if (!htmlInSucai && !outIsFinal) return;
  if (process.env.SKIP_FLAVOR_GATE === '1') { console.error('⚠ 已跳过去 AI 味闸（预览，不得交付）'); return; }
  if (!CARD.test(path.basename(abs))) {
    console.error(`✗ ${html}：定稿卡必须命名为 1_cover…4_egg（[1-4]_*.html，放在 素材/ 下），去 AI 味闸只认这个名字。` +
      '\n  预览请设 SKIP_FLAVOR_GATE=1（预览图不得交付）。');
    process.exit(1);
  }
  const dir = path.dirname(abs);
  const all = fs.existsSync(dir) ? fs.readdirSync(dir) : [];
  const files = all.filter(f => CARD.test(f)).sort().map(f => path.join(dir, f));
  if (!files.length) {
    // 不再把空列表交给 ai_flavor_check（它会打印用法、返回 2，把人往错的方向带）
    const other = all.filter(f => f.endsWith('.html'));
    console.error(`✗ ${path.relative(process.cwd(), dir) || dir}/ 下没有 [1-4]_*.html，先跑 build 脚本` +
      (other.length ? `\n  现有 ${other.join(' ')}：定稿卡要改名成 1_cover / 2_answer / 3_mechanism / 4_egg` : ''));
    process.exit(1);
  }
  if (!fs.existsSync(abs)) { console.error(`✗ 找不到 ${html}`); process.exit(1); }
  const md = path.join(dir, '..', '发布文案.md');
  if (fs.existsSync(md)) files.push(md);
  const r = require('child_process').spawnSync('python3', [path.join(__dirname, 'ai_flavor_check.py'), ...files], { encoding: 'utf-8' });
  if (r.status !== 0) {
    console.error(r.stdout || '');
    console.error(r.stderr || '');
    console.error('✗ 去 AI 味闸没过（或没能运行），不出图。改完重跑；仅预览可设 SKIP_FLAVOR_GATE=1。');
    process.exit(1);
  }
}

async function main() {
  const [html, out, w = 1080, h = 1440] = process.argv.slice(2);
  if (!html || !out) {
    console.error('用法：node shot.js <html> <out.png> [宽 1080] [高 1440]\n  素材/ 下的定稿卡要叫 [1-4]_*.html，出图前会自动过去 AI 味闸；预览设 SKIP_FLAVOR_GATE=1');
    process.exit(2);
  }
  flavorGate(html, out);
  if (!require('fs').existsSync(html)) { console.error(`✗ 找不到 ${html}`); process.exit(1); }
  const browser = await chromium.launch({ channel: 'chrome' }).catch(() => chromium.launch());
  const page = await browser.newPage({
    viewport: { width: +w, height: +h },
    deviceScaleFactor: 2,
  });
  await page.goto('file://' + path.resolve(html), { waitUntil: 'networkidle' });
  // 字体就绪再截图，不要只睡一个定时器。用系统已装字体时 networkidle 之后
  // fonts.status 通常已经是 loaded（实测常低于 1ms），所以这行平时几乎无开销；
  // 但一旦有人违反 DNA 禁令引入 @import/webfont，定时器就会拍到 fallback 字形，
  // 而 social-card-qa.mjs 里是等 fonts.ready 的 —— 门禁过了、截图却是错字形，最难查。
  // 两边保持同一个等待条件，零成本。
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600);   // 余下的是渲染/合成的沉降时间
  await page.screenshot({ path: path.resolve(out), clip: { x: 0, y: 0, width: +w, height: +h } });
  await browser.close();
  console.log('OK ' + out);
}
main().catch(e => { console.error(e.message); process.exit(1); });
