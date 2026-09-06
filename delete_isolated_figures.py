# -*- coding: utf-8 -*-
"""批量删除 figures 层中无任何正文来源支持的孤立幻觉页面。
这些页面在 audit report 中标记为 MAJOR（孤立页面），
且经验证在 summaries 中也没有任何提及。
"""
import os

FIG_DIR = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki\figures'

# 孤立幻觉页面（已验证无 raw 来源、无 summary 引用）
TO_DELETE = [
    '中里耶夫斯基.md',
    '乔治·斯坦纳.md',
    '克劳斯.md',
    '克拉克.md',
    '加芬克尔.md',
    '勒维特.md',
    '史特劳斯.md',
    '尼尔·postman.md',
    '尼达.md',
    '巴雷.md',
    '德拉·克罗蒂埃.md',
    '涂尔干.md',
    '科苏斯.md',
    '米克罗斯.md',
    '米沃什.md',
    '纳吉.md',
    '翁贝托·波乔尼.md',
    '艾皮亚.md',
    '苏台德.md',
    '茨维塔耶娃.md',
    '莱布尼茨.md',
    '菲茨杰拉德.md',
    '西蒙娜·韦伊.md',
    '诺拉.md',
    '贝尔格.md',
    '赫胥黎.md',
    '都德.md',
    '韦伯恩.md',
    '韦努蒂.md',
    '马尔克.md',
    '鲍尔斯.md',
]

deleted = []
for fname in TO_DELETE:
    fpath = os.path.join(FIG_DIR, fname)
    if os.path.isfile(fpath):
        os.remove(fpath)
        deleted.append(fname)
        print(f'  ✓ 删除: {fname}')
    else:
        print(f'  - 不存在: {fname}')

print(f'\n共删除 {len(deleted)} 个孤立幻觉页面')
