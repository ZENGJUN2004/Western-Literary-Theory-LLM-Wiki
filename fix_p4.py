"""P4 final: 剩余断链修复"""
import os, re

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'

# 1. 别名修正表（链接名 → canonical path）
ALIAS_FIXES = {
    'figures/阿多尔诺': 'figures/阿多诺',
    'figures/马歇雷': 'figures/马舍雷',
    'figures/马契雷': 'figures/马舍雷',
    'figures/詹姆逊': 'figures/杰姆逊',
    'figures/海顿·怀特': 'figures/海登·怀特',
    'figures/亨利·詹姆士': 'figures/亨利·詹姆斯',
}

# 2. summaries 链接 → 实际文件路径映射
# 扫描现有 summaries 文件建立映射
summaries_map = {}
for root, dirs, files in os.walk(os.path.join(base, 'summaries')):
    for f in files:
        if f.endswith('.md') and f != '_index.md':
            name = f.replace('.md', '')
            summaries_map[name] = f'summaries/{name}'

def fuzzy_summary_match(link_name):
    """在 summaries_map 中找最接近的匹配"""
    # 完全匹配
    if link_name in summaries_map:
        return summaries_map[link_name]
    # 包含匹配
    for k, v in summaries_map.items():
        if link_name in k or k in link_name:
            return v
    # 数字前缀匹配
    import re as _re
    nums = _re.findall(r'[0-9]+(?:-[0-9]+)*', link_name)
    if nums:
        for k, v in summaries_map.items():
            if any(n in k for n in nums):
                return v
    return None

# 3. 修复所有文件
fix_count = 0
file_count = 0

for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        original = content
        
        # 修复别名
        for wrong, right in ALIAS_FIXES.items():
            if f'[[{wrong}]]' in content:
                content = content.replace(f'[[{wrong}]]', f'[[{right}]]')
            # 带 alias 的情况
            content = content.replace(f'[[{wrong}|', f'[[{right}|')
        
        # 修复 summaries 链接
        def fix_summary_link(m):
            link = m.group(1).strip()
            alias_part = m.group(2) or ''
            
            if not link.startswith('summaries/'):
                return m.group(0)
            
            link_name = link.replace('summaries/', '')
            actual = fuzzy_summary_match(link_name)
            if actual and actual != link:
                if alias_part:
                    return f'[[{actual}|{alias_part}]]'
                return f'[[{actual}|{link_name}]]'
            return m.group(0)
        
        # 匹配 summaries 链接
        content = re.sub(
            r'\[\[(summaries/[^\]|]+?)(?:\|([^\]]+?))?\]\]',
            lambda m: fix_summary_link(m),
            content
        )
        
        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            fix_count += 1
            file_count += 1

print(f"Fixed {fix_count} aliases in {file_count} files")

# 4. 批量修复 summaries 中的裸链接（无 summaries/ 前缀）
# 先收集所有朱立元/最新文论教程/马新国开头的裸链接
print("\n--- Bare summaries links ---")
bare_summary_links = set()
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'\[\[([^\]|@][^\]|]*?)(?:\|[^\]]+?)?\]\]', content):
            link = m.group(1).strip()
            if '/' in link:
                continue
            if re.match(r'(朱立元|最新文论教程|马新国|理论史教程)', link):
                bare_summary_links.add(link)

print(f"Found {len(bare_summary_links)} bare summary links")
for link in sorted(bare_summary_links)[:20]:
    actual = fuzzy_summary_match(link)
    print(f"  [[{link}]] → [[{actual}]]" if actual else f"  [[{link}]] → ???")
