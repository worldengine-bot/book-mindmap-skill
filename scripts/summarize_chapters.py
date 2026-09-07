#!/usr/bin/env python3
"""
summarize_chapters.py — 调用 DeepSeek API（OpenAI 兼容）逐章提炼核心内容。
特性：
  - 并发处理（ThreadPoolExecutor），大幅缩短总耗时
  - 4 级详细程度（summary / standard / detailed / comprehensive）
  - 6 种书籍流派自动检测 + 手选，Prompt 自动匹配
  - 断点续跑（--checkpoint），中断不重跑
  - JSON 解析失败自动修复（含 AI repair 回退）
  - 输出结构化 JSON，供 build_mindmap.py 消费
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

# OpenAI SDK 延迟导入（不影响 --help 运行）

# ── 环境配置 ──────────────────────────────────────────────
MODEL = os.environ.get("BOOK_MINDMAP_MODEL", "deepseek-chat")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MAX_RETRIES = int(os.environ.get("BOOK_MINDMAP_RETRIES", "3"))
DEFAULT_WORKERS = int(os.environ.get("BOOK_MINDMAP_WORKERS", "8"))

# ── 系统提示词（全局）────────────────────────────────────
SYSTEM_PROMPT = (
    "你是一位资深的书籍分析专家，具备以下能力：\n"
    "- 快速识别书籍的论证结构、逻辑框架和知识体系\n"
    "- 精准提炼核心论点，保留原作者的表达精度与风格\n"
    "- 区分作者主张、支撑论据、案例数据和外部引用\n"
    "- 识别跨章节的主题联系、论证递进和概念演化\n"
    "- 输出结构清晰、层次分明的 JSON 分析结果\n\n"
    "⛔ 严格要求：只输出合法的 JSON 对象，不要有任何解释性文字、"
    "Markdown 代码块标记（```）或其他装饰。"
)

# ── 流派分析指令 ─────────────────────────────────────────
GENRE_INSTRUCTIONS: dict[str, str] = {
    "auto": "请先自动判断本章所属的书籍类型，然后选择最合适的分析角度。",

    "business": (
        "请从商业/管理角度分析本章，重点提炼：\n"
        "1. 作者的核心主张与底层商业逻辑\n"
        "2. 支撑数据、研究引用或企业案例\n"
        "3. 可执行的策略框架与行动建议\n"
        "4. 反直觉的洞见或挑战常识的观点\n"
    ),

    "philosophy": (
        "请从哲学/思想角度分析本章，重点提炼：\n"
        "1. 核心哲学命题与论证路径（前提→推论→结论）\n"
        "2. 与其他思想流派/思想家的对话或批评\n"
        "3. 关键概念的界定与精细区分\n"
        "4. 论证的实践意涵与可能的局限性\n"
    ),

    "tech": (
        "请从技术/工程角度分析本章，重点提炼：\n"
        "1. 核心技术概念、原理与设计哲学\n"
        "2. 适用场景、设计权衡与限制条件\n"
        "3. 与其他技术的对比（替代/互补/依赖）\n"
        "4. 常见误区、最佳实践与发展趋势\n"
    ),

    "literature": (
        "请从文学/叙事角度分析本章，重点提炼：\n"
        "1. 情节推进、叙事手法与结构设计\n"
        "2. 人物发展、关系演变与心理变化\n"
        "3. 核心意象、象征与主题深化\n"
        "4. 语言风格、情感张力与审美特征\n"
    ),

    "academic": (
        "请从学术研究角度分析本章，重点提炼：\n"
        "1. 研究问题、理论框架与核心假设\n"
        "2. 方法论选择、数据来源与因果推断\n"
        "3. 核心发现与对已有文献的贡献\n"
        "4. 研究局限与未来可探索的方向\n"
    ),

    "self-help": (
        "请从个人发展角度分析本章，重点提炼：\n"
        "1. 核心理念与需要改变的心智模式\n"
        "2. 具体方法与可操作步骤\n"
        "3. 背后的心理学/神经科学/行为经济学依据\n"
        "4. 常见的执行障碍与突破策略\n"
    ),
}

# ── 结构识别 Prompt ─────────────────────────────────────
STRUCTURE_PROMPT = """请分析以下书籍内容的整体结构。

【书籍内容——前 12 000 字】
{sample_text}

【任务】
1. 识别书名（如能确定）
2. 判断书籍流派：business | philosophy | tech | literature | academic | self-help
3. 一句话概括全书核心主旨
4. 列出所有部分（Part）和章节，每章附起始标记文字以供后续切分定位

【输出格式 — 严格 JSON，不要其他任何内容】
{
  "title": "书名（如无法确定填'未识别'）",
  "genre": "流派代码",
  "one_line_summary": "全书核心主旨（一句话，≤60 字）",
  "core_theme": "核心主题范畴关键词（1-5 个，逗号分隔）",
  "target_audience": "目标读者画像",
  "writing_style": "写作风格描述（如：论证严密+案例丰富 / 叙事为主+理论穿插 / 技术手册风格）",
  "structure_type": "linear | thematic | dialectic | narrative | reference",
  "reading_complexity": "easy | moderate | challenging | dense",
  "parts": [
    {
      "part_title": "部分名称（如无明确分部则用'全书'）",
      "part_summary": "这一部分的整体议题（一句话）",
      "chapters": [
        {
          "number": 1,
          "title": "章节完整标题",
          "start_marker": "章节正文开头 15-20 字的特征文字（用于精确定位切分点）",
          "estimated_tokens": 3000,
          "chapter_type": "theory | case | application | introduction | summary"
        }
      ]
    }
  ]
}"""

# ── 章节摘要 Prompt（按详细程度分 4 级）───────────────

CHAPTER_PROMPT_SUMMARY = """请快速提炼本章的关键信息。

【流派】{genre}
{genre_instructions}

【章节】第{number}章：{chapter_title}
【内容】
{chapter_text}

【输出 — 严格 JSON】
{
  "one_sentence": "本章核心要旨（≤35 字）",
  "key_arguments": ["核心论点 1（完整句）", "核心论点 2", "核心论点 3"],
  "concepts": [
    {"term": "术语", "definition": "简短定义（≤20 字）", "importance": "core | supporting"}
  ],
  "logic_flow": "论证推进逻辑（如：现象→原因→方案）"
}"""

CHAPTER_PROMPT_STANDARD = """请深入分析本章，不遗漏关键信息。

【流派】{genre}
{genre_instructions}

【章节】第{number}章：{chapter_title}
【内容】
{chapter_text}

【输出 — 严格 JSON】
{
  "one_sentence": "本章核心要旨（≤50 字）",
  "key_arguments": ["核心论点 1（精准表述）", "核心论点 2", "核心论点 3", "核心论点 4"],
  "concepts": [
    {
      "term": "术语名称",
      "definition": "精确定义（≤30 字）",
      "importance": "core | supporting",
      "related_to": ["关联术语（可为空数组）"]
    }
  ],
  "evidence": [
    {"type": "study | case | data | logic | anecdote", "description": "证据简述"}
  ],
  "examples": ["具体案例（≤2 个，如无则为空数组）"],
  "counterarguments": ["作者提及的反驳或限定（如无则为空数组）"],
  "logic_flow": "论证推进逻辑",
  "connection_to_prev": "与上一章的递进关系（第 1 章填 null）",
  "practical_implication": "本章观点的实践意义（如无可填空字符串）"
}"""

CHAPTER_PROMPT_DETAILED = """请全面、细致地分析本章，不遗漏重要细节，保留作者的原意和论证风格。

【流派】{genre}
{genre_instructions}

【章节】第{number}章：{chapter_title}
【内容】
{chapter_text}

【输出 — 严格 JSON】
{
  "one_sentence": "本章核心要旨（≤60 字）",
  "key_arguments": ["核心论点 1（完整表述，保留作者语气和论证风格）", "核心论点 2", "核心论点 3", "核心论点 4", "核心论点 5"],
  "supporting_points": ["支撑性分论点（可为空数组）"],
  "concepts": [
    {
      "term": "术语",
      "definition": "精确定义（≤40 字）",
      "importance": "core | supporting",
      "context": "首次出现或重点论述的上下文",
      "related_to": ["关联术语"]
    }
  ],
  "evidence": [
    {
      "type": "study | case | data | anecdote | thought_experiment | historical",
      "description": "证据详细描述",
      "strength": "strong | moderate | weak"
    }
  ],
  "examples": ["具体案例，保留关键细节（≤3 个）"],
  "quotes": [
    {
      "text": "值得引用的原文或译文（≤100 字）",
      "context": "出现的上下文",
      "significance": "为什么重要"
    }
  ],
  "counterarguments": ["反方观点或论证边界条件"],
  "logic_flow": "论证推进的完整逻辑链（步骤化）",
  "connection_to_prev": "与上一章的逻辑递进关系",
  "connection_to_book": "本章在全书论证结构中扮演的角色（铺垫/核心论证/案例支撑/应用/总结）",
  "practical_implication": "可操作的实际启示",
  "critique": "客观述评：论证的优势与可能的不足（如无则填空字符串）"
}"""

CHAPTER_PROMPT_COMPREHENSIVE = """请以学术级别的严谨和深度，对本章进行穷尽式分析，不遗漏任何有价值的信息点。

【流派】{genre}
{genre_instructions}

【章节】第{number}章：{chapter_title}
【内容】
{chapter_text}

【输出 — 严格 JSON】
{
  "one_sentence": "本章核心论点的最精炼表述（≤70 字）",
  "thesis_statement": "作者完整论点陈述（1-2 句，尽可能保留原文风貌）",
  "key_arguments": ["核心论点 1（完整、精准、可脱离上下文独立理解）", "核心论点 2", "核心论点 3", "核心论点 4", "核心论点 5", "核心论点 6"],
  "argument_structure": {
    "type": "deductive | inductive | analogical | dialectical | narrative",
    "premises": ["前提 1", "前提 2"],
    "reasoning_chain": "推理链条的逐步描述",
    "conclusion": "最终结论"
  },
  "supporting_points": [
    {
      "point": "支撑性分论点",
      "evidence_type": "study | case | logic | authority | data",
      "strength": "strong | moderate | weak"
    }
  ],
  "concepts": [
    {
      "term": "术语",
      "definition": "学术级精确定义（≤50 字）",
      "importance": "core | supporting | background",
      "first_introduced": true,
      "context": "使用的语境与范围",
      "related_to": ["关联术语"],
      "common_misunderstanding": "常见误解说明（如无则填空字符串）"
    }
  ],
  "evidence": [
    {
      "type": "study | case | data | anecdote | thought_experiment | historical",
      "description": "证据详细描述",
      "source": "原作者引用的出处（如有）",
      "strength": "strong | moderate | weak",
      "counterevidence_noted": true
    }
  ],
  "examples": ["具体案例，完整保留关键细节（≤4 个）"],
  "quotes": [
    {
      "text": "值得引用的原文金句（≤150 字）",
      "context": "出现的论证上下文",
      "significance": "为什么这句话重要或精彩"
    }
  ],
  "counterarguments": ["反方观点与论证局限"],
  "limitations": ["本章论证未覆盖的方面或潜在弱点"],
  "logic_flow": "完整的论证逻辑链（逐步描述）",
  "connection_to_prev": "与上一章的递进关系（第 1 章填 null）",
  "connection_to_book": "本章在全书论证结构中的定位与作用",
  "cross_references": ["跨章节的主题联系（如能识别）"],
  "practical_implication": "可操作的实际启示",
  "critique": "客观评述：论证的优势、潜在弱点、被忽视的视角",
  "further_reading": "相关的延伸阅读方向（如可推荐）"
}"""

# ── 跨章综合 Synthesis Prompt ──────────────────────────
SYNTHESIS_PROMPT = """你是一位资深学者，刚完成对一本著作的逐章精读。现在请你跳出逐章罗列的思维，对全书进行融会贯通的跨章综合分析。

【书名】{title}
【流派】{genre}
【全书主旨】{one_line_summary}

【各章摘要】
{all_chapter_summaries}

【任务】
以学术洞察力对全书进行 7 个维度的综合分析，揭示分散在各章中的深层逻辑联系。要求：
- 不要复述每章内容，而是提炼跨章主题和逻辑关系
- 论证架构要展示全书论证的递进阶段，而非章节排列
- 分析维度要跨越多个章节，展示主题的演化
- 概念演进要追踪核心概念在全书中的出现、深化、修正、应用过程
- 关键争议要揭示贯穿多章的理论张力或未解决的辩论
- 论据评估要从全书视角评判证据链的强弱
- 实践框架要将各章零散的实践启示整合为结构化可操作的体系

【输出格式 — 严格 JSON，无任何其他文字。保持简洁，每项 ≤80 字。】
{
  "book_thesis": "全书核心论点（1-2句）",
  "argument_architecture": {
    "overall_structure": "论证整体结构简述（≤40字）",
    "stages": [
      {
        "name": "阶段名称",
        "chapter_range": "如第1-4章",
        "chapter_numbers": [1, 2],
        "role": "功能（≤20字）",
        "key_move": "关键推进（≤40字）",
        "key_chapters_detail": [
          {"chapter": 1, "title": "章标题", "contribution": "贡献（≤30字）"}
        ]
      }
    ],
    "flow_diagram": [
      {"from": "阶段A", "to": "阶段B", "relationship": "奠定基础|深化论证|提供案例|提出挑战|综合升华"}
    ]
  },
  "analytical_dimensions": [
    {
      "name": "维度名称（≤12字）",
      "icon": "一个emoji",
      "summary": "核心洞见（≤60字）",
      "chapter_numbers": [1, 4, 8],
      "key_insights": ["洞见1（≤40字）", "洞见2"],
      "evolution": "演化轨迹（≤40字）",
      "concepts_involved": ["概念名"]
    }
  ],
  "concept_evolution": [
    {
      "concept": "概念名",
      "importance": "core|supporting|background",
      "evolution_stages": [
        {"chapter": 1, "stage": "introduced|refined|challenged|applied|synthesized", "description": "推进方式（≤30字）"}
      ],
      "maturation": "成熟轨迹总结（≤50字）"
    }
  ],
  "key_debates": [
    {
      "debate": "辩论主题（≤20字）",
      "nature": "theoretical|practical|perspectival",
      "positions": [
        {"side": "立场A", "chapter_numbers": [3], "core_argument": "主张（≤30字）"},
        {"side": "立场B", "chapter_numbers": [6], "core_argument": "主张（≤30字）"}
      ],
      "resolution": "裁决方式（≤30字）",
      "significance": "重要性（≤40字）"
    }
  ],
  "evidence_assessment": {
    "strongest_chains": [
      {"chapter": 1, "title": "章标题", "strength": "strong", "description": "简述（≤40字）"}
    ],
    "weakest_links": [
      {"chapter": 1, "title": "章标题", "weakness": "weak", "description": "简述（≤40字）"}
    ],
    "overall_pattern": "全书记证模式评价（≤50字）"
  },
  "practical_framework": {
    "overview": "总体框架（≤50字）",
    "components": [
      {
        "name": "组件名（≤15字）",
        "source_chapters": [2, 7],
        "actionable_insight": "洞见（≤50字）",
        "difficulty": "easy|moderate|challenging",
        "impact": "high|medium|low"
      }
    ],
    "implementation_roadmap": "实施路径（≤60字）"
  },
  "reading_pathways": [
    {
      "name": "路径名（≤12字）",
      "target_reader": "读者类型（≤15字）",
      "chapter_sequence": [1, 3, 5],
      "rationale": "理由（≤40字）"
    }
  ]
}

⛔ 注意：每个字段必须简短精炼。7个维度必须全部输出，不能遗漏任何顶层字段。"""

# ── 读前路线图 Prompt ──────────────────────────────────
PRE_READ_GENRE_INSTRUCTIONS: dict[str, str] = {
    "auto": "请自动判断本章类型，给出最合适的阅读引导角度。",

    "business": (
        "请从阅读商业书籍的角度引导：\n"
        "1. 关注作者的底层逻辑框架和核心假设\n"
        "2. 注意区分作者主张和案例数据——案例是为了说服你，不一定是真理\n"
        "3. 思考：这个框架在你的行业/公司是否适用？\n"
    ),

    "philosophy": (
        "请从阅读哲学著作的角度引导：\n"
        "1. 标注论证的起点（前提）和推进路径\n"
        "2. 提示读者注意关键概念的精确定义——同一术语在不同哲学家手中含义不同\n"
        "3. 引导读者寻找论证中的张力点和未说出的预设\n"
    ),

    "tech": (
        "请从阅读技术书籍的角度引导：\n"
        "1. 标注核心原理 vs 实现细节——前者不变，后者可能过时\n"
        "2. 提示读者关注设计取舍（为什么这么做而不是那样做）\n"
        "3. 暗示与其他技术的对比关系（但不说谁好谁坏）\n"
    ),

    "literature": (
        "请从阅读文学作品的角度引导：\n"
        "1. 提示叙事视角和叙事结构的特点（但不剧透情节走向）\n"
        "2. 关注人物动机和关系的微妙变化\n"
        "3. 标注反复出现的意象或主题线索\n"
    ),

    "academic": (
        "请从阅读学术著作的角度引导：\n"
        "1. 关注研究问题和理论框架的设定\n"
        "2. 提示方法论选择的意味（为什么用这种方法而非另一种）\n"
        "3. 引导读者注意因果推断的强度——相关≠因果\n"
    ),

    "self-help": (
        "请从阅读实用书籍的角度引导：\n"
        "1. 标注可操作的方法步骤，提示读者边读边想'我明天就可以做什么'\n"
        "2. 关注背后的原理依据（不是应该做X，而是因为Y所以X有效）\n"
        "3. 引导读者评判建议的适用边界——什么情况下这套方法不管用\n"
    ),
}

PRE_READ_SYSTEM_PROMPT = (
    "你是一位资深的阅读导航师。你的任务不是替读者读完一本书，而是为读者"
    "绘制一张阅读地图——告诉读者前面有什么、哪段路值得停留、哪里可以加速。\n\n"
    "核心原则：\n"
    "- 不剧透结论，只预告方向。说\"作者将论证X与Y的关系\"，不说\"作者证明X导致Y\"\n"
    "- 提出问题而非给出答案。好的阅读引导是让读者带着问题去读\n"
    "- 标注重点但留白。列出概念名但不给精确定义——等读者自己填\n"
    "- 给出阅读策略。这一章难不难？要不要精读？和前后章什么关系？\n\n"
    "⛔ 严格要求：只输出合法的 JSON 对象，不要有任何解释性文字。"
)

PRE_READ_STRUCTURE_PROMPT = """请分析以下书籍内容，为读前导航做准备。

【书籍内容——前 12 000 字】
{sample_text}

【任务】
1. 识别书名
2. 判断书籍流派
3. 用一句话概括这本书试图回答的核心问题（而非结论）
4. 列出所有部分和章节，标注每章在全书知识结构中的定位

【输出格式 — 严格 JSON】
{
  "title": "书名",
  "genre": "流派代码",
  "one_line_summary": "全书试图回答的核心问题（一句话，以'如何'或'为什么'开头，≤50 字）",
  "core_theme": "主题范畴（逗号分隔）",
  "target_audience": "适合读者",
  "writing_style": "写作风格",
  "structure_type": "linear | thematic | dialectic | narrative | reference",
  "reading_complexity": "easy | moderate | challenging | dense",
  "parts": [
    {
      "part_title": "部分名称",
      "part_summary": "这一部分在全书中的角色（如：奠定基础/展开论证/案例应用/总结归纳）",
      "chapters": [
        {
          "number": 1,
          "title": "章节标题",
          "start_marker": "章节正文开头 15-20 字特征文字",
          "chapter_type": "theory | case | application | introduction | summary",
          "estimated_tokens": 3000,
          "difficulty": "easy | moderate | challenging",
          "estimated_minutes": 15,
          "prerequisite_chapters": [],
          "skip_if": "什么情况下可以速读本章（如无法判断填'核心章节，建议精读'）"
        }
      ]
    }
  ]
}"""

PRE_READ_CHAPTER_PROMPT = """你的任务是为读者绘制本章的阅读路线图。不要替读者读完——给指引，留空间。

【流派】{genre}
{genre_instructions}

【章节】第{number}章：{chapter_title}
【内容】
{chapter_text}

【输出 — 严格 JSON】
{
  "core_question": "本章试图回答的核心问题（以'如何'或'为什么'开头，≤40 字）",
  "why_this_matters": "为什么这一章重要——不读会错过什么（≤50 字）",
  "concepts_to_watch": [
    "重点关注概念1——读者读完应能用自己的话解释",
    "重点关注概念2",
    "重点关注概念3"
  ],
  "reading_guide": "2-3 句阅读提示：哪里是关键论证、哪里有好的案例、哪里有容易误解的地方。不剧透结论，只预告类型",
  "author_moves": "作者在本章使用的关键论证手法（如：思想实验 / 数据分析 / 案例对比 / 历史回顾），不剧透具体内容",
  "difficulty": "easy | moderate | challenging",
  "estimated_minutes": 15,
  "chapter_role": "foundation | core_argument | case_study | application | summary | bridge",
  "depends_on": ["依赖的前序章节号（如无则空数组）"],
  "skip_if": "什么情况下可以速读（如无法判断填'核心章节，建议精读'）"
}"""

# ── Prompt 表 ────────────────────────────────────────────
PROMPT_TABLE = {
    "summary":      (CHAPTER_PROMPT_SUMMARY,      2000),
    "standard":     (CHAPTER_PROMPT_STANDARD,     4096),
    "detailed":     (CHAPTER_PROMPT_DETAILED,     6000),
    "comprehensive":(CHAPTER_PROMPT_COMPREHENSIVE,8000),
}


# ═══════════════════════════════════════════════════════════
# 模板填充工具（用 str.replace 避免 JSON 花括号冲突）
# ═══════════════════════════════════════════════════════════

def _fill(template: str, **kwargs) -> str:
    """安全填充模板，使用 {key} 语法但通过 str.replace 实现，JSON 的花括号不会冲突。"""
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


# ═══════════════════════════════════════════════════════════
# API 客户端
# ═══════════════════════════════════════════════════════════

def create_client() -> OpenAI:  # type: ignore[name-defined]
    from openai import OpenAI as OAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未检测到 DEEPSEEK_API_KEY 环境变量")
        print("   请设置：export DEEPSEEK_API_KEY='sk-...'")
        print("   获取 Key：https://platform.deepseek.com/api_keys")
        sys.exit(1)
    return OAI(api_key=api_key, base_url=BASE_URL)


def call_api(
    client,  # OpenAI client
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> str:
    """调用 DeepSeek Chat API，带指数退避重试 + rate-limit 保护。"""
    kwargs: dict = dict(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=messages,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            last_err = exc
            err_str = str(exc).lower()
            if "rate_limit" in err_str or "429" in err_str:
                wait = min(2 ** (attempt + 3), 60)
            elif "timeout" in err_str or "timed out" in err_str:
                wait = min(2 ** (attempt + 1), 30)
            else:
                wait = 2 ** attempt

            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(
                    f"API 调用失败（已重试 {MAX_RETRIES} 次）: {last_err}"
                ) from last_err

            print(f"  ⚠️  API 错误，{wait}s 后重试 ({attempt+1}/{MAX_RETRIES})…")
            time.sleep(wait)
    # unreachable
    raise RuntimeError(f"API 调用失败: {last_err}")


# ═══════════════════════════════════════════════════════════
# JSON 解析（多层 fallback）
# ═══════════════════════════════════════════════════════════

def _strip_markdown_fence(text: str) -> str:
    """去除 ```json ... ``` 包裹。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        # 找到第一个 { 和最后一个 }
        start = t.find("{")
        end = t.rfind("}")
        if start >= 0 and end > start:
            return t[start:end + 1]
        # 否则去首尾行
        if len(lines) >= 3:
            return "\n".join(lines[1:-1])
    return t


def _fix_trailing_commas(text: str) -> str:
    """修复 JSON 中常见的尾部逗号问题。"""
    # 移除 } 或 ] 前的逗号
    fixed = re.sub(r",\s*([}\]])", r"\1", text)
    return fixed


def safe_json_parse(text: str, retry_client=None) -> dict:
    """安全解析 JSON，失败时尝试自动修复 + AI repair 回退。"""
    cleaned = _strip_markdown_fence(text)

    # 尝试 1：直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试 2：修复尾部逗号
    try:
        return json.loads(_fix_trailing_commas(cleaned))
    except json.JSONDecodeError:
        pass

    # 尝试 3：截取第一个完整 JSON 对象
    start = cleaned.find("{")
    end = cleaned.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(cleaned[start:end])
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_fix_trailing_commas(cleaned[start:end]))
        except json.JSONDecodeError:
            pass

    # 尝试 4：让 AI 修复（成本最低的最后一招）
    if retry_client:
        try:
            repair_msg = (
                "以下 JSON 解析失败，请修复语法错误后输出正确的 JSON（仅输出 JSON，无任何其他文字）：\n\n"
                f"原始输出（截断）：\n{text[:2500]}\n\n"
                "请输出修复后的完整 JSON："
            )
            repaired = call_api(
                retry_client,
                [
                    {"role": "system", "content": "你是 JSON 修复器。只输出合法 JSON。"},
                    {"role": "user", "content": repair_msg},
                ],
                max_tokens=4096,
                temperature=0.0,
                json_mode=True,
            )
            return safe_json_parse(repaired, retry_client=None)
        except Exception:
            pass

    # 最终失败
    raise ValueError(f"JSON 解析彻底失败。原始内容前 600 字：\n{text[:600]}")


# ═══════════════════════════════════════════════════════════
# 结构识别
# ═══════════════════════════════════════════════════════════

def detect_structure(client, text: str, *, purpose: str = "post-read") -> dict:
    """识别书籍的整体结构（部分/章节划分）。pre-read 模式使用不同的系统提示和分析角度。"""
    print("🔍 识别书籍结构…")
    sample = text[:12000]

    if purpose == "pre-read":
        sys_prompt = PRE_READ_SYSTEM_PROMPT
        struct_prompt = _fill(PRE_READ_STRUCTURE_PROMPT, sample_text=sample)
    else:
        sys_prompt = SYSTEM_PROMPT
        struct_prompt = _fill(STRUCTURE_PROMPT, sample_text=sample)

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": struct_prompt},
    ]
    raw = call_api(client, messages, max_tokens=3000, temperature=0.2, json_mode=True)
    structure = safe_json_parse(raw, retry_client=client)

    title = structure.get("title", "未识别")
    genre = structure.get("genre", "auto")
    summary = structure.get("one_line_summary", "")
    parts = structure.get("parts", [])
    total_ch = sum(len(p.get("chapters", [])) for p in parts)

    print(f"  📚 书名：《{title}》")
    print(f"  🏷️  流派：{genre}")
    print(f"  {'🧭 核心问题' if purpose == 'pre-read' else '💡 主旨'}：{summary}")
    print(f"  📑 结构：{len(parts)} 部分 · {total_ch} 章")
    print()

    return structure


# ═══════════════════════════════════════════════════════════
# 章节切分
# ═══════════════════════════════════════════════════════════

def _flatten_chapters(structure: dict) -> list[dict]:
    """将嵌套的 parts→chapters 展开为扁平列表。"""
    flat: list[dict] = []
    for part in structure.get("parts", []):
        for ch in part.get("chapters", []):
            flat.append({
                "part": part.get("part_title", ""),
                "part_summary": part.get("part_summary", ""),
                "number": ch.get("number", len(flat) + 1),
                "title": ch.get("title", f"第{ch.get('number', len(flat)+1)}章"),
                "start_marker": ch.get("start_marker", ""),
                "chapter_type": ch.get("chapter_type", "theory"),
                "estimated_tokens": ch.get("estimated_tokens", 3000),
            })
    return flat


def split_chapters(text: str, structure: dict) -> list[dict]:
    """利用 start_marker 将全文切分到各章节；匹配失败时回退到智能均分。"""
    chapters_meta = _flatten_chapters(structure)

    if not chapters_meta:
        return [{
            "part": "全书", "part_summary": "", "number": 1,
            "title": structure.get("title", "全书内容"),
            "start_marker": text[:30].strip(),
            "chapter_type": "theory", "text": text[:12000],
        }]

    lines = text.split("\n")
    boundaries: list[tuple[int, int]] = []  # (chapter_index, line_index)

    # --- 第 1 轮：start_marker 精确匹配 ---
    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if len(stripped) < 5:
            continue
        for ci, chap in enumerate(chapters_meta):
            marker = chap.get("start_marker", "")
            if len(marker) >= 5:
                key = marker[:min(15, len(marker))]
                if key in stripped:
                    boundaries.append((ci, line_idx))
                    break

    # 去重：每章仅保留最早命中
    seen: set[int] = set()
    unique = [(ci, li) for ci, li in sorted(boundaries, key=lambda x: x[1]) if not (ci in seen or seen.add(ci))]

    # --- 第 2 轮：章节标题全文匹配（宽松） ---
    if len(unique) < max(1, len(chapters_meta) * 0.3):
        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            if len(stripped) < 3:
                continue
            for ci, chap in enumerate(chapters_meta):
                if ci in seen:
                    continue
                title = chap.get("title", "")
                if len(title) >= 3 and title in stripped:
                    seen.add(ci)
                    unique.append((ci, line_idx))
                    break

    unique.sort(key=lambda x: x[1])

    # --- 按边界切分 ---
    result: list[dict] = []
    for idx, (ci, start_line) in enumerate(unique):
        end_line = unique[idx + 1][1] if idx + 1 < len(unique) else len(lines)
        chap_text = "\n".join(lines[start_line:end_line])[:15000]
        result.append({**chapters_meta[ci], "text": chap_text})

    matched = {ci for ci, _ in unique}
    unmatched = [chapters_meta[i] for i in range(len(chapters_meta)) if i not in matched]

    # --- 回退：无任何匹配 → 按章节数均分 ---
    if not unique:
        chunk = max(1, len(lines) // len(chapters_meta))
        for i, chap in enumerate(chapters_meta):
            s = i * chunk
            e = s + chunk if i < len(chapters_meta) - 1 else len(lines)
            result.append({**chap, "text": "\n".join(lines[s:e])[:12000]})
    elif unmatched:
        # ── 智能回退：利用已匹配边界为未匹配章节分配真实文本 ──
        # 构建按章节号排序的 ci→line 映射；未匹配章从相邻已匹配章的文本间隙中均分
        ci_line = {ci: li for ci, li in unique}  # 已匹配章节 → 起始行
        sorted_chapters = sorted(enumerate(chapters_meta), key=lambda x: x[1].get("number", 0))

        # 对每个未匹配章节，找到前后最近的已匹配章节的行号边界
        unmatched_blocks: list[tuple[int, int, list[int]]] = []  # (start_line, end_line, [ci, ...])
        current_block_start = 0
        current_block_chapters: list[int] = []

        for ci, chap in sorted_chapters:
            if ci in ci_line:
                if current_block_chapters:
                    # 结束当前未匹配块：文本从 current_block_start 到此已匹配章起始行
                    unmatched_blocks.append((current_block_start, ci_line[ci], current_block_chapters))
                    current_block_chapters = []
                current_block_start = ci_line[ci]  # 下一块从当前匹配章起始行之后开始
            else:
                current_block_chapters.append(ci)

        # 处理最后的未匹配块
        if current_block_chapters:
            # 如果前面没有任何已匹配章，用文本开头；否则从上一匹配章之后开始
            unmatched_blocks.append((current_block_start, len(lines), current_block_chapters))

        for start_line, end_line, block_cis in unmatched_blocks:
            n = len(block_cis)
            block_lines = end_line - start_line
            chunk = max(1, block_lines // n)
            for j, ci in enumerate(block_cis):
                s = start_line + j * chunk
                e = start_line + (j + 1) * chunk if j < n - 1 else end_line
                chap_text = "\n".join(lines[s:e])[:15000]
                if len(chap_text.strip()) >= 60:
                    result.append({**chapters_meta[ci], "text": chap_text})
                else:
                    # 文本仍太短，回退到更大范围
                    fallback = "\n".join(lines[max(0, s-200):min(len(lines), e+200)])[:15000]
                    result.append({**chapters_meta[ci], "text": fallback})

    # 按章节号排序，确保输出顺序与书籍一致（不受标记匹配顺序影响）
    result.sort(key=lambda ch: ch.get("number", 0))
    return result


# ═══════════════════════════════════════════════════════════
# 单章摘要
# ═══════════════════════════════════════════════════════════

def summarize_chapter(
    client, chap: dict, mode: str, genre: str, *, purpose: str = "post-read"
) -> dict:
    """对单个章节调用 API 生成结构化摘要。pre-read 模式输出阅读路线图而非内容摘要。"""
    title = chap.get("title", f"第{chap.get('number', '?')}章")
    number = chap.get("number", "?")
    text = chap.get("text", "")

    if not text.strip() or len(text.strip()) < 60:
        return {
            "one_sentence": "（内容过短，无法分析）",
            "key_arguments": [],
            "concepts": [],
            "evidence": [],
            "examples": [],
            "logic_flow": "",
            "connection_to_prev": None,
        } if purpose == "post-read" else {
            "core_question": "（内容过短）",
            "why_this_matters": "",
            "concepts_to_watch": [],
            "reading_guide": "",
            "author_moves": "",
            "difficulty": "moderate",
            "estimated_minutes": 5,
            "chapter_role": "bridge",
            "depends_on": [],
            "skip_if": "",
        }

    if purpose == "pre-read":
        instr = PRE_READ_GENRE_INSTRUCTIONS.get(genre, PRE_READ_GENRE_INSTRUCTIONS["auto"])
        prompt = _fill(PRE_READ_CHAPTER_PROMPT,
            genre=genre,
            genre_instructions=instr,
            number=number,
            chapter_title=title,
            chapter_text=text,
        )
        sys_prompt = PRE_READ_SYSTEM_PROMPT
        max_tok = 3000
    else:
        template, max_tok = PROMPT_TABLE.get(mode, PROMPT_TABLE["standard"])
        instr = GENRE_INSTRUCTIONS.get(genre, GENRE_INSTRUCTIONS["auto"])
        prompt = _fill(template,
            genre=genre,
            genre_instructions=instr,
            number=number,
            chapter_title=title,
            chapter_text=text,
        )
        sys_prompt = SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": prompt},
    ]
    raw = call_api(client, messages, max_tokens=max_tok, temperature=0.3, json_mode=True)

    try:
        return safe_json_parse(raw, retry_client=client)
    except ValueError:
        return {
            "one_sentence": "（JSON 解析失败，已保留原始输出）",
            "key_arguments": [raw[:400]],
            "concepts": [],
            "evidence": [],
            "examples": [],
            "logic_flow": "",
            "connection_to_prev": None,
            "_raw_output": raw[:1200],
        } if purpose == "post-read" else {
            "core_question": "（解析失败）",
            "why_this_matters": "",
            "concepts_to_watch": [],
            "reading_guide": raw[:400],
            "author_moves": "",
            "difficulty": "moderate",
            "estimated_minutes": 10,
            "chapter_role": "core_argument",
            "depends_on": [],
            "skip_if": "",
        }


# ═══════════════════════════════════════════════════════════
# 并发编排 + 断点续跑
# ═══════════════════════════════════════════════════════════

def process_chapters(
    client,
    chapters: list[dict],
    mode: str,
    genre: str,
    max_workers: int,
    checkpoint_path: Optional[Path] = None,
    *,
    purpose: str = "post-read",
) -> list[dict]:
    """并发处理所有章节，可选断点续跑。"""
    total = len(chapters)
    results: list[Optional[dict]] = [None] * total

    # ── 恢复 checkpoint ──
    completed: set[int] = set()
    if checkpoint_path and checkpoint_path.exists():
        try:
            ckpt = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            for item in ckpt.get("completed", []):
                idx = item["index"]
                results[idx] = item["result"]
                completed.add(idx)
            if completed:
                print(f"📂 从断点恢复：{len(completed)}/{total} 章已完成\n")
        except Exception:
            pass

    pending = [(i, ch) for i, ch in enumerate(chapters) if i not in completed]
    if not pending:
        print("✅ 所有章节已在断点中完成！")
        return [r for r in results if r is not None]

    print(f"⚡ 并发处理 {len(pending)} 个章节（{max_workers} 线程）…\n")

    done_count = len(completed)

    def _save_ckpt():
        if not checkpoint_path:
            return
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        done = [{"index": i, "result": r} for i, r in enumerate(results) if r is not None]
        checkpoint_path.write_text(
            json.dumps({"completed": done, "total": total}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fut_map = {pool.submit(summarize_chapter, client, ch, mode, genre, purpose=purpose): i for i, ch in pending}

        for fut in as_completed(fut_map):
            idx = fut_map[fut]
            chap = chapters[idx]
            label = chap.get("title", f"第{chap.get('number','?')}章")
            try:
                summary = fut.result()
                results[idx] = {**chap, "summary": summary}
                done_count += 1
                print(f"  ✅ [{done_count}/{total}] {label}")
            except Exception as exc:
                done_count += 1
                print(f"  ❌ [{done_count}/{total}] {label} — {exc}")
                results[idx] = {
                    **chap,
                    "summary": {
                        "one_sentence": f"（处理失败）",
                        "key_arguments": [],
                        "concepts": [],
                        "error": str(exc)[:200],
                    },
                }

            if done_count % 3 == 0:
                _save_ckpt()

    _save_ckpt()

    # 成功后删除 checkpoint
    if checkpoint_path and checkpoint_path.exists():
        checkpoint_path.unlink()

    return [r for r in results if r is not None]


# ═══════════════════════════════════════════════════════════
# 跨章节综合分析
# ═══════════════════════════════════════════════════════════

def synthesize_book(
    client, chapters: list[dict], structure: dict, genre: str
) -> dict | None:
    """一次 LLM 调用，将所有章节摘要融合为跨章综合分析。

    返回 dict（合成结果）或 None（调用失败时，优雅降级）。
    """
    # ── 将各章摘要序列化为紧凑文本 ──
    chapter_texts: list[str] = []
    for ch in sorted(chapters, key=lambda c: c.get("number", 0)):
        s = ch.get("summary", {})
        parts: list[str] = []
        ch_num = ch.get("number", "?")
        ch_title = ch.get("title", "")
        parts.append(f"Ch{ch_num} {ch_title}")

        thesis = s.get("thesis_statement", "") or s.get("one_sentence", "")
        if thesis:
            parts.append(f"  论点：{thesis}")

        key_args = s.get("key_arguments", [])
        if key_args:
            args_text = "；".join(a for a in key_args[:3] if a and str(a).strip())
            if args_text:
                parts.append(f"  主张：{args_text}")

        concepts = s.get("concepts", [])
        if concepts:
            c_text = "、".join(c.get("term", "") for c in concepts[:4] if c.get("term"))
            if c_text:
                parts.append(f"  概念：{c_text}")

        conn_book = s.get("connection_to_book", "")
        if conn_book:
            parts.append(f"  定位：{conn_book[:80]}")

        cross = s.get("cross_references", [])
        if cross:
            parts.append(f"  跨章：{'；'.join(str(cr) for cr in cross[:2] if cr)}")

        chapter_texts.append("\n".join(parts))

    all_summaries = "\n\n---\n\n".join(chapter_texts)

    title = structure.get("title", "")
    one_line = structure.get("one_line_summary", "")

    prompt = _fill(
        SYNTHESIS_PROMPT,
        title=title,
        genre=genre,
        one_line_summary=one_line,
        all_chapter_summaries=all_summaries,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    print("\n🧠 执行跨章节综合分析（融会贯通全书，一次 LLM 调用）…")
    try:
        raw = call_api(client, messages, max_tokens=12000, temperature=0.4, json_mode=True)
        synthesis = safe_json_parse(raw, retry_client=client)
        print("  ✅ 综合分析完成")
        return synthesis
    except Exception as exc:
        print(f"  ⚠️  综合分析失败（将使用基础布局）: {exc}")
        return None


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="逐章摘要 — DeepSeek API")
    parser.add_argument("--text", required=True, help="解析后的纯文本路径")
    parser.add_argument("--output", default="/tmp/book2mindmap/summaries.json")
    parser.add_argument(
        "--mode", default="detailed",
        choices=["summary", "standard", "detailed", "comprehensive"],
        help="详细程度（默认 detailed）",
    )
    parser.add_argument(
        "--genre", default="auto",
        choices=["auto", "business", "philosophy", "tech", "literature", "academic", "self-help"],
        help="书籍流派（默认自动检测）",
    )
    parser.add_argument("--lang", default="auto", choices=["zh", "en", "auto"], help="输出语言")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_WORKERS,
                        help=f"并发线程数（默认 {DEFAULT_WORKERS}）")
    parser.add_argument("--checkpoint", action="store_true", help="启用断点续跑")
    parser.add_argument("--purpose", default="post-read", choices=["pre-read", "post-read"],
                        help="使用目的（默认 post-read）")
    parser.add_argument("--synthesize", action="store_true",
                        help="执行跨章节综合分析（一次额外 LLM 调用，推荐 comprehensive 模式使用）")
    args = parser.parse_args()

    # ── 读取文本 ──
    with open(args.text, encoding="utf-8") as f:
        text = f.read()

    print(f"📖 文本长度：{len(text):,} 字符\n")

    # ── 客户端 ──
    client = create_client()

    # ── Step 1：结构识别 ──
    structure = detect_structure(client, text, purpose=args.purpose)

    genre = args.genre
    if genre == "auto":
        genre = structure.get("genre", "business")
        print(f"  🤖 自动检测流派 → {genre}\n")

    lang = args.lang
    if lang == "auto":
        cn = sum(1 for c in text[:5000] if "一" <= c <= "鿿")
        lang = "zh" if cn > 100 else "en"
        print(f"  🌐 自动检测语言 → {lang}\n")

    # ── Step 2：切分 ──
    chapters = split_chapters(text, structure)
    print(f"📑 切分出 {len(chapters)} 个章节单元\n")

    if not chapters:
        print("❌ 未能识别任何章节，请检查书籍格式或尝试其他文件")
        sys.exit(1)

    # ── Step 3：并发摘要 ──
    ckpt_path = None
    if args.checkpoint:
        ckpt_dir = Path(args.output).parent / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        book_id = Path(args.text).stem
        ckpt_path = ckpt_dir / f"{book_id}_ckpt.json"

    results = process_chapters(client, chapters, args.mode, genre, args.max_workers, ckpt_path, purpose=args.purpose)

    # ── Step 4：跨章综合分析（可选，仅 post-read 模式）──
    synthesis = None
    if args.synthesize and args.purpose == "post-read":
        synthesis = synthesize_book(client, results, structure, genre)

    # ── 输出 ──
    output_data = {
        "structure": structure,
        "chapters": results,
        "metadata": {
            "purpose": args.purpose,
            "mode": args.mode if args.purpose == "post-read" else "pre-read",
            "genre": genre,
            "lang": lang,
            "model": MODEL,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "chapter_count": len(results),
            "total_chars": len(text),
        },
    }

    if synthesis:
        output_data["synthesis"] = synthesis

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 摘要完成 → {out}")
    print(f"   目的：{args.purpose}  ·  流派：{genre}  ·  章节：{len(results)}  ·  模型：{MODEL}")


if __name__ == "__main__":
    main()
