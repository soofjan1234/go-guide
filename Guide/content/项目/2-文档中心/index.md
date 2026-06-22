---
title: 文档中心
weight: 2
date: 2026-06-12
draft: false
---

# 一、文档解析
##  PDF、Word、Excel、PPT、Markdown、HTML、EPUB 分别怎么解析？

我们会先根据扩展名、MIME 和文件结构判断文档类型，然后不同格式走不同解析器，最终都抽取成纯文本 content，写入统一的 Document 模型。

PDF：先通过 soffice 转成 HTML，再用 HTML 解析器提取文本。
Word：docx 直接读取 docx 内部 XML，提取 w:t 文本节点；doc 会先通过 soffice 转成 docx，再按 docx 解析。
Excel：使用 excelize 打开 xlsx，遍历 sheet 和 row，把单元格内容拼成文本。
PPT：pptx 本质是 zip 包，读取 ppt/slides/slide*.xml，按页码排序后提取 a:t 文本节点。
Markdown：先用 Markdown parser 转成 HTML，再用 HTML 解析器提取纯文本。
HTML：用 goquery 解析 DOM，然后提取 text。
TXT：会先做编码检测，如果不是 UTF-8，就转换成 UTF-8 后再读取。
EPUB：先解压 EPUB，再按 EPUB 内部章节顺序提取文本。

###  `.doc` 和 `.docx` 的处理有什么区别？

docx 是 Office Open XML，本质是 zip 包，里面是 XML 文件，所以可以直接读取里面的文档 XML，提取文本节点。

doc 是老的二进制格式，直接解析复杂很多，也容易踩兼容性问题。所以我们没有自己实现 doc 二进制解析，而是通过 LibreOffice/soffice 先把 doc 转成 docx，再走统一的 docx 解析流程。

##  为什么限制 50MB？这个阈值怎么定的？

50MB 是一个保护性阈值，主要考虑 NAS 设备资源有限，以及文档解析的 CPU、内存和时间成本。

文件大小和解析后文本大小不完全线性，但大文件通常更容易触发解析耗时长、soffice 转换慢、内存峰值高等问题。我们希望保证后台同步任务不会被少数超大文件拖垮，所以先设定 50MB 作为准入上限。

这个阈值不是绝对理论值，而是结合设备内存、典型用户文档规模和测试观察定的工程参数。后续可以根据设备型号或配置做成可配置项，比如高配 NAS 放宽，低配 NAS 收紧。

# 二、搜索引擎选型
##  ES、MS、bleve、MySQL 对比？

在搜索引擎选型中，我们优先考虑部署复杂度与空间占用。ES虽然功能强大，但更适用于大规模分布式场景，对于资源敏感的nas产品来说 内存占用巨大，默认消耗 1-2GB，同时需要 Java 环境；
Meilisearch降低了使用门槛，但仍需独立部署。
MySQL 的 FULLTEXT 索引能做简单全文检索，但文档中心需要更好的相关性排序、模糊/纠错、中文分词与高亮等，用 MySQL 要么能力不足要么要自己拼，维护成本高；且把「文档检索」和业务结构化数据分开，用嵌入式检索引擎更清晰
Bleve，就像sqlite，完全嵌入式，同时是go原生，无需额外服务，从而降低运维成本并提升部署效率。

## ES和bleve区别

bleve的索引和搜索比es快大概10倍左右

即使排除 JVM 和 HTTP 服务，ES 仍然会因为 DocValues、Aggregation 中间状态、Cluster Metadata 等数据结构占用远高于 Bleve 的内存。

es有内存占用，部署复杂的问题

Bleve 相比 Elasticsearch 少了很多成熟的服务端能力。比如分布式集群、高可用、完善的监控生态、丰富的中文分词插件。

但我们这个场景主要是 NAS 本地检索，数据规模是单设备用户文档，不是互联网级搜索。Bleve 可以满足这些基础全文检索需求。

# 三、内存高以及分块索引
## 怎么理解30兆的会比30个1兆的性能影响更大呢？

1. 当程序处理一个 30MB 的连续文档时，Go 语言的分析器和 Bleve 需要在内存中开辟巨大的连续空间或大对象来存放原始文本、分词后的 Token 数组以及倒排索引的临时对象。
2. 而30 个 1MB 的块：系统每次只需要处理 1MB 的数据，内存峰值大大降低

## 聚合算法是什么？

1. 主文档分两类
	1. 无子文档的，小文档，内容在主文档自己这里
	2. 有子文档的，大文档，内容在子文档里
2. 遍历搜索结果，判断是主文档还是分块；主文档保存到 Map，分块的高亮保存到另一个 Map
3. 如果只匹配到分块，没匹配到主文档，需要主动查询主文档信息
4. 按顺序遍历主文档 ID，拼接高亮内容，取前 5 个片段

## 内存降低怎么测的

多种情况：有all索引，没有all索引；1mb 5mb 10mb分块；10mb 20mb 50mb批量提交

然后通过memstats查看内存占用，对比前后的内存占用，计算出内存降低的百分比

# 四、文件类型校验**
## MIME 类型怎么检测？

我们使用 mimetype 库对文件内容做检测，它不是简单看扩展名，而是读取文件头和部分内容，根据 magic number、文件结构等特征判断 MIME 类型。

## OOXML 内部结构校验具体校验什么？

docx、xlsx、pptx 都属于 Office Open XML，本质是 zip 包。只看 MIME 时，它们有时会被识别成 application/zip，所以我们会打开 zip 的中央目录，检查里面是否存在对应的关键文件。

docx 会检查 `[Content_Types].xml` 和 `word/document.xml`；
xlsx 会检查 `[Content_Types].xml` 和 `xl/workbook.xml`；
pptx 会检查 `[Content_Types].xml` 和 `ppt/presentation.xml`。

只有后缀、MIME 和内部结构都匹配，才认为它是可解析的 Office 文档。