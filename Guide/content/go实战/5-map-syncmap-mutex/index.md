---
title: map / sync.Map / mutex
weight: 5
date: 2026-06-19
draft: false
---

这一章训练 map 并发和并发容器选择。

看到 map 题，先判断五件事：

```text
map 是否已经初始化？
当前操作是读、写、删除，还是遍历？
是否有多个 goroutine 并发访问？
是否需要维护多个字段之间的一致性？
读多写少、写多、还是 key 分散？
```

核心模型：

1. nil map 可以读、可以 delete、可以 range，但不能写。
2. 原生 map 不是并发安全的，并发读写或并发写写可能触发 fatal error。
3. `fatal error: concurrent map writes` 不是普通 panic，不能依赖 recover 兜住。
4. 写多或需要维护业务不变量时，优先 `map + Mutex/RWMutex`。
5. key 分散、并发度高时，可以考虑分段锁。
6. `sync.Map` 适合读多写少、写一次读多次、或者多个 goroutine 操作不相交 key 的场景。
7. `sync.Map` 牺牲了类型安全和部分业务表达能力，不是所有并发 map 的默认选择。

---

## 1. nil map 读

题目：

```go
func main() {
	var m map[string]int
	fmt.Println(m["a"])
}
```

答案：

```text
0
```

推演：

nil map 可以读。读取不存在的 key，会返回 value 类型的零值。这里 value 是 int，所以返回 0。

模型：

```text
nil map 可以读，读不到返回零值。
```

---

## 2. nil map 写

题目：

```go
func main() {
	var m map[string]int
	m["a"] = 1
	fmt.Println(m)
}
```

答案：

```text
panic: assignment to entry in nil map
```

推演：

nil map 没有底层哈希表结构，不能写入。写入 nil map 会 panic。

模型：

```text
nil map 不能写，写前必须 make。
```

---

## 3. nil map delete

题目：

```go
func main() {
	var m map[string]int
	delete(m, "a")
	fmt.Println("done")
}
```

答案：

```text
done
```

推演：

对 nil map 执行 delete 是安全的，不会 panic，也不会产生任何效果。

模型：

```text
delete nil map 安全。
```

---

## 4. nil map range

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

nil map 的长度是 0，range nil map 循环 0 次。

模型：

```text
range nil map 安全，循环 0 次。
```

---

## 5. 读不存在的 key

题目：

```go
func main() {
	m := map[string]int{"a": 1}
	v, ok := m["b"]
	fmt.Println(v, ok)
}
```

答案：

```text
0 false
```

推演：

map 读取可以使用双返回值。key 不存在时，value 是零值，`ok=false`。

模型：

```text
区分零值和不存在，用 comma ok。
```

---

## 6. key 存在但 value 是零值

题目：

```go
func main() {
	m := map[string]int{"a": 0}
	v, ok := m["a"]
	fmt.Println(v, ok)
}
```

答案：

```text
0 true
```

推演：

虽然 value 是 0，但 key 确实存在，所以 `ok=true`。

模型：

```text
value 零值不代表 key 不存在。
```

---

## 7. map 遍历顺序

题目：

```go
func main() {
	m := map[string]int{"a": 1, "b": 2, "c": 3}
	for k, v := range m {
		fmt.Println(k, v)
	}
}
```

答案：

```text
顺序不固定
```

推演：

Go 不保证 map 遍历顺序。同一个 map 多次遍历，顺序也可能不同。

模型：

```text
不要依赖 map 遍历顺序。
```

---

## 8. 遍历时删除当前 key

题目：

```go
func main() {
	m := map[int]int{1: 1, 2: 2, 3: 3}
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

range map 时删除当前 key 是允许的。每次遍历到一个 key 就删除，最终 map 为空。

模型：

```text
遍历 map 时可以删除当前 key。
```

---

## 9. 遍历时新增 key

题目：

```go
func main() {
	m := map[int]int{1: 1}
	for k := range m {
		fmt.Println(k)
		m[2] = 2
	}
}
```

答案：

```text
可能只打印 1，也可能打印 1 和 2
```

推演：

遍历过程中新增的 key，本轮 range 可能看到，也可能看不到。Go 不保证。

模型：

```text
遍历 map 时新增 key，是否被本轮遍历到不确定。
```

---

## 10. 并发写 map

题目：

```go
func main() {
	m := make(map[int]int)
	var wg sync.WaitGroup

	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			for j := 0; j < 1000; j++ {
				m[j] = i
			}
		}(i)
	}

	wg.Wait()
	fmt.Println(len(m))
}
```

答案：

```text
可能 fatal error: concurrent map writes
```

推演：

原生 map 不支持多个 goroutine 同时写。并发写会破坏 map 内部状态，runtime 检测到后会抛出 fatal error。

模型：

```text
原生 map 并发写不安全。
```

---

## 11. 并发读写 map

题目：

```go
func main() {
	m := map[int]int{1: 1}

	go func() {
		for {
			m[1] = 2
		}
	}()

	for {
		_ = m[1]
	}
}
```

答案：

```text
可能 fatal error: concurrent map read and map write
```

推演：

一个 goroutine 写 map，另一个 goroutine 同时读 map，也是不安全的。runtime 可能检测到并报 fatal error。

模型：

```text
原生 map 并发读写不安全。
```

---

## 12. recover 不能兜住 concurrent map fatal

题目：

```go
func main() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Println("recover", r)
		}
	}()

	m := make(map[int]int)
	go func() {
		for {
			m[1] = 1
		}
	}()
	for {
		m[2] = 2
	}
}
```

答案：

```text
可能 fatal error: concurrent map writes
```

推演：

`concurrent map writes` 是 runtime fatal error，不是普通 panic。不能指望外层 recover 像接住普通 panic 一样兜住它。

模型：

```text
map 并发 fatal 不能靠 recover 当并发控制。
```

---

## 13. 用 Mutex 保护 map

题目：

```go
func main() {
	m := make(map[int]int)
	var mu sync.Mutex
	var wg sync.WaitGroup

	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			for j := 0; j < 1000; j++ {
				mu.Lock()
				m[j] = i
				mu.Unlock()
			}
		}(i)
	}

	wg.Wait()
	fmt.Println(len(m))
}
```

答案：

```text
1000
```

推演：

所有写 map 的操作都被同一把 Mutex 保护，所以不会并发写。key 是 0 到 999，最终长度是 1000。

模型：

```text
map + Mutex 是最直接的并发安全方案。
```

---

## 14. 正确的递增

题目：

```go
type Counter struct {
	mu sync.Mutex
	m  map[string]int
}

func (c *Counter) Inc(k string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.m[k]++
}
```

答案：

```text
并发安全
```

推演：

`m[k]++` 不是原子操作，包含读、加、写。这里用同一把 Mutex 保护完整读-改-写过程，所以不会丢更新。

模型：

```text
复合操作要整体加锁。
```

---

## 15. sync.Map Store / Load

题目：

```go
func main() {
	var m sync.Map
	m.Store("a", 1)
	v, ok := m.Load("a")
	fmt.Println(v, ok)
}
```

答案：

```text
1 true
```

推演：

`sync.Map` 的 key 和 value 都是 `any`。`Store` 写入，`Load` 读取，存在则返回 value 和 `ok=true`。

模型：

```text
sync.Map 用 Store/Load，不用下标语法。
```

---

## 16. sync.Map 类型断言

题目：

```go
func main() {
	var m sync.Map
	m.Store("a", 1)
	v, _ := m.Load("a")
	n := v.(int)
	fmt.Println(n + 1)
}
```

答案：

```text
2
```

推演：

`sync.Map` 返回的是 `any`，使用前通常需要类型断言。这里存入的是 int，所以 `v.(int)` 成功。

模型：

```text
sync.Map 牺牲类型安全，需要类型断言。
```

---

## 17. sync.Map LoadOrStore

题目：

```go
func main() {
	var m sync.Map
	actual, loaded := m.LoadOrStore("a", 1)
	fmt.Println(actual, loaded)
	actual, loaded = m.LoadOrStore("a", 2)
	fmt.Println(actual, loaded)
}
```

答案：

```text
1 false
1 true
```

推演：

第一次 key 不存在，存入 1，返回 `loaded=false`。第二次 key 已存在，不会覆盖成 2，而是返回已有值 1 和 `loaded=true`。

模型：

```text
LoadOrStore：不存在才写入，存在则返回旧值。
```

---

## 18. sync.Map 不是业务事务

题目：

```go
func main() {
	var m sync.Map
	m.Store("a", 0)

	var wg sync.WaitGroup
	for i := 0; i < 1000; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			v, _ := m.Load("a")
			m.Store("a", v.(int)+1)
		}()
	}
	wg.Wait()

	v, _ := m.Load("a")
	fmt.Println(v)
}
```

答案：

```text
结果可能小于 1000
```

推演：

`Load` 和 `Store` 各自是并发安全的，但 `Load -> +1 -> Store` 这个组合不是原子的。多个 goroutine 可能读到同一个旧值，再覆盖写回，导致丢更新。

模型：

```text
sync.Map 单个操作安全，不代表复合业务操作原子。
```

---

## 19. sync.Map Range 时修改

题目：

```go
func main() {
	var m sync.Map
	m.Store("a", 1)
	m.Store("b", 2)

	m.Range(func(k, v any) bool {
		fmt.Println(k, v)
		m.Delete(k)
		return true
	})
}
```

答案：

```text
可以运行，但遍历顺序不固定
```

推演：

`sync.Map.Range` 可以和其他方法并发调用。Range 不保证一致快照，遍历顺序也不固定。遍历中删除 key 是允许的，但不要依赖复杂的遍历一致性。

模型：

```text
sync.Map Range 不是一致性快照。
```

---

## 20. 什么时候不用 sync.Map

题目：

```go
type UserState struct {
	Online bool
	Score  int
}

// 需要保证 Online 和 Score 按业务规则一起更新。
```

答案：

```text
更适合 map + Mutex
```

推演：

如果一次业务操作需要同时检查和更新多个字段，或者多个 key 之间有一致性约束，`sync.Map` 不好表达这个临界区。使用 `map + Mutex` 可以把整段业务逻辑锁住，更容易维护不变量。

模型：

```text
需要维护业务不变量时，锁普通 map 更清晰。
```

---

## 21. 分段锁适用场景

题目：

```text
有一个高并发计数服务，key 很多，写入很多，但不同 goroutine 通常写不同 key。
应该用一把全局 Mutex，还是可以考虑分段锁？
```

答案：

```text
可以考虑分段锁
```

推演：

一把全局 Mutex 会让所有 key 的写入串行化。分段锁按 hash 把 key 分到不同 shard，每个 shard 有自己的 map 和锁。不同 shard 可以并发写，降低锁竞争。

模型：

```text
key 分散且写多，可以用 sharded map 降低锁竞争。
```

---

## 22. sync.Map 适用场景

题目：

```text
缓存中 key 写入一次后会被读很多次，很少更新和删除。
适合用 sync.Map 吗？
```

答案：

```text
适合
```

推演：

这是 `sync.Map` 的典型适用场景：写一次、读多次。它可以减少读路径上的锁竞争。

模型：

```text
sync.Map 适合写一次读多次、读多写少。
```

---

## 23. sync.Map 新实现怎么理解

题目：

```text
面试官问：sync.Map 现在是不是变成了 HashTrieMap？
应该怎么答？
```

答案：

```text
要区分版本和构建条件。
```

推演：

经典实现是 `read map + dirty map + misses`。新版本源码中存在 `goexperiment.synchashtriemap` 实验实现，底层是 concurrent hash-trie：对 key 做 hash，然后按 hash 的 bit 分层查找和更新。

但无论实现是 read/dirty 还是 HashTrieMap，使用层面的判断不变：它适合读多写少、写一次读多次，或者多个 goroutine 操作不相交 key；写多且需要维护业务不变量时，普通 map 加锁通常更直接。

模型：

```text
实现会演进，适用场景判断不能丢。
```
