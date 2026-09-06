"""
西方文论教材 PDF → markdown 提取脚本（v2）

输入:  d:\\BaiduNetdiskDownload\\西方文论教材\\*.pdf
输出:  d:\\BaiduNetdiskDownload\\西方文论教材\\kb\\raw\\<教材简称>\\<NN>-<章节>.md

核心策略（解决 layered PDF 双层 OCR 重影）:
1. 不用 page.extract_text()（它把双 OCR 层合并成字符重影）
2. 直接用 page.chars 字符级 API，按 y 聚类成行、按 x 排序重组
3. 行级去重：layered PDF 的两份 OCR 输出几乎是相邻重复行，归一化后相同
4. 按章节标题切片（第X章 / Chapter X / 数字+点号）
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

# ===== 配置 =====

SOURCE_DIR = Path(r"d:\BaiduNetdiskDownload\西方文论教材")
KB_ROOT = SOURCE_DIR / "kb"
RAW_ROOT = KB_ROOT / "raw"
SCRIPTS_DIR = KB_ROOT / "scripts"

# 教材文件名 → (简称, 完整书名, 语种)
BOOK_MAP: dict[str, tuple[str, str, str]] = {
    "[OCR]_朱立元《当代西方文艺理论》_20260903_1657.layered.pdf":
        ("朱立元", "当代西方文艺理论", "zh"),
    "[OCR]_马新国.西方文论史（修订版）_20260903_1609.layered.pdf":
        ("马新国", "西方文论史（修订版）", "zh"),
    "[OCR]_伍蠡甫：《西方文论选》_20260903_1632.layered.pdf":
        ("伍蠡甫", "西方文论选", "zh"),
    "[OCR]_高等学校文科教材  西方文艺理论名著教程（下册）_20260903_1556.layered.pdf":
        ("名著教程下", "西方文艺理论名著教程（下册）", "zh"),
    "[OCR]_西方文艺理论史教程（第一册)_20260903_1656.layered.pdf":
        ("理论史教程一", "西方文艺理论史教程（第一册）", "zh"),
    "[OCR]_当代西方最新文论教程_20260903_1451.layered.pdf":
        ("最新文论教程", "当代西方最新文论教程", "zh"),
    "[OCR]_[Toiffer选版].二十世纪西方文论选.(上).(..._20260903_1308.layered.pdf":
        ("二十世纪文论选上", "二十世纪西方文论选（上）", "zh"),
    "[OCR]_二十世纪西方文论选（下）_20260903_1528.layered.pdf":
        ("二十世纪文论选下", "二十世纪西方文论选（下）", "zh"),
    "[OCR]_Cary Nelson, Lawrence Grossberg-Marxism and the Interpretation of Culture (1988)_20260903_1328.layered.pdf":
        ("Grossberg", "Marxism and the Interpretation of Culture", "en"),
    "[OCR]_西方文艺批评的五种模式 _（美）司各特编著；蓝仁哲译_重庆：重庆出版社_1983.08_177页 (1)_20260903_1656.layered.pdf":
        ("司各特", "西方文艺批评的五种模式", "zh"),
    "[OCR]_西方文艺批评的五种模式 _（美）司各特编著；蓝仁哲译_重庆：重庆出版社_1983.08_177页_20260903_1657.layered.pdf":
        ("司各特", "西方文艺批评的五种模式", "zh"),
    "[OCR]_当代英美文艺批评的五种模式_20260903_1527.layered.pdf":
        ("五种模式", "当代英美文艺批评的五种模式", "zh"),
    "[OCR]_[Toiffer选版].当代学术入门：文学理论_20260903_1305.layered.pdf":
        ("文学理论入门", "当代学术入门：文学理论", "zh"),
    "[OCR]_反世界文学：不可翻译性的政治_20260903_1556.layered.pdf":
        ("反世界文学", "反世界文学：不可翻译性的政治", "zh"),
    "[OCR]_汉语经验之翼的回响——从高校教材资源建设看西方文论在当代中国_20260903_1608.layered.pdf":
        ("汉语经验", "汉语经验之翼的回响", "zh"),
    "[OCR]_西方文论选 （下卷）_20260903_1644.layered.pdf":
        ("西方文论选下", "西方文论选（下卷）", "zh"),
    "[OCR]__当代西方文学理论导引_一书出版_20260903_1328.layered.pdf":
        ("导引出版", "当代西方文学理论导引一书出版", "zh"),
    "[OCR]_二十世纪西方文论选++（上卷）_0_20260903_1712.layered.pdf":
        ("二十世纪文论选上v2", "二十世纪西方文论选（上卷）v2", "zh"),
}

SEEN_SLUGS: set[str] = set()


# ===== 字符级页面文本重组 =====

@dataclass
class CharInfo:
    text: str
    x0: float
    x1: float
    top: float


def cluster_lines(chars: list[CharInfo], y_tol: float = 3.0) -> list[list[CharInfo]]:
    """按 top 聚类成行（同 y 容差内视为同一行）。"""
    if not chars:
        return []
    sorted_chars = sorted(chars, key=lambda c: (c.top, c.x0))
    lines: list[list[CharInfo]] = []
    current: list[CharInfo] = []
    current_top: float | None = None
    for c in sorted_chars:
        if current_top is None:
            current.append(c)
            current_top = c.top
        elif abs(c.top - current_top) <= y_tol:
            current.append(c)
        else:
            current.sort(key=lambda c: c.x0)
            lines.append(current)
            current = [c]
            current_top = c.top
    if current:
        current.sort(key=lambda c: c.x0)
        lines.append(current)
    return lines


def line_to_text(chars: list[CharInfo]) -> str:
    """把同一行的字符拼成文本，间距过大插入空格。"""
    if not chars:
        return ""
    parts: list[str] = []
    prev: CharInfo | None = None
    for c in chars:
        if prev is not None:
            gap = c.x0 - prev.x1
            if gap > 8:  # 中文正常字符宽约 9-10 px；过大说明是分栏或大间隔
                parts.append(" ")
        parts.append(c.text)
        prev = c
    return "".join(parts)


def extract_page_text(page) -> str:
    """从 page.chars 直接重组文本（绕过 extract_text 的合并层）。"""
    chars = [
        CharInfo(text=c["text"], x0=c["x0"], x1=c["x1"], top=c["top"])
        for c in page.chars
        if c.get("text")
    ]
    lines = cluster_lines(chars)
    return "\n".join(line_to_text(line) for line in lines)


# ===== 字符级兜底去重 =====
# 大部分页面用 chars API 已无重影，但页眉/装饰元素可能仍重影
KEEP_DUP = {
    "人人","事事","处处","时时","天天","年年","字字","句句",
    "常常","渐渐","缓缓","匆匆","悄悄","微微",
    "刚刚","仅仅","恰恰","频频","屡屡","迟迟",
    "茫茫","漫漫","长长","短短","高高","低低",
    "深深","浅浅","厚厚","薄薄","重重","轻轻",
    "明明","白白","空空","满满","圆圆","方方",
    "走走","停停","看看","听听","说说","想想",
    "真真","假假","是是","非非","对对","错错",
    "好好","慢慢","快快","早早","晚晚",
}
_CN_RE = r"[\u4e00-\u9fff]"


def dedup_chars_line(line: str) -> str:
    """字符级兜底：相邻中文字符重复且不在白名单时去重。"""
    if not line:
        return line
    placeholders: dict[str, str] = {}
    for i, w in enumerate(KEEP_DUP):
        if w in line:
            token = f"\x00K{i}\x00"
            line = line.replace(w, token)
            placeholders[token] = w
    line = re.sub(rf"({_CN_RE})\1+", r"\1", line)
    for token, w in placeholders.items():
        line = line.replace(token, w)
    return line


# ===== 行级去重 =====

# 归一化时只保留中文字符、英文字母、数字（其余全去掉，含中英标点、空白、点）
_NORMALIZE_KEEP = re.compile(r"[\u4e00-\u9fff A-Za-z0-9]")


def normalize_line(line: str) -> str:
    """归一化：只保留中文字符、英文字母、数字；英文转小写。用于相邻行去重比对。"""
    return "".join(_NORMALIZE_KEEP.findall(line)).lower()


# 极短且无实质内容的行（页码、装饰元素）
_TRIVIAL_LINE = re.compile(r"^[\s\d·。、,.\-\d]+$")


def is_trivial_line(line: str) -> bool:
    """是否是页码、纯符号行等无实质内容行。"""
    s = line.strip()
    if not s:
        return True
    if len(s) <= 5 and _TRIVIAL_LINE.match(s):
        return True
    return False


def dedup_consecutive_lines(text: str) -> str:
    """
    行级去重：layered PDF 把同一段 OCR 两次，相邻行归一化后高度相似（含 OCR 错字）。
    用 SequenceMatcher 相似度判断，> 0.90 视为重复，保留较长那份。
    同时过滤极短无实质内容行（页码、装饰元素）。
    """
    from difflib import SequenceMatcher

    lines = text.split("\n")
    out: list[str] = []
    prev_norm: str = ""
    prev_ln: str = ""
    for ln in lines:
        # 字符级兜底去重（处理页眉重影）
        ln = dedup_chars_line(ln)

        if is_trivial_line(ln):
            continue

        norm = normalize_line(ln)
        if not norm:
            if out and out[-1] != "":
                out.append("")
            prev_norm = ""
            prev_ln = ""
            continue

        if prev_norm:
            # 相似度判断：处理 OCR 错字差异
            ratio = SequenceMatcher(None, norm, prev_norm).ratio()
            if ratio > 0.90:
                # 视为重复，保留较长
                if len(ln) > len(prev_ln):
                    if out:
                        out[-1] = ln
                        prev_ln = ln
                        prev_norm = norm
                continue

        out.append(ln)
        prev_norm = norm
        prev_ln = ln
    return "\n".join(out)


def clean_page_text(text: str) -> str:
    """页面文本后处理：字符级兜底 + 行级去重 + 多空行压缩。"""
    if not text:
        return ""
    text = dedup_consecutive_lines(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ===== 章节切片 =====

# 章节标题识别模式（按优先级）
CHAPTER_PATTERNS = [
    re.compile(r"^\s*第\s*([一二三四五六七八九十百千零\d]+)\s*章\s*(.*)$", re.MULTILINE),
    re.compile(r"^\s*第\s*([一二三四五六七八九十百千零\d]+)\s*节\s*(.*)$", re.MULTILINE),
    re.compile(r"^\s*Chapter\s+(\d+)\s*[:：.]\s*(.*)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*(\d+)\.\s*([^\n]{2,80})$", re.MULTILINE),  # 1. 标题
]


def cn_num_to_int(s: str) -> int:
    """把'一二三...'转成数字。"""
    table = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,
             "十一":11,"十二":12,"十三":13,"十四":14,"十五":15,"十六":16,"十七":17,
             "十八":18,"十九":19,"二十":20,"零":0}
    s = s.strip()
    if s.isdigit():
        return int(s)
    return table.get(s, 0)


@dataclass
class Chapter:
    number: int
    title: str
    pages: tuple[int, int]
    text: str = ""


def split_chapters(pages_text: list[str], book_slug: str) -> list[Chapter]:
    """按章节标题切分整本书的页面文本。"""
    if not pages_text:
        return []

    page_count = len(pages_text)
    chapter_marks: list[tuple[int, int, int, str]] = []  # (page_idx, char_offset, number, title)

    for page_idx, page_text in enumerate(pages_text):
        for pat in CHAPTER_PATTERNS:
            for m in pat.finditer(page_text):
                title = (m.group(2) or "").strip() or m.group(0).strip()
                num_str = m.group(1)
                num = cn_num_to_int(num_str) or (len(chapter_marks) + 1)
                # 过滤误判：标题不太短也不太长
                full = m.group(0).strip()
                if 3 <= len(full) <= 100:
                    chapter_marks.append((page_idx, m.start(), num, title))
                    break  # 同页同模式只取第一个

    if not chapter_marks:
        # 找不到章节标题，把整本书作为一个章节
        return [
            Chapter(
                number=1,
                title=book_slug,
                pages=(1, page_count),
                text="\n\n".join(t for t in pages_text if t),
            )
        ]

    # 去重（同一页同一位置只保留一次）
    seen: set[tuple[int, int]] = set()
    unique: list[tuple[int, int, int, str]] = []
    for mark in chapter_marks:
        key = (mark[0], mark[1])
        if key not in seen:
            seen.add(key)
            unique.append(mark)
    chapter_marks = unique

    chapters: list[Chapter] = []
    for i, (page_idx, char_offset, num, title) in enumerate(chapter_marks):
        if i + 1 < len(chapter_marks):
            next_page, next_offset, _, _ = chapter_marks[i + 1]
        else:
            next_page, next_offset = page_count - 1, len(pages_text[-1]) if pages_text else 0

        parts: list[str] = []
        for p in range(page_idx, next_page + 1):
            page_text = pages_text[p] or ""
            if p == page_idx and p == next_page:
                parts.append(page_text[char_offset:next_offset])
            elif p == page_idx:
                parts.append(page_text[char_offset:])
            elif p == next_page:
                parts.append(page_text[:next_offset])
            else:
                parts.append(page_text)

        chapters.append(
            Chapter(
                number=num,
                title=title,
                pages=(page_idx + 1, next_page + 1),
                text="\n\n".join(p for p in parts if p),
            )
        )

    # 第一个章节标记之前的内容（前言/目录）
    if chapter_marks[0][0] > 0 or chapter_marks[0][1] > 0:
        front_parts: list[str] = []
        first_page, first_offset, _, _ = chapter_marks[0]
        for p in range(0, first_page + 1):
            page_text = pages_text[p] or ""
            if p == first_page:
                front_parts.append(page_text[:first_offset])
            else:
                front_parts.append(page_text)
        front_text = "\n\n".join(t for t in front_parts if t.strip())
        if len(front_text) > 200:
            chapters.insert(0, Chapter(
                number=0,
                title="前言与目录",
                pages=(1, first_page + 1),
                text=front_text,
            ))

    return chapters


# ===== 主流程 =====

def safe_slug(title: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]", "-", title, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len]


def extract_book(pdf_path: Path, slug: str, title: str, lang: str) -> None:
    if slug in SEEN_SLUGS:
        print(f"  [skip] 已处理过 {slug}（重复文件）")
        return
    SEEN_SLUGS.add(slug)

    out_dir = RAW_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [extract] {slug} <- {pdf_path.name}")

    # 写 _meta.md
    (out_dir / "_meta.md").write_text(
        f"---\n"
        f"type: raw-book\n"
        f"slug: @{slug}\n"
        f"title: {title}\n"
        f"lang: {lang}\n"
        f"source_pdf: {pdf_path.name}\n"
        f"ingested_at: 2026-09-03\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"本教材已按章节切片为本目录下的 markdown 文件。"
        f"原始 PDF 位于 `../../{pdf_path.name}`。\n",
        encoding="utf-8",
    )

    pages_text: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = extract_page_text(page)
            txt = clean_page_text(txt)
            pages_text.append(txt)

    chapters = split_chapters(pages_text, slug)
    print(f"    -> {len(chapters)} 章")

    for ch in chapters:
        nn = f"{ch.number:02d}"
        ch_slug = safe_slug(ch.title)
        fname = f"{nn}-{ch_slug}.md"
        fpath = out_dir / fname

        frontmatter = (
            "---\n"
            f"type: raw-chapter\n"
            f"book: @{slug}\n"
            f"chapter: {ch.number}\n"
            f"chapter_title: {ch.title}\n"
            f"pages: {ch.pages[0]}-{ch.pages[1]}\n"
            f"lang: {lang}\n"
            f"ocr_cleaned: true\n"
            f"ingested_at: 2026-09-03\n"
            "---\n\n"
        )
        content = frontmatter + f"# {ch.title}\n\n" + ch.text
        fpath.write_text(content, encoding="utf-8")
        print(f"    -> {fname} ({len(ch.text)} chars)")


def discover_pdfs() -> list[Path]:
    """枚举所有待处理的 PDF。只取 OCR 版（[OCR]_ 前缀），跳过 0 字节和原始扫描版。"""
    pdfs = []
    for p in SOURCE_DIR.glob("*.pdf"):
        if not p.name.startswith("[OCR]_"):
            continue
        if p.stat().st_size == 0:
            print(f"  [skip] 0 bytes: {p.name}")
            continue
        pdfs.append(p)
    return pdfs


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="西方文论教材 PDF -> markdown")
    parser.add_argument("only", nargs="?", default=None,
                        help="只处理指定 slug 的教材")
    args = parser.parse_args()

    print("=" * 60)
    print("西方文论教材 PDF -> markdown 提取 (v2)")
    print("=" * 60)
    print(f"源目录: {SOURCE_DIR}")
    print(f"输出目录: {RAW_ROOT}")
    print()

    pdfs = discover_pdfs()
    print(f"发现 {len(pdfs)} 个有效 PDF\n")

    success = 0
    failed = []
    for pdf in sorted(pdfs):
        entry = BOOK_MAP.get(pdf.name)
        if not entry:
            print(f"  [warn] 未在 BOOK_MAP 注册: {pdf.name}")
            slug = pdf.stem.replace("[OCR]_", "").replace("_20260903", "").replace(" ", "-")[:30]
            title, lang = slug, "zh"
        else:
            slug, title, lang = entry

        if args.only and args.only != slug:
            continue

        try:
            extract_book(pdf, slug, title, lang)
            success += 1
        except Exception as e:
            print(f"  [error] {slug}: {e}")
            failed.append((slug, str(e)))

    print()
    print(f"完成: {success} 本成功, {len(failed)} 本失败")
    if failed:
        for slug, err in failed:
            print(f"  - {slug}: {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
