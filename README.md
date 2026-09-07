# 📚 book-to-mindmap

> 将任意格式书籍一键转换为知识图谱，支持两种输出模式：
>
> 1. **XMind 高级思维导图**（Markdown + OPML）—— 基于 DeepSeek API 自动生成
> 2. **交互式 HTML 知识图谱**（多 Tab 单文件）—— 手工精制的阅读概览页

---

## 特性

- 🔌 **任意格式**：PDF / EPUB / DOCX / TXT / Markdown 通吃
- ⚡ **并发处理**：8 线程并行调用 API，30 章的书 ~15 秒完成
- 🎯 **智能分析**：自动识别书籍流派（商业·哲学·技术·文学·学术·自我提升），匹配分析模板
- 📊 **四级深度**：summary → standard → detailed → comprehensive，从快速概览到学术级穷尽
- 🎨 **XMind 高级版优化**：emoji 标记、块引用笔记、类型图标、关系链、论证结构
- 💰 **极低成本**：处理一本 300 页的书约 ¥0.08（DeepSeek API）
- 🔁 **断点续跑**：中断后自动从已完成章节恢复

---

## 模式二：交互式 HTML 知识图谱

`output/` 目录下提供了大量手工精制的单文件 HTML 阅读概览页（`*_交互式知识图谱.html`），特点：

- 🖥️ **单文件、零依赖**：所有 CSS/JS 内联，无需联网、无需框架
- 🌗 **深色/浅色主题**：一键切换，localStorage 持久化
- 🧭 **多 Tab 导航**：约 10 个标签页覆盖全书结构、核心概念、时间线、信息源等
- 📖 **可点击概念网络**：概念节点可直接跳转到对应章节
- 📱 **响应式布局**：适配笔记本与窄屏

直接双击任意 `.html` 文件即可在浏览器中查看。HTML 制作工作流的详细规范见 `CLAUDE.md`。

---

## 安装

```bash
# 1. 进入项目目录
cd book-to-mindmap

# 2. 安装 Python 依赖
pip install openai pymupdf ebooklib beautifulsoup4 python-docx

# 3. 设置 DeepSeek API Key
export DEEPSEEK_API_KEY="sk-..."
# 获取 Key：https://platform.deepseek.com/api_keys

# 4. （可选）自定义配置
export BOOK_MINDMAP_MODEL="deepseek-chat"   # 默认模型
export BOOK_MINDMAP_WORKERS="10"            # 并发数，默认 8
```

---

## 快速开始

```bash
# 基础用法（detailed 模式，Markdown 输出）
python main.py 深度工作.pdf

# 详细分析 + 双格式输出
python main.py 思考快与慢.epub --mode detailed --format both

# 快速概览（省 token）
python main.py 巨著.pdf --mode summary

# 学术级深度分析
python main.py 纯粹理性批判.pdf --mode comprehensive --genre philosophy

# 大书防中断
python main.py 大部头.pdf --checkpoint --workers 12
```

---

## 输出示例

```markdown
# 📚 《深度工作》思维导图

## 一、📋 全书概览
- 💡 核心主旨：深度工作是当今最有价值的稀缺技能...
- 🏷️ 主题范畴：专注力、知识工作、认知表现...
- 👥 适合读者：知识工作者、学生、创意工作者...
- ✍️ 写作风格：论证严密+案例丰富...

## 二、📂 深度工作的价值

### 🧩 第1章：深度工作是有价值的
- 🎯 TL;DR：认知高峰表现源于深度专注...
- ⭐ 核心论点
  - 机器将取代浅层工作，深度工作者受益...
  - 快速习得复杂技能需要深度工作...
  - 高质量产出 = 时间 × 专注度...
- 📖 关键概念
  - ⭐ **深度工作**：在无干扰状态下高度专注的职业活动...
  - ▫️ **注意力残留**：切换任务后遗留的前一任务思维...
    - 🔗 关联：浅层工作 · 任务切换成本...
- 📊 支撑论据
  - 🔬 经济学家 Sherwin Rosen 的"超级明星"理论...
- 📋 典型案例
  - 荣格在 Bollingen Tower 的深度工作实践...
- ⚠️ 质疑与局限
  - 并非所有职业/角色适用深度工作模式...
```

---

## 导入 XMind

1. 打开 XMind
2. 文件 → 导入 → Markdown（或 OPML）
3. 选择生成的 `.md` / `.opml` 文件
4. 自动生成多级思维导图 ✓

### 其他工具

| 工具 | 推荐格式 | 说明 |
|------|---------|------|
| **XMind** | Markdown / OPML | 直接导入，完美支持 |
| **Obsidian** | Markdown | 放入 vault + Mind Map 插件 |
| **Logseq** | Markdown | 复制大纲内容粘贴 |
| **MindNode** | OPML | 文件 → 导入 → OPML |
| **FreeMind** | OPML | 原生支持 |
| **Notion** | Markdown | 导入为 Markdown 页面 |
| **Typora** | Markdown | 预览大纲结构 |

---

## 目录结构

```
book-to-mindmap/
├── SKILL.md                          ← Claude Code Skill 定义
├── main.py                           ← 一键入口（完整 CLI）
├── scripts/
│   ├── parse_book.py                 ← 文件解析（PDF/EPUB/DOCX/TXT）
│   ├── summarize_chapters.py         ← DeepSeek API 并发逐章摘要
│   └── build_mindmap.py              ← 构建 Markdown + OPML 输出
├── references/
│   └── prompts.md                    ← Prompt 工程参考文档
└── README.md
```

---

## 费用参考（DeepSeek API）

| 书籍规模 | 模式 | 约 Token | 约费用 |
|---------|------|---------|--------|
| 薄书（<100页） | summary | ~15k | ¥0.015 |
| 薄书 | detailed | ~30k | ¥0.03 |
| 中等（100-300页） | detailed | ~80k | ¥0.08 |
| 厚书（300-500页） | detailed | ~150k | ¥0.15 |
| 厚书 | comprehensive | ~300k | ¥0.30 |

> 以上按 DeepSeek 输入 ¥1/M、输出 ¥2/M 估算。实际可能略有浮动。
> 对比：同等工作量用 Claude Sonnet 约 ¥3-8，DeepSeek 成本约为其 **1/30-1/50**。

---

## 常见问题

**Q：PDF 扫描版无法识别？**
A：先用 OCR 工具处理：`ocrmypdf input.pdf output.pdf`

**Q：章节识别错误或遗漏？**
A：在 `summaries.json` 中手动调整章节列表，再单独运行 `build_mindmap.py`

**Q：想调整输出风格或分析角度？**
A：编辑 `scripts/summarize_chapters.py` 中的 `GENRE_INSTRUCTIONS` 字典，或添加自定义流派

**Q：能直接用 Claude API 吗？**
A：可以，需修改 `summarize_chapters.py` 中的 API 调用部分。DeepSeek 是默认推荐（成本最低、速度最快）

**Q：最大能处理多大的书？**
A：理论上无上限——章节切分后每章独立处理，加上断点续跑，即使 1000 页+ 的书也能逐步完成
