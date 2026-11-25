## 客户端取消请求后，怎么继续补记用量？

客户端取消流式请求后，如果还要把已生成的 token 用量记入数据库，可以保留原请求的 `traceID`，给补记单独设一个超时。

直接用 `context.WithTimeout(reqCtx, 2*time.Second)`，子 Context 会继承原请求的取消信号。如果 `reqCtx` 已经取消，子 Context 一创建就会被取消。

```go
base := context.WithoutCancel(reqCtx)
logCtx, cancel := context.WithTimeout(base, 2*time.Second)
defer cancel()

return saveUsage(logCtx)
```

`WithoutCancel` 保留原 Context 里的值，包括通过它传递的 `traceID`，同时解除原请求的取消信号和截止时间。再用 `WithTimeout` 从现在开始给补记两秒，把 `logCtx` 传给数据库调用。

## `omitempty` 和 `omitzero` 有什么区别？

`omit` 是「省略」。在 Go 的 `encoding/json` 里，这两个标签都在把结构体编码成 JSON 时决定要不要写出字段。

- `omitempty` 是 **omit if empty**，空值就省略。数字 `0`、`nil` 和长度为 `0` 的切片都算空。
- `omitzero` 是 **omit if zero**，类型的零值就省略。有 `IsZero() bool` 方法时，由它判断。这个标签从 Go 1.24 开始支持。

| Go 字段值 | `omitempty` | `omitzero` |
| --- | --- | --- |
| `float64(0)` | 省略 | 省略 |
| `[]int(nil)` | 省略 | 省略 |
| `[]int{}` | 省略，因为长度是 `0` | 保留为 `[]`，因为切片的零值是 `nil` |
| `time.Time{}` | 保留 | 省略，因为 `IsZero()` 返回 `true` |

**网关例子**。用 `float64` 接收 `temperature` 时，「没传」和「明确传 `0`」都得到 `0`。要保留这层区别，可以用 `*float64` 搭配 `omitempty`。没传时指针是 `nil`，字段会省略。传 `0` 时指针指向 `0`，输出会保留 `"temperature":0`。

## `GOMEMLIMIT` 能干什么？

GOMEMLIMIT 给 Go 运行时设一个软内存目标。接近这个目标时，Go 会更积极地做 GC。容器上限是 4 GB 的话，我会给运行时统计之外的内存和流量尖峰留余量，再根据压测定这个值。如果大量请求还在使用那些内存，GC 回收不了，进程仍可能触发 OOM

## 并发发多个请求，有一个失败，怎么全部取消？

用 `errgroup.WithContext(parent)`。每个子协程通过 `g.Go` 启动，并用 `http.NewRequestWithContext` 把同一个派生 Context 传给 HTTP 请求。任意子协程返回错误，`errgroup` 就会取消这个 Context，正在进行的请求会收到取消信号。最后用 `g.Wait()` 等所有子协程退出，并返回第一个错误。

如果业务上把 HTTP `4xx`、`5xx` 算作失败，就检查 `StatusCode` 并主动返回错误。如果子协程还要往 Channel 发结果，用 `select` 同时等发送和 `ctx.Done()`，让它在取消后也能退出。

## 怎么确保主流程退出时，子协程也退出？

主流程在返回前先发停止信号，再用 `sync.WaitGroup` 等子协程都返回。

- 用 `context.WithCancel` 时，主流程调用 `cancel()`，子协程监听 `ctx.Done()`，并把 `ctx` 传给支持取消的 HTTP 或数据库调用。
- 用 `stop := make(chan struct{})` 时，主流程调用 `close(stop)`，所有监听 `<-stop` 的子协程都能收到停止信号。子协程等任务或发结果时，可以用 `select` 同时监听 `stop`。

子协程退出时通过 `defer wg.Done()` 通知主流程。主流程发完停止信号就调用 `wg.Wait()`，等全部退出后再返回。
