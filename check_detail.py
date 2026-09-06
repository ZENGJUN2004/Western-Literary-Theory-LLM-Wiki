import os, re
from collections import Counter

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'

existing = set()
aliases = set()
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md','task_plan.md','_check.py','_generate.py','check_broken.py','check_missing.py'):
            continue
        fpath = os.path.join(root, fname)
        relpath = os.path.relpath(fpath, base)
        existing.add(relpath.replace('.md', '').lower())
        with open(fpath, 'r', encoding='utf-8') as f:
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

broken = Counter()
broken_files = {}
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md','task_plan.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', content):
            link = m.group(1).strip()
            if link.startswith('@') or link.startswith('raw/'):
                continue
            target = link.lower()
            basename = target.split('/')[-1] if '/' in target else target
            if target not in all_existing and not any(ep.endswith('/' + basename) for ep in all_existing) and basename not in all_existing and not any(ep.endswith(basename) for ep in all_existing):
                broken[target] += 1
                broken_files.setdefault(target, []).append(os.path.relpath(fpath, base))

print(f'TOTAL broken: {sum(broken.values())} refs / {len(broken)} targets')
print()
for k, v in broken.most_common():
    files = broken_files[k][:3]
    print(f'  {v:2d}x  {k}  →  {", ".join(files)}')
