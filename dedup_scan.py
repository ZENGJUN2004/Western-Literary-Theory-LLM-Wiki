"""P13.1 重复页扫描：生成合并决策清单（pairs + 规模指标 + 入链数）"""
import os, re, json
from collections import defaultdict

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}
layers = ['figures','concepts','movements','works']

def get_aliases(path):
    with open(path,'r',encoding='utf-8') as fh:
        head = fh.read(2000)
    al = []
    m = re.search(r'^aliases:\s*\[(.*?)\]', head, re.MULTILINE)
    if m:
        al += [a.strip().strip('"').strip("'") for a in m.group(1).split(',') if a.strip()]
    m2 = re.search(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', head, re.MULTILINE)
    if m2:
        al += [l.strip().lstrip('-').strip().strip('"').strip("'") for l in m2.group(1).split('\n') if l.strip()]
    return [a for a in al if a]

# alias -> owners
alias_owners = defaultdict(set)
page_meta = {}
for layer in layers:
    d = os.path.join(base, layer)
    for f in os.listdir(d):
        if not f.endswith('.md'): continue
        name = f.replace('.md','')
        p = os.path.join(d,f)
        with open(p,'r',encoding='utf-8') as fh:
            content = fh.read()
        page_meta[f'{layer}/{name}'] = {
            'size': len(content),
            'aliases': get_aliases(p),
        }
        for a in page_meta[f'{layer}/{name}']['aliases']:
            alias_owners[a.lower()].add(f'{layer}/{name}')

# 冲突对（同层）
pairs = set()
for a, owners in alias_owners.items():
    owners = list(owners)
    for i in range(len(owners)):
        for j in range(i+1, len(owners)):
            x, y = owners[i], owners[j]
            if x.split('/')[0] == y.split('/')[0]:
                pairs.add(tuple(sorted([x,y])))

# 入链计数
inbound = defaultdict(int)
link_re = re.compile(r'\[\[(figures|concepts|movements|works)/([^\]|]+?)(?:\|[^\]]*)?\]\]')
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        src = os.path.relpath(os.path.join(root,f),base).replace(os.sep,'/')
        with open(os.path.join(root,f),'r',encoding='utf-8') as fh:
            c = fh.read()
        for m in link_re.finditer(c):
            tgt = f'{m.group(1)}/{m.group(2).strip()}'
            if tgt != src:
                inbound[tgt] += 1

# 输出决策清单
report = []
for x,y in sorted(pairs):
    mx, my = page_meta[x], page_meta[y]
    ix, iy = inbound.get(x,0), inbound.get(y,0)
    # 规范页选择：入链多者优先，其次字数多者
    if (ix, mx['size']) >= (iy, my['size']):
        canon, dup = x, y
    else:
        canon, dup = y, x
    report.append({
        'canon': canon, 'dup': dup,
        'shared_alias': [a for a,owners in alias_owners.items() if {canon,dup} <= owners],
        'canon_size': page_meta[canon]['size'], 'dup_size': page_meta[dup]['size'],
        'canon_in': inbound.get(canon,0), 'dup_in': inbound.get(dup,0),
    })

print(f'重复页对: {len(report)}')
print(f"{'canonical':38s} {'duplicate':38s} {'szC':>5s} {'szD':>5s} {'inC':>4s} {'inD':>4s}  共享alias")
for r in report:
    print(f"{r['canon']:38s} {r['dup']:38s} {r['canon_size']:5d} {r['dup_size']:5d} {r['canon_in']:4d} {r['dup_in']:4d}  {','.join(r['shared_alias'][:2])}")

with open(r'd:\BaiduNetdiskDownload\西方文论教材\dedup_pairs.json','w',encoding='utf-8') as fh:
    json.dump(report, fh, ensure_ascii=False, indent=1)
print('\nSaved: dedup_pairs.json')
