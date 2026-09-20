#!/usr/bin/env node
// 用系统 Chrome 渲染 HTML → PNG（绕过缺失的 playwright chromium 二进制）
const path = require('path');
const { chromium } = require('playwright');   // 需 npm i playwright（不必 install 浏览器，用系统 Chrome）

async function main() {
  const [html, out, w = 1080, h = 1440] = process.argv.slice(2);
  const browser = await chromium.launch({ channel: 'chrome' }).catch(() => chromium.launch());
  const page = await browser.newPage({
    viewport: { width: +w, height: +h },
    deviceScaleFactor: 2,
  });
  await page.goto('file://' + path.resolve(html), { waitUntil: 'networkidle' });
  // 字体就绪再截图，不要只睡一个定时器。用本机已装字体时 networkidle 之后
  // fonts.status 通常已经是 loaded（mac mini 实测等待耗时 0-1ms），所以这行平时是白加的；
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
