import os, re
base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}
targets = ['斯蒂格勒','塞尔','穆卡洛夫斯基','布勒','第三持存','灵韵','伯纳德·肖','学术规范','贝蒂·弗里丹','毕加索','柯南·道尔','笛卡儿']
for root,_,fs in os.walk(base):
    for f in fs:
        if not f.endswith('.md') or f in skip: continue
        p = os.path.join(root,f)
        with open(p,'r',encoding='utf-8') as fh: c = fh.read()
        for m in re.finditer(r'\[\[([^\]|]*?(?:%s)[^\]|]*?)(?:\|([^\]]+))?\]\]' % '|'.join(targets), c):
            link = m.group(1)
            if any(t in link for t in targets) and '/' in link:
                ctx_start = max(0, m.start()-40)
                ctx = c[ctx_start:m.end()+20].replace('\n',' ')
                print(f'{os.path.relpath(p,base)}: [[{link}]]  ...{ctx[-90:]}')
