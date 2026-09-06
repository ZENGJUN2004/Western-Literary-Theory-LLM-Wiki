import os, re
from collections import Counter
base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}
existing = set()
for root,_,fs in os.walk(base):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            existing.add(os.path.relpath(os.path.join(root,f),base).replace('.md','').replace(os.sep,'/').lower())

pat = re.compile(r'\[\[([a-zA-Z]+)\\([^\]|]+?)(?:\|[^\]]*)?\]\]')
bs = Counter(); broken_bs = []; total = 0
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        p = os.path.join(root,f)
        with open(p,'r',encoding='utf-8') as fh: c = fh.read()
        for m in pat.finditer(c):
            total += 1
            layer, name = m.group(1).lower(), m.group(2).strip()
            t = layer + '/' + name.lower()
            bn = name.lower().replace('.md','')
            if t in existing or any(ep.endswith('/'+bn) for ep in existing):
                bs[t] += 1
            else:
                broken_bs.append((os.path.relpath(p,base), m.group(0)))
print(f'反斜杠链接总数: {total}, 指向存在页(需改为/): {sum(bs.values())}, 彻底断链: {len(broken_bs)}')
print('目标分布:', dict(bs.most_common(15)))
for src, l in broken_bs[:15]: print(f'  BROKEN {src}: {l}')
