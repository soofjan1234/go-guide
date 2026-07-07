
# 二、消息队列
机器 A：API 实例 1
机器 B：API 实例 2
机器 C：NSQ + consumer
机器 D：MySQL

## 为什么要引入消息队列

1. 解耦。让HTTP只负责业务逻辑，写事件交给消息队列处理。
2. 削峰。比如固件升级后大量设备重启、某个时间段用户集中远程访问 NAS。NSQ 可以让 HTTP 请求快速返回，然后消费者按数据库能承受的速度慢慢写。

## 为什么使用 NSQ

我选 NSQ 是因为这个项目的消息场景比较简单，主要是把操作记录、连接记录从 HTTP 主链路里异步出去，起到削峰和解耦作用。

它不需要 Kafka 那种大规模、分布式的日志流能力，也不需要 RabbitMQ 的复杂路由、事务消息、路由模型。

NSQ 部署轻量，Go 客户端成熟，topic/channel 模型简单，支持失败重试和队列积压观测，和 Go 服务集成成本低，所以更适合这个项目的规模。

### 为什么不用channel

只适合单进程内异步，不能跨实例，重启丢消息，积压不可观测

### nsq有没有死信队列

在 NSQ 里，每条消息都有 attempts 字段：

消费失败 → Requeue；NSQD 重新投递（延迟递增）；直到达到 max_attempts

超过之后的行为是默认直接丢弃（FIN）

## 为什么要记录事件

操作留痕：用户反馈「连不上 / 凭证无效」时，可按时间线对照事件，避免只靠口述猜。

# 三、nsq
## 结构是什么样的

整体是「多 API 实例生产 → NSQ 缓冲 → 单 consumer 消费写库」：

1. **Producer（机器 A/B）**：HTTP 处理完主业务后，把事件序列化成 JSON，Publish 到对应 topic，然后立刻返回响应。
2. **NSQD（机器 C）**：负责接收、持久化、按 topic 分发消息。
3. **Consumer（机器 C）**：订阅 topic 下的 channel，拉取消息后写 MySQL，成功再 FIN。
4. **MySQL（机器 D）**：事件最终落库，供排障和审计查询。

NSQ 核心概念：

- **topic**：事件类型，比如连接事件、凭证颁发事件，一类业务一个 topic。
- **channel**：消费组；同一个 topic 可以有多个 channel 做不同消费逻辑，我们场景主要是单 channel 写库。
- **nsqlookupd**：做服务发现，producer/consumer 通过它找到 nsqd 地址。

一条请求的链路：`API 实例 → Publish(topic) → NSQD 落盘 → Consumer 消费 → INSERT MySQL → FIN`。

## 是at-least-once还是exactly-once

**at-least-once，不是 exactly-once。**

NSQ 的语义是：消息至少被投递一次。consumer 处理成功后要显式 FIN；如果处理中崩溃、超时或主动 Requeue，消息会被再次投递。

我们没有做 exactly-once，因为事件日志是旁路异步写入，主链路是穿透信令，不要求事件和 HTTP 响应强一致。真要逼近 exactly-once，需要「幂等消费 + 业务唯一键 + 去重表」，成本和复杂度对我们这个规模不划算。

## 消息丢失

事件「希望尽量可靠」，但架构上接受极小概率丢失，换取主链路性能和削峰。可能丢的场景：

1. **Publish 失败**：NSQ 不可用或网络抖动，消息没进队列。HTTP 主流程仍可能已成功，事件旁路丢失。
2. **超过 max_attempts**：consumer 反复失败，NSQ 默认 FIN 丢弃，没有死信队列。
3. **极端宕机**：nsqd 在落盘前崩溃（概率较低，NSQ 会写磁盘）。

我们的应对：

- consumer 写库失败走 Requeue，调大 `max_attempts`，给 transient 错误留重试空间。
- 监控 Depth、Requeue Count，异常时告警。
- 关键凭证类数据在主业务链路同步写库，不只依赖 NSQ 事件。
- NSQ 挂掉时，当前策略是**主流程继续、事件降级丢失**（可追问：是否落本地 buffer）。

## 消息重复

at-least-once 下**重复是正常现象**，典型原因：

1. consumer 写库成功，但 FIN 之前进程崩溃 → NSQ 认为未消费，重新投递。
2. Requeue 重试时，前一次其实已部分成功。
3. 网络超时导致 consumer 不确定结果，再次消费。

我们的处理：**幂等消费**。

- 每条事件带 `event_id`（UUID）或业务唯一键（如 `device_id + event_type + timestamp`）。
- 写库用 `INSERT IGNORE` 或 `ON DUPLICATE KEY UPDATE`，重复投递不会多出脏行。
- consumer 逻辑设计成可重入，避免「先查再插」的非原子竞态。

## 消息顺序

**不保证全局严格有序。**

原因：

1. 多台 API 实例并发 Publish，到达 NSQD 的顺序不确定。
2. NSQ 同一 topic 下多个 consumer 实例会分摊消息（我们主要是单 consumer，这点压力小）。
3. Requeue 会把失败消息延后重投，打乱原有顺序。

对我们的事件日志场景，**通常不需要全局有序**，按事件自带的 `event_time` 排序查时间线即可。如果同一设备的状态机事件需要有序（比如先颁发凭证再校验），更稳妥的做法是：

- 用 `device_id` 做 partition key，同一设备的事件进同一 topic 并由单 consumer 处理；或
- 消费侧按 `event_time` + 版本号做乱序容忍，拒绝明显过期的状态变更。

## 如果 NSQ 堆积了怎么办？怎么监控？

监控 NSQ 的核心是监控其三个关键指标：Depth（堆积深度）、In-Flight（正在处理数） 和 Requeue Count（重投次数）。

NSQ 官方已经提供/stats，使用nsq_exporter拉取并转为metrics，然后使用Prometheus监控。

## 用 NSQ 提升吞吐 1.6 倍怎么测的？

使用vegeta，在rps500-1000-1500下，对比有nsq和无nsq的情况，查看latency，吞吐与平均延迟，得到的
