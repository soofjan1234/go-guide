[问题]
1. gmp抢占机制
2. channel阻塞场景
3. 内存泄漏、逃逸，写屏障
4. map结构
5. 协程使用场景
6. sync.Map、sync.Mutex和分段锁的使用场景

【答案】

## 1. GMP 抢占机制

### 协作式抢占（Go 1.14 前）
1. 编译器在函数入口的栈检查路径插入 `stack check` 汇编代码
2. 调度器发现 G 运行超过 10ms，给 G 打标记：`stackguard0 = stackPreempt`
3. G 运行到下一个函数调用时，执行 `stack check` 发现标记
4. G 主动调用 `runtime.goschedImpl`，让出 CPU

**问题**：`for {}` 无函数调用的死循环不容易被抢占

### 信号抢占（Go 1.14 起）
1. Go 给 M 注册 `sighandler`
2. sysmon 发现 M 上的 G 运行超过 10ms，向 M 发送 SIGURG 信号
3. 操作系统暂停 M，M 跳转执行 `sighandler`
4. 在 `sighandler` 中修改 M 的寄存器，强制插入 `asyncPreempt` 调用
5. M 恢复执行时，先跑 `asyncPreempt`，切换到 g0 栈
6. 在 g0 栈运行 `gopreempt_m`，把 G 踢走，M 找下一个 G

## 2. Channel 阻塞场景

### 发送阻塞
- **nil channel** 上发送
- 无缓冲 channel，且没有接收者在等
- 有缓冲 channel，且缓冲区已满

### 接收阻塞
- **nil channel** 上接收
- 无缓冲 channel，且没有发送者在等
- 有缓冲 channel，且缓冲区为空

### 完整流程
1. 发送时：先检查是否关闭 → 有接收者直接交接 → 看缓冲区 → 阻塞则入 `sendq` 并 `gopark`
2. 接收时：有发送者直接交接 → 看缓冲区 → 阻塞则入 `recvq` 并 `gopark`

## 3. 内存泄漏、逃逸、写屏障

### 内存泄漏
**常见原因**：
- 全局 map/缓存只加不减
- 文件、数据库连接、网络连接未关闭
- 注册回调/订阅却从不注销
- `time.After` 等在循环里误用
- goroutine 泄漏（阻塞在 chan、锁、网络读等，且仍有引用）

**排查**：
- pprof 查看函数执行时间和内存占用
- 压测复现，抓堆快照
- 观察 GC 趋势：`GODEBUG=gctrace=1`

### 内存逃逸
**定义**：编译期判断「生命周期是否超出当前栈帧」，导致分配到堆上

**常见逃逸场景**：
1. 闭包捕获外部变量
2. 方法内返回局部变量的指针
3. 向切片、通道加入指针或含指针的变量
4. 接口动态调用方法
5. 使用反射
6. 切片扩容

**验证**：`go build -gcflags="-m" .`

### 写屏障
**背景**：三色标记并发时，黑对象引用白对象会导致白对象被错误清理

**作用**：写指针时把旧值、新值相关对象标灰入队，防止错杀

## 4. Map 结构

### SwissTable（Go 1.24+）
- 多个 group 内存连续排列，每个 group 16 个槽位
- 每个槽位有 metadata（低 7 位 hash + 标志位：空、墓碑、满）
- **SIMD 优势**：一条指令同时比较 16 个 metadata，快速定位

### 整体结构
- `dirPtr`：指向 Table 数组或单 Group（<8 个）
- `dirLen`、`globalDepth`：用多少位哈希定位
- Table 包含 `groups` 和 `localDepth`

### 扩容
- **翻倍扩容**：容量*2 ≤ 1024，生成两倍大的表，一次性重哈希
- **分裂扩容**：容量*2 > 1024，生成两个最大表，按新的 localDepth 位分流

## 5. 协程使用场景

1. **数据传递**：两个协程之间传数据
2. **事件通知**：等待某个任务完成
3. **生产者/消费者**：持续生产消费，速度可能不一致
4. **限制并发数**：用缓冲 channel 做信号量
5. **多路复用与超时控制**：select + time.After
6. **任务取消**：关闭 channel 广播取消通知

### Goroutine 优势
- 初始栈小（KB 级），可动态扩缩容
- 主要在用户态调度，减少内核切换
- GMP 高效分发（本地优先 + 全局兜底 + 窃取均衡）
- 抢占机制避免长任务霸占 CPU
- 数量可以远高于线程，适合高并发

## 6. sync.Map、sync.Mutex 和分段锁的使用场景

### sync.Mutex
- **适用**：读写都频繁、临界区简单
- **特点**：互斥锁，同一时间只有一个 goroutine 能持有锁

### sync.RWMutex
- **适用**：读多写少
- **特点**：读写锁，读与读不互斥，写与读写都互斥

### sync.Map
- **适用**：多读少写、每个 goroutine 维护自己的 key
- **特点**：
  - 内置 read map 和 dirty map，读优先走 read map（无锁）
  - 用 LoadOrStore、LoadAndDelete、CAS 系列方法避免冲突
  - 少用 Range、Delete（会阻塞）
  - 大 value 用指针避免拷贝

### 分段锁
- **适用**：高并发、key 分布均匀
- **特点**：一个 map 分成多个段，每段各持一把锁，降低锁粒度