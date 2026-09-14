---
title: LangGraph
weight: 54
date: 2026-09-05
draft: false
---

## 条件边：根据 State 选择下一步

条件边是 LangGraph 相比普通 Chain 的第一个核心价值。下面根据已经得到的 `intent`，将请求路由到闲聊或知识问答节点：

```python
from typing import Literal


class IntentState(TypedDict):
    intent: Literal["chat", "knowledge"]
    question: str
    answer: str


def route_intent(state: IntentState) -> Literal["chat", "knowledge"]:
    return state["intent"]


def chat(state: IntentState):
    return {"answer": chat_model.invoke(state["question"]).content}


def knowledge(state: IntentState):
    return {"answer": knowledge_model.invoke(state["question"]).content}


builder = StateGraph(IntentState)
builder.add_node("chat", chat)
builder.add_node("knowledge", knowledge)
builder.add_conditional_edges(START, route_intent)
builder.add_edge("chat", END)
builder.add_edge("knowledge", END)
```

流程不再是固定直线：

```text
{"intent": "chat"}      → START → chat      → END
{"intent": "knowledge"} → START → knowledge → END
```

`add_conditional_edges` 会在运行时调用路由函数。函数读取当前 State，并返回下一个节点名；真实项目中，`intent` 可以由规则、分类模型或上一步 LLM 判断产生。

一个节点应只选一种出边机制：固定 `add_edge`，或条件 `add_conditional_edges`。同时混用同一个节点的固定边和动态边，两个路径都可能执行，流程会难以理解。

## 循环与重试：让失败回到生成节点

模型输出不能保证每次都遵守格式。若要求回答必须以“答案：”开头，可以将生成和校验拆成两个节点，并在校验失败时回到生成节点：

```python
MAX_ATTEMPTS = 3


class RetryState(TypedDict, total=False):
    question: str
    answer: str
    attempts: int
    accepted: bool


def generate(state: RetryState):
    response = model.invoke(f"只以‘答案：’开头回答：{state['question']}")
    return {
        "answer": response.content,
        "attempts": state.get("attempts", 0) + 1,
    }


def validate(state: RetryState):
    return {"accepted": state["answer"].startswith("答案：")}


def route_after_validation(state: RetryState):
    if state["accepted"] or state["attempts"] >= MAX_ATTEMPTS:
        return END
    return "generate"


builder.add_edge(START, "generate")
builder.add_edge("generate", "validate")
builder.add_conditional_edges("validate", route_after_validation)
```

```text
START → generate → validate ── 格式正确 / 已达 3 次 ──→ END
                       ↑
                       └──────────── 格式错误 ────────────┘
```

循环必须有明确的终止条件。本例同时检查“格式是否合格”和“尝试次数是否达到上限”；只检查格式会有无限循环的风险。实际项目还可以设置 LangGraph 的 `recursion_limit` 作为额外保险，但业务逻辑本身仍应主动定义退出条件。

## State reducer：消息为什么能累加

默认情况下，节点更新同一个 State 字段时，后写入的值会覆盖旧值。这对 `answer`、`status` 等单值字段很自然，但对聊天消息列表并不合适：我们希望保留历史，再追加新消息。

LangGraph 用 reducer 定义一个字段如何合并更新。消息状态通常使用内置的 `add_messages`：

```python
from typing import TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated


class MessageState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def answer(state: MessageState):
    response = model.invoke(state["messages"])
    return {"messages": [AIMessage(content=response.content)]}


def summarize(state: MessageState):
    response = model.invoke(state["messages"])
    return {"messages": [AIMessage(content=response.content)]}
```

假设输入是：

```text
[HumanMessage("介绍一下 LangGraph")]
```

两个节点运行后，默认覆盖和 reducer 累加的区别如下：

| 更新策略 | 最终 messages |
| --- | --- |
| 默认覆盖 | 只剩最后一个节点返回的消息。 |
| `add_messages` | 用户消息 + `answer` 的 AI 消息 + `summarize` 的 AI 消息。 |

`add_messages` 不只是列表拼接：它会依据消息 ID 正确处理消息的新增和更新，因此是聊天 Agent 状态的标准选择。
