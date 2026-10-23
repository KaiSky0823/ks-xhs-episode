// 量每张卡里 body > div 各块的上下边界和间距（门禁 R4 测不到绝对定位块之间的叠压，靠它补）。
// 用法：NODE_PATH=ks-xhs-episode-kit/node_modules node _tools/measure_blocks.js 1_cover.html ...
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ channel: 'chrome' });
  const p = await b.newPage({ viewport: { width: 1080, height: 1440 } });
  for (const f of process.argv.slice(2)) {
    await p.goto('file://' + require('path').resolve(f));
    const rs = await p.evaluate(() => [...document.querySelectorAll('body > div')].map(e => {
      const r = e.getBoundingClientRect();
      return { c: e.className, t: Math.round(r.top), b: Math.round(r.bottom), l: Math.round(r.left), rt: Math.round(r.right) };
    }));
    console.log('\n=== ' + f);
    rs.sort((a, x) => a.t - x.t);
    let prev = null;
    for (const r of rs) {
      let note = '';
      if (prev) {
        const horiz = r.l >= prev.rt - 2 || r.rt <= prev.l + 2;
        const gap = r.t - prev.b;
        note = horiz ? '  (左右错开)' : (gap < 15 ? `  ⚠ 与上一块间距 ${gap}px` : `  间距 ${gap}px`);
      }
      console.log(`${String(r.t).padStart(5)}–${String(r.b).padEnd(5)} x${r.l}–${r.rt}  .${r.c}${note}`);
      if (!prev || r.b > prev.b) prev = r;
    }
  }
  await b.close();
})();
