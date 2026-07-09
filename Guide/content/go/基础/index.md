---
title: 基础
weight: 9
date: 2026-05-25
draft: false
---

## go优点/与 C++、Java 区别 +2

1. Go语言简洁，相对与其他语言好上手
2. Go没有继承，用的是组合
3. Go、Java自动垃圾回收；C++需手动
4. Go编译快，Java需要JVM启动慢，C++性能快
5. Go支持协程，并发性更好；Java是Thread和Runnable

## 协程使用场景 +1

1. 后台任务
    - 定时、周期性的任务
    - 探测与保活
2. 生产者和消费者
3. 并行计算的任务
4. I/O 并发
    - HTTP/RPC 服务端：每个请求一个 goroutine
    - 批量 IO：并发读多个文件、多条 DB/Redis 查询
5. 带超时、可取消的长操作

## 一个包里边有多个 init，初始化顺序是 +1

1. 同一文件内，是从上到下
2. 同一包不同文件内，是文件名ascii字典序

## API 版本化 +1

多端并行使用、要做不兼容改动时，常见三种放法：

1. URL Path：/api/v1、/api/v2
    - 直观，调试、文档、日志、网关路由都好做
    - Gin 里用路由组拆开：V1/V2 各一套 handler
    - 缺点：URL 变了，缓存和监控要按版本隔离
    - 最常见
2. Header：Api-Version: 2  
    - URL 不变，资源路径稳定
    - 需在中间件或网关按 header 分流（if/switch 或转发到不同 handler）
    - 缺点：不直观，curl/浏览器不好测
    - 想保持 URL 干净、B 端 SDK 只改配置不改路径、有 API Gateway 统一路由
3. Media Type（内容协商）：Accept: application/vnd.mycompany.user.v2+json
    - 符合 HTTP 内容协商，REST 规范性强
    - 缺点：实现和联调成本最高
    - 对外公开 API、规范要求严、同一资源多种表示

## 代码变程序会经历哪些步骤

![](pic/编译.png)

1. 编译器先解析 `.go` 源码，检查语法、类型、包依赖是否正确。

2. 然后生成中间表示，做一些逃逸分析、内联、死代码消除等优化。

3. 再把中间表示转成目标平台的汇编和机器码。

4. 最后链接 runtime、标准库、第三方包和自己的代码，生成最终可执行文件。