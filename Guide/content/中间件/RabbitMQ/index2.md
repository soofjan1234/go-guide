---
title: 进阶
weight: 2
date: 2026-08-09
draft: false
---

# RabbitMQ 进阶

## 一、如何保证消息可靠

沿着 **Producer → RabbitMQ → Consumer** 看三段链路，分别处理发布失败、Broker 故障和消费失败。

### 1. 发布：Confirm + 路由检查

1. 开启 Publisher Confirm。`ack` 表示 Broker 完成这次发布的确认；持久化消息要等目标队列完成相应持久化，Quorum Queue 要等多数副本接受。`nack` 通常只在内部故障等少见情况出现。
2. 设置 mandatory=true。Confirm `ack` 不等于进了队列。没有匹配到队列的消息也可能收到 `ack`。设置 `mandatory=true` 并处理 Return，或配置 Alternate Exchange，才能发现或接住无法路由的消息。

### 2. Broker：持久化与副本

- **Classic Queue**：已入队消息要在重启后保留，关键是 Queue durable、Message persistent；Exchange durable 保证交换机本身在重启后仍存在。发布者还要等待 Confirm。
- **Quorum Queue**：队列持久化，并把消息复制到多数副本后确认；不要套用“Exchange、Queue、Message 三者缺一不可”。如果死信进入 Classic Queue，还要考虑目标队列的持久化。

### 3. 消费：手动 ACK + Prefetch

重要业务使用手动 ACK：**收到消息 → 业务提交成功 → ACK**。自动 ACK 在 Broker 把消息写入 TCP 套接字时就视为成功，应用尚未处理也可能丢消息。

| 操作 | 作用 |
| --- | --- |
| `ack` | 确认处理成功；`multiple` 可批量确认 |
| `nack` | 拒绝消息，可批量处理，并指定是否重新入队 |
| `reject` | 拒绝单条消息，并指定是否重新入队 |


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


## 四、死信与延迟消息

### 1. 死信

消息被 `nack` / `reject` 且 `requeue=false`、超过 TTL、因队列长度限制被淘汰，或 Quorum Queue 超过投递限制时，可能成为死信。

**死信队列只是普通队列**：原队列配置 DLX 后，死信经 DLX 路由到目标队列。没有可用的 DLX 或目标队列，消息可能被丢弃。队列长度策略若是 `reject-publish`，则拒绝新消息，并非淘汰旧消息。死信队列要监控和告警，不能只存不处理。

### 2. 延迟投递

1. **TTL + DLX**：消息先进入没有消费者的延迟队列，过期后成为死信，再路由到业务队列。混用不同 TTL 可能遇到队头阻塞；固定延迟可按时长拆队列。
2. **延迟交换机插件**：通过 `x-delay` 指定延迟，但待投递消息保存在当前节点的 Mnesia 中，没有队列副本保障；社区插件在 4.3 时已弃用归档。


## 五、顺序

1. **单队列 + 单消费者**：最简单的顺序保证，吞吐受限于单消费者。
2. **多队列 + 多消费者**：按业务分片，保证同一分片的消息顺序；不同分片间不保证顺序。可用 `consistent-hash` 或自定义路由键。
3. **Single Active Consumer (SAC)**：既保证单消费者消费以避免乱序，又避免单消费者挂了导致整个系统瘫痪

## 六、高可用

| 方案 | 适用情况 |
| --- | --- |
| 普通集群 | 共享元数据；Classic Queue 数据不会因为加入集群就自动复制 |
| Quorum Queue | 基于 Raft 复制消息；多数副本可用时才能继续服务，适合重要业务消息 |
| Classic Mirrored Queue | 3.x 历史方案，4.0 已删除，不作为现行选型 |

3 副本 Quorum Queue 可容忍 1 个副本不可用；只剩 1 个副本时无法继续服务。副本提高 Broker 故障下的数据安全性，但不能替代 Producer Confirm、Consumer ACK 和业务幂等。
