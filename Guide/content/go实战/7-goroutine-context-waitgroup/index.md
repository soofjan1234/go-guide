---
title: goroutine / context / WaitGroup
weight: 7
date: 2026-06-19
draft: false
---

这一章进入第二阶段：并发与 runtime 推演。

看到 goroutine、context、WaitGroup 题，先判断五件事：

```text
main goroutine 会不会提前退出？
子 goroutine 有没有退出条件？
WaitGroup 的 Add、Done、Wait 顺序是否正确？
context cancel/timeout 有没有被监听？
channel send/receive 会不会让 goroutine 永久阻塞？
```

核心模型：

1. main goroutine 退出，整个进程退出，其他 goroutine 不会继续跑。
2. goroutine panic 如果没有在本 goroutine 内 recover，会导致整个进程崩溃。
3. WaitGroup 的 `Add` 应该在启动 goroutine 前调用。
4. `Done` 调用次数超过 `Add` 计数会 panic。
5. WaitGroup 不能在使用后复制。
6. context 取消只是发信号，goroutine 必须主动监听 `ctx.Done()` 才能退出。
7. 忘记 cancel、阻塞发送、阻塞接收、无限循环都可能导致 goroutine 泄漏。

---

## 1. main 退出后 goroutine 不继续执行

题目：

```go
func main() {
	go func() {
		fmt.Println("goroutine")
	}()
	fmt.Println("main")
}
```

答案：

```text
至少打印 main；goroutine 不保证打印
```

推演：

main goroutine 执行完后，整个进程就结束。子 goroutine 可能还没来得及被调度，所以不保证打印 `goroutine`。

模型：

```text
main 退出，进程退出，不会等待其他 goroutine。
```

---

## 2. 用 WaitGroup 等待 goroutine

题目：

```go
func main() {
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		fmt.Println("goroutine")
	}()
	wg.Wait()
	fmt.Println("main")
}
```

答案：

```text
goroutine
main
```

推演：

`wg.Add(1)` 增加计数，子 goroutine 执行完调用 `Done()`，计数归零后 `Wait()` 返回。main 会等待子 goroutine 完成。

模型：

```text
WaitGroup 用来等待一组 goroutine 完成。
```

---

## 3. Add 放到 goroutine 里面的风险

题目：

```go
func main() {
	var wg sync.WaitGroup
	go func() {
		wg.Add(1)
		defer wg.Done()
		fmt.Println("work")
	}()
	wg.Wait()
	fmt.Println("done")
}
```

答案：

```text
可能只打印 done
```

推演：

main goroutine 可能先执行到 `wg.Wait()`。如果此时子 goroutine 还没执行 `Add(1)`，Wait 看到计数是 0，会直接返回，然后 main 退出。子 goroutine 不保证执行。

模型：

```text
WaitGroup Add 要在启动 goroutine 前调用。
```

---

## 4. Done 调用过多

题目：

```go
func main() {
	var wg sync.WaitGroup
	wg.Add(1)
	wg.Done()
	wg.Done()
}
```

答案：

```text
panic: sync: negative WaitGroup counter
```

推演：

`Add(1)` 后计数是 1。第一次 `Done()` 让计数变成 0。第二次 `Done()` 等价于 `Add(-1)`，计数变成 -1，WaitGroup 会 panic。

模型：

```text
Done 次数不能超过 Add 的计数。
```

---

## 5. 忘记 Done 导致 Wait 永久阻塞

题目：

```go
func main() {
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		fmt.Println("work")
	}()
	wg.Wait()
	fmt.Println("done")
}
```

答案：

```text
work
deadlock
```

推演：

WaitGroup 计数是 1，但子 goroutine 没有调用 `Done()`。main goroutine 在 `Wait()` 永久等待。所有 goroutine 都睡眠后，运行时报 deadlock。

模型：

```text
Add 之后必须保证 Done 被调用。
```

---

## 6. defer Done 防止提前 return

题目：

```go
func main() {
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		if true {
			return
		}
	}()
	wg.Wait()
	fmt.Println("done")
}
```

答案：

```text
done
```

推演：

虽然 goroutine 提前 return，但 defer 会执行 `wg.Done()`，所以 WaitGroup 计数能归零。

模型：

```text
goroutine 开头 defer wg.Done()，避免遗漏 Done。
```

---

## 7. goroutine panic 会导致进程崩溃

题目：

```go
func main() {
	go func() {
		panic("boom")
	}()
	time.Sleep(time.Second)
	fmt.Println("main")
}
```

答案：

```text
panic: boom
```

推演：

子 goroutine 中 panic，如果没有在本 goroutine 内 recover，会导致整个程序崩溃。main 里的逻辑不能兜住它。

模型：

```text
任意 goroutine 未恢复的 panic 都会使进程崩溃。
```

---

## 8. goroutine 内部 recover

题目：

```go
func main() {
	done := make(chan struct{})
	go func() {
		defer close(done)
		defer func() {
			if r := recover(); r != nil {
				fmt.Println("recover", r)
			}
		}()
		panic("boom")
	}()
	<-done
	fmt.Println("main")
}
```

答案：

```text
recover boom
main
```

推演：

panic 发生在子 goroutine，recover 也在同一个 goroutine 的 defer 中，因此可以接住。`close(done)` 通知 main 继续执行。

模型：

```text
保护 goroutine，要在 goroutine 内部 defer recover。
```

---

## 9. context cancel 不会自动停止 goroutine

题目：

```go
func main() {
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		for {
			fmt.Println("work")
			time.Sleep(time.Second)
		}
	}()
	cancel()
	_ = ctx
	time.Sleep(2 * time.Second)
}
```

答案：

```text
goroutine 仍然继续打印 work，直到 main 退出
```

推演：

`cancel()` 只是关闭 `ctx.Done()`，发送取消信号。子 goroutine 没有监听这个信号，所以不会停止。

模型：

```text
context 取消是协作式取消，goroutine 必须主动监听。
```

---

## 10. 正确监听 ctx.Done

题目：

```go
func main() {
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})

	go func() {
		defer close(done)
		for {
			select {
			case <-ctx.Done():
				fmt.Println("stop")
				return
			default:
				time.Sleep(100 * time.Millisecond)
			}
		}
	}()

	cancel()
	<-done
}
```

答案：

```text
stop
```

推演：

`cancel()` 后，`ctx.Done()` 被关闭。子 goroutine 的 select 能收到信号并 return。

模型：

```text
goroutine 要退出，必须在循环里监听 ctx.Done。
```

---

## 11. context timeout

题目：

```go
func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	select {
	case <-time.After(time.Second):
		fmt.Println("done")
	case <-ctx.Done():
		fmt.Println(ctx.Err())
	}
}
```

答案：

```text
context deadline exceeded
```

推演：

`time.After(time.Second)` 要等 1 秒，但 context 100ms 后超时。`ctx.Done()` 先 ready，`ctx.Err()` 是 `context deadline exceeded`。

模型：

```text
WithTimeout 超时后 Done 关闭，Err 为 deadline exceeded。
```

---

## 12. 手动 cancel 优先于 timeout

题目：

```go
func main() {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	cancel()
	<-ctx.Done()
	fmt.Println(ctx.Err())
}
```

答案：

```text
context canceled
```

推演：

虽然设置了 1 秒超时，但立刻手动调用 cancel。context 的错误是 `context canceled`。

模型：

```text
手动 cancel 的 Err 是 context canceled。
```

---

## 13. 子 context 随父 context 取消

题目：

```go
func main() {
	parent, cancel := context.WithCancel(context.Background())
	child, _ := context.WithCancel(parent)

	cancel()
	<-child.Done()
	fmt.Println(child.Err())
}
```

答案：

```text
context canceled
```

推演：

child context 派生自 parent。parent 被取消后，child 也会被取消。

模型：

```text
context 取消会从父节点传播到子节点。
```

---

## 14. 子 context 取消不影响父 context

题目：

```go
func main() {
	parent := context.Background()
	child, cancel := context.WithCancel(parent)
	cancel()

	select {
	case <-parent.Done():
		fmt.Println("parent canceled")
	default:
		fmt.Println(child.Err())
	}
}
```

答案：

```text
context canceled
```

推演：

取消 child 不会反向取消 parent。`context.Background()` 的 Done 是 nil，不会 ready，所以走 default。

模型：

```text
context 取消只向下传播，不向上传播。
```

---

## 15. 忘记 cancel 的风险

题目：

```go
func f() {
	ctx, _ := context.WithTimeout(context.Background(), time.Minute)
	_ = ctx
}
```

答案：

```text
有资源泄漏风险
```

推演：

`WithTimeout` 会创建 timer。即使函数提前返回，如果不调用 cancel，timer 也要等到超时才释放相关资源。

模型：

```text
WithCancel/WithTimeout/WithDeadline 返回的 cancel 应该被调用。
```

---

## 16. 阻塞发送导致 goroutine 泄漏

题目：

```go
func main() {
	ch := make(chan int)
	go func() {
		ch <- 1
		fmt.Println("sent")
	}()
	time.Sleep(time.Second)
	fmt.Println("main")
}
```

答案：

```text
main
```

推演：

子 goroutine 在无缓冲 channel 上发送，但没有接收方，因此永久阻塞。因为 main 最终退出，进程结束；如果这是长期运行服务中的 goroutine，就会形成泄漏。

模型：

```text
没人接收的无缓冲发送会泄漏 goroutine。
```

---

## 17. 用 ctx 避免阻塞发送泄漏

题目：

```go
func send(ctx context.Context, ch chan<- int) {
	select {
	case ch <- 1:
		fmt.Println("sent")
	case <-ctx.Done():
		fmt.Println("canceled")
	}
}

func main() {
	ctx, cancel := context.WithCancel(context.Background())
	ch := make(chan int)
	cancel()
	send(ctx, ch)
}
```

答案：

```text
canceled
```

推演：

`ch <- 1` 没有接收方，不 ready。ctx 已取消，`ctx.Done()` ready，所以 select 走取消分支，不会永久阻塞。

模型：

```text
可能阻塞的发送，要考虑 select ctx.Done。
```

---

## 18. 阻塞接收导致 goroutine 泄漏

题目：

```go
func main() {
	ch := make(chan int)
	go func() {
		v := <-ch
		fmt.Println(v)
	}()
	time.Sleep(time.Second)
	fmt.Println("main")
}
```

答案：

```text
main
```

推演：

子 goroutine 等待从 channel 接收，但没有发送方，也没有关闭 channel，因此永久阻塞。在长期运行服务里，这就是 goroutine 泄漏。

模型：

```text
没人发送或关闭的接收会泄漏 goroutine。
```

---

## 19. close channel 唤醒接收方

题目：

```go
func main() {
	ch := make(chan int)
	done := make(chan struct{})

	go func() {
		defer close(done)
		v, ok := <-ch
		fmt.Println(v, ok)
	}()

	close(ch)
	<-done
}
```

答案：

```text
0 false
```

推演：

关闭 channel 会唤醒等待接收的 goroutine。接收方读到零值和 `ok=false`。

模型：

```text
close channel 可以广播通知所有接收方退出。
```

---

## 20. for select 忘记 return

题目：

```go
func worker(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			fmt.Println("stop")
		default:
			time.Sleep(time.Second)
		}
	}
}
```

答案：

```text
ctx 取消后仍不会退出
```

推演：

收到 `ctx.Done()` 后只是打印 `stop`，没有 `return` 或 `break` 跳出循环。下一轮循环还会继续执行，所以 goroutine 不会退出。

模型：

```text
收到取消信号后要 return，单纯打印不等于退出。
```

---

## 21. break 只跳出 select

题目：

```go
func worker(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			fmt.Println("stop")
			break
		default:
			time.Sleep(time.Second)
		}
	}
}
```

答案：

```text
ctx 取消后仍不会退出
```

推演：

这里的 `break` 只跳出 select，不会跳出外层 for。循环会继续执行。

模型：

```text
for-select 中退出 goroutine 通常用 return。
```

---

## 22. WaitGroup 复制的风险

题目：

```go
func wait(wg sync.WaitGroup) {
	wg.Wait()
}

func main() {
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
	}()
	wait(wg)
	fmt.Println("done")
}
```

答案：

```text
可能 deadlock
```

推演：

WaitGroup 不能在使用后复制。`wait(wg)` 传值复制了 WaitGroup，`Done()` 操作的是原来的 wg，而 `wait` 里等待的是副本。副本的计数不会归零，可能永久等待。

模型：

```text
WaitGroup 使用后不能复制，传参要传指针。
```

---

## 23. 正确传递 WaitGroup 指针

题目：

```go
func wait(wg *sync.WaitGroup) {
	wg.Wait()
}

func main() {
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
	}()
	wait(&wg)
	fmt.Println("done")
}
```

答案：

```text
done
```

推演：

传递的是 WaitGroup 指针，`Wait()` 和 `Done()` 操作同一个 WaitGroup，所以计数能归零。

模型：

```text
WaitGroup 传递用指针。
```

