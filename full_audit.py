import os, re
from collections import Counter, defaultdict

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb'
wiki = os.path.join(base, 'wiki')
raw = os.path.join(base, 'raw')

skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}

# 1. Wiki layers
print('=== WIKI PAGES ===')
layer_counts = {}
for root,_,fs in os.walk(wiki):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            top = os.path.relpath(os.path.join(root,f),wiki).split(os.sep)[0]
            layer_counts[top] = layer_counts.get(top,0)+1
for k in sorted(layer_counts):
    print(f'  {k:14s}: {layer_counts[k]:4d}')
total_wiki = sum(layer_counts.values())
print(f'  TOTAL         : {total_wiki:4d}')

# 2. Raw slices
print()
print('=== RAW SLICES ===')
raw_counts = {}
for d in sorted(os.listdir(raw)):
    dp = os.path.join(raw,d)
    if os.path.isdir(dp):
        cnt = len([f for f in os.listdir(dp) if f.endswith('.md')])
        raw_counts[d] = cnt
        print(f'  {d:30s}: {cnt:4d}')
total_raw = sum(raw_counts.values())
print(f'  TOTAL                         : {total_raw:4d}')

# 3. Summaries by textbook
print()
print('=== SUMMARIES BY TEXTBOOK ===')
summ_dir = os.path.join(wiki,'summaries')
textbook_chapters = defaultdict(set)
unclassified = []
for f in os.listdir(summ_dir):
    if f.endswith('.md') and f not in skip:
        name = f.replace('.md','')
        matched = False
        for prefix in ['马新国','朱立元','最新文论教程','理论史教程一','理论史教程二','名著教程','五种模式','二十世纪文论选','伍蠡甫','导引出版','司各特','文学理论入门','反世界文学','汉语经验']:
            if name.startswith(prefix):
                m = re.search(r'-(\d{2})', name)
                ch = m.group(1) if m else '??'
                textbook_chapters[prefix].add(ch)
                matched = True
                break
        if not matched:
            unclassified.append(name)
for k in sorted(textbook_chapters):
    chs = sorted(textbook_chapters[k])
    print(f'  {k:16s}: {len(chs):3d} summaries  chs: {chs[:25]}')
if unclassified:
    print(f'  其他             : {len(unclassified):3d} items')
    for u in unclassified[:10]:
        print(f'    {u}')

# 4. Placeholder check
print()
print('=== PLACEHOLDER / INGESTED STATUS ===')
ph = ing = 0
for root,_,fs in os.walk(wiki):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            with open(os.path.join(root,f),'r',encoding='utf-8') as fh:
                c = fh.read(500)
            if 'status: placeholder' in c:
                ph += 1
            elif 'status: ingested' in c:
                ing += 1
print(f'  placeholder: {ph}')
print(f'  ingested   : {ing}')

# 5. Broken links
print()
print('=== BROKEN LINKS ===')
existing = set()
for root,_,fs in os.walk(wiki):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            existing.add(os.path.relpath(os.path.join(root,f),wiki).replace('.md','').lower())
broken = Counter()
for root,_,fs in os.walk(wiki):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        with open(os.path.join(root,f),'r',encoding='utf-8') as fh: c = fh.read()
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', c):
            link = m.group(1).strip()
            if link.startswith('@') or link.startswith('raw/'): continue
            if '/' not in link: continue
            t = link.lower()
            if t not in existing:
                bn = t.split('/')[-1]
                if not any(ep.endswith('/'+bn) for ep in existing):
                    broken[t] += 1
print(f'  broken: {sum(broken.values())} refs / {len(broken)} targets')
if broken:
    for k,v in sorted(broken.items(), key=lambda x:-x[1])[:15]:
        print(f'    {v}x  {k}')

# 6. Cross-layer connectivity
print()
print('=== CROSS-LAYER LINK DENSITY ===')
layer_links = defaultdict(lambda: defaultdict(int))
for root,_,fs in os.walk(wiki):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        src_layer = os.path.relpath(os.path.join(root,f),wiki).split(os.sep)[0]
        with open(os.path.join(root,f),'r',encoding='utf-8') as fh: c = fh.read()
        for m in re.finditer(r'\[\[(figures|concepts|movements|works|summaries|comparisons|overviews|synthesis)/([^\]|]+?)', c):
            layer_links[src_layer][m.group(1)] += 1
for src in sorted(layer_links):
    targets = layer_links[src]
    parts = ', '.join(f'{t}:{n}' for t,n in sorted(targets.items(), key=lambda x:-x[1]))
    print(f'  {src:14s} -> {parts}')

# 7. Average links per page by layer
print()
print('=== AVG LINKS/PAGE ===')
for layer in sorted(layer_counts):
    if layer_counts[layer] == 0: continue
    total_links = sum(layer_links[layer].values())
    avg = total_links / layer_counts[layer] if layer_counts[layer] else 0
    print(f'  {layer:14s}: {avg:.1f} links/page ({total_links} total)')
