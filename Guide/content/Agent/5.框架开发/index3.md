---
title: create_agent
weight: 52
date: 2026-09-05
draft: false
---

# 用 create_agent 创建 Agent

前一节的 Chain 把流程写在代码里：提示词 → 模型 → 输出解析。它适合每一步都确定的任务。

但用户的问题并不总能提前确定处理步骤。例如用户问天气时，需要调用天气工具；用户问普通知识时，可以直接回答。这时可以使用 `create_agent`：模型根据当前消息决定直接回答还是调用工具，框架负责执行工具调用循环。

## 一个最小天气 Agent

下面的示例把模型、天气工具和系统提示组合成一个 Agent：

```python
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from langchain_learning.settings import get_openai_config


SYSTEM_PROMPT = """你是中文天气助手。
用户询问某个城市的天气时，必须调用 get_weather 工具；
其他问题请直接简洁回答。"""


@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气；city 必须是城市名称。"""
    weather_by_city = {
        "北京": "北京：晴，18°C。",
        "上海": "上海：多云，22°C。",
        "深圳": "深圳：小雨，26°C。",
    }
    return weather_by_city.get(city, f"暂未收录 {city} 的天气数据。")


def build_agent():
    # 1. 创建模型；模型负责理解问题并选择下一步。
    model = ChatOpenAI(model="gpt-4.1-mini", **get_openai_config())
    # 2. 注册工具与系统规则；Agent 负责工具调用循环。
    return create_agent(
        model=model,
        tools=[get_weather],
        system_prompt=SYSTEM_PROMPT,
    )


agent = build_agent()
result = agent.invoke(
    {"messages": [{"role": "user", "content": "上海今天天气怎么样？"}]}
)
print(result["messages"][-1].content)
```

其中 `@tool` 会把普通 Python 函数转换为模型可用的工具定义：

| 信息 | 本例来源 | 作用 |
| --- | --- | --- |
| 工具名称 | 函数名 `get_weather` | 模型在工具调用请求中使用它。 |
| 参数 schema | `city: str` | 告诉模型需要传入字符串类型的城市名。 |
| 工具说明 | 函数 docstring | 帮助模型理解何时调用该工具。 |
| 返回值 | `str` | 工具执行后的结果，会作为后续推理的上下文。 |

## Agent 内部发生了什么

调用 `agent.invoke(...)` 后，代码没有直接调用 `get_weather`。实际流程由 Agent 管理：

```text
用户：上海今天天气怎么样？
  ↓
模型根据系统提示判断：需要调用 get_weather
  ↓
生成工具调用请求：get_weather({"city": "上海"})
  ↓
Agent 执行 Python 工具，得到“上海：多云，22°C。”
  ↓
Agent 将工具结果交回模型
  ↓
模型生成最终面向用户的回答
```

`create_agent` 的关键价值就在于这段循环：开发者提供模型、工具和规则；模型负责决定下一步；框架负责执行调用、把结果写回消息列表，并在模型给出最终回答后结束。

## Agent + Memory：让 Agent 记住同一会话的前文

普通 Agent 的单次调用可以完成“模型 → 工具 → 模型”的循环，但下一次 `invoke` 默认不会自动带上前一次的消息。给 Agent 配置 checkpointer 后，框架会按会话保存状态，使后续调用可以读取历史。

```python
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver


def build_agent(checkpointer):
    model = ChatOpenAI(model="gpt-4.1-mini", **get_openai_config())
    # 历史接近 1,000 token 时，压缩早期内容并保留最近 4 条原始消息。
    memory_middleware = SummarizationMiddleware(
        model=model,
        trigger=("tokens", 1_000),
        keep=("messages", 4),
    )
    return create_agent(
        model=model,
        tools=[get_weather],
        system_prompt="你是中文天气助手，请结合当前会话的历史回答。",
        middleware=[memory_middleware],
        checkpointer=checkpointer,
    )


agent = build_agent(InMemorySaver())
session_id = "learning-demo"
# 底层字段名固定为 thread_id；此处用 session_id 表达业务上的会话概念。
config = {"configurable": {"thread_id": session_id}}

agent.invoke(
    {"messages": [{"role": "user", "content": "我叫小明，正在学习 LangChain。"}]},
    config=config,
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "我刚才叫什么名字？"}]},
    config=config,
)
print(result["messages"][-1].content)
```

两次调用使用同一个 `thread_id`，所以第二次调用会在新的用户消息之外，读到“我叫小明”这一轮的历史。流程如下：

```text
第一次调用：用户消息 → Agent → 模型回复 → 保存到 learning-demo
第二次调用：读取 learning-demo 的历史 + 新用户消息 → Agent → 模型回复 → 更新保存状态
```

`InMemorySaver` 只适合教学和本地调试：状态只存在当前 Python 进程，程序重启后就会丢失，也不能在多进程或多机器之间共享。生产环境应使用 SQLite、PostgreSQL 等数据库型 checkpointer，并使用稳定的用户或会话 ID。

### 为什么需要控制历史长度

会话越长，发送给模型的历史消息越多，会同时推高输入 token 成本，并可能超过模型的上下文窗口。常见的处理方式如下：

| 策略 | 做法 | 取舍 |
| --- | --- | --- |
| 直接裁剪 | 删除最早的消息，只保留最近几轮。 | 最便宜，但会遗忘旧信息。 |
| 摘要 | 将早期消息压缩为一段摘要。 | 语义保留更好，但会增加一次模型调用成本。 |
| 长期记忆 | 把用户偏好等事实保存到数据库，需要时检索。 | 可跨会话，但需要设计存储、检索和隐私边界。 |

示例使用 `SummarizationMiddleware`。`trigger=("tokens", 1_000)` 表示历史达到约 1,000 token 时开始压缩；`keep=("messages", 4)` 表示保留最近四条原始消息。实际阈值应根据所用模型的上下文窗口、工具调用产生的消息量和预算调整。
