---
title: 进阶
weight: 20
date: 2026-08-09
draft: false
---

# RabbitMQ 进阶

## 一、如何保证消息可靠

沿着 **Producer → RabbitMQ → Consumer** 看三段链路，分别处理发布失败、Broker 故障和消费失败。

### 1. 发布：Confirm + 路由检查

1. 开启 Publisher Confirm。`ack` 表示 Broker 完成这次发布的确认；持久化消息要等目标队列完成相应持久化，Quorum Queue 要等多数副本接受。`nack` 通常只在内部故障等少见情况出现。
2. **Confirm `ack` 不等于进了队列。** 没有匹配到队列的消息也可能收到 `ack`。设置 `mandatory=true` 并处理 Return，或配置 Alternate Exchange，才能发现或接住无法路由的消息。
3. 记录未确认消息，对超时、`nack` 做有限重试。AMQP 也有发布事务，但开销较高，通常使用 Confirm；它与 RocketMQ 的事务消息不是一回事。

### 2. Broker：持久化与副本

- **Classic Queue**：已入队消息要在重启后保留，关键是 Queue durable、Message persistent；Exchange durable 保证交换机本身在重启后仍存在。发布者还要等待 Confirm。
- **Quorum Queue**：队列持久化，并把消息复制到多数副本后确认；不要套用“Exchange、Queue、Message 三者缺一不可”。如果死信进入 Classic Queue，还要考虑目标队列的持久化。

### 3. 消费：手动 ACK + Prefetch

重要业务使用手动 ACK：**收到消息 → 业务提交成功 → ACK**。自动 ACK 在 Broker 把消息写入 TCP 套接字时就视为成功，应用尚未处理也可能丢消息。手动确认必须通过收到消息的同一 Channel 发送。

| 操作 | 作用 |
| --- | --- |
| `ack` | 确认处理成功；`multiple` 可批量确认 |
| `nack` | 拒绝消息，可批量处理，并指定是否重新入队 |
| `reject` | 拒绝单条消息，并指定是否重新入队 |

`basic.qos` 的 prefetch 限制一个 Consumer 已收到但尚未确认的消息数：`1` 较均衡但吞吐可能低；`0` 在协议层不限制；实际可从几十到几百试起，按消息大小和处理耗时调整。常用的 `global=false` 是**每个 Consumer** 的限制，不是整个 Channel 共享。Quorum Queue 不支持全局 QoS，并有单个 Consumer 的 prefetch 上限。

## 二、重复消费与幂等

RabbitMQ 没收到 ACK 就可能重新投递。例如业务已提交、ACK 却丢失，同一消息会再次到达。因此按**至少一次投递**设计消费者：

1. 首选数据库唯一约束、消费记录表或业务状态条件更新；让幂等判断和业务写入处于同一数据库事务。
2. Redis `SET NX EX` 可快速去重，但要处理“标记成功、业务失败”和“业务成功、标记丢失”，不宜单独承担强一致保证。

消息队列本身不能替业务完成端到端的“恰好一次”；目标是让重复投递只产生一次业务效果。

## 三、消息积压怎么排查

先看队列指标：

| 指标 | 含义 | 优先检查 |
| --- | --- | --- |
| Ready 多 | 尚未投递给 Consumer | 消费者是否在线、消费速率和下游瓶颈 |
| Unacked 多 | 已投递但未确认 | 业务阻塞、漏 ACK、prefetch 是否过大 |

先定位瓶颈，再扩容消费者；如果所有消费者都在等待同一个数据库，扩容可能让数据库更慢。普通 Queue 不适合长期存放海量事件，需要回放时可评估 RabbitMQ Stream 或 Kafka。

内存或磁盘资源告警会阻塞集群的发布连接，消费仍应继续。生产和消费宜分开连接，并处理 `connection.blocked` / `connection.unblocked`。内存水位默认值有版本差异：3.13 为 40%，4.3 为 60%，以实际配置为准。

## 四、死信与延迟消息

### 1. 死信

消息被 `nack` / `reject` 且 `requeue=false`、超过 TTL、因队列长度限制被淘汰，或 Quorum Queue 超过投递限制时，可能成为死信。RabbitMQ 4.0 起，Quorum Queue 的默认 `delivery-limit` 为 20。

**死信队列只是普通队列**：原队列配置 DLX 后，死信经 DLX 路由到目标队列。没有可用的 DLX 或目标队列，消息可能被丢弃。队列长度策略若是 `reject-publish`，则拒绝新消息，并非淘汰旧消息。死信队列要监控和告警，不能只存不处理。

### 2. 延迟投递

1. **TTL + DLX**：消息先进入没有消费者的延迟队列，过期后成为死信，再路由到业务队列。混用不同 TTL 可能遇到队头阻塞；固定延迟可按时长拆队列。
2. **延迟交换机插件**：通过 `x-delay` 指定延迟，但待投递消息保存在当前节点的 Mnesia 中，没有队列副本保障；社区插件在 4.3 时已弃用归档。

4.3 的 Quorum Queue delayed retry 用于消费失败后的延迟重投，不是通用定时投递。

## 五、顺序、优先级与重试

**顺序**：同一业务键路由到同一队列，由单个 Consumer 串行处理；也可用 Single Active Consumer 让多个实例待命。`prefetch > 1` 后的并发处理、失败重入队，都可能改变业务完成顺序。需要并行时按业务键分片；若只关心最终状态，可用版本号拒绝旧消息。

**优先级**：它解决先处理哪条消息，不保证业务保序。Classic Queue 使用 `x-max-priority`；Quorum Queue 在 4.0–4.2 只有两级相对优先级，4.3 起支持 0–31 共 32 级严格优先级，且不使用 `x-max-priority`。已投递的低优先级消息不会被撤回。

**重试**：不要无限 `nack(requeue=true)`，否则异常消息会立即反复投递。为可重试错误设置次数、间隔和最终死信去向，例如 **业务队列 → 分级延迟重试 → 死信队列 → 告警**。参数错误等不可重试问题直接进入死信处理。重试次数不能只保存在消费者内存中。

## 六、高可用

| 方案 | 适用情况 |
| --- | --- |
| 普通集群 | 共享元数据；Classic Queue 数据不会因为加入集群就自动复制 |
| Quorum Queue | 基于 Raft 复制消息；多数副本可用时才能继续服务，适合重要业务消息 |
| Classic Mirrored Queue | 3.x 历史方案，4.0 已删除，不作为现行选型 |

3 副本 Quorum Queue 可容忍 1 个副本不可用；只剩 1 个副本时无法继续服务。副本提高 Broker 故障下的数据安全性，但不能替代 Producer Confirm、Consumer ACK 和业务幂等。
