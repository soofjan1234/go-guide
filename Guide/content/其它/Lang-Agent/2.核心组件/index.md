---
title: 核心组件
weight: 20
---

# 核心组件：模型调用、提示词与输出解析

这一节围绕一个任务展开：从商品描述中提取名称、价格和分类。调用模型负责生成结果，提示词负责说明任务，输出解析负责把结果交给业务代码。

示例采用 LangChain Python v1 生态与 Pydantic v2。

## 1. 模型调用

### 1.1 调用 OpenAI ChatModel

安装基础依赖：

```bash
pip install langchain-openai langchain-core pydantic
```

运行前通过环境变量配置 `OPENAI_API_KEY` 和 `OPENAI_MODEL`，后者填写账号可用的模型名称。

```python
import os
from langchain_openai import ChatOpenAI

# 初始化模型；密钥由 ChatOpenAI 从 OPENAI_API_KEY 读取。
model = ChatOpenAI(model=os.environ["OPENAI_MODEL"])

# 消息分别描述整体要求和本次任务。
messages = [
    ("system", "你负责提取商品信息，不要编造未提供的内容。"),
    ("human", "无线鼠标，售价 99 元，属于数码商品。"),
]
response = model.invoke(messages)
print(response.content)
```

`invoke()` 返回 `AIMessage`，不只是字符串：除了内容，还可能带有工具调用、用量等信息。

接入 OpenAI 兼容服务时可以额外配置 `base_url`，但仍需核对该服务的模型名称、参数和功能支持，不能仅凭接口地址可替换就认为能力完全相同。

### 1.2 切换到 Hugging Face 本地模型

安装额外依赖：

```bash
pip install langchain-huggingface transformers torch
```

将 `HF_MODEL_PATH` 设置为已下载的、Transformers 支持的对话模型目录，目录内需要包含权重、配置和 tokenizer，且 tokenizer 需要有可用的 chat template。

```python
from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline

# 加载本地文本生成模型；实际内存和运行速度取决于模型规模与设备。
pipeline_model = HuggingFacePipeline.from_model_id(
    model_id=os.environ["HF_MODEL_PATH"],
    task="text-generation",
    pipeline_kwargs={"max_new_tokens": 256, "do_sample": False},
)

# 包装为 ChatModel，使用模型的聊天模板处理消息。
hf_model = ChatHuggingFace(llm=pipeline_model)
response = hf_model.invoke(messages)
print(response.content)
```

这里保留消息形式的输入与 `AIMessage` 输出。若直接使用 `HuggingFacePipeline.invoke(text)`，则是文本接口，输入字符串并返回字符串。统一的 `invoke()` 名称不代表所有组件的输入输出类型相同。

## 2. 提示词模板：分离固定指令与动态输入

`PromptTemplate` 的作用很简单：把重复使用的指令写成模板，只替换每次变化的数据。

```python
from langchain_core.prompts import PromptTemplate

prompt = PromptTemplate.from_template("从以下描述提取商品信息：{text}")
text = prompt.format(text="无线鼠标，售价 99 元，属于数码商品。")
response = model.invoke(text)
```

它负责组织输入，不负责保证模型回答正确，也不会自动校验输出格式。

## 3. 输出解析：把模型回答变成业务数据

模型可能回答“这是一款售价 99 元的无线鼠标”。人能看懂，但程序需要明确的字段，才能展示、计算或写入数据库。

常见的衔接方式是：`输入参数 → Prompt → Model → Parser → 业务数据`。

这里要区分三个层次：**能解析 JSON、满足字段约束、符合真实业务事实**。前一层通过，不代表后一层一定通过。

### 3.1 JsonOutputParser：最常见的 JSON 解析

JSON 适合表达对象和列表，也容易与接口、数据库字段衔接。先要求模型输出约定的字段，再把返回文本解析成 Python 数据。

```python
from langchain_core.output_parsers import JsonOutputParser

parser = JsonOutputParser()
prompt = PromptTemplate(
    template=(
        "从商品描述提取 name、price、category 三个字段。"
        "price 用数字表示，单位为元；未提供的信息用 null，不要猜测。\n"
        "{format_instructions}\n商品描述：{text}"
    ),
    input_variables=["text"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)

# | 将上一步输出传给下一步，构成 LCEL 处理链。
chain = prompt | model | parser
result = chain.invoke({"text": "无线鼠标，售价 99 元，属于数码商品。"})
print(result)
```

期望结果如下，具体生成内容需要以实际调用为准：

```python
{"name": "无线鼠标", "price": 99, "category": "数码"}
```

当模型输出 JSON 对象时，`result` 是字典，可通过 `result["name"]` 访问字段；JSON 数组则会解析为列表。因此，业务要求对象时仍需检查顶层类型。

这段代码有两个不同职责：

- `get_format_instructions()` 生成格式提示，由我们显式放进 Prompt；解析器不会自动修改上游提示词。
- `JsonOutputParser` 解析模型已经生成的内容，不会替模型补齐正确的业务信息。

即使返回 `{"price": "不知道"}` 也可能成功解析，因为它是合法 JSON。字段缺失、类型错误、负数价格等问题，需要额外校验。

### 3.2 PydanticOutputParser：增加数据契约

需要明确字段类型与约束时，用 Pydantic 定义结构，再交给解析器校验。下面约定三个字段必须出现，但允许 `null` 表示原文没有提供的信息。

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.output_parsers import PydanticOutputParser

class ProductInfo(BaseModel):
    # 拒绝约定之外的字段。
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(max_length=50, description="商品名称，未知为 null")
    price: float | None = Field(ge=0, description="价格，单位元，未知为 null")
    category: Literal["数码", "食品", "其他"] | None = Field(
        description="商品分类，未知为 null"
    )

parser = PydanticOutputParser(pydantic_object=ProductInfo)
prompt = PromptTemplate(
    template=(
        "从商品描述提取信息；未提供的字段填 null，不要猜测。\n"
        "{format_instructions}\n商品描述：{text}"
    ),
    input_variables=["text"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
chain = prompt | model | parser
product = chain.invoke({"text": "无线鼠标，售价 99 元，属于数码商品。"})

# 返回 Pydantic 对象，可按属性访问，也可转换为字典。
print(product.name)
print(product.model_dump())
```

`description` 只是说明，真正执行约束的是类型声明、`Literal`、`max_length`、`ge` 等规则。这里只写了 `T | None`，没有设置默认值，所以允许空值但不允许省略字段。

Pydantic 默认可能进行类型转换，例如把数字字符串转换成数字；需要拒绝这种转换时，再按字段或模型配置严格模式。类型校验通过也不能证明价格真实，仍需结合原始输入和业务规则核对。

### 3.3 解析失败怎么办？

JSON 无法解析，或者 Pydantic 校验失败时，可以捕获 `OutputParserException`。下面复用上一节的 `chain`：

```python
from langchain_core.exceptions import OutputParserException

try:
    product = chain.invoke({"text": "无线鼠标，售价 99 元，属于数码商品。"})
except OutputParserException:
    # 格式或字段校验失败时，终止本次结果处理。
    print("商品信息解析失败，请重试或人工核对。")
else:
    print(product.model_dump())
```

解析器不会自动重新调用模型。需要自动纠正时，应显式实现有限次数的重试，把校验问题反馈给模型；超过次数后返回失败或转人工处理。模型超时、鉴权失败等属于另外的调用异常，需要分别处理。

### 3.4 如何选择？

| 方式 | 返回值 | 适用情况 |
|---|---|---|
| `JsonOutputParser` | Python 字典、列表等 JSON 对应数据 | 结构简单，业务侧另有字段校验 |
| `PydanticOutputParser` | Pydantic 对象 | 需要必填项、类型、枚举、范围等约束 |

上面两种都是“提示模型生成，再解析校验”。

模型支持结构化输出时，还可以使用 `model.with_structured_output(ProductInfo)`，通过供应商支持的 JSON Schema 或工具调用机制约束输出；具体策略取决于模型与集成，仍需处理失败并校验业务事实。

### 3.5 提示后解析，与生成时约束

`PydanticOutputParser` 对生成阶段施加的是“软性约束”：我们把格式说明放进 Prompt，让模型遵守，生成后再由 Python 解析并校验。模型仍可能输出多余说明或错误格式；解析器虽能处理部分 Markdown 包裹等情况，但遇到无法解析的 JSON 或不符合字段规则的结果，仍会抛出异常。因此，**生成靠提示引导，接收结果靠校验把关**，并不是校验本身也“软”。

`with_structured_output(ProductInfo)` 则把结构要求交给模型接口，并封装后续解析。它不一定转成 `tools` 参数，也不等于“硬件级约束”，需要区分实际使用的模式：

- **工具调用**：把结构定义为工具参数，让模型返回对应参数；普通工具调用不等于严格符合 Schema。如果 Tool Calling 本身启用了 strict schema，它也可以提供强 Schema 保证
- **JSON Mode**：约束 JSON 格式，但不保证字段、类型等完全符合 `ProductInfo`。
- **严格 JSON Schema 结构化输出**：在供应商和模型支持时，由服务端强制遵循受支持的 Schema；部分实现通过约束解码屏蔽不合法的候选 token，比单纯提示更可靠。

传入 Pydantic 类时，默认成功结果会被解析并校验为 `ProductInfo` 对象。不过仍需处理拒答、输出截断、Schema 不支持和调用失败等情况；结构正确也不能保证商品信息真实。
