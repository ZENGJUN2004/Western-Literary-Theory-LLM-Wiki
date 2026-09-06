"""
精确诊断剩余断链（基于 check_detail.py 的 350 targets）
输出：可自动修复 vs 需新建 vs summaries 文件名不匹配
"""
import os, re, difflib
from collections import Counter, defaultdict

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'

# 1. 收集现有页面信息
existing_fullpaths = set()
existing_basenames = {}  # basename → list of fullpaths
aliases_map = {}  # alias → canonical fullpath

for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md','_index.md','task_plan.md'):
            continue
        fpath = os.path.join(root, fname)
        rel = os.path.relpath(fpath, base).replace('.md', '').lower()
        existing_fullpaths.add(rel)
        bn = rel.split('/')[-1]
        existing_basenames.setdefault(bn, []).append(rel)
        
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', content, re.MULTILINE):
            for line in m.group(1).split('\n'):
                line = line.strip().lstrip('-').strip().strip('"').strip("'").lower()
                if line:
                    aliases_map.setdefault(line, []).append(rel)
        for m in re.finditer(r'^aliases:\s*\[(.*?)\]', content, re.MULTILINE):
            for a in m.group(1).split(','):
                a = a.strip().strip('"').strip("'").lower()
                if a:
                    aliases_map.setdefault(a, []).append(rel)

# 2. 扫描所有 [[...]] 链接
all_links = defaultdict(list)
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md','_index.md','task_plan.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', content):
            link = m.group(1).strip()
            if link.startswith('@') or link.startswith('raw/'):
                continue
            all_links[link].append(os.path.relpath(fpath, base))

# 3. 分类每个 link
categories = {
    'ok': [],           # 已有 canonical path
    'bare_fixable': [], # 裸链接但可通过 basename/alias 找到
    'bare_guessable': [], # 裸链接可猜测 folder + basename 存在
    'summary_fuzzy': [], # summaries 文件名可能不匹配
    'folder_missing': [], # 有 folder 前缀但目标真不存在
    'totally_missing': [], # 真的找不到任何匹配
}

# folder 关键词启发式
FOLDER_HINTS = {
    'figures': ['先生','博士','教授','主义者','创始人','奠基人','思想家','批评家','作家','哲学家','理论家','后','先生'],
    'movements': ['主义','学派','流派','运动','派','转向','传统','批评','诗学'],
    'concepts': ['理论','概念','范畴','原则','方法','结构','功能','模式','原型','符号','效果','精神','力量','秩序'],
    'works': ['《','》','book','book of']
}

def find_canonical(target):
    t = target.lower().strip()
    if '/' in t:
        folder = t.split('/')[0]
        bn = t.split('/')[-1]
        if t in existing_fullpaths:
            return t
        if bn in existing_basenames:
            # 优先非 summary
            for ep in existing_basenames[bn]:
                if folder and ep.startswith(folder + '/'):
                    return ep
            return existing_basenames[bn][0]
        if t in aliases_map:
            return aliases_map[t][0]
        return None
    # 裸链接
    if t in aliases_map:
        return aliases_map[t][0]
    if t in existing_basenames:
        # 优先 figure/movement/concept/work
        for pref in ['figures/','movements/','concepts/','works/','summaries/','comparisons/','overviews/']:
            for ep in existing_basenames[t]:
                if ep.startswith(pref):
                    return ep
        return existing_basenames[t][0]
    return None

def guess_folder(target):
    t = target.lower().strip()
    # 检查是否是 summaries 类
    if t.startswith('朱立元-') or t.startswith('最新文论教程-') or t.startswith('马新国-'):
        return 'summaries'
    for folder, keywords in FOLDER_HINTS.items():
        for kw in keywords:
            if kw in t:
                return folder
    # 人名判断：2-5 个中文字，无流派关键词
    cn_chars = re.findall(r'[\u4e00-\u9fff]', t)
    if 2 <= len(cn_chars) <= 4 and not any(kw in t for kw in ['主义','理论','学派','概念','方法']):
        return 'figures'
    # 默认
    return 'concepts'

def fuzzy_find_summary(target):
    """对 summaries/朱立元-xxx 的模糊匹配"""
    t = target.lower()
    if not t.startswith('朱立元-'):
        return None
    # 提取数字前缀
    num_match = re.match(r'朱立元-(\d+(?:-\d+)*)', t)
    if num_match:
        num = num_match.group(1)
        for ep in existing_fullpaths:
            if ep.startswith('summaries/朱立元-') and ('-' + num + '-' in ep or ep.endswith('朱立元-' + num)):
                return ep
    # 模糊匹配 basename 重叠
    for ep in existing_fullpaths:
        if ep.startswith('summaries/朱立元-'):
            ep_name = ep.split('/')[-1]
            ratio = difflib.SequenceMatcher(None, t, ep_name).ratio()
            if ratio > 0.6:
                return ep
    return None

for link, files in sorted(all_links.items(), key=lambda x: -len(x[1])):
    canonical = find_canonical(link)
    
    if canonical:
        categories['ok'].append((link, canonical, len(files)))
        continue
    
    if '/' not in link:
        # 裸链接
        folder = guess_folder(link)
        guessed = f'{folder}/{link}'
        if guessed in existing_fullpaths:
            categories['bare_fixable'].append((link, guessed, len(files)))
            continue
        # summaries 模糊匹配
        if link.lower().startswith('朱立元-') or link.lower().startswith('最新文论教程-') or link.lower().startswith('马新国-'):
            fuzzy = fuzzy_find_summary(link)
            if fuzzy:
                categories['summary_fuzzy'].append((link, fuzzy, len(files)))
                continue
        # basename 模糊匹配
        for ep in existing_fullpaths:
            bn = ep.split('/')[-1]
            if difflib.SequenceMatcher(None, link.lower(), bn).ratio() > 0.7:
                categories['summary_fuzzy'].append((link, ep, len(files)))
                break
        else:
            categories['bare_guessable'].append((link, folder, len(files)))
            continue
        continue
    
    # 有 folder 前缀但没找到
    folder = link.split('/')[0]
    if folder in ('summaries',):
        fuzzy = fuzzy_find_summary(link)
        if fuzzy:
            categories['summary_fuzzy'].append((link, fuzzy, len(files)))
            continue
    
    categories['folder_missing'].append((link, len(files)))

# 4. 输出
print(f"=== 链接分类统计 ===")
for k, v in categories.items():
    print(f"  {k}: {len(v)} 个目标")

print()
print("=== bare_fixable（可自动加 folder 前缀）===")
for link, guessed, n in categories['bare_fixable'][:30]:
    print(f"  [[{link}]] → [[{guessed}]]  ({n} refs)")

print()
print("=== summary_fuzzy（summaries 文件名模糊匹配）===")
for link, ep, n in categories['summary_fuzzy'][:30]:
    print(f"  [[{link}]] → [[{ep}]]  ({n} refs)")

print()
print("=== folder_missing（有前缀但真不存在）===")
for link, n in categories['folder_missing'][:30]:
    print(f"  [[{link}]] ({n} refs)")

print()
print("=== totally_missing（真找不到）===")
for link, folder, n in categories['bare_guessable'][:50]:
    print(f"  [[{link}]] → guess [{folder}] ({n} refs)")
