# 📚 book-to-mindmap

> Turn any book into an interactive knowledge map — a **Claude Code Skill**.
> Say one sentence (or `/book-to-mindmap`); the scripts run automatically behind the scenes — **no manual Python setup, no commands**.

<details>
<summary>🇨🇳 中文 / Chinese（点击展开）</summary>

## 中文版

> 一个 **Claude Code Skill**：把任意格式书籍一键转成知识图谱。
> 你只需说一句话（或 `/book-to-mindmap`），底层脚本由 Skill 自动执行，**无需手动装 Python、敲命令**。

### 两种输出模式（一句话触发）

| 想要什么 | 怎么说（触发词） | 产物 |
|---------|----------------|------|
| 🤖 思维导图（XMind / Obsidian） | 「生成脑图」「导出 XMind」 | `.md` / `.opml` |
| 🎨 交互式知识图谱 | 「/html」「交互式知识图谱」 | `.html` 单文件 |

> 只说「帮我整理这本书」而不指定格式时，Skill 会先问你要哪种。

**🌐 输出语言跟随提问者**：英文提问 → 生成英文；中文提问 → 生成中文。

### 一键安装

复制下面这行发给任意 agent，它会自动把 skill 装好并引导配置：

```
请安装 book-to-mindmap 技能：克隆 https://github.com/worldengine-bot/book-mindmap-skill 到 skills 目录，并引导我配置 DeepSeek API Key（没有 Key 的话告诉我去哪申请）
```

> 装好后再看「快速上手」，一句话即可生成导图。

### 快速上手

复制下面任意一行，直接发给 Claude 即可：

```
生成脑图 深度工作.pdf        # → 产出 .md/.opml，导入 XMind
/html 深度工作.pdf          # → 产出单文件交互式 HTML 图谱
```

> 首次使用只需两件事：① 把本仓库放进 skills 目录（如 `~/.claude/skills/book-to-mindmap/`）；② 配好 `DEEPSEEK_API_KEY`。之后每次一句话即可，无需再装任何东西。

### 环境要求（仅当脱离 Skill 手动运行脚本时才需要）

```bash
pip install openai pymupdf ebooklib beautifulsoup4 python-docx
export DEEPSEEK_API_KEY="sk-..."

# 可选配置
export BOOK_MINDMAP_MODEL="deepseek-chat"   # 默认模型
export BOOK_MINDMAP_WORKERS="10"            # 并发数，默认 8
```

### 支持的模型（不限 DeepSeek / Claude）

摘要步骤走的是 **OpenAI 兼容接口**，任何支持该协议的服务都能用；默认选 DeepSeek 只因性价比高：

| 想用 | 需要设置的环境变量 |
|------|------------------|
| DeepSeek（默认） | `DEEPSEEK_API_KEY=sk-...` |
| OpenAI / Codex | `DEEPSEEK_API_KEY=<OpenAI key>` · `DEEPSEEK_BASE_URL=https://api.openai.com/v1` · `BOOK_MINDMAP_MODEL=gpt-...` |
| 其他（Gemini / Qwen / GLM / Moonshot…） | 同上，换成对应 `base_url` 与模型名 |

> 换模型只改 3 个环境变量（变量名沿用 DeepSeek 命名，属历史遗留）。三个 Python 脚本本身是普通 CLI，不依赖 Claude，任何 agent 或终端都能调用。

### 模式一：XMind 思维导图（Python 流水线）

从书籍到可导入 XMind 的导图，自动跑完三步：

```
书籍文件 → [1] 解析文本 → [2] AI 逐章分析 → [3] 生成 .md / .opml
```

1. **解析**：`parse_book.py` 提取纯文本（PDF / EPUB / DOCX / TXT 通吃）
2. **分析**：`summarize_chapters.py` 并发调用大模型逐章结构化提炼
   - 自动识别流派（商业 · 哲学 · 技术 · 文学 · 学术 · 自我提升），套用对应模板
   - 两种用途：`pre-read` 读前路线图（可填充的阅读模板）/ `post-read` 读后总结（默认）
   - 四级深度：`summary → standard → detailed → comprehensive`
3. **生成**：`build_mindmap.py` 输出 XMind 兼容的 Markdown / OPML

#### 一键运行

```bash
python main.py 深度工作.pdf                            # 读后总结（默认）
python main.py 深度工作.pdf --purpose pre-read         # 读前路线图
python main.py 思考快与慢.epub --mode detailed --format both
python main.py 巨著.pdf --checkpoint --workers 12      # 大书断点续跑
```

#### 主要参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--purpose, -p` | post-read | pre-read 读前路线图 / post-read 读后总结 |
| `--mode, -m` | detailed | summary / standard / detailed / comprehensive |
| `--genre, -g` | auto | 流派自动检测或手动指定 |
| `--format, -f` | markdown | markdown / opml / both |
| `--workers, -w` | 8 | 并发 API 调用数 |
| `--checkpoint` | off | 断点续跑 |

#### 导入 XMind

1. XMind → 文件 → 导入 → Markdown（或 OPML）
2. 选择生成的 `.md` / `.opml` 文件
3. 自动生成多级思维导图 ✓

其他工具：Obsidian（Markdown + Mind Map 插件）· Logseq（Markdown）· MindNode / FreeMind（OPML）。

### 模式二：交互式 HTML 知识图谱（`/html`）

说「/html」或「交互式知识图谱」即可生成单文件 HTML：

- 🖥️ 单文件、零依赖：CSS/JS 全内联，无需联网、无需框架
- 🌗 暗/亮双主题，localStorage 持久化
- 🧭 约 10 个 Tab（总览 → 核心内容 → 📖 信息源 → 🧭 逻辑链）
- 📖 可点击概念网络，节点直达对应章节
- 📱 响应式布局

产出 `output/<书名>_交互式知识图谱.html`，双击即看。制作规范见 `CLAUDE.md`。
（`output/` 为本地产物，已加入 `.gitignore`，不会上传。）

### 目录结构

```
book-to-mindmap/
├── SKILL.md           ← Skill 定义（触发词 + 两种模式）
├── CLAUDE.md          ← HTML 制作规范
├── main.py            ← 一键入口（Python 流水线）
├── scripts/           ← parse_book / summarize_chapters / build_mindmap
├── references/        ← prompt 工程参考
└── README.md
```

### 费用参考（DeepSeek，2026-08-17 起峰谷定价）

> ⚠️ 旧版「输入 ¥1/M、输出 ¥2/M」已过时。现行价格（元 / 百万 token）：

| 模型 | 时段 | 输入·缓存未命中 | 输出 |
|------|------|----------------|------|
| deepseek-v4-flash | 空闲 | ¥1.5 | ¥4.5 |
| deepseek-v4-flash | 高峰 | ¥3.0 | ¥9.0 |
| deepseek-v4-pro | 空闲 | ¥4.5 | ¥13.5 |
| deepseek-v4-pro | 高峰 | ¥9.0 | ¥27.0 |

- 高峰时段：北京时间 9:00–12:00、14:00–18:00；空闲时段为高峰的一半。
- 缓存命中价约为未命中的 1/100，是控成本关键。

**典型一本书估算成本**（`deepseek-v4-flash`·空闲时段·缓存未命中，供参考）：

| 书籍规模 | 约 Token | 约费用 |
|---------|---------|--------|
| 薄书（<100页） | ~30k | ~¥0.05 |
| 中等（100–300页） | ~80k | ~¥0.15 |
| 厚书（300–500页） | ~150k | ~¥0.25 |
| 厚书 comprehensive | ~300k | ~¥0.50 |

> 实际费用随峰谷、缓存命中、模型选择浮动（高峰 ≈ 空闲 ×2，v4-pro ≈ v4-flash ×3）。可用 `BOOK_MINDMAP_MODEL` 指定模型。

### 常见问题

**Q：PDF 扫描版无法识别？**
A：先用 OCR 处理：`ocrmypdf input.pdf output.pdf`

**Q：章节识别错误或遗漏？**
A：在 `summaries.json` 中手动调整章节列表，再单独运行 `build_mindmap.py`

**Q：想调整输出风格或分析角度？**
A：编辑 `scripts/summarize_chapters.py` 中的 `GENRE_INSTRUCTIONS` 字典，或添加自定义流派

**Q：能直接用 Claude API 吗？**
A：可以，需修改 `summarize_chapters.py` 中的 API 调用部分。DeepSeek 是默认推荐（成本低、速度快）

**Q：最大能处理多大的书？**
A：理论上无上限——章节切分后每章独立处理，加上断点续跑，1000 页+ 的书也能逐步完成

</details>

---

## Two Output Modes (trigger with one sentence)

| What you want | What to say (trigger) | Output |
|--------------|----------------------|--------|
| 🤖 Mind map (XMind / Obsidian) | "generate mind map", "export to XMind" | `.md` / `.opml` |
| 🎨 Interactive knowledge graph | `/html`, "interactive knowledge graph" | single `.html` file |

> If you only say "help me organize this book" without a format, the Skill will ask which mode you want.

**🌐 Language follows the user**: ask in English → English output; ask in Chinese → Chinese output.

---

## One-Click Install

Copy and send the line below to any agent — it will install the skill and guide you through setup:

```
Please install the book-to-mindmap skill: clone https://github.com/worldengine-bot/book-mindmap-skill into the skills directory, and guide me to configure the DeepSeek API Key (tell me where to get one if I don't have it)
```

> Once installed, see "Quick Start" below — one sentence generates your map.

---

## Quick Start

Copy either line below and send it to Claude:

```
generate mind map  Deep Work.pdf   # → .md/.opml, import into XMind
/html  Deep Work.pdf               # → single-file interactive HTML graph
```

> First use only requires two things: ① put this repo in the skills directory (e.g. `~/.claude/skills/book-to-mindmap/`); ② set `DEEPSEEK_API_KEY` (see "Environment Requirements"). After that, one sentence each time.

---

## Environment Requirements (only needed when running scripts manually, outside the Skill)

```bash
pip install openai pymupdf ebooklib beautifulsoup4 python-docx
export DEEPSEEK_API_KEY="sk-..."

# optional
export BOOK_MINDMAP_MODEL="deepseek-chat"   # default model
export BOOK_MINDMAP_WORKERS="10"            # concurrency, default 8
```

---

## Supported Models (not limited to DeepSeek / Claude)

The summarization step uses an **OpenAI-compatible API**, so any service speaking that protocol works; DeepSeek is the default simply for cost:

| Want to use | Env vars to set |
|-------------|-----------------|
| DeepSeek (default) | `DEEPSEEK_API_KEY=sk-...` |
| OpenAI / Codex | `DEEPSEEK_API_KEY=<OpenAI key>` · `DEEPSEEK_BASE_URL=https://api.openai.com/v1` · `BOOK_MINDMAP_MODEL=gpt-...` |
| Others (Gemini / Qwen / GLM / Moonshot…) | same as above, with the matching `base_url` and model name |

> Switching models only changes 3 env vars (the names are DeepSeek-ified legacy). The three Python scripts are plain CLIs, independent of Claude — callable from any agent or terminal.

---

## Mode 1: XMind Mind Map (Python pipeline)

From book to XMind-importable map in three automatic steps:

```
book file → [1] parse text → [2] AI per-chapter analysis → [3] build .md / .opml
```

1. **Parse**: `parse_book.py` extracts plain text (PDF / EPUB / DOCX / TXT)
2. **Analyze**: `summarize_chapters.py` calls an LLM concurrently, chapter by chapter
   - auto-detects genre (business · philosophy · tech · literature · academic · self-help) and applies a matching template
   - two purposes: `pre-read` reading roadmap (a fill-in template) / `post-read` summary (default)
   - four depths: `summary → standard → detailed → comprehensive`
3. **Build**: `build_mindmap.py` emits XMind-compatible Markdown / OPML

### One-liner

```bash
python main.py 深度工作.pdf                            # post-read summary (default)
python main.py 深度工作.pdf --purpose pre-read         # pre-read roadmap
python main.py 思考快与慢.epub --mode detailed --format both
python main.py 巨著.pdf --checkpoint --workers 12      # big book, checkpoint resume
```

### Key options

| Option | Default | Description |
|--------|---------|-------------|
| `--purpose, -p` | post-read | pre-read roadmap / post-read summary |
| `--mode, -m` | detailed | summary / standard / detailed / comprehensive |
| `--genre, -g` | auto | auto-detect or specify genre |
| `--format, -f` | markdown | markdown / opml / both |
| `--workers, -w` | 8 | concurrent API calls |
| `--checkpoint` | off | checkpoint resume |

### Import into XMind

1. XMind → File → Import → Markdown (or OPML)
2. Choose the generated `.md` / `.opml`
3. A multi-level mind map is generated ✓

Other tools: Obsidian (Markdown + Mind Map plugin) · Logseq (Markdown) · MindNode / FreeMind (OPML).

---

## Mode 2: Interactive HTML Knowledge Graph (`/html`)

Say `/html` or "interactive knowledge graph" to generate a single-file HTML:

- 🖥️ Single file, zero dependencies: CSS/JS all inlined, offline, no framework
- 🌗 Dark/light theme, persisted via localStorage
- 🧭 ~10 tabs (overview → core content → 📖 sources → 🧭 logic chain)
- 📖 Clickable concept web, nodes jump to the matching section
- 📱 Responsive layout

Outputs `output/<book>_交互式知识图谱.html`, double-click to open. Authoring spec in `CLAUDE.md`.
(`output/` is local-only and gitignored — not uploaded.)

---

## Directory Structure

```
book-to-mindmap/
├── SKILL.md           ← Skill definition (triggers + two modes)
├── CLAUDE.md          ← HTML authoring spec
├── main.py            ← one-command entry (Python pipeline)
├── scripts/           ← parse_book / summarize_chapters / build_mindmap
├── references/        ← prompt engineering reference
└── README.md
```

---

## Pricing (DeepSeek, peak/off-peak since 2026-08-17)

> ⚠️ The old "input ¥1/M, output ¥2/M" is outdated. Current prices (CNY per million tokens):

| Model | Period | Input (cache miss) | Output |
|-------|--------|-------------------|--------|
| deepseek-v4-flash | off-peak | ¥1.5 | ¥4.5 |
| deepseek-v4-flash | peak | ¥3.0 | ¥9.0 |
| deepseek-v4-pro | off-peak | ¥4.5 | ¥13.5 |
| deepseek-v4-pro | peak | ¥9.0 | ¥27.0 |

- Peak hours: Beijing 9:00–12:00, 14:00–18:00; off-peak is half the peak price.
- Cache-hit price is ~1/100 of cache-miss — the key lever for cost control.

**Typical per-book estimate** (`deepseek-v4-flash` · off-peak · cache miss, for reference):

| Book size | ~Tokens | ~Cost |
|-----------|---------|-------|
| Thin (<100 pages) | ~30k | ~¥0.05 |
| Medium (100–300 pages) | ~80k | ~¥0.15 |
| Thick (300–500 pages) | ~150k | ~¥0.25 |
| Thick + comprehensive | ~300k | ~¥0.50 |

> Actual cost varies by peak/off-peak, cache hits, and model (peak ≈ off-peak ×2, v4-pro ≈ v4-flash ×3). Pick a model via `BOOK_MINDMAP_MODEL`.

---

## FAQ

**Q: Scanned PDF won't OCR?**
A: Preprocess with `ocrmypdf input.pdf output.pdf`

**Q: Chapter detection wrong or missing?**
A: Adjust the chapter list in `summaries.json`, then rerun `build_mindmap.py`

**Q: Want to change output style or analysis angle?**
A: Edit `GENRE_INSTRUCTIONS` in `scripts/summarize_chapters.py`, or add a custom genre

**Q: Can I use the Claude API directly?**
A: Yes — modify the API call part of `summarize_chapters.py`. DeepSeek is the default recommendation (low cost, fast)

**Q: How big a book can it handle?**
A: Theoretically unbounded — chapters are split and processed independently, plus checkpoint resume, so even 1000+ page books complete gradually.
