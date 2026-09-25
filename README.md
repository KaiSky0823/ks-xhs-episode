# ks-xhs-episode · 小红书冷知识账号，一集一条命令 🎨

> *End-to-end pipeline for a Xiaohongshu "weird facts" account: topic → multi-agent fact-check → one API call for the background → four vertical cards → copy → publish log.*

做图文号最累的不是画图，是**每一集都要把选题、核查、出图、文案、登记从头走一遍**，走到第三集就开始偷工减料，第五集就停更。

这个 skill 把这条流程钉死成七步。原型账号「奇奇怪怪回收站」（生活脑洞 / 冷知识）已经**用它跑通了九集**。

## 🖼️ 为什么不是「让模型直接出图」

试过，不行：中文多字错字、文字被裁、同一个角色每次长得都不一样、标注位置控不准。

所以是**三层分工**：

| 层 | 谁做 | 为什么 |
|---|---|---|
| 底图（纸纹 / 网点 / 褪色渍） | 生图 API | 质感是模型强项，且不含任何需要精确的东西 |
| 文字 | HTML/CSS + Chrome 截图 | 中文永不出错，像素级可控 |
| 角色 / 机制图示 | 手写 SVG | 颜色跟色板走，位置精确，跨集一致 |

**整条流程只有一次 API 调用**：每集一张底图，四张图共用。其余全本地，成本几乎为零。

## 🧠 这套东西真正值钱的地方

不是排版，是**核查协议**（`references/02`）。四条底线：

1. 🔒 **先核后画** —— 物种、数字、机制、年份没钉死之前不动笔
2. 🏷️ **每条上图的话都要标强度** —— 一手全文 / 一手摘要 / 二手 / 未证实，只有前两档能当硬事实
3. 🚫 **「不能写」清单比「能写」清单更重要** —— 它拦住的错误更多
4. ⚖️ **否定断言门槛更高** —— 「没人测过」「查无出处」必须读到全文才能说

九集里 agent 编造或记错过 **6 次**结论，全部靠读原文推翻（复盘在 `references/06`）。你不装这套协议，这 6 次就会变成 6 条评论区翻车。

## 💬 你说什么，它给什么

你说：「下一集做『为什么猫总是把东西推下桌』」

它先出选题评分（共鸣 × 研究 × 反转 × 可画），派 agent 核查并标强度，生成底图，出四张 2160×2880 竖图并跑门禁，写标题 / 正文 / hashtag / 评论区预备答案，最后登记。

## 📦 里面有什么

```
SKILL.md                      七步流程 + 四条底线
references/
  00-环境与快速开始.md        装什么、跑通第一张图、门禁在查什么、常见报错
  01-选题.md                  评分口径、排期纪律
  02-核查协议.md              ★核心★ 多 agent 分工、强度四档、必须亲自做的三件事
  03-四张图.md                四张各自的内容职责 + 门禁测不到的七件事
  04-文案.md                  标题 / 正文 / hashtag / 评论区预备答案
  05-发布与登记.md            发布前检查、发布后三处登记
  06-九集复盘.md              实战踩过的坑，按类型归档
  07-底图与生图API.md         API 参数、密钥用法、魔数校验、四道闸
  08-视觉规范.md              色板 / 字号 / 角度 / 几何 / SVG / 禁忌 / 门禁
  09-换成你自己的账号.md      要换哪些、角色怎么设计、换生图服务
scripts/                      gen_bg / measure_bg / shot / social-card-qa / _fontcheck
templates/                    build 骨架 + 核查结论 + 发布文案 + 占位角色 SVG
```

## ⚙️ 安装

```bash
git clone https://github.com/KaiSky0823/ks-xhs-episode.git ~/.claude/skills/ks-xhs-episode
cd ~/.claude/skills/ks-xhs-episode
npm i playwright
pip install pillow numpy
export ARK_API_KEY=<你自己的 key>
```
中文字体要 Noto Sans CJK SC + Noto Serif SC。「五条命令跑通第一张图」见 `references/00`。

## 🔁 换成你自己的

账号名、角色、语气、hashtag 配方换成你的（见 `references/09`）。方法论、几何约束、核查协议直接拿走。换别家生图服务也行，产出满足三条硬规格即可：**2160×2880、比例精确 0.75、真 PNG**。

## License

MIT © 2026 KaiSky0823
