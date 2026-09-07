# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This project has **two distinct output modes** for turning books into interactive knowledge maps:

1. **Python pipeline** (`main.py` → `scripts/`) — automated markdown/OPML mindmap generation via DeepSeek API
2. **Hand-crafted interactive HTML** (`output/*_交互式知识图谱.html`) — rich, multi-tab single-page knowledge graphs

The README and SKILL.md document the Python pipeline. This file focuses on the HTML creation workflow.

## HTML output: reference template

When asked to create an interactive HTML for a book, use this pattern. The canonical reference implementation is:

```
output/产业政治_交互式知识图谱.html        ← original template (1,056 lines)
output/AI产业全景图谱_交互式知识图谱.html  ← most feature-complete (1,436 lines, use as primary reference)
```

Every book HTML follows this architecture:
- **Single-file, zero external dependencies** — all CSS/JS inlined, no CDN, no frameworks
- **Dark theme default** with light theme toggle (localStorage-persisted via `data-theme` attribute)
- **CSS custom properties** (`:root` + `[data-theme="light"]`) for all colors — 2 accent colors, 4 semantic colors (red/amber/green/cyan), alpha variants for each
- **Sticky horizontal nav bar** with ~10 tabs, each switching a `.section` via vanilla JS
- **Hero section** with gradient title, animated grid background, stats row, scroll-hint bounce
- **Reusable CSS components**: `.card` / `.card-grid` / `.card-grid-2` / `.card-grid-4` / `.flow-container` + `.flow-node` / `.timeline` + `.tl-item` / `.compare-table` / `.highlight` / `.concept-web` / `.accordion` / `.app-grid` + `.app-icon-card` / `.scenario-card` / `.stat-card`
- **Scroll animations**: `IntersectionObserver` on `.fade-up` elements (threshold 0.15)
- **Responsive**: single `@media (max-width: 768px)` breakpoint collapses all grids to 1fr

## Workflow for creating a new book HTML

### Step 1: Extract the book's text content

```bash
# For text-based PDFs:
python3 -c "
import fitz
doc = fitz.open('path/to/book.pdf')
for i in range(doc.page_count):
    print(doc[i].get_text())
doc.close()
" > /tmp/book_text.txt

# For image-based/scanned PDFs (no text layer):
# Extract pages as images, then OCR with macOS Vision:
python3 -c "
import fitz, os
doc = fitz.open('path/to/book.pdf')
os.makedirs('/tmp/book_pages', exist_ok=True)
for i in range(doc.page_count):
    doc[i].get_pixmap(dpi=150).save(f'/tmp/book_pages/page_{i+1:03d}.png')
doc.close()
"
# Then OCR each page:
for f in /tmp/book_pages/page_*.png; do
  swift /tmp/ocr.swift "$f" 2>&1
done

# For EPUBs:
unzip -o "book.epub" -d /tmp/epub_extract
```

### Step 2: Read the reference HTML template

Always read `output/AI产业全景图谱_交互式知识图谱.html` first — it has the most complete component set including `.app-grid`, `.app-icon-card`, `.stat-row`, `.accordion`, `.scenario-card`, and the `📖 信息源` tab.

### Step 3: Analyze and structure the book

- Read the table of contents and enough content pages (typically 30-60 pages sampled) to understand: book structure, core thesis, key concepts, major chapter groupings, important figures/companies/events, and source references
- Design a 10-tab structure that mirrors the book's logical flow
- The last 2 tabs should always be `📖 信息源` and `🧭 逻辑链`

### Step 4: Write the HTML

Key patterns to follow exactly:

**CSS variables**: Choose 2 accent colors that fit the book's theme. Keep semantic colors consistent (red for conflict/danger, amber for economics/warning, green for positive/cooperation, cyan for technology/infrastructure). Add domain-specific color variables if needed.

**Hero stats**: 4 numbers that capture the book's essence (chapter count, key metric, time span, etc.)

**Nav bar**: No more than 11 items to avoid horizontal scroll on laptop screens. Keep labels short (2-4 characters + emoji).

**Each section**: `<div class="section-title"><span class="icon">EMOJI</span>TITLE</div>` followed by `<div class="section-subtitle">` with a 1-2 sentence description.

**Color-coded domain cards**: Use `border-left: 4px solid var(--domain-color)` or `border-top` for enterprise/ideology cards to create visual grouping.

**信息源 tab**: Must include:
- `app-icon-card` grid of key figures (16 max, each with emoji + name + nationality + one-line contribution)
- `compare-table` of core references/readings
- `concept-web` of key data sources or tools
- `highlight` box with usage guide organized by research purpose

**概念网络 (concept-web) 必须可点击**: Each `.concept-node` must have a `data-target="sectionId"` attribute mapping to the corresponding tab. Add the JS handler below to make clicks switch sections:

```js
// ==================== CONCEPT WEB NAVIGATION ====================
document.querySelectorAll('.concept-node[data-target]').forEach(node => {
  node.addEventListener('click', () => {
    const navItem = document.querySelector('.nav-item[data-section="' + node.dataset.target + '"]');
    if (navItem) { navItem.click(); }
    node.style.transition = 'all 0.15s ease'; node.style.boxShadow = '0 0 20px var(--a30)'; node.style.borderColor = 'var(--accent2)';
    setTimeout(() => { node.style.boxShadow = ''; node.style.borderColor = ''; }, 800);
  });
});
```

CSS must include glow on hover and `.core:hover` variant:
```css
.concept-node:hover { transform: scale(1.08); border-color: var(--accent); box-shadow: 0 0 12px var(--a15); }
.concept-node.core:hover { border-color: var(--accent); box-shadow: 0 0 16px var(--a2-40); }
```

### Step 5: Verify

```bash
open "output/Book_Name_交互式知识图谱.html"
```
Check: theme toggle works, all tabs switch correctly, scroll animations fire, responsive layout on narrow viewport, no visual glitches in light mode.

## Adding the 信息源 tab to existing HTMLs

When retrofitting the sources tab onto an existing HTML:

1. Add `<div class="nav-item" data-section="sources">📖 信息源</div>` before the closing `</div></nav>`
2. Add the full `<section class="section" id="sec-sources">` before `<!-- Footer -->`
3. Ensure `.app-grid`, `.app-icon-card` CSS classes exist in the `<style>` block
4. Add `.app-grid { grid-template-columns: 1fr 1fr; }` to the responsive `@media` block

## Common color palettes

| Book theme | Accent 1 | Accent 2 | Hero gradient hint |
|------------|----------|----------|---------------------|
| Politics/geopolitics | `#6366f1` (indigo) | `#a855f7` (purple) | blue→purple→amber→green |
| Technology/AI | `#6366f1` (indigo) | `#a855f7` (purple) | white→indigo→purple→cyan→amber |
| Economics/industry | `#3b82f6` (blue) | `#8b5cf6` (purple) | blue→cyan→purple |
| Chips/semiconductor | `#4da6ff` (silicon blue) | `#7c5ce7` (purple) | silicon blue→cyan→amber |

## OCR helper script

Save this to `/tmp/ocr.swift` when dealing with image-based PDFs:
```swift
import Vision, AppKit
func ocr(path: String) -> String {
    guard let nsImage = NSImage(contentsOfFile: path),
          let tiff = nsImage.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let cgImage = bitmap.cgImage else { return "ERROR" }
    let request = VNRecognizeTextRequest()
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en"]
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    try? VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
    return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}
print(CommandLine.arguments.count > 1 ? ocr(path: CommandLine.arguments[1]) : "")
```
