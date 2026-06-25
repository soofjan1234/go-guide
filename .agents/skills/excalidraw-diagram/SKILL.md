---
name: excalidraw-diagram
description: Draw Excalidraw diagrams to local .md files (Obsidian format) using Write tool output with excalidraw-plugin parsed JSON. Triggers on "Excalidraw", "画图", "流程图", "思维导图", "可视化", "diagram", "标准Excalidraw", "standard excalidraw", "Excalidraw动画", "动画图", "animate".
---

# Excalidraw Diagram Generator（画到本地）

根据文字内容**在内存中设计图表**，并**用 Write 工具将结果写入本地 .md 文件**（Obsidian Excalidraw 格式）。

## 生成策略：强制使用 Python 脚本

为了保证图表布局的精确性（尤其是坐标计算和折线箭头）并确保生成合法的 JSON 数据，**必须使用 Python 脚本** 生成 Excalidraw 数据。

**操作要求：**
- **布局逻辑**：使用语义化的 Python 代码处理坐标计算、自动换行和对齐。
- **落盘方式**：脚本生成 JSON 后，将其嵌入到「Output Formats」模板中，并**最终由 Write 工具**写入本地 `.md` 文件。
- **脚本留存**：临时生成的绘图脚本建议放在 `scripts/` 或 `tools/` 目录下，以便后续修改维护。
- **规范遵循**：脚本输出必须严格遵守下文的 Design Rules 和 Element Template。


## 输出方式

| 方式 | 说明 |
|------|------|
| **开始画图** | 用 Write 将图表写入项目内的 .md 文件，格式见「Output Formats」。路径建议：`{当前目录}/Excalidraw/[主题].[类型].md` |

## Workflow

1. 分析内容，确定概念、关系、层级
2. 根据「Diagram Types & Selection Guide」选择图表类型
3. 在内存中「设计」布局与元素列表；必须使用脚本生成符合 Element Template 的 `elements` JSON，严禁手写以防逻辑与排版错误。
4. **用 Write 工具**将 Obsidian 格式的 .md 写入本地路径（见「Output Formats」）
5. 回复中说明保存路径、文件名，以及所用图表类型


## Output Formats（默认输出）

**默认**使用 Write 将图表写成以下 Obsidian .md 格式，保存到用户项目内的路径（如 `Article/xxx/Excalidraw/图名.md`）。

### Obsidian 格式（.md）

```markdown
---
excalidraw-plugin: parsed
tags: [excalidraw]
---
==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠== You can decompress Drawing data with the command palette: 'Decompress current Excalidraw file'. For more info check in plugin settings under 'Saving'

# Excalidraw Data

## Text Elements
%%
## Drawing
\`\`\`json
{JSON 完整数据}
\`\`\`
%%
```

**关键要点：**
- Frontmatter 必须包含 `tags: [excalidraw]`
- 警告信息必须完整
- Drawing 块：用 `%%` 包裹，代码块统一使用 `json`（完整 JSON）
- 不能使用 `excalidraw-plugin: parsed` 以外的其他 frontmatter 设置
- **文件扩展名**：`.md`


---

## Diagram Types & Selection Guide

选择合适的图表形式，以提升理解力与视觉吸引力。

| 类型 | 英文 | 使用场景 | 做法 |
|------|------|---------|------|
| **流程图** | Flowchart | 步骤说明、工作流程、任务执行顺序 | 用箭头连接各步骤，清晰表达流程走向 |
| **思维导图** | Mind Map | 概念发散、主题分类、灵感捕捉 | 以中心为核心向外发散，放射状结构 |
| **层级图** | Hierarchy | 组织结构、内容分级、系统拆解 | 自上而下或自左至右构建层级节点 |
| **关系图** | Relationship | 要素之间的影响、依赖、互动 | 图形间用连线表示关联，箭头与说明 |
| **对比图** | Comparison | 两种以上方案或观点的对照分析 | 左右两栏或表格形式，标明比较维度 |
| **时间线图** | Timeline | 事件发展、项目进度、模型演化 | 以时间为轴，标出关键时间点与事件 |
| **矩阵图** | Matrix | 双维度分类、任务优先级、定位 | 建立 X 与 Y 两个维度，坐标平面安置 |
| **自由布局** | Freeform | 内容零散、灵感记录、初步信息收集 | 无需结构限制，自由放置图块与箭头 |

## Design Rules

### Text & Format
- **所有文本元素必须使用** `fontFamily: 5`（Excalifont 手写字体）
- **文本中的双引号替换规则**：`"` 替换为 `『』`
- **文本中的圆括号替换规则**：`()` 替换为 `「」`
- **字体大小规则**（硬性下限，低于此值在正常缩放下不可读）：
  - 标题：20-28px（最小 20px）
  - 副标题：18-20px
  - 正文/标签：16-18px（最小 16px）
  - 次要注释：14px（仅限不重要的辅助说明，慎用）
  - **绝对禁止低于 14px**
- **行高**：所有文本使用 `lineHeight: 1.25`
- **文字居中估算**：独立文本元素没有自动居中，需手动计算 x 坐标：
  - 估算文字宽度：`estimatedWidth = text.length * fontSize * 0.5`（CJK 字符用 `* 1.0`）
  - 居中公式：`x = centerX - estimatedWidth / 2`
  - 示例：文字 "Hello"（5字符, fontSize 20）居中于 x=300 → `estimatedWidth = 5 * 20 * 0.5 = 50` → `x = 300 - 25 = 275`
- **容器内文本对齐（推荐）**：文本放在矩形/卡片内时，按容器中心计算，避免目测偏移：
  - `text.x = rect.x + (rect.width - text.width) / 2`
  - `text.y = rect.y + (rect.height - text.height) / 2`
- **自动换行阈值**：当单行文本估算宽度超过容器可用宽度（默认阈值 `180px`）时，必须手动插入 `\n` 分行，并按新行数重算 `text.height`（`lineHeight: 1.25`）。

### Layout & Design
- **画布范围**：建议所有元素在 0-1200 x 0-800 区域内
- **最小形状尺寸**：带文字的矩形/椭圆不小于 120x60px
- **元素间距**：最小 20-30px 间距，防止重叠
- **层次清晰**：使用不同颜色和形状区分不同层级的信息
- **图形元素**：适当使用矩形框、圆形、箭头等元素来组织信息
- **禁止 Emoji**：不要在图表文本中使用任何 Emoji 符号，如需视觉标记请使用简单图形（圆形、方形、箭头）或颜色区分
- **箭头路径规则（避免穿模）**：
  - 元素非水平/垂直对齐时，优先用折线箭头（`points` 至少 3 个点，包含一个中间拐点）。
  - 箭头应连接形状边缘附近，不要直接瞄准形状中心，避免箭头尖端被覆盖。
  - 若路径会穿过关键节点，先加拐点绕开，再保证箭头方向清晰。

### Color Palette

**文字颜色（strokeColor for text）：**

| 用途 | 色值 | 说明 |
|------|------|------|
| 标题 | `#1e40af` | 深蓝 |
| 副标题/连接线 | `#3b82f6` | 亮蓝 |
| 正文文字 | `#374151` | 深灰（白底最浅不低于 `#757575`） |
| 强调/重点 | `#f59e0b` | 金色 |

**形状填充色（backgroundColor, fillStyle: "solid"）：**

| 色值 | 语义 | 适用场景 |
|------|------|---------|
| `#a5d8ff` | 浅蓝 | 输入、数据源、主要节点 |
| `#b2f2bb` | 浅绿 | 成功、输出、已完成 |
| `#ffd8a8` | 浅橙 | 警告、待处理、外部依赖 |
| `#d0bfff` | 浅紫 | 处理中、中间件、特殊项 |
| `#ffc9c9` | 浅红 | 错误、关键、告警 |
| `#fff3bf` | 浅黄 | 备注、决策、规划 |
| `#c3fae8` | 浅青 | 存储、数据、缓存 |
| `#eebefa` | 浅粉 | 分析、指标、统计 |

**区域背景色（大矩形 + opacity: 30，用于分层图表）：**

| 色值 | 语义 |
|------|------|
| `#dbe4ff` | 前端/UI 层 |
| `#e5dbff` | 逻辑/处理层 |
| `#d3f9d8` | 数据/工具层 |

**对比度规则：**
- 白底上文字最浅不低于 `#757575`，否则不可读
- 浅色填充上用深色变体文字（如浅绿底用 `#15803d`，不用 `#22c55e`）
- 避免浅灰色文字（`#b0b0b0`、`#999`）出现在白底上
- **同色系描边规则（新增）**：
  - 尽量避免“彩色填充 + 纯黑描边”的生硬组合。
  - `strokeColor` 优先使用 `backgroundColor` 的深色同系版本。
  - 示例：`#a5d8ff`（浅蓝填充）→ `#1e40af`（深蓝描边）。

参考：[references/excalidraw-schema.md](references/excalidraw-schema.md)

## JSON Structure

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin",
  "elements": [...],
  "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```

## Element Template

Each element requires these fields (do NOT add extra fields like `frameId`, `index`, `versionNonce`, `rawText` -- they may cause issues on excalidraw.com. `boundElements` must be `null` not `[]`, `updated` must be `1` not timestamps):

```json
{
  "id": "unique-id",
  "type": "rectangle",
  "x": 100, "y": 100,
  "width": 200, "height": 50,
  "angle": 0,
  "strokeColor": "#1e1e1e",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "groupIds": [],
  "roundness": {"type": 3},
  "seed": 123456789,
  "version": 1,
  "isDeleted": false,
  "boundElements": null,
  "updated": 1,
  "link": null,
  "locked": false
}
```

`strokeStyle` values: `"solid"`（实线，默认）| `"dashed"`（虚线）| `"dotted"`（点线）。虚线适合表示可选路径、异步流、弱关联等。

Text elements add:
```json
{
  "text": "显示文本",
  "fontSize": 20,
  "fontFamily": 5,
  "textAlign": "center",
  "verticalAlign": "middle",
  "containerId": null,
  "originalText": "显示文本",
  "autoResize": true,
  "lineHeight": 1.25
}
```


See [references/excalidraw-schema.md](references/excalidraw-schema.md) for all element types.

---

## Additional Technical Requirements

### Text Elements 处理
- `## Text Elements` 部分在 Markdown 中**必须留空**，仅用 `%%` 作为分隔符
- Obsidian ExcaliDraw 插件会根据 JSON 数据**自动填充文本元素**
- 不需要手动列出所有文本内容

### 坐标与布局
- **坐标系统**：左上角为原点 (0,0)
- **推荐范围**：所有元素在 0-1200 x 0-800 像素范围内
- **元素 ID**：每个元素需要唯一的 `id`（可以是字符串，如「title」「box1」等）

### 字段规范（单一规则源）
- 统一遵循上文 `## Element Template`
- **不要出现**：`frameId`, `index`, `versionNonce`, `rawText`
- `boundElements` 必须是 `null`（不是 `[]`）
- `updated` 使用 `1`（不要写时间戳）

### appState 配置
```json
"appState": {
  "gridSize": null,
  "viewBackgroundColor": "#ffffff"
}
```

### files 字段
```json
"files": {}
```

## Common Mistakes to Avoid

- **文字偏移** — 独立 text 元素的 `x` 是左边缘，不是中心。必须用居中公式手动计算，否则文字会偏到一边
- **元素重叠** — y 坐标相近的元素容易堆叠。放置新元素前检查与周围元素是否有至少 20px 间距
- **画布留白不足** — 内容不要贴着画布边缘。在四周留 50-80px 的 padding
- **标题没有居中于图表** — 标题应居中于下方图表的整体宽度，不是固定在 x=0
- **箭头标签溢出** — 长文字标签（如 "ATP + NADPH"）会超出短箭头。保持标签简短或加大箭头长度
- **对比度不够** — 浅色文字在白底上几乎不可见。文字颜色不低于 `#757575`，有色文字用深色变体
- **字号太小** — 低于 14px 在正常缩放下不可读，正文最小 16px

## Implementation Notes

### 画到本地流程（默认）

当用户请求画图时，**将图表写成本地 .md 文件**。

#### 1. 选择图表类型
- 根据内容参考「Diagram Types & Selection Guide」选择最合适的图表形式

#### 2. 在内存中构建完整 JSON
- 按 Design Rules、Color Palette、Element Template 设计好所有元素
- 组装为完整的 `{ type, version, source, elements, appState, files }` JSON
- 能写成 Mermaid 的图可先构思结构，再转为对应 elements（箭头、矩形、文本等）
- **脚本化生成**：统一使用 Python 等脚本生成 JSON。通过语义化布局代码控制坐标，减少排版错误并简化后期维护。生成后在回复中说明脚本路径。

#### 3. 用 Write 写入 .md
- 路径：`{当前目录}/Excalidraw/[主题].[类型].md`（若项目里已存在 `excalidraw/` 或 `Excalidraw/`，优先复用现有目录大小写）
- 内容：Obsidian 格式，见「Output Formats」；`## Drawing` 下统一使用 `%%` 包裹的 `json` 完整数据

#### 4. 用户反馈
- 说明已保存的路径与文件名
- 说明所选图表类型与设计思路
- 若用户需要再在浏览器中编辑，可提示可配合 Obsidian / Excalidraw 插件打开该 .md

### 交付前检查清单（必须）
1. 文件扩展名是否为 `.md`
2. Frontmatter 是否包含且仅包含 `excalidraw-plugin: parsed` 与 `tags: [excalidraw]`
3. 警告行是否完整
4. `## Text Elements` 是否留空
5. `## Drawing` 是否为 `%%` 包裹 + `json` 代码块
6. 颜色与字号是否符合 Design Rules（正文不低于 16px）

### Example 回复（画到本地）

```
图已画到本地：

**保存路径**：`Article/sync.map/Excalidraw/sync.Map.哈希树.结构图.md`

本图采用 [层级图/结构示意图]，因为 [简短原因]。用 Obsidian 的 Excalidraw 插件或支持该格式的编辑器打开即可查看与编辑。若需要改布局或配色，可以说具体需求。
```

