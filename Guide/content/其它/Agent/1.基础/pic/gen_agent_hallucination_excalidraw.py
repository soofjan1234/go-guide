import json
from pathlib import Path


OUT = Path(__file__).with_name("Agent为什么会产生幻觉.excalidraw.md")


def base(el_id, el_type, x, y, width, height, stroke="#1e40af", bg="transparent"):
    return {
        "id": el_id,
        "type": el_type,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "roundness": {"type": 3},
        "seed": abs(hash(el_id)) % 1_000_000_000,
        "version": 1,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }


def text_width(text, font_size):
    max_line = max(text.split("\n"), key=len)
    return max(len(max_line) * font_size * 0.9, 80)


def text_height(text, font_size):
    return len(text.split("\n")) * font_size * 1.25


def text(el_id, content, cx, cy, font_size=18, color="#374151"):
    width = text_width(content, font_size)
    height = text_height(content, font_size)
    el = base(el_id, "text", cx - width / 2, cy - height / 2, width, height, stroke=color)
    el.update(
        {
            "text": content,
            "fontSize": font_size,
            "fontFamily": 5,
            "textAlign": "center",
            "verticalAlign": "middle",
            "containerId": None,
            "originalText": content,
            "autoResize": True,
            "lineHeight": 1.25,
        }
    )
    return el


def box(el_id, label, x, y, width, height, stroke, bg, font_size=18):
    cx = x + width / 2
    cy = y + height / 2
    return [
        base(f"{el_id}_box", "rectangle", x, y, width, height, stroke=stroke, bg=bg),
        text(f"{el_id}_text", label, cx, cy, font_size=font_size, color="#374151"),
    ]


def arrow(el_id, x1, y1, x2, y2, stroke="#3b82f6"):
    el = base(el_id, "arrow", x1, y1, x2 - x1, y2 - y1, stroke=stroke)
    el.update(
        {
            "points": [[0, 0], [x2 - x1, y2 - y1]],
            "lastCommittedPoint": None,
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": None,
            "endArrowhead": "arrow",
        }
    )
    return el


def build_elements():
    elements = []
    elements.append(text("title", "Agent 为什么会产生幻觉", 600, 60, font_size=28, color="#1e40af"))

    elements.extend(
        box(
            "center",
            "Agent 幻觉\n不是单点故障\n而是链路问题",
            450,
            305,
            300,
            130,
            stroke="#f59e0b",
            bg="#fff3bf",
            font_size=20,
        )
    )

    nodes = [
        (
            "llm",
            "LLM 底层限制\n概率生成\n不等于事实验证",
            100,
            150,
            "#1e40af",
            "#a5d8ff",
            (450, 345),
            (310, 210),
        ),
        (
            "tool",
            "工具使用偏差\n参数幻觉\n错误返回值误读",
            800,
            150,
            "#b45309",
            "#ffd8a8",
            (750, 345),
            (800, 210),
        ),
        (
            "memory",
            "记忆偏差\nRAG 脏数据\n上下文过载",
            90,
            500,
            "#0f766e",
            "#c3fae8",
            (450, 395),
            (310, 560),
        ),
        (
            "plan",
            "多步规划偏差\n早期误差\n沿链路放大",
            450,
            585,
            "#7e22ce",
            "#d0bfff",
            (600, 435),
            (600, 585),
        ),
        (
            "prompt",
            "谄媚与提示词敏感\n迎合错误前提\n被约束逼出答案",
            800,
            500,
            "#be123c",
            "#ffc9c9",
            (750, 395),
            (800, 560),
        ),
    ]

    for node_id, label, x, y, stroke, bg, start, end in nodes:
        elements.extend(box(node_id, label, x, y, 310, 120, stroke=stroke, bg=bg))
        elements.append(arrow(f"arrow_{node_id}", start[0], start[1], end[0], end[1]))

    elements.extend(
        box(
            "bottom_note",
            "治理思路：让模型行动，也要给它校验、护栏和权限边界",
            300,
            735,
            600,
            60,
            stroke="#15803d",
            bg="#b2f2bb",
            font_size=18,
        )
    )
    elements.append(arrow("arrow_note", 600, 585, 600, 735, stroke="#15803d"))
    return elements


def main():
    data = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://github.com/zsviczian/obsidian-excalidraw-plugin",
        "elements": build_elements(),
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    content = """---
excalidraw-plugin: parsed
tags: [excalidraw]
---
==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠== You can decompress Drawing data with the command palette: 'Decompress current Excalidraw file'. For more info check in plugin settings under 'Saving'

# Excalidraw Data

## Text Elements
%%
## Drawing
```json
"""
    content += json.dumps(data, ensure_ascii=False, indent=2)
    content += """
```
%%
"""
    OUT.write_text(content, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
