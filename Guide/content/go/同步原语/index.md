---
title: 同步原语
weight: 14
date: 2026-05-25
draft: false
---

## WaitGroup +1

![同步原语.WaitGroup](pic/同步原语.WaitGroup.png)

sync.WaitGroup 只有三个方法：

1. Add(delta int)：把计数器加上 delta。通常用来设定要等待的协程数量。
2. Done()：把计数器减 1。相当于 Add(-1)。通常在子协程结束时（利用 defer）调用。
3. Wait()：阻塞当前协程，直到计数器变成 0。
