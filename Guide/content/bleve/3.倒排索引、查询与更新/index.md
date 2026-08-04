---
title: Bleve 倒排索引、查询与更新
weight: 3
date: 2026-07-01
draft: false
---

# 倒排索引

Bleve 的核心存储模型是：

> 文档先分词，再按 segment 写入倒排索引。倒排索引记录某个字段里的某个词出现在哪些文档中，以及词频、位置等信息。

普通存储更像：

```text
文档 -> 词
```

倒排索引反过来：

```text
词 -> 文档列表
```

例如：

```json
{
  "title": "Raft consensus",
  "content": "Raft is a consensus algorithm"
}
```

经过 analyzer 后可能得到：

```text
title: raft, consensus
content: raft, consensus, algorithm
```

索引入口大致是：

```text
title:raft       -> doc 1
content:raft     -> doc 1
content:algorithm -> doc 1
```

---

## Field + Term

Bleve 按字段组织 term。`title` 里的 `raft` 和 `content` 里的 `raft` 是两个入口：

```text
title:raft
  -> doc 1, doc 8, doc 20

content:raft
  -> doc 1, doc 3, doc 8, doc 100
```

这样可以保留字段语义：标题命中、正文命中、boost、高亮、相关性计算都能区分处理。

## Posting List

某个 term 对应的文档列表叫 posting list：

```text
term: content:raft
  -> docID: 1, 100, 250
  -> freq:  3, 1, 7
  -> pos:   [4, 20, 88], [9], [1, 5, 9, 13]
```

| 信息 | 作用 |
|---|---|
| docID | 词出现在哪些文档里 |
| freq | 词在文档里出现几次 |
| position | 词序位置，用于短语查询、高亮 |
| offset | 原文字符偏移，用于生成高亮片段 |

简单搜索只需要 docID；相关性排序、高亮、短语查询会用到更多信息。

## Gap 编码

posting list 里的 docID 递增排列，可以用相邻差值压缩：

```text
原始 docID: 1, 100, 250
gap 编码:   1, 99, 150
```

gap 通常比原始 docID 小，更适合变长整数或块压缩。

## Term Dictionary

term dictionary 用来快速判断某字段下是否存在某个 term，并定位 posting list：

```text
找 content:raft
-> 定位 posting list
-> 读取 docID、词频、位置等信息
```

---

# 查询流程

Bleve 搜索不会逐篇文档做 `contains`，而是直接走倒排索引。

搜索 `raft` 时：

```text
_all:raft
```

指定字段时：

```text
title:raft
content:raft
```

## 单词查询

以 `content:raft` 为例：

```text
1. 查询词经过 analyzer
2. 得到 term: raft
3. 在每个 segment 的 term dictionary 中找 content:raft
4. 读取 posting list
5. 计算相关性分数
6. 合并多 segment 结果
7. 排序、分页、返回
```

关键路径：

```text
term -> posting list -> docID
```

## 多词查询

搜索 `raft consensus` 时，先分成两个 term：

```text
raft
consensus
```

AND 查询取交集：

```text
raft      -> doc 1, doc 3, doc 8, doc 100
consensus -> doc 1, doc 8, doc 20

交集 -> doc 1, doc 8
```

OR 查询取并集，再结合词频、字段长度、boost 等信息算分。

---

# 删除与修改

Segment-based 索引通常不原地修改旧 posting list。原因是倒排索引经过压缩，频繁中间插入或删除会带来大量重写。

Bleve 更接近：

```text
新增靠追加
删除靠标记
修改 = 删除旧文档 + 新增新文档
```

## 删除

删除文档时，旧 segment 通常不会立刻物理清理，而是记录删除标记。

```text
content:raft -> doc 1, doc 3, doc 8
```

删除 `doc 3` 后，posting list 可以暂时不变，只额外记录：

```text
doc 3 已删除
```

查询命中 `doc 3` 时，会被删除标记过滤。真正清理发生在后台 merge。

## 修改

修改等价于：

```text
1. 标记旧文档删除
2. 重新分析并写入新版本
```

例如 `doc 1` 从：

```text
content: raft algorithm
```

改成：

```text
content: paxos algorithm
```

Bleve 不会在旧 posting list 中原地删 `raft -> doc 1`、插 `paxos -> doc 1`，而是让旧版本失效，新版本进入新的写入批次或 segment。

## Merge

merge 会把多个小 segment 合成大 segment，并清理已删除文档：

```text
segment A + segment B + segment C
  -> merge
  -> segment D
```

merge 后：

```text
1. segment 数量减少
2. 删除文档被清理
3. posting list 重新编码
4. 查询时需要合并的 segment 更少
```

所以删除和修改不会立刻释放全部空间，要等 merge 后才压实。
