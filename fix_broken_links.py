# -*- coding: utf-8 -*-
"""修复引用了已删除 figures 页面的断链。
"""
import os, re

FIG_DIR = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki\figures'
BASE = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'

DELETED = [
    '中里耶夫斯基', '乔治·斯坦纳', '克劳斯', '克拉克', '加芬克尔',
    '勒维特', '史特劳斯', '尼尔·postman', '尼达', '巴雷',
    '德拉·克罗蒂埃', '涂尔干', '科苏斯', '米克罗斯', '米沃什',
    '纳吉', '翁贝托·波乔尼', '艾皮亚', '苏台德', '茨维塔耶娃',
    '莱布尼茨', '菲茨杰拉德', '西蒙娜·韦伊', '诺拉', '贝尔格',
    '赫胥黎', '都德', '韦伯恩', '韦努蒂', '马尔克', '鲍尔斯',
    '多斯·埃idos', '奇努克',
]

fixed_files = set()
total_replacements = 0

for root, dirs, files in os.walk(BASE):
    for fname in files:
        if not fname.endswith('.md') or fname.startswith('_'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        new_content = content
        for name in DELETED:
            # 匹配 [[figures/名字]] 和 [[figures/名字.md]]
            pattern = re.compile(r'\[\[figures/' + re.escape(name) + r'\]\]')
            new_content = pattern.sub(name, new_content)
        if new_content != content:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            count = len(pattern.findall(content) if False else [])
            fixed_files.add(os.path.relpath(fpath, BASE))

print(f'修复完成，共修改 {len(fixed_files)} 个文件')
for f in sorted(fixed_files):
    print(f'  - {f}')
