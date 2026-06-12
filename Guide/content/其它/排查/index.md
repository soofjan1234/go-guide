---
title: 排查
weight: 8
date: 2026-06-12
draft: false
---

# 线上出问题：通用排查流程

首先看现象是什么问题

## 功能不正常

直接查看代码逻辑是否有漏洞

## CPU高

先分清「真 CPU 忙」还是「假高负载」，Load 高但 CPU 低，多半是IO等待、锁的状态

1. top命令看是业务进程还是别的
2. go服务去看pprof接口看书哪个函数占用高
3. 无限循环、计算密集、并发过大

## 内存高

free -h：看 available，Linux 会用 cache，used 高不一定有问题

1. top+pprof, 看 inuse_space / inuse_objects：谁分配最多
2. 配合 runtime.ReadMemStats 打点
3. 缓存无上限、goroutine 泄漏、大对象一次读入

## 数据库慢

慢查询日志，是否持续出现

1. 看Explain命令是否走索引
2. 未走则添加，走了则看是否正确，是否徽标太多
3. 是否有锁
4. 一些常见的优化手段
