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
            top = os.path.relpath(os.path.join(root,f),wiki).replace(os.sep,'/').split('/')[0]
            layer_counts[top] = layer_counts.get(top,0)+1
for k in sorted(layer_counts):
    print(f'  {k:14s}: {layer_counts[k]:4d}')
print(f'  TOTAL         : {sum(layer_counts.values()):4d}')

# 2. Raw slices
print('\n=== RAW SLICES ===')
raw_counts = {}
for d in sorted(os.listdir(raw)):
    dp = os.path.join(raw,d)
    if os.path.isdir(dp):
        cnt = len([f for f in os.listdir(dp) if f.endswith('.md')])
        raw_counts[d] = cnt
        print(f'  {d:30s}: {cnt:4d}')
print(f'  TOTAL                         : {sum(raw_counts.values()):4d}')

# 3. Summaries by textbook
print('\n=== SUMMARIES BY TEXTBOOK ===')
summ_dir = os.path.join(wiki,'summaries')
textbook_chapters = defaultdict(set)
unclassified = []
for f in os.listdir(summ_dir):
    if f.endswith('.md') and f not in skip:
        name = f.replace('.md','')
        matched = False
        for prefix in ['马新国','朱立元','最新文论教程','理论史教程一','理论史教程二','名著教程','五种模式','二十世纪文论选','伍蠡甫','导引出版','司各特','文学理论入门','反世界文学','汉语经验','Grossberg','西方文论选']:
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

# 4. Broken links (FIXED: use forward slash)
print('\n=== BROKEN LINKS (fixed) ===')
existing = set()
aliases = set()
for root,_,fs in os.walk(wiki):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            rel = os.path.relpath(os.path.join(root,f),wiki).replace('.md','').replace(os.sep,'/').lower()
            existing.add(rel)
            # also add aliases
            with open(os.path.join(root,f),'r',encoding='utf-8') as fh:
                content = fh.read(2000)
            for m in re.finditer(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', content, re.MULTILINE):
                for line in m.group(1).split('\n'):
                    a = line.strip().lstrip('-').strip().strip('"').strip("'").lower()
                    if a:
                        aliases.add(a)
            for m in re.finditer(r'^aliases:\s*\[(.*?)\]', content, re.MULTILINE):
                for a in m.group(1).split(','):
                    a = a.strip().strip('"').strip("'").lower()
                    if a:
                        aliases.add(a)

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
            if t in existing: continue
            if t in aliases: continue
            # basename fallback
            bn = t.split('/')[-1]
            if any(ep.endswith('/'+bn) for ep in existing): continue
            broken[t] += 1
print(f'  broken: {sum(broken.values())} refs / {len(broken)} targets')
if broken:
    for k,v in sorted(broken.items(), key=lambda x:-x[1])[:20]:
        print(f'    {v:3d}x  {k}')

# 5. Cross-layer density
print('\n=== CROSS-LAYER LINKS ===')
layer_links = defaultdict(lambda: defaultdict(int))
for root,_,fs in os.walk(wiki):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        src_layer = os.path.relpath(os.path.join(root,f),wiki).replace(os.sep,'/').split('/')[0]
        with open(os.path.join(root,f),'r',encoding='utf-8') as fh: c = fh.read()
        for m in re.finditer(r'\[\[(figures|concepts|movements|works|summaries|comparisons|overviews|synthesis)/([^\]|]+?)', c):
            layer_links[src_layer][m.group(1)] += 1
for src in sorted(layer_links):
    targets = layer_links[src]
    parts = ', '.join(f'{t}:{n}' for t,n in sorted(targets.items(), key=lambda x:-x[1]))
    avg = sum(targets.values()) / layer_counts.get(src,1)
    print(f'  {src:14s} ({avg:.1f}/pg): {parts}')

# 6. Raw -> Summary utilization
print('\n=== RAW UTILIZATION ===')
for tb in ['马新国','朱立元','最新文论教程','理论史教程一','名著教程下','文学理论入门','伍蠡甫','二十世纪文论选上','二十世纪文论选上v2','二十世纪文论选下','五种模式','西方文论选--上_10891710_1733.layered','西方文论选下']:
    raw_dir = os.path.join(raw, tb)
    if not os.path.isdir(raw_dir): continue
    slices = len([f for f in os.listdir(raw_dir) if f.endswith('.md')])
    # count summaries referencing this textbook
    summ_count = 0
    for root,_,fs in os.walk(wiki):
        for f in fs:
            if f.endswith('.md') and f not in skip:
                with open(os.path.join(root,f),'r',encoding='utf-8') as fh:
                    c = fh.read()
                if f'raw/{tb}/' in c or f'@{tb}' in c or tb in f:
                    summ_count += 1
                    break
    print(f'  {tb:50s}: {slices:4d} raw -> {summ_count:3d} refs')
