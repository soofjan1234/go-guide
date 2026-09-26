---
title: "Bleve：从查询到搜索结果"
weight: 2
date: 2026-07-01
draft: false
---

# Bleve：从查询到搜索结果

写入文档时，Bleve 已把“字段 + 词”映射到文档。查询时走相反方向：**分析输入 → 查倒排索引 → 给结果排序**。以下以 Bleve v2.5.5 为准。

沿用上一章的文档，再加一篇作为对照：

- `doc-1`：`title=Raft consensus`，`content=Raft powers consensus`
- `doc-2`：`title=Consensus basics`，`content=Consensus needs quorum`

## 1. 先确定要搜什么

常见查询可以这样区分：

- **Match Query**（分析后匹配：普通全文搜索的基石）
  - 流程：原始输入字符串 -> 通过分词器（Analyzer）拆分成词项（Terms）-> 去倒排索引里查找匹配的文档。
  - 不关注词项在文档里的具体顺序，默认执行的是 OR 逻辑
- **Term Query**（精确匹配：未分析的裸词查询）
  - 完全不经过分词器，只有当倒排词典里存在一模一样的 Term 时，才会命中。
- **Match Phrase Query**（短语匹配：兼顾词项与位置顺序）
  - 流程：原始输入 -> 通过分词器拆成词项 -> 校验文档中是否包含所有这些词项 -> 严格校验这些词项的相对位置（Position）和顺序。
- **Query String Query**（语法解析查询：强大的高级搜索功能）¬

`title:raft` 只是**限定搜索标题**，不等于对整个标题做精确比较。要整串匹配路径，应在建索引时把 `path` 显式设为 `keyword`，再搜索完整路径。

没有指定字段时，Bleve 默认查 `_all`。如果建索引时关闭了 `_all`，必须把 `DefaultField` 改成实际字段，例如 `content`。

## 2. 再把输入变成词

字段的分析器决定查询会查哪些词：

1. 对 `content` 执行 Match Query `Raft consensus`，`standard` 分析器产生 `raft` 和 `consensus`。
2. 英文停用词会被去掉；例如 `Raft is reliable` 中的 `is` 不参与匹配。
3. `keyword` 不拆词。索引里若保存了完整路径 `/guide/raft`，只查 `/guide` 不会自动命中。

中文默认按字切分；如果改用按词切分，写入和查询两边都要使用兼容的分析方式。

## 3. 到 Segment 中找文档

以 `content:consensus` 为例：

1. 在每个 Segment 的 `content` 词典中找 `consensus`。
2. 读取倒排列表，得到命中的段内 `docNum`。
3. 过滤已删除或已更新的旧版本，再汇总各段结果。
4. 计算分数、排序，最后按需取回字段。

示例中的 `doc-1` 和 `doc-2` 都包含 `content:consensus`。倒排列表保存的是段内 `docNum`，结果对外返回的是文档 `_id`。

## 4. 多个词怎么匹配

Match Query 搜索 `raft consensus` 时，默认是 **OR**：

- `doc-1` 同时命中两个词。
- `doc-2` 命中 `consensus`，也会进入结果。

如果要求两个词**都出现**，才把操作符设为 AND；此时示例中只剩 `doc-1`。因此，不能把“两个倒排列表先求交集”当成默认查询流程。

## 5. 为什么结果有先后

- **相关性**：Bleve 根据词频、词的区分度、字段长度等计算分数，匹配更多词的文档通常更靠前。v2.5.5 默认使用 **TF-IDF**；要用 BM25，需显式设置 `ScoringModel = "bm25"`。
- **短语与高亮**：除了命中的文档，还要知道词的位置和偏移。`IncludeTermVectors` 默认开启；关闭后会影响依赖这些信息的功能。
- **字段取回**：倒排索引用于找到文档；要从结果中拿到 `title` 等原值，该字段还需保留 Stored Fields。

搜索结果不符合预期时，依次检查**字段、分析器、查询类型**，再检查评分和结果字段配置。
