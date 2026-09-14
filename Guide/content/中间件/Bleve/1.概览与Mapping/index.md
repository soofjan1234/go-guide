---
title: Bleve 概览与 Mapping
weight: 1
date: 2026-07-01
draft: false
---

# Bleve：Go 生态里的全文检索库

Bleve 是面向 Go 的全文检索与索引库：在进程内维护倒排索引，用熟悉的 `Index` / `Search` API 完成文档入库与查询。默认索引实现是 **Scorch**（段式存储 + 后台持久化与合并），适合单机或中小规模、希望少运维组件的场景；需要跨机分片、集群联邦时，一般会转向 Elasticsearch/OpenSearch 等独立搜索服务。

下文以 **bleve v2.5.5** 源码路径为参照（与 `go/pkg/mod` 中版本一致），说明一条文档从 API 到索引内部的转换过程，以及读源码时该看哪些文件。

---

## 从 API 到内部文档

当你写下：

```go
type Page struct {
    Path    string `json:"path"`
    Title   string `json:"title"`
    Content string `json:"content"`
}

index.Index("doc-1", &Page{Path: "/a/b", Content: "hello bleve"})
// 或
index.Index("doc-1", map[string]interface{}{"path": "/a/b", "content": "hello bleve"})
```

对外类型是 `bleve.Index`。打开或创建索引后：

- **单条写入**：`Index(id, data)` 先按 mapping 把 `data` 变成内部的 `document.Document`，再交给底层 `index.Index` 的 `Update`。
- **批量写入**：`Batch(b)` 把 `Batch` 里的操作交给底层 `Batch`，通常比逐条 `Index` 吞吐更好。

内部文档大致可以理解成：

```go
type Document struct {
    // 文档唯一标识
    id string `json:"id"`

    // 普通字段：mapping 展开后的各类 Field（文本/日期/geo 等）
    Fields []Field `json:"fields"`

    // 合成字段（如 _all），与 Fields 分开存放
    CompositeFields []*CompositeField

    ...
}
```

比如一篇文档是：

```json
{
  "path": "/docs/go/bleve",
  "title": "Bleve 入门",
  "content": "Bleve 是 Go 的全文检索库"
}
```

假设 mapping 里：

- `title`、`content` 是普通可检索文本字段
- 开了 `_all`，把多个字段拼成一个合成字段

那在 `document.Document` 里大概会变成：

- `Fields`：`path`、`title`、`content`
    - 每个都是独立字段，后面可按字段名精确查，比如只搜 `title:Bleve`
- `CompositeFields`：`_all`
    - 把 `title` 和 `content` 的词合起来，支持不指定字段的全文搜
    - 虽然方便，但相当于多建一套或多套倒排结构，会额外消耗 CPU 和内存

---

## Mapping：字段如何进索引

Mapping 这层可以理解成两步。

第一步是 **先定规则**，主要在 `mapping/index.go`：

- 决定这条数据走哪套 `DocumentMapping`
- 命中明确配置的字段规则，比如 `path` 走 `keyword` 分词器
- 没单独写规则的字段，再回退到默认 analyzer、默认日期解析
- `_all` 决定要不要做一个“把多个字段合起来搜”的合成字段
- 动态字段开关（`IndexDynamic` / `StoreDynamic` / `DocValuesDynamic`）决定遇到没声明过的字段时，要不要自动建索引、存原文、建 doc values

第二步是 **再造字段**，主要在 `mapping/document.go` / `mapping/field.go`：

- 把 JSON 或结构体转换成一个 `document.Document` 对象
- 把每个值变成具体的 `Field`，比如文本、日期、地理位置
- 套用字段规则，例如 `path` 用 `keyword`，整串匹配，不拆词
- 给每个字段打上选项：要不要分词、要不要存盘、要不要 doc values

## DocumentMapping

`DocumentMapping` 定义的是这类文档里每个字段怎么处理，比如：

- 字段是否建立索引
- 用哪个 analyzer 分词，默认 analyzer 通常是 `standard`
- 是否存原文（store），默认不存
- 是否建 doc values，排序和聚合常用，默认不建
- 是否参与 `_all`，默认参与

所以排错时通常是这样：

- **搜不到**：先看 mapping / analyzer 是否把字段正确建成可检索字段
- **索引太大**：先看是否多开了 store、doc values，或者动态字段收得太松
