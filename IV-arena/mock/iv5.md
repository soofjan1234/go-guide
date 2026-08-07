1. MySQL查询优化
2. Redis热点Key发现，优化
3. GO
    1. fd是什么
4. 运维
    1. 限流
    2. k8s的基本架构
5. 云端
    1. 混合加密
    2. 秘钥分发
6. 文件索引
    1. fsnotify 为什么会有内存开销
    2. windows、mac的文件监听
    3. 百万级文件同步测试过吗
7. 场景题
    1. 官网访问慢怎么排查
    2. 部分下单失败怎么排查

[答案]
## MySQL查询优化

1. 确认是否稳定复现。
2. 定位具体哪条 SQL 慢。
3. 用 EXPLAIN / EXPLAIN ANALYZE 查看执行计划，重点关注 type、key、rows、Extra。
4. 检查索引是否命中，有没有索引失效。
5. 分析 SQL 本身，是否存在 SELECT *、返回数据过多、复杂 JOIN、排序或分组等问题。
6. 检查是否存在锁等待，事务过长。
7. 检查系统资源，例如 CPU、磁盘 I/O、内存是否成为瓶颈。
8. 优化后再次验证，确保确实改善。

## Redis热点Key发现，优化

### 发现

1. redis-cli --hotkeys（推荐）：使用 LFU（Least Frequently Used）算法遍历所有 Key，直接找出最高频访问的 Key。
    - 前提条件： 内存淘汰策略必须设置为 LFU 机制
2. MONITOR命令：实时打印 Redis 接收到的所有命令
3. 客户端 SDK 统计（如 Lettuce/Jedis 拦截）

### 优化

1. 本地缓存
    - 机制： 请求先查应用本地内存，命中直接返回；未命中再查 Redis 并回填本地。
    - 数据一致性： 结合 Redis 6.0 的 Tracking 机制（失效广播通知），当 Redis 中的 Key 被修改时，自动让客户端本地缓存失效。
2. 分散热点 Key（Key 加随机前/后缀）
    - 将单个热点 Key 拆分为多个独立的子 Key，分散落到不同的 Redis 散列槽（Hash Slot）或分片节点上。
3. 读写分离 / 增加 Counter & Slave 节点

## Window、MacOS的监听

1. FSEvents (File System Events) ：Apple 专为 macOS 设计的、极其优秀的文件监听系统
    - 以“目录”为单位在内核中记录变化（利用了文件系统的日志）
2. ReadDirectoryChangesW ：Window 标准的目录监控 API
    - 它会向内核申请一个缓冲区（Buffer）。当文件发生变化时，Windows 内核把事件写入这个缓冲区，用户态程序通过异步 I/O（IOCP 或 Overlapped）去读取。