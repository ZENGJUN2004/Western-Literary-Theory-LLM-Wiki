"""P13.3: 反斜杠链接归一化 + 二次去重重写（含观审→净化） + 验证"""
import os, re, json
from collections import defaultdict

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}
LAYERS = 'figures|concepts|movements|works|summaries|comparisons|overviews|synthesis|raw'

# ---- 重建 dup->canon 映射（决策文件 + 观审补充）----
dup2canon = {}
for i in range(1,5):
    with open(rf'd:\BaiduNetdiskDownload\西方文论教材\dedup_decisions_{i}.json','r',encoding='utf-8') as fh:
        for e in json.load(fh):
            if e.get('action')=='merge':
                dup2canon[e['dup']] = e['canon']
dup2canon['concepts/观审'] = 'concepts/净化-catharsis'
def resolve(x):
    seen = set()
    while x in dup2canon and x not in seen:
        seen.add(x); x = dup2canon[x]
    return x
final = {d: resolve(d) for d in list(dup2canon)}
final = {d:c for d,c in final.items() if d != c}

folder_map = {}
name_map = {}
all_pages = set()
for root,_,fs in os.walk(base):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            all_pages.add(os.path.relpath(os.path.join(root,f),base).replace('.md','').replace(os.sep,'/').lower())
bn_count = defaultdict(int)
for pg in all_pages: bn_count[pg.split('/')[-1]] += 1
for d,c in final.items():
    df, dn = d.split('/',1)
    folder_map[(df.lower(), dn.lower())] = c
    if bn_count[dn] == 1:
        name_map[dn.lower()] = c

link_re = re.compile(r'\[\[([^\]|]+?)(\|[^\]]*)?\]\]')
def rewrite(m):
    inner, disp = m.group(1).strip(), m.group(2) or ''
    # 反斜杠归一化（仅层前缀形态）
    t = inner
    tl = t.lower().replace('\\','/')
    if '/' in tl:
        f2, n2 = tl.split('/',1)
        n2 = n2[:-3] if n2.endswith('.md') else n2
        if (f2,n2) in folder_map:
            return '[[%s%s]]' % (folder_map[(f2,n2)], disp)
        return '[[%s/%s%s]]' % (f2, n2, disp) if '\\' in t else m.group(0)
    if tl in name_map:
        return '[[%s%s]]' % (name_map[tl], disp)
    return m.group(0)

norm_count = 0; duprw_count = 0; files = 0
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        p = os.path.join(root,f)
        with open(p,'r',encoding='utf-8') as fh: c = fh.read()
        orig = c
        # 1) 反斜杠归一化（统计真实反斜杠链）
        bs_hits = re.findall(r'\[\[(?:%s)\\\\[^\]]*\]\]' % LAYERS, c) or re.findall(r'\[\[(?:%s)\\[^\]]*\]\]' % LAYERS, c)
        c = re.sub(r'\[\[(%s)\\' % LAYERS, r'[[\1/', c)
        norm_count += len(bs_hits)
        # 2) dup 重写
        def rw2(m):
            inner, disp = m.group(1).strip(), m.group(2) or ''
            tl = inner.lower()
            if '/' in tl:
                f2, n2 = tl.split('/',1)
                if n2.endswith('.md'): n2 = n2[:-3]
                if (f2,n2) in folder_map:
                    return '[[%s%s]]' % (folder_map[(f2,n2)], disp)
            elif tl in name_map:
                return '[[%s%s]]' % (name_map[tl], disp)
            return m.group(0)
        before = c
        c = link_re.sub(rw2, c)
        if c != before:
            duprw_count += sum(1 for _ in re.finditer(r'\[\[(?:%s)\\' % LAYERS, before))
        if c != orig:
            with open(p,'w',encoding='utf-8') as fh: fh.write(c)
            files += 1

print(f'反斜杠链接归一化: {norm_count} 个')
print(f'文件修改: {files}')
print(f'剩余待查 dup 形式引用: {duprw_count}')

# ---- 验证：正斜杠断链 + 残留反斜杠 ----
existing = set()
for root,_,fs in os.walk(base):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            existing.add(os.path.relpath(os.path.join(root,f),base).replace('.md','').replace(os.sep,'/').lower())
broken = defaultdict(int); res_bs = 0
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        with open(os.path.join(root,f),'r',encoding='utf-8') as fh: c = fh.read()
        res_bs += len(re.findall(r'\[\[(?:%s)\\' % LAYERS, c))
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]', c):
            link = m.group(1).strip()
            if link.startswith('@') or link.startswith('raw/'): continue
            if '/' not in link: continue
            t = link.lower()
            if t in existing: continue
            bn = t.split('/')[-1]
            if not any(ep.endswith('/'+bn) for ep in existing):
                broken[t] += 1
print(f'残留反斜杠链接: {res_bs}')
print(f'断链: {sum(broken.values())} refs / {len(broken)} targets')
for k,v in sorted(broken.items(), key=lambda x:-x[1])[:15]:
    print(f'  {v:3d}x  {k}')
