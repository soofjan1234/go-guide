---
title: pprof
weight: 15
date: 2026-07-09
draft: false
---

pprof 是 Go 自带的性能采样工具，用来回答一个很直接的问题：

```text
程序到底把 CPU、内存、goroutine、锁等待、阻塞时间花在哪里？
```

看到线上性能问题，先按这个模型判断：

```text
CPU 高，看 cpu profile
内存涨，看 heap profile
goroutine 涨，看 goroutine profile
锁竞争，看 mutex profile
阻塞等待，看 block profile
延迟抖动，看 profile 之外也要结合 trace、日志和监控
```

pprof 不是凭空给结论，它只是把采样结果聚合出来。真正排查时，要把 profile 和业务现象放在一起看：流量、QPS、错误率、延迟、GC、goroutine 数量、机器负载都要对上。

---

## 1. pprof 是什么

pprof 的核心是采样。

它不会记录每一次函数调用，而是在一段时间内按规则采样，然后统计哪些函数、哪些调用路径出现得最多。

常见 profile：

| profile | 主要用途 |
|---|---|
| `profile` | CPU 采样，常用来排查 CPU 飙高、接口变慢 |
| `heap` | 堆内存采样，常用来排查内存上涨、对象分配热点 |
| `goroutine` | goroutine 栈快照，常用来排查 goroutine 泄漏 |
| `mutex` | 锁竞争采样，常用来排查大量时间卡在锁上 |
| `block` | 阻塞采样，常用来排查 channel、select、锁等待等阻塞点 |
| `threadcreate` | 系统线程创建信息，通常用于定位线程异常增长 |

---

## 2. 如何开启 pprof

HTTP 服务里最常见的方式是导入 `net/http/pprof`：

```go
package main

import (
	"net/http"
	_ "net/http/pprof"
)

func main() {
	http.ListenAndServe("127.0.0.1:6060", nil)
}
```

`net/http/pprof` 会把调试入口注册到默认的 `http.DefaultServeMux` 上，默认路径是：

```text
/debug/pprof/
```

如果业务服务本身不用默认路由，通常会单独起一个只监听本机或内网的调试端口：

```go
go func() {
	// pprof 端口只给排查使用，不应该直接暴露到公网。
	if err := http.ListenAndServe("127.0.0.1:6060", nil); err != nil {
		panic(err)
	}
}()
```

线上使用要注意：

1. 不要把 pprof 端口暴露到公网。
2. 尽量只监听 `127.0.0.1`、内网地址，或者放在有鉴权的运维入口后面。
3. CPU profile 会增加一些运行开销，抓取时间不要无脑拉很长。
4. mutex、block profile 需要额外开启采样，线上要谨慎设置采样率。

---

## 3. 常用入口

常用地址：

```text
http://127.0.0.1:6060/debug/pprof/
http://127.0.0.1:6060/debug/pprof/profile?seconds=30
http://127.0.0.1:6060/debug/pprof/heap
http://127.0.0.1:6060/debug/pprof/goroutine
http://127.0.0.1:6060/debug/pprof/goroutine?debug=2
http://127.0.0.1:6060/debug/pprof/mutex
http://127.0.0.1:6060/debug/pprof/block
http://127.0.0.1:6060/debug/pprof/threadcreate
```

常用命令：

```bash
go tool pprof http://127.0.0.1:6060/debug/pprof/profile?seconds=30
go tool pprof http://127.0.0.1:6060/debug/pprof/heap
go tool pprof http://127.0.0.1:6060/debug/pprof/goroutine
```

也可以直接打开 Web 页面：

```bash
go tool pprof -http=:8080 http://127.0.0.1:6060/debug/pprof/heap
```

进入 pprof 交互模式后，常用命令：

```text
top        看热点函数
top -cum   看累计调用路径
list       看函数对应源码行
peek       看函数调用关系
web        生成调用图
traces     看采样调用栈
```

---

## 4. CPU 飙高怎么排查

CPU 高时，先抓 CPU profile：

```bash
go tool pprof http://127.0.0.1:6060/debug/pprof/profile?seconds=30
```

进入交互模式后先看：

```text
top
top -cum
```

`top` 里最重要的是两个指标：

| 指标 | 含义 |
|---|---|
| `flat` | 函数自身消耗的 CPU 时间 |
| `cum` | 函数自身加上子调用累计消耗的 CPU 时间 |

判断方式：

1. `flat` 高，说明 CPU 主要消耗在这个函数自身。
2. `cum` 高但 `flat` 不高，说明这个函数本身不重，但它调用出去的路径很重。
3. `top -cum` 更适合看入口链路，比如某个 handler、worker、定时任务触发了重逻辑。

定位到函数后，用 `list` 看具体源码行：

```text
list handleRequest
```

CPU 高的常见原因：

1. 死循环、忙等循环。
2. 大量 JSON 序列化、反序列化。
3. 正则表达式、字符串拼接、加解密等计算热点。
4. 大量小对象分配导致 GC 压力变高。
5. 锁竞争严重，业务 goroutine 反复抢锁。
6. 日志量过大，格式化和 IO 拖慢主路径。

排查模型：

```text
先看 top 找热点函数
再看 top -cum 找入口路径
再用 list 定位源码行
最后结合业务流量判断是不是正常热点
```

---
## 5. 内存上涨怎么排查

内存问题先抓 heap：

```bash
go tool pprof http://127.0.0.1:6060/debug/pprof/heap
```

heap profile 里最容易混淆的是这几组指标：

| 指标 | 含义 |
|---|---|
| `alloc_space` | 程序启动以来累计分配过多少内存 |
| `inuse_space` | 当前仍然存活、没有被 GC 回收的内存 |
| `alloc_objects` | 程序启动以来累计分配过多少对象 |
| `inuse_objects` | 当前仍然存活的对象数量 |

排查内存泄漏，重点看 `inuse_space` 和 `inuse_objects`。

```text
alloc_space 高，只能说明历史分配多。
inuse_space 持续上涨，才更像当前存活对象越来越多。
```

常用方式：

```text
top
top -cum
list 函数名
```

如果要看当前存活内存：

```text
sample_index=inuse_space
top
```

如果要看累计分配热点：

```text
sample_index=alloc_space
top
```

内存上涨的常见原因：

1. 全局 map、缓存只加不删。
2. slice 截取后引用了底层大数组。
3. goroutine 泄漏，导致栈和闭包捕获对象一直可达。
4. 连接、文件、响应体没有关闭。
5. 定时器、回调、订阅对象没有释放。
6. 大量临时对象分配，虽然不泄漏，但会造成 GC 压力。

判断是不是泄漏，可以抓两次 heap 做对比：

```bash
go tool pprof -base old.pb.gz new.pb.gz
```

模型：

```text
只涨 alloc_space，不一定是泄漏
持续涨 inuse_space，才重点怀疑存活对象没释放
heap 要结合 GC、流量、缓存策略一起看
```

---

## 6. goroutine 泄漏怎么排查

goroutine 数持续上涨时，先看 goroutine profile：

```bash
go tool pprof http://127.0.0.1:6060/debug/pprof/goroutine
```

很多时候直接看文本栈更快：

```bash
curl http://127.0.0.1:6060/debug/pprof/goroutine?debug=2
```

重点看大量重复的栈。

常见阻塞位置：

```text
chan send        卡在发送，没有接收方
chan receive     卡在接收，没有发送方，也没人 close
select           select 分支没有退出条件
sync.Mutex       卡在锁上
net/http         卡在网络读写或连接未释放
time.Sleep       worker 睡眠循环没有退出条件
```

典型泄漏代码：

```go
func worker(ch <-chan int) {
	for {
		v := <-ch
		_ = v
	}
}
```

如果 `ch` 没有人继续发送，也不会关闭，这个 goroutine 会一直阻塞。

更稳的写法是监听退出信号：

```go
func worker(ctx context.Context, ch <-chan int) {
	for {
		select {
		case <-ctx.Done():
			return
		case v, ok := <-ch:
			if !ok {
				return
			}
			_ = v
		}
	}
}
```

goroutine 泄漏排查模型：

```text
先看 goroutine 数是否持续上涨
再抓 goroutine?debug=2
找大量重复栈
看它们卡在 channel、锁、网络、select 还是 sleep
最后反推谁负责关闭、取消、释放
```

---

## 7. mutex 和 block 怎么用

mutex profile 用来看锁竞争，但默认采样率通常不是你想要的状态。排查前可以显式设置：

```go
runtime.SetMutexProfileFraction(1)
```

含义：

```text
记录互斥锁竞争事件，值越小采样越少，1 表示尽量记录每次竞争。
```

block profile 用来看阻塞等待，需要设置：

```go
runtime.SetBlockProfileRate(1)
```

含义：

```text
记录 goroutine 阻塞事件，1 表示尽量记录每次阻塞。
```

然后抓：

```bash
go tool pprof http://127.0.0.1:6060/debug/pprof/mutex
go tool pprof http://127.0.0.1:6060/debug/pprof/block
```

mutex 和 block 的区别：

| profile | 关注点 |
|---|---|
| `mutex` | goroutine 等锁花了多久 |
| `block` | goroutine 在 channel、select、锁等阻塞点等了多久 |

注意：

1. 这两个 profile 有额外开销，不要长期高采样率开启。
2. 线上排查可以临时打开，抓完再关掉或恢复采样率。
3. 如果只是 CPU 高，不一定先看 mutex；如果延迟高但 CPU 不高，mutex 和 block 往往更有价值。
