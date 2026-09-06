"""P13.2 执行器：链接重写 + 别名迁移/修正 + 待删清单（不执行删除）"""
import os, re, json, glob
from collections import defaultdict

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}

# ---------- 载入决策 ----------
entries = []
for i in range(1, 5):
    p = rf'd:\BaiduNetdiskDownload\西方文论教材\dedup_decisions_{i}.json'
    with open(p,'r',encoding='utf-8') as fh:
        arr = json.load(fh)
    for e in arr:
        e['_batch'] = i
        entries.append(e)
print(f'载入决策: {len(entries)} 条')

merges = [e for e in entries if e.get('action')=='merge']
fixes  = [e for e in entries if e.get('action')=='aliasfix']
print(f'merge: {len(merges)}, aliasfix: {len(fixes)}')

# ---------- 簇链解析 dup -> final canon ----------
dup2canon = {}
for e in merges:
    dup2canon[e['dup']] = e['canon']
def resolve(x):
    seen = set()
    while x in dup2canon and x not in seen:
        seen.add(x); x = dup2canon[x]
    return x
final_dup2canon = {d: resolve(d) for d in dup2canon}
# 自指清理（不应有）
final_dup2canon = {d:c for d,c in final_dup2canon.items() if d != c}
print(f'待吸收页(去链解析后): {len(final_dup2canon)}')

# 别名迁移表 canon -> set
alias_add = defaultdict(set)
for e in merges:
    canon = final_dup2canon.get(e['dup'], e['canon'])
    for a in e.get('aliases_to_add', []) or []:
        if a: alias_add[canon].add(a.strip())
    alias_add[canon].add(e['dup'].split('/')[-1])

# aliasfix 增删
alias_rm = defaultdict(set)
alias_fix_add = defaultdict(set)
for e in fixes:
    for ed in e.get('edits', []) or []:
        pg = ed.get('page')
        if not pg: continue
        for a in ed.get('remove_aliases', []) or []:
            alias_rm[pg].add(a.strip())
        for a in ed.get('add_aliases', []) or []:
            alias_fix_add[pg].add(a.strip())

# ---------- 链接重写 ----------
# 构建 folder 限定的重写映射 + 唯一裸名映射
folder_map = {}   # (folder, name) -> canon path
name_map = {}     # bare name -> canon path (仅当该 name 全库唯一属于 dup)
for d, c in final_dup2canon.items():
    df, dn = d.split('/',1)
    folder_map[(df.lower(), dn.lower())] = c
    folder_map[(df.lower(), dn.lower()+'.md')] = c  # 容错 .md 后缀

all_pages = set()
for root,_,fs in os.walk(base):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            all_pages.add(os.path.relpath(os.path.join(root,f),base).replace('.md','').replace(os.sep,'/').lower())
basename_count = defaultdict(int)
for pg in all_pages:
    basename_count[pg.split('/')[-1]] += 1
for d, c in final_dup2canon.items():
    dn = d.split('/')[-1]
    if basename_count[dn] == 1:
        name_map[dn.lower()] = c

link_re = re.compile(r'\[\[([^\]|]+?)(\|[^\]]*)?\]\]')
def rewrite_link(m):
    inner, disp = m.group(1), m.group(2) or ''
    t = inner.strip()
    tl = t.lower()
    # folder 限定
    if '/' in tl:
        f2, n2 = tl.split('/',1)
        if (f2,n2) in folder_map:
            return '[[%s%s]]' % (folder_map[(f2,n2)], disp)
        if (f2,n2[:-3]) in folder_map and n2.lower().endswith('.md'):
            return '[[%s%s]]' % (folder_map[(f2,n2[:-3])], disp)
        return m.group(0)
    # 裸名
    if tl in name_map:
        return '[[%s%s]]' % (name_map[tl], disp)
    if tl[:-3] in name_map and tl.endswith('.md'):
        return '[[%s%s]]' % (name_map[tl[:-3]], disp)
    return m.group(0)

files_changed = 0
total_rew = 0
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        p = os.path.join(root,f)
        with open(p,'r',encoding='utf-8') as fh:
            c = fh.read()
        c2, n = link_re.subn(rewrite_link, c)
        # 统计实际变化
        if c2 != c:
            with open(p,'w',encoding='utf-8') as fh:
                fh.write(c2)
            files_changed += 1
            total_rew += sum(1 for _ in re.finditer(r'\[\[(?:%s)\b' % '|'.join(
                [re.escape(d.split('/')[-1]) for d in final_dup2canon]), c2)) # 估值，不计精确
print(f'链接重写: {files_changed} 个文件被修改')

# ---------- 别名操作 ----------
def parse_aliases(head):
    """返回 (list_of_aliases, span,(start,end) in head or None)"""
    m = re.search(r'^aliases:\s*\[(.*?)\]\s*$', head, re.MULTILINE)
    if m:
        vals = [a.strip().strip('"').strip("'") for a in m.group(1).split(',') if a.strip()]
        return vals, m.span(0)
    m = re.search(r'^aliases:\s*\n((?:[ \t]+-[ \t]*.*\n?)+)', head, re.MULTILINE)
    if m:
        vals = []
        for line in m.group(1).split('\n'):
            line = line.strip()
            if line.startswith('-'):
                v = line[1:].strip().strip('"').strip("'")
                if v: vals.append(v)
        return vals, m.span(0)
    return None, None

def fmt_alias_line(vals):
    if not vals: return 'aliases: []'
    parts = []
    for v in vals:
        if re.match(r'^[A-Za-z0-9\u4e00-\u9fff·\-\s]+$', v) and ',' not in v and '"' not in v:
            parts.append(v)
        else:
            parts.append('"%s"' % v.replace('"','\\"'))
    return 'aliases: [' + ', '.join(parts) + ']'

alias_changed = 0
def apply_alias(page, remove=set(), add=set()):
    global alias_changed
    p = os.path.join(base, page + '.md')
    if not os.path.exists(p):
        print(f'  !! 别名操作跳过，页面不存在: {page}')
        return
    with open(p,'r',encoding='utf-8') as fh:
        c = fh.read()
    # 只在 frontmatter 内操作
    if c.startswith('---'):
        end = c.find('\n---', 3)
        if end != -1:
            head = c[:end]
            tail = c[end:]
            vals, span = parse_aliases(head)
            if vals is None:
                # 插入 aliases 行到 frontmatter 首行后
                lines = head.split('\n')
                lines.insert(1, fmt_alias_line(sorted(add)))
                new_head = '\n'.join(lines)
            else:
                s = set(vals) - remove
                s |= add
                new_line = fmt_alias_line(sorted(s))
                new_head = head[:span[0]] + new_line + head[span[1]:]
            c2 = new_head + tail
            if c2 != c:
                with open(p,'w',encoding='utf-8') as fh:
                    fh.write(c2)
                alias_changed += 1
            return
    # 无 frontmatter： prepend
    if add:
        c2 = '---\n' + fmt_alias_line(sorted(add)) + '\n---\n\n' + c
        with open(p,'w',encoding='utf-8') as fh:
            fh.write(c2)
        alias_changed += 1

for canon, adds in alias_add.items():
    apply_alias(canon, add=adds)
for pg, rms in alias_rm.items():
    apply_alias(pg, remove=rms)
for pg, adds in alias_fix_add.items():
    apply_alias(pg, add=adds)
print(f'别名更新: {alias_changed} 个文件')

# ---------- 待删清单 ----------
to_delete = sorted(d for d in final_dup2canon)
with open(r'd:\BaiduNetdiskDownload\西方文论教材\dedup_to_delete.txt','w',encoding='utf-8') as fh:
    fh.write('\n'.join(to_delete))
print(f'待删文件: {len(to_delete)}（未删除，见 dedup_to_delete.txt）')

# ---------- 验证 ----------
existing = set()
for root,_,fs in os.walk(base):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            existing.add(os.path.relpath(os.path.join(root,f),base).replace('.md','').replace(os.sep,'/').lower())
broken = defaultdict(int)
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        with open(os.path.join(root,f),'r',encoding='utf-8') as fh:
            c = fh.read()
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]', c):
            link = m.group(1).strip()
            if link.startswith('@') or link.startswith('raw/'): continue
            if '/' not in link: continue
            t = link.lower()
            if t not in existing:
                bn = t.split('/')[-1]
                if not any(ep.endswith('/'+bn) for ep in existing):
                    broken[t] += 1
print(f'断链（dup 文件删除前）: {sum(broken.values())} refs / {len(broken)} targets')
for k,v in sorted(broken.items(), key=lambda x:-x[1])[:10]:
    print(f'  {v}x  {k}')
