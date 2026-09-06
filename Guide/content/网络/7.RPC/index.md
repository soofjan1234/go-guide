---
title: RPC
weight: 70
date: 2026-05-27
draft: false
---

## 什么是RPC

RPC（Remote Procedure Call，远程过程调用）是一种计算机通信协议。它的核心思想是：让调用远程计算机（服务）上的函数，就像调用本地代码中的函数一样简单、透明。

## RPC vs HTTP/RESTful 对比

1. 核心理念：HTTP 面向资源（URL + HTTP 动词）；RPC 面向动作/函数
2. 传输协议：HTTP 通常是 HTTP/1.1（文本协议）；RPC 通常基于 HTTP/2 或 TCP 自定义长连接 
3. 数据序列化：HTTP 通常是 JSON / XML（文本，可读性好但体积大、解析慢）；PRC 通常是 Protobuf / Thrift（二进制，体积极小、解析极快） 
4. 契约约束：HTTP 弱约束（靠 Swagger/OpenAPI 文档，容易失效）；PRC 强约束（基于 `.proto` 或 IDL 文件强类型编译） 
5. 性能/吞吐：HTTP 较慢，Header 冗余，内存分配多；PRC 极高，适合微服务内部高频通信 

### Protobuf + gRPC  vs  HTTP + JSON

.proto + gRPC 往往更合适：
- 字段和类型固定，改接口时更容易发现双方不兼容。
- 自动生成 Go/C++ 等客户端代码，少手写请求和响应解析。
- 二进制编码通常更小、更快。
- 原生支持 deadline、取消、流式调用和标准状态码。
- 很适合 Unix Domain Socket 的本机进程通信。

但 HTTP + JSON 也有明显优势：
- 浏览器、脚本、curl 都能直接调用和调试。
- 对外开放 API 更通用，文档和排障门槛低。
- 数据结构经常变化、调用方语言杂时更灵活。

## RPC 的核心工作流程

你写业务时调的是本地函数，真正发出去的是 Stub：

1. Client Stub：方法名 + 参数 → 序列化 → 丢给网络
2. Server Stub：字节流 → 反序列化 → 调本地真正的实现
3. 结果原路回来，Client Stub 拆成 resp 给你

## RPC 框架的核心四大组件

现代工业级的 RPC 框架（如 gRPC、Dubbo、Kitex）不仅仅是简单的“网络+序列化”，它通常包含以下四大核心能力：

 ① IDL（Interface Definition Language，接口定义语言）

- 为了让客户端和服务端对“函数签名和数据结构”达成一致，使用独立的 IDL 文件进行跨语言定义。
- 最经典代表：Protocol Buffers（`.proto`）。编写一次 `.proto`，即可自动生成 Go、Java、Python、C++ 的 Stub 代码。

 ② 序列化/反序列化 (Serialization / Deserialization)

- 将内存对象转换为可跨网络传输的字节流。
- 衡量指标：序列化后的体积大小（影响带宽）、CPU 消耗与内存分配（影响 QPS）。
- 常见选择：Protobuf、Thrift、Hessian、MessagePack（JSON/Gob 在高性能场景较少使用）。

 ③ 网络传输与协议 (Transport Protocol)

- 自定义 TCP 协议：（如 Dubbo、早期 RPC）协议头定义极简，解析极快。
- HTTP/2 协议：（如 gRPC）利用 HTTP/2 的多路复用（Multiplexing）、多流传输（Streaming）以及 Header 压缩（HPACK），天然支持双向流式通信（Bidirectional Streaming）。

 ④ 服务治理 (Service Governance) —— 生产级 RPC 的关键

单个 RPC 只是点对点通信，而在微服务集群中，RPC 框架必须结合治理能力：

- 服务注册与发现（Registry）：客户端通过 Consul / Etcd / Nacos 动态感知服务端的 IP 列表。
- 负载均衡（Load Balancing）：客户端本地进行 Round-Robin、随机、加权或最小连接数轮询。
- 熔断限流与降级（Circuit Breaker / Rate Limiting）：防止单点故障引发雪崩。
- 链路追踪与可观测性（Tracing）：注入 `TraceID` / `SpanID`，打通 OpenTelemetry / Jaeger 链路。

## 为什么不适用HTTP/3 

HTTP/3 (QUIC) 的核心卖点主要针对复杂的公网弱网环境（移动互联网），一旦放进数据中心内网，这些优势瞬间变得毫无意义：

| HTTP/3 (QUIC) 的王牌优势| 在公网（客户端 ↔ 服务器）表现| 在数据中心机房内（微服务 ↔ 微服务）表现
| --- | --- | --- |
| 解决丢包导致的队头阻塞| 4G/5G/弱 Wi-Fi 丢包率高达 1%~5%，QUIC 优势极大。| 毫无意义。机房内全是高规格光纤、局域网，丢包率几乎为 0。TCP 在内网基本不会触发队头阻塞。
| 0-RTT / 快速建连| 移动端延迟几十到几百毫秒，省一次握手省下几百毫秒。| 毫无意义。微服务之间全都是长连接池（Connection Pool），服务启动后几年都不断开，建连开销被摊薄为 0。
| 连接迁移（Wi-Fi 切 5G）| 手机走在路上 IP 随时变，不断连体验极好。| 毫无意义。机房服务器的 IP 全是静态固定的，永远不会到处乱跑。