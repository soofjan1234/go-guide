很多，而且这句话的价值就在于它**天然能引出一整套 RAG 工程问题**。如果我是面试官，看到：

> 构建合成基准集 + 历史真实邮件双阶段 Retrieval Benchmark，以 Recall@K、MRR、P95 延迟和内存对 4 个 Embedding 模型进行选型。

我大概率会沿着下面几个方向追。

1. **为什么要两阶段？直接拿真实邮件测不行吗？**
   你可以答：合成集的 Ground Truth 明确，可以刻意覆盖型号混淆、错误码、拼写错误、双问题等边界场景，适合控制变量；真实邮件反映线上真实分布，但 Ground Truth 更难获得。所以先用合成集做能力筛选，再用历史邮件验证泛化。

2. **你的合成数据怎么生成？会不会模型自己出题、自己评测，导致数据污染？**
   这是非常可能被问的。你需要讲清楚：先冻结知识片段，再生成 Query 和 relevant chunk 标注；开发集用于调整输入方式，保留集不参与调参；最终真实邮件集再做第二阶段验证。你现在设计里的开发/保留隔离就是很好的回答。

3. **真实邮件的 Ground Truth 怎么来的？**
   这个可能是最重要的问题。
   不能回答“历史邮件有对应回复，所以回复就是 Ground Truth”。面试官会继续问：“那你怎么知道这封邮件应该命中哪个产品文档 chunk？”

你需要有一套明确流程：

**历史客户邮件 → 对应人工回复 → 候选证据召回 → 自动初标 → 人工确认 relevant chunks → 冻结评测集。**

这样 Recall/MRR 才有意义。

4. **为什么用 Recall@K 和 MRR？两者有什么区别？**
   标准回答可以很简单：

Recall@K 看的是：

> **正确证据有没有进入 Top-K。**

MRR 看的是：

> **第一个正确证据排得够不够靠前。**

例如正确 chunk 排第 3：

`Recall@3 = 1`，但 `MRR = 1/3`。

所以一个保证“有没有找到”，一个衡量“是不是排得足够前”。

5. **为什么不是只看 Recall@1？**

你的项目特别好回答，因为存在**一封邮件需要多个证据片段**的情况。

例如：

> “DDNS 域名访问不了，同时路由器 WAN 是 100.72.x.x。”

它同时涉及 DDNS 和 CGNAT。Top-1 天生装不下两个 relevant chunks，所以你还设计了“完整覆盖问题”。这会显得你真正理解 retrieval evaluation，而不是背 Recall 公式。

6. **四个 Embedding 模型最后怎么选？**

这时候就可以讲真实实验：

Snowflake：

* 两路 Recall@3 = 100%
* 84/84 完整覆盖
* P95 ≈ 58ms
* 内存 ≈ 803MiB

而 BGE-M3：

* 某一路 Recall@3 = 98.81%
* P95 ≈ 205ms
* 内存 ≈ 1.7GiB

然后你的重点不是：

> “Snowflake 分数最高，所以选 Snowflake。”

而是：

> **质量达到要求以后，再综合 latency、memory 和部署复杂度选择。Embedding 选型是多目标问题，不是排行榜最高就直接用。**

这个回答很好。

7. **为什么不直接看 MTEB 排行榜？**

这个问题也很适合发挥：

> MTEB 衡量通用能力，但我的数据是英文 NAS 售后邮件，有型号、协议、错误码、拼写错误、用户口语和多故障组合。通用 benchmark 不能替代 domain-specific evaluation，所以排行榜用于筛候选，业务 Benchmark 决定最终选型。

这句话面试效果会很好。

8. **为什么还测 P95 和内存？Embedding 又不是生成模型。**

因为 Embedding 不只发生在离线建库：

> 文档 Embedding 可以离线批量完成，但 Query Embedding 在每次检索链路上。如果 Agent 一封邮件触发 query rewrite、多路检索甚至多次 retrieval，Embedding latency 会进入在线 P95；本地部署时内存还直接影响机器成本以及能否和其他服务共存。

这又能接到系统工程。

9. **换 Embedding 模型为什么要重新建库？维度一样能不能继续用？**

这是很好的追问题：

> 不能。即使都是 1024 维，不同模型产生的是不同向量空间，旧 document embedding 和新 query embedding 没有可比性。所以模型、输入模板、pooling、归一化方式变化，都应该视为一个新的索引版本并重新 embedding。

你现在设计文档里本身就明确考虑了这个问题。

10. **Embedding 选好了，为什么还要全文检索 + RRF？**

这就能顺势进入你简历现有的 Hybrid Search：

> Dense retrieval 擅长语义相似，但 NAS 售后里有型号、错误码、协议名等 lexical signal，例如具体错误码可能 BM25/全文检索更稳定。所以向量和全文分别召回，再通过 RRF 融合，避免直接比较两套不可比的 score。

然后面试官还能继续追：

**为什么用 RRF、不直接加权分数？RRF 的 k 怎么定？Hybrid Search 后 Recall 提升多少？要不要 rerank？**

这就已经从一个 Embedding bullet，自然进入整个 RAG 系统了。
