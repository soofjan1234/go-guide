

2. **你的合成数据怎么生成？会不会模型自己出题、自己评测，导致数据污染？**
   这是非常可能被问的。你需要讲清楚：先冻结知识片段，再生成 Query 和 relevant chunk 标注；开发集用于调整输入方式，保留集不参与调参；最终真实邮件集再做第二阶段验证。你现在设计里的开发/保留隔离就是很好的回答。

3. **真实邮件的 Ground Truth 怎么来的？**
   这个可能是最重要的问题。
   不能回答“历史邮件有对应回复，所以回复就是 Ground Truth”。面试官会继续问：“那你怎么知道这封邮件应该命中哪个产品文档 chunk？”

你需要有一套明确流程：

**历史客户邮件 → 对应人工回复 → 候选证据召回 → 自动初标 → 人工确认 relevant chunks → 冻结评测集。**

这样 Recall/MRR 才有意义。

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


**为什么用 RRF、不直接加权分数？RRF 的 k 怎么定？Hybrid Search 后 Recall 提升多少？要不要 rerank？**

这就已经从一个 Embedding bullet，自然进入整个 RAG 系统了。
