# -*- coding: utf-8 -*-
"""批量修复 MINOR 残留：来源为非正文切片的 figures 页。
策略：删除 sources 中的 _meta 和 00-前言与目录 行，保留有效正文来源。
若全部来源被清除，则删除整个 sources 字段。
"""
import os, re, sys

FIG_DIR = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki\figures'

# 需要清除的无效来源关键词
BAD_SOURCE_KEYWORDS = ['_meta', '00-前言与目录']

def is_bad_source(s):
    s_clean = s.strip().strip('"').strip("'").strip()
    s_clean = re.sub(r'^\[\[', '', s_clean).strip()
    s_clean = re.sub(r'\]\]$', '', s_clean).strip()
    for kw in BAD_SOURCE_KEYWORDS:
        if kw in s_clean:
            return True
    return False

def clean_source_raw(s):
    """剥掉引号和 [[...]]，返回原始 raw 路径"""
    s = s.strip().strip('"').strip("'").strip()
    s = re.sub(r'^\[\[', '', s)
    s = re.sub(r'\]\]$', '', s)
    return s.strip()

def process_file(fpath):
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'sources:' not in content.split('---', 2)[1] if '---' in content else '':
        return False

    # 找到 frontmatter 范围
    parts = content.split('---')
    if len(parts) < 3:
        return False

    fm = parts[1]
    body = '---'.join(parts[2:])

    # --- YAML list 格式 ---
    # sources:
    #   - "[[raw/...]]"
    yaml_match = re.search(r'^sources:\s*\n((?:\s*-\s*.+\n?)*)', fm, re.MULTILINE)
    if yaml_match:
        lines = yaml_match.group(0).split('\n')
        kept_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('-'):
                src = clean_source_raw(stripped[1:])
                if not is_bad_source(src):
                    kept_lines.append(line)
            else:
                kept_lines.append(line)
        if not kept_lines or all(l.strip().startswith('-') and is_bad_source(clean_source_raw(l.strip()[1:])) for l in kept_lines if l.strip()):
            # 全部无效，删除整个 sources 字段
            new_fm = re.sub(r'^sources:\s*\n(?:\s*-\s*.+\n?)*', '', fm, flags=re.MULTILINE)
        else:
            new_fm = fm[:yaml_match.start()] + '\n'.join(kept_lines) + fm[yaml_match.end():]
        new_content = '---\n' + new_fm + '---\n' + body
        if new_content != content:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        return False

    # --- inline JSON 格式 ---
    # sources: ["[[raw/...]]", "[[raw/...]]"]
    json_match = re.search(r'^sources:\s*\[(.*?)\]', fm, re.MULTILINE | re.DOTALL)
    if json_match:
        items_str = json_match.group(1)
        items = re.findall(r'"([^"]*)"', items_str)
        kept = [item for item in items if not is_bad_source(item)]
        if not kept:
            new_fm = re.sub(r'^sources:\s*\[.*?\]', '', fm, flags=re.MULTILINE | re.DOTALL)
        else:
            new_items = ', '.join(f'"{item}"' for item in kept)
            new_fm = fm[:json_match.start()] + f'sources: [{new_items}]' + fm[json_match.end():]
        new_content = '---\n' + new_fm + '---\n' + body
        if new_content != content:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        return False

    return False

if __name__ == '__main__':
    changed = 0
    for fname in sorted(os.listdir(FIG_DIR)):
        if not fname.endswith('.md') or fname.startswith('_'):
            continue
        fpath = os.path.join(FIG_DIR, fname)
        if process_file(fpath):
            print(f'  ✓ {fname}')
            changed += 1
    print(f'\n共修改 {changed} 个文件')
