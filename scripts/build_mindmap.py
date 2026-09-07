#!/usr/bin/env python3
"""
build_mindmap.py — 将摘要 JSON 转换为 XMind / Obsidian 兼容的思维导图格式。
支持：
  - Markdown 大纲（XMind 导入、Obsidian Mind Map 插件）
  - OPML（MindNode、FreeMind、XMind 均支持）
  - 专为 XMind 高级版优化的富文本节点（emoji 标记、块引用笔记、标签）
"""

from __future__ import annotations

import json
import argparse
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString


# ── 中国数字（支持到 99）─────────────────────────────────
_CN_UNITS = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
             "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
             "二十一", "二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八", "二十九", "三十",
             "三十一", "三十二", "三十三", "三十四", "三十五", "三十六", "三十七", "三十八", "三十九", "四十"]

def _cn_num(n: int) -> str:
    """数字转中文序号（1→一, 11→十一, 40→四十）。"""
    if 1 <= n < len(_CN_UNITS):
        return _CN_UNITS[n]
    return str(n)

# ── 流派图标的 Unicode 映射 ─────────────────────────────
GENRE_ICON: dict[str, str] = {
    "business":    "💼",
    "philosophy":  "🧠",
    "tech":        "💻",
    "literature":  "📖",
    "academic":    "🎓",
    "self-help":   "🌱",
    "auto":        "📚",
}

# ── 节点类型图标 ─────────────────────────────────────────
TYPE_ICON: dict[str, str] = {
    "theory":       "🧩",
    "case":         "📋",
    "application":  "🔧",
    "introduction": "🚪",
    "summary":      "📝",
    "core":         "⭐",
    "supporting":  "▫️",
    "study":        "🔬",
    "data":         "📊",
    "anecdote":     "💬",
    "thought_experiment": "💭",
    "historical":   "📜",
    "logic":        "🔗",
    "authority":    "🎯",
    "strong":       "✅",
    "moderate":     "🔹",
    "weak":         "🔸",
}

# ── 读前模式 —— 章节角色图标 ──────────────────────────
ROLE_ICON: dict[str, str] = {
    "foundation":     "🧱",
    "core_argument":  "⭐",
    "case_study":     "📋",
    "application":    "🔧",
    "summary":        "📝",
    "bridge":         "🌉",
}

DIFFICULTY_BAR: dict[str, str] = {
    "easy":        "🟢 轻松 · 预计",
    "moderate":    "🟡 适中 · 预计",
    "challenging": "🟠 有挑战 · 预计",
}


# ═══════════════════════════════════════════════════════════
# Markdown 构建器（XMind 优化）
# ═══════════════════════════════════════════════════════════

def _esc(text: str) -> str:
    """转义 Markdown 特殊字符（避免破坏格式）。"""
    return text.replace("*", "\\*").replace("#", "\\#").replace("|", "\\|")

def _trim(text: str, max_len: int = 120) -> str:
    """截断过长文本。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"

def _s(val) -> str:
    """安全获取字符串值，兼容 LLM 偶尔返回的 list/dict。"""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return "；".join(str(v) for v in val if v)
    return str(val).strip()


def build_markdown(data: dict) -> str:
    """生成专为 XMind 高级版优化的 Markdown 大纲。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")

    title = structure.get("title", "书籍思维导图")
    genre_icon = GENRE_ICON.get(genre, "📚")
    lines: list[str] = []

    # ── 中心主题 ──
    lines.append(f"# {genre_icon} 《{title}》思维导图\n")

    # ── 一、全书概览（富信息） ──
    lines.append("## 一、📋 全书概览\n")

    if structure.get("one_line_summary"):
        lines.append(f"- 💡 核心主旨：{_esc(structure['one_line_summary'])}")
    if structure.get("core_theme"):
        lines.append(f"- 🏷️ 主题范畴：{_esc(structure['core_theme'])}")
    if structure.get("target_audience"):
        lines.append(f"- 👥 适合读者：{_esc(structure['target_audience'])}")
    if structure.get("writing_style"):
        lines.append(f"- ✍️ 写作风格：{_esc(structure['writing_style'])}")
    if structure.get("structure_type"):
        lines.append(f"- 🏗️ 结构类型：{_esc(structure['structure_type'])}")
    if structure.get("reading_complexity"):
        complexity_map = {"easy": "🟢 轻松", "moderate": "🟡 适中", "challenging": "🟠 有挑战", "dense": "🔴 密集"}
        lines.append(f"- 📖 阅读难度：{complexity_map.get(structure['reading_complexity'], structure['reading_complexity'])}")

    # 流派说明
    genre_desc = {
        "business": "商业/管理", "philosophy": "哲学/思想", "tech": "技术/工程",
        "literature": "文学/叙事", "academic": "学术/研究", "self-help": "自我提升",
    }
    if genre in genre_desc:
        lines.append(f"- 📂 书籍流派：{genre_desc[genre]}")

    lines.append("")

    # ── 按部分组织章节（先按章节号排序，保证输出顺序与书籍一致）──
    parts: dict[str, list[dict]] = {}
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    part_index = 0
    for part_name, part_chapters in parts.items():
        # 获取该部分的 summary（可能有）
        part_summary = ""
        for ch in part_chapters:
            if ch.get("part_summary"):
                part_summary = ch["part_summary"]
                break

        prefix = _cn_num(part_index + 2)
        lines.append(f"## {prefix}、📂 {_esc(part_name)}\n")
        if part_summary:
            lines.append(f"> {_esc(part_summary)}\n")
        part_index += 1

        for chap in part_chapters:
            summary = chap.get("summary", {})
            ch_title = chap.get("title", f"第{chap.get('number', '?')}章")
            ch_num = chap.get("number", "?")
            ch_type = chap.get("chapter_type", "theory")
            ch_icon = TYPE_ICON.get(ch_type, "📄")

            lines.append(f"### {ch_icon} 第{ch_num}章：{_esc(ch_title)}\n")

            # ── 一句话总结（核心摘要节点）──
            one_sentence = summary.get("one_sentence", "")
            if one_sentence:
                lines.append(f"- 🎯 TL;DR：{_esc(one_sentence)}")
                lines.append("")

            # ── 论纲结构（如有）──
            arg_struct = summary.get("argument_structure")
            if arg_struct:
                lines.append("- 🧩 论证结构")
                if arg_struct.get("type"):
                    lines.append(f"  - 类型：{arg_struct['type']}")
                premises = arg_struct.get("premises", [])
                if premises:
                    lines.append(f"  - 前提：{'；'.join(_esc(p) for p in premises[:4])}")
                if arg_struct.get("reasoning_chain"):
                    lines.append(f"  - 推理链：{_esc(_trim(arg_struct['reasoning_chain'], 150))}")
                if arg_struct.get("conclusion"):
                    lines.append(f"  - 结论：{_esc(arg_struct['conclusion'])}")
                lines.append("")

            # ── 核心论点 ──
            key_args = summary.get("key_arguments", [])
            if key_args:
                lines.append("- ⭐ 核心论点")
                for a in key_args:
                    if a and a.strip():
                        lines.append(f"  - {_esc(_trim(a.strip(), 150))}")
                lines.append("")

            # ── 支撑论点（detailed+ 模式）──
            supporting = summary.get("supporting_points", [])
            if supporting:
                lines.append("- ▫️ 支撑论点")
                for sp in supporting:
                    if isinstance(sp, dict):
                        point = sp.get("point", "")
                        etype = sp.get("evidence_type", "")
                        icon = TYPE_ICON.get(etype, "▫️")
                        if point:
                            lines.append(f"  - {icon} {_esc(_trim(point, 120))}")
                    elif sp and str(sp).strip():
                        lines.append(f"  - {_esc(_trim(str(sp), 120))}")
                lines.append("")

            # ── 关键概念 ──
            concepts = summary.get("concepts", [])
            if concepts:
                lines.append("- 📖 关键概念")
                for c in concepts[:8]:
                    term = c.get("term", "")
                    definition = c.get("definition", "")
                    importance = c.get("importance", "")
                    icon = "⭐" if importance == "core" else "▫️"
                    if term:
                        entry = f"  - {icon} **{_esc(term)}**"
                        if definition:
                            entry += f"：{_esc(definition)}"
                        lines.append(entry)
                        # 常见误解（comprehensive 模式）
                        misunderstanding = c.get("common_misunderstanding", "")
                        if misunderstanding:
                            lines.append(f"    - ⚠️ 注意：{_esc(_trim(misunderstanding, 100))}")
                        # 关联术语
                        related = c.get("related_to", [])
                        if related and isinstance(related, list) and len(related) > 0:
                            lines.append(f"    - 🔗 关联：{' · '.join(_esc(r) for r in related[:5])}")
                lines.append("")

            # ── 论据/证据（表格模式）──
            evidence_table = summary.get("evidence_table")
            if evidence_table:
                lines.append("- 📊 支撑论据")
                cols = evidence_table.get("columns", [])
                if cols:
                    lines.append("  | " + " | ".join(_esc(c) for c in cols) + " |")
                    lines.append("  |" + "|".join("---" for _ in cols) + "|")
                for row in evidence_table.get("rows", []):
                    lines.append("  | " + " | ".join(_esc(str(c)) for c in row) + " |")
                lines.append("")

            # ── 论据/证据（列表模式）──
            evidence = summary.get("evidence", [])
            if evidence:
                lines.append("- 📊 支撑论据")
                for ev in evidence[:20]:
                    if isinstance(ev, dict):
                        desc = ev.get("description", "")
                        etype = ev.get("type", "")
                        strength = ev.get("strength", "")
                        icon = TYPE_ICON.get(etype, "📊")
                        sicon = TYPE_ICON.get(strength, "")
                        line = f"  - {icon} {_esc(_trim(desc, 400))}"
                        if sicon:
                            line += f" [{sicon}]"
                        lines.append(line)
                    elif ev and str(ev).strip():
                        lines.append(f"  - {_esc(_trim(str(ev), 400))}")
                lines.append("")

            # ── 案例 ──
            examples = summary.get("examples", [])
            if examples:
                lines.append("- 📋 典型案例")
                for ex in examples[:4]:
                    ex_text = ex if isinstance(ex, str) else ex.get("description", str(ex))
                    if ex_text and ex_text.strip():
                        lines.append(f"  - {_esc(_trim(ex_text.strip(), 150))}")
                lines.append("")

            # ── 引文（detailed+ 模式）──
            quotes = summary.get("quotes", [])
            if quotes:
                lines.append("- 💬 关键引文")
                for q in quotes[:3]:
                    if isinstance(q, dict):
                        q_text = q.get("text", "")
                        q_sig = q.get("significance", "")
                        if q_text:
                            lines.append(f"  - 「{_esc(_trim(q_text, 150))}」")
                            if q_sig:
                                lines.append(f"    > {_esc(q_sig)}")
                    elif q and str(q).strip():
                        lines.append(f"  - 「{_esc(_trim(str(q), 150))}」")
                lines.append("")

            # ── 论证逻辑流 ──
            logic = _s(summary.get("logic_flow", ""))
            if logic:
                lines.append(f"- 🔗 论证逻辑：{_esc(_trim(logic, 150))}")
                lines.append("")

            # ── 反方观点 / 局限 ──
            counter = summary.get("counterarguments", [])
            limitations = summary.get("limitations", [])
            critique = _s(summary.get("critique", ""))
            if counter or limitations or critique:
                lines.append("- ⚠️ 质疑与局限")
                for ca in counter[:3]:
                    if ca and str(ca).strip():
                        lines.append(f"  - {_esc(_trim(str(ca), 130))}")
                for lim in limitations[:3]:
                    if lim and str(lim).strip():
                        lines.append(f"  - {_esc(_trim(str(lim), 130))}")
                if critique:
                    lines.append(f"  - 💬 {_esc(_trim(critique, 150))}")
                lines.append("")

            # ── 跨章联系 ──
            connection_book = _s(summary.get("connection_to_book", ""))
            cross_refs = summary.get("cross_references", [])
            if connection_book:
                lines.append(f"- 🧭 全书定位：{_esc(_trim(connection_book, 120))}")
            if cross_refs:
                for cr in cross_refs[:3]:
                    if cr and str(cr).strip():
                        lines.append(f"  - 🔗 {_esc(_trim(str(cr), 120))}")
            if connection_book or cross_refs:
                lines.append("")

            # ── 实践启示 ──
            implication = _s(summary.get("practical_implication", ""))
            if implication:
                lines.append(f"- 🎯 实践启示：{_esc(_trim(implication, 150))}")
                lines.append("")

            # ── 延伸阅读 ──
            further = _s(summary.get("further_reading", ""))
            if further:
                lines.append(f"- 📚 延伸阅读：{_esc(_trim(further, 120))}")
                lines.append("")

    # ── 末章：全书总结 ──
    lines.append("---\n")
    lines.append("## 📌 全书总结与行动指南\n")
    lines.append(f"- 📖 全书主旨：{_esc(structure.get('one_line_summary', '（未识别）'))}")

    # 聚合所有章节的 practice implications
    all_implications: list[str] = []
    for ch in chapters:
        imp = _s(ch.get("summary", {}).get("practical_implication", ""))
        if imp:
            all_implications.append(imp)
    if all_implications:
        lines.append("- 🎯 核心行动建议")
        for imp in all_implications[:10]:
            lines.append(f"  - {_esc(_trim(imp, 120))}")

    lines.append("")
    lines.append("---")
    lines.append(f"> 🕐 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 🛠️ 工具：book-to-mindmap · 模型：{metadata.get('model', 'deepseek-chat')} · 模式：{metadata.get('mode', 'detailed')}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# Pre-Read Markdown 构建器（可填充的阅读路线图）
# ═══════════════════════════════════════════════════════════

def build_markdown_preread(data: dict) -> str:
    """生成读前阅读路线图 —— 可填充的思维导图模板。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")

    title = structure.get("title", "书籍思维导图")
    genre_icon = GENRE_ICON.get(genre, "📚")
    lines: list[str] = []

    # ── 中心主题 ──
    lines.append(f"# {genre_icon} 《{title}》阅读路线图\n")

    # ── 一、全书概览 ──
    lines.append("## 一、🗺️ 阅读地图总览\n")

    if structure.get("one_line_summary"):
        lines.append(f"- 🎯 核心问题：{_esc(structure['one_line_summary'])}")
    if structure.get("core_theme"):
        lines.append(f"- 🏷️ 主题范畴：{_esc(structure['core_theme'])}")
    if structure.get("target_audience"):
        lines.append(f"- 👥 目标读者：{_esc(structure['target_audience'])}")
    if structure.get("writing_style"):
        lines.append(f"- ✍️ 写作风格：{_esc(structure['writing_style'])}")
    if structure.get("structure_type"):
        lines.append(f"- 🏗️ 结构类型：{_esc(structure['structure_type'])}")
    if structure.get("reading_complexity"):
        complexity_map = {"easy": "🟢 轻松阅读", "moderate": "🟡 需要专注", "challenging": "🟠 有挑战", "dense": "🔴 需要精读"}
        lines.append(f"- 📖 整体难度：{complexity_map.get(structure['reading_complexity'], structure['reading_complexity'])}")

    genre_desc = {
        "business": "商业/管理", "philosophy": "哲学/思想", "tech": "技术/工程",
        "literature": "文学/叙事", "academic": "学术/研究", "self-help": "自我提升",
    }
    if genre in genre_desc:
        lines.append(f"- 📂 书籍流派：{genre_desc[genre]}")

    lines.append("")
    lines.append("- 💡 使用说明")
    lines.append("  - 每个章节标注了核心问题 → 带着问题去读")
    lines.append("  - 概念名已列出 → 读完用自己的话填写定义")
    lines.append("  - ☐ 读完勾选，一句话总结自己的理解")
    lines.append("  - 这份导图 = 你的个人笔记，不是AI的摘要")
    lines.append("")

    # ── 阅读策略：构建依赖图 ──
    lines.append("## 二、📋 推荐阅读顺序\n")
    # 按部分给建议（先按章节号排序）
    sorted_chapters = sorted(chapters, key=lambda c: c.get("number", 0))
    parts: dict[str, list[dict]] = {}
    for ch in sorted_chapters:
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    part_idx = 0
    all_roles: dict[str, list[str]] = {}
    for chs in parts.values():
        for ch in chs:
            s = ch.get("summary", {})
            role = s.get("chapter_role", "core_argument")
            all_roles.setdefault(role, []).append(ch.get("title", "?"))

    role_desc = {
        "foundation": "基础框架章（必读，后续依赖）",
        "core_argument": "核心论证章（建议精读）",
        "case_study": "案例章（可选择性速读）",
        "application": "应用章（按需阅读）",
        "summary": "总结章（可快速浏览）",
        "bridge": "过渡章",
    }

    for role, ctitles in all_roles.items():
        if role in role_desc:
            lines.append(f"- {ROLE_ICON.get(role, '📄')} **{role_desc[role]}**：{' · '.join(_esc(t) for t in ctitles[:5])}")

    lines.append("")

    # ── 按部分展开章节（先按章节号排序）──
    part_idx = 0
    for part_name, part_chapters in parts.items():
        part_summary = ""
        for ch in part_chapters:
            if ch.get("part_summary"):
                part_summary = ch["part_summary"]
                break

        prefix = _cn_num(part_idx + 3)
        lines.append(f"## {prefix}、📂 {_esc(part_name)}\n")
        if part_summary:
            lines.append(f"> {_esc(part_summary)}\n")
        part_idx += 1

        for chap in part_chapters:
            s = chap.get("summary", {})
            ch_title = chap.get("title", f"第{chap.get('number', '?')}章")
            ch_num = chap.get("number", "?")
            role = s.get("chapter_role", "core_argument")
            role_icon = ROLE_ICON.get(role, "📄")
            difficulty = s.get("difficulty", "moderate")
            diff_bar = DIFFICULTY_BAR.get(difficulty, "🟡")
            est_min = s.get("estimated_minutes", 15)

            lines.append(f"### {role_icon} 第{ch_num}章：{_esc(ch_title)}\n")

            # 核心问题
            core_q = s.get("core_question", "")
            if core_q:
                lines.append(f"- 🎯 **要回答的问题**：{_esc(core_q)}")
                lines.append("")

            # 为什么要读
            why = s.get("why_this_matters", "")
            if why:
                lines.append(f"- 💡 为什么重要：{_esc(why)}")
                lines.append("")

            # 阅读引导
            guide = s.get("reading_guide", "")
            if guide:
                lines.append("- 📖 阅读提示")
                lines.append(f"  > {_esc(guide)}")
                lines.append("")

            # 作者手法
            moves = s.get("author_moves", "")
            if moves:
                lines.append(f"- 🎬 论证手法：{_esc(moves)}")
                lines.append("")

            # 关键概念（只列名，留白）
            concepts = s.get("concepts_to_watch", [])
            if concepts:
                lines.append("- 🔑 关键概念（读完用自己的话补充定义）")
                for c in concepts:
                    if c and c.strip():
                        lines.append(f"  - **{_esc(c)}**：[　　　]")
                lines.append("")

            # 阅读难度 + 时间
            depends = s.get("depends_on", [])
            dep_text = ""
            if depends:
                dep_text = f" · 依赖第{'、'.join(str(d) for d in depends)}章"
            lines.append(f"- ⚡ {diff_bar} {est_min} 分钟{dep_text}")
            lines.append("")

            # 跳读建议
            skip = s.get("skip_if", "")
            if skip:
                lines.append(f"- 🏃 速读建议：{_esc(skip)}")
                lines.append("")

            # 完成后填空
            lines.append("- ☐ **已读完本章**")
            lines.append("  - 一句话总结：[　　　　　　　　　　　　　　]")
            lines.append("  - 我没想到的：[　　　　　　　　　　　　　　]")
            lines.append("  - 我可以应用的：[　　　　　　　　　　　　　　]")
            lines.append("")

    # ── 全书读完后的总结位 ──
    lines.append("---\n")
    lines.append("## 📌 全书读后总结\n")
    lines.append(f"- 📖 这本书回答了：{_esc(structure.get('one_line_summary', ''))}")
    lines.append("- 💭 我最大的收获：[　　　　　　　　　　　　　　]")
    lines.append("- ⚡ 改变了我对什么的看法：[　　　　　　　　　　　　　　]")
    lines.append("- 🔗 与哪些已有的知识产生了关联：[　　　　　　　　　　　　　　]")
    lines.append("- 📚 接下来想读的相关书：[　　　　　　　　　　　　　　]")
    lines.append("")
    lines.append("---")
    lines.append(f"> 🕐 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 🛠️ 工具：book-to-mindmap · 模型：{metadata.get('model', 'deepseek-chat')} · 模式：pre-read")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# Pre-Read OPML 构建器
# ═══════════════════════════════════════════════════════════

def build_opml_preread(data: dict) -> str:
    """生成 OPML 格式的阅读路线图。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    genre = data.get("metadata", {}).get("genre", "auto")

    title = structure.get("title", "书籍思维导图")
    genre_icon = GENRE_ICON.get(genre, "📚")

    root = Element("opml", version="2.0")
    head = SubElement(root, "head")
    SubElement(head, "title").text = f"{genre_icon} 《{title}》阅读路线图"
    SubElement(head, "dateCreated").text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    body = SubElement(root, "body")
    center = _opml_outline(body, f"{genre_icon} 《{title}》", note=structure.get("one_line_summary", ""))

    # 总览
    overview = _opml_outline(center, "🗺️ 阅读地图总览")
    if structure.get("one_line_summary"):
        _opml_outline(overview, f"🎯 {structure['one_line_summary']}")
    if structure.get("reading_complexity"):
        _opml_outline(overview, f"📖 难度：{structure['reading_complexity']}")

    # 按部分（先按章节号排序）
    parts: dict[str, list[dict]] = {}
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    part_idx = 0
    for part_name, part_chs in parts.items():
        part_summary = next((ch.get("part_summary", "") for ch in part_chs if ch.get("part_summary")), "")
        prefix = _cn_num(part_idx + 2)
        part_node = _opml_outline(center, f"{prefix}、📂 {part_name}", note=part_summary)
        part_idx += 1

        for chap in part_chs:
            s = chap.get("summary", {})
            ch_title = chap.get("title", f"第{chap.get('number','?')}章")
            ch_num = chap.get("number", "?")
            role = s.get("chapter_role", "core_argument")
            role_icon = ROLE_ICON.get(role, "📄")

            note_lines = []
            core_q = s.get("core_question", "")
            if core_q:
                note_lines.append(f"核心问题：{core_q}")
            guide = s.get("reading_guide", "")
            if guide:
                note_lines.append(f"阅读提示：{guide}")
            difficulty = s.get("difficulty", "moderate")
            est_min = s.get("estimated_minutes", 15)
            note_lines.append(f"难度：{difficulty} · 约 {est_min} 分钟")

            ch_node = _opml_outline(part_node, f"{role_icon} 第{ch_num}章：{ch_title}",
                                    note="\n".join(note_lines))

            core_q_node = _opml_outline(ch_node, f"🎯 {core_q}" if core_q else "🎯 核心问题")
            concepts = s.get("concepts_to_watch", [])
            if concepts:
                conc_node = _opml_outline(ch_node, "🔑 关键概念（填空）")
                for c in concepts:
                    if c and c.strip():
                        _opml_outline(conc_node, f"□ {c}：")
            _opml_outline(ch_node, "☐ 已读完")
            _opml_outline(ch_node, "一句话总结：[　　]")

    raw = tostring(root, encoding="unicode")
    dom = parseString(raw)
    return dom.toprettyxml(indent="  ")


# ═══════════════════════════════════════════════════════════
# OPML 构建器（_note 属性承载详细笔记）
# ═══════════════════════════════════════════════════════════

def _opml_outline(parent: Element, text: str, note: str = "", **attrs: str) -> Element:
    """创建一个 OPML outline 节点。"""
    attrib = {"text": text}
    if note:
        attrib["_note"] = note
    attrib.update(attrs)
    return SubElement(parent, "outline", attrib)


def build_opml(data: dict) -> str:
    """生成 OPML 2.0 格式（XMind / MindNode / FreeMind 兼容）。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")

    title = structure.get("title", "书籍思维导图")
    genre_icon = GENRE_ICON.get(genre, "📚")

    root = Element("opml", version="2.0")
    head = SubElement(root, "head")
    SubElement(head, "title").text = f"{genre_icon} 《{title}》思维导图"
    SubElement(head, "dateCreated").text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    body = SubElement(root, "body")

    # ── 中心主题 ──
    center = _opml_outline(body, f"{genre_icon} 《{title}》", note=structure.get("one_line_summary", ""))

    # ── 全书概览 ──
    overview = _opml_outline(center, "📋 全书概览")
    if structure.get("one_line_summary"):
        _opml_outline(overview, f"💡 {structure['one_line_summary']}")
    if structure.get("core_theme"):
        _opml_outline(overview, f"🏷️ {structure['core_theme']}")
    if structure.get("target_audience"):
        _opml_outline(overview, f"👥 {structure['target_audience']}")
    if structure.get("writing_style"):
        _opml_outline(overview, f"✍️ {structure['writing_style']}")

    # ── 按部分组织（先按章节号排序）──
    parts: dict[str, list[dict]] = {}
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    part_idx = 0
    for part_name, part_chs in parts.items():
        part_summary = next((ch.get("part_summary", "") for ch in part_chs if ch.get("part_summary")), "")
        prefix = _cn_num(part_idx + 2)
        part_node = _opml_outline(center, f"{prefix}、📂 {part_name}", note=part_summary)
        part_idx += 1

        for chap in part_chs:
            s = chap.get("summary", {})
            ch_title = chap.get("title", f"第{chap.get('number','?')}章")
            ch_num = chap.get("number", "?")
            ch_type = chap.get("chapter_type", "theory")
            ch_icon = TYPE_ICON.get(ch_type, "📄")

            ch_node = _opml_outline(part_node, f"{ch_icon} 第{ch_num}章：{ch_title}",
                                    note=s.get("one_sentence", ""))

            # 核心论点
            key_args = s.get("key_arguments", [])
            if key_args:
                args_node = _opml_outline(ch_node, "⭐ 核心论点")
                for a in key_args:
                    if a and a.strip():
                        _opml_outline(args_node, _trim(a.strip(), 150))

            # 概念
            concepts = s.get("concepts", [])
            if concepts:
                conc_node = _opml_outline(ch_node, "📖 关键概念")
                for c in concepts[:8]:
                    term = c.get("term", "")
                    definition = c.get("definition", "")
                    if term:
                        label = f"**{term}**"
                        if definition:
                            label += f"：{definition}"
                        _opml_outline(conc_node, _trim(label, 150),
                                      note=c.get("common_misunderstanding", ""))

            # 论据
            evidence = s.get("evidence", [])
            if evidence:
                ev_node = _opml_outline(ch_node, "📊 支撑论据")
                for ev in evidence[:20]:
                    if isinstance(ev, dict):
                        _opml_outline(ev_node, _trim(ev.get("description", ""), 150))
                    elif ev and str(ev).strip():
                        _opml_outline(ev_node, _trim(str(ev), 150))

            # 案例
            examples = s.get("examples", [])
            if examples:
                ex_node = _opml_outline(ch_node, "📋 典型案例")
                for ex in examples[:4]:
                    ex_text = ex if isinstance(ex, str) else ex.get("description", str(ex))
                    if ex_text and ex_text.strip():
                        _opml_outline(ex_node, _trim(ex_text.strip(), 150))

            # 引文
            quotes = s.get("quotes", [])
            if quotes:
                q_node = _opml_outline(ch_node, "💬 关键引文")
                for q in quotes[:3]:
                    if isinstance(q, dict):
                        _opml_outline(q_node, _trim(q.get("text", ""), 200),
                                      note=q.get("significance", ""))
                    elif q and str(q).strip():
                        _opml_outline(q_node, _trim(str(q), 200))

            # 逻辑 / 实践
            logic = _s(s.get("logic_flow", ""))
            if logic:
                _opml_outline(ch_node, f"🔗 论证逻辑：{_trim(logic, 150)}")

            impl = _s(s.get("practical_implication", ""))
            if impl:
                _opml_outline(ch_node, f"🎯 实践启示：{_trim(impl, 150)}")

            critique = _s(s.get("critique", ""))
            if critique:
                _opml_outline(ch_node, f"💬 评述：{_trim(critique, 150)}")

    # ── 美化 XML 输出 ──
    raw = tostring(root, encoding="unicode")
    dom = parseString(raw)
    return dom.toprettyxml(indent="  ")


# ═══════════════════════════════════════════════════════════
# 质量验证
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# HTML 构建器（交互式知识图谱，支持深色/护眼双主题）
# ═══════════════════════════════════════════════════════════

HTML_CSS = r"""
  :root {
    --bg: #0a0e17; --card-bg: #111827; --card-bg2: #1a1f2e; --border: #1e293b;
    --text: #e2e8f0; --text2: #94a3b8; --accent: #3b82f6; --accent2: #8b5cf6;
    --red: #ef4444; --amber: #f59e0b; --green: #10b981; --cyan: #06b6d4;
    --us: #3b82f6; --cn: #ef4444;
    --a03: rgba(59,130,246,0.03); --a05: rgba(59,130,246,0.05); --a08: rgba(59,130,246,0.08);
    --a10: rgba(59,130,246,0.10); --a15: rgba(59,130,246,0.15); --a30: rgba(59,130,246,0.30);
    --a2-08: rgba(139,92,246,0.08); --a2-20: rgba(139,92,246,0.20); --a2-40: rgba(139,92,246,0.40);
    --r05: rgba(239,68,68,0.05); --r08: rgba(239,68,68,0.08); --r15: rgba(239,68,68,0.15); --r30: rgba(239,68,68,0.30);
    --am05: rgba(245,158,11,0.05); --am08: rgba(245,158,11,0.08); --am15: rgba(245,158,11,0.15); --am30: rgba(245,158,11,0.30);
    --g08: rgba(16,185,129,0.08); --g15: rgba(16,185,129,0.15); --g30: rgba(16,185,129,0.30);
    --c08: rgba(6,182,212,0.08); --c15: rgba(6,182,212,0.15);
    --white02: rgba(255,255,255,0.02); --white03: rgba(255,255,255,0.03); --white05: rgba(255,255,255,0.05);
    --black20: rgba(0,0,0,0.20); --black30: rgba(0,0,0,0.30); --black40: rgba(0,0,0,0.40);
    --nav-bg: rgba(10,14,23,0.88);
    --hero-grad: radial-gradient(ellipse at center, #1a1f3a 0%, var(--bg) 70%);
    --hero-grid: rgba(59,130,246,0.03);
    --hero-title-grad: linear-gradient(135deg, #e2e8f0 0%, #60a5fa 40%, #a78bfa 70%, #e2e8f0 100%);
    --card-shadow: 0 8px 30px rgba(0,0,0,0.3); --ent-shadow: 0 15px 40px rgba(0,0,0,0.4);
  }
  [data-theme="light"] {
    --bg: #faf8f5; --card-bg: #ffffff; --card-bg2: #f3f0eb; --border: #e4e0d8;
    --text: #2d2a26; --text2: #6b6560; --accent: #2563eb; --accent2: #7c3aed;
    --red: #dc2626; --amber: #d97706; --green: #059669; --cyan: #0891b2;
    --us: #2563eb; --cn: #dc2626;
    --a03: rgba(37,99,235,0.03); --a05: rgba(37,99,235,0.05); --a08: rgba(37,99,235,0.07); --a10: rgba(37,99,235,0.08);
    --a15: rgba(37,99,235,0.10); --a30: rgba(37,99,235,0.20);
    --a2-08: rgba(124,58,237,0.06); --a2-20: rgba(124,58,237,0.12); --a2-40: rgba(124,58,237,0.24);
    --r05: rgba(220,38,38,0.04); --r08: rgba(220,38,38,0.06); --r15: rgba(220,38,38,0.10); --r30: rgba(220,38,38,0.20);
    --am05: rgba(217,119,6,0.04); --am08: rgba(217,119,6,0.06); --am15: rgba(217,119,6,0.10); --am30: rgba(217,119,6,0.20);
    --g08: rgba(5,150,105,0.06); --g15: rgba(5,150,105,0.10); --g30: rgba(5,150,105,0.20);
    --c08: rgba(8,145,178,0.06); --c15: rgba(8,145,178,0.10);
    --white02: rgba(0,0,0,0.015); --white03: rgba(0,0,0,0.02); --white05: rgba(0,0,0,0.04);
    --black20: rgba(0,0,0,0.05); --black30: rgba(0,0,0,0.08); --black40: rgba(0,0,0,0.12);
    --nav-bg: rgba(250,248,245,0.92);
    --hero-grad: radial-gradient(ellipse at center, #e8e4db 0%, var(--bg) 70%);
    --hero-grid: rgba(37,99,235,0.04);
    --hero-title-grad: linear-gradient(135deg, #2d2a26 0%, #2563eb 40%, #7c3aed 70%, #2d2a26 100%);
    --card-shadow: 0 4px 20px rgba(0,0,0,0.06); --ent-shadow: 0 8px 30px rgba(0,0,0,0.08);
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif; line-height:1.6; overflow-x:hidden; transition:background 0.4s,color 0.4s; }
  ::-webkit-scrollbar { width:6px; } ::-webkit-scrollbar-track { background:var(--bg); } ::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
  .theme-toggle { position:fixed; top:0.6rem; right:1.2rem; z-index:200; display:flex; align-items:center; gap:0.5rem; background:var(--card-bg); border:1px solid var(--border); border-radius:50px; padding:0.35rem; cursor:pointer; box-shadow:0 2px 12px rgba(0,0,0,0.08); transition:all 0.3s; user-select:none; }
  .theme-toggle:hover { border-color:var(--accent); transform:scale(1.03); }
  .theme-toggle .t-option { width:32px; height:28px; border-radius:50px; display:flex; align-items:center; justify-content:center; font-size:0.85rem; transition:all 0.3s; color:var(--text2); }
  .theme-toggle .t-option.active { background:var(--accent); color:#fff; }
  .hero { min-height:100vh; display:flex; align-items:center; justify-content:center; text-align:center; position:relative; overflow:hidden; background:var(--hero-grad); transition:background 0.5s; }
  .hero::before { content:''; position:absolute; top:0;left:0;right:0;bottom:0; background:linear-gradient(90deg,var(--hero-grid) 1px,transparent 1px),linear-gradient(0deg,var(--hero-grid) 1px,transparent 1px); background-size:60px 60px; animation:gridMove 20s linear infinite; }
  @keyframes gridMove { 0%{transform:translate(0,0)} 100%{transform:translate(60px,60px)} }
  .hero-content { position:relative; z-index:1; padding:2rem; }
  .hero-badge { display:inline-block; padding:0.4rem 1.2rem; border:1px solid var(--a30); border-radius:50px; font-size:0.85rem; color:var(--accent); margin-bottom:1.5rem; letter-spacing:0.1em; }
  .hero h1 { font-size:clamp(2.5rem,6vw,4rem); font-weight:900; background:var(--hero-title-grad); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; margin-bottom:1rem; line-height:1.2; }
  .hero h2 { font-size:clamp(1rem,2.5vw,1.3rem); color:var(--text2); font-weight:400; margin-bottom:2rem; }
  .hero-stats { display:flex; gap:2rem; justify-content:center; flex-wrap:wrap; margin:2rem 0; }
  .hero-stat { text-align:center; padding:1rem 1.5rem; background:var(--white03); border-radius:1rem; border:1px solid var(--border); }
  .hero-stat .num { font-size:2rem; font-weight:800; color:var(--accent); }
  .hero-stat .label { font-size:0.8rem; color:var(--text2); margin-top:0.2rem; }
  .scroll-hint { position:absolute; bottom:2rem; left:50%; transform:translateX(-50%); animation:bounce 2s infinite; }
  .scroll-hint svg { width:24px; height:24px; stroke:var(--text2); }
  @keyframes bounce { 0%,100%{transform:translate(-50%,0)} 50%{transform:translate(-50%,10px)} }
  .nav { position:sticky; top:0; z-index:100; background:var(--nav-bg); backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px); border-bottom:1px solid var(--border); padding:0; overflow-x:auto; -webkit-overflow-scrolling:touch; transition:background 0.4s; }
  .nav-inner { display:flex; gap:0; max-width:1400px; margin:0 auto; padding:0 5rem 0 1rem; }
  .nav-item { flex-shrink:0; padding:0.9rem 1.2rem; cursor:pointer; font-size:0.85rem; color:var(--text2); border-bottom:2px solid transparent; transition:all 0.3s; white-space:nowrap; }
  .nav-item:hover { color:var(--text); background:var(--white03); }
  .nav-item.active { color:var(--accent); border-bottom-color:var(--accent); }
  .section { max-width:1400px; margin:0 auto; padding:4rem 2rem; display:none; }
  .section.active { display:block; animation:fadeIn 0.5s ease; }
  @keyframes fadeIn { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }
  .section-title { font-size:2rem; font-weight:800; margin-bottom:1rem; display:flex; align-items:center; gap:0.8rem; }
  .section-title .icon { font-size:2.2rem; }
  .section-subtitle { color:var(--text2); font-size:1.05rem; margin-bottom:2.5rem; max-width:800px; }
  .card { background:var(--card-bg); border:1px solid var(--border); border-radius:1rem; padding:1.5rem; transition:all 0.3s; }
  .card:hover { border-color:var(--a30); transform:translateY(-2px); box-shadow:var(--card-shadow); }
  .card-title { font-weight:700; font-size:1.1rem; margin-bottom:0.8rem; }
  .card-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:1.2rem; }
  .card-grid-2 { display:grid; grid-template-columns:repeat(auto-fill,minmax(450px,1fr)); gap:1.2rem; }
  .card-grid-4 { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:1.2rem; }
  .highlight { border-left:4px solid var(--accent); padding:1rem 1.5rem; margin:1.5rem 0; background:var(--a05); border-radius:0 0.5rem 0.5rem 0; }
  .highlight.warn { border-left-color:var(--amber); background:var(--am05); }
  .highlight.danger { border-left-color:var(--red); background:var(--r05); }
  .highlight .hl-title { font-weight:700; margin-bottom:0.3rem; color:var(--accent); }
  .highlight.warn .hl-title { color:var(--amber); }
  .highlight.danger .hl-title { color:var(--red); }
  .flow-container { display:flex; align-items:center; flex-wrap:wrap; gap:0.5rem; padding:1.5rem; overflow-x:auto; font-size:0.85rem; }
  .flow-node { padding:0.7rem 1.2rem; border-radius:0.8rem; font-weight:600; flex-shrink:0; text-align:center; }
  .flow-node.dark { background:var(--card-bg2); border:1px solid var(--border); }
  .flow-node.blue { background:var(--a15); border:1px solid var(--a30); color:var(--accent); }
  .flow-node.red { background:var(--r15); border:1px solid var(--r30); color:var(--red); }
  .flow-node.amber { background:var(--am15); border:1px solid var(--am30); color:var(--amber); }
  .flow-node.green { background:var(--g15); border:1px solid var(--g30); color:var(--green); }
  .flow-arrow { color:var(--text2); font-size:1.2rem; flex-shrink:0; }
  .ent-tag { display:inline-block; font-size:0.75rem; padding:0.2rem 0.7rem; border-radius:50px; margin:0.2rem; }
  .tag-red { background:var(--r15); color:var(--red); }
  .tag-blue { background:var(--a15); color:var(--accent); }
  .tag-amber { background:var(--am15); color:var(--amber); }
  .tag-green { background:var(--g15); color:var(--green); }
  .tag-cyan { background:var(--c15); color:var(--cyan); }
  .ent-card { background:var(--card-bg); border:1px solid var(--border); border-radius:1rem; overflow:hidden; transition:all 0.3s; cursor:pointer; margin-bottom:1.2rem; }
  .ent-card:hover { transform:translateY(-3px); box-shadow:var(--ent-shadow); }
  .ent-card.huawei { border-top:4px solid var(--red); }
  .ent-card.tsmc { border-top:4px solid var(--cyan); }
  .ent-card.samsung { border-top:4px solid var(--green); }
  .ent-card.apple { border-top:4px solid var(--amber); }
  .ent-header { padding:1.5rem 1.5rem 1rem; }
  .ent-name { font-size:1.5rem; font-weight:800; }
  .ent-role { font-size:0.8rem; color:var(--text2); margin-top:0.3rem; }
  .ent-body { padding:0 1.5rem 1.5rem; }
  .accordion { border:1px solid var(--border); border-radius:0.8rem; overflow:hidden; margin-bottom:0.8rem; }
  .acc-header { padding:1rem 1.5rem; background:var(--card-bg); cursor:pointer; display:flex; align-items:center; justify-content:space-between; font-weight:600; transition:background 0.3s; user-select:none; }
  .acc-header:hover { background:var(--card-bg2); }
  .acc-header .arrow { transition:transform 0.3s; font-size:0.8rem; }
  .accordion.open .acc-header .arrow { transform:rotate(180deg); }
  .acc-body { max-height:0; overflow:hidden; transition:max-height 0.4s ease; background:var(--black20); }
  .accordion.open .acc-body { max-height:3000px; }
  .acc-content { padding:1.5rem; }
  .compare-table { width:100%; border-collapse:collapse; font-size:0.9rem; }
  .compare-table th { text-align:left; padding:0.8rem 1rem; background:var(--a10); color:var(--accent); font-weight:600; border-bottom:2px solid var(--border); }
  .compare-table td { padding:0.8rem 1rem; border-bottom:1px solid var(--border); vertical-align:top; }
  .compare-table tr:hover td { background:var(--white02); }
  .timeline { position:relative; padding-left:2rem; }
  .timeline::before { content:''; position:absolute; left:0; top:0; bottom:0; width:2px; background:linear-gradient(to bottom,var(--accent),var(--accent2),var(--red),var(--amber)); }
  .tl-item { position:relative; margin-bottom:2rem; padding:1.5rem; background:var(--card-bg); border:1px solid var(--border); border-radius:1rem; cursor:pointer; transition:all 0.3s; }
  .tl-item:hover { border-color:var(--accent); transform:translateX(5px); }
  .tl-item::before { content:''; position:absolute; left:-2.35rem; top:2rem; width:12px; height:12px; border-radius:50%; background:var(--accent); border:3px solid var(--bg); }
  .tl-item:nth-child(2)::before { background:var(--accent2); }
  .tl-item:nth-child(3)::before { background:var(--red); }
  .tl-item:nth-child(4)::before { background:var(--amber); }
  .tl-header { display:flex; align-items:center; gap:1rem; margin-bottom:0.8rem; flex-wrap:wrap; }
  .tl-era { font-size:0.8rem; font-weight:600; padding:0.3rem 0.8rem; border-radius:50px; background:var(--a15); color:var(--accent); }
  .tl-country { font-weight:800; font-size:1.1rem; }
  .concept-web { display:flex; flex-wrap:wrap; justify-content:center; gap:0.8rem; padding:2rem 0; }
  .concept-node { padding:0.6rem 1.2rem; border-radius:50px; font-weight:600; font-size:0.85rem; cursor:pointer; transition:all 0.3s; border:1px solid var(--border); background:var(--card-bg); }
  .concept-node:hover { transform:scale(1.08); border-color:var(--accent); }
  .concept-node.core { background:var(--a2-20); border-color:var(--a2-40); color:var(--accent2); }
  .fade-up { opacity:0; transform:translateY(30px); transition:all 0.6s ease; }
  .fade-up.visible { opacity:1; transform:translateY(0); }
  .progress-bar { height:6px; background:var(--border); border-radius:3px; overflow:hidden; margin:0.5rem 0; }
  .progress-fill { height:100%; border-radius:3px; transition:width 1s ease; }
  .progress-fill.high { background:var(--green); } .progress-fill.medium { background:var(--amber); } .progress-fill.low { background:var(--red); }
  @media (max-width:768px) {
    .hero h1 { font-size:2rem; } .hero-stats { gap:1rem; } .hero-stat { padding:0.8rem 1rem; } .hero-stat .num { font-size:1.5rem; }
    .card-grid,.card-grid-2,.card-grid-4 { grid-template-columns:1fr; }
    .section { padding:2rem 1rem; } .nav-inner { padding:0 4rem 0 0.5rem; } .nav-item { padding:0.7rem 0.8rem; font-size:0.75rem; }
    .flow-container { font-size:0.75rem; } .flow-node { padding:0.5rem 0.8rem; }
  }

  /* ========================================
     STAGE HEADER (argument architecture)
     ======================================== */
  .stage-header { display:flex; align-items:center; gap:1rem; margin-bottom:1.5rem; padding:1.2rem 1.5rem; background:var(--card-bg); border:1px solid var(--border); border-radius:1rem; }
  .stage-num { width:44px; height:44px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:900; font-size:1.2rem; color:#fff; flex-shrink:0; }
  .stage-num.s1 { background:var(--accent); }
  .stage-num.s2 { background:var(--accent2); }
  .stage-num.s3 { background:var(--red); }
  .stage-num.s4 { background:var(--amber); }
  .stage-num.s5 { background:var(--green); }
  .stage-info { flex:1; }
  .stage-info .stage-name { font-weight:700; font-size:1.05rem; }
  .stage-info .stage-meta { font-size:0.8rem; color:var(--text2); margin-top:0.2rem; }
  .stage-info .stage-move { font-size:0.85rem; color:var(--accent); margin-top:0.4rem; }
  .stage-chapters { display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:0.8rem; }

  /* ========================================
     DEBATE CARD
     ======================================== */
  .debate-card { background:var(--card-bg); border:1px solid var(--border); border-radius:1rem; overflow:hidden; margin-bottom:1.5rem; }
  .debate-header { padding:1.2rem 1.5rem; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:0.8rem; flex-wrap:wrap; }
  .debate-header .debate-name { font-weight:800; font-size:1.1rem; }
  .debate-nature { font-size:0.7rem; padding:0.2rem 0.6rem; border-radius:50px; font-weight:600; }
  .debate-nature.theoretical { background:var(--a15); color:var(--accent); }
  .debate-nature.practical { background:var(--am15); color:var(--amber); }
  .debate-nature.perspectival { background:var(--r15); color:var(--red); }
  .debate-positions { display:grid; grid-template-columns:1fr 1fr; gap:0; }
  .debate-pos { padding:1.5rem; }
  .debate-pos:first-child { border-right:1px solid var(--border); background:var(--a03); }
  .debate-pos .pos-side { font-weight:700; margin-bottom:0.5rem; display:flex; align-items:center; gap:0.4rem; }
  .debate-pos .pos-arg { font-size:0.85rem; color:var(--text2); }
  .debate-resolution { padding:1rem 1.5rem; border-top:1px solid var(--border); font-size:0.85rem; }
  @media (max-width:768px) { .debate-positions { grid-template-columns:1fr; } .debate-pos:first-child { border-right:none; border-bottom:1px solid var(--border); } }

  /* ========================================
     MATRIX (2x2 quadrant)
     ======================================== */
  .matrix { display:grid; grid-template-columns:1fr 1fr; grid-template-rows:auto 1fr 1fr; gap:1px; background:var(--border); border-radius:1rem; overflow:hidden; max-width:900px; margin:0 auto; }
  .matrix-label { grid-column:1/-1; display:flex; justify-content:space-between; padding:0.5rem 2rem; font-size:0.75rem; color:var(--text2); background:var(--card-bg2); }
  .matrix-cell { padding:1.5rem; background:var(--card-bg); text-align:center; cursor:pointer; transition:all 0.3s; }
  .matrix-cell:hover { background:var(--card-bg2); transform:scale(1.02); }
  .matrix-cell .m-title { font-size:1rem; font-weight:800; margin-bottom:0.3rem; }
  .matrix-cell .m-sub { font-size:0.8rem; color:var(--text2); }
  .matrix-axis-y { writing-mode:vertical-rl; text-orientation:mixed; position:absolute; left:-1.5rem; top:50%; transform:translateY(-50%); font-size:0.75rem; color:var(--text2); }

  /* ========================================
     FRAMEWORK COMPONENT CARD
     ======================================== */
  .fw-card { background:var(--card-bg); border:1px solid var(--border); border-radius:1rem; padding:1.5rem; transition:all 0.3s; position:relative; }
  .fw-card:hover { border-color:var(--a30); transform:translateY(-2px); box-shadow:var(--card-shadow); }
  .fw-card .fw-name { font-weight:700; font-size:1rem; margin-bottom:0.5rem; }
  .fw-card .fw-insight { font-size:0.85rem; color:var(--text2); margin-bottom:0.8rem; line-height:1.6; }
  .fw-metrics { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:0.5rem; }
  .fw-metric { flex:1; min-width:100px; }
  .fw-metric .fw-label { font-size:0.7rem; color:var(--text2); margin-bottom:0.2rem; text-transform:uppercase; letter-spacing:0.05em; }
  .fw-metric .fw-bar { height:6px; background:var(--border); border-radius:3px; overflow:hidden; }
  .fw-metric .fw-fill { height:100%; border-radius:3px; transition:width 1s ease; }
  .fw-fill.easy { background:var(--green); width:30%; }
  .fw-fill.moderate { background:var(--amber); width:60%; }
  .fw-fill.challenging { background:var(--red); width:90%; }
  .fw-fill.high { background:var(--green); width:85%; }
  .fw-fill.medium { background:var(--amber); width:55%; }
  .fw-fill.low { background:var(--red); width:25%; }
  .fw-source { font-size:0.7rem; color:var(--text2); margin-top:0.5rem; }
  .fw-card .fw-icon { font-size:1.5rem; margin-bottom:0.5rem; }

  /* ========================================
     EVIDENCE METER
     ======================================== */
  .evidence-meter { display:flex; gap:3px; align-items:center; }
  .evidence-meter .dot { width:8px; height:8px; border-radius:50%; background:var(--border); }
  .evidence-meter .dot.filled { background:var(--accent); }
  .evidence-meter .dot.filled.strong { background:var(--green); }
  .evidence-meter .dot.filled.moderate { background:var(--amber); }
  .evidence-meter .dot.filled.weak { background:var(--red); }

  /* ========================================
     CROSS-REFERENCE LINK
     ======================================== */
  .xref-link { display:inline-flex; align-items:center; gap:0.2rem; font-size:0.75rem; padding:0.15rem 0.5rem; border-radius:50px; background:var(--a08); color:var(--accent); cursor:pointer; transition:all 0.2s; }
  .xref-link:hover { background:var(--a15); }
"""


HTML_JS = r"""
// Theme toggle
const html = document.documentElement;
const toggle = document.getElementById('themeToggle');
const tOptions = toggle.querySelectorAll('.t-option');
function setTheme(theme) {
  html.setAttribute('data-theme', theme);
  localStorage.setItem('book-mindmap-theme', theme);
  tOptions.forEach(o => o.classList.toggle('active', o.dataset.themeVal === theme));
}
const saved = localStorage.getItem('book-mindmap-theme') || 'dark';
setTheme(saved);
tOptions.forEach(opt => {
  opt.addEventListener('click', (e) => { e.stopPropagation(); setTheme(opt.dataset.themeVal); });
});

// Navigation
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    const target = document.getElementById('sec-' + item.dataset.section);
    if (target) {
      target.classList.add('active');
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => {
        target.querySelectorAll('.fade-up').forEach(el => {
          if (el.getBoundingClientRect().top < window.innerHeight) el.classList.add('visible');
        });
      }, 100);
    }
  });
});

// Scroll animations
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
}, { threshold: 0.15 });
document.querySelectorAll('.fade-up').forEach(el => observer.observe(el));

// Accordion
document.querySelectorAll('.acc-header').forEach(header => {
  header.addEventListener('click', () => header.parentElement.classList.toggle('open'));
});
"""


def _html_esc(text: str) -> str:
    """HTML 转义。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _html_tag(label: str, color_class: str) -> str:
    """生成一个小标签 span。"""
    return f'<span class="ent-tag {color_class}">{_html_esc(label)}</span>'


def _html_card(title: str, body: str, extra_class: str = "") -> str:
    """生成一张 card div。"""
    cls = f'card {extra_class}'.strip()
    return f'<div class="{cls}"><div class="card-title">{_html_esc(title)}</div>{body}</div>'


def _html_accordion(title: str, body: str) -> str:
    """生成一个可折叠的 accordion。"""
    return (
        f'<div class="accordion"><div class="acc-header">'
        f'{_html_esc(title)} <span class="arrow">▾</span></div>'
        f'<div class="acc-body"><div class="acc-content">{body}</div></div></div>'
    )


def build_html(data: dict) -> str:
    """生成交互式 HTML 知识图谱（post-read 模式）。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")

    title = _html_esc(structure.get("title", "书籍思维导图"))
    one_line = _html_esc(structure.get("one_line_summary", ""))
    core_theme = _html_esc(structure.get("core_theme", ""))
    audience = _html_esc(structure.get("target_audience", ""))
    style = _html_esc(structure.get("writing_style", ""))
    complexity = structure.get("reading_complexity", "moderate")

    generated_at = metadata.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    mode_label = metadata.get("mode", "detailed")
    chapter_count = len(chapters)

    # ── 按部分组织章节 ──
    parts: dict[str, list[dict]] = {}
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    # ── 聚合全书核心概念 ──
    all_concepts: list[str] = []
    seen_concepts: set[str] = set()
    for ch in chapters:
        for c in ch.get("summary", {}).get("concepts", []):
            term = c.get("term", "")
            if term and term not in seen_concepts:
                seen_concepts.add(term)
                all_concepts.append(term)

    # ── 构建章节 accordion HTML ──
    chapter_html_parts: list[str] = []
    part_index = 0
    for part_name, part_chapters in parts.items():
        ch_items: list[str] = []
        for chap in part_chapters:
            s = chap.get("summary", {})
            ch_title = _html_esc(chap.get("title", f"第{chap.get('number','?')}章"))
            ch_num = chap.get("number", "?")

            body_lines: list[str] = []
            one_sent = s.get("one_sentence", "")
            if one_sent:
                body_lines.append(f'<p style="color:var(--accent);font-weight:600;margin-bottom:0.8rem;">🎯 {_html_esc(one_sent)}</p>')

            key_args = s.get("key_arguments", [])
            if key_args:
                items = "".join(f"<li>{_html_esc(_trim(str(a), 150))}</li>" for a in key_args if a and str(a).strip())
                body_lines.append(f"<p style='font-weight:600;'>⭐ 核心论点</p><ul style='padding-left:1.2rem;color:var(--text2);'>{items}</ul>")

            concepts = s.get("concepts", [])
            if concepts:
                tags = " ".join(_html_tag(c.get("term", ""), "tag-blue") for c in concepts[:8] if c.get("term"))
                body_lines.append(f"<p style='font-weight:600;margin-top:0.6rem;'>📖 关键概念</p><div>{tags}</div>")

            evidence = s.get("evidence", [])
            if evidence:
                ev_items = "".join(
                    f"<li>{_html_esc(_trim(e.get('description', str(e)) if isinstance(e, dict) else str(e), 120))}</li>"
                    for e in evidence[:20]
                )
                body_lines.append(f"<p style='font-weight:600;margin-top:0.6rem;'>📊 支撑论据</p><ul style='padding-left:1.2rem;color:var(--text2);'>{ev_items}</ul>")

            examples = s.get("examples", [])
            if examples:
                ex_items = "".join(f"<li>{_html_esc(_trim(str(e) if not isinstance(e, dict) else e.get('description', str(e)), 150))}</li>" for e in examples[:3])
                body_lines.append(f"<p style='font-weight:600;margin-top:0.6rem;'>📋 案例</p><ul style='padding-left:1.2rem;color:var(--text2);'>{ex_items}</ul>")

            critique = _s(s.get("critique", ""))
            limitations = s.get("limitations", [])
            if critique or limitations:
                lim_text = critique if critique else "；".join(str(l) for l in limitations[:3])
                body_lines.append(f'<div class="highlight warn" style="margin-top:0.8rem;"><div class="hl-title">⚠️ 质疑与局限</div>{_html_esc(_trim(lim_text, 200))}</div>')

            impl = _s(s.get("practical_implication", ""))
            if impl:
                body_lines.append(f'<div class="highlight" style="margin-top:0.8rem;"><div class="hl-title">🎯 实践启示</div>{_html_esc(_trim(impl, 150))}</div>')

            # 用 accordion 包裹每个章节
            ch_items.append(_html_accordion(
                f"第{ch_num}章：{ch_title}",
                "\n".join(body_lines) or f'<p style="color:var(--text2);">（暂无详细摘要）</p>'
            ))

        prefix = _cn_num(part_index + 1)
        ch_html = "\n".join(ch_items)
        chapter_html_parts.append(
            f'<div class="card" style="margin-bottom:1.5rem;">'
            f'<div class="card-title">📂 {prefix}、{_html_esc(part_name)}</div>{ch_html}</div>'
        )
        part_index += 1

    # ── 完整页面组装 ──
    concept_html = " ".join(
        f'<span class="concept-node{" core" if i < 3 else ""}">{_html_esc(c)}</span>'
        for i, c in enumerate(all_concepts[:15])
    )

    genre_labels = {"business": "💼 商业/管理", "philosophy": "🧠 哲学/思想", "tech": "💻 技术/工程",
                    "literature": "📖 文学/叙事", "academic": "🎓 学术/研究", "self-help": "🌱 自我提升", "auto": "📚 综合"}
    genre_label = genre_labels.get(genre, "📚 综合")

    complexity_labels = {"easy": "🟢 轻松", "moderate": "🟡 适中", "challenging": "🟠 有挑战", "dense": "🔴 密集"}

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>《{title}》交互式知识图谱</title>
<style>{HTML_CSS}</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="切换深色/护眼模式">
  <span class="t-option active" data-theme-val="dark">🌙</span>
  <span class="t-option" data-theme-val="light">☀️</span>
</button>

<section class="hero">
  <div class="hero-content">
    <div class="hero-badge">📚 交互式知识图谱 · AI 深度阅读可视化</div>
    <h1>{title}</h1>
    <h2>{one_line}</h2>
    <div class="hero-stats">
      <div class="hero-stat"><div class="num">{chapter_count}</div><div class="label">章节</div></div>
      <div class="hero-stat"><div class="num">{len(parts)}</div><div class="label">部分</div></div>
      <div class="hero-stat"><div class="num">{len(all_concepts)}</div><div class="label">核心概念</div></div>
      <div class="hero-stat"><div class="num">{mode_label}</div><div class="label">分析深度</div></div>
    </div>
  </div>
  <div class="scroll-hint">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 13l5 5 5-5M7 6l5 5 5-5"/></svg>
  </div>
</section>

<nav class="nav">
  <div class="nav-inner">
    <div class="nav-item active" data-section="overview">🌐 总览</div>
    <div class="nav-item" data-section="structure">📑 全书结构</div>
    <div class="nav-item" data-section="chapters">📖 逐章分析</div>
    <div class="nav-item" data-section="concepts">🔗 概念网络</div>
  </div>
</nav>

<section class="section active" id="sec-overview">
  <div class="section-title"><span class="icon">🌐</span>书籍总览</div>
  <div class="section-subtitle">{one_line}</div>
  <div class="card-grid-2">
    <div class="card">
      <div class="card-title">📋 基本信息</div>
      <table style="width:100%;font-size:0.9rem;color:var(--text2);">
        <tr><td style="padding:0.3rem 0;">📚 书名</td><td style="font-weight:600;color:var(--text);">{title}</td></tr>
        <tr><td>🏷️ 流派</td><td>{genre_label}</td></tr>
        <tr><td>✍️ 风格</td><td>{style}</td></tr>
        <tr><td>📖 难度</td><td>{complexity_labels.get(complexity, complexity)}</td></tr>
        <tr><td>👥 读者</td><td>{audience}</td></tr>
        <tr><td>📂 主题</td><td>{core_theme}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title">💡 核心主旨</div>
      <p style="color:var(--text2);font-size:0.95rem;line-height:1.8;">{one_line}</p>
      <p style="margin-top:1rem;color:var(--text2);font-size:0.85rem;">主题范畴：{core_theme}</p>
    </div>
  </div>
  {f'<div class="highlight" style="margin-top:1.5rem;"><div class="hl-title">💡 分析说明</div>本书共 {chapter_count} 章、{len(parts)} 部分。以下按部分组织的逐章分析基于 {mode_label} 模式生成，点击各章标题展开查看详细内容。</div>' if chapter_count > 0 else ''}
</section>

<section class="section" id="sec-structure">
  <div class="section-title"><span class="icon">📑</span>全书结构</div>
  <div class="section-subtitle">全书共分为 {len(parts)} 个部分、{chapter_count} 章。</div>
  <div class="card-grid">
    {_build_structure_cards(parts, chapters)}
  </div>
</section>

<section class="section" id="sec-chapters">
  <div class="section-title"><span class="icon">📖</span>逐章分析</div>
  <div class="section-subtitle">点击各章节标题展开详细分析。共 {chapter_count} 章，按部分组织。</div>
  {"".join(chapter_html_parts)}
</section>

<section class="section" id="sec-concepts">
  <div class="section-title"><span class="icon">🔗</span>概念网络</div>
  <div class="section-subtitle">全书 {len(all_concepts)} 个核心概念，点击标签可跳转查看详情。</div>
  <div class="card" style="text-align:center;">
    <div class="concept-web">{concept_html}</div>
  </div>
  <div style="margin-top:2rem;">
    <div class="card-title" style="margin-bottom:1rem;">📊 跨章概念分布</div>
    <div class="card-grid">
      {_build_concept_distribution_cards(chapters)}
    </div>
  </div>
</section>

<footer style="text-align:center;padding:3rem;color:var(--text2);font-size:0.8rem;border-top:1px solid var(--border);">
  <p>📚 《{title}》交互式知识图谱</p>
  <p style="margin-top:0.5rem;">基于 DeepSeek {mode_label} 模式全书分析 | 生成于 {generated_at}</p>
  <p style="margin-top:0.5rem;">🛠️ 工具：book-to-mindmap · 模型：{_html_esc(metadata.get('model','deepseek-chat'))}</p>
</footer>

<script>{HTML_JS}</script>
</body>
</html>"""


def _build_structure_cards(parts: dict, chapters: list) -> str:
    """构建全书结构卡片。"""
    cards: list[str] = []
    for i, (part_name, part_chapters) in enumerate(parts.items()):
        ch_list = "".join(
            f'<tr><td style="padding:0.2rem 0.5rem;font-size:0.8rem;color:var(--text2);">第{ch.get("number","?")}章 · {_html_esc(ch.get("title",""))}</td></tr>'
            for ch in part_chapters
        )
        cards.append(
            f'<div class="card fade-up"><div class="card-title">{_cn_num(i+1)}、{_html_esc(part_name)}</div>'
            f'<p style="font-size:0.85rem;color:var(--text2);margin-bottom:0.5rem;">{len(part_chapters)} 章</p>'
            f'<table style="width:100%;">{ch_list}</table></div>'
        )
    return "\n".join(cards)


def _build_concept_distribution_cards(chapters: list) -> str:
    """构建概念分布卡片。"""
    concept_map: dict[str, list[str]] = {}
    for ch in chapters:
        ch_title = ch.get("title", "")
        ch_num = str(ch.get("number", "?"))
        for c in ch.get("summary", {}).get("concepts", []):
            term = c.get("term", "")
            if term:
                concept_map.setdefault(term, []).append(f"第{ch_num}章")
    cards: list[str] = []
    for term, locs in list(concept_map.items())[:12]:
        loc_str = " · ".join(locs)
        cards.append(
            f'<div class="card"><div class="card-title">{_html_tag(term, "tag-blue")}</div>'
            f'<p style="font-size:0.8rem;color:var(--text2);">出现在：{loc_str}</p></div>'
        )
    return "\n".join(cards) if cards else '<div class="card"><p style="color:var(--text2);">（暂无概念数据）</p></div>'


# ═══════════════════════════════════════════════════════════
# 跨章综合 Builder 辅助函数（synthesis → HTML widgets）
# ═══════════════════════════════════════════════════════════

def _build_synthesis_overview(syn: dict, chapters: list[dict], parts_count: int) -> str:
    """总览 Tab：书籍核心命题 + 分析维度预览 + 阅读路径卡片 + 概念网络。"""
    bt = _html_esc(syn.get("book_thesis", ""))
    dims = syn.get("analytical_dimensions", [])
    pathways = syn.get("reading_pathways", [])

    # ── 核心命题卡片 ──
    thesis_card = f"""<div class="highlight" style="margin-bottom:1.5rem;font-size:1.05rem;">
<div class="hl-title">💡 全书核心命题</div>{bt}</div>"""

    # ── 分析维度预览 ──
    dim_cards = ""
    for i, d in enumerate(dims[:8]):
        icon = _html_esc(d.get("icon", "📖"))
        name = _html_esc(d.get("name", ""))
        summary = _html_esc(_trim(d.get("summary", ""), 100))
        ch_nums = d.get("chapter_numbers", [])
        ch_str = f"第{'、'.join(str(n) for n in ch_nums[:6])}章" if ch_nums else ""
        dim_cards += f"""<div class="card fade-up"><div class="card-title">{icon} {name}</div>
<p style="font-size:0.85rem;color:var(--text2);margin-bottom:0.5rem;">{summary}</p>
<p style="font-size:0.75rem;color:var(--text2);">📖 {ch_str}</p></div>"""

    # ── 阅读路径 ──
    path_cards = ""
    path_icons = ["🧭", "⚡", "🔬"]
    for i, p in enumerate(pathways[:3]):
        pi = path_icons[i] if i < len(path_icons) else "📖"
        name = _html_esc(p.get("name", ""))
        reader = _html_esc(p.get("target_reader", ""))
        rationale = _html_esc(_trim(p.get("rationale", ""), 100))
        seq = p.get("chapter_sequence", [])
        seq_str = " → ".join(f"第{n}章" for n in seq[:8])
        path_cards += f"""<div class="card"><div class="card-title">{pi} {name}</div>
<p style="font-size:0.8rem;color:var(--accent);margin-bottom:0.3rem;">👤 {reader}</p>
<p style="font-size:0.85rem;color:var(--text2);margin-bottom:0.5rem;">{rationale}</p>
<p style="font-size:0.75rem;color:var(--text2);">{seq_str}</p></div>"""

    # ── 概念网络 ──
    all_concepts: list[str] = []
    seen: set[str] = set()
    for ch in chapters:
        for c in ch.get("summary", {}).get("concepts", []):
            t = c.get("term", "")
            if t and t not in seen:
                seen.add(t)
                all_concepts.append(t)
    concept_html = " ".join(
        f'<span class="concept-node{" core" if i < 3 else ""}">{_html_esc(c)}</span>'
        for i, c in enumerate(all_concepts[:18])
    )

    return f"""{thesis_card}
<div class="card-grid-2" style="margin-bottom:1.5rem;">
<div class="card"><div class="card-title">📊 全书分析概览</div>
<p style="font-size:0.9rem;color:var(--text2);line-height:1.8;">
🔬 <strong>{len(dims)} 个分析维度</strong> 跨越章节边界<br>
🏛️ <strong>{len(syn.get('argument_architecture',{}).get('stages',[]))} 个论证阶段</strong> 揭示逻辑递进<br>
⚔️ <strong>{len(syn.get('key_debates',[]))} 个关键争议</strong> 贯穿全书<br>
📈 <strong>{len(syn.get('concept_evolution',[]))} 个核心概念</strong> 追踪演化轨迹
</p></div>
<div class="card"><div class="card-title">🗺️ 推荐阅读路径</div>
{"".join(path_cards) if path_cards else '<p style="font-size:0.85rem;color:var(--text2);">（按需选择阅读顺序）</p>'}</div></div>
<div class="highlight" style="margin-bottom:1.5rem;"><div class="hl-title">📊 全书核心概念网络</div><div class="concept-web">{concept_html}</div></div>
<div class="card-grid-4" style="margin-bottom:1.5rem;"><div class="card-title" style="grid-column:1/-1;margin-bottom:0;">🔍 分析维度速览</div>{dim_cards}</div>"""


def _build_argument_architecture(syn: dict) -> str:
    """论证架构 Tab：阶段性流图 + 连接关系表。"""
    arch = syn.get("argument_architecture", {})
    overall = _html_esc(arch.get("overall_structure", ""))
    stages = arch.get("stages", [])
    flows = arch.get("flow_diagram", [])

    # ── 阶段卡片 ──
    stage_html = ""
    for i, st in enumerate(stages):
        sn = i + 1
        sclass = f"s{min(sn, 5)}"
        name = _html_esc(st.get("name", ""))
        role = _html_esc(st.get("role", ""))
        move = _html_esc(st.get("key_move", ""))
        crange = _html_esc(st.get("chapter_range", ""))
        details = st.get("key_chapters_detail", [])
        ch_tags = "".join(
            f'<span class="ent-tag tag-blue">第{d.get("chapter","?")}章 · {_html_esc(d.get("title","")[:20])}</span>'
            for d in details[:5]
        )
        stage_html += f"""<div class="stage-header fade-up">
<div class="stage-num {sclass}">{sn}</div>
<div class="stage-info">
<div class="stage-name">{name}</div>
<div class="stage-meta">📖 {crange} · {role}</div>
<div class="stage-move">🔑 {move}</div>
<div class="stage-chapters">{ch_tags}</div>
</div></div>"""

    # ── 流图连接 ──
    flow_html = ""
    if flows:
        flow_nodes = ""
        for i, f in enumerate(flows):
            color = ["blue", "purple", "red", "amber", "green"][i % 5]
            from_n = _html_esc(f.get("from", ""))
            to_n = _html_esc(f.get("to", ""))
            rel = _html_esc(f.get("relationship", ""))
            # Map purple to accent2
            node_color = "blue" if color == "purple" else color
            from_cls = "blue" if color in ("blue", "purple") else node_color
            flow_nodes += f'<div class="flow-node {from_cls}">{from_n}</div><div class="flow-arrow">→</div>'
            if i == len(flows) - 1:
                flow_nodes += f'<div class="flow-node {["amber","green","red","blue","green"][i%5]}">{to_n}</div>'

        flow_html = f"""<div class="card" style="margin-bottom:1.5rem;text-align:center;">
<div class="card-title">🔄 论证推进流</div>
<div class="flow-container" style="justify-content:center;flex-wrap:wrap;">{flow_nodes}</div></div>"""

    # ── 关系表 ──
    rel_rows = ""
    for f in flows:
        rel_rows += f"""<tr><td>{_html_esc(f.get('from',''))}</td>
<td style="color:var(--accent);font-weight:600;">→ {_html_esc(f.get('relationship',''))}</td>
<td>{_html_esc(f.get('to',''))}</td></tr>"""

    return f"""<div class="highlight" style="margin-bottom:2rem;"><div class="hl-title">🏛️ 论证结构总览</div>{overall}</div>
{flow_html}
<div class="card-grid" style="margin-bottom:2rem;">{stage_html}</div>
{('<div class="card" style="margin-bottom:1.5rem;"><div class="card-title">📋 阶段连接关系</div><table class="compare-table"><tr><th>起始阶段</th><th>逻辑关系</th><th>目标阶段</th></tr>' + rel_rows + '</table></div>') if rel_rows else ''}"""


def _build_concept_evolution(syn: dict) -> str:
    """概念演进 Tab：时间线展示核心概念的跨章演化。"""
    evolutions = syn.get("concept_evolution", [])
    if not evolutions:
        return '<div class="card"><p style="color:var(--text2);">（暂无概念演化数据）</p></div>'

    sections = ""
    stage_labels = {
        "introduced": ("🚪 引入", "green"),
        "refined": ("🔧 深化", "blue"),
        "challenged": ("⚔️ 挑战", "red"),
        "applied": ("🔬 应用", "amber"),
        "synthesized": ("🧩 综合", "blue"),
    }
    for ev in evolutions:
        concept = _html_esc(ev.get("concept", ""))
        maturation = _html_esc(ev.get("maturation", ""))
        stages = ev.get("evolution_stages", [])
        timeline_items = ""
        for i, s in enumerate(stages):
            stage = s.get("stage", "introduced")
            label, color = stage_labels.get(stage, ("📌", "blue"))
            ch_num = s.get("chapter", "?")
            desc = _html_esc(s.get("description", ""))
            timeline_items += f"""<div class="tl-item fade-up">
<div class="tl-header"><span class="tl-era">{label}</span><span class="tl-country">第{ch_num}章</span></div>
<p style="color:var(--text2);font-size:0.85rem;">{desc}</p></div>"""

        sections += f"""<div class="card" style="margin-bottom:1.5rem;">
<div class="card-title">📈 {concept}</div>
<p style="font-size:0.8rem;color:var(--text2);margin-bottom:1rem;">🧬 {maturation}</p>
<div class="timeline">{timeline_items}</div></div>"""

    return sections


def _build_evidence_assessment(syn: dict) -> str:
    """论据评估 Tab：证据链强弱表 + 全局模式总结。"""
    ea = syn.get("evidence_assessment", {})
    strongest = ea.get("strongest_chains", [])
    weakest = ea.get("weakest_links", [])
    overall = _html_esc(ea.get("overall_pattern", ""))

    strong_rows = ""
    for s in strongest[:6]:
        strong_rows += f"""<tr><td>第{s.get('chapter','?')}章</td>
<td>{_html_esc(s.get('title','')[:30])}</td>
<td><span class="evidence-meter"><span class="dot filled strong"></span><span class="dot filled strong"></span><span class="dot filled strong"></span><span class="dot filled strong"></span><span class="dot filled strong"></span></span></td>
<td style="font-size:0.85rem;color:var(--text2);">{_html_esc(_trim(s.get('description',''), 120))}</td></tr>"""

    weak_rows = ""
    for w in weakest[:6]:
        weak_rows += f"""<tr><td>第{w.get('chapter','?')}章</td>
<td>{_html_esc(w.get('title','')[:30])}</td>
<td><span class="evidence-meter"><span class="dot filled weak"></span><span class="dot filled weak"></span><span class="dot"></span><span class="dot"></span><span class="dot"></span></span></td>
<td style="font-size:0.85rem;color:var(--text2);">{_html_esc(_trim(w.get('description',''), 120))}</td></tr>"""

    return f"""<div class="highlight" style="margin-bottom:1.5rem;"><div class="hl-title">📊 全书记证模式</div>{overall}</div>
<div class="card" style="margin-bottom:1.5rem;">
<div class="card-title">✅ 最强证据链</div>
{('<table class="compare-table"><tr><th>章节</th><th>标题</th><th>强度</th><th>描述</th></tr>' + strong_rows + '</table>') if strong_rows else '<p style="color:var(--text2);">（暂无数据）</p>'}</div>
<div class="card highlight danger" style="margin-bottom:1.5rem;border-left:4px solid var(--red);">
<div class="card-title" style="color:var(--red);">⚠️ 薄弱环节</div>
{('<table class="compare-table"><tr><th>章节</th><th>标题</th><th>强度</th><th>问题</th></tr>' + weak_rows + '</table>') if weak_rows else '<p style="color:var(--text2);">（暂无数据）</p>'}</div>"""


def _build_dimension_tab(dim: dict, chapters: list[dict]) -> str:
    """单个分析维度的内容 Tab。"""
    name = _html_esc(dim.get("name", ""))
    icon = _html_esc(dim.get("icon", "📖"))
    summary = _html_esc(dim.get("summary", ""))
    evolution = _html_esc(dim.get("evolution", ""))
    insights = dim.get("key_insights", [])
    concepts = dim.get("concepts_involved", [])
    ch_nums = dim.get("chapter_numbers", [])

    # 洞察块
    ins_html = ""
    for ins in insights[:5]:
        ins_html += f'<div class="highlight" style="margin-bottom:0.8rem;"><div class="hl-title">💡</div>{_html_esc(ins)}</div>'

    # 概念标签
    tag_html = " ".join(
        _html_tag(c, ["tag-blue", "tag-red", "tag-amber", "tag-green", "tag-cyan"][i % 5])
        for i, c in enumerate(concepts[:10])
    )

    # 相关章节卡片
    ch_cards = ""
    ch_set = set(ch_nums)
    for ch in chapters:
        if ch.get("number") in ch_set:
            s = ch.get("summary", {})
            ct = _html_esc(ch.get("title", "")[:40])
            cn = ch.get("number", "?")
            thesis = _html_esc(_trim(s.get("thesis_statement", "") or s.get("one_sentence", ""), 100))
            cb = _html_esc(_trim(s.get("connection_to_book", ""), 80))
            ch_cards += f"""<div class="card"><div class="card-title">第{cn}章 · {ct}</div>
{('<p style="font-size:0.85rem;color:var(--accent);margin-bottom:0.5rem;">🎯 ' + thesis + '</p>') if thesis else ''}
{('<p style="font-size:0.8rem;color:var(--text2);">📌 ' + cb + '</p>') if cb else ''}</div>"""

    return f"""<div class="highlight" style="margin-bottom:1.5rem;font-size:1.05rem;"><div class="hl-title">{icon} {name}</div>{summary}</div>
{('<div class="highlight" style="margin-bottom:1.5rem;"><div class="hl-title">📈 演化轨迹</div>' + evolution + '</div>') if evolution else ''}
{ins_html}
{('<div style="margin:1rem 0;"><div class="card-title" style="margin-bottom:0.5rem;">🔗 涉及概念</div><div>' + tag_html + '</div></div>') if tag_html else ''}
<div style="margin-top:1.5rem;"><div class="card-title" style="margin-bottom:0.5rem;">📖 相关章节</div><div class="card-grid">{"".join(ch_cards) if ch_cards else '<p style="color:var(--text2);">（暂无详细数据）</p>'}</div></div>"""


def _build_key_debates(syn: dict) -> str:
    """关键争议 Tab：辩论卡片 + 双栏立场对比。"""
    debates = syn.get("key_debates", [])
    if not debates:
        return '<div class="card"><p style="color:var(--text2);">（暂无辩论数据）</p></div>'

    cards = ""
    for d in debates:
        name = _html_esc(d.get("debate", ""))
        nature = d.get("nature", "theoretical")
        resolution = _html_esc(_trim(d.get("resolution", ""), 150))
        significance = _html_esc(d.get("significance", ""))
        nature_labels = {"theoretical": "理论争议", "practical": "实践困境", "perspectival": "视角冲突"}

        positions = d.get("positions", [])
        pos_html = ""
        pos_colors = [
            ("🔵", "var(--a03)", "var(--accent)"),
            ("🟠", "var(--am05)", "var(--amber)"),
        ]
        for i, pos in enumerate(positions[:2]):
            side = _html_esc(pos.get("side", ""))
            arg = _html_esc(_trim(pos.get("core_argument", ""), 120))
            chs = pos.get("chapter_numbers", [])
            ch_str = f"第{'、'.join(str(n) for n in chs[:4])}章" if chs else ""
            pi, pbg, pcolor = pos_colors[i] if i < len(pos_colors) else ("📌", "var(--card-bg)", "var(--text)")
            pos_html += f"""<div class="debate-pos" style="background:{pbg};">
<div class="pos-side"><span style="color:{pcolor};font-size:1.2rem;">{pi}</span> <span>{side}</span></div>
<div class="pos-arg">{arg}</div>
<div style="font-size:0.7rem;color:var(--text2);margin-top:0.5rem;">📖 {ch_str}</div></div>"""

        res_block = ""
        if resolution:
            res_cls = "highlight warn" if "悬置" in resolution or "未解决" in resolution else "highlight"
            res_block = f'<div class="{res_cls}" style="margin:0;"><div class="hl-title">⚖️ 裁决</div>{resolution}</div>'

        sig_block = f'<div class="highlight" style="margin:0;border-left-color:var(--accent2);"><div class="hl-title" style="color:var(--accent2);">💡 重要性</div>{significance}</div>' if significance else ""

        cards += f"""<div class="debate-card">
<div class="debate-header"><div class="debate-name">⚔️ {name}</div>
<span class="debate-nature {nature}">{nature_labels.get(nature, '理论争议')}</span></div>
<div class="debate-positions">{pos_html}</div>
{res_block}{sig_block}</div>"""

    return cards


def _build_practical_framework(syn: dict) -> str:
    """实践框架 Tab：组件卡片 + 难度/影响矩阵 + 实施路线图。"""
    pf = syn.get("practical_framework", {})
    overview = _html_esc(pf.get("overview", ""))
    components = pf.get("components", [])
    roadmap = _html_esc(pf.get("implementation_roadmap", ""))

    # ── 组件卡片 ──
    comp_cards = ""
    for c in components:
        name = _html_esc(c.get("name", ""))
        insight = _html_esc(_trim(c.get("actionable_insight", ""), 150))
        difficulty = c.get("difficulty", "moderate")
        impact = c.get("impact", "medium")
        sources = c.get("source_chapters", [])
        src_str = f"第{'、'.join(str(n) for n in sources[:5])}章" if sources else ""

        diff_labels = {"easy": "🟢 低门槛", "moderate": "🟡 需投入", "challenging": "🔴 高难度"}
        imp_labels = {"high": "⭐ 高影响", "medium": "📌 中等影响", "low": "📎 渐进收益"}

        comp_cards += f"""<div class="fw-card fade-up">
<div class="fw-name">{name}</div>
<div class="fw-insight">{insight}</div>
<div class="fw-metrics">
<div class="fw-metric"><div class="fw-label">难度</div><div class="fw-bar"><div class="fw-fill {difficulty}"></div></div><div style="font-size:0.7rem;color:var(--text2);margin-top:0.2rem;">{diff_labels.get(difficulty, '🟡 需投入')}</div></div>
<div class="fw-metric"><div class="fw-label">影响</div><div class="fw-bar"><div class="fw-fill {impact}"></div></div><div style="font-size:0.7rem;color:var(--text2);margin-top:0.2rem;">{imp_labels.get(impact, '📌 中等影响')}</div></div></div>
<div class="fw-source">{src_str}</div></div>"""

    # ── 2x2 矩阵 ──
    matrix_html = ""
    if components:
        # 分配组件到象限
        q_hl = []  # 高影响低难度 (最佳起点)
        q_hh = []  # 高影响高难度 (战略目标)
        q_ll = []  # 低影响低难度 (快速胜利)
        q_lh = []  # 低影响高难度 (低优先级)
        for c in components:
            d = c.get("difficulty", "moderate")
            i = c.get("impact", "medium")
            if i == "high" and d == "easy":
                q_hl.append(c)
            elif i == "high" and d in ("moderate", "challenging"):
                q_hh.append(c)
            elif i in ("medium", "low") and d == "easy":
                q_ll.append(c)
            else:
                q_lh.append(c)

        def _q_cell(title, items, accent_color):
            if not items:
                return f'<div class="matrix-cell"><div class="m-title" style="color:var(--text2);">—</div></div>'
            names = " · ".join(_html_esc(c.get("name", "")[:15]) for c in items[:3])
            return f'<div class="matrix-cell" style="border-left:3px solid {accent_color};"><div class="m-title">{title}</div><div class="m-sub">{names}</div></div>'

        matrix_html = f"""<div style="position:relative;max-width:900px;margin:2rem auto;">
<div style="text-align:center;font-size:0.75rem;color:var(--text2);margin-bottom:0.5rem;">影响 →</div>
<div class="matrix">
<div class="matrix-label"><span>低难度</span><span>高难度</span></div>
{_q_cell("🟢 最佳起点 (高影响·低难度)", q_hl, "var(--green)")}
{_q_cell("🔴 战略目标 (高影响·高难度)", q_hh, "var(--red)")}
{_q_cell("🟡 快速胜利 (渐近收益·低难度)", q_ll, "var(--amber)")}
{_q_cell("⚪ 低优先级 (渐近收益·高难度)", q_lh, "var(--text2)")}
</div></div>"""

    return f"""<div class="highlight" style="margin-bottom:1.5rem;"><div class="hl-title">🎯 框架总览</div>{overview}</div>
<div class="card-grid-2" style="margin-bottom:2rem;">{comp_cards}</div>
{matrix_html}
{('<div class="card" style="margin-bottom:1.5rem;"><div class="card-title">🗺️ 实施路线图</div><p style="color:var(--text2);font-size:0.9rem;line-height:1.8;">' + roadmap + '</p></div>') if roadmap else ''}"""


def build_html_preread(data: dict) -> str:
    """生成交互式 HTML 阅读路线图（pre-read 模式）。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")

    title = _html_esc(structure.get("title", "书籍思维导图"))
    one_line = _html_esc(structure.get("one_line_summary", ""))
    core_theme = _html_esc(structure.get("core_theme", ""))
    audience = _html_esc(structure.get("target_audience", ""))
    style = _html_esc(structure.get("writing_style", ""))
    complexity = structure.get("reading_complexity", "moderate")

    generated_at = metadata.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    chapter_count = len(chapters)

    # ── 按角色分组 ──
    roles: dict[str, list[dict]] = {"foundation": [], "core_argument": [], "case_study": [], "application": [], "summary": [], "bridge": []}
    for ch in chapters:
        s = ch.get("summary", {})
        role = s.get("chapter_role", "core_argument")
        roles.setdefault(role, []).append(ch)

    role_labels = {
        "foundation": ("🧱 基础框架章（必读）", "tag-blue"),
        "core_argument": ("⭐ 核心论证章（精读）", "tag-red"),
        "case_study": ("📋 案例章（可速读）", "tag-amber"),
        "application": ("🔧 应用章（按需）", "tag-green"),
        "summary": ("📝 总结章（浏览）", "tag-cyan"),
        "bridge": ("🌉 过渡章", ""),
    }

    strategy_items: list[str] = []
    for role, ctitles in roles.items():
        if ctitles and role in role_labels:
            label, tag_cls = role_labels[role]
            names = " · ".join(_html_esc(c.get("title", "?")) for c in ctitles[:5])
            strategy_items.append(f'<p style="margin:0.3rem 0;font-size:0.9rem;"><strong>{label}</strong>：{names}</p>')

    # ── 章节 roadmap ──
    parts: dict[str, list[dict]] = {}
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    chapter_html_parts: list[str] = []
    for part_name, part_chapters in parts.items():
        ch_items: list[str] = []
        for chap in part_chapters:
            s = chap.get("summary", {})
            ch_title = _html_esc(chap.get("title", f"第{chap.get('number','?')}章"))
            ch_num = chap.get("number", "?")

            body_parts: list[str] = []
            core_q = s.get("core_question", "")
            if core_q:
                body_parts.append(f'<p style="color:var(--accent);font-weight:700;">🎯 要回答的问题：{_html_esc(core_q)}</p>')
            why = s.get("why_this_matters", "")
            if why:
                body_parts.append(f'<p style="color:var(--text2);margin-top:0.4rem;">💡 为什么重要：{_html_esc(why)}</p>')
            guide = s.get("reading_guide", "")
            if guide:
                body_parts.append(f'<p style="color:var(--text2);margin-top:0.4rem;font-style:italic;">📖 {_html_esc(guide)}</p>')
            concepts = s.get("concepts_to_watch", [])
            if concepts:
                tags = " ".join(_html_tag(c, "tag-blue") for c in concepts if c and str(c).strip())
                body_parts.append(f'<p style="font-weight:600;margin-top:0.6rem;">🔑 重点关注概念（填你自己的定义）</p><div>{tags}</div>')
            difficulty = s.get("difficulty", "moderate")
            est = s.get("estimated_minutes", 15)
            diff_bar = {"easy": "🟢 轻松", "moderate": "🟡 适中", "challenging": "🟠 有挑战"}.get(difficulty, "🟡")
            body_parts.append(f'<p style="margin-top:0.6rem;font-size:0.85rem;color:var(--text2);">⚡ {diff_bar} · 预计 {est} 分钟</p>')
            body_parts.append('<p style="font-size:0.85rem;color:var(--text2);">☐ 已读完本章 — 一句话总结：[　　　　　]</p>')

            ch_items.append(_html_accordion(f"第{ch_num}章：{ch_title}", "\n".join(body_parts)))

        chapter_html_parts.append(
            f'<div class="card" style="margin-bottom:1.5rem;">'
            f'<div class="card-title">📂 {_html_esc(part_name)}</div>{"".join(ch_items)}</div>'
        )

    genre_labels = {"business": "💼 商业/管理", "philosophy": "🧠 哲学/思想", "tech": "💻 技术/工程",
                    "literature": "📖 文学/叙事", "academic": "🎓 学术/研究", "self-help": "🌱 自我提升", "auto": "📚 综合"}
    complexity_labels = {"easy": "🟢 轻松阅读", "moderate": "🟡 需要专注", "challenging": "🟠 有挑战", "dense": "🔴 需要精读"}

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>《{title}》阅读路线图</title>
<style>{HTML_CSS}</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="切换深色/护眼模式">
  <span class="t-option active" data-theme-val="dark">🌙</span>
  <span class="t-option" data-theme-val="light">☀️</span>
</button>

<section class="hero">
  <div class="hero-content">
    <div class="hero-badge">🧭 阅读路线图 · Pre-Read 模式</div>
    <h1>{title}</h1>
    <h2>读前导航 —— 带着问题去读，边读边填自己的笔记</h2>
    <div class="hero-stats">
      <div class="hero-stat"><div class="num">{chapter_count}</div><div class="label">章节</div></div>
      <div class="hero-stat"><div class="num">{len(parts)}</div><div class="label">部分</div></div>
      <div class="hero-stat"><div class="num">{genre_labels.get(genre, '📚')[:2]}</div><div class="label">流派</div></div>
      <div class="hero-stat"><div class="num">{complexity_labels.get(complexity, '🟡')[:2]}</div><div class="label">难度</div></div>
    </div>
  </div>
  <div class="scroll-hint">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 13l5 5 5-5M7 6l5 5 5-5"/></svg>
  </div>
</section>

<nav class="nav">
  <div class="nav-inner">
    <div class="nav-item active" data-section="overview">🗺️ 阅读地图</div>
    <div class="nav-item" data-section="strategy">📋 阅读策略</div>
    <div class="nav-item" data-section="chapters">📖 章节导航</div>
    <div class="nav-item" data-section="notes">📝 读后笔记</div>
  </div>
</nav>

<section class="section active" id="sec-overview">
  <div class="section-title"><span class="icon">🗺️</span>阅读地图总览</div>
  <div class="section-subtitle">{one_line}</div>
  <div class="card-grid-2">
    <div class="card">
      <div class="card-title">📋 书籍信息</div>
      <table style="width:100%;font-size:0.9rem;color:var(--text2);">
        <tr><td style="padding:0.3rem 0;">📚 书名</td><td style="font-weight:600;color:var(--text);">{title}</td></tr>
        <tr><td>🏷️ 流派</td><td>{genre_labels.get(genre, '📚 综合')}</td></tr>
        <tr><td>✍️ 风格</td><td>{style}</td></tr>
        <tr><td>📖 整体难度</td><td>{complexity_labels.get(complexity, '🟡 适中')}</td></tr>
        <tr><td>👥 目标读者</td><td>{audience}</td></tr>
        <tr><td>📂 主题</td><td>{core_theme}</td></tr>
      </table>
    </div>
    <div class="card">
      <div class="card-title">🧭 核心问题</div>
      <p style="color:var(--accent);font-size:1.1rem;font-weight:700;">{one_line}</p>
      <p style="margin-top:1rem;font-size:0.85rem;color:var(--text2);">把这个问题记在脑中，每读完一章回头问问自己：这一章为回答这个问题提供了什么？</p>
    </div>
  </div>
  <div class="highlight" style="margin-top:1.5rem;">
    <div class="hl-title">💡 使用说明</div>
    <p style="font-size:0.9rem;color:var(--text2);">
      每个章节标注了核心问题 → 带着问题去读<br>
      关键概念只列名 → 读完用自己的话填写定义<br>
      ☐ 读完勾选，一句话总结自己的理解<br>
      这份导图 = 你的个人笔记，不是 AI 的摘要
    </p>
  </div>
</section>

<section class="section" id="sec-strategy">
  <div class="section-title"><span class="icon">📋</span>推荐阅读策略</div>
  <div class="section-subtitle">根据章节在全书中的角色，推荐差异化的阅读深度。</div>
  <div class="card">{"".join(strategy_items)}</div>
</section>

<section class="section" id="sec-chapters">
  <div class="section-title"><span class="icon">📖</span>逐章导航</div>
  <div class="section-subtitle">点击各章节标题查看阅读提示和填空位。共 {chapter_count} 章。</div>
  {"".join(chapter_html_parts)}
</section>

<section class="section" id="sec-notes">
  <div class="section-title"><span class="icon">📝</span>全书读后总结</div>
  <div class="section-subtitle">读完本书后，在这里写下你的收获。</div>
  <div class="card" style="padding:2rem;">
    <div style="font-size:0.95rem;color:var(--text2);line-height:2.2;">
      <p>📖 这本书回答了：<em>{one_line}</em></p>
      <p>💭 我最大的收获：[　　　　　　　　　　　　　　]</p>
      <p>⚡ 改变了我对什么的看法：[　　　　　　　　　　　　　　]</p>
      <p>🔗 与哪些已有的知识产生了关联：[　　　　　　　　　　　　　　]</p>
      <p>📚 接下来想读的相关书：[　　　　　　　　　　　　　　]</p>
    </div>
  </div>
</section>

<footer style="text-align:center;padding:3rem;color:var(--text2);font-size:0.8rem;border-top:1px solid var(--border);">
  <p>🧭 《{title}》阅读路线图</p>
  <p style="margin-top:0.5rem;">Pre-Read 模式 | 生成于 {generated_at}</p>
  <p style="margin-top:0.5rem;">🛠️ 工具：book-to-mindmap · 模型：{_html_esc(metadata.get('model','deepseek-chat'))}</p>
</footer>

<script>{HTML_JS}</script>
</body>
</html>"""


def build_html_full(data: dict) -> str:
    """HTML full 布局入口：有 synthesis 数据则走学者级全景布局，否则走基础布局。

    与 build_html 的区别：
    - build_html: 4 Tab 紧凑布局（总览/结构/逐章/概念），适合快速浏览
    - build_html_full: 多 Tab 全景布局（synthesis 模式：融会贯通的跨章分析；
      基础模式：每 Part 独立 Tab + 逻辑链），适合 comprehensive/detailed 模式
    """
    if data.get("synthesis"):
        return _build_html_full_synthesized(data)
    return _build_html_full_legacy(data)


def _build_html_full_synthesized(data: dict) -> str:
    """学者级全景布局：以 synthesis 的 7 个分析维度为主 Tab，
    总览 Tab 展示全局洞见，后续 Tab 分别展示论证架构、概念演进、
    论据评估、各分析维度、关键争议、实践框架。"""

    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")
    syn = data.get("synthesis", {})

    title = _html_esc(structure.get("title", "书籍思维导图"))
    one_line = _html_esc(structure.get("one_line_summary", ""))
    generated_at = metadata.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    mode_label = metadata.get("mode", "detailed")
    chapter_count = len(chapters)

    # ── 按 Part 组织 ──
    parts: dict[str, list[dict]] = {}
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    # ── 分析维度 ──
    dims = syn.get("analytical_dimensions", [])
    MAX_CONTENT_TABS = 9
    if len(dims) > MAX_CONTENT_TABS:
        merged_dims = dims[MAX_CONTENT_TABS - 1:]
        dims = dims[:MAX_CONTENT_TABS - 1]
        merged = {
            "name": "更多维度", "icon": "📖",
            "summary": "；".join(d.get("name", "") for d in merged_dims),
            "chapter_numbers": [],
            "key_insights": [],
            "evolution": "",
            "concepts_involved": [],
        }
        for d in merged_dims:
            merged["chapter_numbers"].extend(d.get("chapter_numbers", []))
            merged["key_insights"].extend(d.get("key_insights", []))
            merged["concepts_involved"].extend(d.get("concepts_involved", []))
        dims.append(merged)

    # ── Tab 定义 ──
    tab_defs: list[dict] = [
        {"id": "overview", "label": "🌐 总览"},
        {"id": "argument", "label": "🏛️ 论证架构"},
        {"id": "concepts", "label": "📈 概念演进"},
        {"id": "evidence", "label": "📊 论据评估"},
    ]
    for i, d in enumerate(dims):
        icon = d.get("icon", "📖")
        short = d.get("name", f"维度{i+1}")[:8]
        tab_defs.append({"id": f"dim-{i}", "label": f"{icon} {short}", "dim_idx": i})
    tab_defs.append({"id": "debates", "label": "⚔️ 关键争议"})
    tab_defs.append({"id": "framework", "label": "🎯 实践框架"})

    # ── 构建 Tab 内容 ──
    tab_contents: dict[str, str] = {}
    tab_contents["overview"] = _build_synthesis_overview(syn, chapters, len(parts))
    tab_contents["argument"] = _build_argument_architecture(syn)
    tab_contents["concepts"] = _build_concept_evolution(syn)
    tab_contents["evidence"] = _build_evidence_assessment(syn)
    tab_contents["debates"] = _build_key_debates(syn)
    tab_contents["framework"] = _build_practical_framework(syn)
    for i in range(len(dims)):
        tab_contents[f"dim-{i}"] = _build_dimension_tab(dims[i], chapters)

    # ── Nav + Section ──
    nav_html = "\n".join(
        f'<div class="nav-item{" active" if i == 0 else ""}" data-section="{td["id"]}">{td["label"]}</div>'
        for i, td in enumerate(tab_defs)
    )
    section_html = "\n".join(
        f'<section class="section{" active" if i == 0 else ""}" id="sec-{td["id"]}">'
        f'<div class="section-title"><span class="icon">{td["label"].split()[0]}</span>{td["label"].split(" ",1)[-1]}</div>'
        f'{tab_contents.get(td["id"], "")}</section>'
        for i, td in enumerate(tab_defs)
    )

    gl = {"business": "💼 商业/管理", "philosophy": "🧠 哲学/思想", "tech": "💻 技术/工程",
          "literature": "📖 文学/叙事", "academic": "🎓 学术/研究", "self-help": "🌱 自我提升", "auto": "📚 综合"}

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>《{title}》交互式知识图谱</title>
<style>{HTML_CSS}</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="切换深色/护眼模式">
  <span class="t-option active" data-theme-val="dark">🌙</span>
  <span class="t-option" data-theme-val="light">☀️</span>
</button>

<section class="hero">
  <div class="hero-content">
    <div class="hero-badge">📚 交互式知识图谱 · 学者级跨章综合分析</div>
    <h1>{title}</h1>
    <h2>{one_line}</h2>
    <div class="hero-stats">
      <div class="hero-stat"><div class="num">{chapter_count}</div><div class="label">章节</div></div>
      <div class="hero-stat"><div class="num">{len(dims)}</div><div class="label">分析维度</div></div>
      <div class="hero-stat"><div class="num">{len(syn.get('argument_architecture',{}).get('stages',[]))}</div><div class="label">论证阶段</div></div>
      <div class="hero-stat"><div class="num">{len(syn.get('concept_evolution',[]))}</div><div class="label">核心概念</div></div>
    </div>
  </div>
  <div class="scroll-hint">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 13l5 5 5-5M7 6l5 5 5-5"/></svg>
  </div>
</section>

<nav class="nav"><div class="nav-inner">{nav_html}</div></nav>

{section_html}

<footer style="text-align:center;padding:3rem;color:var(--text2);font-size:0.8rem;border-top:1px solid var(--border);">
  <p>📚 《{title}》交互式知识图谱 · {gl.get(genre, '📚 综合')}</p>
  <p style="margin-top:0.5rem;">基于 DeepSeek {mode_label} 模式全书分析 + 跨章综合 | 生成于 {generated_at}</p>
  <p style="margin-top:0.5rem;">🛠️ 工具：book-to-mindmap · 模型：{_html_esc(metadata.get('model','deepseek-chat'))}</p>
</footer>
<script>{HTML_JS}</script>
</body>
</html>"""


def _build_html_full_legacy(data: dict) -> str:
    """基础全景布局（无 synthesis 数据时的回退方案）：
    每 Part 一个独立 Tab + 总览 + 逻辑链。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")

    title = _html_esc(structure.get("title", "书籍思维导图"))
    one_line = _html_esc(structure.get("one_line_summary", ""))
    core_theme = _html_esc(structure.get("core_theme", ""))
    audience = _html_esc(structure.get("target_audience", ""))
    style = _html_esc(structure.get("writing_style", ""))

    generated_at = metadata.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    mode_label = metadata.get("mode", "detailed")
    chapter_count = len(chapters)

    # ── 按 Part 组织 ──
    parts: dict[str, list[dict]] = {}
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        pn = ch.get("part", "主体内容")
        parts.setdefault(pn, []).append(ch)

    part_names = list(parts.keys())
    MAX_CONTENT_TABS = 8
    if len(part_names) > MAX_CONTENT_TABS:
        merged_name = " · ".join(part_names[MAX_CONTENT_TABS - 1:])
        merged_chapters: list[dict] = []
        for pn in part_names[MAX_CONTENT_TABS - 1:]:
            merged_chapters.extend(parts[pn])
        new_parts = {pn: parts[pn] for pn in part_names[:MAX_CONTENT_TABS - 1]}
        new_parts[merged_name] = merged_chapters
        parts = new_parts
        part_names = list(parts.keys())

    # ── Tab 定义 ──
    TAB_ICONS = ["📜", "🏛️", "🏗️", "⚔️", "🏭", "🏢", "🔧", "🔮"]
    tab_defs: list[dict] = [{"id": "overview", "label": "🌐 总览"}]
    for i, pn in enumerate(part_names):
        icon = TAB_ICONS[i] if i < len(TAB_ICONS) else "📖"
        short = pn if len(pn) <= 8 else pn[:6] + "…"
        tab_defs.append({"id": f"part-{i}", "label": f"{icon} {short}", "part_name": pn, "part_idx": i})
    tab_defs.append({"id": "chain", "label": "🧭 逻辑链"})

    # ── 聚合概念 ──
    all_concepts: list[str] = []
    seen: set[str] = set()
    for ch in chapters:
        for c in ch.get("summary", {}).get("concepts", []):
            t = c.get("term", "")
            if t and t not in seen:
                seen.add(t)
                all_concepts.append(t)

    # ── 章节 accordion 构建 ──
    def _ch_acc(chap: dict) -> str:
        s = chap.get("summary", {})
        ch_title = _html_esc(chap.get("title", f"第{chap.get('number','?')}章"))
        ch_num = chap.get("number", "?")
        b: list[str] = []
        one = s.get("one_sentence", "")
        if one:
            b.append(f'<p style="color:var(--accent);font-weight:600;margin-bottom:0.8rem;">🎯 {_html_esc(one)}</p>')
        args = s.get("key_arguments", [])
        if args:
            items = "".join(f"<li>{_html_esc(_trim(str(a), 150))}</li>" for a in args if a and str(a).strip())
            b.append(f"<p style='font-weight:600;'>⭐ 核心论点</p><ul style='padding-left:1.2rem;color:var(--text2);font-size:0.9rem;'>{items}</ul>")
        cons = s.get("concepts", [])
        if cons:
            tags = " ".join(_html_tag(c.get("term", ""), "tag-blue") for c in cons[:8] if c.get("term"))
            b.append(f"<p style='font-weight:600;margin-top:0.6rem;'>📖 关键概念</p><div>{tags}</div>")
        ev = s.get("evidence", [])
        if ev:
            eis = "".join(f"<li>{_html_esc(_trim(e.get('description', str(e)) if isinstance(e, dict) else str(e), 120))}</li>" for e in ev[:5])
            b.append(f"<p style='font-weight:600;margin-top:0.6rem;'>📊 支撑论据</p><ul style='padding-left:1.2rem;color:var(--text2);font-size:0.9rem;'>{eis}</ul>")
        exs = s.get("examples", [])
        if exs:
            eis2 = "".join(f"<li>{_html_esc(_trim(str(e) if not isinstance(e, dict) else e.get('description', str(e)), 150))}</li>" for e in exs[:3])
            b.append(f"<p style='font-weight:600;margin-top:0.6rem;'>📋 案例</p><ul style='padding-left:1.2rem;color:var(--text2);font-size:0.9rem;'>{eis2}</ul>")
        quotes = s.get("quotes", [])
        for q in quotes[:2]:
            if isinstance(q, dict) and q.get("text"):
                b.append(f'<div class="highlight" style="margin-top:0.6rem;font-size:0.9rem;"><div class="hl-title">💬</div>「{_html_esc(_trim(q["text"], 200))}」</div>')
        crit = _s(s.get("critique", ""))
        lims = s.get("limitations", [])
        if crit or lims:
            txt = crit if crit else "；".join(str(l) for l in lims[:3])
            b.append(f'<div class="highlight warn" style="margin-top:0.8rem;"><div class="hl-title">⚠️ 质疑与局限</div>{_html_esc(_trim(txt, 200))}</div>')
        impl = _s(s.get("practical_implication", ""))
        if impl:
            b.append(f'<div class="highlight" style="margin-top:0.8rem;"><div class="hl-title">🎯 实践启示</div>{_html_esc(_trim(impl, 150))}</div>')
        return _html_accordion(f"第{ch_num}章：{ch_title}", "\n".join(b))

    def _part_content(pchaps: list[dict]) -> str:
        ps = pchaps[0].get("part_summary", "") if pchaps else ""
        header = ""
        if ps:
            header = f'<div class="highlight" style="margin-bottom:1.5rem;"><div class="hl-title">📂 本部分概览</div>{_html_esc(ps)}</div>'
        return header + "\n".join(_ch_acc(c) for c in pchaps)

    def _overview_tab() -> str:
        gl = {"business": "💼 商业/管理", "philosophy": "🧠 哲学/思想", "tech": "💻 技术/工程",
              "literature": "📖 文学/叙事", "academic": "🎓 学术/研究", "self-help": "🌱 自我提升", "auto": "📚 综合"}
        cw = " ".join(f'<span class="concept-node{" core" if i < 3 else ""}">{_html_esc(c)}</span>' for i, c in enumerate(all_concepts[:18]))
        return f"""<div class="card-grid-2" style="margin-bottom:1.5rem;">
<div class="card"><div class="card-title">📋 书籍信息</div>
<table style="width:100%;font-size:0.9rem;color:var(--text2);">
<tr><td style="padding:0.3rem 0;">📚 书名</td><td style="font-weight:600;color:var(--text);">{title}</td></tr>
<tr><td>🏷️ 流派</td><td>{gl.get(genre, '📚 综合')}</td></tr>
<tr><td>✍️ 风格</td><td>{style}</td></tr>
<tr><td>👥 读者</td><td>{audience}</td></tr>
<tr><td>📂 主题</td><td>{core_theme}</td></tr>
<tr><td>📖 章节</td><td>{chapter_count} 章 · {len(parts)} 部分</td></tr></table></div>
<div class="card"><div class="card-title">💡 核心命题</div>
<p style="color:var(--text2);font-size:0.95rem;line-height:1.8;">{one_line}</p></div></div>
<div class="highlight" style="margin-bottom:2rem;"><div class="hl-title">📊 全书核心概念网络</div><div class="concept-web">{cw}</div></div>
<div class="card-grid">{_build_structure_cards(parts, chapters)}</div>"""

    def _chain_tab() -> str:
        conns = []
        for ch in chapters:
            c = _s(ch.get("summary", {}).get("connection_to_book", ""))
            if c and c not in conns:
                conns.append(c)
        imps = []
        for ch in chapters:
            imp = _s(ch.get("summary", {}).get("practical_implication", ""))
            if imp:
                imps.append(f'<tr><td style="padding:0.4rem 0.5rem;color:var(--accent);font-weight:600;">第{ch.get("number","?")}章</td><td style="padding:0.4rem 0.5rem;color:var(--text2);">{_html_esc(_trim(imp, 150))}</td></tr>')
        cc = _build_concept_distribution_cards(chapters)
        conn_html = " ".join(f'<div class="flow-node dark" style="font-size:0.85rem;">{_html_esc(c)}</div>' for c in conns[:12]) if conns else '<p style="color:var(--text2);">（暂无跨章连接数据）</p>'
        impl_tab = f'<table class="compare-table" style="font-size:0.85rem;">{"".join(imps)}</table>' if imps else '<p style="color:var(--text2);">（暂无实践启示数据）</p>'
        return f"""<div class="card" style="margin-bottom:1.5rem;"><div class="card-title">🔄 全书论证脉络</div>
<div style="padding:1rem 0;"><div class="flow-container" style="justify-content:flex-start;flex-wrap:wrap;">{conn_html}</div></div></div>
<div class="card" style="margin-bottom:1.5rem;"><div class="card-title">🎯 各章实践启示</div>{impl_tab}</div>
<div style="margin-top:1.5rem;"><div class="card-title" style="margin-bottom:1rem;">📊 跨章概念分布</div><div class="card-grid">{cc}</div></div>"""

    # ── 组装 ──
    tab_contents: dict[str, str] = {}
    for td in tab_defs:
        sid = td["id"]
        if sid == "overview":
            tab_contents[sid] = _overview_tab()
        elif sid == "chain":
            tab_contents[sid] = _chain_tab()
        else:
            pn = td.get("part_name", "")
            pcs = parts.get(pn, [])
            ps = pcs[0].get("part_summary", "") if pcs else ""
            tab_contents[sid] = (
                f'<div class="card" style="margin-bottom:2rem;padding:2rem;text-align:center;">'
                f'<div class="card-title" style="font-size:1.3rem;">📂 {_html_esc(pn)}</div>'
                + (f'<p style="color:var(--text2);margin-top:0.5rem;">{_html_esc(ps)}</p>' if ps else "") +
                f'<p style="color:var(--text2);font-size:0.85rem;margin-top:0.5rem;">{len(pcs)} 章</p></div>\n'
                f'{_part_content(pcs)}'
            )

    nav_html = "\n".join(
        f'<div class="nav-item{" active" if i == 0 else ""}" data-section="{td["id"]}">{td["label"]}</div>'
        for i, td in enumerate(tab_defs)
    )
    section_html = "\n".join(
        f'<section class="section{" active" if i == 0 else ""}" id="sec-{td["id"]}">'
        f'<div class="section-title"><span class="icon">{td["label"].split()[0]}</span>{td["label"].split(" ",1)[-1]}</div>'
        f'{tab_contents.get(td["id"], "")}</section>'
        for i, td in enumerate(tab_defs)
    )

    gl = {"business": "💼 商业/管理", "philosophy": "🧠 哲学/思想", "tech": "💻 技术/工程",
          "literature": "📖 文学/叙事", "academic": "🎓 学术/研究", "self-help": "🌱 自我提升", "auto": "📚 综合"}

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>《{title}》交互式知识图谱</title>
<style>{HTML_CSS}</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="切换深色/护眼模式">
  <span class="t-option active" data-theme-val="dark">🌙</span>
  <span class="t-option" data-theme-val="light">☀️</span>
</button>

<section class="hero">
  <div class="hero-content">
    <div class="hero-badge">📚 交互式知识图谱 · AI 深度阅读可视化</div>
    <h1>{title}</h1>
    <h2>{one_line}</h2>
    <div class="hero-stats">
      <div class="hero-stat"><div class="num">{chapter_count}</div><div class="label">章节</div></div>
      <div class="hero-stat"><div class="num">{len(parts)}</div><div class="label">维度</div></div>
      <div class="hero-stat"><div class="num">{len(all_concepts)}</div><div class="label">核心概念</div></div>
      <div class="hero-stat"><div class="num">{mode_label}</div><div class="label">分析深度</div></div>
    </div>
  </div>
  <div class="scroll-hint">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 13l5 5 5-5M7 6l5 5 5-5"/></svg>
  </div>
</section>

<nav class="nav"><div class="nav-inner">{nav_html}</div></nav>

{section_html}

<footer style="text-align:center;padding:3rem;color:var(--text2);font-size:0.8rem;border-top:1px solid var(--border);">
  <p>📚 《{title}》交互式知识图谱 · {gl.get(genre, '📚 综合')}</p>
  <p style="margin-top:0.5rem;">基于 DeepSeek {mode_label} 模式全书分析 | 生成于 {generated_at}</p>
  <p style="margin-top:0.5rem;">🛠️ 工具：book-to-mindmap · 模型：{_html_esc(metadata.get('model','deepseek-chat'))}</p>
</footer>
<script>{HTML_JS}</script>
</body>
</html>"""


def build_html_full_preread(data: dict) -> str:
    """pre-read 富交互 HTML：按章节角色（基础/核心/案例/应用）分组展示。"""
    structure = data.get("structure", {})
    chapters = data.get("chapters", [])
    metadata = data.get("metadata", {})
    genre = metadata.get("genre", "auto")

    title = _html_esc(structure.get("title", "书籍思维导图"))
    one_line = _html_esc(structure.get("one_line_summary", ""))
    core_theme = _html_esc(structure.get("core_theme", ""))
    audience = _html_esc(structure.get("target_audience", ""))
    style = _html_esc(structure.get("writing_style", ""))
    complexity = structure.get("reading_complexity", "moderate")
    generated_at = metadata.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    roles: dict[str, list[dict]] = {}
    for ch in chapters:
        s = ch.get("summary", {})
        r = s.get("chapter_role", "core_argument")
        roles.setdefault(r, []).append(ch)

    role_meta = {
        "foundation": ("🧱 基础框架章", "必读——后续章节依赖", "tag-blue"),
        "core_argument": ("⭐ 核心论证章", "精读——全书最关键的论证", "tag-red"),
        "case_study": ("📋 案例章", "可速读——理解核心论证后再看", "tag-amber"),
        "application": ("🔧 应用章", "按需阅读", "tag-green"),
        "summary": ("📝 总结章", "浏览回顾全书要点", "tag-cyan"),
        "bridge": ("🌉 过渡章", "连接前后内容", ""),
    }

    role_tabs: list[dict] = []
    for role, chs in roles.items():
        if chs and role in role_meta:
            role_tabs.append({"id": f"role-{role}", "label": role_meta[role][0], "role": role, "chapters": chs})

    tabs: list[dict] = [{"id": "overview", "label": "🗺️ 阅读地图"}, {"id": "strategy", "label": "📋 阅读策略"}]
    for rt in role_tabs:
        tabs.append({"id": rt["id"], "label": rt["label"], "role_data": rt})
    tabs.append({"id": "notes", "label": "📝 读后笔记"})

    gl = {"business": "💼 商业/管理", "philosophy": "🧠 哲学/思想", "tech": "💻 技术/工程",
          "literature": "📖 文学/叙事", "academic": "🎓 学术/研究", "self-help": "🌱 自我提升", "auto": "📚 综合"}
    cl = {"easy": "🟢 轻松阅读", "moderate": "🟡 需要专注", "challenging": "🟠 有挑战", "dense": "🔴 需要精读"}

    ov = f"""<div class="card-grid-2"><div class="card"><div class="card-title">📋 书籍信息</div>
<table style="width:100%;font-size:0.9rem;color:var(--text2);">
<tr><td style="padding:0.3rem 0;">📚 书名</td><td style="font-weight:600;color:var(--text);">{title}</td></tr>
<tr><td>🏷️ 流派</td><td>{gl.get(genre, '📚 综合')}</td></tr>
<tr><td>✍️ 风格</td><td>{style}</td></tr>
<tr><td>📖 整体难度</td><td>{cl.get(complexity, '🟡 适中')}</td></tr>
<tr><td>👥 目标读者</td><td>{audience}</td></tr></table></div>
<div class="card"><div class="card-title">🧭 核心问题</div>
<p style="color:var(--accent);font-size:1.1rem;font-weight:700;">{one_line}</p>
<p style="margin-top:1rem;font-size:0.85rem;color:var(--text2);">把这个问题记在脑中，每读完一章回头问自己：这一章为回答这个问题提供了什么？</p></div></div>
<div class="highlight" style="margin-top:1.5rem;"><div class="hl-title">💡 使用说明</div>
<p style="font-size:0.9rem;color:var(--text2);">每个章节标注了核心问题 → 带着问题去读<br>关键概念只列名 → 读完用自己的话填写定义<br>☐ 读完勾选，一句话总结自己的理解<br>这份导图 = 你的个人笔记，不是 AI 的摘要</p></div>"""

    strategy_items = []
    for role, chs in roles.items():
        if chs and role in role_meta:
            label, desc, _ = role_meta[role]
            names = " · ".join(_html_esc(c.get("title", "?")) for c in chs[:5])
            strategy_items.append(f'<div class="card" style="margin-bottom:0.8rem;"><div class="card-title">{label}</div><p style="font-size:0.85rem;color:var(--text2);margin-bottom:0.3rem;">{desc}</p><p style="font-size:0.8rem;color:var(--text2);">涉及：{names}</p></div>')
    st_html = "\n".join(strategy_items) if strategy_items else '<p style="color:var(--text2);">（暂无策略数据）</p>'

    role_html_map: dict[str, str] = {}
    for rt in role_tabs:
        ch_items = []
        for chap in rt["chapters"]:
            s = chap.get("summary", {})
            ct = _html_esc(chap.get("title", f"第{chap.get('number','?')}章"))
            cn = chap.get("number", "?")
            b = []
            cq = s.get("core_question", "")
            if cq: b.append(f'<p style="color:var(--accent);font-weight:700;">🎯 {_html_esc(cq)}</p>')
            w = s.get("why_this_matters", "")
            if w: b.append(f'<p style="color:var(--text2);margin-top:0.4rem;">💡 {_html_esc(w)}</p>')
            g = s.get("reading_guide", "")
            if g: b.append(f'<p style="color:var(--text2);margin-top:0.4rem;font-style:italic;">📖 {_html_esc(g)}</p>')
            cs = s.get("concepts_to_watch", [])
            if cs:
                tags = " ".join(_html_tag(c, "tag-blue") for c in cs if c and str(c).strip())
                b.append(f'<p style="font-weight:600;margin-top:0.6rem;">🔑 重点关注概念</p><div>{tags}</div>')
            d = s.get("difficulty", "moderate")
            est = s.get("estimated_minutes", 15)
            db = {"easy": "🟢 轻松", "moderate": "🟡 适中", "challenging": "🟠 有挑战"}.get(d, "🟡")
            b.append(f'<p style="margin-top:0.6rem;font-size:0.85rem;color:var(--text2);">⚡ {db} · 预计 {est} 分钟</p>')
            b.append('<p style="font-size:0.85rem;color:var(--text2);">☐ 已读完本章 — 一句话总结：[　　　　　]</p>')
            ch_items.append(_html_accordion(f"第{cn}章：{ct}", "\n".join(b)))
        role_html_map[rt["id"]] = "\n".join(ch_items)

    notes = f"""<div class="card" style="padding:2rem;"><div style="font-size:0.95rem;color:var(--text2);line-height:2.2;">
<p>📖 这本书回答了：<em>{one_line}</em></p>
<p>💭 我最大的收获：[　　　　　　　　　　　　　　]</p>
<p>⚡ 改变了我对什么的看法：[　　　　　　　　　　　　　　]</p>
<p>🔗 与哪些已有的知识产生了关联：[　　　　　　　　　　　　　　]</p>
<p>📚 接下来想读的相关书：[　　　　　　　　　　　　　　]</p></div></div>"""

    contents = {"overview": ov, "strategy": st_html, "notes": notes}
    contents.update(role_html_map)

    nav_html = "\n".join(
        f'<div class="nav-item{" active" if i == 0 else ""}" data-section="{t["id"]}">{t["label"]}</div>'
        for i, t in enumerate(tabs)
    )
    section_html = "\n".join(
        f'<section class="section{" active" if i == 0 else ""}" id="sec-{t["id"]}">'
        f'<div class="section-title"><span class="icon">{t["label"].split()[0]}</span>{t["label"].split(" ",1)[-1]}</div>'
        f'{contents.get(t["id"], "")}</section>'
        for i, t in enumerate(tabs)
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>《{title}》阅读路线图</title>
<style>{HTML_CSS}</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="切换深色/护眼模式">
  <span class="t-option active" data-theme-val="dark">🌙</span>
  <span class="t-option" data-theme-val="light">☀️</span>
</button>
<section class="hero"><div class="hero-content">
<div class="hero-badge">🧭 阅读路线图 · Pre-Read 模式</div>
<h1>{title}</h1>
<h2>读前导航 —— 带着问题去读，边读边填自己的笔记</h2>
<div class="hero-stats">
<div class="hero-stat"><div class="num">{len(chapters)}</div><div class="label">章节</div></div>
<div class="hero-stat"><div class="num">{len(role_tabs)}</div><div class="label">角色类型</div></div>
<div class="hero-stat"><div class="num">{gl.get(genre, '📚')[:2]}</div><div class="label">流派</div></div>
<div class="hero-stat"><div class="num">{cl.get(complexity, '🟡')[:2]}</div><div class="label">难度</div></div>
</div></div>
<div class="scroll-hint"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 13l5 5 5-5M7 6l5 5 5-5"/></svg></div>
</section>
<nav class="nav"><div class="nav-inner">{nav_html}</div></nav>
{section_html}
<footer style="text-align:center;padding:3rem;color:var(--text2);font-size:0.8rem;border-top:1px solid var(--border);">
<p>🧭 《{title}》阅读路线图 · Pre-Read 模式 | 生成于 {generated_at}</p>
<p style="margin-top:0.5rem;">🛠️ 工具：book-to-mindmap · 模型：{_html_esc(metadata.get('model','deepseek-chat'))}</p>
</footer>
<script>{HTML_JS}</script>
</body></html>"""


def validate(md: str) -> list[str]:
    """对生成的 Markdown 做基础质量检查。"""
    warnings: list[str] = []
    lines_list = md.split("\n")

    h2 = sum(1 for l in lines_list if l.startswith("## "))
    h3 = sum(1 for l in lines_list if l.startswith("### "))
    if h2 < 2:
        warnings.append(f"⚠️  二级标题（部分）数量偏少（{h2}），结构可能不完整")
    if h3 == 0:
        warnings.append("⚠️  未检测到任何章节标题（###），请检查书籍格式或结构识别结果")

    # 检查长节点
    long_items = [l for l in lines_list if l.startswith("  - ") and len(l) > 140]
    if long_items:
        warnings.append(f"💡 {len(long_items)} 个叶节点超过 140 字，在 XMind 中可能会显示较长，建议关注")

    return warnings


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="构建思维导图输出文件")
    parser.add_argument("--summaries", required=True, help="摘要 JSON 文件路径")
    parser.add_argument("--output", default="./output/mindmap.md", help="输出文件路径")
    parser.add_argument("--format", default="markdown", choices=["markdown", "opml", "html", "html-full"],
                        help="输出格式（默认 markdown）。html-full=多Tab全景布局")
    args = parser.parse_args()

    with open(args.summaries, encoding="utf-8") as f:
        data = json.load(f)

    purpose = data.get("metadata", {}).get("purpose", "post-read")
    fmt = args.format

    format_labels = {"markdown": "Markdown", "opml": "OPML", "html": "HTML 交互式知识图谱", "html-full": "HTML 全景知识图谱"}
    label = f"🗺️  构建{format_labels.get(fmt, fmt)} {'阅读路线图' if purpose == 'pre-read' else '思维导图'}（{purpose}）…"
    print(label)

    if fmt == "html-full":
        output_text = build_html_full_preread(data) if purpose == "pre-read" else build_html_full(data)
    elif fmt == "html":
        output_text = build_html_preread(data) if purpose == "pre-read" else build_html(data)
    elif purpose == "pre-read":
        output_text = build_opml_preread(data) if fmt == "opml" else build_markdown_preread(data)
    else:
        output_text = build_opml(data) if fmt == "opml" else build_markdown(data)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(output_text, encoding="utf-8")

    # 只对 Markdown 做质量验证
    if fmt == "markdown":
        warns = validate(output_text)
        if warns:
            print("💡 质量提示：")
            for w in warns:
                print(f"  {w}")

    chapter_count = sum(1 for l in output_text.split("\n") if l.startswith("### ")) if fmt == "markdown" else len(data.get("chapters", []))
    print(f"\n✅ 完成！共 {chapter_count} 个章节节点")
    print(f"📄 输出文件：{out.resolve()}")

    if fmt in ("html", "html-full"):
        print("\n🌐 用浏览器打开 HTML 文件即可交互浏览")
        print("   💡 右上角 ☀️/🌙 按钮一键切换深色/护眼模式")
        if fmt == "html-full":
            print(f"   📑 多 Tab 全景布局 · {len(data.get('structure', {}).get('parts', []))} 个内容维度独立展示")
    elif purpose == "pre-read":
        print("\n📥 导入 XMind → 开始阅读 → 边读边在思维导图中填空和批注")
    elif fmt == "markdown":
        print("\n📥 导入 XMind：文件 → 导入 → Markdown")
    else:
        print("\n📥 导入 XMind / MindNode / FreeMind：文件 → 导入 → OPML")


if __name__ == "__main__":
    main()
