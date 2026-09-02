---
title: 文档中心1
weight: 10
date: 2026-06-12
draft: false
---

# 文档解析
## MIME 类型怎么检测？

我们使用 github.com/gabriel-vasile/mimetype 库对文件内容做检测，它不是简单看扩展名，而是读取文件头和部分内容，根据 magic number、文件结构等特征判断 MIME 类型。

对docx、xlsx、pptx 来说，只看 MIME 时，它们有时会被识别成 application/zip，所以我们会打开 zip 的中央目录，检查里面是否存在对应的关键xml文件。

比如docx 会检查 `[Content_Types].xml` 和 `word/document.xml`

##  PDF、Word、Excel、PPT、Markdown、HTML、EPUB 分别怎么解析？

- PDF：通过pdftotext解析

- Word：docx 直接读取 docx 内部 XML，提取 w:t 文本节点；doc 会通过 antiword 解析。
- Excel：使用 excelize 打开 xlsx，遍历 sheet 和 row，把单元格内容拼成文本。
- PPT：pptx 本质是 zip 包，读取 ppt/slides/slide*.xml，按页码排序后提取 a:t 文本节点。

- Markdown：先用 Markdown parser 转成 HTML，再用 HTML 解析器提取纯文本。
- HTML：用 goquery 解析 DOM，然后提取 text。

- TXT：会先做编码检测，如果不是 UTF-8，就转换成 UTF-8 后再读取。
- EPUB：先解压 EPUB，再按 EPUB 内部章节顺序提取文本。

## 为什么不用其它方法

1. Apache Tika：极度稳定、格式支持最全，但是基于JVM环境
2. Pandoc：内存占用高
3. LibreOffice：还原度最高，支持老旧格式，但是太重
4. Docling\RapidDoc\MarkItDown：都需要python环境，cpu、内存占用效果不如第三方库

我选型时优先考虑四个指标：格式覆盖、文本抽取质量、部署成本、失败可控性

# 搜索引擎
## ES、MS、bleve、MySQL 对比？

ES虽然功能强大，但更适用于大规模分布式场景，需要 Java 环境，默认消耗 1-2GB；

Bleve，就像sqlite，完全嵌入式，同时是go原生，无需额外服务，从而降低运维成本并提升部署效率。

Meilisearch搜索比bleve快，建立比bleve慢，更适合千万级文档；

ZincSearch 中文分词有问题，并且项目很久没更新，成熟度不足

SQLite FTS5更适合单机、轻量、简单查询、数据和 SQLite 强绑定的场景

MySQL 的 FULLTEXT 索引能做简单全文检索，但文档中心需要中文分词与高亮等，用 MySQL 要么要自己拼，维护成本高

PostgreSQL，为了搜索引入一整套数据库”，收益不足以覆盖成本，GIN只是一种倒排索引结构，不等于完整的中文搜索方案

## 怎么没有用这个 AI 搜索 / 向量搜索？

1. 需要精确搜索。RAG可能匹配到语义相似的
2. 资源考虑。RAG 要做 embedding、向量索引
3. 当前需求不需要生成答案。如果产品需求是“帮我总结这些文档”“根据资料回答问题”，那可以考虑 RAG。

# bleve的增删改查

## 存储

Bleve 底层用 Scorch，和 ES/Lucene 类似，都是 段式倒排索引。

文档写入时先按 mapping 分词，把每个 term 映射到 出现在哪些 docID、频次多少、字段内偏移多少，这就是 posting list，不是把整篇正文按文档顺序存一份。

经过 Gap 编码后，由 [2003, 2005, 2008, 2012, 2015...] 变成 [2003, 2, 3, 4, 3...]，配合压缩算法能降低内存，加快速度

一批文档会先分析成 内存段，再持久化到磁盘；查询时扫多个段合并结果，后台还会 merge 小段。

### 搜索

用户输入关键词后，Bleve 先用和建索引相同的 analyzer 把查询词拆开，比如「文档中心」→「文档」「中心」。

然后在倒排索引里查每个词项的 posting list，得到候选 docID，多个词再合并交集/并集，按相关性打分排序。

因为索引是段式的，查询时会扫当前所有 segment，把各段结果合并后再取 TopN。

### 删改

倒排索引不会原地改。旧 segment 只读，删/改时在 segment 里用 obsolete 位图标记作废，新内容写进新 segment。

查询时多段合并，过滤掉已作废的 docID；后台 merge 再物理清理旧 posting。
