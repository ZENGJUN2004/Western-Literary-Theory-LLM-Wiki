"""
Wiki Fill — 从维基百科提取结构化数据并回填 figures 页
用法：python wiki_fill.py [--dry-run] [--limit N] [--page FILE]
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

KB_ROOT = Path(__file__).parent / "kb" / "wiki" / "figures"
LOG_FILE = Path(__file__).parent / "kb" / "wiki" / "_log.md"

WIKI_ZH = "https://zh.wikipedia.org/w/api.php"
WIKI_EN = "https://en.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "WikiFill/1.0 (western-literary-theory-kb; contact: kb-maintainer@localhost)"
}


def parse_frontmatter(path: Path) -> tuple[dict, str, str]:
    """解析 frontmatter，返回 (fm_dict, body, raw_path)"""
    content = path.read_text(encoding="utf-8")
    if content.startswith("\ufeff"):
        content = content[1:]
    m = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not m:
        return {}, content, ""
    body = m.group(2)
    fm_raw = m.group(1)
    fm = {}
    list_key = None
    for line in fm_raw.splitlines():
        kv = line.split(":", 1)
        if len(kv) == 2:
            k, v = kv[0].strip(), kv[1].strip()
            if v == "":
                # 块状列表开始（后续 "- item" 行归属该键）
                list_key = k
                fm[k] = []
            elif v.startswith("[") and v.endswith("]"):
                items = v[1:-1].split(",")
                fm[k] = [x.strip().strip('"').strip("'") for x in items if x.strip()]
                list_key = None
            else:
                fm[k] = v.strip().strip('"').strip("'")
                list_key = None
        else:
            m2 = re.match(r"^\s*-\s+(.+)$", line)
            if m2 and list_key and list_key in fm:
                fm[list_key].append(m2.group(1).strip())
    return fm, body, content


def rebuild_frontmatter(fm: dict, raw_content: str) -> str:
    """重建 frontmatter 字符串"""
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            if not v:
                continue  # 空列表不写出，保持 frontmatter 简洁
            lines.append(f"{k}: [{', '.join(f'\"{x}\"' for x in v)}]")
        else:
            lines.append(f"{k}: \"{v}\"")
    lines.append("---")
    return "\n".join(lines) + "\n"


def extract_name_aliases(fm: dict) -> list[str]:
    """从 aliases 字段提取用于 Wiki 搜索的关键词列表"""
    aliases = fm.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = [aliases] if aliases else []
    results = []
    for a in aliases:
        a = str(a).strip()
        # 跳过纯中文名（含中文字符），优先用英文名
        if any("\u4e00" <= c <= "\u9fff" for c in a):
            continue
        if not a:
            continue
        # 去掉 @ 前缀
        results.append(a.lstrip("@").strip())
    return [x for x in results if x] if results else [fm.get("title", "")]


def wiki_search(query: str, lang: str = "zh") -> list[dict]:
    """在指定语言 Wikipedia 中搜索，返回页面摘要信息（带重试防限流）"""
    api_url = WIKI_ZH if lang == "zh" else WIKI_EN
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "format": "json",
        "srprop": "size|wordcount",
    }
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(api_url, params=params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()
            return data.get("query", {}).get("search", [])
        except Exception as e:
            last_err = str(e)
            time.sleep(1.5 * (attempt + 1))
    return [{"error": last_err or "unknown", "query": query}]


def get_page_info(title: str, lang: str = "zh") -> dict:
    """获取 Wikipedia 页面的详细信息（生卒年、国籍、代表作等）"""
    api_url = WIKI_ZH if lang == "zh" else WIKI_EN
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts|info|pageprops",
        "exintro": True,
        "explaintext": True,
        "inprop": "url",
        "redirects": 1,  # 自动跟随重定向（如 塞缪尔·亨廷顿 → 萨缪尔·P·亨廷顿）
        "format": "json",
    }
    for attempt in range(3):
        try:
            r = requests.get(api_url, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid == "-1":
                    return {"error": "not_found", "title": title}
                props = page.get("pageprops", {})
                extract = page.get("extract", "")
                # 消歧页/人名列表页检测（既有 pageprops 标记，也看 extract 文案）
                disambig = bool(props.get("disambiguation")) or bool(
                    any(k in props for k in ("disambiguationtitles", "disambiguationtag"))
                )
                if not disambig:
                    head = extract[:400].lower()
                    if any(kw in head for kw in ("may refer to", "can refer to", "refers to",
                                                  "可以指", "可指", "可能指", "消歧义", "消歧",
                                                  "指的是下列", "personset", "persons", "是一个消歧义")):
                        disambig = True
                return {
                    "title": page.get("title", title),
                    "extract": extract,
                    "url": page.get("fullurl", ""),
                    "length": page.get("length", 0),
                    "wikibase": props.get("wikibase_item", ""),
                    "disambiguation": disambig,
                }
            return {"error": "no_result", "title": title}
        except Exception as e:
            last_err = str(e)
            time.sleep(2 * (attempt + 1))
    return {"error": last_err or "unknown", "title": title}


def _norm(s: str) -> str:
    """归一化：NFKC 转半角、拆组合字符，再去掉空格/点/下划线/连字符/间隔号/撇号并转小写，
    用于宽松匹配（如 D.A. Miller → damiller、Éluard → eluard）"""
    s = unicodedata.normalize("NFKC", s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[\s._\-·']", "", s).lower()


NATIONS = ["中国", "法国", "英国", "德国", "美国", "意大利", "西班牙", "俄罗斯",
           "日本", "韩国", "印度", "荷兰", "比利时", "奥地利", "瑞士", "丹麦",
           "瑞典", "挪威", "芬兰", "波兰", "捷克", "匈牙利", "希腊", "土耳其",
           "伊朗", "以色列", "墨西哥", "加拿大", "澳大利亚", "巴西", "阿根廷",
           "葡萄牙", "爱尔兰", "苏格兰", "犹太", "阿拉伯", "埃及"]


def norm_nation(n: str) -> str:
    """国籍归一化"""
    return {"古希腊": "希腊", "古罗马": "罗马", "古希腊罗马": "希腊罗马",
            "俄国": "俄罗斯", "苏联": "俄罗斯"}.get(n, n)


MONTH_EN = r"(?:Jan\.?|Feb\.?|Mar\.?|Apr\.?|May|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Oct\.?|Nov\.?|Dec\.?|January|February|March|April|June|July|August|September|October|November|December)"
DASH = r"[—－–~～至到\-]"


def extract_lifespan(text: str) -> list[str]:
    """从维基简介提取生卒年。

    策略：优先匹配姓名括号内的生卒锚点，以排除维护横幅/正文杂项日期；
    支持中文完整日期、年份对、混合格式（1572年—1631年3月31日）及英文日期；
    对提取结果做区间合理性校验，拿不准就返回空（宁可漏、不可错）。
    """
    first = text[:600]
    out = []

    def push_range(y1, y2, bc1=False, bc2=False):
        """校验并写入闭区间生卒（含公元前）"""
        if bc1 and bc2:
            hi, lo = max(y1, y2), min(y1, y2)
            if 3 <= hi - lo <= 150:
                out.append(f"前{hi}–前{lo}")
        elif not (bc1 or bc2):
            if 1000 <= y1 < y2 <= 2026 and 3 <= y2 - y1 <= 150:
                out.append(f"{y1}–{y2}")

    def push_open(y, bc=False):
        """校验并写入开放结束（在世，YYYY年M月D日—）"""
        if not bc and 1000 <= y <= 2006:
            out.append(f"{y}–今")

    def try_zh():
        # 1) 完整双日期：（…YYYY年M月D日—YYYY年M月D日…）
        m = re.search(rf"（[^）]{{0,150}}?(\d{{4}})年\d{{1,2}}月\d{{1,2}}日[^）]{{0,40}}?{DASH}[^）]{{0,40}}?(\d{{4}})年\d{{1,2}}月\d{{1,2}}日[^）]*）", first)
        if m:
            push_range(int(m.group(1)), int(m.group(2)))
            return
        # 2) 混合：年份+完整日期（约翰·多恩：1572年—1631年3月31日）
        m = re.search(rf"（[^）]{{0,150}}?(\d{{4}})年[^）]{{0,40}}?{DASH}[^）]{{0,40}}?(\d{{4}})年\d{{1,2}}月\d{{1,2}}日[^）]*）", first)
        if m:
            push_range(int(m.group(1)), int(m.group(2)))
            return
        # 3) 混合：完整日期+年份（1928年12月7日—1944年）
        m = re.search(rf"（[^）]{{0,150}}?(\d{{4}})年\d{{1,2}}月\d{{1,2}}日[^）]{{0,40}}?{DASH}[^）]{{0,40}}?(\d{{4}})年[^）]*）", first)
        if m:
            push_range(int(m.group(1)), int(m.group(2)))
            return
        # 4) 完整日期+开放结束（在世）：（…YYYY年M月D日—…）
        m = re.search(rf"（[^）]{{0,150}}?(\d{{4}})年\d{{1,2}}月\d{{1,2}}日\s*{DASH}(?!\s*\d{{4}}年)[^）]*）", first)
        if m:
            push_open(int(m.group(1)))
            return
        # 5) 纯年份对：（…YYYY年—YYYY年…）
        m = re.search(rf"（[^）]{{0,150}}?(\d{{4}})年[^）]{{0,40}}?{DASH}[^）]{{0,40}}?(\d{{4}})年[^）]*）", first)
        if m:
            push_range(int(m.group(1)), int(m.group(2)))
            return
        # 6) 年份+开放结束：（…YYYY年—…）
        m = re.search(rf"（[^）]{{0,150}}?(\d{{4}})年[^）]{{0,30}}?{DASH}(?!\s*\d{{4}}年)[^）]*）", first)
        if m:
            push_open(int(m.group(1)))
            return
        # 7) 公元前：（…前384年—前322年…）
        m = re.search(r"（[^）]{0,150}?前(\d{1,4})年[^）]{0,40}?[—－–~～至到][^）]{0,40}?前(\d{1,4})年[^）]*）", first)
        if m:
            push_range(int(m.group(1)), int(m.group(2)), bc1=True, bc2=True)

    def try_en():
        name_zone = first[:220]  # 人物页生卒锚点通常在姓名导语内；正文的 (YYYY–YYYY) 多为任职/出版区间
        # 7a) 在世：(; born 1928) / (born 1928) / (born 11 November 1928) / (born March 22, 1928)
        #     支持分号前缀与英美两种日期顺序（如 Hirsch extract "(; born March 22, 1928)"）
        m = re.search(r"\(?;?\s*born\s+(?:\d{1,2}\s+" + MONTH_EN + r"\.?,?\s*|" + MONTH_EN + r"\.?\s+\d{1,2},\s*)?(\d{4})\)?", name_zone)
        if m:
            push_open(int(m.group(1)))
            return
        # 8) 英文完整日期：(28 February 1865 – 22 January 1945)
        m = re.search(rf"\([^()]{{0,200}}?(\d{{1,2}})\s+{MONTH_EN}\s+(\d{{4}})\s*[–—−-]\s*(\d{{1,2}})\s+{MONTH_EN}\s+(\d{{4}})[^()]*\)", first)
        if m:
            push_range(int(m.group(2)), int(m.group(4)))
            return
        # 8b) 姓名区跨格式生卒：(…) 1828 – 20 November [O.S. 7 November] 1910 …)
        #     经典英文姓名导语，日期以开放距离跨接（允许 [O.S.] / 月份词/分号）
        m = re.search(r"\([^()]{0,160}?(\d{4})[^()]{0,50}?[–—−][^()]{0,50}?(\d{4})[^()]*\)", name_zone)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            if y1 < y2:
                push_range(y1, y2)
                return
        # 8d) 容忍 IPA/嵌套括号：(; Russian: …(j)… ; 1828 – … 1910)
        #     全点号通配，仅靠首尾括号锚定；限姓名区避免正文任职/出版区间
        m = re.search(r"\(.{0,190}?(\d{4}).{0,90}?[–—−].{0,90}?(\d{4}).{0,40}?\)", name_zone, re.DOTALL)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            if y1 < y2:
                push_range(y1, y2)
                return
        # 9) 英文年份对 (1900–1990)：仅限姓名区，避免匹配正文的任职/出版区间
        m = re.search(rf"\([^()]{{0,200}}?(\d{{4}})\s*[–—−-]\s*(\d{{4}})[^()]*\)", name_zone)
        if m:
            push_range(int(m.group(1)), int(m.group(2)))
            return
        # 10) 英文公元前：(384 BC – 322 BC)
        m = re.search(r"\((\d{1,4})\s*(?:BCE|BC)\s*(?:[–—\-]|\s)*(\d{1,4})\s*(?:BCE|BC)\)", first)
        if m:
            push_range(int(m.group(1)), int(m.group(2)), bc1=True, bc2=True)

    try_zh()
    if not out:
        try_en()
    return out[:2]


def check_identity(extract: str, aliases: list, query: str = "", head_len: int = 260) -> bool:
    """校验 extract 是否确认命中了别名所指的人物（区别于当前查询串）。

    判据：
    1) 查询为多词全名（含空格，如 "Sandra Gilbert"/"Roland Barthes"）：
       要求名字和姓氏的 token 分别出现在 extract 前部（允许中间名
       "Roland Gérard Barthes" 仍通过），否则拒绝——纯姓（Gilbert/
       Brooks/Barthes）不是证据，他人页面 extract 常含 "XX Gilbert"。
       例："汉弗莱·吉尔伯特" 页不含 "Sandra" → 拒绝；而
       罗兰·巴特页含 "Roland...Barthes" → 通过。
    2) 查询为短名：检查"区别性全名"别名（含空格或归一化长度 >=9），
       必须命中其一；没有则退化为短别名（>=4 字符）匹配。
    3) 别名全部等于查询串（如仅"弗罗斯特"）：任意别名命中即可。
    """
    head = extract[:head_len]
    head_n = _norm(head)
    q_n = _norm(query)

    def _all_tokens_near(head_lo_s: str, toks: list) -> bool:
        """所有 token 必须在 head 中按序出现，且相邻 token 之间间隔不超过 2 个词。
        防止"约翰·汤姆林森·卜内"式的假命中（名+姓命中但中间/尾部插入其他词）。"""
        pos = -1
        first_idx = None
        last_idx = -1
        for t in toks:
            if not t:
                continue
            i = head_lo_s.find(t, pos + 1)
            if i == -1:
                return False
            if first_idx is None:
                first_idx = i
            pos = i
            last_idx = i + len(t)
        # 首尾 token 间插入的字符数不可过大（排除"John Tomlinson Brunner"里三者相距很远 / 中间名可容忍）
        # 放宽至 full+20：覆盖 "Leonardo di ser Piero da Vinci" 式长中名结构（gap=30, full=13）
        gap = last_idx - first_idx
        full = sum(len(t) for t in toks)
        return gap <= full + 20

    if " " in query:
        # 多词全名查询：名 + 姓 token 须按序、紧密地出现在 extract 前部
        head_lo = head.lower()
        tokens = [t for t in query.lower().split() if len(t) >= 3]
        if tokens and _all_tokens_near(head_lo, tokens):
            return True
        # 全名未命中时，再检查其他"区别性全名"别名（如库里英文名 vs 查询简体）
        for a in aliases:
            if (" " in a) and _norm(a) != q_n:
                a_tokens = [t for t in a.lower().split() if len(t) >= 3]
                if a_tokens and _all_tokens_near(head_lo, a_tokens):
                    return True
        return False

    others = [a for a in aliases if a and _norm(a) != q_n]
    distinctive = [a for a in others if (" " in a) or len(_norm(a)) >= 9]

    if distinctive:
        # 存在区别性全名：必须命中其一（短姓不构成证据）
        for a in distinctive:
            if _norm(a) in head_n:
                return True
        return False
    if others:
        # 只有短别名：任一 >=4 字符别名命中即可
        for a in others:
            a_n = _norm(a)
            if len(a_n) >= 4 and a_n in head_n:
                return True
        return False
    # 别名全部等于查询串（如仅"弗罗斯特"）：任意别名命中即可
    for a in aliases:
        a_n = _norm(a)
        if len(a_n) >= 4 and a_n and a_n in head_n:
            return True
    return False


def extract_nationality(text: str) -> list[str]:
    """从简介第一段提取国籍（XX人/XX籍/XX裔 或 XX小说家/哲学家 等结构）。
    为避免误捕引文中提及的他国人物（如 维柯 extract 中的"英国思想家以赛亚·伯林"），
    将"国名+职业"结构限制在姓名导语窗（<=120 字符），而"XX人/XX籍/XX裔"结构可扫全段。"""
    first_para = text[:350]
    intro = first_para[:150]  # 姓名导语窗（人物自我国籍区，扩至 150 以捕获"意大利启蒙运动时期的政治哲学家"等长导语）
    known = NATIONS
    nations = []

    def add_nation(n_raw):
        """归一化并校验，加入国籍列表"""
        n = norm_nation(n_raw)
        if n in known:
            if n not in nations:
                nations.append(n)
            return True
        # 回退：known 中是否有词是 n_raw 的子串（如"美国文学"→"美国"）
        sub = next((k for k in known if k in n_raw), None)
        if sub and sub not in nations:
            nations.append(sub)
        return sub is not None

    # 结构一：XX人/XX籍/XX裔（爱尔兰人、美籍）——扫描全段（这些结构通常关于主体）
    for m in re.finditer(r"([\u4e00-\u9fff]{2,4})(?:国)?(?:人|籍|裔)", first_para):
        add_nation(m.group(1))
    # 结构二：国名+职业（爱尔兰小说家、美国语言学家、法国哲学家）——限姓名导语窗
    if not nations:
        jobs = r"(?:小说家|诗人|哲学家|语言学家|文学家|文学批评家|文学理论家|作家|政治家|批评家|思想家|美学家|心理学家|历史学家|社会学家|剧作家|散文家|翻译家|经济学家|数学家|物理学家|生物学家|音乐家|画家|导演|演员|理论家|学者|评论家)"
        # Fix E: 允许国名与职业词间 0-8 字 gap（如"意大利启蒙运动时期的政治哲学家"）
        for m in re.finditer(r"([\u4e00-\u9fff]{2,4})(?:国)?[^，。；（）\n]{0,8}?" + jobs, intro):
            add_nation(m.group(1))
    if not nations:
        # 英文格式——仅限前 150 字符（英文姓名导语窗更短）
        en_zone = first_para[:150]
        en_known = {"French": "法国", "British": "英国", "German": "德国",
                    "American": "美国", "Italian": "意大利", "Spanish": "西班牙",
                    "Russian": "俄罗斯", "Japanese": "日本", "Korean": "韩国",
                    "Indian": "印度", "Dutch": "荷兰", "Belgian": "比利时",
                    "Austrian": "奥地利", "Swiss": "瑞士", "Danish": "丹麦",
                    "Swedish": "瑞典", "Norwegian": "挪威", "Finnish": "芬兰",
                    "Polish": "波兰", "Czech": "捷克", "Greek": "希腊",
                    "Turkish": "土耳其", "Irish": "爱尔兰", "Scottish": "苏格兰",
                    "Chinese": "中国", "Canadian": "加拿大", "Australian": "澳大利亚",
                    "Brazilian": "巴西", "Portuguese": "葡萄牙", "Hungarian": "匈牙利",
                    "Israeli": "以色列", "Mexican": "墨西哥", "Egyptian": "埃及"}
        for n, zh in en_known.items():
            if re.search(r"\b" + n + r"\b", en_zone):
                nations.append(zh)
    return nations[:3]


def extract_key_works(text: str, max_count: int = 3) -> list[str]:
    """从简介中提取可能的代表作"""
    works = []
    # 中文书名号格式
    for m in re.finditer(r"《([^》]{2,20})》", text):
        w = m.group(1).strip()
        # 过滤过于通用的词
        if len(w) >= 2 and not re.match(r"^(哲学|文学|艺术|美学|理论|研究|方法|原则)$", w):
            works.append(f"《{w}》")
    # 英文斜体/引号格式
    for m in re.finditer(r"[\"\'‘“](.{3,40})[\"\'’”]", text):
        w = m.group(1).strip()
        if len(w) >= 2:
            works.append(w)
    # 去重并按出现顺序保留
    seen = set()
    unique = []
    for w in works:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:max_count]


def cross_check(fm: dict, lifespan: list, nationality: list, body: str = "") -> dict:
    """用 figures 页已有 tags/正文交叉校验 wiki 数据，返回冲突清单（有冲突的字段不应写入）"""
    conflicts = {}

    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    tag_str = " ".join(str(t) for t in tags)

    # 1) 国籍冲突：tags 中出现的国别 vs wiki 提取国籍（归一化后无交集则冲突）
    tag_nations = {norm_nation(n) for n in NATIONS if norm_nation(n) in tag_str}
    wiki_nat = set(nationality)
    if tag_nations and wiki_nat and not (tag_nations & wiki_nat):
        conflicts["nationality"] = {"tags": sorted(tag_nations), "wiki": sorted(wiki_nat)}

    # 2) 生卒年冲突：tags 及正文标题行中的 4 位年份 vs wiki 生卒首年，
    #    差 > 10 视为冲突。正文标题通常是"# XX（Roland Barthes, 1915-1980）"，
    #    标题年份比正文第一段的事件/出版年（如"1899 年出版"）更接近生卒记录；
    #    若 wiki 首年与标题生卒年相去甚远，说明疑似同名异人
    #    （如库里 1941 年的叙事学家 vs wiki 1970 年自行车运动员）。
    title_line = body.splitlines()[0] if body else ""
    tag_years_source = tag_str + " " + title_line
    tag_years = [int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", tag_years_source)]
    wiki_year = None
    if lifespan:
        m = re.search(r"(\d{4})", lifespan[0])
        wiki_year = int(m.group(1)) if m else None
    if tag_years and wiki_year:
        if all(abs(wiki_year - y) > 10 for y in tag_years):
            conflicts["lifespan"] = {"tags_year": tag_years, "wiki": lifespan[0]}

    return conflicts


def fill_figure(path: Path, dry_run: bool = False) -> dict:
    """对单个 figures 页执行 Wiki 回填，返回操作摘要"""
    fm, body, raw = parse_frontmatter(path)
    aliases = extract_name_aliases(fm)
    title = fm.get("title", path.stem)

    result = {
        "file": path.name,
        "title": title,
        "aliases_searched": aliases,
        "wiki_data": {},
        "actions": [],
        "success": False,
        "error": None,
    }

    # 尝试中英文搜索
    # 搜索词池：全部别名（中文+英文）+ title
    query_pool = []
    for a in aliases:
        if a and a not in query_pool:
            query_pool.append(a)
    if title and title not in query_pool:
        query_pool.append(title)
    # Fix D: zh 搜索池额外包含中文别名（extract_name_aliases 过滤了中文，需在搜索时补回）
    zh_pool = []
    for a in (fm.get("aliases") or []):
        a = str(a).strip()
        if a and any("\u4e00" <= c <= "\u9fff" for c in a) and a not in zh_pool:
            zh_pool.append(a)
    if title and title not in zh_pool:
        zh_pool.append(title)
    # 长别名/英文全名优先：避免短名（"巴尔特"/"Barthes"）先命中无关页面
    # （如德国城市"巴尔特"、姓氏页），导致长查询词永远轮不到
    query_pool.sort(key=lambda x: -len(_norm(x)))
    zh_pool.sort(key=lambda x: -len(_norm(x)))

    best = None  # (lang, matched_title, page_info)
    for lang, pool in [("zh", zh_pool), ("en", [a for a in query_pool if not any("\u4e00" <= c <= "\u9fff" for c in a)])]:
        for q in pool:
            search_results = wiki_search(q, lang)
            valid = [s for s in search_results if "error" not in s]
            if not valid:
                continue
            time.sleep(0.6)

            matched = None
            for sr in valid:
                t = sr.get("title", "")
                if "消歧" in t or "disambiguation" in t.lower():
                    continue
                t_lower = t.lower().replace("_", " ")
                q_lower = q.lower()
                t_n, q_n = _norm(t), _norm(q)
                is_cjk = any("\u4e00" <= c <= "\u9fff" for c in q)
                if q_n and q_n == t_n:
                    matched = (t, "high")
                    break
                if q_n and q_n in t_n:
                    # 中文查询子串命中标题（例："乌斯宾斯基"→"亚历山大·乌斯宾斯基"）有歧义，
                    # 一律降级为 low，交由 extract 别名校验把关；英文查询子串命中可接受（high）
                    matched = (t, "low" if is_cjk else "high")
                    break
                if t_n and t_n in q_n:
                    matched = (t, "high")
                    break
                # 别名命中：仅当命中的别名是"含空格全名"或归一化等于查询时才给 high；
                # 短姓/短名（Gilbert/Brooks）子串命中他人页面（"汉弗莱·吉尔伯特"）
                # 不足以证明页面即目标人物，否则会抢占 zh 结果、让准确的 en 匹配轮不到。
                alias_hit_high = False
                for x in aliases:
                    xn = _norm(x)
                    if len(xn) >= 4 and xn in t_n:
                        alias_hit_high = (" " in x) or (xn == q_n)
                        break
                if alias_hit_high:
                    matched = (t, "high")
                    break
            if not matched:
                # 放宽候选：取第一条搜索结果（需通过 extract 校验防错配）
                matched = (valid[0]["title"], "low")

            page_info = get_page_info(matched[0], lang)
            if page_info.get("error") == "not_found":
                continue
            if page_info.get("disambiguation"):
                continue  # 拒绝消歧页/人名列表页（如 Grossberg → Carl/Lawrence 列表）
            # 空 extract（重定向未跟随/页面无简介）视为无效候选，继续尝试其他语言
            if len(page_info.get("extract", "").strip()) < 15:
                continue
            # 身份校验：区别性别名必须出现在 extract 前部，防短别名/凡名子串错配
            # （"Brooks"→DJ 艺名页、"吉尔伯特"→汉弗莱页 均会被拒绝）
            # 强标题豁免：title 与查询归一化相等，且查询为长中文名/含空格英文全名时，
            # 页面标题即目标，直接放行（如 "罗兰·巴特"、"Roland Barthes"）；
            # 但豁免仅适用于"人物页"——若页面 extract 不含任何人物特征
            # （无生卒锚点、无 XX人/XX家 职业词，且标题含 城市/州/位于 等地理词），
            # 则视为无关实体（如德国城市"巴尔特"），不放行，继续尝试更长的查询词。
            cjk_count = sum(1 for c in q if "\u4e00" <= c <= "\u9fff")
            strong_title = (matched[1] == "high" and (cjk_count >= 3 or " " in q))
            # Fix A: 非人物页降级仅对 CJK 查询生效（英文精确 title 匹配可靠，
            # 如 "E. D. Hirsch" 不应被中文 no_job 检查误伤）
            if strong_title and cjk_count >= 3:
                this_extract = page_info.get("extract", "")
                geo_hint = any(k in this_extract[:200] for k in ("城市", "州", "位于", "镇", "县"))
                no_lifespan = not extract_lifespan(this_extract)
                no_job = not any(k in this_extract[:200] for k in
                                 ("人", "家", "学者", "理论家", "批评家", "作家", "哲学家", "小说家", "诗人"))
                if no_lifespan and (geo_hint or no_job):
                    strong_title = False  # 疑似非人物页（如德国城市"巴尔特"）
            if not strong_title and not check_identity(page_info.get("extract", ""), aliases, q):
                continue
            # Fix C: low 置信度匹配要求有 lifespan（防误配无生卒的书名页/事件页）
            if matched[1] == "low" and not extract_lifespan(page_info.get("extract", "")):
                continue
            page_info["match_confidence"] = matched[1]
            best = (lang, matched[0], page_info)
            break
        if best:
            break

    if best:
        lang, matched_title, page_info = best
        result["wiki_data"]["matched_page"] = page_info
        result["wiki_data"]["lang"] = lang
        result["wiki_data"]["matched_title"] = matched_title
        result["wiki_data"]["match_confidence"] = page_info.get("match_confidence")

        # 提取结构化数据
        text = page_info.get("extract", "")
        lifespan = extract_lifespan(text)
        nationality = extract_nationality(text)
        works = extract_key_works(text)

        result["wiki_data"]["lifespan"] = lifespan
        result["wiki_data"]["nationality"] = nationality
        result["wiki_data"]["works"] = works
        result["wiki_data"]["source_url"] = page_info.get("url", "")
        result["success"] = True
        result["actions"].append(f"wiki_search:{lang}:{matched_title}")

        if lifespan or nationality:
            # 交叉校验：仅"生卒年冲突"说明疑似同名异人（身份存疑），阻止写入；
            # 国籍冲突多为 tags 标注口径差异（如研究领域 vs 实际国籍），仅作标记不阻止。
            conflicts = cross_check(fm, lifespan, nationality, body)
            result["conflict"] = conflicts if conflicts else None
            identity_doubt = "lifespan" in conflicts
            if identity_doubt:
                result["actions"].append("conflict_skip:lifespan,nationality")
            elif conflicts:
                result["actions"].append(f"conflict_flag:{','.join(conflicts)}")
            # 更新 frontmatter
            if lifespan and "wiki_lifespan" not in fm and not identity_doubt:
                fm["wiki_lifespan"] = lifespan[0]
                result["actions"].append(f"frontmatter:wiki_lifespan={lifespan[0]}")
            if nationality and "wiki_nationality" not in fm and not identity_doubt:
                fm["wiki_nationality"] = nationality[:3]
                result["actions"].append(f"frontmatter:wiki_nationality={'/'.join(nationality[:3])}")
            if not dry_run:
                new_header = rebuild_frontmatter(fm, raw)
                new_content = new_header + body
                path.write_text(new_content, encoding="utf-8")
                result["actions"].append("file_saved")

        return result

    result["error"] = "no_match_found"
    return result


def main():
    parser = argparse.ArgumentParser(description="Wiki Fill — 从 Wikipedia 回填 figures 页数据")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")
    parser.add_argument("--limit", type=int, default=0, help="限制处理数量（0=全部）")
    parser.add_argument("--page", type=str, help="处理单个文件（文件名，不含路径）")
    args = parser.parse_args()

    print("=" * 60)
    print("Wiki Fill — Wikipedia 数据结构回填")
    print("=" * 60)
    print(f"模式: {'DRY RUN（仅预览）' if args.dry_run else 'WRITE（写入文件）'}")

    figures_dir = KB_ROOT
    if not figures_dir.exists():
        print(f"错误：figures 目录不存在：{figures_dir}")
        sys.exit(1)

    files = sorted(figures_dir.glob("*.md"))
    if args.page:
        target = figures_dir / args.page
        if target not in files:
            print(f"错误：未找到文件 {target}")
            sys.exit(1)
        files = [target]

    if args.limit > 0:
        files = files[:args.limit]

    print(f"待处理 figures 页: {len(files)} 个\n")

    results = []
    for i, fpath in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {fpath.name}...", end=" ", flush=True)
        try:
            result = fill_figure(fpath, dry_run=args.dry_run)
            results.append(result)

            if result["success"]:
                status = "✓"
                if result.get("conflict"):
                    status = "⚠"  # 存在与 tags 交叉校验冲突的字段
                if result["wiki_data"].get("lifespan"):
                    status += f" 生卒:{result['wiki_data']['lifespan'][0]}"
                if result["wiki_data"].get("nationality"):
                    status += f" 国籍:{'/'.join(result['wiki_data']['nationality'][:2])}"
                if args.dry_run and ("frontmatter:" in str(result["actions"])):
                    status += " (预览)"
                if result.get("conflict"):
                    status += f" 冲突:{','.join(result['conflict'])}"
                print(status)
            else:
                print(f"✗ {result.get('error', 'unknown')}")
        except Exception as e:
            print(f"✗ ERROR: {e}")
            results.append({"file": fpath.name, "error": str(e), "success": False})

        time.sleep(0.6)

    # 统计报告
    print("\n" + "=" * 60)
    print("汇总报告")
    print("=" * 60)

    success_count = sum(1 for r in results if r["success"])
    empty_count = sum(1 for r in results if not r["success"])
    with_lifespan = sum(1 for r in results if r.get("wiki_data", {}).get("lifespan"))
    with_nationality = sum(1 for r in results if r.get("wiki_data", {}).get("nationality"))
    written_count = sum(1 for r in results if "file_saved" in r.get("actions", []))

    print(f"成功匹配: {success_count}/{len(results)}")
    print(f"  含生卒年: {with_lifespan}")
    print(f"  含国籍:   {with_nationality}")
    conflict_count = sum(1 for r in results if r.get("conflict"))
    if conflict_count:
        print(f"⚠ 交叉校验标记: {conflict_count}（国籍口径差异等，详见报告）")
    print(f"未匹配:    {empty_count}")
    print(f"文件写入:  {written_count}" if not args.dry_run else "文件写入:  0（DRY RUN 模式）")

    # 列出失败的案例
    failures = [r for r in results if not r["success"]]
    if failures and len(failures) <= 20:
        print(f"\n未匹配列表:")
        for r in failures:
            print(f"  - {r['file']}: {r.get('error', '?')}")

    # 保存详细报告
    report_path = KB_ROOT.parent / "_wiki_fill_report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细报告已保存至: {report_path}")

    return results


if __name__ == "__main__":
    main()
