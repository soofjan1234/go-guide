---
title: Go GMP 调度机制教学视频 Hyperframe 制作稿
source: ../index.md
target_duration: 7-8 min
aspect_ratio: 16:9
language: zh-CN
style: 技术教学 / 白板动画 / 轻量代码感
---

# Hyperframe Prompt

请基于下面的分镜制作一条中文技术教学视频，主题是「Go GMP 调度机制」。

整体风格：
- 画面干净，偏白板动画和技术图解，不要营销感。
- 重点用运动关系解释概念：G 是任务，M 是工人/线程，P 是工位与资源包，schedt 是总控室。
- 每个概念出现时，用简短大字标题 + 图示局部放大 + 口播解释。
- 尽量复用素材图，不要把整篇文章全文贴到画面上。
- 字幕使用中文，最多两行，每行不超过 18 个字。
- 关键术语保留英文：G、M、P、schedt、g0、runq、netpoll、syscall、asyncPreempt。

素材：
- `../pic/GMP机制.GMP关系总览.png`
- `../pic/GMP.工作窃取机制图.png`
- `../pic/GMP.协作式抢占机制.png`
- `../pic/GMP.信号式抢占机制.png`
- `../pic/GMP机制.普通阻塞.png`
- `../pic/GMP机制.网络阻塞.png`
- `../pic/GMP机制.系统调用阻塞.png`

# 视频结构

## 0. 开场：一句话理解 GMP

时长：0:00-0:35

画面：
- 显示标题「Go GMP 调度机制」。
- 背景放 `GMP机制.GMP关系总览.png`，轻微虚化后依次高亮 G、M、P、schedt。
- 屏幕中央出现一句话：`M 是工人，G 是任务，P 是工位与资源包，schedt 是总控室。`

口播：
> 这期我们用一个最小模型理解 Go 的 GMP 调度。你先记一句话：M 是工人，G 是任务，P 是工位和资源包，schedt 是全局总控室。后面所有调度、抢占、阻塞和唤醒，其实都围绕这四个角色展开。

字幕重点：
- `GMP = G + M + P + schedt`
- `M 跑 G，必须先绑定 P`

## 1. G：可挂起、可恢复、可迁移的任务

时长：0:35-1:20

画面：
- 用一个 `go func(){...}` 代码块生成一个 G。
- G 卡片上拆出两层信息：执行现场、调度状态。
- 状态条依次切换：runnable、running、waiting、syscall。

口播：
> G，也就是 goroutine，不只是一个函数调用。对 runtime 来说，它是一份可以被调度的执行快照。里面有栈、PC、SP 这些执行现场，也有当前状态：可运行、运行中、等待中，或者正在系统调用里。因为 G 带着这些信息，所以它可以被挂起、恢复，甚至被换到另一个 M 上继续执行。

字幕重点：
- `G = 可调度的执行单元`
- `保存现场，才能切走再切回`

## 2. M：真正跑在 CPU 上的线程

时长：1:20-2:05

画面：
- M 以 OS thread 的形态出现，手里拿到一个 G 并放到 CPU 上运行。
- 展示 M 内部：`g0`、`curg`、`p`。
- `g0` 单独以后台工作台形式出现。

口播：
> M 是真正干活的操作系统线程。一个 M 当前跑哪个业务 goroutine，会记录在 curg 里。但调度器自己的工作，比如切换、调度、进入 mcall，通常不在业务 G 的栈上做，而是在 g0 这条专用调度栈上完成。你可以把 g0 理解成后台工作台：runtime 在这里整理现场，然后再把 CPU 交给下一个 G。

字幕重点：
- `M = OS thread`
- `g0 = 调度专用栈`

## 3. P：被低估的资源包

时长：2:05-2:55

画面：
- P 展开成一个资源包：`runnext`、`runq[256]`、`mcache`、`gFree`、`pcache`。
- 重点突出本地队列：G 先进入 `runnext` 或 `runq`。
- M 没有 P 时变灰，绑定 P 后才亮起。

口播：
> P 经常被误解成 CPU，但它更像运行 goroutine 需要的一包 runtime 资源。最关键的是本地运行队列：runnext 是下一跳优先位，runq 是普通本地队列，固定 256 个槽位，多数访问可以无锁。M 必须先绑定到 P，才有资格执行用户 G。没有 P 的 M，就像工人没有工位，不能开工。

字幕重点：
- `P = 资源包，不是物理 CPU`
- `本地队列优先`

## 4. 调度主线：本地优先，全局兜底，窃取均衡

时长：2:55-3:55

画面：
- 使用 `GMP.工作窃取机制图.png`。
- 动画步骤：M 绑定 P -> 查本地 runq -> 查全局队列 -> 从别的 P 偷一半任务。
- schedt 作为总控室出现，显示全局 runnable 队列和 idle M/P 列表。

口播：
> 把三者连起来看：M 要跑 G，必须先拿到 P。拿到 P 后，它优先从这个 P 的本地队列找任务。本地没有，就去全局队列找；还没有，就去别的 P 那里偷一部分 G 过来。这样做有两个好处：大多数调度都在本地完成，减少锁竞争；当某个 P 太忙时，又能通过 work stealing 把压力摊开。

字幕重点：
- `local first`
- `global fallback`
- `work stealing`

## 5. 抢占：防止一个 G 独占 CPU

时长：3:55-5:10

画面：
- 先展示 `GMP.协作式抢占机制.png`。
- 时间轴：G1 运行超过 10ms -> 标记 stackPreempt -> 下次函数调用 -> goschedImpl。
- 再切换到 `GMP.信号式抢占机制.png`。
- 动画：sysmon -> SIGURG -> sighandler -> 注入 asyncPreempt -> mcall 到 g0 -> gopreempt_m。

口播：
> 如果一个 G 一直跑长循环，不主动让出 CPU，其他 G 就可能饿住。Go 的抢占经历过两个阶段。早期主要靠协作式抢占：调度器发现 G 跑太久，就把它标记成 stackPreempt，等它下次函数调用做 stack check 时，自己让出执行权。但如果代码是没有函数调用的死循环，这招就不够及时。Go 1.14 之后引入信号式抢占：sysmon 发现某个 G 跑太久，会向对应 M 发 SIGURG，sighandler 介入，修改寄存器，把 asyncPreempt 注入到当前执行点。随后通过 mcall 切到 g0，在调度栈上把这个 G 抢下来。

字幕重点：
- `协作式：等 G 自己走到检查点`
- `信号式：runtime 主动插入 asyncPreempt`

## 6. 普通阻塞：G 等，M/P 继续干活

时长：5:10-5:55

画面：
- 使用 `GMP机制.普通阻塞.png`。
- 示例：channel 收发对不上，G1 从 running 进入 waiting。
- M 和 P 不解绑，立刻切到 G2。
- 条件满足后，G1 通过 `ready/runqput` 回到队列。

口播：
> 普通阻塞发生在 channel、锁、time.Sleep 这类场景。关键点是：阻塞的是 G，不是整个 M 和 P。G1 等条件满足时，M 还绑定着 P，可以马上去跑另一个 G。等条件满足，等待队列把 G1 唤醒，runtime 通过 ready 或 runqput 把它重新放回可运行队列，后面 findRunnable 再把它捞起来。

字幕重点：
- `普通阻塞：只让 G 等`
- `M/P 不浪费`

## 7. 网络阻塞：G 挂到 fd 上，netpoll 负责唤醒

时长：5:55-6:45

画面：
- 使用 `GMP机制.网络阻塞.png`。
- G 发起 Read/Write，关联到 `fd + event + pollDesc`。
- 内核 epoll/kqueue 报告就绪，netpoll 把 G 放回队列。

口播：
> 网络阻塞更特殊一点。比如 net.Conn Read 发现现在没数据，G 不会傻等在 M 上，而是 park 起来，并把自己关心的 fd 和读写事件记录到 pollDesc 里。M 继续跑别的 G。等内核通过 epoll 或 kqueue 通知这个 fd 就绪，runtime 的 netpoll 层会把对应的 G 设回 runnable，再放回本地或全局队列。下一次调度到它时，再重试 Read 或 Write。

字幕重点：
- `fd 就绪由内核通知`
- `netpoll 负责把 G 叫回来`

## 8. 系统调用阻塞：M 可能卡住，所以 P 要释放

时长：6:45-7:35

画面：
- 使用 `GMP机制.系统调用阻塞.png`。
- G 进入 syscall，状态变成 `_Gsyscall`。
- M 进入内核并变暗，P 被释放给另一个 M。
- syscall 返回：快路径拿 P；失败则进全局队列。

口播：
> 最后看系统调用阻塞。如果 G 进入一个可能长时间阻塞的 syscall，当前 M 也会跟着陷进内核。为了不浪费调度资源，runtime 会在 entersyscall 路径释放 P，让这个 P 可以被别的 M 接管，继续跑其他 runnable G。等 syscall 返回，G 走 exitsyscall，优先尝试快速拿一个 P 继续跑；如果拿不到，就变回 runnable，进入全局队列等待调度。

字幕重点：
- `syscall 会拖住 M`
- `释放 P，保证其他 G 继续跑`

## 9. 总结收束

时长：7:35-8:00

画面：
- 回到 `GMP机制.GMP关系总览.png`。
- 四句总结逐行出现。

口播：
> 所以 GMP 的核心不是死记结构体，而是记住这条链路：M 绑定 P 才能跑 G；调度本地优先，全局兜底，窃取均衡；抢占保证长任务不会一直霸占 CPU；阻塞时尽量只让该等的 G 等，把 M 和 P 释放给更多可运行任务。理解这条线，后面再看 findRunnable、sysmon、netpoll 和 syscall，就顺很多了。

字幕重点：
- `M-P 绑定后跑 G`
- `本地优先，全局兜底`
- `抢占防独占`
- `阻塞要释放调度资源`

# 生成建议

- 语速：中文 260-300 字/分钟。
- 配音：稳、清晰、像面试前复习课。
- 背景音乐：低音量，无歌词。
- 画面文字：只保留关键词，不展示大段正文。
- 每个图示镜头都要有局部高亮，否则观众会迷失。

