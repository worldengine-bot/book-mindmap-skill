#!/usr/bin/env python3
"""
parse_book.py — 统一书籍解析入口
支持 PDF（pymupdf）· EPUB（ebooklib）· DOCX（python-docx）· TXT / Markdown
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path


# ═══════════════════════════════════════════════════════════
# 各格式解析器
# ═══════════════════════════════════════════════════════════

def parse_pdf(path: str) -> str:
    """用 pymupdf 提取 PDF 文本，保留页码标记和基本布局。"""
    try:
        import fitz
    except ImportError:
        sys.exit("请先安装 pymupdf：pip install pymupdf")

    doc = fitz.open(path)
    total = len(doc)
    pages: list[str] = []

    for i, page in enumerate(doc, 1):
        # 文本块模式保留段落结构
        text = page.get_text("text").strip()
        if text:
            pages.append(f"[第{i}页]\n{text}")
        if total > 50 and i % 50 == 0:
            print(f"  📖 PDF 解析进度：{i}/{total} 页 ({i*100//total}%)")

    doc.close()
    return "\n\n".join(pages)


def parse_epub(path: str) -> str:
    """用 ebooklib 解析 EPUB，按文档顺序拼接章节。"""
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("请先安装依赖：pip install ebooklib beautifulsoup4")

    book = epub.read_epub(path)
    items = list(book.get_items())
    chapters: list[str] = []

    for item in items:
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            # 提取最高级标题
            title_tag = soup.find(["h1", "h2", "h3"])
            title = title_tag.get_text(strip=True) if title_tag else ""
            body = soup.get_text(separator="\n", strip=True)
            if len(body) > 100:
                header = f"=== {title} ===" if title else ""
                chapters.append(f"{header}\n{body}" if header else body)

    return "\n\n".join(chapters)


def parse_docx(path: str) -> str:
    """用 python-docx 解析 Word 文档，保留标题层级。"""
    try:
        from docx import Document
    except ImportError:
        sys.exit("请先安装依赖：pip install python-docx")

    doc = Document(path)
    lines: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if "Heading 1" in style:
            lines.append(f"# {text}")
        elif "Heading 2" in style:
            lines.append(f"## {text}")
        elif "Heading 3" in style:
            lines.append(f"### {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def parse_text(path: str) -> str:
    """直接读取 TXT / MD 文件。"""
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


# ═══════════════════════════════════════════════════════════
# 分块工具
# ═══════════════════════════════════════════════════════════

def chunk_text(text: str, max_chars: int = 12000) -> list[str]:
    """按段落边界将长文本切分为块，尽可能保持段落完整。

    用于超长文本的预处理——当一本书的文本超过 DeepSeek
    上下文窗口时，可以用此函数拆分为多个 chunk 分段输入。

    注意：当前流水线中，章节切分（split_chapters）已做了
    更智能的边界识别，此函数主要用于 fallback 场景。
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > max_chars and current:
            chunks.append("\n\n".join(current).strip())
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current).strip())

    return chunks


# ═══════════════════════════════════════════════════════════
# 分派表
# ═══════════════════════════════════════════════════════════

PARSERS = {
    ".pdf":  parse_pdf,
    ".epub": parse_epub,
    ".docx": parse_docx,
    ".doc":  parse_docx,
    ".txt":  parse_text,
    ".md":   parse_text,
    ".markdown": parse_text,
}


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="解析书籍文件 → 纯文本")
    parser.add_argument("input", help="书籍文件路径")
    parser.add_argument("--output", default="/tmp/book2mindmap/book_text.txt", help="输出路径")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        sys.exit(f"❌ 文件不存在：{path}")

    suffix = path.suffix.lower()
    if suffix not in PARSERS:
        sys.exit(f"❌ 不支持的格式：{suffix}\n   支持：PDF / EPUB / DOCX / TXT / MD")

    print(f"📖 解析：{path.name}（{suffix}）")

    text = PARSERS[suffix](str(path))

    # 输出
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    char_count = len(text)
    est_tokens = char_count // 2  # 中文约 2 字符/token，英文约 4 字符/token 取折中
    chunk_count = len(chunk_text(text))

    print(f"✅ 解析完成：{char_count:,} 字符 · 约 {est_tokens:,} tokens · 可分 {chunk_count} 块")
    print(f"📄 输出：{out}")


if __name__ == "__main__":
    main()
