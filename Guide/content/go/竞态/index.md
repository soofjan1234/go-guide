---
title: 竞态
weight: 16
date: 2026-07-10
draft: false
---

## 竞态和数据竞争 

### 竞态 Race Condition

**竞态**是一类更大的问题：程序最终结果依赖多个并发操作的执行时序，而这个时序又不是业务逻辑真正想依赖的东西。

简单说就是：**谁先执行、谁后执行，会改变结果**。

```go
var balance = 100

func withdraw(name string, amount int) {
	if balance >= amount {
		time.Sleep(time.Millisecond)
		balance -= amount
		fmt.Println(name, "success")
	}
}

func main() {
	go withdraw("A", 80)
	go withdraw("B", 80)
	time.Sleep(time.Second)
	fmt.Println(balance)
}
```

两个 goroutine 都可能先看到 `balance >= 80`，然后都扣款成功，最后余额变成负数。

这里的问题本质不是“扣款语句写错了”，而是**检查余额**和**扣减余额**这两个动作没有被当成一个不可打断的整体。

### 数据竞争 Data Race

**数据竞争**是竞态里更具体、更底层的一种：多个 goroutine 同时访问同一块内存，至少一个是写，并且这些访问之间没有同步关系。

```go
var n int

func main() {
	for i := 0; i < 1000; i++ {
		go func() {
			n++
		}()
	}

	time.Sleep(time.Second)
	fmt.Println(n)
}
```

`n++` 不是一个原子动作，它大致会经历：

1. 从内存读取 `n`
2. 在寄存器里加 1
3. 把结果写回内存

多个 goroutine 同时做这三步时，后写入的人可能覆盖前面已经写好的结果，所以最后大概率不是 1000。

### 二者关系

- **数据竞争一定是竞态**：因为访问顺序会影响内存里的最终值。
- **竞态不一定是数据竞争**：即使所有内存访问都被锁保护了，业务流程仍然可能因为时序错误出问题。

比如下面这段代码没有裸写共享变量，但仍然可能发生“先检查、后使用”的竞态：

```go
if userCanBuy(userID) {
	// 这里到真正下单之间，用户状态可能已经被其他请求改掉。
	createOrder(userID)
}
```

所以可以这样记：

```text
Race Condition 更偏业务结果：并发时序影响了正确性。
Data Race 更偏内存访问：共享内存被并发读写且缺少同步。
```

## 竞态是如何产生的 

竞态通常来自三个条件同时出现：

1. **共享状态**：多个 goroutine 能看到同一份数据，比如全局变量、map、切片、结构体字段、数据库记录、缓存状态。
2. **并发执行**：这些 goroutine 的执行顺序不固定，调度器、I/O、GC、系统调用都可能改变实际顺序。
3. **缺少同步或同步范围不对**：没有锁、channel、原子操作等同步手段，或者只保护了单次读写，没有保护完整业务不变量。

常见场景：

### 读改写不是原子操作

```go
counter++
```

这一行看起来只有一句，但它不是原子操作。并发执行时可能丢失更新。

### map 并发读写

```go
m := map[string]int{}

go func() {
	m["a"] = 1
}()

go func() {
	fmt.Println(m["a"])
}()
```

Go 原生 `map` 不支持并发读写。并发写、读写交错时，轻则数据不一致，重则直接报错：

```text
fatal error: concurrent map read and map write
```

### 闭包捕获外部共享变量

```go
current := 0

for i := 0; i < 3; i++ {
	current = i
	go func() {
		fmt.Println(current)
	}()
}
```

多个 goroutine 共享了外层的 `current`，打印结果就取决于 goroutine 真正运行时 `current` 已经被改成了什么。

写并发代码时，要明确每个 goroutine 使用的是**自己的副本**还是**共享变量**。

### 同步粒度太小

```go
mu.Lock()
ok := stock > 0
mu.Unlock()

if ok {
	mu.Lock()
	stock--
	mu.Unlock()
}
```

单独看每次读写都有锁，但“判断库存”和“扣减库存”被拆开了，中间可能被其他 goroutine 插队。

正确保护的不是某一行代码，而是业务不变量：**库存大于 0 时才能扣减**。

## 如何检测竞态 

### 用 race detector 检测数据竞争

Go 自带 race detector，可以在运行测试、运行程序、编译程序时打开：

```powershell
go test -race ./...
go run -race main.go
go build -race ./...
```

如果检测到数据竞争，会打印类似信息：

```text
WARNING: DATA RACE
Read at 0x...
Previous write at 0x...
Goroutine 8 ...
Goroutine 7 ...
```

重点看三类信息：

1. 哪个地址发生了并发访问
2. 哪个 goroutine 在读，哪个 goroutine 在写
3. 调用栈分别指向哪些代码行

race detector 很适合抓**内存层面的数据竞争**，但它不是万能的：

- 没跑到的代码路径，它检测不到。
- 业务层竞态不一定能报出来，比如“两个请求都通过库存校验”。
- 开启后程序会变慢，通常用于测试环境、CI 或本地排查，不建议线上常驻开启。

### 用压力测试放大时序问题

竞态往往和时序有关，所以单次运行不一定复现。可以多跑几次：

```powershell
go test -race -count=100 ./...
```

如果是某个具体测试：

```powershell
go test -race -run TestOrderCreate -count=100 ./...
```

### 用日志和断言确认业务不变量

业务竞态要靠业务不变量来抓。

比如库存不能为负、订单不能重复支付、同一个任务不能被两个 worker 同时领取，这些都应该有明确断言或唯一约束。

```go
if stock < 0 {
	panic("stock must not be negative")
}
```

工程里更常见的做法是：

- 数据库唯一索引兜底：防止重复创建。
- 条件更新兜底：`WHERE stock > 0`。
- 状态机校验：只允许从合法旧状态转到新状态。
- 测试里构造并发请求，验证最终状态。

## 如何消灭竞态 +3

### 1. 不共享：每个 goroutine 只处理自己的数据

最好的同步，是尽量不共享。

```go
func worker(nums []int) int {
	sum := 0
	for _, n := range nums {
		sum += n
	}
	return sum
}
```

如果每个 goroutine 只处理自己的局部变量，天然就没有数据竞争。

### 2. 用 Mutex 保护临界区

共享状态必须读改写时，用锁把完整临界区包起来。

```go
var (
	mu      sync.Mutex
	counter int
)

func inc() {
	mu.Lock()
	defer mu.Unlock()

	counter++
}
```

关键点：锁要保护的是**完整不变量**，不是只保护某一次读或某一次写。

库存扣减应该这样：

```go
func deduct() bool {
	mu.Lock()
	defer mu.Unlock()

	if stock <= 0 {
		return false
	}
	stock--
	return true
}
```

### 3. 用 channel 串行化所有权

如果一个状态只允许一个 goroutine 修改，可以把它放到专门的 goroutine 里，通过 channel 发送请求。

```go
type req struct {
	delta int
	done  chan int
}

func counterLoop(ch <-chan req) {
	n := 0
	for r := range ch {
		n += r.delta
		r.done <- n
	}
}
```

这类写法的核心是：**状态属于一个 goroutine，其他 goroutine 只能发消息，不能直接改状态**。

### 4. 用 atomic 处理简单数值

如果只是计数器、开关位这类简单状态，可以用 `sync/atomic`。

```go
var n atomic.Int64

func inc() {
	n.Add(1)
}

func value() int64 {
	return n.Load()
}
```

atomic 适合很小的、独立的状态。只要涉及多个字段之间的一致性，比如“余额和流水要一起更新”，通常还是应该用锁或事务。

### 5. 用不可变对象和拷贝

读多写少时，可以让读者永远读不可变快照，写者创建新对象再替换。

```go
type Config struct {
	Timeout time.Duration
	Addr    string
}

var current atomic.Value

func loadConfig() Config {
	return current.Load().(Config)
}

func storeConfig(c Config) {
	current.Store(c)
}
```

读取方拿到的是一个值拷贝，不会和写入方同时修改同一个对象。

### 6. 在外部系统里用事务和约束兜底

很多竞态不是发生在 Go 进程内，而是发生在多个请求、多个服务、多个实例之间。

比如扣库存、抢优惠券、任务领取，不能只靠进程内 `sync.Mutex`，因为请求可能落在不同机器上。

常见兜底方式：

- 数据库事务
- 乐观锁版本号
- 唯一索引
- 条件更新：`UPDATE ... WHERE stock > 0`
- 分布式锁
- 幂等键

## 面试回答 +1

可以这样回答：

竞态是并发程序的结果依赖执行时序，数据竞争是多个 goroutine 同时访问同一内存，至少一个写，并且没有同步关系。数据竞争一定是竞态，但竞态不一定是数据竞争。

竞态通常来自共享状态、并发执行和同步缺失。典型例子是 `counter++`、map 并发读写、先检查再执行、库存扣减这类读改写流程。

检测上，Go 可以用 `go test -race ./...` 打开 race detector，它能发现内存层面的 data race，但业务竞态要靠压力测试、日志、断言、唯一约束和状态机校验来发现。

解决上，优先减少共享；必须共享时，用 `sync.Mutex` 保护完整临界区，用 channel 串行化所有权，用 `sync/atomic` 处理简单计数；跨进程场景还要靠数据库事务、唯一索引、条件更新、幂等键等机制兜底。
