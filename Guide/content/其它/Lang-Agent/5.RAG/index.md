---
title: RAG 基础与知识库构建
weight: 50
---

# RAG 基础与知识库构建

RAG（Retrieval-Augmented Generation，检索增强生成）是在回答前获取相关资料，将其作为上下文交给模型。它不修改模型权重，也不保证答案自动正确：检索不到、资料过时或模型误读都会影响结果。

本节用虚构商品说明搭建一个最小示例，重点讲解文本分割、嵌入与向量存储；检索、生成和评估调优放在下一篇。文档问答适合查询说明书、售后规则；实时库存应优先调用业务查询工具，不能把旧文档当成当前库存。

## 1. 两条流程

```text
建库：加载资料 → 清洗 → 切分 → Embedding → 索引存储
问答：用户问题 → 检索候选 → 可选重排序 → 组织上下文 → 生成回答与引用
```

RAG 不强制要求向量数据库，也可以检索关键词索引、SQL 或业务接口。这里采用向量检索便于说明 LangChain 的组件组合。

## 2. 知识库构建

### 2.1 加载、清洗与保留来源

LangChain 使用 `Document` 表示文本及元数据：`page_content` 是内容，`metadata` 可以保存来源、章节、版本和权限信息。

加载 PDF、网页或 Markdown 后，应处理重复段落、导航噪声和解析错误，尤其要检查表格是否丢失行列关系。来源信息在切分后也需要保留，否则无法追溯回答依据。

### 2.2 文本分割

分块太大可能混入无关内容，太小可能丢失语义。重叠可以保留边界上下文，但会增加存储和重复召回。优先尊重标题、段落等结构，再结合评测调整大小。

#### 常用分割方法

| 方法 | 如何切分 | 适用情况 |
|---|---|---|
| `CharacterTextSplitter` | 按一个指定分隔符拆开，再按长度合并 | 段落边界明确的简单文本 |
| `RecursiveCharacterTextSplitter` | 按分隔符优先级逐层拆分过长内容 | 通用文本，适合先作为基线 |
| `MarkdownTextSplitter` | 使用 Markdown 相关分隔规则递归切分 | 需要考虑 Markdown 结构的文本 |
| `MarkdownHeaderTextSplitter` | 按标题分组，将标题层级写入 metadata | 需要保留章节归属的技术文档 |
| 按 token 计数的递归分割 | 使用 tokenizer 计算块长度 | 需要对齐模型输入预算 |

递归分割使用的是文本规则，不是让模型判断语义。`MarkdownTextSplitter` 也不保证每块都携带完整标题层级；需要可检索的标题元数据时，应使用 `MarkdownHeaderTextSplitter`。

#### 参数与输入输出

- `chunk_size`：目标块大小上限，单位由长度函数决定。
- `chunk_overlap`：相邻块的目标重叠量，不保证每对块恰好重叠这么多。
- `length_function=len`：按字符计数，不是按 token 计数。
- `separators`：从较大边界向较小边界尝试，末尾 `""` 允许最终退化到字符级拆分。

`split_text(text)` 通常将字符串变成字符串列表；`split_documents(documents)` 将 `Document` 列表变成更小的 `Document` 列表，并保留原元数据。标题分割器的 `split_text()` 则直接返回带标题元数据的 `Document`，不要混淆返回类型。

安装 `langchain-core`、`langchain-text-splitters` 后，可直接运行下面的纯文本示例：

```python
from langchain_core.documents import Document
from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter

# 使用足够长的示例，便于看到分块结果。
documents = [Document(
    page_content=("M1 鼠标支持蓝牙连接。首次使用需要完成设备配对。\n\n"
                  "保修期为一年。申请保修时需要提供购买凭证。\n\n"
                  "清洁时请断开电源。不要让液体进入设备内部。"),
    metadata={"source": "mouse-m1-manual"},
)]
simple_splitter = CharacterTextSplitter(
    separator="\n\n", chunk_size=40, chunk_overlap=8,
)
splitter = RecursiveCharacterTextSplitter(
    chunk_size=40, chunk_overlap=8,
    separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    add_start_index=True,
)
chunks = splitter.split_documents(documents)
for chunk in chunks:
    print(len(chunk.page_content), chunk.page_content, chunk.metadata)
```

可以换成 `simple_splitter.split_documents(documents)` 对比。若某个段落超过 40 字又没有指定分隔符，`CharacterTextSplitter` 可能留下超长块；它不是严格每 40 字切一刀。`start_index` 用于定位块在原文中的起点。

#### Markdown：先按标题分组，再限制块长度

```python
from langchain_text_splitters import MarkdownHeaderTextSplitter

markdown = "# M1 鼠标\n\n## 连接\n支持蓝牙连接。\n\n## 保修\n保修一年。"
header_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "title"), ("##", "section")],
    strip_headers=False,
)
sections = header_splitter.split_text(markdown)
for section in sections:
    section.metadata["source"] = "mouse-m1.md"

# 复用上面的递归分割器，继续拆分过长章节。
markdown_chunks = splitter.split_documents(sections)
for chunk in markdown_chunks:
    print(chunk.metadata, chunk.page_content)
```

这种方式将“属于哪一章”存入元数据，而不只依赖块内的标题文字。递归处理每个章节时，重叠不会跨越不同章节。

#### 按 token 控制大小

安装 `tiktoken` 后，可以改变长度计量方式：

```python
token_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name="cl100k_base",
    chunk_size=128,
    chunk_overlap=20,
    separators=["\n\n", "\n", "。", " ", ""],
)
token_chunks = token_splitter.split_documents(documents)
```

这里的 128 和 20 按指定编码器的 token 计算。`cl100k_base` 只是示例，应匹配实际模型的 tokenizer；Embedding 的单次输入限制和生成模型的总上下文限制也要分别检查。

### 2.3 向量嵌入与存储

Embedding 将文本映射到向量空间，用距离或相似度检索候选。建库与查询必须使用匹配的 Embedding 模型和配置；更换模型后，通常需要重建向量索引。

#### 两个核心方法：embed_documents 与 embed_query

```python
import os
from langchain_openai import OpenAIEmbeddings

# 配置 OPENAI_API_KEY、OPENAI_EMBEDDING_MODEL 后运行，会调用服务端接口。
embeddings = OpenAIEmbeddings(model=os.environ["OPENAI_EMBEDDING_MODEL"])
document_vectors = embeddings.embed_documents([
    "M1 无线鼠标保修一年。", "K1 机械键盘保修两年。",
])
query_vector = embeddings.embed_query("M1 鼠标保修多久？")
print(len(document_vectors))  # 两段文本，对应两个向量。
print(len(query_vector))      # 向量维度，取决于模型及配置。
```

`embed_documents` 接收文本列表，返回向量列表；`embed_query` 接收一个问题，返回一个向量。一些模型对问题和文档采用不同指令或编码方式，所以接口有意区分两者。

向量不是文本的可逆编码，也不是唯一标识。维度相同不代表来自不同模型的向量可以混用。对商品编号等精确字符串，仅靠语义向量不一定够，混合检索放在下一篇讨论。

#### 本地方案：HuggingFaceEmbeddings

安装 `langchain-huggingface` 和 `sentence-transformers`，并将 `HF_EMBEDDING_PATH` 指向已下载且兼容 Sentence Transformers 的嵌入模型目录：

```python
from langchain_huggingface import HuggingFaceEmbeddings

local_embeddings = HuggingFaceEmbeddings(
    model_name=os.environ["HF_EMBEDDING_PATH"],
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)
local_vectors = local_embeddings.embed_documents(["M1 无线鼠标保修一年。"])
local_query = local_embeddings.embed_query("保修多久？")
```

本地推理由自己的设备承担计算开销；如果传入远程模型 ID，则首次加载可能下载权重。还应遵循模型卡规定的 query/document 前缀或 prompt 配置，不能只更换名称就假定效果相同。

`normalize_embeddings=True` 将向量归一化为单位长度，使余弦、点积与欧氏距离的排序关系更容易对齐；它不是通用的“提升准确率”开关，要与模型建议及索引度量匹配。

#### 向量存储负责什么？

Embedding 模型负责计算向量，向量库负责保存向量、原文、元数据及 ID，并建立检索索引。常用接口包括：

| 方法 | 用途 |
|---|---|
| `from_documents(...)` | 根据文档与 Embedding 对象初始化向量库 |
| `add_documents(...)` | 添加文档，通常内部会调用文档嵌入方法 |
| `similarity_search(query, k=...)` | 将问题嵌入后搜索，返回文档 |
| `similarity_search_with_score(...)` | 返回文档及分数，分数语义取决于具体实现 |
| `as_retriever(...)` | 包装成可接入 LCEL 的检索器 |

下面先演示 API 的具体操作，各示例按小节顺序执行。文末再将建库步骤汇总为一个函数。

```python
from langchain_core.vectorstores import InMemoryVectorStore

# 使用前面的 chunks 和服务端 embeddings，内部自动计算文档向量。
store = InMemoryVectorStore(embedding=embeddings)
ids = store.add_documents(chunks)
hits = store.similarity_search("M1 鼠标保修多久？", k=2)
print(ids)
for hit in hits:
    print(hit.metadata, hit.page_content)
```

若切换本地模型，将 `embedding=embeddings` 改为 `embedding=local_embeddings` 并重建索引即可。通常不需要先手动调用 `embed_documents` 再 `add_documents`，否则会重复计算。

#### FAISS：保存与重新加载本地索引

内存库适合演示。FAISS 是向量索引库；LangChain 的封装将向量索引与文档、元数据关联起来，但不等同于具备完整权限和服务治理能力的数据库服务。

额外安装 `langchain-community`、`faiss-cpu` 后：

```python
from langchain_community.vectorstores import FAISS

# 复用前面的 chunks 和 embeddings，建立索引并保存。
vector_db = FAISS.from_documents(chunks, embeddings)
vector_db.save_local("./faiss_product_demo")

# 仅加载自己生成且确认未被篡改的文件；文档存储使用 pickle 反序列化。
loaded_db = FAISS.load_local(
    "./faiss_product_demo",
    embeddings,
    allow_dangerous_deserialization=True,
)
for doc, score in loaded_db.similarity_search_with_score("鼠标保修多久？", k=2):
    print(score, doc.page_content)
```

不要对陌生索引文件开启危险反序列化。加载时仍需提供与建库一致的 Embedding 配置，用于计算新问题的向量；保存索引不会自动保存服务端模型或本地模型权重。这里默认 FAISS L2 索引返回距离，越小越近，不应当作 0～1 的置信概率。

### 2.4 汇总：完整建库流程

下面使用内存向量库，避免引入额外数据库。设置 `OPENAI_API_KEY` 和 `OPENAI_EMBEDDING_MODEL`。建库和查询都会调用 Embedding 服务，内容会发送到所配置的服务端。

```bash
pip install langchain-core langchain-openai langchain-text-splitters
```

```python
import os
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


def build_vector_store() -> InMemoryVectorStore:
    """加载示例商品资料、切分并调用 Embedding 服务，返回内存向量库。"""
    # 虚构资料，用稳定来源 ID 标记，方便引用与评测。
    documents = [
        Document(
            page_content="M1 无线鼠标支持蓝牙连接，重量 60 克。保修期为一年。",
            metadata={"source": "mouse-m1-manual"},
        ),
        Document(
            page_content="K1 机械键盘采用有线连接，保修期为两年。",
            metadata={"source": "keyboard-k1-manual"},
        ),
    ]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    # 默认长度按字符计算，不是 token；这些参数只是示例起点。
    embeddings = OpenAIEmbeddings(model=os.environ["OPENAI_EMBEDDING_MODEL"])
    vector_store = InMemoryVectorStore(embedding=embeddings)
    vector_store.add_documents(chunks)
    return vector_store
```

定义函数不会自动建库，调用 `build_vector_store()` 才会请求 Embedding 服务。每次调用都会新建内存索引，演示时在程序启动阶段调用一次；实际应用通常离线建库，并在问答服务中加载已有索引。

内存索引会随进程退出丢失。本例资料很短，不会体现真实长文档的切分效果。生产系统还需要支持文档更新、旧版本失效与删除，避免答案引用过期资料。
