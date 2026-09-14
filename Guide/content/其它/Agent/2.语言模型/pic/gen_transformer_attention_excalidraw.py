import json
import zlib
from pathlib import Path


OUT = Path(__file__).with_name("Transformer自注意力.excalidraw.md")


def seed(name):
    return zlib.crc32(name.encode("utf-8")) % 1_000_000_000


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
        "seed": seed(el_id),
        "version": 1,
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }


def text_metrics(content, font_size):
    lines = content.split("\n")
    width = max(len(line) * font_size * 0.9 for line in lines)
    height = len(lines) * font_size * 1.25
    return max(width, 80), height


def text(el_id, content, cx, cy, font_size=18, color="#374151"):
    width, height = text_metrics(content, font_size)
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
    return [
        base(f"{el_id}_box", "rectangle", x, y, width, height, stroke=stroke, bg=bg),
        text(f"{el_id}_text", label, x + width / 2, y + height / 2, font_size=font_size),
    ]


def ellipse(el_id, label, x, y, width, height, stroke, bg, font_size=18):
    shape = base(f"{el_id}_ellipse", "ellipse", x, y, width, height, stroke=stroke, bg=bg)
    shape["roundness"] = None
    return [shape, text(f"{el_id}_text", label, x + width / 2, y + height / 2, font_size=font_size)]


def arrow(el_id, points, stroke="#3b82f6", dashed=False):
    x0, y0 = points[0]
    rel = [[x - x0, y - y0] for x, y in points]
    xs = [p[0] for p in rel]
    ys = [p[1] for p in rel]
    el = base(el_id, "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys), stroke=stroke)
    el.update(
        {
            "points": rel,
            "lastCommittedPoint": None,
            "startBinding": None,
            "endBinding": None,
            "startArrowhead": None,
            "endArrowhead": "arrow",
        }
    )
    if dashed:
        el["strokeStyle"] = "dashed"
    return el


def build_elements():
    elements = []
    elements.append(text("title", "Transformer 自注意力：让词直接互相关注", 600, 48, 26, "#1e40af"))

    tokens = [
        ("tok_wo", "我", 170, "#a5d8ff", "#1e40af"),
        ("tok_mai", "买", 300, "#a5d8ff", "#1e40af"),
        ("tok_le", "了", 430, "#a5d8ff", "#1e40af"),
        ("tok_apple", "苹果", 560, "#fff3bf", "#f59e0b"),
        ("tok_15", "15", 690, "#a5d8ff", "#1e40af"),
        ("tok_phone", "手机", 820, "#b2f2bb", "#15803d"),
    ]
    elements.append(text("sentence_label", "句子：我 买 了 苹果 15 手机", 495, 105, 18, "#374151"))
    for el_id, label, x, bg, stroke in tokens:
        elements.extend(box(el_id, label, x, 135, 90, 58, stroke, bg, 20))

    elements.extend(
        box(
            "query",
            "苹果的 Query\n我在找什么？\n科技产品相关信息",
            120,
            285,
            260,
            120,
            "#f59e0b",
            "#fff3bf",
            18,
        )
    )
    elements.extend(
        box(
            "key",
            "手机的 Key\n我是什么？\n电子产品",
            815,
            285,
            240,
            120,
            "#15803d",
            "#b2f2bb",
            18,
        )
    )
    elements.extend(
        ellipse(
            "score",
            "匹配度高\nAttention Score",
            475,
            300,
            250,
            110,
            "#3b82f6",
            "#a5d8ff",
            18,
        )
    )
    elements.extend(
        box(
            "value",
            "手机的 Value\n真实语义信息\n『科技产品』",
            820,
            505,
            245,
            120,
            "#0f766e",
            "#c3fae8",
            18,
        )
    )
    elements.extend(
        box(
            "result",
            "融合后\n苹果不只是水果\n也获得『科技品牌』语义",
            360,
            530,
            390,
            115,
            "#7e22ce",
            "#d0bfff",
            18,
        )
    )

    elements.append(arrow("apple_to_query", [(605, 193), (250, 285)], "#f59e0b"))
    elements.append(arrow("phone_to_key", [(865, 193), (935, 285)], "#15803d"))
    elements.append(arrow("query_to_score", [(380, 345), (475, 355)], "#3b82f6"))
    elements.append(arrow("key_to_score", [(815, 345), (725, 355)], "#3b82f6"))
    elements.append(arrow("score_to_value", [(725, 410), (840, 505)], "#0f766e"))
    elements.append(arrow("value_to_result", [(820, 565), (750, 590)], "#7e22ce"))
    elements.append(arrow("result_to_apple", [(555, 530), (605, 193)], "#7e22ce", dashed=True))

    elements.extend(
        box(
            "note",
            "核心：每个词都能直接关注其他词\n不再依赖 RNN 那条逐词传递的长链路",
            250,
            705,
            700,
            70,
            "#1e40af",
            "#a5d8ff",
            18,
        )
    )
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
