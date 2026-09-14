---
title: 记忆与工具调用
weight: 30
---

# 记忆与工具调用

上一节解决了模型输入与输出的组织问题。这一节让助手能够连续理解对话，并通过工具查询商品信息。

**记忆决定本次能参考哪些上下文，工具提供模型之外的数据或操作能力，Agent 负责组织模型与工具之间的循环。** 示例采用 LangChain Python v1。

## 1. 记忆：保存历史，再把需要的信息交给模型

假设用户先问“查询无线鼠标”，接着问“它还有库存吗？”。第二次调用需要包含前面的上下文，模型才知道“它”指什么。

这不是修改模型权重，而是应用保存历史，在下一次调用时重新提供相关内容。某些模型服务提供会话接口，也是在服务端维护上下文，不意味着模型权重记住了这次对话。

### 1.1 存储历史与选择上下文是两件事

- **存储层**：保存消息与状态，供后续读取、恢复或审计。
- **上下文选择**：决定本次请求传入哪些历史，可以是全部消息、最近消息或摘要。

因此，“只给模型看最近几轮”不一定要删除数据库中的完整记录；“给模型看摘要”也不意味着系统没有保存原文。

| 策略 | 本次提供的上下文 | 主要代价 |
|---|---|---|
| 全量历史 | 所有历史消息 | 输入不断增长，增加费用与延迟，可能超出上下文窗口 |
| 窗口裁剪 | 最近一部分消息 | 可能遗漏早期的重要信息 |
| 摘要压缩 | 历史摘要，可搭配最近消息 | 需要生成摘要，且可能丢失细节或引入错误 |

窗口应结合 token 预算控制，不能只数轮次：一轮可能很长；有工具调用时，一轮也不只有两条消息。裁剪时要保持工具调用消息与对应结果完整，避免留下无法匹配的 `ToolMessage`。

摘要通常在历史达到阈值后更新，并保留近期原文。若每轮都将全部历史重新送给摘要模型，摘要步骤的输入仍会不断增长，不能认为整个系统的 token 消耗已经固定。

### 1.2 LangChain v1 的短期记忆

`create_agent` 将对话消息放在 Agent 状态的 `messages` 中。配置 `checkpointer` 后，可以保存执行过程中的状态，再用同一个 `thread_id` 延续会话。

```python
import os
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

# 运行前配置 OPENAI_API_KEY 和账号可用的 OPENAI_MODEL。
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])
agent = create_agent(
    model=model,
    tools=[],
    checkpointer=InMemorySaver(),
)

# thread_id 标识一段会话；同一用户可以拥有多段独立会话。
config = {"configurable": {"thread_id": "conversation-001"}}
agent.invoke({"messages": [{"role": "user", "content": "我正在看无线鼠标。"}]}, config)
result = agent.invoke(
    {"messages": [{"role": "user", "content": "我刚才在看什么商品？"}]},
    config,
)
print(result["messages"][-1].content)
```

连续调用时只提交本轮新增消息，由框架恢复并合并历史，避免重复提交已有消息。同一个 `InMemorySaver` 实例必须被复用；每轮重新创建会丢失此前内存状态。

`InMemorySaver` 适合演示，进程结束后状态消失。跨进程恢复需要数据库支持的 checkpointer，例如 PostgreSQL。`thread_id` 只是状态索引，不是鉴权机制，服务端还需要验证当前用户是否有权访问该会话。

### 1.3 短期记忆与长期记忆

短期记忆服务于一段会话；长期记忆保存跨会话仍有用的信息，例如用户偏好。LangGraph 的 checkpointer 用于线程状态，Store 用于跨线程的数据存取。

长期记忆并不是把所有历史无限追加到 Prompt：应用需要决定哪些信息值得保存、何时检索，以及哪些内容应该更新或删除。

## 2. 工具：模型提出调用请求，程序执行函数

查询库存需要访问业务数据。仅在 Prompt 中告诉模型“你能查库存”，不会让它自动获得数据库连接或执行代码的能力。

完整过程是：

```text
用户提问 → 模型生成响应
              ├─ 无工具调用 → 返回回答
              └─ 有工具调用 → 程序校验参数并执行工具
                                  ↓
                           ToolMessage 返回结果
                                  ↓
                           模型继续生成响应
```

这里有三个职责：工具定义描述能力与参数；模型选择工具并生成参数；运行时执行工具，再把结果交给模型。

### 2.1 用 @tool 定义工具

```python
from langchain.tools import tool
from pydantic import BaseModel, Field

class ProductQuery(BaseModel):
    name: str = Field(min_length=1, max_length=50, description="需要查询的商品名称")

@tool(args_schema=ProductQuery)
def lookup_product(name: str) -> dict:
    """按商品名称查询价格和库存；不存在时返回 found=false。"""
    # 固定数据仅用于教学；实际项目在此调用业务服务或数据库。
    catalog = {
        "无线鼠标": {"price": 99, "stock": 12},
        "机械键盘": {"price": 299, "stock": 0},
    }
    product = catalog.get(name)
    if product is None:
        return {"found": False, "name": name}
    return {"found": True, "name": name, **product}
```

名称与 docstring 帮助模型理解工具用途；`args_schema` 定义参数结构与校验；函数体才是实际执行的业务逻辑。参数校验通过不代表商品一定存在，因此工具仍需返回明确的查询结果。

这里的 Pydantic 用来校验**工具输入参数**，上一节的 `PydanticOutputParser` 用来校验**模型输出结果**，作用位置不同。

定义完成后，把模型和工具列表交给 `create_agent`，就可以直接使用：

```python
from langchain.agents import create_agent

# 1. 复用前文的 model 和 lookup_product，创建工具调用 Agent。
tools = [lookup_product]
product_agent = create_agent(
    model=model,
    tools=tools,
    system_prompt="你是商品助手，价格与库存请通过工具查询，不要猜测。",
    debug=True,  # 打印运行过程，便于观察模型与工具的交互。
)

# 2. Agent 自动完成模型调用、工具执行和结果回传。
response = product_agent.invoke({
    "messages": [{"role": "user", "content": "无线鼠标多少钱？还有库存吗？"}]
})

# 3. 从返回状态中读取最后一条消息。
print(response["messages"][-1].content)
```

这里不需要自己写循环或构造 `ToolMessage`，`create_agent` 已封装这些步骤。`debug=True` 用于观察运行状态与消息，不代表能看到模型完整的内部思考过程。

### 2.2 bind_tools 与 create_agent 的区别

`model.bind_tools([lookup_product])` 将工具定义提供给模型。一次 `invoke()` 可能返回带 `tool_calls` 的 `AIMessage`，但绑定动作不会替你运行本地函数。

手动实现时，需要读取工具名与参数、执行函数，并构造带有对应 `tool_call_id` 的 `ToolMessage`；连同原始 `AIMessage` 再次交给模型，直到结束或达到执行限制。

`create_agent` 已封装这个循环，适合直接构建工具调用助手。不能在工具执行完成后就直接等待用户下一次输入，否则本轮缺少模型根据工具结果继续处理的步骤。

## 3. 综合案例：带记忆的商品查询助手

安装依赖：

```bash
pip install langchain langchain-openai langgraph pydantic
```

先运行前文的 import、`model` 初始化及 `lookup_product` 定义，再执行下面代码。查询数据是固定示例，不代表真实库存。

```python
# 创建带工具与短期记忆的 Agent。
shopping_agent = create_agent(
    model=model,
    tools=[lookup_product],
    checkpointer=InMemorySaver(),
    system_prompt=(
        "你是商品查询助手。价格与库存必须通过 lookup_product 查询。"
        "结合对话历史理解商品指代；无法确定商品时先询问用户。"
        "未查询到商品时明确说明，不要编造。"
    ),
)
config = {"configurable": {"thread_id": "shopping-001"}}

# 第一轮明确商品，第二轮通过历史理解“它”的指代。
for question in ["无线鼠标多少钱？", "它还有库存吗？"]:
    result = shopping_agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config,
    )
    print(result["messages"][-1].content)
```

期望第一轮查询到价格 99 元，第二轮仍查询无线鼠标并得到库存 12。实际是否按要求调用，应检查消息记录，不能只凭最终回答正确就断定工具执行成功。

```python
# 查看公开消息与工具调用记录，不代表模型完整的内部思考过程。
for message in result["messages"]:
    print(message.type, message.content)
    if getattr(message, "tool_calls", None):
        print("工具调用：", message.tool_calls)
```

可以验证三件事：同一 `thread_id` 是否保留商品上下文；消息中是否出现 `lookup_product` 调用及对应结果；换一个 `thread_id` 后是否从独立会话开始。

本例用 Prompt 要求查询工具，这是行为引导。若业务规定价格与库存必须来自查询服务，应在业务流程中强制执行或验证查询，不能把提示词当作执行保证。历史库存也可能过期，涉及实时数据时应重新查询。