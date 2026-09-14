---
title: Runnable 与 LCEL
weight: 40
---

# Runnable 与 LCEL：把组件组合成流程

前面已经使用过 `prompt | model | parser`。这里的 `|` 是 LCEL（LangChain Expression Language）的组合语法，其基础是 Runnable：具有统一执行接口的组件。

模型、提示词、解析器和组合后的链都可以作为 Runnable 使用。**Runnable 约定如何调用组件，但不会保证任意两个组件的输入输出类型都能直接对接。**

## 1. 常见组件与调用方式

| 组件 | 作用 |
|---|---|
| `RunnableSequence`  | 顺序执行，前一步输出传给后一步 |
| `RunnableParallel` / `RunnableMap` | 同一输入分别交给多个分支，按键汇总结果；Map 是 Parallel 的别名 |
| `RunnableBranch` | 按条件选择第一个匹配的分支，否则使用默认分支 |
| `RunnableLambda` | 将普通函数包装成 Runnable |
| `RunnablePassthrough` | 原样传递输入；配合 `assign` 为字典补充字段 |

执行单次输入用 `invoke()`，多条输入用 `batch()`，异步调用用 `ainvoke()`，流式读取用 `stream()`。`batch()` 表示对多条输入执行，不一定对应模型供应商的离线批处理 API。

下面先使用不需要模型的代码理解数据流。安装依赖：

```bash
pip install langchain-core
```

## 2. 顺序执行：RunnableSequence

```python
from langchain_core.runnables import RunnableLambda

# 第一步清理文本，第二步将字符串转换为字典。
clean = RunnableLambda(lambda text: text.strip())
wrap = RunnableLambda(lambda text: {"product": text})
chain = clean | wrap

print(chain.invoke("  无线鼠标  "))
# {'product': '无线鼠标'}
print(chain.batch([" 鼠标 ", " 键盘 "]))
# [{'product': '鼠标'}, {'product': '键盘'}]
```

`clean | wrap` 构成 `RunnableSequence`。把模型加入流程时也是同样的规则：如果模型返回 `AIMessage`，下游需要字符串，可以用 `StrOutputParser` 转换；下游 Prompt 需要多个变量，则要组织成对应的字典。

## 3. 并行处理：RunnableParallel

```python
from langchain_core.runnables import RunnableParallel

# 两个分支收到的是同一个完整输入，不是按分支名称自动提取字段。
parallel = RunnableParallel(
    name=RunnableLambda(lambda data: data["name"]),
    total=RunnableLambda(lambda data: data["price"] * data["quantity"]),
)
print(parallel.invoke({"name": "无线鼠标", "price": 99, "quantity": 2}))
# {'name': '无线鼠标', 'total': 198}
```

分支之间没有先后依赖，适合对同一文本分别生成摘要、关键词等。不要让并行分支修改共享输入；并行也不保证更快，仍受网络、限流和任务本身影响。

## 4. 保留与补充输入：RunnablePassthrough

```python
from langchain_core.runnables import RunnablePassthrough

# 输入必须是字典；保留原字段，并计算 total。
with_total = RunnablePassthrough.assign(
    total=RunnableLambda(lambda data: data["price"] * data["quantity"])
)
print(with_total.invoke({"price": 99, "quantity": 2}))
# {'price': 99, 'quantity': 2, 'total': 198}
```

一个常见误区是写 `{"target_audience": RunnablePassthrough()}`，以为它会取出输入中的 `target_audience`。实际上它透传整个输入。要提取字段，应使用 `lambda data: data["target_audience"]`。

同一次 `assign` 中的多个计算都读取该步骤的输入，不应依赖同次计算新生成的其他字段。有依赖关系时，串联多次 `assign`。

## 5. 条件路由：RunnableBranch

```python
from langchain_core.runnables import RunnableBranch

# 从上到下匹配条件；最后一个参数是默认分支。
route = RunnableBranch(
    (lambda data: data["stock"] > 0, RunnableLambda(lambda data: "有货")),
    RunnableLambda(lambda data: "缺货"),
)
print(route.invoke({"stock": 12}))  # 有货
print(route.invoke({"stock": 0}))   # 缺货
```

分支由开发者定义的条件决定。若需要模型判断问题类型，可以先得到分类结果，再路由；这与 Agent 自主选择工具是不同的执行方式。

## 6. 加入模型：保留原输入，生成商品文案

安装 `langchain-openai`，配置 `OPENAI_API_KEY` 与可用的 `OPENAI_MODEL`，再运行下面示例。代码复用前文导入的 Runnable 类。

```python
import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
extract_prompt = PromptTemplate.from_template(
    "从以下商品说明提取两个卖点，不要补充未提供的事实：{description}"
)
write_prompt = PromptTemplate.from_template(
    "面向{audience}，根据卖点写一段简短介绍，不要夸大：{selling_points}"
)

# assign 保留 description、audience，并补充第一步生成的卖点。
marketing_chain = (
    RunnablePassthrough.assign(
        selling_points=extract_prompt | model | StrOutputParser()
    )
    | write_prompt
    | model
    | StrOutputParser()
)
answer = marketing_chain.invoke({
    "description": "无线鼠标，支持蓝牙连接，重量 60 克。",
    "audience": "经常出差的用户",
})
print(answer)
```

这条链调用模型两次：先提取卖点，再生成文案。拆成多步便于观察和替换某一步，但也增加调用成本；简单任务不必为了使用链而拆分。

## 7. 与 LangGraph 的边界

LCEL 适合表达顺序、并行、分支以及数据转换。需要显式循环、可恢复状态、人工暂停等流程控制时，可以使用 LangGraph。它们可以配合：一个 LangGraph 节点内部也可以执行 LCEL 链。

调用 `stream()` 不代表每一步都能逐 token 透传；中间若有必须等完整输入的函数，该步骤就会产生缓冲。
