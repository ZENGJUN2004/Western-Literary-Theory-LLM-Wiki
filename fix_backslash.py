"""修复反斜杠路径链接"""
import os, re

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'
count = 0

for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md','task_plan.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        # 修复 [[folder\name]] → [[folder/name]]
        def fix_bs(m):
            folder = m.group(1)
            name = m.group(2)
            rest = m.group(3) or ''
            return f'[[{folder}/{name}{rest}]]'
        content = re.sub(r'\[\[([^\]\|]*?)\\([^\]\|]*?)(\|[^\]]+?)?\]\]', fix_bs, content)
        
        if content != original:
            fixes = len(re.findall(r'\\', original)) - len(re.findall(r'\\', content))
            count += fixes
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'Fixed {fixes} backslashes in {os.path.relpath(fpath, base)}')

print(f'\nTotal backslash fixes: {count}')
