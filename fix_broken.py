"""
批量修复断链脚本 v2
- 裸链接加 folder 前缀
- summary 链接文件名不匹配修正
- 输出需要人工判断的疑难项
"""
import os, re, sys
from collections import Counter, defaultdict

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
changed_files = set()
total_fixes = 0

# 1. 收集所有现有页面名（不含 folder）
existing_basenames = set()
existing_fullpaths = set()
for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d not in ('.obsidian', '__pycache__')]
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md','task_plan.md'):
            continue
        fpath = os.path.join(root, fname)
        relpath = os.path.relpath(fpath, base).replace('.md', '').lower()
        existing_fullpaths.add(relpath)
        basename = relpath.split('/')[-1]
        existing_basenames.add(basename)

# 收集现有 folder 中的 basename 到 fullpath 映射
basename_to_fullpaths = defaultdict(list)
for ep in existing_fullpaths:
    bn = ep.split('/')[-1]
    basename_to_fullpaths[bn].append(ep)

# 别名映射（从 frontmatter 提取）
aliases_to_fullpath = {}
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md','task_plan.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        relpath = os.path.relpath(fpath, base).replace('.md', '').lower()
        # frontmatter type
        type_m = re.search(r'^type:\s*(\w+)', content, re.MULTILINE)
        page_type = type_m.group(1) if type_m else ''
        # aliases
        for m in re.finditer(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', content, re.MULTILINE):
            for line in m.group(1).split('\n'):
                line = line.strip().lstrip('-').strip().strip('"').strip("'")
                if line:
                    key = line.lower()
                    aliases_to_fullpath.setdefault(key, []).append(relpath)
        for m in re.finditer(r'^aliases:\s*\[(.*?)\]', content, re.MULTILINE):
            for a in m.group(1).split(','):
                a = a.strip().strip('"').strip("'")
                if a:
                    key = a.lower()
                    aliases_to_fullpath.setdefault(key, []).append(relpath)

# 2. 定义启发式规则
# 常见流派/学派关键词（→ movements）
MOVEMENT_KEYWORDS = ['批评', '学派', '流派', '主义', '论', '运动', '派', '转向', '传统']
# 常见概念关键词（→ concepts）
CONCEPT_KEYWORDS = ['理论', '概念', '范畴', '原则', '方法', '结构', '功能', '模式', '原型', '符号']

def guess_folder(target, existing_page_type=None):
    """猜测裸链接应该归属的 folder"""
    t = target.lower().strip()
    
    # 如果已有同名 basename 的 page，用它的 folder
    matches = basename_to_fullpaths.get(t, [])
    if matches:
        # 取第一个非 summary 的
        for m in matches:
            if not m.startswith('summaries/'):
                return m.split('/')[0]
        return matches[0].split('/')[0]
    
    # 别名匹配
    alias_matches = aliases_to_fullpath.get(t, [])
    if alias_matches:
        return alias_matches[0].split('/')[0]
    
    # 启发式：判断是人名还是流派/概念
    # 人名特征：2-4字中文名，不含"学派/主义/理论"等
    if len(target) <= 4 and not any(kw in target for kw in MOVEMENT_KEYWORDS + CONCEPT_KEYWORDS):
        return 'figures'
    if any(kw in target for kw in MOVEMENT_KEYWORDS):
        return 'movements'
    if any(kw in target for kw in CONCEPT_KEYWORDS):
        return 'concepts'
    # 其他默认 concepts
    return 'concepts'

def find_canonical_path(target):
    """找到 target 对应的规范路径，返回 (folder, basename) 或 None"""
    t = target.lower().strip()
    
    # 已有 basename 匹配
    matches = basename_to_fullpaths.get(t, [])
    if matches:
        # 优先 figure/movement/concept/work，避免 summary
        for pref in ['figures/', 'movements/', 'concepts/', 'works/', 'comparisons/', 'overviews/']:
            for m in matches:
                if m.startswith(pref):
                    return m
        return matches[0]
    
    # 别名匹配
    alias_matches = aliases_to_fullpath.get(t, [])
    if alias_matches:
        for pref in ['figures/', 'movements/', 'concepts/', 'works/']:
            for m in alias_matches:
                if m.startswith(pref):
                    return m
        return alias_matches[0]
    
    # 可能是 summary 的别名 → 搜索 summary
    for ep in existing_fullpaths:
        if ep.startswith('summaries/') and ep.endswith('/' + t):
            return ep
    
    return None

# 3. 扫描所有 md 文件，修复断链
stats = Counter()
manual_review = []

for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d not in ('.obsidian', '__pycache__')]
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md','task_plan.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        def fix_link(m):
            link = m.group(1).strip()
            # 跳过 @ 引用和 raw 链接
            if link.startswith('@') or link.startswith('raw/'):
                return m.group(0)
            
            target = link.lower()
            display = m.group(0)
            
            # Case 1: 已有 folder 前缀
            if '/' in target:
                folder = target.split('/')[0]
                basename = target.split('/')[-1]
                
                # 检查 canonical path
                canonical = find_canonical_path(basename)
                if canonical and canonical != target:
                    # 有规范路径 → 修正
                    new_link = canonical
                    stats['canonical_fix'] += 1
                    # 保留 display text
                    if '|' in m.group(0):
                        display_text = m.group(0).split('|')[1].rstrip(']]')
                        return f'[[{new_link}|{display_text}]]'
                    return f'[[{new_link}]]'
                
                # 确实不存在的 folder+basename → 记录
                if folder in ('figures','concepts','movements','works','summaries','comparisons','overviews','synthesis'):
                    if target not in existing_fullpaths and not any(ep.endswith('/' + basename) for ep in existing_fullpaths):
                        stats['missing_page'] += 1
                        manual_review.append(f'  {target}  (in {os.path.relpath(fpath, base)})')
                return m.group(0)
            
            # Case 2: 裸链接无 folder
            canonical = find_canonical_path(link)
            if canonical:
                new_link = canonical
                stats['bare_fix_known'] += 1
                if '|' in m.group(0):
                    display_text = m.group(0).split('|')[1].rstrip(']]')
                    return f'[[{new_link}|{display_text}]]'
                return f'[[{new_link}]]'
            
            # 猜测 folder
            folder = guess_folder(link)
            guessed = f'{folder}/{link}'
            # 检查猜测的目标是否存在
            guessed_exists = (guessed in existing_fullpaths) or any(ep.endswith('/' + guessed.split('/')[-1]) for ep in existing_fullpaths)
            if guessed_exists:
                stats['bare_fix_guess'] += 1
                return f'[[{guessed}]]'
            
            # 真的不存在，记录待人工
            stats['bare_missing'] += 1
            manual_review.append(f'  bare: [[{link}]]  → guess [[{guessed}]]  (in {os.path.relpath(fpath, base)})')
            return m.group(0)
        
        content = re.sub(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', fix_link, content)
        
        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            changed_files.add(os.path.relpath(fpath, base))

total_fixes = sum(stats.values())

# 4. 输出报告
print(f'=== 批量断链修复报告 ===')
print(f'修复总数: {total_fixes}')
print(f'修改文件: {len(changed_files)}')
print()
print(f'修复类型:')
for k, v in stats.items():
    print(f'  {k}: {v}')
print()
if manual_review:
    print(f'=== 需人工判断 ({len(manual_review)} 项) ===')
    for item in manual_review[:80]:
        print(item)
    if len(manual_review) > 80:
        print(f'  ... 还有 {len(manual_review)-80} 项')
print()
print('=== 修改的文件 ===')
for f in sorted(changed_files):
    print(f'  {f}')
