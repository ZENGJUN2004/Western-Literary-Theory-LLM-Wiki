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

    # 生成量化分析数据和页面
    print("\n生成量化分析数据…")
    generate_stats_data(all_pages)
    generate_stats_page()

    # 生成问答索引和页面
    print("\n生成问答索引…")
    generate_qa_index(all_pages)
    generate_qa_page()

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
    <a href="{base_href}stats.html" style="border-color:#16a34a;color:#16a34a;font-weight:600;">量化分析</a>
    <a href="{base_href}qa.html" style="border-color:#a855f7;color:#a855f7;font-weight:600;">知识问答</a>
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


def generate_stats_data(all_pages):
    """生成量化分析数据 stats-data.json"""
    from collections import Counter, defaultdict

    # 加载图谱边数据（用于中心性计算）
    graph_path = OUTPUT_DIR / "graph-data.json"
    edges = []
    if graph_path.exists():
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        edges = graph_data["edges"]

    # 节点元数据
    node_meta = {}  # slug -> {type, title, tags, nationality, lifespan, book, chapter, body_len}
    tag_counter = Counter()
    nationality_counter = Counter()
    book_counter = Counter()
    type_counter = Counter()
    body_lengths = []
    era_counter = Counter()

    wiki_link_re = re.compile(r"\[\[([^\]|]+)(?:\|([^]]+))?\]\]")

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

            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            meta = {
                "type": type_dir,
                "title": title,
                "tags": tags,
                "body_len": len(body),
            }

            for t in tags:
                tag_counter[t] += 1

            type_counter[type_dir] += 1
            body_lengths.append(len(body))

            # figures 特有
            if type_dir == "figure":
                nat = fm.get("wiki_nationality", [])
                if isinstance(nat, str):
                    nat = [n.strip() for n in nat.split(",") if n.strip()]
                if isinstance(nat, list):
                    for n in nat:
                        nationality_counter[n] += 1
                meta["nationality"] = nat if isinstance(nat, list) else []

                lifespan = fm.get("wiki_lifespan", "")
                if lifespan:
                    # 提取世纪/年代
                    m = re.search(r"(\d{4})", str(lifespan))
                    if m:
                        year = int(m.group(1))
                        century = (year // 100) + 1
                        era_label = f"{century}世纪"
                        era_counter[era_label] += 1
                        meta["era"] = era_label
                    else:
                        meta["era"] = str(lifespan)[:10]
                else:
                    meta["era"] = ""

            # summaries 特有
            if type_dir == "summary":
                book = fm.get("book", "")
                if book:
                    book_counter[book] += 1
                    meta["book"] = book
                else:
                    meta["book"] = ""

            node_meta[slug] = meta
        except Exception as e:
            pass

    # === 1. 度中心性 ===
    in_deg = Counter()
    out_deg = Counter()
    for e in edges:
        out_deg[e["from"]] += 1
        in_deg[e["to"]] += 1

    degree_list = []
    for slug, meta in node_meta.items():
        total = in_deg[slug] + out_deg[slug]
        degree_list.append({
            "slug": slug,
            "title": meta["title"],
            "type": meta["type"],
            "in": in_deg[slug],
            "out": out_deg[slug],
            "total": total,
        })
    degree_list.sort(key=lambda x: x["total"], reverse=True)

    # 孤立节点
    isolated = [d for d in degree_list if d["total"] == 0]

    # === 2. 类型间关系矩阵 ===
    type_matrix = defaultdict(lambda: defaultdict(int))
    for e in edges:
        src_type = node_meta.get(e["from"], {}).get("type", "unknown")
        tgt_type = node_meta.get(e["to"], {}).get("type", "unknown")
        type_matrix[src_type][tgt_type] += 1

    type_matrix_dict = {}
    for src in type_matrix:
        type_matrix_dict[src] = dict(type_matrix[src])

    # === 3. 页面长度分布 ===
    if body_lengths:
        max_len = max(body_lengths)
        bins = [0, 500, 1000, 2000, 3000, 5000, 8000, 12000, 20000, 50000]
        bin_labels = ["<500", "500-1k", "1k-2k", "2k-3k", "3k-5k", "5k-8k", "8k-12k", "12k-20k", "20k-50k", "50k+"]
        length_hist = [0] * len(bin_labels)
        for bl in body_lengths:
            placed = False
            for i in range(len(bins) - 1):
                if bins[i] <= bl < bins[i + 1]:
                    length_hist[i] += 1
                    placed = True
                    break
            if not placed:
                length_hist[-1] += 1
    else:
        bin_labels = []
        length_hist = []

    # === 汇总 ===
    stats = {
        "total_pages": len(node_meta),
        "total_edges": len(edges),
        "type_distribution": dict(type_counter),
        "degree_top50": degree_list[:50],
        "in_degree_top30": sorted(degree_list, key=lambda x: x["in"], reverse=True)[:30],
        "out_degree_top30": sorted(degree_list, key=lambda x: x["out"], reverse=True)[:30],
        "isolated_count": len(isolated),
        "isolated_sample": isolated[:30],
        "tag_top50": tag_counter.most_common(50),
        "nationality_distribution": nationality_counter.most_common(30),
        "era_distribution": era_counter.most_common(20),
        "book_distribution": book_counter.most_common(30),
        "type_matrix": type_matrix_dict,
        "length_histogram": {"labels": bin_labels, "data": length_hist},
        "avg_body_length": int(sum(body_lengths) / len(body_lengths)) if body_lengths else 0,
        "max_body_length": max(body_lengths) if body_lengths else 0,
        "node_meta": node_meta,
    }

    out_path = OUTPUT_DIR / "stats-data.json"
    out_path.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    print(f"量化分析数据: {len(node_meta)} 节点 → {out_path}")
    return stats


def generate_stats_page():
    """生成量化分析页面 stats.html（自然语言查询 + Chart.js 可视化）"""
    stats_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>量化分析 · 西方文论 Wiki</title>
<base href="{BASE_HREF}">
<style>
:root {{
  --bg: #fafaf8; --fg: #1a1a1a; --muted: #6b6b6b;
  --accent: #2563eb; --accent-light: #dbeafe;
  --border: #e2e2e0; --card-bg: #ffffff; --green: #16a34a; --orange: #f59e0b; --purple: #a855f7;
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
.container {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px 80px; }}
h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 6px; }}
.subtitle {{ color: var(--muted); font-size: 15px; margin-bottom: 28px; }}
.back {{ font-size: 14px; color: var(--muted); margin-bottom: 16px; display: inline-block; }}

.query-box {{
  display: flex; gap: 8px; margin-bottom: 16px;
}}
.query-box input {{
  flex: 1; padding: 12px 16px; border: 2px solid var(--border); border-radius: 10px;
  background: var(--card-bg); color: var(--fg); font-size: 16px; outline: none; transition: border-color 0.2s;
}}
.query-box input:focus {{ border-color: var(--accent); }}
.query-box button {{
  padding: 12px 24px; border: none; border-radius: 10px; background: var(--accent); color: #fff;
  font-size: 15px; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
}}
.query-box button:hover {{ opacity: 0.9; }}

.suggestions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 32px; }}
.sug-chip {{
  padding: 6px 14px; border: 1px solid var(--border); border-radius: 20px;
  font-size: 13px; cursor: pointer; transition: all 0.2s; color: var(--fg); background: var(--card-bg);
}}
.sug-chip:hover {{ border-color: var(--accent); color: var(--accent); background: var(--accent-light); }}

.result-header {{
  display: flex; align-items: baseline; gap: 12px; margin-bottom: 16px;
}}
.result-title {{ font-size: 20px; font-weight: 600; }}
.result-desc {{ font-size: 14px; color: var(--muted); }}

.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 32px; }}
.card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 18px; text-align: center; }}
.card-num {{ font-size: 30px; font-weight: 700; color: var(--accent); }}
.card-label {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}

.chart-wrap {{
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; margin-bottom: 24px;
}}
.chart-wrap h3 {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; }}
.chart-container {{ position: relative; height: 380px; }}

.matrix-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.matrix-table th, .matrix-table td {{
  border: 1px solid var(--border); padding: 6px 10px; text-align: center;
}}
.matrix-table th {{ background: var(--accent-light); color: var(--accent); font-weight: 600; }}
.matrix-table td {{ color: var(--muted); }}
.matrix-table td.hot {{ color: var(--fg); font-weight: 600; }}

.rank-list {{ list-style: none; }}
.rank-list li {{
  display: flex; align-items: center; gap: 12px; padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}}
.rank-list li:last-child {{ border-bottom: none; }}
.rank-num {{ font-size: 13px; color: var(--muted); width: 28px; }}
.rank-title {{ flex: 1; }}
.rank-title a {{ color: var(--fg); }}
.rank-title a:hover {{ color: var(--accent); }}
.rank-bar {{ flex: 0 0 120px; height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; }}
.rank-bar-inner {{ height: 100%; background: var(--accent); border-radius: 4px; }}
.rank-val {{ font-size: 13px; color: var(--muted); width: 40px; text-align: right; }}
.rank-type {{ font-size: 11px; padding: 1px 8px; border-radius: 10px; background: var(--accent-light); color: var(--accent); }}

.empty {{ text-align: center; padding: 60px 20px; color: var(--muted); }}
.loading {{ text-align: center; padding: 40px; color: var(--muted); }}
</style>
</head>
<body>
<div class="container">
  <a class="back" href="{BASE_HREF}">← 返回首页</a>
  <h1>量化分析</h1>
  <p class="subtitle">用自然语言提问，自动生成图表 · 数据来源：wiki 页面与关系网络</p>

  <div class="query-box">
    <input id="q" type="text" placeholder="例如：谁连接度最高？有多少美国文论家？哪些标签最热门？" onkeydown="if(event.key==='Enter')doQuery()">
    <button onclick="doQuery()">分析</button>
  </div>

  <div class="suggestions" id="suggestions"></div>

  <div id="results"></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const BASE = "{BASE_HREF}";
const TYPE_LABELS = {{ figure:"人物", concept:"概念", movement:"流派", work:"原典",
  summary:"摘要", comparison:"对比", overview:"谱系", synthesis:"综合" }};
const TYPE_COLORS = {{
  figure: "#ef4444", concept: "#2563eb", movement: "#16a34a", work: "#a855f7",
  summary: "#f59e0b", comparison: "#06b6d4", overview: "#ec4899", synthesis: "#6b7280",
}};

let STATS = null;
let currentChart = null;

const SUGGESTIONS = [
  "整体概况",
  "谁连接度最高？",
  "哪些概念被引用最多？",
  "各类型页面数量",
  "最热门的标签",
  "文论家来自哪些国家？",
  "各世纪文论家分布",
  "哪些教材贡献最多？",
  "哪些页面没有连接？",
  "页面内容长度分布",
  "类型间关系矩阵",
];

function renderSuggestions() {{
  const c = document.getElementById('suggestions');
  c.innerHTML = SUGGESTIONS.map(s =>
    `<span class="sug-chip" onclick="document.getElementById('q').value='${{s}}';doQuery()">${{s}}</span>`
  ).join('');
}}

fetch(BASE + 'stats-data.json')
  .then(r => r.json())
  .then(data => {{ STATS = data; renderSuggestions(); }})
  .catch(e => {{ document.getElementById('results').innerHTML = '<div class="empty">数据加载失败</div>'; }});

function doQuery() {{
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  if (!STATS) {{ document.getElementById('results').innerHTML = '<div class="loading">数据加载中…</div>'; return; }}
  const intent = classify(q);
  renderResult(intent, q);
}}

function classify(q) {{
  const ql = q.toLowerCase();
  // 国别
  if (/国别|国家|来自|美国|德国|法国|英国|俄国|苏联|中国|日本|意大利|国别|国籍/.test(q)) return 'nationality';
  // 时期/世纪
  if (/世纪|时期|年代|时代|20世纪|19世纪|18世纪|古典/.test(q)) return 'era';
  // 教材/来源
  if (/教材|来源|贡献|哪本书|原书|章节|书目/.test(q)) return 'book';
  // 孤立
  if (/孤立|没有连接|孤岛|未连接|无连接|断开/.test(q)) return 'isolated';
  // 长度/体量
  if (/长度|字数|体量|内容量|篇幅|多少字/.test(q)) return 'length';
  // 关系矩阵
  if (/关系矩阵|类型间|跨类型|关联矩阵|互联/.test(q)) return 'matrix';
  // 连接度/中心性/重要
  if (/连接度|中心性|最重要|核心|影响力|度中心|枢纽|关键节点/.test(q)) return 'degree';
  // 被引用/入度
  if (/被引用|被提及|被链接|入度|指向/.test(q)) return 'in_degree';
  // 出度/引用
  if (/引用了|链接了|出度|指向了/.test(q)) return 'out_degree';
  // 标签/关键词
  if (/标签|关键词|热门|高频|词频/.test(q)) return 'tags';
  // 类型分布/数量
  if (/类型|各类|多少个|数量|分布|统计|多少/.test(q)) return 'type_dist';
  // 概览
  if (/概览|总览|概况|整体|全貌|汇总|总览/.test(q)) return 'overview';
  // 默认：概览
  return 'overview';
}}

function destroyChart() {{
  if (currentChart) {{ currentChart.destroy(); currentChart = null; }}
}}

function makeChart(ctx, cfg) {{
  destroyChart();
  const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  Chart.defaults.color = dark ? '#999' : '#6b6b6b';
  Chart.defaults.borderColor = dark ? '#333' : '#e2e2e0';
  currentChart = new Chart(ctx, cfg);
}}

function renderResult(intent, q) {{
  const r = document.getElementById('results');
  let html = '';

  switch(intent) {{
    case 'overview':
      html = renderOverview();
      break;
    case 'degree':
      html = renderDegree('total');
      break;
    case 'in_degree':
      html = renderDegree('in');
      break;
    case 'out_degree':
      html = renderDegree('out');
      break;
    case 'type_dist':
      html = renderTypeDist();
      break;
    case 'tags':
      html = renderTags();
      break;
    case 'nationality':
      html = renderNationality();
      break;
    case 'era':
      html = renderEra();
      break;
    case 'book':
      html = renderBook();
      break;
    case 'isolated':
      html = renderIsolated();
      break;
    case 'length':
      html = renderLength();
      break;
    case 'matrix':
      html = renderMatrix();
      break;
  }}
  r.innerHTML = html;
  if (typeof drawChart === 'function' && window._pendingChart) {{
    drawChart(window._pendingChart);
    window._pendingChart = null;
  }}
}}

function renderOverview() {{
  const s = STATS;
  return `
    <div class="result-header"><span class="result-title">整体概况</span><span class="result-desc">知识库宏观统计</span></div>
    <div class="cards">
      <div class="card"><div class="card-num">${{s.total_pages}}</div><div class="card-label">页面总数</div></div>
      <div class="card"><div class="card-num">${{s.total_edges}}</div><div class="card-label">关系链接</div></div>
      <div class="card"><div class="card-num">${{Object.keys(s.type_distribution).length}}</div><div class="card-label">内容类型</div></div>
      <div class="card"><div class="card-num">${{s.tag_top50.length > 0 ? s.tag_top50.length : 0}}</div><div class="card-label">标签种类</div></div>
      <div class="card"><div class="card-num">${{s.isolated_count}}</div><div class="card-label">孤立节点</div></div>
      <div class="card"><div class="card-num">${{(s.avg_body_length/1000).toFixed(1)}}k</div><div class="card-label">平均字数</div></div>
    </div>
    <div class="chart-wrap"><h3>各类型页面数量</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
    <div class="chart-wrap"><h3>页面内容长度分布</h3><div class="chart-container"><canvas id="cv2"></canvas></div></div>
  `;
}}

function renderDegree(metric) {{
  const labels = {{ total: '总连接度', in: '被引用数（入度）', out: '引用数（出度）' }};
  const dataKey = metric === 'total' ? 'degree_top50' : (metric === 'in' ? 'in_degree_top30' : 'out_degree_top30');
  const items = STATS[dataKey].slice(0, 20);
  return `
    <div class="result-header"><span class="result-title">${{labels[metric]}} Top 20</span><span class="result-desc">基于 wiki 页面间的 [[链接]] 关系计算</span></div>
    <div class="chart-wrap"><h3>${{labels[metric]}} 排名</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
    <div class="chart-wrap"><h3>详细列表</h3>
      <ul class="rank-list">${{items.map((d, i) => {{
        const pct = (d[metric] / items[0][metric] * 100).toFixed(0);
        return `<li>
          <span class="rank-num">${{i+1}}</span>
          <span class="rank-type">${{TYPE_LABELS[d.type] || d.type}}</span>
          <span class="rank-title"><a href="${{BASE}}${{d.slug}}.html">${{d.title}}</a></span>
          <div class="rank-bar"><div class="rank-bar-inner" style="width:${{pct}}%"></div></div>
          <span class="rank-val">${{d[metric]}}</span>
        </li>`;
      }}).join('')}}</ul>
    </div>
  `;
}}

function renderTypeDist() {{
  return `
    <div class="result-header"><span class="result-title">各类型页面数量</span><span class="result-desc">按内容类型统计</span></div>
    <div class="chart-wrap"><h3>类型分布</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
  `;
}}

function renderTags() {{
  const items = STATS.tag_top50.slice(0, 25);
  return `
    <div class="result-header"><span class="result-title">热门标签 Top 25</span><span class="result-desc">基于页面 frontmatter 中的 tags 字段</span></div>
    <div class="chart-wrap"><h3>标签频次</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
  `;
}}

function renderNationality() {{
  const items = STATS.nationality_distribution;
  return `
    <div class="result-header"><span class="result-title">文论家国别分布</span><span class="result-desc">基于人物页面的 wiki_nationality 字段</span></div>
    <div class="chart-wrap"><h3>国别占比</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
  `;
}}

function renderEra() {{
  const items = STATS.era_distribution;
  return `
    <div class="result-header"><span class="result-title">文论家世纪分布</span><span class="result-desc">基于人物页面的 wiki_lifespan 字段</span></div>
    <div class="chart-wrap"><h3>各世纪文论家数量</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
  `;
}}

function renderBook() {{
  const items = STATS.book_distribution.slice(0, 20);
  return `
    <div class="result-header"><span class="result-title">教材/原典贡献 Top 20</span><span class="result-desc">基于摘要页面的 book 字段</span></div>
    <div class="chart-wrap"><h3>各教材摘要数量</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
  `;
}}

function renderIsolated() {{
  const items = STATS.isolated_sample;
  return `
    <div class="result-header"><span class="result-title">孤立节点</span><span class="result-desc">共 ${{STATS.isolated_count}} 个页面没有任何 wiki 链接（入度+出度=0）</span></div>
    <div class="chart-wrap">
      <ul class="rank-list">${{items.map((d, i) => `
        <li>
          <span class="rank-num">${{i+1}}</span>
          <span class="rank-type">${{TYPE_LABELS[d.type] || d.type}}</span>
          <span class="rank-title"><a href="${{BASE}}${{d.slug}}.html">${{d.title}}</a></span>
          <span class="rank-val" style="color:var(--orange)">0</span>
        </li>`).join('')}}</ul>
    </div>
  `;
}}

function renderLength() {{
  return `
    <div class="result-header"><span class="result-title">页面内容长度分布</span><span class="result-desc">平均 ${{(STATS.avg_body_length/1000).toFixed(1)}}k 字，最长 ${{(STATS.max_body_length/1000).toFixed(1)}}k 字</span></div>
    <div class="chart-wrap"><h3>字数区间分布</h3><div class="chart-container"><canvas id="cv1"></canvas></div></div>
  `;
}}

function renderMatrix() {{
  const types = Object.keys(STATS.type_matrix);
  let header = '<th>→</th>';
  types.forEach(t => {{ header += `<th>${{TYPE_LABELS[t] || t}}</th>`; }});
  let rows = '';
  types.forEach(src => {{
    let row = `<th>${{TYPE_LABELS[src] || src}}</th>`;
    types.forEach(tgt => {{
      const v = (STATS.type_matrix[src] || {{}})[tgt] || 0;
      const cls = v > 0 ? 'hot' : '';
      row += `<td class="${{cls}}">${{v || ''}}</td>`;
    }});
    rows += `<tr>${{row}}</tr>`;
  }});
  return `
    <div class="result-header"><span class="result-title">类型间关系矩阵</span><span class="result-desc">行=引用方，列=被引用方，数值=wiki 链接数</span></div>
    <div class="chart-wrap">
      <table class="matrix-table"><thead><tr>${{header}}</tr></thead><tbody>${{rows}}</tbody></table>
    </div>
  `;
}}

// 图表绘制
function drawChart(type) {{
  const ctx = document.getElementById('cv1');
  if (!ctx) return;
  const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;

  if (type === 'degree') {{
    const items = STATS.degree_top50.slice(0, 20).reverse();
    makeChart(ctx, {{
      type: 'bar',
      data: {{
        labels: items.map(d => d.title),
        datasets: [{{ label: '总连接度', data: items.map(d => d.total),
          backgroundColor: items.map(d => TYPE_COLORS[d.type] || '#6b7280') }}]
      }},
      options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ beginAtZero: true }}, y: {{ ticks: {{ font: {{ size: 11 }} }} }} }} }}
    }});
  }} else if (type === 'type_dist') {{
    const td = STATS.type_distribution;
    const labels = Object.keys(td).map(t => TYPE_LABELS[t] || t);
    makeChart(ctx, {{
      type: 'doughnut',
      data: {{ labels, datasets: [{{ data: Object.values(td),
        backgroundColor: Object.keys(td).map(t => TYPE_COLORS[t] || '#6b7280') }}] }},
      options: {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'right' }} }} }}
    }});
  }} else if (type === 'tags') {{
    const items = STATS.tag_top50.slice(0, 25).reverse();
    makeChart(ctx, {{
      type: 'bar',
      data: {{ labels: items.map(d => d[0]), datasets: [{{ label: '频次', data: items.map(d => d[1]), backgroundColor: '#2563eb' }}] }},
      options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ beginAtZero: true }} }} }}
    }});
  }} else if (type === 'nationality') {{
    const items = STATS.nationality_distribution;
    makeChart(ctx, {{
      type: 'pie',
      data: {{ labels: items.map(d => d[0]), datasets: [{{ data: items.map(d => d[1]),
        backgroundColor: ['#ef4444','#2563eb','#16a34a','#a855f7','#f59e0b','#06b6d4','#ec4899','#6b7280','#f43f5e','#84cc16'] }}] }},
      options: {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'right' }} }} }}
    }});
  }} else if (type === 'era') {{
    const items = STATS.era_distribution;
    makeChart(ctx, {{
      type: 'bar',
      data: {{ labels: items.map(d => d[0]), datasets: [{{ label: '文论家数', data: items.map(d => d[1]), backgroundColor: '#16a34a' }}] }},
      options: {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ y: {{ beginAtZero: true }} }} }}
    }});
  }} else if (type === 'book') {{
    const items = STATS.book_distribution.slice(0, 20).reverse();
    makeChart(ctx, {{
      type: 'bar',
      data: {{ labels: items.map(d => d[0]), datasets: [{{ label: '摘要数', data: items.map(d => d[1]), backgroundColor: '#a855f7' }}] }},
      options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ beginAtZero: true }}, y: {{ ticks: {{ font: {{ size: 10 }} }} }} }} }}
    }});
  }} else if (type === 'length') {{
    const h = STATS.length_histogram;
    makeChart(ctx, {{
      type: 'bar',
      data: {{ labels: h.labels, datasets: [{{ label: '页面数', data: h.data, backgroundColor: '#f59e0b' }}] }},
      options: {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ y: {{ beginAtZero: true }} }} }}
    }});
  }}
}}

// 概览页面需要两个图表
function drawOverviewCharts() {{
  // cv1: 类型分布
  const ctx1 = document.getElementById('cv1');
  if (ctx1) {{
    const td = STATS.type_distribution;
    const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    Chart.defaults.color = dark ? '#999' : '#6b6b6b';
    Chart.defaults.borderColor = dark ? '#333' : '#e2e2e0';
    currentChart = new Chart(ctx1, {{
      type: 'bar',
      data: {{ labels: Object.keys(td).map(t => TYPE_LABELS[t] || t),
        datasets: [{{ label: '页面数', data: Object.values(td),
          backgroundColor: Object.keys(td).map(t => TYPE_COLORS[t] || '#6b7280') }}] }},
      options: {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ y: {{ beginAtZero: true }} }} }}
    }});
  }}
  // cv2: 长度分布
  const ctx2 = document.getElementById('cv2');
  if (ctx2) {{
    const h = STATS.length_histogram;
    new Chart(ctx2, {{
      type: 'bar',
      data: {{ labels: h.labels, datasets: [{{ label: '页面数', data: h.data, backgroundColor: '#f59e0b' }}] }},
      options: {{ responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ y: {{ beginAtZero: true }} }} }}
    }});
  }}
}}

// 覆盖 renderResult 中的图表调用
const _origRenderResult = renderResult;
renderResult = function(intent, q) {{
  _origRenderResult(intent, q);
  // 延迟绘制图表（等 DOM 更新）
  setTimeout(() => {{
    if (intent === 'overview') drawOverviewCharts();
    else {{
      const chartMap = {{
        degree: 'degree', in_degree: 'degree', out_degree: 'degree',
        type_dist: 'type_dist', tags: 'tags', nationality: 'nationality',
        era: 'era', book: 'book', length: 'length',
      }};
      if (chartMap[intent]) drawChart(chartMap[intent]);
    }}
  }}, 50);
}};
</script>
</body>
</html>'''
    out_path = OUTPUT_DIR / "stats.html"
    out_path.write_text(stats_html, encoding="utf-8")
    print(f"量化分析页: {out_path}")


def generate_qa_index(all_pages):
    """生成问答检索索引 qa-index.json（句子分割 + 预算倒排索引）"""
    from collections import Counter

    def extract_terms(text):
        """提取中文 2-gram/3-gram + 英文单词"""
        terms = []
        for w in re.findall(r"[a-zA-Z]{2,}", text):
            terms.append(w.lower())
        cn = re.sub(r"[^\u4e00-\u9fa5]", "", text)
        for i in range(len(cn) - 1):
            terms.append(cn[i:i+2])
            if i < len(cn) - 2:
                terms.append(cn[i:i+3])
        return terms

    qa_docs = []
    df = {}  # document frequency
    doc_tf = []  # 每个文档的 term frequency
    total_len = 0

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

            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            # 清理 markdown 标记
            clean_body = body
            clean_body = re.sub(r"\[\[([^\]|]+)(?:\|([^]]+))?\]\]", r"\2|\1", clean_body)
            clean_body = re.sub(r"^#+\s+", "", clean_body, flags=re.MULTILINE)
            clean_body = re.sub(r"\*\*(.+?)\*\*", r"\1", clean_body)
            clean_body = re.sub(r"\*(.+?)\*", r"\1", clean_body)
            clean_body = re.sub(r"`(.+?)`", r"\1", clean_body)
            clean_body = re.sub(r"^>\s*", "", clean_body, flags=re.MULTILINE)
            clean_body = re.sub(r"^-\s+", "", clean_body, flags=re.MULTILINE)
            clean_body = re.sub(r"^\d+\.\s+", "", clean_body, flags=re.MULTILINE)
            clean_body = re.sub(r"\[\[.*?\]\]", "", clean_body)
            clean_body = re.sub(r"^---.*$", "", clean_body, flags=re.MULTILINE)

            # 按句子分割
            sentences = re.split(r"[。\n！？；]", clean_body)
            sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 8]

            doc_len = len(clean_body)
            total_len += doc_len

            qa_docs.append({
                "slug": slug,
                "title": title,
                "type": type_dir,
                "tags": tags,
                "sentences": sentences,
                "len": doc_len,
            })
        except Exception:
            pass

    avg_len = total_len / len(qa_docs) if qa_docs else 1

    # 输出（不包含 df，查询时用 indexOf 即可）
    qa_data = {
        "docs": qa_docs,
        "avg_len": avg_len,
        "total_docs": len(qa_docs),
    }

    out_path = OUTPUT_DIR / "qa-index.json"
    out_path.write_text(json.dumps(qa_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"问答索引: {len(qa_docs)} 文档, {total_len} 字 → {out_path}")
    return qa_data


def generate_qa_page():
    """生成问答页面 qa.html（BM25 检索 + 段落提取）"""
    qa_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>知识问答 · 西方文论 Wiki</title>
<base href="{BASE_HREF}">
<style>
:root {{
  --bg: #fafaf8; --fg: #1a1a1a; --muted: #6b6b6b;
  --accent: #2563eb; --accent-light: #dbeafe;
  --border: #e2e2e0; --card-bg: #ffffff;
  --highlight: #fde68a;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1a1a1a; --fg: #e8e8e6; --muted: #999;
    --accent: #60a5fa; --accent-light: #1e3a5f;
    --border: #333; --card-bg: #222;
    --highlight: #92710a;
  }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, "Noto Serif SC", Georgia, serif; background: var(--bg); color: var(--fg); line-height: 1.7; }}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.container {{ max-width: 860px; margin: 0 auto; padding: 40px 24px 80px; }}
h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 6px; }}
.subtitle {{ color: var(--muted); font-size: 15px; margin-bottom: 28px; }}
.back {{ font-size: 14px; color: var(--muted); margin-bottom: 16px; display: inline-block; }}

.query-box {{ display: flex; gap: 8px; margin-bottom: 16px; }}
.query-box input {{
  flex: 1; padding: 14px 18px; border: 2px solid var(--border); border-radius: 12px;
  background: var(--card-bg); color: var(--fg); font-size: 17px; outline: none; transition: border-color 0.2s;
}}
.query-box input:focus {{ border-color: var(--accent); }}
.query-box button {{
  padding: 14px 28px; border: none; border-radius: 12px; background: var(--accent); color: #fff;
  font-size: 16px; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
}}
.query-box button:hover {{ opacity: 0.9; }}

.suggestions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 28px; }}
.sug-chip {{
  padding: 6px 14px; border: 1px solid var(--border); border-radius: 20px;
  font-size: 13px; cursor: pointer; transition: all 0.2s; color: var(--fg); background: var(--card-bg);
}}
.sug-chip:hover {{ border-color: var(--accent); color: var(--accent); background: var(--accent-light); }}

.answer-section {{
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; margin-bottom: 16px;
}}
.answer-section h3 {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; color: var(--accent); }}

.answer-passage {{
  padding: 16px 18px; border-left: 3px solid var(--accent); margin-bottom: 14px;
  background: var(--bg); border-radius: 0 8px 8px 0; font-size: 15px; line-height: 1.8;
}}
.answer-passage .source {{
  margin-top: 10px; font-size: 13px; color: var(--muted);
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}}
.answer-passage .source .type-tag {{
  padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600;
  background: var(--accent-light); color: var(--accent);
}}
.answer-passage .score {{
  font-size: 12px; color: var(--muted); margin-left: auto;
}}
.hl {{ background: var(--highlight); padding: 0 2px; border-radius: 3px; }}

.no-result {{ text-align: center; padding: 60px 20px; color: var(--muted); font-size: 16px; }}
.loading {{ text-align: center; padding: 40px; color: var(--muted); }}

.related-pages {{ margin-top: 12px; }}
.related-pages a {{
  display: inline-block; margin: 4px 6px 4px 0; padding: 4px 12px;
  border: 1px solid var(--border); border-radius: 6px; font-size: 13px; color: var(--fg);
}}
.related-pages a:hover {{ border-color: var(--accent); color: var(--accent); }}

.status-bar {{
  font-size: 13px; color: var(--muted); margin-bottom: 16px; padding: 0 4px;
}}

.context-expand {{
  margin-top: 8px; font-size: 13px; color: var(--accent); cursor: pointer;
  user-select: none;
}}
.context-expand:hover {{ text-decoration: underline; }}
.context-body {{
  display: none; margin-top: 8px; padding: 12px; background: var(--bg); border-radius: 8px;
  font-size: 14px; color: var(--muted); line-height: 1.6;
}}
.context-body.show {{ display: block; }}
</style>
</head>
<body>
<div class="container">
  <a class="back" href="{BASE_HREF}">← 返回首页</a>
  <h1>知识问答</h1>
  <p class="subtitle">用自然语言提问，自动从知识库 1381 个页面中检索最相关答案</p>

  <div class="query-box">
    <input id="q" type="text" placeholder="例如：什么是互文性？弗洛伊德的精神分析批评如何影响文论？" onkeydown="if(event.key==='Enter')doAsk()">
    <button onclick="doAsk()">提问</button>
  </div>

  <div class="suggestions" id="suggestions"></div>
  <div id="status"></div>
  <div id="results"></div>
</div>

<script>
const BASE = "{BASE_HREF}";
const TYPE_LABELS = {{
  figure:"人物", concept:"概念", movement:"流派", work:"原典",
  summary:"摘要", comparison:"对比", overview:"谱系", synthesis:"综合"
}};

let DOCS = [];
let AVG_LEN = 1;
let TOTAL_DOCS = 0;

const STOP_WORDS = new Set([
  "的","了","是","在","和","与","或","也","都","就","还","又","把","被","让","使","对","为","以","于","从","到","向","由","按","据","说","着","过","起","来","去","上","下","中","里","外","前","后","间","侧","们","这","那","些","某","其","此","该","它","他","她","你","我","什么","怎么","如何","为什么","哪些","哪个","请","帮","给","关于","对于","请问","一下"
]);

const SUGGESTIONS = [
  "什么是互文性？",
  "什么是结构主义？",
  "弗洛伊德的精神分析批评如何影响文论？",
  "马克思对文论有什么贡献？",
  "新批评的核心观点是什么？",
  "什么是三一律？",
  "后结构主义有哪些代表人物？",
  "解释学的发展历程？",
  "什么是作者之死？",
  "女性主义批评的主要观点？",
];

function renderSuggestions() {{
  const c = document.getElementById('suggestions');
  c.innerHTML = SUGGESTIONS.map(s =>
    `<span class="sug-chip" onclick="document.getElementById('q').value='${{s.replace(/'/g,"\\'")}}';doAsk()">${{s}}</span>`
  ).join('');
}}

// 加载问答索引（无 DF，查询时用 indexOf 即可）
document.getElementById('status').innerHTML = '<div class="loading">正在加载知识库…</div>';
const loadStart = performance.now();
fetch(BASE + 'qa-index.json')
  .then(r => r.json())
  .then(data => {{
    DOCS = data.docs;
    AVG_LEN = data.avg_len;
    TOTAL_DOCS = data.total_docs;
    const loadTime = ((performance.now() - loadStart) / 1000).toFixed(1);
    document.getElementById('status').innerHTML = '<div class="status-bar">知识库已就绪 · ' + TOTAL_DOCS + ' 页面 · 加载耗时 ' + loadTime + 's</div>';
    renderSuggestions();
    document.getElementById('q').focus();
  }})
  .catch(e => {{
    document.getElementById('status').innerHTML = '<div class="no-result">知识库加载失败</div>';
  }});

// 提取关键词（2-4字汉字组 + 英文单词）
function extractTerms(text) {{
  const terms = [];
  // 提取英文单词
  const enWords = text.match(/[a-zA-Z]{{2,}}/g);
  if (enWords) terms.push(...enWords.map(w => w.toLowerCase()));
  // 提取中文 2-gram, 3-gram
  const cnChars = text.replace(/[^\u4e00-\u9fa5]/g, "");
  for (let i = 0; i < cnChars.length - 1; i++) {{
    terms.push(cnChars.substr(i, 2));
    if (i < cnChars.length - 2) {{
      terms.push(cnChars.substr(i, 3));
    }}
  }}
  return terms;
}}

// 从问题中提取查询词
function extractQueryTerms(query) {{
  // 去掉停用词
  const words = query.replace(/[^\u4e00-\u9fa5a-zA-Z0-9？？]/g, " ").trim().split(/\s+/);
  const filtered = words.filter(w => w.length > 1 && !STOP_WORDS.has(w));
  // 重新组合并提取 n-gram
  const text = filtered.join("");
  const terms = extractTerms(text);
  // 对英文词也要过滤停用词
  return terms;
}}

// 计算查询词的 DF（文档频率）——仅需遍历文档一次
function computeDF(queryTerms) {{
  const df = {{}};
  queryTerms.forEach(t => df[t] = 0);
  DOCS.forEach(doc => {{
    const docLower = (doc.title + " " + (doc.sentences || []).join(" ")).toLowerCase();
    queryTerms.forEach(qt => {{
      if (docLower.indexOf(qt) >= 0) df[qt]++;
    }});
  }});
  return df;
}}

// BM25 评分（使用 indexOf 匹配）
function bm25Score(queryTerms, df, doc) {{
  const k1 = 1.5, b = 0.75;
  let score = 0;

  const docText = doc.title + " " + (doc.sentences || []).join(" ");
  const docLower = docText.toLowerCase();
  const titleLower = doc.title.toLowerCase();
  const tagText = (doc.tags || []).join(" ").toLowerCase();

  const dl = doc.len || 1;

  const seen = new Set();
  queryTerms.forEach(qt => {{
    if (seen.has(qt)) return;
    seen.add(qt);

    const df_val = df[qt] || 0;
    if (df_val === 0) return;

    let f = 0;
    let pos = docLower.indexOf(qt);
    while (pos >= 0) {{ f++; pos = docLower.indexOf(qt, pos + qt.length); }}

    let titleF = 0;
    pos = titleLower.indexOf(qt);
    while (pos >= 0) {{ titleF++; pos = titleLower.indexOf(qt, pos + qt.length); }}

    let tagF = 0;
    pos = tagText.indexOf(qt);
    while (pos >= 0) {{ tagF++; pos = tagText.indexOf(qt, pos + qt.length); }}

    if (f === 0 && titleF === 0 && tagF === 0) return;

    const idf = Math.log((TOTAL_DOCS - df_val + 0.5) / (df_val + 0.5) + 1);
    const combinedF = f + 3 * titleF + 2 * tagF;
    const tfNorm = (combinedF * (k1 + 1)) / (combinedF + k1 * (1 - b + b * dl / AVG_LEN));
    score += idf * tfNorm;
  }});

  return score;
}}

// 从文档中提取最相关句子
function extractRelevantSentences(queryTerms, doc, maxSentences) {{
  const sentences = doc.sentences || [];
  const scored = sentences.map(s => {{
    let sScore = 0;
    const sLower = s.toLowerCase();
    queryTerms.forEach(qt => {{
      if (sLower.includes(qt.toLowerCase())) {{
        // 长词权重高
        sScore += qt.length >= 3 ? 3 : 1;
      }}
    }});
    return {{ text: s, score: sScore, idx: sentences.indexOf(s) }};
  }}).filter(s => s.score > 0);

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, maxSentences);
}}

// 高亮关键词（避免正则转义问题，使用 split/join）
function highlight(text, terms) {{
  let result = text;
  const sortedTerms = [...new Set(terms)].sort((a, b) => b.length - a.length);
  sortedTerms.forEach(t => {{
    if (t.length < 2) return;
    const lower = result.toLowerCase();
    const tLower = t.toLowerCase();
    let idx = lower.indexOf(tLower);
    while (idx >= 0) {{
      const before = result.substring(0, idx);
      const match = result.substring(idx, idx + t.length);
      const after = result.substring(idx + t.length);
      result = before + '<span class="hl">' + match + '</span>' + after;
      idx = (before + '<span class="hl">' + match + '</span>' + after).toLowerCase().indexOf(tLower, idx + 25 + t.length);
    }}
  }});
  return result;
}}

function doAsk() {{
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  if (DOCS.length === 0) {{
    document.getElementById('results').innerHTML = '<div class="loading">知识库加载中…</div>';
    return;
  }}

  const queryTerms = extractQueryTerms(q);
  if (queryTerms.length === 0) {{
    document.getElementById('results').innerHTML = '<div class="no-result">请输入更具体的问题</div>';
    return;
  }}

  // BM25 检索
  const queryStart = performance.now();
  const df = computeDF(queryTerms);
  const scored = DOCS.map(doc => ({{
    doc,
    score: bm25Score(queryTerms, df, doc),
  }})).filter(d => d.score > 0);

  scored.sort((a, b) => b.score - a.score);

  const topDocs = scored.slice(0, 5);
  const queryTime = ((performance.now() - queryStart) / 1000).toFixed(2);
  const status = document.getElementById('status');
  status.innerHTML = `<div class="status-bar">检索到 ${{scored.length}} 个相关页面 · 耗时 ${{queryTime}}s · 展示 Top ${{topDocs.length}}</div>`;

  const results = document.getElementById('results');
  if (topDocs.length === 0) {{
    results.innerHTML = '<div class="no-result">未找到相关内容，请换一种提问方式试试</div>';
    return;
  }}

  let html = '';
  topDocs.forEach((item, i) => {{
    const doc = item.doc;
    const sents = extractRelevantSentences(queryTerms, doc, 3);

    // 构建答案段落
    let passageHtml = '';
    sents.forEach(s => {{
      passageHtml += `<div class="answer-passage">${{highlight(s.text, queryTerms)}}
        <div class="source">
          <span class="type-tag">${{TYPE_LABELS[doc.type] || doc.type}}</span>
          <a href="${{BASE}}${{doc.slug}}.html">${{doc.title}}</a>
          <span class="score">相关度 ${{item.score.toFixed(2)}} · 句子匹配 ${{s.score}}</span>
        </div>
      </div>`;
    }});

    // 上下文展开
    if (sents.length > 0) {{
      const ctxIdx = sents[0].idx;
      const ctxBefore = (doc.sentences[ctxIdx - 1] || "").trim();
      const ctxAfter = (doc.sentences[ctxIdx + 1] || "").trim();
      let ctxParts = '';
      if (ctxBefore) ctxParts += `<div>… ${{highlight(ctxBefore, queryTerms)}}</div>`;
      ctxParts += `<div style="color:var(--muted);margin:4px 0">[ 以上为提取的关键段落 ]</div>`;
      if (ctxAfter) ctxParts += `<div>… ${{highlight(ctxAfter, queryTerms)}}</div>`;
      passageHtml += `<div class="context-expand" onclick="this.nextElementSibling.classList.toggle('show')">展开上下文 ▸</div><div class="context-body">${{ctxParts}}</div>`;
    }}

    // 相关页面链接
    const relatedLinks = scored.slice(i + 1, i + 4).map(r =>
      `<a href="${{BASE}}${{r.doc.slug}}.html">${{r.doc.title}}</a>`
    ).join('');
    if (relatedLinks) {{
      passageHtml += `<div class="related-pages"><span style="color:var(--muted);font-size:13px">相关页面：</span>${{relatedLinks}}</div>`;
    }}

    html += `<div class="answer-section">
      <h3>答案 ${{i + 1}} · ${{doc.title}}</h3>
      ${{passageHtml}}
    </div>`;
  }});

  results.innerHTML = html;
}}
</script>
</body>
</html>'''
    out_path = OUTPUT_DIR / "qa.html"
    out_path.write_text(qa_html, encoding="utf-8")
    print(f"问答页: {out_path}")


if __name__ == "__main__":
    main()
