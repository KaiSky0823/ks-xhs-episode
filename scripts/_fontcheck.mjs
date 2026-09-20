import { chromium } from 'playwright';
import crypto from 'crypto';
const b = await chromium.launch({ channel: 'chrome' }).catch(() => chromium.launch());
const p = await b.newPage();
const FONTS = {
  serifSC: "'Noto Serif SC'", sansSC: "'Noto Sans CJK SC'",
  bogus:   "'ZZZ-Nonexistent'", pingfang: "'PingFang SC'",
};
const hashes = {}, metrics = {};
for (const [k, f] of Object.entries(FONTS)) {
  await p.setContent(`<body style="margin:0;background:#fff">
    <div id="t" style="font:900 114px ${f},serif;white-space:nowrap;width:1400px">泼它永远不中Ag</div></body>`);
  await p.evaluate(() => document.fonts.ready);
  const buf = await p.locator('#t').screenshot();
  hashes[k] = crypto.createHash('md5').update(buf).digest('hex').slice(0, 12);
  metrics[k] = await p.evaluate(() => {
    const c = document.createElement('canvas').getContext('2d');
    c.font = getComputedStyle(document.getElementById('t')).font;
    const m = c.measureText('泼');
    return { ink: +(m.actualBoundingBoxAscent + m.actualBoundingBoxDescent).toFixed(1),
             adv: +m.width.toFixed(1) };
  });
}
for (const k of Object.keys(FONTS))
  console.log(`  ${k.padEnd(9)} md5=${hashes[k]}  墨迹高=${metrics[k].ink}px advance=${metrics[k].adv}px`);
console.log();
console.log(hashes.serifSC !== hashes.bogus ? '✓ Noto Serif SC   真生效' : '✗ Noto Serif SC 静默降级');
console.log(hashes.sansSC  !== hashes.bogus ? '✓ Noto Sans CJK SC 真生效' : '✗ Noto Sans CJK SC 静默降级');
console.log(hashes.serifSC !== hashes.sansSC ? '✓ 衬线/黑体渲染确实不同(两者都是真字体)' : '⚠️ 两者渲染相同=可疑');
await b.close();
