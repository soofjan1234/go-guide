---
title: channel / select
weight: 4
date: 2026-06-19
draft: false
---

这一章训练 channel 和 select 的实战推演。

看到 channel 题，先判断四件事：

```text
channel 是 nil、open，还是 closed？
channel 是无缓冲，还是有缓冲？
当前操作是 send、receive，还是 close？
有没有另一个 goroutine 配合？
```

核心模型：

1. 无缓冲 channel 发送和接收必须配对，否则阻塞。
2. 有缓冲 channel 缓冲未满时发送不阻塞，缓冲非空时接收不阻塞。
3. nil channel 的发送和接收都会永久阻塞。
4. closed channel 不能发送，发送会 panic。
5. closed channel 可以接收，缓冲读完后返回零值和 `ok=false`。
6. close nil channel 会 panic，重复 close 会 panic。
7. select 只会执行一个 ready case；多个 ready case 会伪随机选择一个。
8. select 有 default 时，如果没有 ready case，会立即执行 default。

---

## 1. 无缓冲 channel 单独发送

题目：

```go
func main() {
	ch := make(chan int)
	ch <- 1
	fmt.Println("done")
}
```

答案：

```text
deadlock
```

推演：

无缓冲 channel 发送必须有接收方同时准备好。这里只有 main goroutine 发送，没有其他 goroutine 接收，所以 main 阻塞，最终运行时报 deadlock。

模型：

```text
无缓冲 channel：发送和接收必须配对。
```

---

## 2. 无缓冲 channel 配对发送接收

题目：

```go
func main() {
	ch := make(chan int)
	go func() {
		ch <- 1
	}()
	fmt.Println(<-ch)
}
```

答案：

```text
1
```

推演：

子 goroutine 发送，main goroutine 接收。无缓冲 channel 的发送和接收配对成功，值从发送方直接交给接收方。

模型：

```text
无缓冲 channel 是同步交接。
```

---

## 3. 有缓冲 channel 发送不一定阻塞

题目：

```go
func main() {
	ch := make(chan int, 2)
	ch <- 1
	ch <- 2
	fmt.Println("done")
}
```

答案：

```text
done
```

推演：

channel 容量是 2，连续发送两个值后缓冲区刚好满，但没有超过容量，所以不会阻塞。

模型：

```text
有缓冲 channel：缓冲未满时发送不阻塞。
```

---

## 4. 有缓冲 channel 满了再发送

题目：

```go
func main() {
	ch := make(chan int, 2)
	ch <- 1
	ch <- 2
	ch <- 3
	fmt.Println("done")
}
```

答案：

```text
deadlock
```

推演：

第三次发送时缓冲区已满，没有接收方取走数据，所以发送阻塞，最终 deadlock。

模型：

```text
有缓冲 channel：缓冲满时发送阻塞。
```

---

## 5. 有缓冲 channel 接收

题目：

```go
func main() {
	ch := make(chan int, 2)
	ch <- 1
	ch <- 2
	fmt.Println(<-ch)
	fmt.Println(<-ch)
}
```

答案：

```text
1
2
```

推演：

channel 保持 FIFO 顺序。先发送 1，再发送 2，接收时也按 1、2 的顺序读出。

模型：

```text
channel 缓冲区按 FIFO 接收。
```

---

## 6. nil channel 发送

题目：

```go
func main() {
	var ch chan int
	ch <- 1
	fmt.Println("done")
}
```

答案：

```text
deadlock
```

推演：

nil channel 没有底层数据结构，发送会永久阻塞。main goroutine 被阻塞后，没有其他 goroutine 可运行，最终 deadlock。

模型：

```text
nil channel 发送永久阻塞。
```

---

## 7. nil channel 接收

题目：

```go
func main() {
	var ch chan int
	fmt.Println(<-ch)
}
```

答案：

```text
deadlock
```

推演：

nil channel 接收也会永久阻塞。它不会返回零值，也不会 panic。

模型：

```text
nil channel 接收永久阻塞。
```

---

## 8. close 后接收

题目：

```go
func main() {
	ch := make(chan int)
	close(ch)
	v, ok := <-ch
	fmt.Println(v, ok)
}
```

答案：

```text
0 false
```

推演：

channel 已关闭且没有缓冲数据，接收会立即返回元素类型零值和 `ok=false`。

模型：

```text
closed channel 可读，读空后返回零值和 ok=false。
```

---

## 9. close 有缓冲 channel 后接收

题目：

```go
func main() {
	ch := make(chan int, 2)
	ch <- 1
	ch <- 2
	close(ch)
	fmt.Println(<-ch)
	fmt.Println(<-ch)
	v, ok := <-ch
	fmt.Println(v, ok)
}
```

答案：

```text
1
2
0 false
```

推演：

close 不会清空缓冲区。关闭后仍然可以先读出已有的 1 和 2。缓冲区读空后，再接收才返回零值和 `ok=false`。

模型：

```text
close 后先读缓冲，缓冲读空才 ok=false。
```

---

## 10. 向 closed channel 发送

题目：

```go
func main() {
	ch := make(chan int, 1)
	close(ch)
	ch <- 1
}
```

答案：

```text
panic: send on closed channel
```

推演：

关闭 channel 表示不会再有发送。向已关闭 channel 发送会直接 panic。

模型：

```text
closed channel 不能发送。
```

---

## 11. 重复 close

题目：

```go
func main() {
	ch := make(chan int)
	close(ch)
	close(ch)
}
```

答案：

```text
panic: close of closed channel
```

推演：

channel 只能关闭一次。第二次 close 会 panic。

模型：

```text
close 只能由发送方执行一次。
```

---

## 12. close nil channel

题目：

```go
func main() {
	var ch chan int
	close(ch)
}
```

答案：

```text
panic: close of nil channel
```

推演：

nil channel 没有底层结构，不能 close。

模型：

```text
close nil channel 会 panic。
```

---

## 13. range closed channel

题目：

```go
func main() {
	ch := make(chan int, 2)
	ch <- 1
	ch <- 2
	close(ch)

	for v := range ch {
		fmt.Println(v)
	}
	fmt.Println("done")
}
```

答案：

```text
1
2
done
```

推演：

`range ch` 会一直接收，直到 channel 关闭并且缓冲区读空。这里先读出 1 和 2，然后退出循环。

模型：

```text
range channel 在 closed 且 drained 后退出。
```

---

## 14. range 未关闭 channel

题目：

```go
func main() {
	ch := make(chan int, 2)
	ch <- 1
	ch <- 2

	for v := range ch {
		fmt.Println(v)
	}
	fmt.Println("done")
}
```

答案：

```text
1
2
deadlock
```

推演：

range 读完缓冲区里的 1 和 2 后，会继续等待新的值。因为 channel 没有关闭，也没有其他 goroutine 继续发送，所以阻塞并 deadlock。

模型：

```text
range channel 需要发送方 close 才能自然结束。
```

---

## 15. select with default

题目：

```go
func main() {
	ch := make(chan int)
	select {
	case v := <-ch:
		fmt.Println(v)
	default:
		fmt.Println("default")
	}
}
```

答案：

```text
default
```

推演：

无缓冲 channel 没有发送方，接收 case 不 ready。select 有 default，所以不会阻塞，直接执行 default。

模型：

```text
select 有 default 时，没有 ready case 就立即走 default。
```

---

## 16. select 没有 default

题目：

```go
func main() {
	ch := make(chan int)
	select {
	case v := <-ch:
		fmt.Println(v)
	}
}
```

答案：

```text
deadlock
```

推演：

select 没有 default，且唯一的接收 case 不 ready，所以 main goroutine 阻塞，最终 deadlock。

模型：

```text
select 没有 ready case 且没有 default，会阻塞。
```

---

## 17. select 多个 ready case

题目：

```go
func main() {
	ch1 := make(chan int, 1)
	ch2 := make(chan int, 1)
	ch1 <- 1
	ch2 <- 2

	select {
	case v := <-ch1:
		fmt.Println("ch1", v)
	case v := <-ch2:
		fmt.Println("ch2", v)
	}
}
```

答案：

```text
可能输出 ch1 1，也可能输出 ch2 2
```

推演：

两个 case 都 ready，select 会伪随机选择一个执行，不保证固定顺序。

模型：

```text
select 多个 ready case，随机选一个。
```

---

## 18. select 中 nil channel case 被禁用

题目：

```go
func main() {
	var ch1 chan int
	ch2 := make(chan int, 1)
	ch2 <- 2

	select {
	case v := <-ch1:
		fmt.Println("ch1", v)
	case v := <-ch2:
		fmt.Println("ch2", v)
	}
}
```

答案：

```text
ch2 2
```

推演：

nil channel 的接收永远不 ready。在 select 中，nil channel 的 case 等价于被禁用。只有 ch2 ready，所以执行 ch2。

模型：

```text
nil channel case 在 select 中永远不 ready。
```

---

## 19. 动态关闭 select 分支

题目：

```go
func main() {
	ch := make(chan int, 1)
	ch <- 1
	close(ch)

	for i := 0; i < 2; i++ {
		select {
		case v, ok := <-ch:
			if !ok {
				ch = nil
				fmt.Println("closed")
				continue
			}
			fmt.Println(v)
		}
	}
}
```

答案：

```text
1
closed
```

推演：

第一次 select 从已关闭但仍有缓冲数据的 channel 读到 1。第二次 select 读到零值和 `ok=false`，说明 channel 已经关闭且读空，于是把 `ch = nil`，后续这个 case 就会被禁用。

模型：

```text
select 里常用 ch = nil 动态禁用某个 case。
```

---

## 20. select 发送到 closed channel

题目：

```go
func main() {
	ch := make(chan int, 1)
	close(ch)

	select {
	case ch <- 1:
		fmt.Println("sent")
	default:
		fmt.Println("default")
	}
}
```

答案：

```text
panic: send on closed channel
```

推演：

向 closed channel 发送会 panic。即使这个发送写在 select case 中，也不会变成 default。只要 select 评估到这个发送 case，就会触发 panic。

模型：

```text
select 不能保护向 closed channel 发送。
```

