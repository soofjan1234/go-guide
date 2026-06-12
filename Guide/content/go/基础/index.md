---
title: 基础
weight: 9
date: 2026-05-25
draft: false
---

## 与 C++、Java 区别 +2

1. Go语言简洁，相对与其他语言好上手
2. Go没有继承，用的是组合
3. Go、Java自动垃圾回收；C++需手动
4. Go编译快，Java需要JVM启动慢，C++性能快
5. Go支持协程，并发性更好；Java是Thread和Runnable

## 优点 +1

参考上文

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


