"""最终验证：核对 338 个 figures 页的完整状态"""
import os, re, yaml

figures_dir = r"d:\BaiduNetdiskDownload\西方文论教材\kb\wiki\figures"
files = sorted(f for f in os.listdir(figures_dir) if f.endswith('.md'))

both = []       # has both lifespan + nationality
lifespan_only = []
nationality_only = []
no_fm = []
bad_yaml = []
no_intro = []   # has data but no 生平简介 section

for f in files:
    path = os.path.join(figures_dir, f)
    with open(path, 'r', encoding='utf-8-sig') as fh:
        content = fh.read()
    name = f.replace('.md', '')

    if not content.startswith('---'):
        no_fm.append(name)
        continue

    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not m:
        no_fm.append(name)
        continue

    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception as e:
        bad_yaml.append(f'{name}: {e}')
        continue

    has_l = bool(fm.get('wiki_lifespan'))
    has_n = bool(fm.get('wiki_nationality'))
    has_intro = bool(re.search(r'^##\s+(生平|生平简介)', content, re.MULTILINE))

    if has_l and has_n:
        both.append(name)
    elif has_l:
        lifespan_only.append(name)
    elif has_n:
        nationality_only.append(name)

    if (has_l or has_n) and not has_intro:
        no_intro.append(name)

print(f"总文件数: {len(files)}")
print(f"✓ 两者兼具 (lifespan + nationality): {len(both)}")
print(f"  有 lifespan 无 nationality ({len(lifespan_only)}): {lifespan_only}")
print(f"  有 nationality 无 lifespan ({len(nationality_only)}): {nationality_only}")
print(f"✗ 无 frontmatter: {len(no_fm)} {no_fm}")
print(f"✗ YAML 解析错误: {len(bad_yaml)}")
for e in bad_yaml:
    print(f"  {e}")
print(f"⚠ 有数据但无 生平简介: {len(no_intro)} {no_intro}")
print(f"\n覆盖率: {len(both)}/{len(files)} = {len(both)/len(files)*100:.1f}%")
