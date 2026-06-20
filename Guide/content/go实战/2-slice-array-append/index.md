---
title: slice / array / append
weight: 2
date: 2026-06-19
draft: false
---

这一章训练切片的实战推演能力。

核心模型：

1. 数组是值类型，赋值和传参会复制整个数组。
2. slice 不是数组本身，而是一个 header：指针、长度、容量。
3. slice 赋值会复制 header，多个 slice 可能共享同一个底层数组。
4. 截断只改变当前 slice 的 len，不会改变底层数组，也不会改变另一个 slice 的 len。
5. append 时如果 cap 足够，会复用底层数组；如果 cap 不够，会扩容并复制到新数组。
6. 函数传 slice，本质是复制 slice header；函数内改元素会影响外面，函数内 append 是否影响外面取决于是否扩容以及外部是否接收返回值。

---

## 1. 数组赋值会复制

题目：

```go
func main() {
	a := [3]int{1, 2, 3}
	b := a
	b[0] = 9
	fmt.Println(a)
	fmt.Println(b)
}
```

答案：

```text
[1 2 3]
[9 2 3]
```

推演：

数组是值类型，`b := a` 会复制整个数组。`a` 和 `b` 是两个不同数组，修改 `b[0]` 不影响 `a[0]`。

模型：

```text
数组赋值 = 复制整个数组。
```

---

## 2. slice 赋值共享底层数组

题目：

```go
func main() {
	a := []int{1, 2, 3}
	b := a
	b[0] = 9
	fmt.Println(a)
	fmt.Println(b)
}
```

答案：

```text
[9 2 3]
[9 2 3]
```

推演：

`b := a` 复制的是 slice header。两个 header 的 ptr 指向同一个底层数组，所以通过 `b[0]` 修改元素，会影响 `a` 看到的内容。

模型：

```text
slice 赋值 = 复制 header，共享底层数组。
```

---

## 3. 截断不会改变另一个 slice 的 len

题目：

```go
func main() {
	a := []int{1, 2, 3, 4}
	b := a
	a = a[:2]
	fmt.Println(a, len(a), cap(a))
	fmt.Println(b, len(b), cap(b))
}
```

答案：

```text
[1 2] 2 4
[1 2 3 4] 4 4
```

推演：

`a = a[:2]` 只修改 `a` 这个 slice header 的 len。`b` 是另一个 header，它的 len 仍然是 4。底层数组没有变。

模型：

```text
截断只改当前 slice header 的 len。
```

---

## 4. 截断后修改元素仍会影响另一个 slice

题目：

```go
func main() {
	a := []int{1, 2, 3, 4}
	b := a
	a = a[:2]
	a[1] = 9
	fmt.Println(a)
	fmt.Println(b)
}
```

答案：

```text
[1 9]
[1 9 3 4]
```

推演：

虽然 `a` 的 len 变成 2，但 `a` 和 `b` 仍共享同一个底层数组。`a[1] = 9` 修改的是底层数组下标 1，因此 `b` 也能看到。

模型：

```text
len 变短不代表底层数组断开。
```

---

## 5. append 不扩容时会改底层数组

题目：

```go
func main() {
	base := []int{1, 2, 3, 4}
	a := base[:2]
	b := base[:3]
	a = append(a, 9)
	fmt.Println(a)
	fmt.Println(b)
	fmt.Println(base)
}
```

答案：

```text
[1 2 9]
[1 2 9]
[1 2 9 4]
```

推演：

`a := base[:2]` 时，`a` 的 len 是 2，cap 是 4。append 一个元素时 cap 足够，不扩容，直接写到底层数组的下标 2。`b` 长度是 3，所以能看到下标 2 被改成 `9`。

模型：

```text
append 不扩容 = 写回共享底层数组。
```

---

## 6. append 不扩容但另一个 slice 的 len 不变

题目：

```go
func main() {
	base := []int{1, 2, 3, 4}
	a := base[:2]
	b := a
	a = append(a, 9)
	fmt.Println(a)
	fmt.Println(b)
	fmt.Println(base)
}
```

答案：

```text
[1 2 9]
[1 2]
[1 2 9 4]
```

推演：

`a` 和 `b` 初始都指向同一个底层数组，len 都是 2，cap 都是 4。`append(a, 9)` 没扩容，写到底层数组下标 2。但 `b` 的 len 仍是 2，所以打印 `b` 看不到第 3 个元素。

模型：

```text
共享底层数组不代表共享 len。
```

---

## 7. append 扩容后与旧数组分离

题目：

```go
func main() {
	a := []int{1, 2}
	b := a
	a = append(a, 3)
	a[0] = 9
	fmt.Println(a)
	fmt.Println(b)
}
```

答案：

```text
[9 2 3]
[1 2]
```

推演：

`a` 初始 len=2、cap=2。append 第 3 个元素时 cap 不够，会扩容并分配新底层数组。之后 `a` 指向新数组，`b` 仍指向旧数组，所以 `a[0] = 9` 不影响 `b`。

模型：

```text
append 扩容 = 新数组，旧 slice 不受后续元素修改影响。
```

---

## 8. make 指定 len 和 cap

题目：

```go
func main() {
	a := make([]int, 2, 4)
	a[0] = 1
	a[1] = 2
	b := append(a, 3)
	c := append(a, 4)
	fmt.Println(a)
	fmt.Println(b)
	fmt.Println(c)
}
```

答案：

```text
[1 2]
[1 2 4]
[1 2 4]
```

推演：

`a` 的 len=2、cap=4。`append(a, 3)` 不扩容，把底层数组下标 2 写成 3，得到 `b`。接着 `append(a, 4)` 仍然从 `a` 的 len=2 开始追加，覆盖同一个底层数组下标 2，把 3 改成 4。因此 `b` 和 `c` 打印时都看到 `[1 2 4]`。

模型：

```text
对同一个短 slice 多次 append，可能覆盖同一个底层数组位置。
```

---

## 9. append 返回值必须接住

题目：

```go
func main() {
	a := []int{1, 2}
	append(a, 3)
	fmt.Println(a)
}
```

答案：

```text
编译错误
```

推演：

`append` 的返回值必须被使用。Go 不允许调用 `append(a, 3)` 后丢弃返回值。

模型：

```text
append 会返回新的 slice header，必须接住。
```

---

## 10. 函数内修改 slice 元素

题目：

```go
func change(s []int) {
	s[0] = 9
}

func main() {
	a := []int{1, 2, 3}
	change(a)
	fmt.Println(a)
}
```

答案：

```text
[9 2 3]
```

推演：

函数传参时复制 slice header，但复制后的 header 仍指向同一个底层数组。`s[0] = 9` 修改底层数组，所以外面的 `a` 能看到。

模型：

```text
函数内改元素，会影响外部共享底层数组。
```

---

## 11. 函数内 append 不接返回值

题目：

```go
func add(s []int) {
	s = append(s, 3)
}

func main() {
	a := []int{1, 2}
	add(a)
	fmt.Println(a)
}
```

答案：

```text
[1 2]
```

推演：

传入函数的是 slice header 的副本。`s = append(s, 3)` 只改变函数内部的 `s` header，外部 `a` 的 len 不会变。即使 append 不扩容，外部 `a` 的 len 仍然是 2，打印时看不到追加的元素。

模型：

```text
函数内 append 后不返回，外部 slice header 不会变。
```

---

## 12. 函数内 append 并返回

题目：

```go
func add(s []int) []int {
	s = append(s, 3)
	return s
}

func main() {
	a := []int{1, 2}
	a = add(a)
	fmt.Println(a)
}
```

答案：

```text
[1 2 3]
```

推演：

append 返回新的 slice header。外部用 `a = add(a)` 接住这个 header，所以 `a` 的 len 更新为 3。

模型：

```text
函数内 append，要把新 slice 返回给调用方。
```

---

## 13. full slice expression 限制 cap

题目：

```go
func main() {
	base := []int{1, 2, 3, 4}
	a := base[:2:2]
	b := append(a, 9)
	b[0] = 8
	fmt.Println(base)
	fmt.Println(a)
	fmt.Println(b)
}
```

答案：

```text
[1 2 3 4]
[1 2]
[8 2 9]
```

推演：

`base[:2:2]` 的意思是 len=2、cap=2。append 时 cap 不够，必须扩容，`b` 指向新的底层数组。之后 `b[0] = 8` 只修改新数组，不影响 `base` 和 `a`。

模型：

```text
s[i:j:k] 可以限制 cap，让 append 更容易扩容隔离。
```

---

## 14. 子切片的 cap 从起点算到原数组末尾

题目：

```go
func main() {
	a := []int{1, 2, 3, 4, 5}
	b := a[2:3]
	fmt.Println(b, len(b), cap(b))
}
```

答案：

```text
[3] 1 3
```

推演：

`b := a[2:3]` 的 len 是 `3 - 2 = 1`。cap 从起点下标 2 算到原底层数组末尾，所以是 3，对应元素空间 `[3,4,5]`。

模型：

```text
普通切片 cap = 原数组容量 - 起始下标。
```

---

## 15. nil slice 可以 append

题目：

```go
func main() {
	var a []int
	fmt.Println(a == nil, len(a), cap(a))
	a = append(a, 1)
	fmt.Println(a == nil, len(a), cap(a), a)
}
```

答案：

```text
true 0 0
false 1 1 [1]
```

推演：

nil slice 的 header 中 ptr 为 nil，len 和 cap 都是 0。nil slice 可以直接 append，append 后会分配底层数组。

模型：

```text
nil slice 可读 len/cap，也可以 append。
```

---

## 16. 空 slice 和 nil slice 不一样

题目：

```go
func main() {
	var a []int
	b := []int{}
	fmt.Println(a == nil, len(a), cap(a))
	fmt.Println(b == nil, len(b), cap(b))
}
```

答案：

```text
true 0 0
false 0 0
```

推演：

`var a []int` 是 nil slice。`b := []int{}` 是非 nil 的空 slice。它们的 len 和 cap 都是 0，但 nil 判断不同。

模型：

```text
nil slice 和空 slice 长度一样，但 nil 状态不同。
```

---

## 17. range 中修改元素

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

range 中的 `v` 是元素值的拷贝。修改 `v` 不会修改底层数组中的元素。

模型：

```text
range value 是拷贝，改 v 不改原元素。
```

---

## 18. range 中用下标修改元素

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

通过下标 `a[i]` 修改的是底层数组里的真实元素，所以切片内容会变化。

模型：

```text
要在 range 中修改 slice 元素，用下标。
```

---

## 19. 对 slice range 时 append

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

range 开始时会确定遍历的长度，这里初始长度是 3。循环中 append 会让 `a` 变长，但本次 range 只遍历最初的 3 个元素，不会无限循环。

模型：

```text
range slice 的遍历次数由开始时的 len 决定。
```

---

## 20. 对数组 range 会复制数组

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

对数组做 range 时，range 表达式会复制数组。循环中的 `v` 来自复制出来的数组，所以即使第一轮把原数组 `a[1]` 改成 9，第二轮的 `v` 仍然是复制数组里的 2。循环结束后，原数组确实被改成 `[1 9 3]`。

模型：

```text
range 数组会复制数组；range slice 不会复制底层数组。
```

