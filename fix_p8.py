"""P8: 批量修复断链 — alias 重定向 + 泛概念改纯文本"""
import os, re

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
skip = {'_log.md','_index.md','task_plan.md','_indexes.md'}

# 11 个 alias 重定向
ALIAS_REDIRECT = {
    'movements/现代主义': 'movements/后现代主义',  # 临时：先重定向到后现代主义，subagent 会创建独立页面
    'figures/巴尔': 'figures/巴尔特',
    'figures/福科': 'figures/福柯',
    'figures/霍尔': 'figures/斯图亚特·霍尔',
    'figures/塞尔': 'figures/塞尔登',
    'figures/米勒': 'figures/希利斯·米勒',
    'movements/精神分析': 'movements/精神分析批评',
    'movements/现实主义文论': 'movements/现实主义',
    'figures/布洛': 'figures/布洛赫',
    'figures/布勒': 'figures/布勒东',
    'figures/哈特': 'figures/哈特曼',
    'figures/伍德': 'figures/科林伍德',
    'figures/詹姆斯': 'figures/亨利·詹姆斯',
    'movements/人类学': 'movements/文学人类学',
}

# 29 个泛概念：[[concepts/xxx]] → xxx（纯文本）
PLAIN_TEXT = [
    '人文主义','理想','语境','人物','焦虑','存在','文化','中国','教材',
    '审美','冲动','美','幻觉','影响','时间','抒情','对话','研究','语言',
    '史诗','想象','表征','音乐','体裁','世界','技术','自由','介入','结构',
]

fix_count = 0

for root,_,fs in os.walk(base):
    for fname in fs:
        if not fname.endswith('.md') or fname in skip:
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        original = content

        # 1. Alias 重定向
        for wrong, right in ALIAS_REDIRECT.items():
            # [[wrong]] → [[right]]
            content = content.replace(f'[[{wrong}]]', f'[[{right}]]')
            # [[wrong|display]] → [[right|display]]
            content = content.replace(f'[[{wrong}|', f'[[{right}|')

        # 2. 泛概念改纯文本
        for concept in PLAIN_TEXT:
            # [[concepts/concept]] → concept
            content = content.replace(f'[[concepts/{concept}]]', concept)
            # [[concepts/concept|display]] → display
            content = re.sub(
                rf'\[\[concepts/{re.escape(concept)}\|([^\]]+?)\]\]',
                r'\1',
                content
            )

        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            fix_count += 1

print(f'Fixed {fix_count} files')

# 验证
existing = set()
for root,_,fs in os.walk(base):
    for f in fs:
        if f.endswith('.md') and f not in skip:
            rel = os.path.relpath(os.path.join(root,f), base).replace('.md','').replace(os.sep,'/').lower()
            existing.add(rel)

broken = 0
for root,_,fs in os.walk(base):
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
                    broken += 1
print(f'Remaining broken: {broken} refs')
