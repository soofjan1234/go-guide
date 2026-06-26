---
title: GMP2
weight: 1
date: 2026-05-13
draft: false
---

## 调度流程 +2

### 1. GMP 调度流程（主循环在干什么）

{{< bilingual >}}
{{< en >}}

{{< /en >}}

{{< zh >}}
主流程可以先记这条链：

`rt0_go -> schedinit -> newproc -> mstart -> schedule -> findRunnable -> execute`

![](pic/GMP机制.调度主链冷启动.png)

用大白话按顺序过一遍：

1. **程序刚起来**先进 `rt0_go`（入口汇编/引导）。
2. 接着 **`schedinit` 把调度器、P 的数量、内存/GC 等「场子」铺好**。
3. 再用 **`newproc` 捏出第一个要跑的 goroutine（比如 main）并塞进队列**。
4. 当前线程 **`mstart`，相当于「我开始上班」**：此后长期在调度逻辑里转。
5. 进入 **`schedule` 这个无限循环**：每一圈先 **`findRunnable` 找一个能干活的 G**，找到了就 **`execute` 真正去跑它**。跑不下去（让出、阻塞、被抢占、syscall 等）又会回到 **`schedule`**，周而复始。
{{< /zh >}}
{{< /bilingual >}}

### 2. 创建G的流程

{{< bilingual >}}
{{< en >}}

{{< /en >}}

{{< zh >}}
当你写下 `go f()`，大致会走这条路：

1. `newproc` 在用户 G 上用 `systemstack` 切到 **g0 栈**，避免在用户栈上做复杂调度逻辑。
2. `newproc1` 里通过 `gfget` **优先复用** P 本地 / 全局 `gFree` 中的 G，不够再新建；把状态设为 `_Grunnable`（少数 parked 路径为 `_Gwaiting`）。
3. `runqput` 把新 G 放进当前 P 的队列（常优先 `runnext`）
{{< /zh >}}
{{< /bilingual >}}

## 查找g的流程 +2

![](pic/GMP机制.findRunnable找G顺序.png)

{{< bilingual >}}
{{< en >}}

{{< /en >}}

{{< zh >}}
1. 先看**特殊任务**：比如 trace reader、GC worker（这些是运行时的高优先级内部活）。
2. 然后做一次**公平性检查**：不是每次都看全局队列，但会按节拍（如每隔一段 tick）看一眼，避免本地队列长期“自嗨”把全局任务饿死。
3. 接着看本地队列：`runqget` 内部先看 `runnext`，再看普通 `runq`。
4. 本地没有，再看全局 runq。
5. 再看 netpoll：有没有网络事件刚好把某些 G 变成可运行。
6. 还没有，就进入 stealWork，去别的 P 试着“借/偷”任务（通常是忙闲不均时触发）。
7. 仍然没活：让出 P，M 进入自旋或休眠，等后续 `wakep`/事件唤醒。

**为何「全局队列」会在叙述里出现两次？** 
前者是 **公平性**：避免某个 P 本地一直有活、全局里的 G 长期饿死；后者是 **前面几步都落空后的兜底**：集中从全局再取一轮。
{{< /zh >}}
{{< /bilingual >}}

## g的优点 +1

{{< bilingual >}}
{{< en >}}

{{< /en >}}

{{< zh >}}
goroutine 轻量主要来自：

1. 初始栈小（KB 级），并且可动态增长/收缩。
2. 主要在用户态调度，减少内核切换。
3. GMP 让任务分发更高效（本地优先 + 全局兜底 + 窃取均衡）。
4. 抢占机制避免长任务长期霸占 CPU。
5. 数量上可以远高于线程，适合高并发模型。
{{< /zh >}}
{{< /bilingual >}}

## 为什么 P 重要？ +1

{{< bilingual >}}
{{< en >}}

{{< /en >}}

{{< zh >}}
1. 把“队列和资源”从 M 身上分离出来，M 可以换，P 的本地上下文还在。
2. 本地优先，降低全局锁竞争。
3. 更容易做工作窃取和负载均衡。
{{< /zh >}}
{{< /bilingual >}}

## P、M的数量 +1

{{< bilingual >}}
{{< en >}}

{{< /en >}}

{{< zh >}}
P的数量通常是机器CPU核数，可以通过环境变量`GOMAXPROCS`设置。

go 程序启动时，会设置 M 的最大数量，默认 10000. 但是内核很难支持这么多的线程数，所以这个限制可以忽略。
M 的数量不固定，runtime 会按需创建/回收：
1. **并行度上限主要看 P（`GOMAXPROCS`）**。  
2. **M 可以多于 P，但跑用户 G 时 M 必须先绑定 P**。
{{< /zh >}}
{{< /bilingual >}}
