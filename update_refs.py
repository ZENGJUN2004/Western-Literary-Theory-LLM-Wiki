"""更新 wiki 中 raw/马新国/ 旧路径引用 → 重命名后的新路径"""
import os, re, sys
sys.path.insert(0, r'd:\BaiduNetdiskDownload\西方文论教材')
import rename_maxin as R  # 导入复用转换函数；无 APPLY 环境变量，不会重命名

raw_dir = R.base
raw_files = {f[:-3] for f in os.listdir(raw_dir) if f.endswith('.md')}

def newname(old):
    s = old[:-3] if old.endswith('.md') else old
    m = re.match(r'^(\d{2})-(.+)$', s)
    page_m = re.search(r'-(\d{2,3})$', s)
    page = int(page_m.group(1)) if page_m else None
    cur = int(m.group(1)) if m else None
    body_rest = m.group(2) if m else s
    bf = R.fix_body(body_rest)
    kw = R.kw_chapter(bf)
    ns = None
    if m and cur and 1 <= cur <= 25 and kw == cur:
        ns = f'{cur:02d}-{bf}'
    elif page is not None:
        chn, chname = R.chapter_by_page(page)
        if chn:
            short = chname.split('（')[0]
            body = re.sub(r'^\d+-', '', s)
            body = R.fix_body(body)
            if short.replace('-', '') not in body.replace('-', ''):
                body = f'{chname}-{body}'
            ns = f'{chn:02d}-{body}'
    elif kw is not None:
        ns = f'{kw:02d}-{re.sub(r"^\d+-", "", bf)}'
    elif bf != body_rest:
        ns = (f'{cur:02d}-{bf}' if m else bf)
    return ns

wiki = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
repl_map = {}
missed = set()
for root, _, fs in os.walk(wiki):
    for f in fs:
        if not f.endswith('.md'):
            continue
        p = os.path.join(root, f)
        with open(p, 'r', encoding='utf-8') as fh:
            c = fh.read()
        orig = c
        for m in re.finditer(r'raw/马新国/([^\]\)|\s]+)', c):
            old = m.group(1)
            if old in repl_map:
                new = repl_map[old]
            else:
                ns = newname(old)
                if ns is None:
                    ns = old[:-3] if old.endswith('.md') else old
                if ns in raw_files:
                    new = ns
                    repl_map[old] = new
                else:
                    missed.add(old)
                    continue
            if new != old:
                c = c.replace(f'raw/马新国/{old}', f'raw/马新国/{new}')
        if c != orig:
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(c)

print(f'映射并替换: {len(repl_map)} 个路径')
for k in sorted(repl_map)[:15]:
    print(f'  {k} -> {repl_map[k]}')
print(f'\n未匹配（保留原样）: {len(missed)} 个')
for k in sorted(missed):
    print(f'  {k}')
