import os, re

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'

# Collect all existing wiki pages
existing_pages = set()
for root, dirs, files in os.walk(base):
    for fname in files:
        if fname.endswith('.md') and fname not in ('_log.md', '_index.md'):
            relpath = os.path.relpath(os.path.join(root, fname), base)
            existing_pages.add(relpath.replace('.md', '').lower())

alias_pages = set()
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        alias_match = re.search(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', content, re.MULTILINE)
        if alias_match:
            for line in alias_match.group(1).split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    alias = line[1:].strip().strip('"').strip("'")
                    if alias:
                        alias_pages.add(alias.lower())

all_existing = existing_pages | alias_pages

# Find all broken [[...]] links (excluding @ citations and raw/ paths)
broken = {}
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        link_matches = re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', content)
        for m in link_matches:
            link = m.group(1).strip()
            # Skip non-wiki links: @ citations, raw/ paths, external links
            if link.startswith('@') or link.startswith('raw/'):
                continue
            if '/' not in link:
                continue
            target = link.lower()
            if target not in all_existing:
                basename = target.split('/')[-1] if '/' in target else target
                found = False
                for ep in all_existing:
                    if ep == target or ep.endswith('/' + basename) or basename in ep:
                        found = True
                        break
                if not found:
                    relpath = os.path.relpath(fpath, base)
                    if relpath not in broken:
                        broken[relpath] = []
                    broken[relpath].append(link)

# Count by category
figures_broken = sum(1 for links in broken.values() for l in links if l.startswith('figures/'))
concepts_broken = sum(1 for links in broken.values() for l in links if l.startswith('concepts/'))
movements_broken = sum(1 for links in broken.values() for l in links if l.startswith('movements/'))
works_broken = sum(1 for links in broken.values() for l in links if l.startswith('works/'))
other_broken = sum(1 for links in broken.values() for l in links if not any(l.startswith(p) for p in ['figures/', 'concepts/', 'movements/', 'works/']))

total_broken = figures_broken + concepts_broken + movements_broken + works_broken + other_broken

print(f'Broken wiki page links summary (excluding @ citations and raw/ paths):')
print(f'  figures/: {figures_broken}')
print(f'  concepts/: {concepts_broken}')
print(f'  movements/: {movements_broken}')
print(f'  works/: {works_broken}')
print(f'  other: {other_broken}')
print(f'  TOTAL: {total_broken}')
print(f'Files with broken links: {len(broken)}')

# Show unique broken targets
all_broken_targets = set()
for links in broken.values():
    all_broken_targets.update(links)
print(f'\nUnique broken targets: {len(all_broken_targets)}')
for t in sorted(all_broken_targets):
    print(f'  - {t}')
