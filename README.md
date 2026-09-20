# ks-xhs-episode

一个 [Claude Code](https://claude.com/claude-code) skill：**小红书冷知识账号出一整集的完整流程**——
选题、多 agent 深度事实核查、生图 API 出底图、四张竖图、文案、评论区预备答案、发布后登记。

原型是小红书账号「奇奇怪怪回收站」（生活脑洞 / 冷知识），已跑通九集。

## 为什么不是「让模型直接出图」

试过，不行：中文多字错字、文字被裁、同一个角色每次都不一样、标注位置控不准。
所以是**三层分工**：

| 层 | 谁做 | 为什么 |
|---|---|---|
| 底图（纸纹 / 网点 / 褪色渍） | 生图 API | 质感是模型强项，且不含任何需要精确的东西 |
| 文字 | HTML/CSS + Chrome 截图 | 中文永不出错，像素级可控 |
| 角色 / 机制图示 | 手写 SVG | 颜色跟色板走，位置精确，跨集一致 |

**整条流程只有一次 API 调用**：每集一张底图，四张图共用。其余全本地。

## 装

```bash
git clone https://github.com/KaiSky0823/ks-xhs-episode.git ~/.claude/skills/ks-xhs-episode
cd ~/.claude/skills/ks-xhs-episode
npm i playwright
pip install pillow numpy
export ARK_API_KEY=<你自己的 key>
```

中文字体要 Noto Sans CJK SC + Noto Serif SC。
完整环境说明和「五条命令跑通第一张图」在 [`references/00-环境与快速开始.md`](references/00-环境与快速开始.md)。

## 里面有什么

```
SKILL.md                      七步流程 + 四条底线
references/
  00-环境与快速开始.md        装什么、跑通第一张图、门禁在查什么、常见报错
  01-选题.md                  评分口径（共鸣 × 研究 × 反转 × 可画）、排期纪律
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

## 这套东西真正值钱的地方

不是排版，是**核查协议**（`references/02`）。四条底线：

1. **先核后画** —— 物种、数字、机制、年份没钉死之前不动笔
2. **每条上图的话都要标强度** —— 一手全文 / 一手摘要 / 二手 / 未证实，只有前两档能当硬事实
3. **「不能写」清单比「能写」清单更重要** —— 它拦住的错误更多
4. **否定断言门槛更高** —— 「没人测过」「查无出处」必须读到全文才能说

九集里 agent 编造或记错过六次结论，全部靠读原文推翻（见 `references/06`）。

## 换成你自己的

账号名、角色、语气、hashtag 配方要换成你的，见 [`references/09`](references/09-换成你自己的账号.md)。
方法论、几何约束、核查协议可以直接拿走。

换别家生图服务也行，产出满足三条硬规格即可：**2160×2880、比例精确 0.75、真 PNG**。

## License

MIT
