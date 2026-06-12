---
title: 关键字
weight: 6
date: 2026-05-21
draft: false
---

## defer +3


![](pic/关键字.defer.png)

特点：用于收尾，比如关闭连接、通道等，先进后出，os.Exit()不会触发

```go
func f() {
    a := 1
    defer fmt.Println(a)
    a++
    defer func(){
        defer fmt.Println(a)
    }()
    a++
}
```

这段代码的输出是：3和1

`defer fmt.Println(a)`，它的参数在「登记 defer」这一刻就求值、定死了；真正延后的是「调用」本身，不是「再算一遍参数」
`defer func() { fmt.Println(a) }()`， 后面是一个函数调用，按规则：没有写在参数列表里的东西，就不会在登记时求值。a 出现在函数体内部，属于闭包捕获的变量；只有函数被调用时才会访问。

## make 和 new +2

![](pic/关键字.make与new.png)

new是针对所有对象，返回的是 *T，指向一块已分配且置为零值的内存，指针本身 不是 nil。
make针对的切片、map、通道，可以指定长度容量，返回的是已初始化好的值

## panic +1

![](pic/关键字.panic.png)

**触发情况**
1. 手动调用
2. 运行时触发：数组越界、空指针、OOM

一旦某个函数里发生 `panic`：

1. 当前函数**立刻停止后续普通代码**的执行；
2. 依次执行当前函数中已经注册的 `defer`；
3. 返回到上一层调用者，继续做同样的“执行 defer → 返回”；
4. 如果一路都没人 `recover` 它，最终由 `runtime` 打印堆栈并**终止程序**。

```go
func f() {
    defer fmt.Println("1")
    defer fmt.Println("2")
    panic("panic")
    defer fmt.Println("3")
}
```

输出为2和1

### recover 要点

recover可以对panic进行恢复

**为nil的原因可能有**：
1. 未发生panic
2. 不在defer里面写recover
3. panic(nil) 时，recover() 也会得到 nil



