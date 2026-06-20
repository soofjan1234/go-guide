---
title: interface / nil / method set
weight: 6
date: 2026-06-19
draft: false
---

这一章训练 interface、nil 和方法集的实战推演。

看到 interface 题，先判断四件事：

```text
接口值本身是否为 nil？
接口里有没有动态类型？
接口里的动态值是否为 nil？
方法是值接收者，还是指针接收者？
```

核心模型：

1. interface 值由两部分组成：动态类型 + 动态值。
2. 只有动态类型和动态值都为空时，interface 才等于 nil。
3. typed nil 放进 interface 后，interface 本身不等于 nil。
4. 类型断言失败时，单返回值形式会 panic，双返回值形式不会 panic。
5. 值接收者方法，值和指针都能调用；指针接收者方法，只有指针类型的方法集包含它。
6. 一个类型是否实现接口，看的是方法集，不是这个类型能不能“语法上调用”某个方法。

---

## 1. nil interface

题目：

```go
func main() {
	var x interface{}
	fmt.Println(x == nil)
}
```

答案：

```text
true
```

推演：

`x` 没有动态类型，也没有动态值，所以接口值本身是 nil。

模型：

```text
interface 的动态类型和值都为空，才等于 nil。
```

---

## 2. typed nil 放入 interface

题目：

```go
type User struct {
	Name string
}

func main() {
	var u *User = nil
	var x interface{} = u
	fmt.Println(x == nil)
}
```

答案：

```text
false
```

推演：

`x` 的动态类型是 `*User`，动态值是 nil。动态值虽然是 nil，但动态类型不为空，所以 `x != nil`。

模型：

```text
typed nil 放进 interface 后，interface 不等于 nil。
```

---

## 3. 返回 typed nil error

题目：

```go
type MyError struct{}

func (e *MyError) Error() string {
	return "my error"
}

func f() error {
	var e *MyError = nil
	return e
}

func main() {
	err := f()
	fmt.Println(err == nil)
}
```

答案：

```text
false
```

推演：

`error` 是接口。`f` 返回时，把 `*MyError` 类型的 nil 指针装进 error 接口里。接口有动态类型 `*MyError`，所以 `err != nil`。

模型：

```text
返回 error 时不要返回 typed nil。
```

---

## 4. 正确返回 nil error

题目：

```go
type MyError struct{}

func (e *MyError) Error() string {
	return "my error"
}

func f() error {
	var e *MyError = nil
	if e == nil {
		return nil
	}
	return e
}

func main() {
	err := f()
	fmt.Println(err == nil)
}
```

答案：

```text
true
```

推演：

如果没有错误，直接返回无类型的 `nil`，这样 error 接口的动态类型和动态值都为空。

模型：

```text
无错误时 return nil，不要 return typed nil。
```

---

## 5. interface 中的 typed nil 调方法

题目：

```go
type User struct{}

func (u *User) Hello() {
	fmt.Println("hello")
}

func main() {
	var u *User = nil
	var x interface{} = u
	x.(*User).Hello()
}
```

答案：

```text
hello
```

推演：

类型断言 `x.(*User)` 得到 nil 的 `*User` 指针。调用方法时，如果方法内部没有解引用 receiver，就不会 panic。这里 `Hello` 没有访问 `u` 的字段，所以能打印。

模型：

```text
nil 指针 receiver 可以调用方法，是否 panic 取决于方法内部是否解引用。
```

---

## 6. nil 指针 receiver 解引用

题目：

```go
type User struct {
	Name string
}

func (u *User) Hello() {
	fmt.Println(u.Name)
}

func main() {
	var u *User = nil
	u.Hello()
}
```

答案：

```text
panic
```

推演：

调用 nil 指针 receiver 的方法本身可以发生，但方法内部访问 `u.Name` 时需要解引用 nil 指针，因此 panic。

模型：

```text
nil 指针 receiver 不是调用时必 panic，而是解引用时 panic。
```

---

## 7. 类型断言成功

题目：

```go
func main() {
	var x interface{} = 123
	n := x.(int)
	fmt.Println(n + 1)
}
```

答案：

```text
124
```

推演：

`x` 的动态类型是 int，断言 `x.(int)` 成功。

模型：

```text
类型断言判断接口的动态类型。
```

---

## 8. 类型断言失败 panic

题目：

```go
func main() {
	var x interface{} = 123
	s := x.(string)
	fmt.Println(s)
}
```

答案：

```text
panic
```

推演：

`x` 的动态类型是 int，不是 string。单返回值类型断言失败会 panic。

模型：

```text
单返回值类型断言失败会 panic。
```

---

## 9. comma ok 类型断言

题目：

```go
func main() {
	var x interface{} = 123
	s, ok := x.(string)
	fmt.Println(s, ok)
}
```

答案：

```text
 false
```

推演：

双返回值类型断言失败不会 panic，会返回目标类型零值和 `ok=false`。string 的零值是空字符串，所以打印时前面是空的。

模型：

```text
双返回值类型断言失败：零值 + false。
```

---

## 10. type switch

题目：

```go
func printType(x interface{}) {
	switch v := x.(type) {
	case int:
		fmt.Println("int", v)
	case string:
		fmt.Println("string", v)
	default:
		fmt.Println("unknown")
	}
}

func main() {
	printType("go")
}
```

答案：

```text
string go
```

推演：

type switch 根据接口的动态类型匹配分支。`x` 的动态类型是 string，所以进入 string 分支。

模型：

```text
type switch 看接口动态类型。
```

---

## 11. 空接口接收任何值

题目：

```go
func main() {
	var x interface{}
	x = 1
	fmt.Println(x)
	x = "go"
	fmt.Println(x)
}
```

答案：

```text
1
go
```

推演：

空接口没有方法要求，任何类型都实现空接口。接口变量可以先后保存不同动态类型的值。

模型：

```text
interface{} 可以保存任何类型的值。
```

---

## 12. 值接收者实现接口

题目：

```go
type Speaker interface {
	Speak()
}

type User struct{}

func (User) Speak() {
	fmt.Println("speak")
}

func main() {
	var s Speaker
	var u User
	s = u
	s.Speak()
}
```

答案：

```text
speak
```

推演：

`Speak` 是值接收者方法，`User` 的方法集包含它，因此 `User` 实现了 `Speaker`。

模型：

```text
值接收者方法属于 T 的方法集。
```

---

## 13. 指针也能使用值接收者方法

题目：

```go
type Speaker interface {
	Speak()
}

type User struct{}

func (User) Speak() {
	fmt.Println("speak")
}

func main() {
	var s Speaker
	var u *User = &User{}
	s = u
	s.Speak()
}
```

答案：

```text
speak
```

推演：

值接收者方法也属于 `*User` 的方法集，所以 `*User` 也实现了 `Speaker`。

模型：

```text
值接收者：T 和 *T 都实现接口。
```

---

## 14. 指针接收者方法和接口赋值

题目：

```go
type Speaker interface {
	Speak()
}

type User struct{}

func (*User) Speak() {
	fmt.Println("speak")
}

func main() {
	var s Speaker
	var u User
	s = u
	s.Speak()
}
```

答案：

```text
编译错误
```

推演：

`Speak` 是指针接收者方法。`User` 的方法集不包含 `Speak`，只有 `*User` 的方法集包含 `Speak`。所以 `User` 没有实现 `Speaker`。

模型：

```text
指针接收者：只有 *T 实现接口，T 不实现。
```

---

## 15. 指针接收者正确赋值

题目：

```go
type Speaker interface {
	Speak()
}

type User struct{}

func (*User) Speak() {
	fmt.Println("speak")
}

func main() {
	var s Speaker
	var u User
	s = &u
	s.Speak()
}
```

答案：

```text
speak
```

推演：

`&u` 的类型是 `*User`，`*User` 的方法集包含指针接收者方法 `Speak`，因此可以赋值给接口。

模型：

```text
指针接收者实现接口时，要把 *T 放进接口。
```

---

## 16. 可以调用不等于实现接口

题目：

```go
type Speaker interface {
	Speak()
}

type User struct{}

func (*User) Speak() {
	fmt.Println("speak")
}

func main() {
	var u User
	u.Speak()

	var s Speaker = u
	_ = s
}
```

答案：

```text
编译错误
```

推演：

`u.Speak()` 能调用，是因为 `u` 是可寻址变量，编译器可以自动取地址变成 `(&u).Speak()`。

但接口赋值看的是 `User` 的方法集。`User` 的方法集不包含指针接收者方法，所以 `var s Speaker = u` 编译失败。

模型：

```text
能调用方法，不代表 T 的方法集实现了接口。
```

---

## 17. interface 比较

题目：

```go
func main() {
	var a interface{} = 1
	var b interface{} = 1
	fmt.Println(a == b)
}
```

答案：

```text
true
```

推演：

两个 interface 的动态类型都是 int，动态值也都是 1。int 可比较，所以接口比较结果为 true。

模型：

```text
interface 比较：动态类型相同，动态值可比较且相等。
```

---

## 18. interface 中放不可比较类型

题目：

```go
func main() {
	var a interface{} = []int{1}
	var b interface{} = []int{1}
	fmt.Println(a == b)
}
```

答案：

```text
panic
```

推演：

slice 不可比较。接口比较时，如果动态类型不可比较，会 panic。

模型：

```text
interface 动态值不可比较时，比较会 panic。
```

---

## 19. interface 和具体类型比较

题目：

```go
func main() {
	var x interface{} = 1
	fmt.Println(x == 1)
}
```

答案：

```text
true
```

推演：

比较时，非接口值 `1` 会转换为 interface 后再比较。动态类型都是 int，动态值都是 1，所以相等。

模型：

```text
interface 可以和可赋值的具体值比较。
```

---

## 20. typed nil 和具体 nil 比较

题目：

```go
type User struct{}

func main() {
	var u *User = nil
	var x interface{} = u
	fmt.Println(x == nil)
	fmt.Println(x == (*User)(nil))
}
```

答案：

```text
false
true
```

推演：

`x == nil` 比较的是接口本身是否为空。`x` 有动态类型 `*User`，所以不等于 nil。

`x == (*User)(nil)` 时，右侧也会作为 `*User` 类型的 nil 参与比较。两边动态类型和值都相同，所以为 true。

模型：

```text
typed nil interface 不等于 nil，但可以等于同类型 nil 指针。
```

