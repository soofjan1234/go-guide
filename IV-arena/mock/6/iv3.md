**一、整体架构**
1. 如果用户上传/修改/删除一个文档，索引如何更新？

**二、Elasticsearch 到 Bleve 迁移**
1. Elasticsearch 在 NAS 设备上的主要问题是什么？
2. Bleve 相比 Elasticsearch 少了哪些能力？你们怎么取舍？
3. 迁移后搜索效果、性能、资源占用分别有什么变化？

**三、超长文档分块索引**
1. 为什么大文档直接索引会导致内存峰值过高？
2. 你们为什么按 1MB 分块？这个大小怎么来的？
3. 分块以后，用户搜索时怎么把 chunk 结果还原成原文档？
4. 如果一个文档有 100 个 chunk，删除或更新时怎么处理？
5. 你说 heapInuse 降低 76%+，怎么测的？用什么工具？测试数据是什么？

**四、文档解析**
1. PDF、Word、Excel、PPT、Markdown、HTML、EPUB 分别怎么解析？
2. `.doc` 和 `.docx` 的处理有什么区别？
3. 为什么要用 LibreOffice/soffice？
4. 为什么限制 50MB？这个阈值怎么定的？

**五、文件类型校验**
1. MIME 类型怎么检测？
2. OOXML 内部结构校验具体校验什么？

[答案]
1. es在nas上的问题，bleve少了哪些能力，如何取舍

es有内存占用，部署复杂的问题

Bleve 相比 Elasticsearch 少了很多成熟的服务端能力。比如分布式集群、高可用、完善的监控生态、丰富的中文分词插件。

但我们这个场景主要是 NAS 本地检索，数据规模是单设备用户文档，不是互联网级搜索。Bleve 可以满足这些基础全文检索需求。

所以取舍是：放弃 ES 的分布式和复杂分析能力，换取更低的资源占用、更简单的部署、更少的外部依赖和更好的端侧可控性。

2. PDF、Word、Excel、PPT、Markdown、HTML、EPUB 分别怎么解析？

我们会先根据扩展名、MIME 和文件结构判断文档类型，然后不同格式走不同解析器，最终都抽取成纯文本 content，写入统一的 Document 模型。

PDF：先通过 soffice 转成 HTML，再用 HTML 解析器提取文本。
Word：docx 直接读取 docx 内部 XML，提取 w:t 文本节点；doc 会先通过 soffice 转成 docx，再按 docx 解析。
Excel：使用 excelize 打开 xlsx，遍历 sheet 和 row，把单元格内容拼成文本。
PPT：pptx 本质是 zip 包，读取 ppt/slides/slide*.xml，按页码排序后提取 a:t 文本节点。
Markdown：先用 Markdown parser 转成 HTML，再用 HTML 解析器提取纯文本。
HTML：用 goquery 解析 DOM，然后提取 text。
TXT：会先做编码检测，如果不是 UTF-8，就转换成 UTF-8 后再读取。
EPUB：先解压 EPUB，再按 EPUB 内部章节顺序提取文本。

3. doc和docx的区别

docx 是 Office Open XML，本质是 zip 包，里面是 XML 文件，所以可以直接读取里面的文档 XML，提取文本节点。

doc 是老的二进制格式，直接解析复杂很多，也容易踩兼容性问题。所以我们没有自己实现 doc 二进制解析，而是通过 LibreOffice/soffice 先把 doc 转成 docx，再走统一的 docx 解析流程。

4. 为什么限制 50MB，阈值怎么定

50MB 是一个保护性阈值，主要考虑 NAS 设备资源有限，以及文档解析的 CPU、内存和时间成本。

文件大小和解析后文本大小不完全线性，但大文件通常更容易触发解析耗时长、soffice 转换慢、内存峰值高等问题。我们希望保证后台同步任务不会被少数超大文件拖垮，所以先设定 50MB 作为准入上限。

这个阈值不是绝对理论值，而是结合设备内存、典型用户文档规模和测试观察定的工程参数。后续可以根据设备型号或配置做成可配置项，比如高配 NAS 放宽，低配 NAS 收紧。

5. MIME 类型怎么检测

我们使用 mimetype 库对文件内容做检测，它不是简单看扩展名，而是读取文件头和部分内容，根据 magic number、文件结构等特征判断 MIME 类型。

6. OOXML 内部结构校验具体校验什么

docx、xlsx、pptx 都属于 Office Open XML，本质是 zip 包。只看 MIME 时，它们有时会被识别成 application/zip，所以我们会打开 zip 的中央目录，检查里面是否存在对应的关键文件。

docx 会检查 `[Content_Types].xml` 和 `word/document.xml`；
xlsx 会检查 `[Content_Types].xml` 和 `xl/workbook.xml`；
pptx 会检查 `[Content_Types].xml` 和 `ppt/presentation.xml`。

只有后缀、MIME 和内部结构都匹配，才认为它是可解析的 Office 文档。