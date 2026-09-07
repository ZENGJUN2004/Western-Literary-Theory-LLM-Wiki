"""
西方文论 Wiki 静态站点生成器
将 kb/wiki/ 下的 markdown 页面转换为 GitHub Pages 静态 HTML
支持：frontmatter 解析、[[wiki-link]] 转换、目录生成、搜索索引
"""
import os, re, sys, json, html as html_mod
from pathlib import Path
from datetime import datetime

# 路径配置
SCRIPT_DIR = Path(__file__).parent.resolve()
KB_ROOT = SCRIPT_DIR / "kb" / "wiki"
OUTPUT_DIR = KB_ROOT.parent.parent / "wiki-site" / "docs"
RAW_DIR = KB_ROOT.parent.parent / "raw"

# 确保输出目录存在
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 类型路由
TYPE_DIRS = {
    "figure": "figures",
    "concept": "concepts",
    "movement": "movements",
    "work": "works",
    "comparison": "comparisons",
    "overview": "overviews",
    "synthesis": "synthesis",
    "summary": "summaries",
}

# ============================================================
# 1. Frontmatter 解析
# ============================================================
def parse_frontmatter(content):
    """解析 YAML frontmatter，返回 (fm_dict, body_str)"""
    if not content.startswith("---"):
        return {}, content
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return {}, content
    fm_text = m.group(1)
    body = content[m.end():]

    # 简易 YAML 解析（不需要 PyYAML 依赖）
    fm = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 列表格式
        if val.startswith("["):
            items = re.findall(r'"([^"]*)"', val)
            if not items:
                items = re.findall(r"'([^']*)'", val)
            fm[key] = items
        elif val.startswith('"') and val.endswith('"'):
            fm[key] = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            fm[key] = val[1:-1]
        else:
            fm[key] = val
    return fm, body


# ============================================================
# 2. 链接解析：[[type/name|display]] → <a href>
# ============================================================
# 已知的页面路径映射
PAGE_PATHS = {}

def build_page_index():
    """建立所有页面的 path → title 映射"""
    global PAGE_PATHS
    PAGE_PATHS = {}
    for type_dir, dir_name in TYPE_DIRS.items():
        dir_path = KB_ROOT / dir_name
        if not dir_path.exists():
            continue
        for f in dir_path.glob("*.md"):
            rel = f.relative_to(KB_ROOT)
            slug = str(rel.with_suffix("")).replace("\\", "/")
            PAGE_PATHS[slug] = {"type": type_dir, "file": str(f), "slug": slug}
            # 也建立别名映射
            try:
                fm, _ = parse_frontmatter(f.read_text(encoding="utf-8-sig"))
                for alias in fm.get("aliases", []):
                    alias_slug = alias.replace("/", "_").replace(" ", "-").lower()
                    PAGE_PATHS[alias_slug] = {"type": type_dir, "file": str(f), "slug": slug}
            except:
                pass

build_page_index()

def resolve_link(target):
    """解析 [[type/name]] 链接，返回 (href, display_text)"""
    # 清理：去掉 type/ 前缀和 | display 部分
    target = re.sub(r"^\w+/", "", target)  # 去掉 figures/ 等前缀
    parts = target.split("|")
    display = parts[-1].strip()
    key = parts[0].strip()

    # 去掉尾部的 URL 参数，如 |古典文论]] → 古典文论
    key = re.sub(r">\s*$", "", key)

    # 查找匹配
    if key in PAGE_PATHS:
        info = PAGE_PATHS[key]
        return f'"{info["slug"]}.html"', display

    # 尝试模糊匹配（去掉空格/标点）
    key_norm = re.sub(r"[\s\-·•]", "", key)
    for slug, info in PAGE_PATHS.items():
        slug_norm = re.sub(r"[\s\-·•]", "", slug)
        if key_norm == slug_norm or key_norm in slug_norm or slug_norm in key_norm:
            return f'"{info["slug"]}.html"', display

    # 未找到，返回原文本但不加链接
    return None, display


# GitHub Pages subpath base URL
BASE_HREF = "/Western-Literary-Theory-LLM-Wiki/"


def convert_wiki_links(text):
    """将 [[...]] 链接转换为 HTML <a> 标签"""
    def replace_link(m):
        inner = m.group(1)
        href, display = resolve_link(inner)
        if href:
            # 将相对路径转换为相对于 <base> 的路径
            # href 格式: "concepts/互文性.html" → /Western-Literary-Theory-LLM-Wiki/concepts/互文性.html
            href_clean = href.strip('"')
            absolute_href = BASE_HREF + href_clean
            return f'<a href="{absolute_href}" class="wiki-link">{display}</a>'
        else:
            # 未找到的链接显示为灰色提示
            return f'<span class="wiki-missing">{inner}</span>'

    return re.sub(r"\[\[([^\]|]+)(?:\|([^]]+))?\]\]", replace_link, text)


# ============================================================
# 3. Markdown → HTML 转换
# ============================================================
def md_to_html(md_text):
    """将 markdown 转换为 HTML"""
    lines = md_text.split("\n")
    html_lines = []
    in_code_block = False
    in_table = False
    table_rows = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # 代码块
        if line.startswith("```"):
            if in_code_block:
                html_lines.append(f"<pre><code>{html_mod.escape(''.join(table_rows))}</code></pre>")
                table_rows = []
                in_code_block = False
            else:
                in_code_block = True
                table_rows = []
            i += 1
            continue

        if in_code_block:
            table_rows.append(line)
            i += 1
            continue

        # 空行
        if not line.strip():
            html_lines.append("")
            i += 1
            continue

        # 标题
        if line.startswith("# "):
            html_lines.append(f'<h1>{convert_wiki_links(html_mod.escape(line[2:]))}</h1>')
        elif line.startswith("## "):
            html_lines.append(f'<h2>{convert_wiki_links(html_mod.escape(line[3:]))}</h2>')
        elif line.startswith("### "):
            html_lines.append(f'<h3>{convert_wiki_links(html_mod.escape(line[4:]))}</h3>')
        elif line.startswith("#### "):
            html_lines.append(f'<h4>{convert_wiki_links(html_mod.escape(line[5:]))}</h4>')
        # 引用块
        elif line.startswith("> "):
            content = convert_wiki_links(html_mod.escape(line[2:]))
            html_lines.append(f'<blockquote>{content}</blockquote>')
        # 表格行
        elif line.startswith("|") and line.endswith("|"):
            cells = [html_mod.escape(c.strip()) for c in line.strip("|").split("|")]
            html_lines.append(f"<tr>{''.join(f'<td>{c}</td>' for c in cells)}</tr>")
        # 分隔线
        elif line.startswith("---") or line.startswith("***"):
            html_lines.append("<hr>")
        # 无序列表
        elif line.startswith("- "):
            content = convert_wiki_links(html_mod.escape(line[2:]))
            html_lines.append(f'<li>{content}</li>')
        # 有序列表
        elif re.match(r"^\d+\. ", line):
            content = convert_wiki_links(html_mod.escape(line.split(". ", 1)[1]))
            html_lines.append(f'<li>{content}</li>')
        # 普通段落
        else:
            content = convert_wiki_links(html_mod.escape(line))
            html_lines.append(f"<p>{content}</p>")

        i += 1

    # 处理代码块残留
    if table_rows:
        html_lines.append(f"<pre><code>{html_mod.escape(''.join(table_rows))}</code></pre>")

    # 将连续的 <li> 包在 <ul> 中
    result = []
    in_ul = False
    for line in html_lines:
        if line.startswith("<li>"):
            if not in_ul:
                result.append("<ul>")
                in_ul = True
            result.append(line)
        else:
            if in_ul:
                result.append("</ul>")
                in_ul = False
            result.append(line)
    if in_ul:
        result.append("</ul>")

    return "\n".join(result)


# ============================================================
# 4. HTML 模板
# ============================================================
TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - 西方文论 Wiki</title>
<base href="/Western-Literary-Theory-LLM-Wiki/">
<style>
:root {{
  --bg: #fafaf8;
  --fg: #1a1a1a;
  --muted: #6b6b6b;
  --accent: #2563eb;
  --accent-light: #dbeafe;
  --border: #e2e2e0;
  --card-bg: #ffffff;
  --tag-bg: #f0f0ed;
  --sidebar-bg: #f5f5f3;
  --link-color: #1d4ed8;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1a1a1a;
    --fg: #e8e8e6;
    --muted: #999;
    --accent: #60a5fa;
    --accent-light: #1e3a5f;
    --border: #333;
    --card-bg: #222;
    --tag-bg: #2a2a2a;
    --sidebar-bg: #1e1e1e;
    --link-color: #93c5fd;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, "Noto Serif SC", "Source Han Serif CN", Georgia, serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.8;
  font-size: 16px;
}}
a {{ color: var(--link-color); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.wiki-link {{ color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent-light); }}
.wiki-link:hover {{ border-bottom-color: var(--accent); text-decoration: none; }}
.wiki-missing {{ color: var(--muted); font-style: italic; opacity: 0.6; }}

/* 布局 */
.layout {{ display: flex; min-height: 100vh; }}

/* 侧边栏 */
.sidebar {{
  width: 260px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  padding: 20px 16px;
  overflow-y: auto;
  position: fixed;
  top: 0; left: 0; bottom: 0;
  z-index: 100;
}}
.sidebar-header {{
  padding: 8px 0 16px;
  border-bottom: 2px solid var(--border);
  margin-bottom: 16px;
}}
.sidebar-header h1 {{
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.02em;
}}
.sidebar-header p {{
  font-size: 12px;
  color: var(--muted);
  margin-top: 4px;
}}
.nav-section {{ margin-bottom: 20px; }}
.nav-section-title {{
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  padding: 4px 8px;
  margin-bottom: 4px;
}}
.nav-item {{
  display: block;
  padding: 4px 8px;
  font-size: 14px;
  color: var(--fg);
  border-radius: 4px;
  text-decoration: none;
}}
.nav-item:hover {{ background: var(--accent-light); color: var(--accent); text-decoration: none; }}
.nav-item.active {{ background: var(--accent-light); color: var(--accent); font-weight: 600; }}
.search-box {{
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--fg);
  font-size: 14px;
  margin-bottom: 16px;
  outline: none;
}}
.search-box:focus {{ border-color: var(--accent); }}

/* 主内容区 */
.main {{
  flex: 1;
  margin-left: 260px;
  padding: 40px 60px;
  max-width: 900px;
}}
.content {{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 40px 48px;
}}
.content h1 {{
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--border);
}}
.content h2 {{
  font-size: 20px;
  font-weight: 600;
  margin-top: 32px;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}}
.content h3 {{ font-size: 17px; margin-top: 24px; margin-bottom: 8px; }}
.content h4 {{ font-size: 15px; margin-top: 20px; margin-bottom: 6px; }}
.content p {{ margin-bottom: 12px; }}
.content blockquote {{
  border-left: 3px solid var(--accent);
  padding: 8px 16px;
  margin: 16px 0;
  background: var(--accent-light);
  border-radius: 0 4px 4px 0;
  font-style: italic;
}}
.content ul {{ margin: 12px 0 12px 24px; }}
.content li {{ margin-bottom: 4px; }}
.content table {{
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
  font-size: 14px;
}}
.content th, .content td {{
  border: 1px solid var(--border);
  padding: 8px 12px;
  text-align: left;
}}
.content th {{ background: var(--sidebar-bg); font-weight: 600; }}
.content pre {{
  background: var(--sidebar-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px;
  overflow-x: auto;
  font-size: 13px;
  margin: 16px 0;
}}
.content code {{ font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 13px; }}
.content hr {{ border: none; border-top: 1px solid var(--border); margin: 24px 0; }}

/* 元数据栏 */
.meta-bar {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}}
.meta-tag {{
  display: inline-block;
  padding: 2px 10px;
  background: var(--tag-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  font-size: 12px;
  color: var(--muted);
  text-decoration: none;
}}
.meta-tag:hover {{ background: var(--accent-light); color: var(--accent); border-color: var(--accent); text-decoration: none; }}
.meta-type {{
  padding: 2px 10px;
  background: var(--accent-light);
  border: 1px solid var(--accent);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
}}
.meta-info {{ font-size: 12px; color: var(--muted); margin-left: auto; }}

/* 导航栏（上一页/下一页） */
.page-nav {{
  display: flex;
  justify-content: space-between;
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
}}
.page-nav a {{
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  color: var(--fg);
  text-decoration: none;
}}
.page-nav a:hover {{ border-color: var(--accent); color: var(--accent); text-decoration: none; }}

/* 移动端 */
.menu-toggle {{
  display: none;
  position: fixed;
  top: 12px; left: 12px;
  z-index: 200;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 18px;
  cursor: pointer;
}}
@media (max-width: 768px) {{
  .sidebar {{ transform: translateX(-100%); transition: transform 0.3s; }}
  .sidebar.open {{ transform: translateX(0); }}
  .main {{ margin-left: 0; padding: 60px 16px 40px; }}
  .content {{ padding: 24px 20px; }}
  .menu-toggle {{ display: block; }}
}}
</style>
</head>
<body>

<button class="menu-toggle" onclick="document.querySelector('.sidebar').classList.toggle('open')">☰</button>

<div class="layout">
<nav class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <h1>西方文论 Wiki</h1>
    <p>Western Literary Theory Knowledge Base</p>
  </div>
  <input type="text" class="search-box" placeholder="搜索页面…" id="searchBox" onkeyup="filterNav()">
  <div id="navTree"></div>
</nav>

<main class="main">
  <article class="content" id="content">
    {body_html}
  </article>
  <div class="page-nav" id="pageNav">
    {prev_next}
  </div>
</main>
</div>

<script>
// 基础路径（GitHub Pages subpath）
const BASE_HREF = "{base_href}";
// 侧边栏导航数据
const NAV_DATA = {nav_json};

function buildNav() {{
  const tree = document.getElementById('navTree');
  let html = '';
  for (const [section, items] of Object.entries(NAV_DATA)) {{
    html += `<div class="nav-section">
      <div class="nav-section-title">${{section}}</div>`;
    for (const [slug, info] of Object.entries(items)) {{
      const title = info.title || slug;
      const active = window.location.pathname.includes(slug + '.html') ? ' active' : '';
      html += `<a class="nav-item${{active}}" href="${{BASE_HREF}}${{slug}}.html">${{title}}</a>`;
    }}
    html += '</div>';
  }}
  tree.innerHTML = html;
}}
buildNav();

function filterNav() {{
  const q = document.getElementById('searchBox').value.toLowerCase();
  document.querySelectorAll('.nav-item').forEach(a => {{
    const match = !q || a.textContent.toLowerCase().includes(q) || a.href.toLowerCase().includes(q);
    a.style.display = match ? '' : 'none';
  }});
  document.querySelectorAll('.nav-section').forEach(sec => {{
    sec.style.display = sec.querySelector('.nav-item:not([style*="none"])') ? '' : 'none';
  }});
}}
</script>
</body>
</html>'''


# ============================================================
# 5. 主生成逻辑
# ============================================================
def generate_nav_data():
    """生成侧边栏导航 JSON"""
    nav = {}
    for type_dir, dir_name in TYPE_DIRS.items():
        dir_path = KB_ROOT / dir_name
        if not dir_path.exists():
            continue
        items = {}
        for f in sorted(dir_path.glob("*.md")):
            rel = f.relative_to(KB_ROOT)
            slug = str(rel.with_suffix("")).replace("\\", "/")
            try:
                content = f.read_text(encoding="utf-8-sig")
                fm, body = parse_frontmatter(content)
                # 取标题：# 标题 或文件名
                title = ""
                for bl in body.split("\n"):
                    if bl.startswith("# "):
                        title = bl[2:].strip()
                        break
                if not title:
                    title = f.stem
                items[slug] = {"title": title}
            except Exception as e:
                items[slug] = {"title": f.stem, "error": str(e)}
        if items:
            nav[dir_name.capitalize()] = items
    return json.dumps(nav, ensure_ascii=False, indent=2)


def get_prev_next(slug, all_slugs):
    """获取上一页/下一页链接"""
    try:
        idx = all_slugs.index(slug)
    except ValueError:
        return "", ""
    prev = all_slugs[idx-1] if idx > 0 else ""
    next_ = all_slugs[idx+1] if idx < len(all_slugs) - 1 else ""
    return prev, next_


def generate_page(filepath):
    """生成单个页面的 HTML"""
    content = filepath.read_text(encoding="utf-8-sig")
    fm, body = parse_frontmatter(content)

    # 提取标题
    title = ""
    for bl in body.split("\n"):
        if bl.startswith("# "):
            title = bl[2:].strip()
            break
    if not title:
        title = filepath.stem

    # 生成 HTML 正文
    body_html = md_to_html(body)

    # 构建元数据栏
    meta_parts = []
    type_label = fm.get("type", "page")
    type_names = {"figure": "人物", "concept": "概念", "movement": "流派",
                  "work": "原典", "comparison": "对比", "overview": "谱系",
                  "synthesis": "综合", "summary": "摘要"}
    meta_parts.append(f'<span class="meta-type">{type_names.get(type_label, type_label)}</span>')

    tags = fm.get("tags", [])
    for tag in tags[:5]:
        # 标签链接到搜索
        meta_parts.append(f'<a class="meta-tag" href="{BASE_HREF}search.html?q={tag}">{tag}</a>')

    lifespan = fm.get("wiki_lifespan", "")
    if lifespan:
        meta_parts.append(f'<span class="meta-info">{lifespan}</span>')

    updated = fm.get("updated", "")
    if updated:
        meta_parts.append(f'<span class="meta-info">更新于 {updated}</span>')

    meta_bar = "<div class='meta-bar'>" + "".join(meta_parts) + "</div>"

    # 完整 HTML
    full_html = TEMPLATE.format(
        title=title,
        body_html=meta_bar + body_html,
        nav_json=generate_nav_data(),
        prev_next="{prev_next}",  # 保留占位符，稍后由主循环替换
        base_href=BASE_HREF,
    )

    return full_html, title, fm


def main():
    print("=" * 50)
    print("西方文论 Wiki 静态站点生成器")
    print("=" * 50)

    # 收集所有页面并排序
    all_pages = []
    for type_dir, dir_name in TYPE_DIRS.items():
        dir_path = KB_ROOT / dir_name
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.glob("*.md")):
            all_pages.append((type_dir, f))

    print(f"总页面数: {len(all_pages)}")

    # 按 slug 排序以计算 prev/next
    all_slugs = []
    for type_dir, f in all_pages:
        rel = f.relative_to(KB_ROOT)
        slug = str(rel.with_suffix("")).replace("\\", "/")
        all_slugs.append(slug)

    generated = 0
    errors = []

    for type_dir, filepath in all_pages:
        rel = filepath.relative_to(KB_ROOT)
        slug = str(rel.with_suffix("")).replace("\\", "/")
        try:
            html, title, fm = generate_page(filepath)

            # 添加上一页/下一页
            prev, next_ = get_prev_next(slug, all_slugs)
            nav_html = ""
            if prev:
                nav_html += f'<a href="{BASE_HREF}{prev}.html">← 上一页</a>'
            else:
                nav_html += '<span></span>'
            if next_:
                nav_html += f'<a href="{BASE_HREF}{next_}.html">下一页 →</a>'
            else:
                nav_html += '<span></span>'
            html = html.replace('{prev_next}', nav_html)

            # 写文件
            out_path = OUTPUT_DIR / f"{slug}.html"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(html, encoding="utf-8")
            generated += 1

        except Exception as e:
            errors.append(f"  ✗ {slug}: {e}")
            print(f"  ✗ {slug}: {e}")

    print(f"\n生成完成: {generated} 个页面")
    if errors:
        print(f"错误 ({len(errors)}):")
        for e in errors[:5]:
            print(e)

    # 生成搜索索引
    print("\n生成搜索索引…")
    search_idx = []
    for type_dir, filepath in all_pages:
        try:
            content = filepath.read_text(encoding="utf-8-sig")
            fm, body = parse_frontmatter(content)
            rel = filepath.relative_to(KB_ROOT)
            slug = str(rel.with_suffix("")).replace("\\", "/")
            title = ""
            for bl in body.split("\n"):
                if bl.startswith("# "):
                    title = bl[2:].strip()
                    break
            if not title:
                title = filepath.stem
            search_idx.append({
                "slug": slug,
                "title": title,
                "type": type_dir,
                "tags": fm.get("tags", []),
                "body": body[:500],  # 只索引前 500 字
            })
        except:
            pass

    idx_path = OUTPUT_DIR / "search-index.json"
    idx_path.write_text(json.dumps(search_idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"搜索索引: {len(search_idx)} 条记录 → {idx_path}")

    # 生成首页
    generate_homepage(search_idx)

    # 生成独立搜索页（供标签等链接使用）
    generate_search_page()

    # 生成关系图谱数据和页面
    print("\n生成关系图谱…")
    generate_graph_data(all_pages)
    generate_graph_page()

    # 为每个类型目录生成索引页（用keys而不是values）
    for type_key in TYPE_DIRS.keys():
        type_dir = TYPE_DIRS[type_key]
        type_path = OUTPUT_DIR / type_dir
        type_path.mkdir(parents=True, exist_ok=True)
        items = [p for p in search_idx if p["type"] == type_key]
        items.sort(key=lambda x: x["title"])
        type_html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{type_dir} · 西方文论 Wiki</title>
<style>
:root {{ --bg:#fafaf8; --fg:#1a1a1a; --muted:#6b6b6b; --accent:#2563eb; --accent-light:#dbeafe; --border:#e2e2e0; --card-bg:#fff; }}
@media (prefers-color-scheme:dark) {{ :root {{ --bg:#1a1a1a; --fg:#e8e8e6; --muted:#999; --accent:#60a5fa; --accent-light:#1e3a5f; --border:#333; --card-bg:#222; }} }}
body {{ font-family:-apple-system,"Noto Serif SC",Georgia,serif; background:var(--bg); color:var(--fg); line-height:1.7; margin:0; padding:40px 24px; }}
a {{ color:var(--accent); text-decoration:none; }}
h1 {{ font-size:28px; margin-bottom:8px; }}
.back {{ font-size:14px; color:var(--muted); margin-bottom:24px; display:block; }}
.letter-group {{ margin-bottom:24px; }}
.letter {{ font-size:22px; font-weight:700; color:var(--accent); margin:16px 0 8px; border-bottom:1px solid var(--border); padding-bottom:4px; }}
ul {{ list-style:none; padding:0; }}
li {{ padding:4px 0; }}
li a {{ font-size:15px; }}
</style></head><body>
<h1>{type_dir}</h1>
<a class="back" href="{BASE_HREF}">← 返回首页</a>
'''
        # 按拼音首字母分组
        current_letter = ""
        for idx2, p in enumerate(items):
            title = p["title"]
            first_char = title[0] if title else "?"
            if first_char != current_letter:
                if current_letter and idx2 > 0:
                    type_html += '</ul></div>\n'
                current_letter = first_char
                type_html += f'<div class="letter-group"><div class="letter">{first_char}</div><ul>\n'
            type_html += f'<li><a href="{BASE_HREF}{p["slug"]}.html">{title}</a></li>\n'
        if current_letter:
            type_html += '</ul></div>\n'

        type_html += '</body></html>'
        (type_path / "index.html").write_text(type_html, encoding="utf-8")
        print(f"  {type_dir}/index.html ({len(items)} 页)")

    print("\n✓ 生成完毕，站点位于:", OUTPUT_DIR)


def generate_homepage(search_idx):
    """生成首页"""
    home_html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>西方文论 Wiki · 首页</title>
<base href="{base_href}">
<style>
:root {{
  --bg: #fafaf8; --fg: #1a1a1a; --muted: #6b6b6b;
  --accent: #2563eb; --accent-light: #dbeafe;
  --border: #e2e2e0; --card-bg: #ffffff;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1a1a1a; --fg: #e8e8e6; --muted: #999;
    --accent: #60a5fa; --accent-light: #1e3a5f;
    --border: #333; --card-bg: #222;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, "Noto Serif SC", Georgia, serif; background: var(--bg); color: var(--fg); line-height: 1.7; }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.container {{ max-width: 900px; margin: 0 auto; padding: 40px 24px; }}
h1 {{ font-size: 32px; font-weight: 700; margin-bottom: 8px; }}
.subtitle {{ color: var(--muted); font-size: 16px; margin-bottom: 32px; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 40px; }}
.stat-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 16px; text-align: center; }}
.stat-num {{ font-size: 28px; font-weight: 700; color: var(--accent); }}
.stat-label {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
h2 {{ font-size: 20px; font-weight: 600; margin: 32px 0 16px; padding-bottom: 8px; border-bottom: 2px solid var(--border); }}
.search-box {{ width: 100%; padding: 12px 16px; border: 1px solid var(--border); border-radius: 8px; background: var(--card-bg); color: var(--fg); font-size: 16px; margin-bottom: 24px; outline: none; }}
.search-box:focus {{ border-color: var(--accent); }}
.result-list {{ list-style: none; }}
.result-list li {{ padding: 8px 12px; border-radius: 6px; margin-bottom: 4px; }}
.result-list li:hover {{ background: var(--accent-light); }}
.result-type {{ display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; margin-right: 8px; background: var(--accent-light); color: var(--accent); }}
.result-title {{ font-weight: 500; }}
.result-body {{ font-size: 13px; color: var(--muted); margin-top: 2px; }}
.section-nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }}
.section-nav a {{ padding: 6px 14px; border: 1px solid var(--border); border-radius: 20px; font-size: 14px; color: var(--fg); }}
.section-nav a:hover {{ border-color: var(--accent); color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <h1>西方文论 Wiki</h1>
  <p class="subtitle">Western Literary Theory Knowledge Base · 共 {total} 个页面</p>

  <div class="stats">
    <div class="stat-card"><div class="stat-num">{figures}</div><div class="stat-label">人物</div></div>
    <div class="stat-card"><div class="stat-num">{concepts}</div><div class="stat-label">概念</div></div>
    <div class="stat-card"><div class="stat-num">{movements}</div><div class="stat-label">流派</div></div>
    <div class="stat-card"><div class="stat-num">{works}</div><div class="stat-label">原典</div></div>
    <div class="stat-card"><div class="stat-num">{summaries}</div><div class="stat-label">章节摘要</div></div>
    <div class="stat-card"><div class="stat-num">{others}</div><div class="stat-label">其他</div></div>
  </div>

  <div class="section-nav">
    <a href="{base_href}figures/">人物</a>
    <a href="{base_href}concepts/">概念</a>
    <a href="{base_href}movements/">流派</a>
    <a href="{base_href}works/">原典</a>
    <a href="{base_href}comparisons/">对比</a>
    <a href="{base_href}overviews/">谱系</a>
    <a href="{base_href}synthesis/">综合</a>
    <a href="{base_href}summaries/">摘要</a>
    <a href="{base_href}graph.html" style="border-color:var(--accent);color:var(--accent);font-weight:600;">关系图谱</a>
  </div>

  <input class="search-box" type="text" id="searchInput" placeholder="搜索页面…" oninput="doSearch(this.value)">

  <h2>搜索结果</h2>
  <ul class="result-list" id="results"></ul>

  <h2>全部页面</h2>
  <ul class="result-list" id="allPages"></ul>
</div>

<script>
const INDEX = {search_json};
const BASE_HREF = "{base_href}";
const TYPE_LABELS = {{figure:"人物", concept:"概念", movement:"流派", work:"原典",
  comparison:"对比", overview:"谱系", synthesis:"综合", summary:"摘要"}};

function doSearch(q) {{
  const results = document.getElementById('results');
  if (!q.trim()) {{ results.innerHTML = ''; return; }}
  q = q.toLowerCase();
  const hits = INDEX.filter(p =>
    p.title.toLowerCase().includes(q) ||
    p.body.toLowerCase().includes(q) ||
    p.tags.some(t => t.toLowerCase().includes(q))
  ).slice(0, 20);
  results.innerHTML = hits.map(p => `
    <li>
      <a href="{base_href}${{p.slug}}.html">
        <span class="result-type">${{TYPE_LABELS[p.type] || p.type}}</span>
        <span class="result-title">${{p.title}}</span>
      </a>
      <div class="result-body">${{p.body.substring(0, 100)}}…</div>
    </li>
  `).join('');
}}

// 渲染全部页面（按类型分组）
const allPages = document.getElementById('allPages');
const byType = {{}};
INDEX.forEach(p => {{
  if (!byType[p.type]) byType[p.type] = [];
  byType[p.type].push(p);
}});
const TYPE_ORDER = ['figure','concept','movement','work','comparison','overview','synthesis','summary'];
TYPE_ORDER.forEach(t => {{
  if (!byType[t]) return;
  allPages.innerHTML += `<li style="margin-top:12px;font-weight:600;color:var(--accent)">${{TYPE_LABELS[t]||t}}（${{byType[t].length}}）</li>`;
  byType[t].slice(0, 50).forEach(p => {{
    allPages.innerHTML += `<li><a href="${{BASE_HREF}}${{p.slug}}.html">${{p.title}}</a></li>`;
  }});
  if (byType[t].length > 50) allPages.innerHTML += `<li style="color:var(--muted)">… 还有 ${{byType[t].length - 50}} 个</li>`;
}});
</script>
</body>
</html>'''

    home_path = OUTPUT_DIR / "index.html"
    home_path.write_text(home_html.format(
        total=len(search_idx),
        figures=sum(1 for p in search_idx if p["type"] == "figure"),
        concepts=sum(1 for p in search_idx if p["type"] == "concept"),
        movements=sum(1 for p in search_idx if p["type"] == "movement"),
        works=sum(1 for p in search_idx if p["type"] == "work"),
        summaries=sum(1 for p in search_idx if p["type"] == "summary"),
        others=sum(1 for p in search_idx if p["type"] not in ("figure","concept","movement","work","summary")),
        search_json=json.dumps(search_idx, ensure_ascii=False, indent=2),
        base_href=BASE_HREF,
    ), encoding="utf-8")
    print(f"首页: {home_path}")


def generate_search_page():
    """生成独立搜索页 search.html（标签等链接指向它）"""
    search_html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>搜索 · 西方文论 Wiki</title>
<base href="{BASE_HREF}">
<style>
body {{ font-family:-apple-system,"Noto Serif SC",Georgia,serif; background:#fafaf8; color:#1a1a1a; line-height:1.7; margin:0; padding:40px 24px; max-width:820px; }}
a {{ color:#2563eb; text-decoration:none; }}
h1 {{ font-size:28px; margin-bottom:8px; }}
.back {{ font-size:14px; color:#6b6b6b; margin-bottom:24px; display:block; }}
#q {{ width:100%; padding:10px 14px; border:1px solid #e2e2e0; border-radius:8px; font-size:15px; margin-bottom:24px; }}
.result-list {{ list-style:none; padding:0; }}
.result-list li {{ padding:8px 12px; border-radius:6px; margin-bottom:4px; }}
.result-list li:hover {{ background:#dbeafe; }}
.result-type {{ display:inline-block; padding:1px 8px; border-radius:10px; font-size:11px; font-weight:600; margin-right:8px; background:#dbeafe; color:#2563eb; }}
.result-title {{ font-weight:500; }}
.result-body {{ font-size:13px; color:#6b6b6b; margin-top:2px; }}
</style></head><body>
<h1>搜索</h1>
<a class="back" href="{BASE_HREF}">← 返回首页</a>
<input id="q" type="text" placeholder="输入关键词…" oninput="doSearch(this.value)">
<ul class="result-list" id="results"></ul>
<script>
const url = new URL(location.href);
const initial = url.searchParams.get('q') || '';
document.getElementById('q').value = initial;
fetch('{BASE_HREF}search-index.json').then(r => r.json()).then(INDEX => {{
  window._INDEX = INDEX;
  if (initial) doSearch(initial);
}});
function doSearch(q) {{
  const results = document.getElementById('results');
  if (!q.trim()) {{ results.innerHTML = ''; return; }}
  q = q.toLowerCase();
  const hits = (window._INDEX || []).filter(p =>
    p.title.toLowerCase().includes(q) ||
    p.body.toLowerCase().includes(q) ||
    (p.tags || []).some(t => t.toLowerCase().includes(q))
  ).slice(0, 30);
  const labels = {{ figure:"人物", concept:"概念", movement:"流派", work:"原典",
    comparison:"对比", overview:"谱系", synthesis:"综合", summary:"摘要" }};
  results.innerHTML = hits.map(p => `
    <li>
      <a href="{BASE_HREF}${{p.slug}}.html">
        <span class="result-type">${{labels[p.type] || p.type}}</span>
        <span class="result-title">${{p.title}}</span>
      </a>
      <div class="result-body">${{p.body.substring(0, 100)}}…</div>
    </li>
  `).join('');
}}
</script>
</body></html>'''
    (OUTPUT_DIR / "search.html").write_text(search_html, encoding="utf-8")
    print(f"搜索页: {OUTPUT_DIR / 'search.html'}")


def generate_graph_data(all_pages):
    """生成关系图谱数据 graph-data.json（节点 + 边）"""
    nodes = []
    edges = []
    edge_set = set()  # 去重

    # 先收集所有合法 slug 集合
    all_slugs = set()
    for type_dir, filepath in all_pages:
        rel = filepath.relative_to(KB_ROOT)
        slug = str(rel.with_suffix("")).replace("\\", "/")
        all_slugs.add(slug)

    # 生成节点
    for type_dir, filepath in all_pages:
        try:
            content = filepath.read_text(encoding="utf-8-sig")
            fm, body = parse_frontmatter(content)
            rel = filepath.relative_to(KB_ROOT)
            slug = str(rel.with_suffix("")).replace("\\", "/")
            title = ""
            for bl in body.split("\n"):
                if bl.startswith("# "):
                    title = bl[2:].strip()
                    break
            if not title:
                title = filepath.stem
            nodes.append({
                "id": slug,
                "label": title,
                "group": type_dir,
                "tags": fm.get("tags", []),
            })
        except:
            pass

    # 生成边（从 wiki-links 提取）
    wiki_link_re = re.compile(r"\[\[([^\]|]+)(?:\|([^]]+))?\]\]")
    for type_dir, filepath in all_pages:
        try:
            content = filepath.read_text(encoding="utf-8-sig")
            _, body = parse_frontmatter(content)
            rel = filepath.relative_to(KB_ROOT)
            source_slug = str(rel.with_suffix("")).replace("\\", "/")

            for m in wiki_link_re.finditer(body):
                inner = m.group(1)
                # 去掉 type/ 前缀
                target = re.sub(r"^\w+/", "", inner)
                target = target.split("|")[0].strip()
                target = re.sub(r">\s*$", "", target)

                # 精确匹配
                if target in PAGE_PATHS:
                    target_slug = PAGE_PATHS[target]["slug"]
                else:
                    # 模糊匹配
                    key_norm = re.sub(r"[\s\-·•]", "", target)
                    target_slug = None
                    for slug, info in PAGE_PATHS.items():
                        slug_norm = re.sub(r"[\s\-·•]", "", slug)
                        if key_norm == slug_norm or key_norm in slug_norm or slug_norm in key_norm:
                            target_slug = info["slug"]
                            break
                    if not target_slug:
                        continue

                if target_slug in all_slugs and target_slug != source_slug:
                    edge_key = (source_slug, target_slug)
                    if edge_key not in edge_set:
                        edge_set.add(edge_key)
                        edges.append({"from": source_slug, "to": target_slug})
        except:
            pass

    graph_data = {"nodes": nodes, "edges": edges}
    out_path = OUTPUT_DIR / "graph-data.json"
    out_path.write_text(json.dumps(graph_data, ensure_ascii=False), encoding="utf-8")
    print(f"关系图谱: {len(nodes)} 节点, {len(edges)} 边 → {out_path}")
    return graph_data


def generate_graph_page():
    """生成关系图谱可视化页面 graph.html"""
    graph_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关系图谱 · 西方文论 Wiki</title>
<base href="{BASE_HREF}">
<style>
:root {{
  --bg: #fafaf8; --fg: #1a1a1a; --muted: #6b6b6b;
  --accent: #2563eb; --border: #e2e2e0; --card-bg: #ffffff;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1a1a1a; --fg: #e8e8e6; --muted: #999;
    --accent: #60a5fa; --border: #333; --card-bg: #222;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, "Noto Serif SC", Georgia, serif; background: var(--bg); color: var(--fg); }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

#topbar {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 10;
  background: var(--card-bg); border-bottom: 1px solid var(--border);
  padding: 10px 20px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}}
#topbar .title {{ font-size: 18px; font-weight: 700; white-space: nowrap; }}
#topbar .back {{ font-size: 14px; color: var(--muted); }}
#search {{ padding: 6px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--fg); font-size: 14px; width: 200px; outline: none; }}
#search:focus {{ border-color: var(--accent); }}

.filters {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.filter-chip {{
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border: 1px solid var(--border); border-radius: 20px;
  font-size: 13px; cursor: pointer; user-select: none; transition: all 0.2s;
}}
.filter-chip input {{ margin: 0; accent-color: var(--accent); }}
.filter-chip.active {{ border-color: var(--accent); background: rgba(37,99,235,0.08); }}
.filter-chip .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}

#controls {{
  position: fixed; top: 56px; right: 16px; z-index: 10;
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; display: flex; flex-direction: column; gap: 8px; font-size: 13px;
}}
#controls button {{
  padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg); color: var(--fg); cursor: pointer; font-size: 13px;
}}
#controls button:hover {{ border-color: var(--accent); color: var(--accent); }}
#info {{
  position: fixed; bottom: 16px; left: 16px; z-index: 10;
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 16px; font-size: 13px; color: var(--muted);
}}

#network {{ width: 100vw; height: 100vh; }}

#tooltip {{
  position: fixed; z-index: 20; background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px; font-size: 14px; pointer-events: none;
  display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.12); max-width: 320px;
}}
#tooltip .tt-title {{ font-weight: 700; margin-bottom: 4px; }}
#tooltip .tt-type {{ font-size: 12px; color: var(--muted); }}
#tooltip .tt-link {{ margin-top: 6px; }}

.loading {{ position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%); font-size: 18px; color: var(--muted); }}
</style>
</head>
<body>

<div id="topbar">
  <span class="title">关系图谱</span>
  <a class="back" href="{BASE_HREF}">← 返回首页</a>
  <input id="search" type="text" placeholder="搜索节点…" oninput="searchNode(this.value)">
  <div class="filters" id="filters"></div>
</div>

<div id="controls">
  <button onclick="togglePhysics()" id="physBtn">⏸ 暂停物理</button>
  <button onclick="zoomFit()">⊞ 适配视图</button>
  <button onclick="toggleLabels()" id="labelBtn">隐藏标签</button>
</div>

<div id="info"><span id="infoText">加载中…</span></div>
<div id="tooltip"><div class="tt-title"></div><div class="tt-type"></div><div class="tt-link"></div></div>

<div id="network"></div>
<div class="loading" id="loading">正在加载图谱数据…</div>

<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<script>
const TYPE_COLORS = {{
  figure: "#ef4444",
  concept: "#2563eb",
  movement: "#16a34a",
  work: "#a855f7",
  summary: "#f59e0b",
  comparison: "#06b6d4",
  overview: "#ec4899",
  synthesis: "#6b7280",
}};
const TYPE_LABELS = {{
  figure: "人物", concept: "概念", movement: "流派", work: "原典",
  summary: "摘要", comparison: "对比", overview: "谱系", synthesis: "综合",
}};

let network = null;
let allNodes = [], allEdges = [];
let physicsOn = true;
let labelsVisible = true;
let activeTypes = new Set();

fetch('{BASE_HREF}graph-data.json')
  .then(r => r.json())
  .then(data => {{
    document.getElementById('loading').style.display = 'none';

    allNodes = data.nodes.map(n => ({{
      id: n.id,
      label: n.label,
      group: n.group,
      tags: n.tags || [],
      _deg: 0,
    }}));
    allEdges = data.edges.map(e => ({{
      from: e.from,
      to: e.to,
      _width: 0.5,
    }}));

    // 计算度数
    allEdges.forEach(e => {{
      const ns = allNodes.find(n => n.id === e.from);
      const nt = allNodes.find(n => n.id === e.to);
      if (ns) ns._deg++;
      if (nt) nt._deg++;
    }});

    // 节点大小按度数缩放
    allNodes.forEach(n => {{
      n.value = Math.max(3, Math.min(30, 3 + n._deg * 1.5));
      n.color = TYPE_COLORS[n.group] || "#6b7280";
      n.font = {{ color: document.documentElement.style.getPropertyValue('--fg') || '#1a1a1a', size: 12 }};
      if (!labelsVisible) n.label = undefined;
    }});

    // 边样式
    allEdges.forEach(e => {{
      e.color = {{ opacity: 0.25 }};
      e.arrows = {{ to: {{ enabled: true, scaleFactor: 0.3 }} }};
      e.smooth = {{ type: "continuous" }};
    }});

    initFilters();
    drawNetwork();
    updateInfo();
  }});

function initFilters() {{
  const container = document.getElementById('filters');
  const types = Object.keys(TYPE_LABELS);
  types.forEach(t => {{
    const count = allNodes.filter(n => n.group === t).length;
    if (count === 0) return;
    activeTypes.add(t);
    const chip = document.createElement('label');
    chip.className = 'filter-chip active';
    chip.innerHTML = `<input type="checkbox" checked onchange="toggleType('${{t}}', this.checked)">
      <span class="dot" style="background:${{TYPE_COLORS[t]}}"></span>${{TYPE_LABELS[t]}}(${{count}})`;
    container.appendChild(chip);
  }});
}}

function toggleType(type, checked) {{
  if (checked) activeTypes.add(type); else activeTypes.delete(type);
  const chip = event.target.closest('.filter-chip');
  chip.classList.toggle('active', checked);
  drawNetwork();
  updateInfo();
}}

function drawNetwork() {{
  const visibleIds = new Set(allNodes.filter(n => activeTypes.has(n.group)).map(n => n.id));
  const visNodes = allNodes.filter(n => visibleIds.has(n.id));
  const visEdges = allEdges.filter(e => visibleIds.has(e.from) && visibleIds.has(e.to));

  const container = document.getElementById('network');
  const data = {{ nodes: new vis.DataSet(visNodes), edges: new vis.DataSet(visEdges) }};

  if (network) network.destroy();

  const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  network = new vis.Network(container, data, {{
    nodes: {{
      shape: 'dot',
      scaling: {{ min: 6, max: 30, label: {{ min: 8, max: 16, maxVisible: 30, drawThreshold: 8 }} }},
      font: {{ color: dark ? '#e8e8e6' : '#1a1a1a', size: 12, face: 'sans-serif', strokeColor: dark ? '#1a1a1a' : '#fafaf8', strokeWidth: 3 }},
      borderWidth: 1.5,
    }},
    edges: {{
      color: {{ opacity: 0.2 }},
      arrows: {{ to: {{ enabled: true, scaleFactor: 0.3 }} }},
      smooth: {{ type: "continuous" }},
    }},
    physics: {{
      enabled: physicsOn,
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {{ gravitationalConstant: -30, centralGravity: 0.008, springLength: 80, springConstant: 0.04, damping: 0.4 }},
      stabilization: {{ iterations: 150, updateInterval: 25 }},
    }},
    interaction: {{
      hover: true,
      tooltipDelay: 200,
      navigationButtons: true,
      keyboard: true,
      multiselect: false,
    }},
  }});

  network.on('click', function(params) {{
    if (params.nodes.length > 0) {{
      const nodeId = params.nodes[0];
      const node = allNodes.find(n => n.id === nodeId);
      if (node) {{
        window.location.href = '{BASE_HREF}' + node.id + '.html';
      }}
    }}
  }});

  network.on('hoverNode', function(params) {{
    const node = allNodes.find(n => n.id === params.node);
    if (!node) return;
    const tt = document.getElementById('tooltip');
    tt.querySelector('.tt-title').textContent = node.label;
    tt.querySelector('.tt-type').textContent = (TYPE_LABELS[node.group] || node.group) + ' · 连接度: ' + node._deg;
    tt.querySelector('.tt-link').innerHTML = '<a href="{BASE_HREF}' + node.id + '.html">查看详情 →</a>';
    tt.style.display = 'block';
  }});
  network.on('blurNode', function() {{
    document.getElementById('tooltip').style.display = 'none';
  }});
  document.getElementById('network').addEventListener('mousemove', function(e) {{
    const tt = document.getElementById('tooltip');
    if (tt.style.display !== 'none') {{
      tt.style.left = (e.clientX + 14) + 'px';
      tt.style.top = (e.clientY + 14) + 'px';
    }}
  }});
}}

function togglePhysics() {{
  physicsOn = !physicsOn;
  if (network) network.setOptions({{ physics: {{ enabled: physicsOn }} }});
  document.getElementById('physBtn').textContent = physicsOn ? '⏸ 暂停物理' : '▶ 启动物理';
}}

function zoomFit() {{
  if (network) network.fit({{ animation: {{ duration: 500 }} }});
}}

function toggleLabels() {{
  labelsVisible = !labelsVisible;
  allNodes.forEach(n => {{ n.label = labelsVisible ? allNodes.find(x => x.id === n.id).label : undefined; n.label = labelsVisible ? (window._origLabels || {{}})[n.id] || n.label : undefined; }});
  if (!window._origLabels) {{
    window._origLabels = {{}};
    allNodes.forEach(n => {{ window._origLabels[n.id] = n.label; }});
  }}
  drawNetwork();
  document.getElementById('labelBtn').textContent = labelsVisible ? '隐藏标签' : '显示标签';
}}

function searchNode(q) {{
  if (!network || !q.trim()) return;
  q = q.toLowerCase();
  const matches = allNodes.filter(n =>
    activeTypes.has(n.group) &&
    (n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
  );
  if (matches.length > 0) {{
    network.selectNodes([matches[0].id]);
    network.focus(matches[0].id, {{ scale: 1.5, animation: {{ duration: 500 }} }});
  }}
  updateInfo(matches.length);
}}

function updateInfo(hitCount) {{
  const visNodes = allNodes.filter(n => activeTypes.has(n.group));
  const visIds = new Set(visNodes.map(n => n.id));
  const visEdges = allEdges.filter(e => visIds.has(e.from) && visIds.has(e.to));
  let txt = `节点 ${{visNodes.length}} · 边 ${{visEdges.length}}`;
  if (hitCount !== undefined) txt += ` · 搜索命中 ${{hitCount}}`;
  document.getElementById('infoText').textContent = txt;
}}
</script>
</body>
</html>'''
    out_path = OUTPUT_DIR / "graph.html"
    out_path.write_text(graph_html, encoding="utf-8")
    print(f"关系图谱页: {out_path}")


if __name__ == "__main__":
    main()
