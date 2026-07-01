---
title: GMP2
weight: 1
date: 2026-05-13
draft: false
---

## 调度流程 +2

### 1. GMP 调度流程（主循环在干什么）

![](pic/GMP机制.调度主链冷启动.png)

{{< bilingual >}}
{{< en >}}

You can first remember the main flow as this chain:

`rt0_go -> schedinit -> newproc -> mstart -> schedule -> findRunnable -> execute`

In plain language, step by step:

1. **When the program starts**, it first enters `rt0_go` (the assembly/bootstrap entry point).
2. Then **`schedinit` sets up the scheduler, the number of Ps, memory, GC, and other runtime foundations**.
3. Next, **`newproc` creates the first goroutine to run (for example, `main`) and puts it into a queue**.
4. The current thread enters **`mstart`, which is like saying "I am starting work"**: from then on, it stays in the scheduling logic for a long time.
5. It enters the infinite **`schedule` loop**: each round first uses **`findRunnable` to find a runnable G**, then uses **`execute` to actually run it**. If that G can no longer continue (yield, block, preemption, syscall, etc.), execution returns to **`schedule`**, and the cycle repeats.

{{< /en >}}

{{< zh >}}
主流程可以先记这条链：

`rt0_go -> schedinit -> newproc -> mstart -> schedule -> findRunnable -> execute`

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

When you write `go f()`, the rough path is:

1. `newproc` runs on the user G, but uses `systemstack` to switch to the **g0 stack**, so complex scheduling logic does not run on the user stack.
2. In `newproc1`, `gfget` **tries to reuse** a G from the local P or global `gFree` list first; if none is available, it creates a new one. The state is set to `_Grunnable` (a few parked paths use `_Gwaiting`).
3. `runqput` puts the new G into the current P's queue, often preferring `runnext`.

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

1. First check **special runtime tasks**, such as the trace reader and GC workers. These are high-priority internal runtime jobs.
2. Then perform a **fairness check**. The scheduler does not check the global queue every time, but it does look at it periodically (for example, every certain number of ticks) to avoid letting local queues starve global tasks forever.
3. Next, check the local queue: internally, `runqget` checks `runnext` first, then the normal `runq`.
4. If the local queue has nothing, check the global run queue.
5. Then check netpoll: whether network events have just made some Gs runnable.
6. If there is still nothing, enter `stealWork` and try to "borrow/steal" work from other Ps. This usually happens when work is unevenly distributed.
7. If there is still no work: release the P, and the M enters spinning or sleeping, waiting to be woken later by `wakep` or another event.

**Why does the "global queue" appear twice in explanations?**
The first one is about **fairness**: preventing a P whose local queue always has work from starving Gs in the global queue. The second one is a **fallback after the earlier steps fail**: take another centralized look at the global queue.

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

Goroutines are lightweight mainly because:

1. The initial stack is small (KB-level), and it can grow or shrink dynamically.
2. Scheduling mostly happens in user space, reducing kernel context switches.
3. GMP makes task distribution more efficient: local-first, global fallback, and work stealing for balance.
4. Preemption prevents long-running tasks from occupying the CPU for too long.
5. The number of goroutines can be far higher than the number of threads, which fits high-concurrency models well.

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

1. P separates "queues and resources" from M. M can change, while P's local scheduling context remains.
2. Local-first scheduling reduces contention on the global lock.
3. Work stealing and load balancing become easier.

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

The number of Ps is usually the number of CPU cores, and it can be set with the `GOMAXPROCS` environment variable.

When a Go program starts, it sets the maximum number of Ms to 10000 by default. In practice, the kernel usually cannot support that many threads, so this limit can mostly be ignored.
The number of Ms is not fixed. The runtime creates and recycles them as needed:

1. **The upper bound of parallelism mainly depends on P (`GOMAXPROCS`)**.
2. **There can be more Ms than Ps, but an M must bind to a P before it can run a user G**.

{{< /en >}}

{{< zh >}}
P的数量通常是机器CPU核数，可以通过环境变量`GOMAXPROCS`设置。

go 程序启动时，会设置 M 的最大数量，默认 10000. 但是内核很难支持这么多的线程数，所以这个限制可以忽略。
M 的数量不固定，runtime 会按需创建/回收：
1. **并行度上限主要看 P（`GOMAXPROCS`）**。  
2. **M 可以多于 P，但跑用户 G 时 M 必须先绑定 P**。
{{< /zh >}}
{{< /bilingual >}}
