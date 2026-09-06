---
title: LangChain
weight: 51
date: 2026-09-05
draft: false
---

# LangChain是什么

LangChain 解决了一个核心问题：让大语言模型能够与外部世界交互。

LangChain 1.x 把模型、工具、提示词、循环收进一套现成组件，不用自己从零写。

对比：

| 名字 | 一句话 |
| --- | --- |
| LangChain | 造 Agent 的套件。入口是 `create_agent`。 |
| LangGraph | 更底层的状态图：节点、边、循环、持久化。LangChain 的 Agent 建在它上面。 |
| LangSmith | 观测和评估。每一步模型或工具调用都能翻出来，方便查为什么跑歪。 |
| Deep Agents | 预装好的厚套件：规划、文件系统、子 Agent、记忆。底下仍是 `create_agent`。 |

## 入门示例

### 先认识 Chain：固定流程的模型调用

不是所有 LangChain 程序都要创建 Agent。若步骤已经确定，例如“根据主题生成三条学习建议”，直接把提示词、模型和输出解析器串成一条 Chain 更简单。

```python
def build_chain():
    """组装一个把主题转成学习建议的 LCEL 链。"""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是一位耐心的编程教练，请用中文简洁回答。"),
            ("human", "我正在学习 {topic}，请给我 3 条入门建议。"),
        ]
    )
    model = ChatOpenAI(model="gpt-4.1-mini", **get_openai_config())
    return prompt | model | StrOutputParser()


def main():
    answer = build_chain().invoke({"topic": "LangChain"})
    print(answer)
```

管道中的每个组件都有统一的“接收输入、产出输出”接口。上面这条链的数据依次是：

```text
{"topic": "LangChain"}
  → 填充后的聊天消息
  → 模型返回的 AIMessage
  → 普通字符串
```

这里的流程由程序预先规定，模型只负责生成回答。适合总结、改写、固定问答、信息提取等任务。

### 为 Chain 加上会话记忆

普通 Chain 的每次调用彼此独立。使用 `RunnableWithMessageHistory` 包装它后，可以按 `session_id` 保存对话历史，使后续提问能够引用前文。

```python
def build_chatbot():
    # 1. 用字典隔离不同 session_id 的对话历史。
    histories = {}

    def get_session_history(session_id):
        # 2. 同一会话始终取回同一个历史对象。
        if session_id not in histories:
            histories[session_id] = InMemoryChatMessageHistory()
        return histories[session_id]

    # 3. 将历史消息插入当前用户问题之前。
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是中文学习助手。请结合之前的对话回答。"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ]
    )
    chain = prompt | ChatOpenAI(model="gpt-4.1-mini", **get_openai_config())
    # 4. 包装链：调用前注入历史，调用后自动保存本轮问答。
    return RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="history",
    )


chatbot = build_chatbot()
# 两次调用使用相同 ID，第二次才能读到第一次的内容。
config = {"configurable": {"session_id": "learning-demo"}}

chatbot.invoke({"input": "我叫小明，正在学习 LangChain。"}, config=config)

answer = chatbot.invoke({"input": "我刚才在学习什么？"}, config=config)
print(answer.content)
```

同一个 `session_id` 会取回同一份历史：包装器先把历史填入 `history` 占位符，再调用模型，并保存本轮问答。`InMemoryChatMessageHistory` 只保存在当前 Python 进程，程序重启后会清空；生产环境应换成 Redis 或数据库等持久化存储。

### RAG：先检索资料，再回答问题

RAG（检索增强生成）让模型先从已有资料中找相关内容，再根据这些内容回答，适合文档问答。

```python
def build_vector_store():
    # 1. 将本地资料读取为 LangChain 文档。
    document = Document(page_content=document_path.read_text(encoding="utf-8"))
    # 2. 切成带重叠的片段，减少切分边界造成的语义丢失。
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=120,
        chunk_overlap=20,
    ).split_documents([document])
    # 3. 为每个片段生成向量，并建立内存向量库。
    return Chroma.from_documents(chunks, OpenAIEmbeddings(**get_openai_config()))


def answer_question(question):
    # 1. 将问题与片段比较，取最相关的两段资料。
    documents = build_vector_store().similarity_search(question, k=2)
    # 2. 把命中的片段拼成模型本轮可见的上下文。
    context = "\n\n".join(document.page_content for document in documents)
    prompt = ChatPromptTemplate.from_template(
        "只根据以下资料用中文回答；资料未提及则回答‘资料中没有说明’。"
        "\n\n资料：{context}\n\n问题：{question}"
    )
    # 3. 要求模型只依据检索结果回答，降低脱离资料作答的概率。
    chain = prompt | ChatOpenAI(model="gpt-4.1-mini", **get_openai_config()) | StrOutputParser()
    return chain.invoke({"context": context, "question": question})


print(answer_question("RAG 的常见流程是什么？"))
```

数据流是“文档 → 切分 → 向量库 → 检索相关片段 → 模型回答”。示例中的向量库只在内存中存在，并且每次提问都会重新构建；实际服务通常会预先构建并持久化向量库。

### 小结：LangChain 帮我们组合模型周边能力

到这里可以把 LangChain 理解成一套把模型应用拼起来的组件：

- Chain：把提示词、模型和输出处理串成固定流程。
- Message History：按会话保存前文，让模型能延续对话。
- RAG：从资料中检索相关片段，再交给模型回答。

LangChain 并不会让模型本身更聪明；它解决的是如何把提示词、上下文、资料、工具和执行流程可靠地组合起来。当任务还需要模型自行决定是否调用工具、以及下一步做什么时，再进一步使用 Agent。
