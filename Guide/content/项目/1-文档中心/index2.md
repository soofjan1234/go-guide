---
title: Bleve 底层存储与检索流程
weight: 2
date: 2026-07-01
draft: false
---

# 一、Bleve 底层是怎么存的？

Bleve 可以理解成一个嵌入式全文检索引擎，核心存储模型是：

> 文档经过分词后，按 segment 存储倒排索引；倒排索引记录某个字段里的某个词，出现在哪些文档里，以及出现频率、位置等信息。

它不是把文档原文简单地一行行存起来然后扫描，而是先把文档分析成 term，再建立 term 到文档的映射。

比如一篇文档是：

```json
{
  "title": "Raft consensus",
  "content": "Raft is a consensus algorithm"
}
```

经过 analyzer 处理后，可能得到：

```text
title: raft, consensus
content: raft, consensus, algorithm
```

然后 Bleve 会建立类似这样的倒排索引：

```text
title:raft
  -> doc 1

content:raft
  -> doc 1

content:algorithm
  -> doc 1
```

这里的核心不是“文档 -> 词”，而是反过来：

```text
词 -> 哪些文档包含这个词
```

所以它叫倒排索引。

## 1. field + term 是基本检索单元

Bleve 的倒排索引通常不是只按裸 term 存，而是按字段维度组织。

比如 `title` 里的 `raft` 和 `content` 里的 `raft` 是两个不同的检索入口：

```text
title:raft
  -> doc 1, doc 8, doc 20

content:raft
  -> doc 1, doc 3, doc 8, doc 100
```

这样做的好处是可以保留字段语义。比如命中标题通常比命中正文更重要，后续做相关性打分、boost、高亮时都能利用这个信息。

## 2. posting list 里存什么？

倒排索引里某个 term 对应的一串文档列表，通常叫 posting list。

它大概会包含：

```text
term: content:raft
  -> docID: 1, 100, 250
  -> freq:  3, 1, 7
  -> pos:   [4, 20, 88], [9], [1, 5, 9, 13]
```

几个字段的含义：

| 信息 | 作用 |
|---|---|
| docID | 这个词出现在哪些文档里 |
| freq | 这个词在文档里出现了几次 |
| position | 这个词在文档中的词序位置，用于短语查询、高亮 |
| offset | 这个词在原文中的字符偏移，用于生成高亮片段 |

如果只做简单搜索，docID 就够了；如果要做相关性排序、高亮、短语查询，就需要 freq、position、offset 这些额外信息。

## 3. 为什么会存成间隔？

posting list 里的 docID 是递增的，所以可以用 gap/delta 编码压缩。

比如原始 docID 是：

```text
1, 100, 250
```

直接存原值也可以，但数值可能越来越大。因为它们是递增的，所以可以改成存相邻差值：

```text
1, 99, 150
```

也就是：

```text
1
100 - 1 = 99
250 - 100 = 150
```

这样做的收益是 gap 往往比原始 docID 小，更适合用变长整数、块压缩等方式存储。

所以如果说“第一页和第一百页存成 1、99”，更准确的说法是：

> 不是页号，而是文档 ID；倒排表里 docID 递增排列，然后用相邻 docID 的差值来压缩存储。

## 4. segment 是什么？

Bleve 底层不是不断修改一个巨大的索引文件，而是把索引拆成多个 segment。

可以粗略理解成：

```text
segment A
  - term dictionary
  - inverted index
  - stored fields
  - doc values

segment B
  - term dictionary
  - inverted index
  - stored fields
  - doc values
```

每个 segment 内部都有自己的一套倒排索引和局部 docID。

新增文档时，Bleve 更偏向追加生成新的 segment，而不是原地改旧 segment。这样写入路径更简单，也更适合批量写入。

## 5. term dictionary 是什么？

倒排索引不是直接从所有 term 里线性扫描，而是会有 term dictionary。

它的作用是快速判断某个字段下有没有某个 term，并定位到对应的 posting list。

比如查询 `content:raft` 时，大致流程是：

```text
先在 term dictionary 中找 content:raft
找到后，再跳到对应 posting list
读取 docID 列表、词频、位置等信息
```

# 二、Bleve 搜索是什么样的？

Bleve 搜索时，不会把每篇文档拿出来逐个 contains 判断，而是直接走倒排索引。

比如搜索：

```text
raft
```

如果查的是 `_all` 字段，就会变成找：

```text
_all:raft
```

如果是指定字段搜索，可能是：

```text
title:raft
content:raft
```

## 1. 单词查询流程

以查 `content:raft` 为例：

```text
1. 对查询词 raft 做 analyzer 处理
2. 得到 term: raft
3. 在每个 segment 的 term dictionary 中查 content:raft
4. 找到对应 posting list
5. 读取命中的 docID
6. 根据 freq、field length 等信息计算相关性分数
7. 合并多个 segment 的结果
8. 排序、分页、返回
```

也就是说，查询速度快的关键在于：

```text
term -> posting list -> docID
```

它可以直接定位到包含这个词的文档，而不是全量扫描文档内容。

## 2. 多词查询流程

比如搜索：

```text
raft consensus
```

经过分词后得到两个 term：

```text
raft
consensus
```

如果是 AND 查询，就会取 posting list 的交集：

```text
raft      -> doc 1, doc 3, doc 8, doc 100
consensus -> doc 1, doc 8, doc 20

交集 -> doc 1, doc 8
```

如果是 OR 查询，就会取并集：

```text
并集 -> doc 1, doc 3, doc 8, doc 20, doc 100
```

然后再结合词频、字段长度、字段 boost 等信息计算分数。

## 3. 跨 segment 怎么查？

因为索引被拆成多个 segment，所以一次查询会在多个 segment 上执行。

比如：

```text
segment A:
  content:raft -> local doc 1, local doc 5

segment B:
  content:raft -> local doc 2, local doc 9
```

搜索时会分别查每个 segment，然后把每个 segment 的局部 docID 映射成全局文档，再合并排序。

可以理解成：

```text
每个 segment 内部先查一次
多个 segment 的结果再归并
```

segment 越多，查询时需要参与归并的结果也越多，所以后台 merge 对查询性能也有帮助。

## 4. `_all` 字段在查询里的作用

`_all` 是一个聚合字段，它会把多个字段中允许进入 `_all` 的文本汇总到一起建索引。

比如：

```text
title: raft consensus
content: raft is a consensus algorithm
```

如果开启 `_all`，会额外形成：

```text
_all: raft consensus raft is a consensus algorithm
```

这样用户输入一个关键词时，可以直接查 `_all`：

```text
_all:raft
```

不用应用层手动拼：

```text
title:raft OR content:raft OR summary:raft
```

它的收益是默认搜索体验简单、字段解耦、不容易漏查；代价是索引体积变大，并且字段语义会被弱化。

# 三、删除和修改是什么样的？

Bleve 这种 segment-based 的索引，通常不会在旧 segment 里原地修改 posting list。

原因是倒排索引是压缩过的结构，posting list 也经常是连续编码的。如果每次修改文档都去中间改一段，会非常复杂，而且性能不稳定。

所以它更偏向：

```text
新增靠追加
删除靠标记
修改 = 删除旧文档 + 新增新文档
```

## 1. 删除文档

删除文档时，通常不是马上把旧 segment 里的内容物理擦掉，而是先记录一个删除标记。

比如原来：

```text
content:raft -> doc 1, doc 3, doc 8
```

现在删除 doc 3，倒排表可能暂时还是：

```text
content:raft -> doc 1, doc 3, doc 8
```

但系统会记录：

```text
doc 3 已删除
```

查询时即使 posting list 里扫到了 doc 3，也会根据删除标记把它过滤掉。

等后台 segment merge 时，才会真正把已删除文档从新 segment 里清理掉。

## 2. 修改文档

修改文档可以理解成两步：

```text
1. 标记旧文档删除
2. 把新版本文档重新分析、重新写入索引
```

比如 doc 1 原来是：

```text
content: raft algorithm
```

后来改成：

```text
content: paxos algorithm
```

它不会去旧 posting list 里把 `raft -> doc 1` 原地删掉，再把 `paxos -> doc 1` 原地插进去。

更常见的做法是：

```text
旧 doc 1 标记删除
新 doc 1 写入新的 segment 或新的索引批次
```

查询 `raft` 时，旧 doc 1 会被删除标记过滤掉；查询 `paxos` 时，会命中新版本文档。

## 3. segment merge 做什么？

随着不断新增、删除、修改，segment 会越来越多，里面也会有一些已经删除的文档。

merge 的作用是把多个小 segment 合成更大的 segment，并顺手清理掉已删除文档。

大致过程：

```text
segment A + segment B + segment C
  -> merge
  -> segment D
```

merge 后：

```text
1. 小 segment 数量减少
2. 删除文档被真正清理
3. posting list 重新编码
4. 查询时需要归并的 segment 更少
```

所以删除和修改不是立刻释放所有空间，而是等 merge 后才真正压实。

# 四、一句话总结

Bleve 底层可以这样理解：

> 文档先经过 analyzer 分词，然后写入多个不可变 segment；每个 segment 里用 field + term 组织倒排索引，posting list 记录命中的 docID、词频、位置等信息，并用 gap 编码压缩。查询时先从 term dictionary 找到 posting list，再跨 segment 合并结果；删除靠标记，修改等价于删除旧文档再新增新文档，最后通过 merge 清理和压实。

