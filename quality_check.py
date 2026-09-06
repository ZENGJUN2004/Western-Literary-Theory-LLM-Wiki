import os, re
base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}

alias_owner = {}
dup_aliases = []
for layer in ['figures','concepts','movements','works']:
    d = os.path.join(base, layer)
    names = [f.replace('.md','') for f in os.listdir(d) if f.endswith('.md')]
    for f in names:
        with open(os.path.join(d,f+'.md'),'r',encoding='utf-8') as fh:
            head = fh.read(1500)
        al = []
        m = re.search(r'aliases:\s*\[(.*?)\]', head)
        if m:
            al = [a.strip().strip('"').strip("'") for a in m.group(1).split(',')]
        m2 = re.search(r'aliases:\s*\n((?:\s*-\s*.*\n)*)', head)
        if m2:
            al += [l.strip().lstrip('-').strip() for l in m2.group(1).split('\n') if l.strip()]
        for a in al:
            a2 = a.lower()
            if a2 in alias_owner and alias_owner[a2] != layer+'/'+f:
                dup_aliases.append((a, alias_owner[a2], layer+'/'+f))
            else:
                alias_owner[a2] = layer+'/'+f

print(f'跨页重复 alias: {len(dup_aliases)}')
for a,x,y in dup_aliases[:15]:
    print(f'  [{a}] {x} <-> {y}')

idx = os.path.join(base,'_index.md')
with open(idx,'r',encoding='utf-8') as fh:
    c = fh.read()
n_comp = c.count('comparisons/')
n_over = c.count('overviews/')
n_syn = c.count('synthesis/')
print()
print(f'_index.md: {len(c)} chars | comparisons links: {n_comp} | overviews links: {n_over} | synthesis links: {n_syn}')
