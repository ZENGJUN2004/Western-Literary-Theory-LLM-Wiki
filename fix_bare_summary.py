"""批量修复裸 summaries 链接 → 加 summaries/ 前缀"""
import os, re

base = r'd:\BaiduNetdiskDownload\西方文论教材\kb\wiki'

# 扫描 summaries 文件建立精确映射
summaries_basenames = set()
for root, dirs, files in os.walk(os.path.join(base, 'summaries')):
    for f in files:
        if f.endswith('.md') and f != '_index.md':
            summaries_basenames.add(f.replace('.md', ''))

def fuzzy_summary_match(link_name):
    """在 summaries_basenames 中找最接近的匹配"""
    if link_name in summaries_basenames:
        return link_name
    for k in summaries_basenames:
        if link_name in k or k in link_name:
            return k
    import re as _re
    nums = _re.findall(r'[0-9]+(?:-[0-9]+)*', link_name)
    if nums:
        for k in summaries_basenames:
            if any(n in k for n in nums):
                return k
    return None

fix_count = 0
for root, dirs, files in os.walk(base):
    for fname in files:
        if not fname.endswith('.md') or fname in ('_log.md', '_index.md', 'task_plan.md', '_indexes.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        original = content
        
        def fix_bare_summary(m):
            link = m.group(1).strip()
            rest = m.group(2) or ''
            actual = fuzzy_summary_match(link)
            if actual:
                if actual == link:
                    return f'[[summaries/{link}{rest}]]'
                return f'[[summaries/{actual}|{link}{rest}]]'
            return m.group(0)
        
        content = re.sub(
            r'\[\[((?:朱立元|最新文论教程|马新国|理论史教程)[^\]|]*?)(\|[^\]]*?)?\]\]',
            fix_bare_summary,
            content
        )
        
        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            fix_count += 1

print(f"Fixed bare summary links in {fix_count} files")
