# -*- coding: utf-8 -*-
"""幻觉/矛盾内容审计（只读 + 输出报告）。
用法: python audit_hallucination.py [KB根目录 / 项目根目录 / wiki目录]

扫描范围：figures 页面的生平断言（生卒年、国籍、代表作、师承、政治/宗教立场），
与 summaries 中对同一人物的描述交叉比对，标记矛盾、缺失来源、数学错误等。
同时检查 figures 页 frontmatter sources 是否指向真实 raw 文件。

输出：终端分级报告（CRITICAL / MAJOR / MINOR / INFO）+ kb/_audit_report.md 可追溯清单
"""
import os, re, sys, datetime
from collections import defaultdict


def resolve_wiki(arg):
    if os.path.isdir(os.path.join(arg, 'kb', 'wiki')):
        return os.path.join(arg, 'kb', 'wiki')
    if os.path.isdir(os.path.join(arg, 'wiki')):
        return os.path.join(arg, 'wiki')
    return arg


BASE = resolve_wiki(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
KB_ROOT = os.path.dirname(BASE)
RAW = os.path.join(KB_ROOT, 'raw')
FIG_DIR = os.path.join(BASE, 'figures')
SUM_DIR = os.path.join(BASE, 'summaries')


# ---------- 工具 ----------

def read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def body_of(text):
    """去掉 frontmatter 正文"""
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            return parts[2]
    return text


def parse_aliases(text):
    aliases = set()
    m = re.search(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', text, re.MULTILINE)
    if m:
        for line in m.group(1).split('\n'):
            line = line.strip()
            if line.startswith('-'):
                a = line[1:].strip().strip('"').strip("'")
                if a:
                    aliases.add(a)
    m = re.search(r'^aliases:\s*\[(.*?)\]', text, re.MULTILINE)
    if m:
        for a in m.group(1).split(','):
            a = a.strip().strip('"').strip("'")
            if a:
                aliases.add(a)
    return aliases


def clean_source(s):
    """剥掉引号、[[...]] 包裹，返回纯净链接"""
    s = s.strip()
    s = s.strip('"').strip("'")
    s = s.strip()
    s = re.sub(r'^\[\[', '', s)
    s = re.sub(r'\]\]$', '', s)
    s = s.strip()
    return s


def parse_sources(text):
    """解析 frontmatter sources，返回 (raw_links, at_links, others)"""
    raw_links, at_links, others = [], [], []
    m = re.search(r'^sources:\s*\n((?:\s*-\s*.*\n)*)', text, re.MULTILINE)
    if not m:
        m = re.search(r'^sources:\s*\[(.*?)\]', text, re.MULTILINE)
        if m:
            for s in m.group(1).split(','):
                s = clean_source(s)
                if s:
                    (raw_links if 'raw/' in s else at_links if s.startswith('@') else others).append(s)
    else:
        for line in m.group(1).split('\n'):
            line = line.strip()
            if line.startswith('-'):
                s = clean_source(line[1:])
                if s:
                    (raw_links if 'raw/' in s else at_links if s.startswith('@') else others).append(s)
    return raw_links, at_links, others


def raw_file_exists(rel):
    """检查 raw 相对路径（raw/教材/切片名）是否存在，自动补 .md 扩展名"""
    # rel 形如 raw/朱立元/05-2-3意识流的不可分割性
    if not rel.startswith('raw/'):
        return False
    rest = rel[4:]  # 去掉 raw/
    full = os.path.join(RAW, rest)
    if os.path.isfile(full):
        return True
    if os.path.isfile(full + '.md'):
        return True
    if os.path.isdir(full):
        return True
    return False


# ---------- 1. 构建人名→figures 页的反向索引 ----------

figure_pages = {}        # {文件名: 完整路径}
name_to_files = defaultdict(set)  # {规范名: {文件名}}
file_to_canon = {}       # {文件名: 规范名(标题第一行)}

for f in os.listdir(FIG_DIR):
    if not f.endswith('.md') or f.startswith('_'):
        continue
    path = os.path.join(FIG_DIR, f)
    text = read(path)
    canon_match = re.search(r'^#\s+(.+?)\s*[（(]', text, re.MULTILINE)
    canon = canon_match.group(1).strip() if canon_match else f[:-3]
    file_to_canon[f[:-3]] = canon
    aliases = parse_aliases(text)
    name_to_files[canon].add(f[:-3])
    for a in aliases:
        name_to_files[a].add(f[:-3])
    figure_pages[f[:-3]] = path

print(f'figures 页总数: {len(figure_pages)}')

# ---------- 2. 预读全部 summaries 正文（后续复用）----------

summary_texts = {}
for f in os.listdir(SUM_DIR):
    if not f.endswith('.md') or f.startswith('_'):
        continue
    summary_texts[f[:-3]] = read(os.path.join(SUM_DIR, f))

print(f'summaries 页总数: {len(summary_texts)}')

# ---------- 3. 审计函数 ----------

findings = []  # list of (severity, figure_name, category, detail, evidence)

YEAR_RANGE_RE = re.compile(r'(\d{4})\s*[–\-—至到]\s*(\d{4})')
BIRTH_ONLY_RE = re.compile(r'(?:生于|出生于|生卒)\s*[:：]?\s*(\d{4})\s*年')
DEATH_ONLY_RE = re.compile(r'(\d{4})\s*年.*?(?:逝|卒|逝世|去世|过世)')
NATIONALITY_RE = re.compile(r'国[别籍]\s*[/／]\s*(?:时代)?\s*[:：]?\s*(.+?)(?:[，,]|$)')

# 国籍词典（用于交叉比对）
NATION_KEYWORDS = {
    '英国': ['英国', '英格兰', '苏格兰', '威尔士', 'British', 'English', 'Scottish'],
    '法国': ['法国', '法兰西', 'French'],
    '德国': ['德国', '德意志', '德国籍', 'German'],
    '意大利': ['意大利', 'Italian'],
    '西班牙': ['西班牙', 'Spanish'],
    '俄国/苏联': ['俄国', '俄罗斯', '苏联', 'Russian', 'Soviet'],
    '美国': ['美国', 'American', 'USA'],
    '中国': ['中国', 'Chinese'],
    '日本': ['日本', 'Japanese'],
    '希腊': ['希腊', 'Greek'],
    '荷兰': ['荷兰', 'Dutch'],
    '爱尔兰': ['爱尔兰', 'Irish'],
}


def audit_one_figure(fname, path):
    text = read(path)
    body = body_of(text)
    canon = file_to_canon.get(fname, fname)

    # --- 3a. 生卒年数学自洽性 ---
    title_years = YEAR_RANGE_RE.search(text.split('\n')[3] if text.startswith('---') else text[:200])
    if title_years:
        y1, y2 = int(title_years.group(1)), int(title_years.group(2))
        if y2 - y1 < 15 or y2 - y1 > 100:
            findings.append(('CRITICAL', canon, '生卒年数学异常',
                             f'标题行 {y1}-{y2}：寿数 {y2-y1} 岁不在合理区间 [15,100]',
                             f'文件: {fname}'))

    # --- 3b. 阿拉贡式"享年 X 岁"算术检查 ---
    for m in re.finditer(r'(\d{4})\s*年.*?(?:逝|卒|逝世|去世).*?享年\s*(\d{1,3})\s*岁', text):
        year, age = int(m.group(1)), int(m.group(2))
        implied_birth = year - age
        if title_years and abs(implied_birth - int(title_years.group(1))) > 5:
            findings.append(('MAJOR', canon, '生卒年算术矛盾',
                             f'享年 {age} 岁逝于 {year} → 推出生 {implied_birth}，但标题写 {title_years.group(1)}-{title_years.group(2)}',
                             f'文件: {fname}'))

    # --- 3c. 与 summaries 交叉比对生卒年 ---
    aliases = [canon] + list(parse_aliases(text))
    mentioned_in_sums = []
    sum_years = defaultdict(set)   # {year_str: {来源summary名}}
    sum_nations = defaultdict(set)  # {nation_str: {来源summary名}}

    for sname, stext in summary_texts.items():
        matched_alias = None
        for a in aliases:
            if len(a) >= 2 and a in stext:
                matched_alias = a
                break
        if matched_alias:
            mentioned_in_sums.append(sname)
            # 抽取 summary 中紧邻人物名的生卒年（100字符窗口内）
            for mb in BIRTH_ONLY_RE.finditer(stext):
                context = stext[max(0, mb.start()-100):mb.end()+100]
                if matched_alias in context:
                    sum_years[f'生于{mb.group(1)}'].add(sname)
            for md in DEATH_ONLY_RE.finditer(stext):
                context = stext[max(0, md.start()-100):md.end()+100]
                if matched_alias in context:
                    sum_years[f'卒{md.group(1)}'].add(sname)
            for my in YEAR_RANGE_RE.finditer(stext):
                context = stext[max(0, my.start()-100):my.end()+100]
                if matched_alias in context:
                    # 排除运动/流派时间范围描述（如"1910—1918年间活跃于英国"）
                    if any(kw in context for kw in ['年间', '时期', '活跃', '运动', '流派', '时期']):
                        continue
                    sum_years[f'{my.group(1)}-{my.group(2)}'].add(sname)
            # 抽取国籍（同样限制在人物名邻近窗口）
            for nk, kws in NATION_KEYWORDS.items():
                for kw in kws:
                    if kw in stext and matched_alias in stext:
                        # 检查 kw 和别名是否在相近位置出现
                        kw_pos = [m.start() for m in re.finditer(re.escape(kw), stext)]
                        alias_pos = [m.start() for m in re.finditer(re.escape(matched_alias), stext)]
                        if any(abs(k - a) < 200 for k in kw_pos for a in alias_pos):
                            sum_nations[nk].add(sname)

    # 如果 summary 提到生卒年且与 figures 页不同 → 矛盾
    if title_years and sum_years:
        fy1, fy2 = title_years.group(1), title_years.group(2)
        for sy, srcs in sum_years.items():
            if '-' in sy:
                sy1, sy2 = sy.split('-')
                if fy1 != sy1 or fy2 != sy2:
                    findings.append(('MAJOR', canon, '生卒年与summary矛盾',
                                     f'figures 页 {fy1}-{fy2}；summary {sy}（来源: {list(srcs)[:3]}）',
                                     f'文件: {fname}'))

    # --- 3d. 未被任何 summary 提及且无 frontmatter sources 的页面 → 高风险幻觉 ---
    raw_links, at_links, others = parse_sources(text)
    if not mentioned_in_sums and not raw_links and not at_links:
        findings.append(('MAJOR', canon, '孤立页面（无summary交叉+无来源）',
                         '该 figures 页未被任何 summary 提及，且 frontmatter 无 sources 字段。生平数据可能全部源自幻觉。',
                         f'文件: {fname}'))

    # --- 3e. 来源文件有效性检查 ---
    for rl in raw_links:
        if not raw_file_exists(rl):
            findings.append(('CRITICAL', canon, '无效来源链接',
                             f'frontmatter sources 指向 {rl} 但 raw 中不存在',
                             f'文件: {fname}'))
        # 特别检查：_meta.md 或目录文件作来源（不是正文）
        slice_name = rl[4:] if rl.startswith('raw/') else rl
        if '_meta' in slice_name or '前言' in slice_name:
            findings.append(('MINOR', canon, '来源为非正文切片',
                             f'sources 包含 {rl}（可能是目录/元数据文件，非正文）',
                             f'文件: {fname}'))

    # --- 3f. 内部自相矛盾：标题国籍 vs tags vs 生平 ---
    nations_in_text = set()
    for nk, kws in NATION_KEYWORDS.items():
        for kw in kws:
            if kw in body:
                nations_in_text.add(nk)

    if len(nations_in_text) >= 4:
        findings.append(('MINOR', canon, '多国籍关键词',
                         f'正文/标题中同时出现 {len(nations_in_text)} 个国籍关键词: {", ".join(sorted(nations_in_text))}',
                         f'文件: {fname}'))

    # --- 3g. 可疑断言：生平含"原为…学家"但实为常见误写 ---
    suspicious_patterns = [
        (r'精神病患者学家', '应为"精神病理学家"或"精神病学家"'),
        (r'被迫离开大学.*犹太血统', '犹太血统被迫离开大学通常指妻子，本人非犹太'),
    ]
    for pat, note in suspicious_patterns:
        if re.search(pat, body):
            findings.append(('MAJOR', canon, '可疑断言', note + f'（匹配: {pat}）',
                             f'文件: {fname}'))

    # --- 3h. stub 页识别（正文 < 50 字且无生平数据） ---
    non_fm = body.strip()
    if len(non_fm) < 50:
        findings.append(('INFO', canon, 'stub/空页',
                         f'正文仅 {len(non_fm)} 字符，无实质生平数据',
                         f'文件: {fname}'))

    return mentioned_in_sums


# ---------- 4. 执行审计 ----------

print('\n=== 开始审计 ===\n')
covered = defaultdict(int)  # {filename: mentions in summaries}
for fname, path in figure_pages.items():
    mentions = audit_one_figure(fname, path)
    covered[fname] = len(mentions)

# ---------- 5. 输出分级报告 ----------

by_sev = defaultdict(list)
for sev, name, cat, detail, evidence in findings:
    by_sev[sev].append((name, cat, detail, evidence))

sev_order = ['CRITICAL', 'MAJOR', 'MINOR', 'INFO']
sev_emoji = {'CRITICAL': '🔴', 'MAJOR': '🟠', 'MINOR': '🟡', 'INFO': '🔵'}

total_figures = len(figure_pages)
orphan_figs = [f for f, n in covered.items() if n == 0]
well_covered = [f for f, n in covered.items() if n >= 3]

print(f'\n======= 幻觉与矛盾审计总览 =======')
print(f'figures 总数: {total_figures}')
print(f'零 summary 覆盖（高风险）: {len(orphan_figs)}')
print(f'≥3 summary 覆盖（可信）: {len(well_covered)}')
print()
for sev in sev_order:
    items = by_sev.get(sev, [])
    if items:
        print(f'{sev_emoji[sev]} {sev}: {len(items)} 条')
        for name, cat, detail, ev in items[:8]:
            print(f'   [{name}] {cat}: {detail[:120]}')
        if len(items) > 8:
            print(f'   ... 还有 {len(items)-8} 条，详见报告文件')
        print()

# ---------- 6. 写报告文件 ----------

report_path = os.path.join(KB_ROOT, '_audit_report.md')
today = datetime.date.today().isoformat()
lines = [f'# 幻觉与矛盾审计报告（{today}）\n',
         f'扫描范围: figures 层 {total_figures} 页，summaries {len(summary_texts)} 页\n',
         '## 覆盖度\n',
         f'- 零 summary 覆盖（高风险幻觉源）: **{len(orphan_figs)}**',
         f'- 1-2 summary 覆盖: **{sum(1 for f,n in covered.items() if 0 < n < 3)}**',
         f'- ≥3 summary 覆盖（交叉验证充分）: **{len(well_covered)}**\n']

for sev in sev_order:
    items = by_sev.get(sev, [])
    lines.append(f'## {sev_emoji[sev]} {sev}（{len(items)} 条）\n')
    for name, cat, detail, ev in items:
        lines.append(f'- **{name}** · {cat}')
        lines.append(f'  - {detail}')
        lines.append(f'  - 证据: `{ev}`')
    lines.append('')

lines.append('## 零覆盖 figures 清单（需优先核查）\n')
for f in sorted(orphan_figs):
    lines.append(f'- [[figures/{f}]]')

with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'\n完整报告: {report_path}')
