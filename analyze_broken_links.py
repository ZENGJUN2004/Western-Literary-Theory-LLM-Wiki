import os, re
from collections import Counter

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

# Find all broken links and count frequency
broken_links = Counter()
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
                    broken_links[target] += 1

# Sort by frequency
print("=== Broken Links by Frequency (High Priority) ===\n")

# figures
figures = [(k, v) for k, v in broken_links.items() if k.startswith('figures/')]
figures.sort(key=lambda x: -x[1])
print(f"--- figures/ ({len(figures)} unique, {sum(v for k,v in figures)} total refs) ---")
for link, count in figures[:40]:
    print(f"  {count:3d}x  {link}")

print()

# concepts
concepts = [(k, v) for k, v in broken_links.items() if k.startswith('concepts/')]
concepts.sort(key=lambda x: -x[1])
print(f"--- concepts/ ({len(concepts)} unique, {sum(v for k,v in concepts)} total refs) ---")
for link, count in concepts[:40]:
    print(f"  {count:3d}x  {link}")

print()

# movements
movements = [(k, v) for k, v in broken_links.items() if k.startswith('movements/')]
movements.sort(key=lambda x: -x[1])
print(f"--- movements/ ({len(movements)} unique, {sum(v for k,v in movements)} total refs) ---")
for link, count in movements:
    print(f"  {count:3d}x  {link}")

print()

# works
works = [(k, v) for k, v in broken_links.items() if k.startswith('works/')]
works.sort(key=lambda x: -x[1])
print(f"--- works/ ({len(works)} unique, {sum(v for k,v in works)} total refs) ---")
for link, count in works:
    print(f"  {count:3d}x  {link}")

print()

# summaries
summaries = [(k, v) for k, v in broken_links.items() if k.startswith('summaries/')]
summaries.sort(key=lambda x: -x[1])
print(f"--- summaries/ ({len(summaries)} unique, {sum(v for k,v in summaries)} total refs) ---")
for link, count in summaries:
    print(f"  {count:3d}x  {link}")

# Save to file for reference
with open(os.path.join(base, '..', '_broken_links_priority.txt'), 'w', encoding='utf-8') as f:
    f.write("=== Broken Links by Frequency ===\n\n")
    for link, count in sorted(broken_links.items(), key=lambda x: -x[1]):
        f.write(f"  {count:3d}x  {link}\n")

print(f"\nSaved priority list to _broken_links_priority.txt")
