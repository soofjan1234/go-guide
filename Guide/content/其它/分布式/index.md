---
title: 分布式
weight: 6
date: 2026-06-06
draft: false
---
## 分布式锁的实现 +3

![](pic/分布式锁.png)

1. Redis的SET NX EX
	- 性能高
	- 注意锁过期、误删问题
2. MySQL的唯一索引
	- 实现简单
	- 并发性低
3. etcd、ZooKeeper
	- 复杂
	- 强一致性