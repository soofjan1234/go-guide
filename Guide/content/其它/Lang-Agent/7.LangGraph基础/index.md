---
title: LangGraph 基础：状态、节点、边与执行机制
weight: 70
---

# LangGraph 基础：状态、节点、边与执行机制

LangGraph 用图来组织工作流：**State 保存数据，Node 执行任务，Edge 决定接下来执行哪里。** 当流程需要条件分支、反复校验或多路并行时，可以把这些规则明确写进图中。

本文围绕同一个文本处理例子，依次学习三个核心概念、四种流程，以及图内部的执行机制。示例用普通 Python 函数模拟文本摘要，不需要模型密钥；掌握流程后，可以把摘要函数替换成前面学过的模型调用。

使用 Python 3.11 及以上版本，安装依赖：

```bash
pip install langgraph
```

下面的 Python 代码块按顺序放在同一个文件里运行；每种流程创建自己的图，共用前面定义的状态和节点。

## 1. 三个核心概念

### 1.1 State：流程共享的数据

State 是一次工作流执行中的数据载体。对于文本处理，既要保留原文，也要保存清洗结果、摘要和校验结果。

State 可以用 **TypedDict** 定义，也可以用 **Pydantic 的 BaseModel** 定义。先看本文后续示例使用的 TypedDict 写法：

```python
from typing import Annotated, NotRequired, TypedDict
from operator import add
from langgraph.graph import END, START, StateGraph


class TextState(TypedDict):
    """保存文本处理的输入、中间结果和最终输出。"""

    raw_text: str
    cleaned_text: NotRequired[str]
    summary: NotRequired[str]
    keywords: NotRequired[list[str]]
    quality_ok: NotRequired[bool]
    attempts: NotRequired[int]
    final_text: NotRequired[str]
    # 多个节点可以追加记录，合并时使用列表拼接。
    records: Annotated[list[str], add]
```

`TypedDict` 描述字典字段的类型，运行时依然按 `state["raw_text"]` 访问。它不会自动完成运行时参数校验，也不会给字段填入默认值。`NotRequired` 表示该键可以暂时不存在，因此初始输入不必提前包含摘要等结果。

**节点通常只返回发生变化的字段，不需要返回整个 State。** 没有返回的字段继续保留。

#### 另一种写法：Pydantic

如果需要默认值和运行时数据校验，可以使用 Pydantic。下面用同一组字段定义另一种状态类型：

```python
from pydantic import BaseModel, Field


class TextModelState(BaseModel):
    """用 Pydantic 定义文本处理状态及其默认值。"""

    raw_text: str
    cleaned_text: str = ""
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    quality_ok: bool = False
    attempts: int = Field(default=0, ge=0)
    final_text: str = ""
    # 每个实例创建独立列表，状态更新时仍使用列表拼接规则。
    records: Annotated[list[str], add] = Field(default_factory=list)


def clean_model_node(state: TextModelState) -> dict:
    """通过属性读取 Pydantic 状态，返回局部更新字典。"""
    cleaned = " ".join(state.raw_text.split())
    return {"cleaned_text": cleaned, "records": ["清洗完成"]}
```

构图时使用 `StateGraph(TextModelState)`，节点参数也使用对应的模型类型。上面的定义仅用于对比；后续四种流程继续使用 `TextState`。

| 对比项 | TypedDict | Pydantic BaseModel |
| --- | --- | --- |
| 节点内读取字段 | `state["raw_text"]` | `state.raw_text` |
| 类型检查 | 主要用于静态类型检查，不自动校验运行时数据 | 构造模型时按字段类型与约束校验数据 |
| 默认值 | 在初始输入中提供，或读取时用 `get()` 兜底 | 在模型字段中声明 |
| 节点返回值 | 返回局部更新字典 | 同样可以返回局部更新字典 |

例如 `ge=0` 表示 `attempts` 不能小于零。Pydantic 的校验发生在模型构造等校验边界，不能据此认为每个节点返回的更新都已被立即校验；业务结果是否正确仍需单独检查。

#### 状态如何合并：Reducer

Reducer 是某个字段的更新规则，决定“旧值”和“新返回值”如何组合。

| 字段定义 | 合并方式 | 示例 |
| --- | --- | --- |
| `summary: NotRequired[str]` | 未声明 Reducer，默认用新值覆盖旧值 | 旧摘要被新摘要替换 |
| `records: Annotated[list[str], add]` | 使用 `operator.add` 拼接列表 | `["清洗完成"]` 加上 `["摘要完成"]` |

例如已有 `records = ["清洗完成"]`，节点只需返回 `{"records": ["摘要完成"]}`，合并后就得到两条记录。不要返回旧列表再加新记录，否则旧内容会被重复拼接。

同一轮多个节点同时写一个字段时，默认覆盖规则不能用来决定谁胜出，通常会触发并发更新错误。需要让它们写不同字段，或者为共享字段定义合适的 Reducer。**Reducer 负责合并数据，不负责安排节点先后顺序。**

### 1.2 Node：执行一个处理步骤

节点接收当前状态，执行逻辑，再返回状态更新。下面先定义清洗和摘要两个节点：

```python
# 教学示例以字符数判断摘要长度，最多允许 12 个字符。
SUMMARY_LIMIT = 12


def clean_node(state: TextState) -> dict:
    """去掉原文首尾空白，合并连续空白字符。"""
    cleaned = " ".join(state["raw_text"].split())
    return {"cleaned_text": cleaned, "records": ["清洗完成"]}


def summarize_node(state: TextState) -> dict:
    """模拟生成摘要，第一次保留原文，重试时截短以演示循环。"""
    # 1. 记录本次生成是第几次尝试。
    attempt = state.get("attempts", 0) + 1
    text = state["cleaned_text"]
    # 2. 用确定性结果演示质量检查和重试，不代表真实摘要算法。
    summary = text if attempt == 1 else text[:SUMMARY_LIMIT]
    return {
        "summary": summary,
        "attempts": attempt,
        "records": [f"摘要生成第 {attempt} 次"],
    }
```

清洗节点只返回 `cleaned_text` 和 `records`，原文不会消失。摘要节点再从更新后的状态读取清洗结果。

节点可以调用模型、检索数据库、执行工具或处理数据，不要求一定是纯函数。对于状态本身，优先返回更新字典，不要依赖原地修改 `state` 或其中的列表来传递结果。

### 1.3 Edge：决定执行路线

| 类型 | 作用 | API |
| --- | --- | --- |
| 固定边 | A 完成后执行 B | `add_edge("a", "b")` |
| 条件边 | 根据状态选择后续节点 | `add_conditional_edges(...)` |

循环不是另一套 API，而是让边回到之前的节点，并设置退出条件。

`START` 和 `END` 是入口、出口标记，不需要自己编写对应函数。注册一个节点不会让它自动执行，必须通过入口和边把它接入流程。

## 2. 如何实现不同流程

### 2.1 顺序：清洗后生成摘要

```text
START → clean → summarize → END
```

```python
# 先创建构图对象，再注册节点与执行路线。
linear_builder = StateGraph(TextState)
linear_builder.add_node("clean", clean_node)
linear_builder.add_node("summarize", summarize_node)
linear_builder.add_edge(START, "clean")
linear_builder.add_edge("clean", "summarize")
linear_builder.add_edge("summarize", END)
linear_graph = linear_builder.compile()

initial_state = {
    "raw_text": "  LangGraph 支持状态管理、条件分支和并行执行。  ",
    "records": [],
}
linear_result = linear_graph.invoke(initial_state)
print(linear_result["summary"])
# LangGraph 支持状态管理、条件分支和并行执行。
```

`StateGraph(TextState)` 绑定状态结构，`add_node()` 注册函数，边指定执行顺序。`compile()` 得到可以执行的图，`invoke()` 传入初始状态并返回最终状态。

### 2.2 分支：合格输出，不合格兜底

先增加质量检查和两种输出节点：

```python
def check_node(state: TextState) -> dict:
    """只检查摘要非空且长度合格，不判断内容质量。"""
    ok = 0 < len(state["summary"]) <= SUMMARY_LIMIT
    return {"quality_ok": ok, "records": [f"长度检查：{ok}"]}


def output_node(state: TextState) -> dict:
    """将合格摘要写入最终结果。"""
    return {"final_text": state["summary"]}


def fallback_node(state: TextState) -> dict:
    """在无法生成合格摘要时返回明确的失败结果。"""
    return {"final_text": "摘要未通过长度检查，请检查输入或调整生成方式。"}


def route_quality(state: TextState) -> str:
    """根据检查结果选择输出或兜底路线。"""
    return "pass" if state["quality_ok"] else "fail"


branch_builder = StateGraph(TextState)
branch_builder.add_node("clean", clean_node)
branch_builder.add_node("summarize", summarize_node)
branch_builder.add_node("check", check_node)
branch_builder.add_node("output", output_node)
branch_builder.add_node("fallback", fallback_node)
branch_builder.add_edge(START, "clean")
branch_builder.add_edge("clean", "summarize")
branch_builder.add_edge("summarize", "check")
branch_builder.add_conditional_edges(
    "check", route_quality, {"pass": "output", "fail": "fallback"}
)
branch_builder.add_edge("output", END)
branch_builder.add_edge("fallback", END)
branch_graph = branch_builder.compile()

print(branch_graph.invoke(initial_state)["final_text"])
# 摘要未通过长度检查，请检查输入或调整生成方式。
```

路由函数返回路线标识，映射表把标识对应到节点。这里的输入太长，所以走 `fallback`；把原文换成“简短文本”，就会走 `output`。

不要同时给 `check` 添加一条通向 `output` 的固定边来表示“默认分支”。固定边仍会触发，可能导致输出和兜底都执行。互斥分支统一由条件边选择。

### 2.3 循环：不合格时有限重试

继续使用前面的节点，只修改检查后的路由：

```text
clean → summarize → check
          ↑           ├→ 合格 → output → END
          └───────────┤  不合格且还有次数
                      └→ 不合格且次数耗尽 → fallback → END
```

```python
# 包含首次生成在内，最多尝试两次，即最多重试一次。
MAX_ATTEMPTS = 2


def route_retry(state: TextState) -> str:
    """优先输出合格结果，否则在次数上限内重试。"""
    if state["quality_ok"]:
        return "pass"
    if state["attempts"] < MAX_ATTEMPTS:
        return "retry"
    return "fail"


loop_builder = StateGraph(TextState)
loop_builder.add_node("clean", clean_node)
loop_builder.add_node("summarize", summarize_node)
loop_builder.add_node("check", check_node)
loop_builder.add_node("output", output_node)
loop_builder.add_node("fallback", fallback_node)
loop_builder.add_edge(START, "clean")
loop_builder.add_edge("clean", "summarize")
loop_builder.add_edge("summarize", "check")
loop_builder.add_conditional_edges(
    "check", route_retry,
    {"pass": "output", "retry": "summarize", "fail": "fallback"},
)
loop_builder.add_edge("output", END)
loop_builder.add_edge("fallback", END)
loop_graph = loop_builder.compile()

loop_result = loop_graph.invoke(initial_state, config={"recursion_limit": 20})
print(loop_result["attempts"], loop_result["quality_ok"])
# 2 True
```

本例第二次会截短文本，因此通过长度检查。真实场景应把失败原因传入下一次生成，不能假定重新调用模型就一定改善结果。长度合格也不代表摘要准确、完整。

业务中的 `MAX_ATTEMPTS` 控制生成次数；`recursion_limit` 是执行的超步骤上限，超过时会抛出 `GraphRecursionError`。它是防止流程失控的保护措施，不能代替业务退出条件，也不表示模型调用次数。

### 2.4 并行与汇合：同时生成摘要和提取关键词

摘要和关键词都只依赖清洗后的文本，可以一起执行：

```text
               ┌→ summarize ─┐
START → clean ─┤             ├→ combine → END
               └→ keywords ──┘
```

```python
def keywords_node(state: TextState) -> dict:
    """从预设词表匹配关键词，模拟一条独立的文本分析分支。"""
    candidates = ["LangGraph", "状态", "分支", "并行"]
    words = [word for word in candidates if word in state["cleaned_text"]]
    return {"keywords": words, "records": ["关键词提取完成"]}


def combine_node(state: TextState) -> dict:
    """读取两条分支的结果并汇总。"""
    result = f"摘要：{state['summary']}；关键词：{'、'.join(state['keywords'])}"
    return {"final_text": result}


parallel_builder = StateGraph(TextState)
parallel_builder.add_node("clean", clean_node)
parallel_builder.add_node("summarize", summarize_node)
parallel_builder.add_node("keywords", keywords_node)
parallel_builder.add_node("combine", combine_node)
parallel_builder.add_edge(START, "clean")
# 同一个节点连接两个后继，形成并行分叉。
parallel_builder.add_edge("clean", "summarize")
parallel_builder.add_edge("clean", "keywords")
# 用列表明确声明：等两个前驱都完成，再执行汇总。
parallel_builder.add_edge(["summarize", "keywords"], "combine")
parallel_builder.add_edge("combine", END)
parallel_graph = parallel_builder.compile()

parallel_result = parallel_graph.invoke(initial_state)
print(parallel_result["final_text"])
print(parallel_result["records"])
```

两条分支分别写 `summary` 和 `keywords`，不会争抢同一个结果字段；它们都写 `records`，因此使用前面定义的列表拼接 Reducer。不要把这些记录的列表顺序当成真实完成时间顺序。

图按配置的边调度，不会分析函数代码并自动推断业务依赖。如果关键词节点需要读取本次新生成的摘要，就应连成 `summarize → keywords`，而不能放在同一轮并行。

## 3. 工作流内部怎么运行

### 3.1 compile 与 invoke 的区别

- **构图**：声明状态、注册节点、连接边，相当于描述执行规则。
- **`compile()`**：检查部分图结构约束，生成可执行图；不会运行摘要节点，也不会证明业务逻辑正确。
- **`invoke()`**：带着输入真正执行，更新状态，直到流程结束后返回结果。

在这些未配置跨调用状态保存的示例中，每次 `invoke(initial_state)` 都重新开始一次执行。上一个图的 `attempts` 不会自动带入下一个图。

### 3.2 Super-step：按轮次推进执行

LangGraph 的运行时采用类似 Pregel 的执行方式。**一个超步骤（Super-step）可以理解为一轮节点执行：同一轮可以执行一个节点，也可以执行多个并行节点。**

每轮大致分成三个阶段：

1. **选择节点**：依据上一轮的更新及图中连线，确定本轮要运行的节点。
2. **执行节点**：节点读取当前可见状态，执行逻辑，提交更新。
3. **应用更新**：本轮任务完成后，按各字段的 Reducer 合并更新，供后续轮次读取。

关键点是：**同一轮节点写入的更新，不会立刻被同一轮的其他节点读到。** 即使摘要先完成，正在并行执行的关键词节点也不能因此读取到本轮的新摘要。

以前面的并行图为例，只统计业务节点的执行轮次，不把入口处理单独算入下表：

| 业务轮次 | 本轮执行节点 | 本轮读取的关键数据 | 轮末新增或更新的数据 |
| --- | --- | --- | --- |
| 第 1 轮 | `clean` | `raw_text` | `cleaned_text`、清洗记录 |
| 第 2 轮 | `summarize`、`keywords` | 同一份 `cleaned_text` | `summary`、`attempts`、`keywords`、两条记录 |
| 第 3 轮 | `combine` | 已合并的摘要和关键词 | `final_text` |

因此 `combine` 能读到两条分支的结果：汇合边约束了执行时机，轮末更新机制让结果在下一轮可见。两者共同保证流程按预期推进。

循环图则会再次激活之前的节点。节点名虽然相同，但它在新一轮读取的是更新后的状态，例如 `attempts` 已经增加，因此可以判断是否继续。

### 3.3 观察每个节点返回了什么

使用 `stream_mode="updates"` 查看各节点提交的更新：

```python
for update in parallel_graph.stream(initial_state, stream_mode="updates"):
    print(update)
```

输出依次包含清洗更新、两条并行分支的更新、汇总更新；并行分支的事件先后顺序不应作为程序判断依据。这里看到的是各节点的局部更新，不是每次都输出完整 State。

图没有待执行节点、也没有待传递的消息后结束。`END` 标记一条路线走到了出口；如果还有其他并行分支在执行，不能把一条边连到 `END` 理解成强制取消所有任务。

到这里可以把整个机制串起来：**节点读取状态并返回更新，Reducer 合并字段，边确定后续路线，运行时按超步骤推进，直到没有后续任务。**
