1. mySQL
    - 索引下推
    - 数据一致性
2. channel
3. 消息队列对比


这一节的主要问题是：**记住了产品标签，但没把“适用场景—实现机制—代价”串起来。** 面试官连续追问，就是想听“为什么”。

### 1. RabbitMQ、Kafka、RocketMQ 各有什么优缺点？

**主要问题：**

- “Kafka 适合日志”方向正确，但用途不止日志。
- “RocketMQ 适合一致性要求高的交易系统”需要落到事务消息等具体能力，不能暗示它自动保证业务强一致。
- 不能直接断言 RabbitMQ 吞吐一定低于另外两个，要说明队列类型、可靠性配置和测试条件。

**建议回答：**

> 我会从业务需求来比较。
>
> Kafka 更偏向事件流和大规模数据管道，比如日志、埋点和流处理。它支持消息保留和按消费位置重放，适合多组消费者独立处理数据；但需要管理分区和消费进度，批量参数也要权衡吞吐与延迟。
>
> RocketMQ 更偏业务消息，提供事务消息、顺序消息和延迟消息等能力，适合订单状态流转这类场景。不过事务消息主要协调本地事务和消息发送，消费端仍然需要处理幂等和失败重试。
>
> RabbitMQ 的特点是交换机路由灵活，适合任务分发和复杂路由。吞吐要结合队列类型和配置判断，它也有面向高吞吐的 Streams，不能简单排一个固定名次。

依据：[Kafka 设计](https://kafka.apache.org/design/)、[RocketMQ 事务消息](https://rocketmq.apache.org/docs/featureBehavior/04transactionmessage/)、[RabbitMQ 交换机](https://www.rabbitmq.com/docs/exchanges)与 [Streams](https://www.rabbitmq.com/docs/streams)。

### 2. 为什么 Kafka、RocketMQ 能做到高吞吐？

**主要问题：** “因为是分布式架构”太宽泛，RabbitMQ 也支持集群。要解释如何降低单条消息的处理成本，以及如何扩大并行度。

**建议回答：**

> 主要从两个方向理解：一个是减少每条消息的开销，另一个是增加并行处理能力。
>
> Kafka 把消息追加到分区日志里，采用顺序写；生产和消费支持批量处理，减少网络请求和 I/O 次数。它利用操作系统页缓存，并在适用的传输路径上利用零拷贝减少数据复制。多个分区还能分布到不同 Broker，支持并行处理。
>
> RocketMQ 的经典存储设计也采用追加写，把消息正文写入 CommitLog，再通过 ConsumeQueue 索引定位消息；多个队列和 Broker 提供并行处理能力。
>
> 所以高吞吐来自存储、批量传输和并行设计的共同作用，不能只归因于“分布式”。

依据：[Kafka 设计](https://kafka.apache.org/20/design/design/)、[RocketMQ 存储设计](https://github.com/apache/rocketmq/blob/develop/docs/en/Design_Store.md)。

### 3. 具体是什么架构？怎么设计的？

**主要问题：** 前一问只提了 partition，没有继续解释消息写到哪里、消费者怎么读。

**建议回答：**

> 以 Kafka 为例，Topic 会划分成多个 Partition，各分区分布在不同 Broker 上。生产者把消息发给目标分区的 Leader，消息按顺序追加到日志中，并按配置复制到其他副本。
>
> 消费者通过 offset 记录消费位置，按批次拉取消息。对于常规消费者组，一个分区同一时刻由组内一个消费者负责，因此多个分区可以并行消费，但单个分区也会限制并行度。
>
> RocketMQ 的经典存储结构有所不同：同一个 Broker 上不同队列的消息正文统一追加到 CommitLog，ConsumeQueue 保存定位信息。消费时先查对应队列的索引，再到 CommitLog 读取正文。

这里最值得记清的区别是：**Kafka 按分区组织日志；RocketMQ 的经典设计将消息正文与消费队列索引分开存储。** [Kafka 设计](https://kafka.apache.org/20/design/design/)、[RocketMQ 存储设计](https://github.com/apache/rocketmq/blob/develop/docs/en/Design_Store.md)