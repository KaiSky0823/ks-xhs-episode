#!/usr/bin/env python3
"""ai_flavor_check —— 去 AI 味硬闸：图上字 / 标题 / 正文 / 评论回复。

用法：
  python3 scripts/ai_flavor_check.py 第N集-XX/素材/{1_cover,2_answer,3_mechanism,4_egg}.html 第N集-XX/发布文案.md

输入：
  .html  卡片源文件，查 HTML 文字和内联 SVG 的 <text>（气泡、标签、角色台词）
  .md    发布文案，只查「标题 / 正文 / Hashtag / 评论区预备答案」四节里真正会发出去的字：
         引用块（> …）、代码块、评论表的「回法」列；说明性文字、「实际发布」不查

  加 --dump：不检查，只把每个文件里会被查的文字按顺序打印出来（收尾句单独标出），给审稿 agent 当输入。

  另有两条版式硬约束（只对 .html 生效）：C1 整集最多 1 个独立限定框（class 里带 note 这个词，健康类安全提醒写成
  class="note safety" 豁免；底栏说明别叫 note，叫 caption）；C2 来源行（class="src"）必须一行，只留「作者 年份」。

通俗度提示（REVIEW，不拦出图）：V13 论文腔 / 术语词；V14 单卡数字 ≥6 个（不含年份）。它们只是辅助，
抓不住「比喻太绕」「逻辑链长」，那两样靠 references/11-通俗度与冷读测试.md 的冷读。

退出码：0 = 没有 FAIL；1 = 有 FAIL，不要交付；2 = 用法错误。

FAIL  = 硬约束。一个都不许有：改写句子，不要想办法绕过正则。
        唯一的例外：内容负责人明确批准的一句（每集最多 1 句），写进 `ai_flavor_ok.txt`（和 素材/ 同级或上一级），
        格式 `原句 | 批准日期 | 批准理由`；脚本会跳过这一句，并在末尾列出来。没有明确批准，不得自行加入。
REVIEW = 疑似。逐条处理：改掉，或让审稿 agent / 本人判断后写明理由留下。
收尾句 = 每张卡 class 带 final / foot 的那一句（<div> 或 <p>），单独列出来，必须逐句过「事实 / 邀请 / 不写」三选一；
         两截（逗号或空格断开）又没有数字 / 出处（「」『』《》）/ 动作的，C3 直接 FAIL。

为什么有它：系列冷读和脚本回归显示，句式层规则能发现对仗、格言和套话等问题；文字的整体观感仍需人工审阅。
"""
import html
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

# ── 硬约束：命中即 FAIL ─────────────────────────────────────────────
HARD = [
    ('H1 「不是X，是Y」族', [
        # 逗号、顿号、分号，或者账号自己的空格断句（「不是浪漫 是本能」）都算断开
        r'不是[^。！？\n]{1,24}?(?:[，,、；;]|\s+)\s*(?:而)?是',
        r'不是[^。！？\n]{1,30}而是',
        r'并非[^。！？\n]{1,24}而是',
        r'不怪[^，。\n]{1,12}[，,]\s*怪',
        r'与其说.{1,30}不如说',
        r'重要的不是',
        r'不只是[^。！？\n]{1,20}更是',
        # 「这是真的，不是吗」是反问、「只是试管里的结果 不是说抹了就有用」是限定，都不拦（V4 仍会提示）。
        # 逗号版中间允许空格（「手心轻触（16 人），不是」）；空格版中间不许再有空格，免得跨好几截
        r'是[^，。！？\n]{1,16}[，,]\s*不是(?![吗吧呢么嘛]|说)',
        r'是[^，。！？\n\s]{1,16}\s+不是(?![吗吧呢么嘛]|说)',
    ]),
    # 破折号：— ― 和两个连字符都拦；– 只放行数字区间（1902–03、17–25%、90°–270°）
    ('H2 破折号', [r'[—―]|--|(?<![0-9０-９°%℃])–|–(?![0-9０-９])']),
    ('H3 格言公式（X，等于/才是/就是…的语言）', [
        r'[，,]\s*等于',
        r'[，,]\s*才是',
        r'是[^，。！？\n]{1,10}的(?:语言|镜子|货币|缩影|注脚|代名词)',
        r'就是[^，。！？\n]{1,12}的(?:语言|镜子)',
    ]),
    ('H4 意义拔高 / 宣传腔', [
        r'标志着|见证了|体现了|彰显|折射出|重新定义|赋能|璀璨|底蕴|得天独厚|致力于|匠心|不容错过|令人惊叹|极致体验',
    ]),
    ('H5 填充 / 假坦诚 / 签到 / 聊天残留 / 万能展望', [
        r'值得注意的是|需要指出的是|不得不说|说实话|老实讲|讲真|让我们|接下来(?:看看|我们)|话不多说',
        r'希望这对你有帮助|需要我展开|好问题|未来可期|前景广阔|拭目以待|总而言之|综上所述|由此可见',
    ]),
    ('H6 无名氏归因', [
        r'有专家认为|业内人士|不少观察者|专家指出|有研究表明|有研究发现',
    ]),
    ('H8 书面连接词 / 套话 / 自标深度 / 元评论', [
        r'然而|因此|并且|值得一提|不仅[^。！？\n]{0,20}而且|此外|总的来说|一句话总结|翻译翻译',
        r'再深入一层|最深的一层|更深地说|打个比方|接下来我们|让我们重新思考|值得我们深思|引人深思|发人深省',
        r'不可否认|众所周知|自古以来|总结起来就是|不言而喻',
    ]),
    ('H9 翻译腔 / 学术腔模板', [
        r'在[^，。！？\n]{1,14}的(?:过程中|背景下)|对于[^，。！？\n]{1,12}而言|基于[^，。！？\n]{1,12}的考虑',
        r'随着[^，。！？\n]{1,14}的发展|进行(?:讨论|分析|处理|研究|比较|测量)|近年来|通过对',
    ]),
    ('H10 英式对仗 / 自指剧透', [
        r'两个[^，。！？\n]{1,6}[，,]\s*一个',
        r'你(?:重新|亲身|亲眼)?(?:发明|创造|见证|分娩)了',
    ]),
    ('H11 求互动（评论区聊聊 / 告诉我 / 留言）', [
        # 「研究告诉我们」不算；「留言板」不算；「说一声」两可，降为 REVIEW（V17；V15 这个编号以前用过、已撤）
        r'评论区(?:说|聊|告诉|留言|见|等|分享)|欢迎(?:留言|评论|分享|讨论)|你们(?:怎么看|觉得呢)'
        r'|告诉我(?!们)|聊聊|留言(?![板簿本])|点赞|关注我|求收藏',
    ]),
    ('H7 emoji 装饰', [
        # 不整段拦 U+2600–27BF：✓ ✗ ⚠ ♪ 在往期机制图里是功能符号（对错标记、健康提醒、音符）
        r'[\U0001F300-\U0001FAFF✨⭐❤❣♥♡✌☺☻★☆✿❀✧✦☀☁☘❄✊✋☝✍]',
    ]),
]

HARD_RE = [(name, [re.compile(p) for p in pats]) for name, pats in HARD]
NUM = re.compile(r'[0-9０-９]|[一二两三四五六七八九十百千万]+(?:年|个|次|天|秒|分|倍|米|厘|度|岁|人|周|格|条|张|篇|家)')
INVITE = re.compile(r'[试看告诉说数摸量查翻问留]')
# 收尾句里的「这张图是示意 / 没核过」是事实声明，不是金句（C 版封面「示意图 事实未核」）
DISCLAIM = re.compile(r'示意|未核|没核|未证实|待核实')
# 收尾句容器：<div> 或 <p>，class 里带 final 或 foot 这个词即可（class="foot big" 也算）。
# 条件必须写在正则里：先匹配任意 class 再筛，外层 <div class="wrap"> 会把里面的 .final 吞掉
CLOSER = re.compile(r'<(div|p)\b[^>]*\bclass="[^"]*(?<![\w-])(?:final|foot)(?![\w-])[^"]*"[^>]*>(.*?)</\1>', re.S)
CLASS_TOKEN = lambda cls, *names: any(t in names for t in cls.split())
# 通俗度提示：论文口径的词。命中只是 REVIEW，不拦出图；比喻太绕和逻辑链长需靠 references/11 的冷读检查。
JARGON = re.compile(r'口径|分母|分子|显著|样本|受试|被试|对照|变量|效应|相关性|置信|检验|基线|组水平|合起来看|整体上看|严格控制|合理的估计|量表|统计|参与者|实验组|机制')


def norm(x):
    return re.sub(r'[\s，,。；;：:、！!？?「」『』（）()·\-"]', '', x)


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s))).strip()


def html_lines(src):
    """返回 (普通行, 收尾句, 上下文, 正文行)。后两项只有 md 用得到。"""
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)   # 模板里注释掉的示例块不算
    closers = []
    for m in CLOSER.finditer(src):
        inner = re.sub(r'<small>.*?</small>', '', m.group(2), flags=re.S)
        if clean(inner):
            closers.append(clean(inner))
    body = re.sub(r'<style.*?</style>|<script.*?</script>', '', src, flags=re.S)
    lines = [clean(m.group(1)) for m in re.finditer(r'<text\b[^>]*>(.*?)</text>', body, re.S)]
    body = re.sub(r'<svg.*?</svg>', '', body, flags=re.S)
    body = re.sub(r'</div>|<br\s*/?>|</p>|</small>|</li>', '\n', body)
    lines += [clean(x) for x in body.split('\n')]
    return [l for l in lines if l], closers, {}, []


def md_lines(src):
    """只取会发出去的字：标题 / 正文 / Hashtag / 评论区 四节里的引用块、代码块、评论表「回法」列，
    外加两种不在引用块里的写法：标题节的「**主推** > 问句」（模板格式），
    正文节紧跟在「**A · …**」这类小标题后面的普通段落（不用代码块写的正文）。"""
    out, sec, fence, ctx, body = [], '', False, {}, []
    take = False   # 正文节：上一个非空行是不是「**X · …**」小标题（或它后面的段落）
    for raw in src.split('\n'):
        if raw.strip().startswith('```'):
            fence = not fence
            take = False   # 代码块就是这一版的正文，块后面的段落是说明
            continue
        if not fence and re.match(r'#{1,6}\s', raw):
            sec = raw
            take = False
            continue
        if '实际发布' in sec or not any(k in sec for k in ('标题', '正文', 'Hashtag', '评论区')):
            continue
        if fence:
            out.append(raw.strip())
            if '正文' in sec:
                body.append(raw.strip())
        elif raw.startswith('>'):
            out.append(re.sub(r'[*`]', '', raw.lstrip('> ')).strip())
        elif '标题' in sec and re.match(r'\s*\*\*[^*]+\*\*[^>]*>\s*\S', raw):
            out.append(re.sub(r'[*`]', '', raw.split('>', 1)[1]).strip())
        elif '正文' in sec and re.match(r'\s*\*\*[^*]+\*\*', raw):
            take = True
        elif '正文' in sec and raw.strip() and take:
            t = raw.strip()
            if re.match(r'(?:出处|提示|备注)[：:]|[-*|>#]|---', t):
                take = False
                continue
            t = re.sub(r'[*`]', '', t)
            out.append(t)
            body.append(t)
        elif '评论区' in sec and raw.startswith('|') and not re.match(r'\|\s*[-:]', raw):
            cells = [c.strip() for c in raw.strip().strip('|').split('|')]
            if len(cells) >= 2 and cells[1] not in ('回法',):
                a = re.sub(r'[*`]', '', cells[1])
                out.append(a)
                ctx[a] = cells[0]
    return [l for l in out if l], [], ctx, [l for l in body if l]


def review(line):
    """疑似项：返回 [(名称, 说明)]。"""
    hits = []
    if re.search(r'[？?]\s*[^？?，,。！\n]{1,10}[。！]', line):
        hits.append(('V1 疑似自问自答', '问句后紧跟一个短答案'))
    sents = [s for s in re.split(r'[。！？]', line) if s.strip()]
    run = 0
    for s in sents:
        run = run + 1 if len(s.strip()) <= 6 else 0
        if run >= 3:
            hits.append(('V2 疑似短句轰炸', '连续 3 个 ≤6 字的短句'))
            break
    clauses = [c.strip() for c in re.split(r'[，,、；;。]', line) if len(c.strip()) >= 2]
    for i in range(len(clauses) - 2):
        a, b, c = clauses[i:i + 3]
        if a[:2] == b[:2] == c[:2] or a[-2:] == b[-2:] == c[-2:]:
            hits.append(('V3 疑似排比三连', '三个分句开头或结尾相同'))
            break
    if re.search(r'这事我得|讲一件|接下来|挖到这儿|想到这里|往后翻|我继续往下|下面(?:来|看)', line):
        hits.append(('V6 疑似脚手架 / 报站 / 预告', '直接说事，别预告要说事；删了不塌就删'))
    if re.search(r'非常|极其|相当|十分(?!制)|特别|重大的|根本的|惊人的|深刻的|显著的|巨大的', line):
        hits.append(('V7 疑似形容词 / 程度副词通胀', '能砍就砍，每个字都得干活'))
    if re.search(r'被[^，。！？\n]{1,8}(?:锁|推|肢解|发现|迫|认为)', line):
        hits.append(('V8 疑似翻译腔被动', '改成主动，或换个说法'))
    if re.search(r'(?:^|[，。；])我(?:觉得|认为|想)', line):
        hits.append(('V9 疑似「我觉得」开头', '换成「看到 / 听过 / 感觉」，或直接陈述'))
    if line.count('，') + line.count(',') >= 4 and '；' not in line and len(re.findall(r'(?:19|20)\d\d', line)) < 2:
        hits.append(('V10 疑似长句', '4 个以上逗号，拆成短句'))
    if '；' in line and len(re.findall(r'(?:19|20)\d\d', line)) < 2 and len(re.findall(r'[A-Za-z]', line)) < 6:
        hits.append(('V12 疑似分号', '分号可能偏书面；来源行里的分号不算'))
    m13 = JARGON.findall(line)
    if m13:
        hits.append(('V13 疑似论文腔 / 术语', '「' + '」「'.join(dict.fromkeys(m13)) + '」：读者要停下来想。换成一句人话，或者删；术语最多留一个并当场解释'))
    # 一个逗号，或者一个空格（空格断句）分成两半。空格版只看短的纯中文陈述句（每半 ≤7 字）：
    # 「高罗佩 1961」「明清的书里 有写接吻吗」「荷兰人高罗佩认为 中国人只在房里亲」这种不算
    m = re.fullmatch(r'([^，,\s]+)(?:[，,]\s*|\s+)([^，,\s]+?)[。！？]?', line)
    comma = re.search(r'[，,]', line)
    if m and len(m[1]) >= 3 and len(m[2]) >= 3 and abs(len(m[1]) - len(m[2])) <= 1 \
            and (comma or (len(m[1]) <= 7 and len(m[2]) <= 7
                           and not re.search(r'[0-9A-Za-z·？?]|吗|呢|什么|怎么', line))):
        hits.append(('V4 疑似对仗', '一个逗号或空格、前后两半字数几乎相等'))
    if re.search(r'说一声', line):
        hits.append(('V17 疑似求互动', '「说一声」是叙述（他走之前说一声）就留；是叫读者回话就删'))
    return hits


def check(path, card_lines=(), ok=frozenset()):
    src = path.read_text(encoding='utf-8')
    lines, closers, ctx, body = html_lines(src) if path.suffix == '.html' else md_lines(src)
    fails, revs = [], []
    for line in dict.fromkeys(lines + closers):
        for name, pats in HARD_RE:
            for p in pats:
                m = p.search(line)
                if m:
                    # 评论回复整句都用空格断句，「讲的是离欲 不是日常」多半是在纠正事实，空格版只提示不拦；
                    # 带逗号 / 「而是」的照样 FAIL。图上字、标题、正文不走这条豁免
                    if name.startswith('H1 ') and line in ctx and not re.search(r'[，,、；;]|而是', m.group(0)):
                        revs.append(('V16 疑似「不是X 是Y」（评论回复·空格版）', line,
                                     f'命中「{m.group(0)}」：在纠正事实就留；是在造金句就改'))
                    else:
                        fails.append((name, line, m.group(0)))
                    break
        for name, why in review(line):
            revs.append((name, line, why))
    for c in closers:
        # 两截 = 有逗号，或者用空格断句（「嘴唇会记住 心也会记住」）。带引号 / 书名号出处的放行。
        # 空格版不管问句（「这三件事 在身体里是同一回事吗？」是抛问题，不是格言）；逗号版照旧
        two = re.search(r'[，,]', c) or (re.search(r'\S\s+\S', c) and not re.search(r'[？?]\s*$|[吗呢]\s*$', c))
        if two and not NUM.search(c) \
                and not INVITE.search(c) and not DISCLAIM.search(c) and not re.search(r'[「『《]', c):
            fails.append(('C3 收尾句像金句（两截、无数字 / 出处 / 动作）', c, '换成一个具体事实、一个能做的动作，或者不写；确需保留时按文件头的审批例外记录'))
    for b in body:
        nb = norm(b)
        for c in card_lines:
            nc = norm(c)
            m = SequenceMatcher(None, nb, nc).find_longest_match(0, len(nb), 0, len(nc))
            if m.size >= 8:
                revs.append(('V11 正文与图上文字重复', b, f'和图上「{c[:30]}」有连续 {m.size} 字相同（去标点后）：正文不要复述图上内容'))
                break
    if path.suffix == '.html':
        # V14 一张卡里不同的数字太多（不算年份）。图里字块数量试过当 V15，和画面好坏对不上（第二版 ② 10 处、第三版 ③ 11 处），已撤，改人工看
        txt = ' '.join(lines)
        nums = {n for n in re.findall(r'\d+(?:\.\d+)?', re.sub(r'(?:19|20)\d\d', ' ', txt))}
        if len(nums) >= 6:
            revs.append(('V14 单卡数字太多', '、'.join(sorted(nums, key=lambda x: float(x))), f'一张卡里有 {len(nums)} 个不同的数字（不含年份），读者会串；留最要紧的 ≤5 个，其余放发布文案'))
        for m in re.finditer(r'<div class="src[^"]*">(.*?)</div>', src, re.S):
            t = clean(m.group(1))
            w = sum(1 if ord(c) > 0x2E80 else 0.55 for c in t)
            if w > 40:
                fails.append(('C2 来源行超过一行', t, f'宽度约 {w:.0f}（上限 40）：只留「作者 年份」用 · 隔开，完整引文放发布文案「图上数字的出处」表'))
    seen = set()
    fails = [f for f in fails if not (f[:2] in seen or seen.add(f[:2]))]
    fails = [f for f in fails if norm(f[1]) not in ok]
    revs = [r for r in revs if norm(r[1]) not in ok]
    return fails, revs, closers, len(set(lines + closers))


def main(argv):
    # --ok 后面那个参数是批准文件，不是待查文件
    paths = [Path(a) for i, a in enumerate(argv) if not a.startswith('-') and not (i and argv[i - 1] == '--ok')]
    if not paths:
        print(__doc__)
        return 2
    dump = '--dump' in argv
    ok_path = next((Path(argv[i + 1]) for i, a in enumerate(argv) if a == '--ok' and i + 1 < len(argv)), None)
    if ok_path is None:
        ok_path = next((q for p in paths for q in (p.parent / 'ai_flavor_ok.txt', p.parent.parent / 'ai_flavor_ok.txt') if q.exists()), None)
    ok_rows = []
    if ok_path and ok_path.exists():
        ok_rows = [l.strip() for l in ok_path.read_text(encoding='utf-8').split('\n') if l.strip() and not l.startswith('#')]
    ok = frozenset(norm(r.split('|')[0]) for r in ok_rows)
    total_fail = 0
    card_lines = []
    # C1 按 class 里的 note 这个词数（class="box note" 也算），带 safety 的豁免
    notes = [(p.name, sum(1 for m in re.finditer(r'<(?:div|p|section|aside)\b[^>]*\bclass="([^"]*)"',
                                                 re.sub(r'<!--.*?-->', '', p.read_text(encoding='utf-8'), flags=re.S))
                          if CLASS_TOKEN(m.group(1), 'note') and not CLASS_TOKEN(m.group(1), 'safety')))
             for p in paths if p.suffix == '.html' and p.exists()]
    if sum(n for _, n in notes) > 1:
        total_fail += 1
        print('✗ C1 「先说清楚」类独立框：整集最多 1 张用（健康类安全提醒豁免，写成 class="note safety"）。现有：'
              + '、'.join(f'{f} ×{n}' for f, n in notes if n)
              + '。如果其中有的是底栏说明而不是限定框，把它的 class 改成 caption（note 这个名字专指限定框）')
    for p in paths:
        if p.suffix == '.html' and p.exists():
            card_lines += html_lines(p.read_text(encoding='utf-8'))[0]
    for p in paths:
        if dump and p.exists():
            src = p.read_text(encoding='utf-8')
            lines, closers, ctx, _ = html_lines(src) if p.suffix == '.html' else md_lines(src)
            print(f'\n## {p.name}')
            for l in dict.fromkeys(lines):
                print(f'- 【问：{ctx[l]}】{l}' if l in ctx else f'- {l}')
            for c in closers:
                print(f'- 【收尾句】{c}')
            continue
        if not p.exists():
            print(f'✗ 找不到 {p}')
            return 2
        fails, revs, closers, n = check(p, card_lines, ok)
        total_fail += len(fails)
        print(f'\n── {p} ── 查了 {n} 行 · {len(fails)} FAIL · {len(revs)} REVIEW')
        for name, line, hit in fails:
            print(f'  ✗ {name}｜{line}\n      命中：{hit}')
        for name, line, why in revs:
            print(f'  ? {name}｜{line}\n      {why}')
        for c in closers:
            print(f'  ▸ 收尾句：{c}')
    if dump:
        return 0
    if ok_rows:
        print(f'\n已批准例外（{ok_path}）：')
        for r in ok_rows:
            print(f'  ◎ {r}')
        if len(ok_rows) > 1:
            total_fail += 1
            print(f'  ✗ 本集批准了 {len(ok_rows)} 句，上限 1 句')
    print(f'\n合计 {total_fail} FAIL。' + ('不要交付，改完重跑。' if total_fail else
          '没有硬约束命中（这只证明句式层干净；REVIEW 要逐条处理，感觉层交审稿 agent）。'))
    return 1 if total_fail else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
