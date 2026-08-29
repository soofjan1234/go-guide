---
title: 其它
weight: 140
date: 2026-05-25
draft: false
---

## interface +1

![interface.概览](pic/interface.概览.png)

分为两种：

1. **空接口** `eface`：`(_type, data)`，比如`any` / `interface{}`
2. **非空接口** `iface`：`(itab, data)`，`itab` 含方法表 + 类型

### 接口 nil

在 Go 里，`error` 大致等价于下面这样的接口：

```go
type error interface {
	Error() string
}
```

结合 `error`，看清为什么 `err == nil` 有时会误判。

```go
type MyError struct{ msg string }

func (e *MyError) Error() string { return e.msg }

var e1 error
var p *MyError
var e2 error = p

fmt.Println(e1 == nil) // true：接口值「类型、值」都空
fmt.Println(e2 == nil) // false：动态类型已是 *MyError，只是 data 为 nil
```

## WaitGroup +1

![同步原语.WaitGroup](pic/同步原语.WaitGroup.png)

sync.WaitGroup 只有三个方法：

1. Add(delta int)：把计数器加上 delta。通常用来设定要等待的协程数量。
2. Done()：把计数器减 1。相当于 Add(-1)。通常在子协程结束时（利用 defer）调用。
3. Wait()：阻塞当前协程，直到计数器变成 0。

```go
var mutex sync.Mutex

func f() {
    gnum := 0
    wg := sync.WaitGroup{}
    count := 10000

    wg.Add(1)
    for i := 0; i < count; i++ {
        go func() {
            defer wg.Done()
            
            mutex.Lock()
            gnum++
            mutex.Unlock()
        }()
    }
    wg.Wait()
    fmt.Println(gnum)
}
```

`Add(1)` 只把计数设为 1，却启动了 `count` 个 goroutine 各自 `Done()`，第二个及之后的 `Done()` 会让计数变负，**panic: sync: negative WaitGroup counter**，通常还来不及打印 `gnum`。

正确写法是循环前 `wg.Add(count)`（或每次 `go` 前 `Add(1)`），使 `Add` 与 `Done` 次数一致；配合 `mutex` 保护共享变量，稳定输出 **10000**。

## 限制并发、等待、取消 +2

### 1. 限制并发：两种

**工人池**：固定起 `x` 个 goroutine，循环从任务通道取活。并发上限 = 工人数，多出来的任务堵在 channel 里，**不会创建 1000 个 G**。

```go
tasks := make(chan int)
var wg sync.WaitGroup
for i := 0; i < x; i++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        for t := range tasks { // 通道关闭且读完才退出
            do(t)
        }
    }()
}
for _, t := range jobs {
    tasks <- t
}
close(tasks) // 只有生产者关
wg.Wait()
```

**信号量**：`sem := make(chan struct{}, x)`，循环里先占用一个槽再 `go`。并发上限 = 缓冲大小；**acquire 要放在 `go` 之前**，否则会先拉起 1000 个 G，只是其中 `x` 个在跑、其余堵在 `sem <-`。

```go
sem := make(chan struct{}, x)
var wg sync.WaitGroup
for i := 0; i < 1000; i++ {
    wg.Add(1)
    sem <- struct{}{} // 满了就阻塞主循环，不再多起 G
    go func(i int) {
        defer wg.Done()
        defer func() { <-sem }()
        do(i)
    }(i)
}
wg.Wait()
```

| | 工人池 | 信号量 |
|---|---|---|
| 同时跑的任务 | `x` | `x` |
| goroutine 数量 | 恒为 `x` | 约 `x`（acquire 在 `go` 前） |
| 适合 | 任务流长、要复用工人 | 一次性 N 个任务、写法简单 |

### 2. 等待：两种（语义不同）

- **WaitGroup**：等**全部**结束。`Wait()` 不能被取消、不能超时，计数变 0 才返回。
- **select + 结果通道**：等**一个事件**（成功 / 失败 / `ctx.Done()`），主流程可以先返回。结果通道必须带缓冲（容量 1），否则超时后无人接收，工人卡在发送上泄漏。见 Context 节。

要「全部结束 + 谁先错谁取消其余」，用 `errgroup.WithContext`（内部仍是 WaitGroup + ctx）。

### 3. 取消：信号一样，退出路径不同

取消/超时都是 **`ctx, cancel := WithCancel/WithTimeout`，工人 `select` 监听 `ctx.Done()`**（或自己 `close(done)`）。`cancel()` 只是广播「该停了」，**不会把已经在跑的 G 杀掉**，也不会让 `wg.Wait()` 提前返回。

因此和上面两种模型绑定时：

1. **工人池**：`cancel` 之后工人必须在「取任务」处 `select`，否则还会把通道里剩余任务做完。主循环也要停投递。只 `close(tasks)` 是「没有新任务了」，不是取消正在执行的 `do()`；`do()` 内部还要把 `ctx` 传到 HTTP/DB。

```go
ctx, cancel := context.WithCancel(context.Background())
defer cancel()

tasks := make(chan int)
var wg sync.WaitGroup
for i := 0; i < x; i++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        for {
            select {
            case <-ctx.Done():
                return
            case t, ok := <-tasks:
                if !ok {
                    return
                }
                do(ctx, t) // 进行中的活也要能停
            }
        }
    }()
}

loop:
for _, t := range jobs {
    select {
    case <-ctx.Done():
        break loop // 停投递
    case tasks <- t:
    }
}
close(tasks)
wg.Wait()
```

2. **信号量**：每个任务一个 G，各自听 `ctx.Done()`。主流程若用 select 提前返回，工人仍要靠 ctx 自己退出；`Wait()` 的话会等到这些退出（所以工人必须响应 ctx，否则超时也等死）。

```go
ctx, cancel := context.WithTimeout(context.Background(), time.Second)
defer cancel()

sem := make(chan struct{}, x)
var wg sync.WaitGroup
for i := 0; i < 1000; i++ {
    select {
    case <-ctx.Done():
        wg.Wait()
        return ctx.Err()
    case sem <- struct{}{}:
    }
    
    wg.Add(1)
    go func(i int) {
        defer wg.Done()
        defer func() { <-sem }()
        select {
        case <-ctx.Done():
            return
        default:
        }
        do(ctx, i)
    }(i)
}
wg.Wait()
```

3. **WaitGroup vs select**：取消不能替代 Wait。select 先返回后，未收尾的 G 仍在跑 → 必须 ctx + 缓冲结果通道；若必须确认全部停干净，取消后还是要 `Wait()`（或 errgroup）。

```go
ctx, cancel := context.WithTimeout(parent, 100*time.Millisecond)
defer cancel()

resCh := make(chan string, 1) // 必须带缓冲，防泄漏
go func() {
    v, err := do(ctx)
    if err != nil {
        return
    }
    resCh <- v
}()

select {
case v := <-resCh:
    return v, nil
case <-ctx.Done():
    return "", ctx.Err() // 主流程先返回；工人靠 ctx 自己退出
}
// 若必须等工人停干净：cancel() 之后再 wg.Wait()
```
