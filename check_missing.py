import os, re, sys
from collections import Counter

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'

# 1. 收集所有现有页面和 aliases
existing = set()
aliases = set()
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md'):
            continue
        relpath = os.path.relpath(os.path.join(root, fname), base)
        existing.add(relpath.replace('.md', '').lower())
        # aliases
        with open(os.path.join(root, fname), 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', content, re.MULTILINE):
            for line in m.group(1).split('\n'):
                line = line.strip().lstrip('-').strip().strip('"').strip("'")
                if line:
                    aliases.add(line.lower())
        for m in re.finditer(r'^aliases:\s*\[(.*?)\]', content, re.MULTILINE):
            for a in m.group(1).split(','):
                a = a.strip().strip('"').strip("'")
                if a:
                    aliases.add(a.lower())

all_existing = existing | aliases

# 2. 扫描所有断链
broken = Counter()
broken_files = {}
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', content):
            link = m.group(1).strip()
            if link.startswith('@') or link.startswith('raw/') or '/' not in link:
                continue
            target = link.lower()
            basename = target.split('/')[-1]
            if target not in all_existing and not any(ep.endswith('/' + basename) for ep in all_existing):
                broken[target] += 1
                broken_files.setdefault(target, []).append(fname)

# 3. 分类输出
print(f'现存页面: {len(existing)}, aliases: {len(aliases)}')
print(f'断链: {sum(broken.values())} refs / {len(broken)} targets')
print()

cats = {'figures': [], 'concepts': [], 'movements': [], 'works': []}
for k, v in broken.most_common():
    cat = k.split('/')[0]
    if cat in cats:
        cats[cat].append((k, v))

for cat, items in cats.items():
    if items:
        print(f'=== {cat.upper()} ({len(items)} targets) ===')
        for k, v in items:
            print(f'  {v:2d}x  {k}')
        print()
