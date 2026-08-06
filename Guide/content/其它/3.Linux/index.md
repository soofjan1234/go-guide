---
title: Linux
weight: 30
date: 2026-05-27
draft: false
---

## 进程、协程、线程对比 +3

1. 进程资源分配的最小单位；线程是CPU调度的最小单位；协程是轻量级线程
2. 协程是用户态的，切换开销最小，适合 I/O 密集高并发；其他两个需要系统调用，切换开销较大
3. 进程资源隔离；线程共享进程地址空间等资源；协程共享进程内存，由 runtime 映射到 OS 线程（M:N）

## 进程通信 +1

1. 管道、匿名管道
2. 信号、信号量
3. 共享内存
4. 消息队列
5. 套接字

## 权限模型 (rwx / 755) +1

- **权限位**：`r` (读/4), `w` (写/2), `x` (执行/1)。
- **三组身份**：所有者 (Owner) / 所属组 (Group) / 其他人 (Others)。
- **常见权限**：
  - `755` (`rwxr-xr-x`)：所有者全权，其他人可读可执行。
  - `644` (`rw-r--r--`)：普通文件标准权限。
  - `600` (`rw-------`)：私钥文件常用权限。

## 脚本第一行（Shebang）作用 +1

告诉系统用哪个解释器执行脚本。
- `#!/bin/bash`：路径固定，如果 bash 不在 `/bin` 下会报错。
- `#!/usr/bin/env bash`：更便携，会从当前用户的 `PATH` 中查找 bash。

## top

上半部分是系统整体状态，下半部分是进程列表。

```txt
Tasks: 301 total,   1 running, 300 sleeping,   0 stopped,   0 zombie
  Mem:  3979024K total,  3757200K used,   221824K free,   183996K buffers
 Swap:  4086656K total,     1024K used,  4085632K free,  2319180K cached
400%cpu  48%user   0%nice  22%sys 323%idle   0%iow   5%irq   2%sirq   0%host

  PID USER         PR  NI VIRT  RES  SHR S[%CPU] %MEM     TIME+ ARGS      
 1569 root         20   0 1.2G  27M  14M S  3.0   0.6  12:07.98 LincStorageMGMT
30608 root         20   0  10G 5.5M 4.3M R  2.0   0.1   0:00.18 top
```

1. 内存
  - mem和swap下面会讲到
2. cpu
  - user (User)：用户程序占用的 CPU。如果太高，说明你的代码在死循环或进行重度计算。
  - sys (System)：内核占用的 CPU。如果太高，说明系统调用太频繁（如频繁的线程上下文切换）。
  - iow (I/O Wait)：重要！CPU 在等待磁盘读写。如果变高，说明磁盘是瓶颈。

## vmstat

```txt
procs ------------memory------------ ----swap--- -----io---- ---system-- ----cpu----
 r  b    swpd    free   buff   cache    si    so    bi    bo    in    cs us sy id wa
 2  0     512   41492 122524 2611056     0     1  1592   417     1  1858  7  9 82  2
 0  0     512   41492 122524 2611056     0     0     0     0     1  3188  1  4 95  0
```

和top的区别：
1. vmstat只看全局指标，而top能定位到具体的进程
2. vmstat是像打日志一样，top的交互式，占用终端
3. vmstat可以看出 CPU 占用或 I/O 是在上升还是下降。

## 内存

通过 free -h 命令查看

```text
              total        used        free      shared  buff/cache   available
Mem:           15Gi       8.0Gi       1.5Gi       500Mi       5.5Gi       6.5Gi
Swap:         2.0Gi       1.0Gi       1.0Gi
```

1. total：总内存
2. free：完全空闲内存。
  - 为了让系统运行更快，操作系统会把暂时不用的空闲内存拿去当缓存（就是后面的 buff/cache），用来加速读取硬盘数据
3. buff/cache：缓存/缓冲
  - 这部分内存虽然目前被占用了，但它是“临时占用”。如果有新的应用程序需要内存，操作系统会瞬间释放这部分缓存，给新程序
4. available：真正可用的内存
  - 当启动一个新程序时，系统真正能调用的最大内存。
  - 计算公式大致为： available ≈ free + 大部分的 buff/cache
5. used：已用内存

对于swap（虚拟内存）是硬盘上的一块区域。当物理内存（RAM）实在不够用时，操作系统会把内存里暂时不常用的数据“丢”到硬盘的 Swap 空间里，把珍贵的物理内存腾出来给急需运行的程序
1. used（已用大小）：
  - 如果 Swap 的 used 等于 0 或者非常小：说明物理内存够用，系统运行在极速状态。
  - 如果 Swap 的 used 很大，且持续增长：说明物理内存（RAM）严重不足。
2. SI/SO (Swap In / Swap Out，即换入换出频率)：
  - 更关键的指标！
  - 由于硬盘的速度比物理内存慢成百上千倍，如果系统在频繁地把数据从内存往 Swap 移（Swap Out），又从 Swap 读回内存（Swap In），这叫“内存抖动”（Thrashing）。
  - 现象： 此时你的电脑/服务器会极度卡顿，CPU 占用率可能飙升（都在处理换入换出），硬盘读写灯狂闪。

其实，free 和 top 的数据都是从 Linux 的 /proc 虚拟文件系统里读出来的：cat /proc/meminfo