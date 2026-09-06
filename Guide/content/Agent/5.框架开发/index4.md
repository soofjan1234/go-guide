---
title: LangGraph
weight: 53
date: 2026-09-05
draft: false
---

# LangGraph：用状态图组织 Agent 工作流

LangChain 的 Chain 适合固定流程：提示词 → 模型 → 输出。步骤一旦确定，顺序写在代码里就够了。

但很多 Agent 任务并不是一条直线。例如，用户问题可能需要先分类；知识问题需要检索资料；答案不满足格式时需要重试；一次对话还要保留前文。此时真正需要管理的是“现在有哪些数据”和“下一步该做什么”。

LangGraph 把这件事表达为一张图：**State 保存过程数据，Node 处理数据，Edge 决定下一步。**

```text
用户问题
  ↓
路由节点 ── 闲聊 ──→ 直接回答
  │
  └─ 知识问题 ──→ 检索资料 ──→ 生成回答 ──→ 校验
                                              │
                                  不合格 ──────┘
                                               ↓
                                              结束
```

简单任务没有必要为了使用 LangGraph 而使用它。它的价值来自多步骤、分支、循环、持久状态和人工介入等场景。

## 最小概念：State、Node、Edge、START 和 END

一个最小图可以把 `{"name": "小明"}` 变成模型生成的问候语：

```python
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph


class GreetingState(TypedDict):
    name: str
    greeting: str


def greet(state: GreetingState):
    response = model.invoke(
        [
            SystemMessage(content="你是友好的中文助手，只返回一句问候语。"),
            HumanMessage(content=f"请向 {state['name']} 问好。"),
        ]
    )
    return {"greeting": response.content}


builder = StateGraph(GreetingState)
builder.add_node("greet", greet)
builder.add_edge(START, "greet")
builder.add_edge("greet", END)
graph = builder.compile()

result = graph.invoke({"name": "小明"})
print(result["greeting"])
```

运行过程如下：

```text
初始 State：{"name": "小明"}
  ↓ START
greet 节点读取 name，调用模型
  ↓ 返回 {"greeting": "你好，小明！"}
最终 State：{"name": "小明", "greeting": "你好，小明！"}
  ↓ END
```

这里的术语分别是：

| 概念 | 作用 | 本例中的含义 |
| --- | --- | --- |
| State | 节点共享的当前数据快照。 | `name` 是输入，`greeting` 是节点写入的结果。 |
| Node | 接收当前 State、执行计算并返回更新的函数。 | `greet` 调用模型生成问候语。 |
| Edge | 两个节点之间的执行路线。 | 指定 `greet` 后结束。 |
| `START` | 虚拟起点，用来指定第一个执行的节点。 | `START → greet`。 |
| `END` | 虚拟终点，表示工作流停止。 | `greet → END`。 |

Node 不需要返回完整 State，只返回自己更新的字段即可。LangGraph 会把 `{"greeting": "..."}` 合并到原有 State，因此 `name` 不会丢失。

## 固定串联：把隐式 Chain 变成显式图

“先根据主题生成大纲，再根据大纲生成总结”是一个固定的两步流程：

```text
START → make_outline → summarize → END
```

```python
class LearningState(TypedDict):
    topic: str
    outline: str
    summary: str


def make_outline(state: LearningState):
    response = model.invoke(f"为 {state['topic']} 生成入门大纲")
    return {"outline": response.content}


def summarize(state: LearningState):
    response = model.invoke(f"总结下面的大纲：\n{state['outline']}")
    return {"summary": response.content}


builder = StateGraph(LearningState)
builder.add_node("make_outline", make_outline)
builder.add_node("summarize", summarize)
builder.add_edge(START, "make_outline")
builder.add_edge("make_outline", "summarize")
builder.add_edge("summarize", END)
```

它和普通 Python 的顺序调用效果相同：

```python
outline = model.invoke("生成大纲")
summary = model.invoke(f"总结：{outline.content}")
```

因此仅有固定两步时，LangGraph 不一定更短。它的好处是把中间数据和依赖关系变成显式结构：`summarize` 清楚地依赖 `outline`。后续要加分支或重试时，不必把所有控制逻辑塞进一个大函数。
