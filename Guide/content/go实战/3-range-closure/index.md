---
title: range / closure
weight: 3
date: 2026-06-19
draft: false
---

这一章训练 `range` 和闭包的实战推演。

看到这类题，先问自己四件事：

```text
range 的对象是什么：slice、array、map、channel、string？
拿到的是值拷贝，还是通过下标访问原数据？
闭包捕获的是哪个变量？
当前 Go 版本是否涉及 Go 1.22 range 变量语义变化？
```

核心模型：

1. `range slice` 时，`v` 是元素值的拷贝。
2. 要修改 slice 元素，应该用下标 `s[i]`。
3. `range array` 会复制数组，`range &array` 不会复制数组。
4. `range map` 顺序不保证。
5. `range string` 按 rune 遍历，索引是字节下标。
6. Go 1.22 起，`for` 循环变量每轮迭代会创建新变量；旧版本中循环变量复用，闭包和取地址容易踩坑。

---

## 1. range value 是拷贝

题目：

```go
func main() {
	a := []int{1, 2, 3}
	for _, v := range a {
		v *= 10
	}
	fmt.Println(a)
}
```

答案：

```text
[1 2 3]
```

推演：

`v` 是元素值的拷贝。修改 `v` 只改这个临时变量，不会修改底层数组里的真实元素。

模型：

```text
range 的 value 是拷贝。
```

---

## 2. 用下标修改元素

题目：

```go
func main() {
	a := []int{1, 2, 3}
	for i := range a {
		a[i] *= 10
	}
	fmt.Println(a)
}
```

答案：

```text
[10 20 30]
```

推演：

`a[i]` 访问的是底层数组里的真实元素，所以可以修改 slice 内容。

模型：

```text
修改 slice 元素，用下标，不要改 range value。
```

---

## 3. range value 取地址

题目：

```go
func main() {
	a := []int{1, 2, 3}
	var ps []*int
	for _, v := range a {
		ps = append(ps, &v)
	}
	for _, p := range ps {
		fmt.Println(*p)
	}
}
```

答案：

```text
Go 1.22 及以后：1 2 3
Go 1.21 及以前：3 3 3
```

推演：

Go 1.21 及以前，`v` 是循环中复用的同一个变量，`&v` 每轮都是同一个地址，循环结束后它的值是最后一个元素 `3`。指针保存的是地址，不是当时的值，比如一直是0x100，到最后打印 `3`。

Go 1.22 起，range 循环变量每轮迭代都会创建新变量，所以 `&v` 每轮地址不同，打印 `1 2 3`。

模型：

```text
老版本 range 变量复用；Go 1.22 起每轮变量独立。
```

---

## 4. 想取元素地址，要取下标

题目：

```go
func main() {
	a := []int{1, 2, 3}
	var ps []*int
	for i := range a {
		ps = append(ps, &a[i])
	}
	*ps[0] = 9
	fmt.Println(a)
}
```

答案：

```text
[9 2 3]
```

推演：

`&a[i]` 取的是底层数组中真实元素的地址。通过指针修改，会影响原 slice。

模型：

```text
要保存 slice 元素地址，用 &s[i]，不要用 &v。
```

---

## 5. 闭包捕获 range 变量

题目：

```go
func main() {
	a := []int{1, 2, 3}
	var fs []func()
	for _, v := range a {
		fs = append(fs, func() {
			fmt.Println(v)
		})
	}
	for _, f := range fs {
		f()
	}
}
```

答案：

```text
Go 1.22 及以后：1 2 3
Go 1.21 及以前：3 3 3
```

推演：

Go 1.21 及以前，闭包捕获的是同一个循环变量 `v`，循环结束后 `v` 是 `3`。闭包捕获的是变量，不是值。

Go 1.22 起，每轮迭代有新的 `v`，闭包捕获的是每轮自己的变量。

模型：

```text
闭包捕获循环变量要注意 Go 版本。
```

---

## 6. 兼容旧版本的写法

题目：

```go
func main() {
	a := []int{1, 2, 3}
	var fs []func()
	for _, v := range a {
		v := v
		fs = append(fs, func() {
			fmt.Println(v)
		})
	}
	for _, f := range fs {
		f()
	}
}
```

答案：

```text
1
2
3
```

推演：

`v := v` 在循环体内创建了一个新的局部变量，每个闭包捕获的是本轮自己的变量。这个写法在 Go 1.21 及以前也能避免闭包捕获复用变量的问题。

模型：

```text
循环里 v := v 可以为闭包创建本轮变量。
```

---

## 7. goroutine 捕获 range 变量

题目：

```go
func main() {
	a := []int{1, 2, 3}
	var wg sync.WaitGroup
	for _, v := range a {
		wg.Add(1)
		go func() {
			defer wg.Done()
			fmt.Println(v)
		}()
	}
	wg.Wait()
}
```

答案：

```text
Go 1.22 及以后：打印 1、2、3，顺序不确定
Go 1.21 及以前：可能打印 3、3、3
```

推演：

这题和闭包捕获一样，只是闭包被 goroutine 延迟执行了。旧版本里 goroutine 很可能在循环结束后才执行，此时复用变量 `v` 已经是最后一个值。

模型：

```text
goroutine + 循环变量，本质仍是闭包捕获问题。
```

---

## 8. 用参数传入 goroutine

题目：

```go
func main() {
	a := []int{1, 2, 3}
	var wg sync.WaitGroup
	for _, v := range a {
		wg.Add(1)
		go func(v int) {
			defer wg.Done()
			fmt.Println(v)
		}(v)
	}
	wg.Wait()
}
```

答案：

```text
打印 1、2、3，顺序不确定
```

推演：

启动 goroutine 时，外层 `v` 的值作为参数传入匿名函数。每个 goroutine 都有自己的参数变量，所以不会共享同一个循环变量。

模型：

```text
goroutine 中使用循环变量，推荐通过参数传入。
```

---

## 9. range slice 时 append

题目：

```go
func main() {
	a := []int{1, 2, 3}
	for _, v := range a {
		a = append(a, v)
	}
	fmt.Println(a)
}
```

答案：

```text
[1 2 3 1 2 3]
```

推演：

range 开始时会确定遍历次数，初始 len 是 3。循环中 append 会让 `a` 变长，但本次 range 只跑 3 轮。

模型：

```text
range slice 的遍历次数由开始时的 len 决定。
```

---

## 10. range slice 时修改后续元素

题目：

```go
func main() {
	a := []int{1, 2, 3}
	for i, v := range a {
		if i == 0 {
			a[1] = 9
		}
		fmt.Println(i, v)
	}
	fmt.Println(a)
}
```

答案：

```text
0 1
1 9
2 3
[1 9 3]
```

推演：

range slice 不会复制底层数组。第一轮把 `a[1]` 改成 9，第二轮取 value 时会从底层数组读取最新的 `a[1]`，所以 `v` 是 9。

模型：

```text
range slice 不复制底层数组，后续元素修改可能被后续迭代看到。
```

---

## 11. range 数组时修改后续元素

题目：

```go
func main() {
	a := [3]int{1, 2, 3}
	for i, v := range a {
		if i == 0 {
			a[1] = 9
		}
		fmt.Println(i, v)
	}
	fmt.Println(a)
}
```

答案：

```text
0 1
1 2
2 3
[1 9 3]
```

推演：

range 数组时，range 表达式会复制整个数组。循环中的 `v` 来自复制数组，所以第二轮仍打印 2。原数组 `a` 确实被改成 `[1 9 3]`。

模型：

```text
range 数组会复制数组。
```

---

## 12. range 数组指针

题目：

```go
func main() {
	a := [3]int{1, 2, 3}
	for i, v := range &a {
		if i == 0 {
			a[1] = 9
		}
		fmt.Println(i, v)
	}
	fmt.Println(a)
}
```

答案：

```text
0 1
1 9
2 3
[1 9 3]
```

推演：

`range &a` 遍历的是数组指针，不会复制整个数组。第一轮修改 `a[1]` 后，第二轮能看到新值 9。

模型：

```text
range 数组会复制，range 数组指针不会复制数组。
```

---

## 13. range map 顺序不固定

题目：

```go
func main() {
	m := map[string]int{
		"a": 1,
		"b": 2,
		"c": 3,
	}
	for k, v := range m {
		fmt.Println(k, v)
	}
}
```

答案：

```text
输出顺序不固定
```

推演：

Go 语言不保证 map 的遍历顺序。同一段代码多次运行，输出顺序都可能不同。

模型：

```text
不要依赖 map range 顺序。
```

---

## 14. range map 时删除当前 key

题目：

```go
func main() {
	m := map[string]int{"a": 1, "b": 2, "c": 3}
	for k := range m {
		delete(m, k)
	}
	fmt.Println(len(m))
}
```

答案：

```text
0
```

推演：

range map 时删除当前正在遍历到的 key 是允许的。每遍历到一个 key 就删除，最终 map 为空。

模型：

```text
range map 时可以删除当前 key。
```

---

## 15. range map 时新增 key

题目：

```go
func main() {
	m := map[string]int{"a": 1}
	for k := range m {
		fmt.Println(k)
		m["b"] = 2
	}
}
```

答案：

```text
可能只打印 a，也可能打印 a 和 b
```

推演：

range map 过程中新增的 key，可能被本次遍历看到，也可能看不到。Go 不保证这个行为。

模型：

```text
range map 时新增 key，不保证本轮是否遍历到。
```

---

## 16. range string 按 rune 遍历

题目：

```go
func main() {
	s := "a你b"
	for i, r := range s {
		fmt.Println(i, string(r))
	}
}
```

答案：

```text
0 a
1 你
4 b
```

推演：

range string 按 UTF-8 解码后的 rune 遍历，但索引 `i` 是字节下标。`a` 占 1 个字节，`你` 占 3 个字节，所以 `b` 的字节下标是 4。

模型：

```text
range string：i 是字节下标，r 是 rune。
```

---

## 17. range nil slice

题目：

```go
func main() {
	var a []int
	for i, v := range a {
		fmt.Println(i, v)
	}
	fmt.Println("done")
}
```

答案：

```text
done
```

推演：

nil slice 的 len 是 0，对 nil slice range 不会 panic，只是循环 0 次。

模型：

```text
range nil slice 安全，循环 0 次。
```

---

## 18. range nil map

题目：

```go
func main() {
	var m map[string]int
	for k, v := range m {
		fmt.Println(k, v)
	}
	fmt.Println("done")
}
```

答案：

```text
done
```

推演：

nil map 可以 range，循环 0 次。注意：nil map 可以读、可以 range，但不能写入。

模型：

```text
range nil map 安全，循环 0 次。
```

---

## 19. range nil channel

题目：

```go
func main() {
	var ch chan int
	for v := range ch {
		fmt.Println(v)
	}
	fmt.Println("done")
}
```

答案：

```text
死锁
```

推演：

nil channel 的接收会永久阻塞。`range ch` 本质上不断从 channel 接收，直到 channel 被关闭。但 nil channel 永远不会有值，也不会被关闭，所以 main goroutine 阻塞，最终运行时报 deadlock。

模型：

```text
range nil channel 会永久阻塞。
```

---

## 20. range closed channel

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

range channel 会不断接收值，直到 channel 关闭并且缓冲区中的值被读完。这里 close 后缓冲区还有 1 和 2，所以先打印两个值，再退出循环。

模型：

```text
range channel：关闭且缓冲读空后退出。
```

