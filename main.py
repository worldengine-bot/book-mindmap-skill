#!/usr/bin/env python3
"""
main.py — 📚 书籍 → XMind 思维导图（一键流水线）
================================================
用法：
  # 默认（detailed 模式，Markdown 输出）
  python main.py 深度工作.pdf

  # 快速概览模式（最省 token，适合超大书）
  python main.py 思考快与慢.epub --mode summary

  # 学术级深度分析
  python main.py 纯粹理性批判.pdf --mode comprehensive --genre philosophy

  # 输出 OPML（MindNode / FreeMind 兼容）
  python main.py mybook.txt --format opml

  # 同时输出 Markdown + OPML
  python main.py mybook.pdf --format both

  # 指定流派 + 断点续跑 + 自定义并发
  python main.py book.pdf --genre tech --checkpoint --workers 12
"""

from __future__ import annotations

import sys
import time
import argparse
import subprocess
from pathlib import Path

# ── 项目根目录（用于定位 scripts/）──────────────────────
ROOT = Path(__file__).resolve().parent


def run_step(cmd: list[str], label: str, step: str) -> int:
    """运行一个子进程步骤，打印清晰的头部信息。stdout 实时输出，stderr 捕获用于错误提示。"""
    header = f"{'='*56}\n  {step}  ▶  {label}\n{'='*56}"
    print(f"\n{header}")
    start = time.monotonic()
    result = subprocess.run(cmd, check=False, stderr=subprocess.PIPE, text=True)
    elapsed = time.monotonic() - start
    if result.returncode != 0:
        print(f"\n❌ {label} 失败（退出码 {result.returncode}）")
        if result.stderr:
            print(f"--- stderr ---\n{result.stderr[:800]}")
        sys.exit(result.returncode)
    print(f"⏱️  耗时 {elapsed:.1f}s")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="📚 书籍 → XMind 思维导图（DeepSeek API）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
读前路线图（推荐）：
  python main.py 书.pdf --purpose pre-read

读后知识总结：
  python main.py 书.pdf                          # 默认 detailed
  python main.py 书.pdf --mode comprehensive      # 学术级
  python main.py 书.pdf --genre tech --format both # 双格式
        """,
    )

    # ── 必选参数 ──
    parser.add_argument("book", help="书籍文件路径（支持 PDF / EPUB / DOCX / TXT / MD）")

    # ── 输出控制 ──
    parser.add_argument("--output", "-o", help="输出文件路径（默认 ./output/<书名>_mindmap.md）")
    parser.add_argument(
        "--format", "-f", default="markdown",
        choices=["markdown", "opml", "html", "html-full", "both"],
        help="输出格式（默认 markdown）。html=基础交互知识图谱 | html-full=多Tab全景布局（推荐comprehensive+detailled模式）",
    )

    # ── 分析控制 ──
    parser.add_argument(
        "--purpose", "-p", default="post-read",
        choices=["pre-read", "post-read"],
        help="使用目的（默认 post-read）。pre-read=读前路线图 | post-read=读后知识总结",
    )
    parser.add_argument(
        "--mode", "-m", default="detailed",
        choices=["summary", "standard", "detailed", "comprehensive"],
        help="详细程度（默认 detailed）。仅 post-read 模式生效。summary=最简・最省token | "
             "standard=标准 | detailed=深入（推荐） | comprehensive=学术级",
    )
    parser.add_argument(
        "--genre", "-g", default="auto",
        choices=["auto", "business", "philosophy", "tech", "literature", "academic", "self-help"],
        help="书籍流派（默认 auto 自动检测）",
    )
    parser.add_argument("--lang", "-l", default="zh", choices=["zh", "en", "auto"],
                        help="输出语言（默认 zh）")

    # ── 性能控制 ──
    parser.add_argument("--workers", "-w", type=int, default=8,
                        help="并发 API 调用数（默认 8，调大可加速但需注意 rate limit）")
    parser.add_argument("--checkpoint", action="store_true",
                        help="启用断点续跑（处理中断后可从已完成章节恢复）")

    # ── 高级 ──
    parser.add_argument("--tmp-dir", default="/tmp/book2mindmap",
                        help="临时文件目录（默认 /tmp/book2mindmap）")
    parser.add_argument("--keep-tmp", action="store_true",
                        help="保留临时文件（调试用）")
    parser.add_argument("--synthesize", action="store_true", default=None,
                        help="执行跨章节综合分析。comprehensive 模式默认开启。")

    args = parser.parse_args()

    # ── 文件存在性检查 ──
    book_path = Path(args.book).resolve()
    if not book_path.exists():
        sys.exit(f"❌ 文件不存在：{book_path}")

    book_name = book_path.stem
    tmp = Path(args.tmp_dir)
    tmp.mkdir(parents=True, exist_ok=True)

    text_path = tmp / "book_text.txt"
    summary_path = tmp / "summaries.json"

    # ── 输出路径 ──
    if args.output:
        out_path = Path(args.output)
        md_path = out_path if out_path.suffix == ".md" else out_path.with_suffix(".md")
        opml_path = out_path if out_path.suffix == ".opml" else out_path.with_suffix(".opml")
        html_path = out_path if out_path.suffix == ".html" else out_path.with_suffix(".html")
    else:
        md_path = Path(f"./output/{book_name}_mindmap.md")
        opml_path = Path(f"./output/{book_name}_mindmap.opml")
        html_path = Path(f"./output/{book_name}_mindmap.html")

    # ── 打印配置 ──
    purpose_label = "🧭 读前路线图" if args.purpose == "pre-read" else "📝 读后总结"

    # 跨章综合：comprehensive 模式默认开启
    if args.synthesize is None:
        args.synthesize = (args.purpose == "post-read" and args.mode == "comprehensive")

    print("╔" + "═" * 54 + "╗")
    print(f"║  📚 {book_name[:40]:<46s} ║")
    print(f"║  {purpose_label:<44s} ║")
    if args.purpose == "post-read":
        print(f"║  📊 深度：{args.mode:<10s}  流派：{args.genre:<10s}  格式：{args.format:<8s} ║")
    else:
        print(f"║  🏷️  流派：{args.genre:<10s}  格式：{args.format:<8s}                    ║")
    print(f"║  ⚡ 并发：{args.workers} 线程  {'🔁 断点续跑' if args.checkpoint else '':>20s} ║")
    if args.synthesize:
        print(f"║  🧠 跨章综合分析（融会贯通）{'':>22s} ║")
    print("╚" + "═" * 54 + "╝")

    start_all = time.monotonic()

    # ────────────────────────────────────────────────────
    # Step 1：解析书籍 → 纯文本
    # ────────────────────────────────────────────────────
    run_step(
        [sys.executable, str(ROOT / "scripts" / "parse_book.py"),
         str(book_path), "--output", str(text_path)],
        label="解析书籍内容",
        step="Step 1/3",
    )

    # ────────────────────────────────────────────────────
    # Step 2：逐章摘要（DeepSeek API）
    # ────────────────────────────────────────────────────
    cmd2 = [
        sys.executable, str(ROOT / "scripts" / "summarize_chapters.py"),
        "--text", str(text_path),
        "--output", str(summary_path),
        "--purpose", args.purpose,
        "--mode", args.mode,
        "--genre", args.genre,
        "--lang", args.lang,
        "--max-workers", str(args.workers),
    ]
    if args.checkpoint:
        cmd2.append("--checkpoint")
    if args.synthesize:
        cmd2.append("--synthesize")

    run_step(cmd2, label=f"逐章摘要（DeepSeek API）{' + 跨章综合分析' if args.synthesize else ''}", step="Step 2/3")

    # ────────────────────────────────────────────────────
    # Step 3：构建思维导图
    # ────────────────────────────────────────────────────

    if args.format in ("markdown", "both"):
        run_step(
            [sys.executable, str(ROOT / "scripts" / "build_mindmap.py"),
             "--summaries", str(summary_path),
             "--output", str(md_path),
             "--format", "markdown"],
            label="构建 Markdown 思维导图",
            step="Step 3/3",
        )

    if args.format in ("opml", "both"):
        run_step(
            [sys.executable, str(ROOT / "scripts" / "build_mindmap.py"),
             "--summaries", str(summary_path),
             "--output", str(opml_path),
             "--format", "opml"],
            label="构建 OPML 思维导图",
            step="Step 3/3 (OPML)",
        )

    if args.format == "html":
        run_step(
            [sys.executable, str(ROOT / "scripts" / "build_mindmap.py"),
             "--summaries", str(summary_path),
             "--output", str(html_path),
             "--format", "html"],
            label="构建 HTML 交互式知识图谱（4 Tab）",
            step="Step 3/3 (HTML)",
        )

    if args.format == "html-full":
        run_step(
            [sys.executable, str(ROOT / "scripts" / "build_mindmap.py"),
             "--summaries", str(summary_path),
             "--output", str(html_path),
             "--format", "html-full"],
            label="构建 HTML 全景知识图谱（多 Tab 每 Part 独立）",
            step="Step 3/3 (HTML-Full)",
        )

    # ── 清理临时文件 ──
    if not args.keep_tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    # ── 完成提示 ──
    total_elapsed = time.monotonic() - start_all
    print(f"\n{'🎉' * 3}  全部完成！总耗时 {total_elapsed:.1f}s  {'🎉' * 3}")

    if args.format in ("markdown", "both"):
        print(f"📄 Markdown：{md_path.resolve()}")
    if args.format in ("opml", "both"):
        print(f"📄 OPML：    {opml_path.resolve()}")
    if args.format in ("html", "html-full"):
        print(f"🌐 HTML：    {html_path.resolve()}")
        print("   用浏览器打开即可交互浏览，点击右上角 ☀️/🌙 切换主题")
        if args.format == "html-full":
            print("   📑 多 Tab 全景布局——每 Part 独立展示")

    if args.purpose == "pre-read":
        print("\n📥 使用方法：")
        print("   1. XMind → 文件 → 导入 → Markdown")
        print("   2. 开始读书，边读边在思维导图中填空、勾选、批注")
        print("   3. 读完这本书，这份导图就是你的个人阅读笔记 🎯")
    else:
        print("\n📥 导入 XMind：")
        print("   文件 → 导入 → Markdown（或 OPML）→ 选择上方文件")
        print("   Obsidian 用户：直接放入 vault，配合 Mind Map 插件渲染")
        print("   Logseq 用户：复制大纲内容粘贴即可")


if __name__ == "__main__":
    main()
