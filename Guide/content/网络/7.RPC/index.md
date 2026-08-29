---
title: RPC
weight: 70
date: 2026-05-27
draft: false
---
**RPC（Remote Procedure Call，远程过程调用）** 是一种计算机通信协议。它的核心思想是：**让调用远程计算机（服务）上的函数，就像调用本地代码中的函数一样简单、透明。**

对于 Go 后端工程师来说，RPC 是构建微服务架构、分布式系统以及高效服务间通信（如 gRPC）的基础底座。

---

### 1. 为什么需要 RPC？（RPC vs HTTP/RESTful）

在单体应用时代，模块间的调用都是**本地函数调用**（比如 `orderService.GetOrder(id)`），直接走内存和 CPU 寄存器，速度在纳秒/微秒级。

当系统演变为微服务架构后，`OrderService` 和 `UserService` 被拆分部署在不同的服务器上。如果使用传统的 HTTP/RESTful 协议通信：

* 需要手动拼接 URL、处理 Query/Body。
* 需要处理 JSON 序列化与反序列化。
* 需要解析 HTTP 状态码、Header 等重型文本协议。

**RPC 的出现就是为了抹平这个网络差异**。它通过封装底层的网络传输、序列化和协议解析，让程序员在代码层面上**感知不到网络的存在**。

#### RPC vs HTTP/RESTful 对比

| 维度 | 传统 HTTP / RESTful | RPC (以 gRPC / Protobuf 为例) |
| --- | --- | --- |
| **核心理念** | 面向资源（URL + HTTP 动词） | 面向动作/函数（直接调用 `Service.Method`） |
| **传输协议** | 通常是 HTTP/1.1（文本协议） | 通常基于 **HTTP/2 或 TCP 自定义长连接** |
| **数据序列化** | 通常是 **JSON / XML**（文本，可读性好但体积大、解析慢） | 通常是 **Protobuf / Thrift**（二进制，体积极小、解析极快） |
| **契约约束** | 弱约束（靠 Swagger/OpenAPI 文档，容易失效） | 强约束（基于 `.proto` 或 IDL 文件强类型编译） |
| **性能/吞吐** | 较慢，Header 冗余，内存分配多 | **极高**，适合微服务内部高频通信 |

---

### 2. RPC 的核心工作流程（透明调用的秘密）

RPC 能做到“像调用本地函数一样”，底层靠的是 **Stub（存根/代理）** 机制。整个过程可以拆解为经典的 **8 个步骤**：

1. **Client（调用方）：** 像调用本地方法一样，发起对 `Client Stub` 的函数调用：`GetUserInfo(req)`。
2. **Client Stub（客户端存根）：** 将调用的方法名、参数打包，并调用**序列化器**将数据转为二进制字节流（如 Protobuf/JSON）。
3. **Network Transport（网络传输）：** 客户端网络库通过 TCP/HTTP2 长连接将二进制数据包发送给目标服务器。
4. **Server Transport（服务端网络层）：** 服务端网卡接收到数据包，递交给 `Server Stub`。
5. **Server Stub（服务端存根）：** 拿到二进制字节流，进行**反序列化**，还原出原始的方法名和参数结构体。
6. **Local Call（本地服务执行）：** `Server Stub` 根据方法名，调用服务端本地真正实现的 `UserService.GetUserInfo()` 函数。
7. **Return Response（返回结果）：** 本地函数执行完毕，结果按照相反的路径（**本地返回 $\rightarrow$ 序列化 $\rightarrow$ 网络传输 $\rightarrow$ 反序列化**）送回 Client。
8. **Client 拿到结果：** `Client Stub` 解包出最终的 `resp` 结构体，`GetUserInfo` 函数返回，完成一次调用。

---

### 3. RPC 框架的核心四大组件

现代工业级的 RPC 框架（如 **gRPC、Dubbo、Kitex**）不仅仅是简单的“网络+序列化”，它通常包含以下四大核心能力：

#### ① IDL（Interface Definition Language，接口定义语言）

* 为了让客户端和服务端对“函数签名和数据结构”达成一致，使用独立的 IDL 文件进行跨语言定义。
* **最经典代表：Protocol Buffers (`.proto`)**。编写一次 `.proto`，即可自动生成 Go、Java、Python、C++ 的 Stub 代码。

#### ② 序列化/反序列化 (Serialization / Deserialization)

* 将内存对象转换为可跨网络传输的字节流。
* **衡量指标：** 序列化后的**体积大小**（影响带宽）、 CPU 消耗与内存分配（影响 QPS）。
* **常见选择：** Protobuf, Thrift, Hessian, MessagePack (JSON/Gob 在高性能场景较少使用)。

#### ③ 网络传输与协议 (Transport Protocol)

* **自定义 TCP 协议：** (如 Dubbo, 早期 RPC) 协议头定义极简，解析极快。
* **HTTP/2 协议：** (如 **gRPC**) 利用 HTTP/2 的**多路复用（Multiplexing）**、多流传输（Streaming）以及 Header 压缩（HPACK），天然支持双向流式通信（Bidirectional Streaming）。

#### ④ 服务治理 (Service Governance) —— 生产级 RPC 的关键

单个 RPC 只是点对点通信，而在微服务集群中，RPC 框架必须结合治理能力：

* **服务注册与发现（Registry）：** 客户端通过 Consul / Etcd / Nacos 动态感知服务端的 IP 列表。
* **负载均衡（Load Balancing）：** 客户端本地进行 Round-Robin、随机、加权或最小连接数轮询。
* **熔断限流与降级（Circuit Breaker / Rate Limiting）：** 防止单点故障引发雪崩。
* **链路追踪与可观测性（Tracing）：** 注入 `TraceID` / `SpanID`，打通 OpenTelemetry / Jaeger 链路。

---

### 4. Go 生态中的主流 RPC 方案

在 Go 语言中，主要有以下几种选择：

1. **Go 标准库 `net/rpc`：**
* Go 自带的极简 RPC 实现，基于 Go 特有的 `gob` 编码或 `json-rpc`。
* **缺点：** 不支持跨语言、功能过于简陋，无服务治理，**生产环境基本不用**。


2. **gRPC-Go（事实上的行业标准）：**
* Google 开源，基于 **Protobuf + HTTP/2**。
* **优势：** 跨语言能力极强、性能高、生态极其繁荣、原生支持 Streaming。
* **适用：** 绝大多数企业微服务通信、云原生生态（Kubernetes/Envoy 原生支持）。


3. **Kitex (字节跳动开源) / TarS (腾讯开源)：**
* 针对高并发场景优化的高性能 Go RPC 框架。
* **优势：** 极致优化了 Go 运行时内存分配（结合 Netpoll 自研网络库），内部深度集成了字节/腾讯的服务治理能力。



---

### 5. 总结：面试提炼

> **问：什么是 RPC？它的底层原理是什么？**
> **答：**
> 1. **定义：** RPC（远程过程调用）是一种让客户端像调用本地函数一样调用远程服务器服务的通信协议，核心目标是**屏蔽网络传输与序列化的复杂细节**。
> 2. **原理：** 依赖 **Stub（代理）机制**。客户端调用 Stub，Stub 将参数**序列化**为二进制，通过 **TCP/HTTP2 长连接**传输到服务端。服务端 Stub 接收后进行**反序列化**，调用本地服务逻辑并将结果按原路返回。
> 3. **与 HTTP/JSON 相比：** RPC 通常基于 **Protobuf + 强类型契约**，数据体积更小、解析更快，且通常基于 HTTP/2 或 TCP 自定义长连接，吞吐量和性能远高于传统 RESTful API，因此是微服务内部通信的首选。
> 
>