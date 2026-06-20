---
title: defer / panic / recover
weight: 1
date: 2026-06-19
draft: false
---

目标：看到 `defer`、`panic`、`recover` 相关代码时，能稳定推演执行顺序、返回值变化和 panic 是否会被接住。

核心模型：

1. `defer` 在函数返回前执行，多个 `defer` 后进先出。
2. `defer` 的参数在注册 defer 时就求值。
3. 匿名函数 defer 可以读取和修改外层变量。
4. `return` 不是原子操作：先设置返回值，再执行 defer，最后真正返回。
5. `recover` 只有在同一个 goroutine 的 defer 函数中直接调用才有效。
6. panic 发生后，本 goroutine 会按栈展开执行 defer；如果没有 recover，程序崩溃。

---

## 1. 多个 defer 的顺序

题目：

```go
func main() {
	defer fmt.Println("A")
	defer fmt.Println("B")
	defer fmt.Println("C")
	fmt.Println("D")
}
```

答案：

```text
D
C
B
A
```

推演：

`defer` 是栈结构，后注册的先执行。`D` 正常执行，函数结束前依次执行 `C -> B -> A`。

模型：

```text
多个 defer：后进先出。
```

---

## 2. defer 参数提前求值

题目：

```go
func main() {
	x := 1
	defer fmt.Println(x)
	x = 2
}
```

答案：

```text
1
```

推演：

执行到 `defer fmt.Println(x)` 时，参数 `x` 已经被求值为 `1`。后面把 `x` 改成 `2`，不会影响这个 defer 已保存的参数。

模型：

```text
defer 的参数在注册 defer 时求值，不是在执行 defer 时求值。
```

---

## 3. defer 匿名函数读取外部变量

题目：

```go
func main() {
	x := 1
	defer func() {
		fmt.Println(x)
	}()
	x = 2
}
```

答案：

```text
2
```

推演：

这里 defer 注册的是匿名函数本身，没有提前把 `x` 作为参数传入。匿名函数执行时再读取外层变量 `x`，此时 `x` 已经变成 `2`。

模型：

```text
defer func(){ 使用外部变量 } 会在真正执行 defer 时读取变量当前值。
```

---

## 4. defer 参数和闭包混合

题目：

```go
func main() {
	x := 1
	defer func(v int) {
		fmt.Println(v, x)
	}(x)
	x = 2
}
```

答案：

```text
1 2
```

推演：

`v` 是 defer 注册时传入的参数，所以是 `1`。匿名函数内部直接读取外层变量 `x`，执行时 `x` 已经是 `2`。

模型：

```text
defer 参数提前定，闭包变量执行时读。
```

---

## 5. 普通返回值与 defer

题目：

```go
func f() int {
	x := 1
	defer func() {
		x++
	}()
	return x
}

func main() {
	fmt.Println(f())
}
```

答案：

```text
1
```

推演：

`return x` 会先把 `x` 的值复制到匿名返回值中，此时返回值是 `1`。然后执行 defer，`x++` 只修改局部变量 `x`，不会再影响已经复制出去的返回值。

模型：

```text
普通返回值：return 表达式先求值，defer 改局部变量不影响返回值。
```

---

## 6. 命名返回值与 defer

题目：

```go
func f() (x int) {
	defer func() {
		x++
	}()
	return 1
}

func main() {
	fmt.Println(f())
}
```

答案：

```text
2
```

推演：

`return 1` 会先把命名返回值 `x` 设置为 `1`，然后执行 defer。defer 中的 `x++` 修改的是命名返回值本身，所以最终返回 `2`。

模型：

```text
命名返回值：return 先赋值，defer 还能改命名返回值。
```

---

## 7. return 后的 defer 执行时机

题目：

```go
func f() (x int) {
	defer func() {
		fmt.Println("defer", x)
		x = 3
	}()
	x = 1
	return 2
}

func main() {
	fmt.Println("return", f())
}
```

答案：

```text
defer 2
return 3
```

推演：

执行 `return 2` 时，先把命名返回值 `x` 改成 `2`。然后执行 defer，所以 defer 里打印的是 `2`，再把 `x` 改成 `3`。最后真正返回 `3`。

模型：

```text
return 表达式赋值 -> defer -> 函数真正返回。
```

---

## 8. panic 时 defer 是否执行

题目：

```go
func main() {
	defer fmt.Println("A")
	panic("boom")
	fmt.Println("B")
}
```

答案：

```text
A
panic: boom
```

推演：

`panic` 发生后，当前 goroutine 开始栈展开，已经注册的 defer 会执行。因此会先打印 `A`。`panic` 后面的 `B` 不会执行。因为没有 recover，程序最终崩溃。

模型：

```text
panic 会触发本 goroutine 已注册的 defer。
```

---

## 9. recover 接住 panic

题目：

```go
func main() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Println("recover", r)
		}
	}()
	panic("boom")
	fmt.Println("after")
}
```

答案：

```text
recover boom
```

推演：

`panic("boom")` 后开始执行 defer。defer 中直接调用 `recover()`，成功接住 panic。`panic` 之后的 `fmt.Println("after")` 不会回去执行。

模型：

```text
recover 接住 panic 后，函数不会回到 panic 后的位置继续执行。
```

---

## 10. recover 不在 defer 中无效

题目：

```go
func main() {
	if r := recover(); r != nil {
		fmt.Println("recover", r)
	}
	panic("boom")
}
```

答案：

```text
panic: boom
```

推演：

`recover` 只有在 panic 发生后的 defer 调用链中才有效。这里 `recover()` 执行时还没有 panic，所以返回 nil。后面的 panic 没有被接住。

模型：

```text
recover 不是 try-catch，平时调用没有效果。
```

---

## 11. recover 间接调用无效

题目：

```go
func doRecover() {
	if r := recover(); r != nil {
		fmt.Println("recover", r)
	}
}

func main() {
	defer func() {
		doRecover()
	}()
	panic("boom")
}
```

答案：

```text
panic: boom
```

推演：

虽然 `doRecover` 是在 defer 函数中被调用的，但 `recover()` 不是在 deferred function 里直接调用，而是在更深一层的普通函数中调用，所以不能接住 panic。

模型：

```text
recover 必须在 defer 函数中直接调用。
```

---

## 12. 同一个 goroutine 中多层函数 recover

题目：

```go
func f() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Println("recover in f:", r)
		}
	}()
	g()
	fmt.Println("after g")
}

func g() {
	panic("boom")
}

func main() {
	f()
	fmt.Println("after f")
}
```

答案：

```text
recover in f: boom
after f
```

推演：

`g` 中 panic 后，会沿着当前 goroutine 的调用栈向上展开。`f` 中注册了 defer recover，因此能接住这个 panic。`g()` 后面的 `after g` 不会执行，但 `f` 返回后，`main` 可以继续执行。

模型：

```text
recover 可以接住同一个 goroutine 调用栈下层函数的 panic。
```

---

## 13. recover 不能跨 goroutine

题目：

```go
func main() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Println("recover", r)
		}
	}()

	go func() {
		panic("boom")
	}()

	time.Sleep(time.Second)
}
```

答案：

```text
panic: boom
```

推演：

`main` goroutine 中的 defer recover 只能接住 `main` goroutine 自己调用栈里的 panic。新 goroutine 中发生的 panic 只能由新 goroutine 自己的 defer recover 接住。这里新 goroutine 没有 recover，所以程序崩溃。

模型：

```text
recover 不能跨 goroutine。
```

---

## 14. 在 goroutine 内部 recover

题目：

```go
func main() {
	done := make(chan struct{})

	go func() {
		defer func() {
			if r := recover(); r != nil {
				fmt.Println("recover", r)
			}
			close(done)
		}()
		panic("boom")
	}()

	<-done
	fmt.Println("main exit")
}
```

答案：

```text
recover boom
main exit
```

推演：

panic 发生在新 goroutine 中，而 recover 也在同一个 goroutine 的 defer 中，所以可以接住。defer 继续执行 `close(done)`，main goroutine 收到通知后继续执行。

模型：

```text
goroutine 内部自己 defer recover，才能保护这个 goroutine。
```

---

## 15. defer 中再次 panic

题目：

```go
func main() {
	defer fmt.Println("A")
	defer func() {
		fmt.Println("B")
		panic("panic in defer")
	}()
	panic("origin panic")
}
```

答案：

```text
B
A
panic: origin panic
	panic: panic in defer
```

推演：

原始 panic 发生后开始执行 defer。后注册的 defer 先执行，打印 `B`，然后它自己又 panic。接着继续执行下一个 defer，打印 `A`。因为没有 recover，最终程序崩溃，并会显示原始 panic 和 defer 中的新 panic。

模型：

```text
panic 展开过程中 defer 仍按后进先出执行；defer 中再次 panic 会替代/叠加当前崩溃信息。
```

---


