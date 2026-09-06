"""P8: 精确分类 66 个断链 target"""
import os, re
from collections import Counter
import difflib

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}

# 收集现有页面 + aliases
existing = set()
all_files = {}  # path -> basename
aliases_map = {}

for root,_,fs in os.walk(base):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            rel = os.path.relpath(os.path.join(root,f), base).replace('.md','').replace(os.sep,'/').lower()
            existing.add(rel)
            bn = rel.split('/')[-1]
            all_files[rel] = bn
            with open(os.path.join(root,f),'r',encoding='utf-8') as fh:
                content = fh.read(2000)
            for m in re.finditer(r'^aliases:\s*\n((?:\s*-\s*.*\n)*)', content, re.MULTILINE):
                for line in m.group(1).split('\n'):
                    a = line.strip().lstrip('-').strip().strip('"').strip("'").lower()
                    if a:
                        aliases_map.setdefault(a, []).append(rel)
            for m in re.finditer(r'^aliases:\s*\[(.*?)\]', content, re.MULTILINE):
                for a in m.group(1).split(','):
                    a = a.strip().strip('"').strip("'").lower()
                    if a:
                        aliases_map.setdefault(a, []).append(rel)

# 收集断链
broken = Counter()
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        with open(os.path.join(root,f),'r',encoding='utf-8') as fh: c = fh.read()
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', c):
            link = m.group(1).strip()
            if link.startswith('@') or link.startswith('raw/'): continue
            if '/' not in link: continue
            t = link.lower()
            if t in existing: continue
            if t in aliases_map: continue
            bn = t.split('/')[-1]
            if any(ep.endswith('/'+bn) for ep in existing): continue
            broken[t] += 1

# 分类
create_page = []  # 需新建页面
alias_fix = []    # 需修复链接→现有页
plain_text = []   # 泛概念，改为纯文本

for target, n in sorted(broken.items(), key=lambda x: -x[1]):
    folder, name = target.split('/', 1)
    
    # 检查是否有相似文件
    similar = []
    for ep, bn in all_files.items():
        if ep.startswith(folder + '/'):
            ratio = difflib.SequenceMatcher(None, name, bn).ratio()
            if ratio > 0.6:
                similar.append((ep, ratio))
    similar.sort(key=lambda x: -x[1])
    
    # 判断类型
    if similar and similar[0][1] > 0.8:
        alias_fix.append((target, similar[0][0], n))
    elif folder in ('movements',):
        create_page.append((target, n))
    elif folder in ('figures',):
        # 检查是否在其他 folder 有同名
        cross = [ep for ep, bn in all_files.items() if bn == name]
        if cross:
            alias_fix.append((target, cross[0], n))
        else:
            create_page.append((target, n))
    elif folder in ('concepts',):
        # 泛概念判断
        generic = ['存在','语境','文化','人物','焦虑','理想','人文主义','现代主义','教材','中国']
        if name in generic or len(name) <= 2:
            plain_text.append((target, n))
        else:
            create_page.append((target, n))
    elif folder in ('works',):
        create_page.append((target, n))
    elif folder in ('summaries',):
        create_page.append((target, n))
    else:
        plain_text.append((target, n))

print(f'=== 断链分类（共 {len(broken)} targets, {sum(broken.values())} refs）===')
print()
print(f'--- 需新建页面: {len(create_page)} targets ---')
for t, n in create_page:
    print(f'  {n:3d}x  [[{t}]]')
print()
print(f'--- 需修复链接→现有页: {len(alias_fix)} targets ---')
for t, match, n in alias_fix:
    print(f'  {n:3d}x  [[{t}]] -> [[{match}]]')
print()
print(f'--- 改纯文本: {len(plain_text)} targets ---')
for t, n in plain_text:
    print(f'  {n:3d}x  [[{t}]]')
