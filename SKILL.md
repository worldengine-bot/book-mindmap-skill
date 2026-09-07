---
name: book-to-mindmap
description: >
  将任意格式书籍转换为思维导图或交互式知识图谱。
  两种输出模式：
  ① Python 自动流水线（Markdown/OPML → XMind/Obsidian）
  ② 手工深度 HTML 交互式知识图谱（10-11 Tab 单页应用，暗/亮双主题，零外部依赖）。
  触发词："书转思维导图"、"生成脑图"、"导出 XMind"、"书籍结构化"、"读书笔记大纲"、
  "交互式知识图谱"、"输出html"、"制作html"、"/html"。
  即使用户只说"帮我整理这本书"，也应主动触发并询问偏好模式。
---

# Book → Mind Map Skill

## 两种输出模式（先询问用户偏好）

| 模式 | 触发词 | 输出 | 适用场景 |
|------|--------|------|----------|
| 🤖 **Python 自动流水线** | "生成脑图"、"导出XMind" | `.md` / `.opml` | 快速结构化·导入思维导图工具 |
| 🎨 **手工深度 HTML** | "交互式知识图谱"、"输出html"、"/html" | `.html` 单文件 | 深度阅读·多维度可视化·演示分享 |

> 当用户说"/html"或"制作成交互式知识图谱html"时，直接进入手工 HTML 模式。
> 当用户说"生成脑图"/"导出XMind"时，使用 Python 流水线。
> 当用户只说"帮我整理这本书"而未指定格式时，主动询问偏好。

---

## 模式一：Python 自动流水线（DeepSeek API）

## 工作流程

```
输入书籍文件
    ↓
[Step 1] parse_book.py → 提取纯文本（保留页码/标题/结构信息）
    ↓
[Step 2] summarize_chapters.py → DeepSeek API 并发逐章分析
    ├── 自动识别书籍流派（商业/哲学/技术/文学/学术/自我提升）
    ├── 识别章节结构（部分→章节 两级切分）
    └── 并发调用 API 生成结构化摘要（4 级详细程度可选）
    ↓
[Step 3] build_mindmap.py → 构建 XMind 兼容输出
    ├── Markdown 大纲（XMind 直接导入、Obsidian Mind Map 插件）
    └── OPML（MindNode、FreeMind、XMind 通用）
    ↓
输出可导入的 .md / .opml 文件
```

---

## Step 1：文件解析

根据文件类型选择解析策略，运行 `scripts/parse_book.py`：

```bash
python scripts/parse_book.py <书籍路径> --output /tmp/book2mindmap/book_text.txt
```

支持格式：
- **PDF** → 用 `pymupdf`（fitz）提取，保留页码 + 段落结构
- **EPUB** → 用 `ebooklib` 提取，按章节顺序拼接，保留标题
- **DOCX** → 用 `python-docx` 提取段落和标题层级
- **TXT/MD** → 直接读取

> 超大 PDF（>50 页）自动显示进度条。

---

## Step 2：结构识别 + 逐章摘要

### 2a. 结构识别

DeepSeek 先扫描全书前 12 000 字，输出：
- 书名、流派、核心主旨
- 所有部分（Part）和章节的完整目录
- 每章的起始标记文字（用于后续章节切分）

### 2b. 章节切分 + 并发摘要

利用结构识别结果将全文切分为独立章节，然后**并发调用 DeepSeek API** 对每章进行结构化提炼。

运行：
```bash
python scripts/summarize_chapters.py \
  --text /tmp/book2mindmap/book_text.txt \
  --output /tmp/book2mindmap/summaries.json \
  --mode detailed \
  --genre auto \
  --max-workers 8
```

### 两种使用目的

| `--purpose` | 含义 | 定位 |
|-------------|------|------|
| `pre-read` 🧭 | **读前路线图**（推荐） | 阅读地图——核心问题 + 关注点 + 填空位 |
| `post-read`（默认）| **读后知识总结** | 知识沉淀——论点 + 概念 + 论据 + 评述 |

**pre-read 模式输出的是一个可填充的思维导图模板：**
- 每章标注核心问题 → 带着问题去读
- 关键概念只列名不写定义 → 读的时候自己填
- ☐ 复选框 + 空白批注位 → 边读边做笔记
- 难度+预估时间+跳读建议 → 规划阅读节奏
- 读完这本书，这份导图就是**你自己的笔记**，不是 AI 的摘要

### 读后模式的详细程度选项（仅 post-read 生效）

| `--mode` | 说明 | 每章 token | 适用 |
|----------|------|-----------|------|
| `summary` | 仅核心论点+概念 | ~2k | 超大书快速概览 |
| `standard` | 标准分析 | ~4k | 常规阅读笔记 |
| `detailed` ⭐ | 深入分析（**默认**） | ~6k | 深度学习 |
| `comprehensive` | 学术级穷尽分析 | ~8k | 学术研究/写书评 |

### 流派选项

`--genre auto` 自动检测，或手动指定：
`business` · `philosophy` · `tech` · `literature` · `academic` · `self-help`

不同流派使用不同的分析 Prompt 模板，例如商业类会重点提炼"底层商业逻辑 + 可执行策略"，哲学类则关注"论证路径 + 概念界定"。pre-read 模式下流派模板切换为"阅读引导视角"（如哲学类会提示关注精确定义和预设，技术类会提示区分原理和实现细节）。

---

## Step 3：生成思维导图

```bash
# Markdown（XMind 导入）
python scripts/build_mindmap.py \
  --summaries /tmp/book2mindmap/summaries.json \
  --output ./output/<书名>_mindmap.md \
  --format markdown

# OPML（MindNode / FreeMind / XMind）
python scripts/build_mindmap.py \
  --summaries /tmp/book2mindmap/summaries.json \
  --output ./output/<书名>_mindmap.opml \
  --format opml
```

### Pre-Read 输出示例

```markdown
# 📚 《深度工作》阅读路线图

## 一、🗺️ 阅读地图总览
- 🎯 核心问题：如何在注意力分散的时代培养深度专注能力？
- 📖 整体难度：🟡 需要专注

## 二、📋 推荐阅读顺序
- 🧱 基础框架章（必读）：第1章 · 第2章
- ⭐ 核心论证章（精读）：第3章 · 第4章 · 第5章
- 📋 案例章（可速读）：第6章 · 第7章

### ⭐ 第3章：深度工作是有价值的
- 🎯 要回答的问题：为什么深度工作比浅层工作更有经济价值？
- 💡 为什么重要：全书最核心的论证——理解了"为什么"才有动力执行
- 📖 阅读提示
  > 作者用经济学框架论证，关注供需关系和稀缺性逻辑。案例涉及历史人物，注意判断相关性而非因果
- 🎬 论证手法：经济理论推演 + 历史人物案例
- 🔑 关键概念（读完用自己的话补充定义）
  - **深度工作**：[　　　]
  - **注意力残留**：[　　　]
  - **生产力度量**：[　　　]
- ⚡ 🟡 适中 · 预计 20 分钟
- ☐ 已读完本章
  - 一句话总结：[　　　　　]
  - 我没想到的：[　　　　　]
  - 我可以应用的：[　　　　　]
```

### 读后模式输出特征（专为 XMind 高级版优化）

- **emoji 标记系统**：⭐核心论点 · 💡洞见 · 📊数据 · 📋案例 · 💬引文 · ⚠️局限 · 🎯行动
- **块引用笔记**：XMind 会将 `> ` 开头的行渲染为 Topic Note
- **节点类型图标**：区分理论/案例/应用/引言等不同章节类型
- **关系标记**：跨章联系、论证逻辑链、概念关联
- **全书总结章**：自动聚合所有章节的实践启示

---

## 一键运行（推荐）

```bash
# 🧭 读前路线图 —— 最常用的命令
python main.py 深度工作.pdf --purpose pre-read

# 📝 读后总结 —— 默认模式
python main.py 深度工作.pdf
python main.py 思考快与慢.epub --mode detailed --format both
python main.py 纯粹理性批判.pdf --mode comprehensive --genre philosophy

# 大书处理：断点续跑 + 高并发
python main.py 巨著.pdf --purpose pre-read --checkpoint --workers 12
```

### 完整参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--purpose, -p` | `post-read` | pre-read（读前路线图）/ post-read（读后总结） |
| `--mode, -m` | `detailed` | summary / standard / detailed / comprehensive（仅 post-read） |
| `--genre, -g` | `auto` | 流派自动检测或手动指定 |
| `--format, -f` | `markdown` | markdown / opml / both |
| `--lang, -l` | `zh` | zh / en / auto |
| `--workers, -w` | `8` | 并发 API 调用数 |
| `--output, -o` | `./output/<书名>_mindmap.md` | 自定义输出路径 |
| `--checkpoint` | off | 启用断点续跑 |
| `--keep-tmp` | off | 保留临时文件（调试用） |

---

## 模式二：手工深度 HTML 交互式知识图谱（`/html`）

当用户说"/html"或"制作成交互式知识图谱html形式"时，使用此模式。

### 工作流程

1. **提取书籍文本**（PDF用PyMuPDF，扫描版用Swift Vision OCR；EPUB用unzip）
2. **深度阅读全书**（至少采样30-60页覆盖全部章节）
3. **参考模板**：阅读 `output/AI产业全景图谱_交互式知识图谱.html`（最完整的参考实现）
4. **手写HTML**：单文件·零外部依赖·暗/亮双主题·10-11 Tab导航·全部CSS/JS内联
5. **输出到** `output/<书名>_交互式知识图谱.html`

### HTML架构要求

- **Tab结构**（10个）：🌐总览 → 核心内容(×6-7) → 📖信息源 → 🧭逻辑链
- **信息源Tab** 必须包含：关键人物卡片(app-icon-card) + 核心文献表(compare-table) + 数据库/工具概念云(concept-web) + 使用指南(highlight)
- **CSS组件**：card/card-grid/flow-container/timeline/compare-table/highlight/concept-web/accordion/app-icon-card/scenario-card/stat-card
- **交互**：主题切换(localStorage)、Tab切换、IntersectionObserver滚动动画、折叠面板

### 完整的实现细节和代码模式见 `CLAUDE.md`

---

## 环境要求

```bash
# Python 依赖
pip install openai pymupdf ebooklib beautifulsoup4 python-docx

# DeepSeek API Key（必需）
export DEEPSEEK_API_KEY="sk-..."

# 可选：自定义模型
export BOOK_MINDMAP_MODEL="deepseek-chat"        # 默认
export BOOK_MINDMAP_WORKERS="10"                 # 默认 8
```

---

## XMind 导入方法

1. 打开 XMind
2. 文件 → 导入 → Markdown（或 OPML）
3. 选择生成的 `.md` 或 `.opml` 文件
4. XMind 自动生成多级思维导图 ✓

> **Obsidian 用户**：直接放入 vault，配合 Mind Map 插件渲染。
> **Logseq 用户**：复制大纲内容粘贴即可。
> **MindNode 用户**：使用 OPML 格式导入。

---

## 导入后的优化建议（XMind 高级版）

生成导图后，可利用 XMind 高级功能手动增强：

1. **添加关系线**：在全书总结视图下，用"关系"连接跨章相关概念
2. **应用主题**：切换 XMind 内置主题调整配色（推荐"优雅"或"商务"主题）
3. **添加边界**：为每个 Part 创建边界框，使结构更清晰
4. **折叠/展开**：利用 XMind 的逐级展开功能，从全书概览逐级下钻
5. **导出分享**：导出为 PNG/SVG/PDF 用于演示或打印

---

## 错误处理

| 问题 | 解决方案 |
|------|----------|
| PDF 扫描版（无文字层） | 先用 OCR 工具处理：`ocrmypdf input.pdf output.pdf` |
| 文件过大（>500页） | 自动并发处理，可加 `--checkpoint` 防中断 |
| API 超时/429 | 自动重试 3 次，rate limit 最长等待 60s |
| 章节识别失败 | 回退到均分模式，或手动编辑 `summaries.json` 再跑 Step 3 |
| JSON 解析失败 | 4 级 fallback：去 fence→修尾逗号→截取→AI repair |
| 断点续跑 | 用 `--checkpoint`，每 3 章存一次进度，重跑跳过已完成章节 |

---

## 费用参考（DeepSeek）

| 书籍规模 | 模式 | 约 Token 消耗 | 约费用 |
|---------|------|-------------|--------|
| 薄书（<100页） | detailed | ~30k | ¥0.03 |
| 中等（100-300页） | detailed | ~80k | ¥0.08 |
| 厚书（300-500页） | detailed | ~150k | ¥0.15 |
| 厚书 | comprehensive | ~300k | ¥0.30 |

> DeepSeek API 定价约 ¥1/百万 token，成本约为 Sonnet 的 1/20-1/50。
