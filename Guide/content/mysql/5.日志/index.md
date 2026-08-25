---
title: 日志
weight: 50
date: 2026-05-27
draft: false
---

## Redo Log +1

![日志.redolog.环形日志](pic/日志.redolog.环形日志.png)

重做日志，方便崩溃后恢复。默认一组循环文件。

记录的是表空间 + 页号 + 偏移做了什么修改

恢复的话是从checkpoint之后恢复，Checkpoint 之前的 Redo 对应脏页都已落盘。

### 为什么用 WAL，先写日志再刷数据页？

![日志.redolog.WAL](pic/日志.redolog.WAL.png)

写日志是顺序写，I/O 模式更简单，吞吐通常更好；刷数据是随机IO

### LSN（Log Sequence Number，日志序列号）的作用

1. 决定崩溃恢复的起点与范围
    - 确定恢复起点：直接从最后一次成功的 Checkpoint LSN 开始往后扫描
    - 幂等重做（避免重复应用）：读取某个数据页时，对比该页的 Page LSN 和 redo log 的 LSN：
        - 小于的话得重做，大于等于的话不需要重做
2. 管理 Redo Log 的循环覆写与空间释放
    - 对比 当前写入 LSN 与 Checkpoint LSN 的差值
        - 如果过大，说明脏页刷盘太慢，redo log 快要追尾了。此时会触发 Furious Flush（同步急刷盘），阻塞业务写请求，强行推进 Checkpoint LSN 释放空间

### 崩溃恢复时，只看 Redo Log 能恢复吗？

1. 两次写保证原页完整
2. Redo Log用于恢复
3. Redo 会重放未提交事务的物理修改，最后靠 Undo 回滚未提交

## Redo Log 和 Binlog、Undolog

### 区别

1. 记录形式不同
    - Redolog是什么表什么页什么偏移做了什么修改
    - Binlog是**逻辑/行级**：改了哪些行、何种事件
    - Undolog是之前的数据以及操作
2. 用处不同
    - Redolog用于崩溃后恢复
    - Binlog用于主从复制、审计
    - Undolog用于回退
3. 层级
    - RedoLog、UndoLog属于**InnoDB 存储引擎**内部
    - BinLog属于**Server 层**，与引擎解耦

### redo log能用于主从复制吗

1. 空间限制：Redo Log是环形循环写入，没有历史全量记录。
    - 如果从库网络中断断开 1 小时，等网络恢复时，主库对应的 redo log 早就被覆写了，从库根本无法追平数据
2. 层级限制：Redo Log 是 InnoDB 专有的，不具备跨引擎能力
3. 语义限制：Redo Log 是“物理日志”，极其依赖底层物理文件结构
    - 要求从库的表空间 ID、数据页分布、甚至文件碎片情况必须与主库完全物理一致

但在现代存算分离的云原生数据库中，通过共享存储突破了物理限制，已经实现了基于 Redo Log 的高效内存级复制。

## 写入顺序

![](pic/image.png)

当update语句执行时：

### 一、 执行阶段：Undo、Redo、Change Buffer 如何配合

1. 定位目标页（或走 Change Buffer）
    - 在 Buffer Pool 里找目标页。若目标是二级非唯一索引且页不在内存，可先不读该页，改写 Change Buffer 记录，后续再 merge 到真实索引页。
2. 先组织 Undo，再应用行修改
    - 先生成本次修改所需的 Undo 信息（回滚与 MVCC 读旧版本要用），再在内存中改行数据。
    - 改完后数据页（以及可能的 Undo 页）都可能成为脏页。
3. Redo 伴随页修改持续产生
    - 无论是写 Undo 页、改数据页，还是写 Change Buffer 相关页，都会把对应物理变更先写入 Redo Log Buffer。
    - 提交或触发刷盘时再按策略写入 Redo 日志文件。此时数据文件里的页仍可能是旧值，这是 WAL 的正常状态。

### 二、 提交：Redo 与 Binlog 的两阶段提交（2PC）

目标：Redo 与 Binlog 对「这个事务是否提交」达成一致，且崩溃恢复时能据此裁决。

1. Prepare（引擎）
    - InnoDB 将本事务的 Redo 刷到磁盘（达到持久化要求），事务在引擎侧标记为 prepare，尚未结束。
2. 写 Binlog（Server）
    - Server 把本次事务对应的 Binlog 事件写入 Binlog 文件并刷盘（策略受 sync_binlog 等影响）。
3. Commit（引擎）
    - Binlog 写成功后，引擎把该事务从 prepare 改为 commit，提交完成。

### 三、 崩溃恢复时怎么判

重启后若发现某事务在 Redo 里是 prepare：

1. 若 Binlog 里已有完整对应记录：说明已走到「可对外宣告」的一侧，引擎会把该事务提交。
2. 若 Binlog 里没有：说明可能在写 Binlog 前崩溃，引擎回滚该事务。

这样不会出现「从库以为提交了、主库 InnoDB 却丢了」这类单边落地。

## 两次写

辅助理解

![](pic/InnoDB.Doublewrite双写自救图.png)

刷脏页到表空间时，若崩溃发生在**写某一页写到一半**，磁盘上会出现 **partial page write（撕裂页）**，直接对该页做 Redo 可能越修越错。

InnoDB 先把脏页副本写到 **doublewrite buffer**（共享表空间中的一块连续区域），再写回真实表空间位置

恢复时若发现页校验失败，可**从 doublewrite 里的完整副本还原整页**，再对该页应用 Redo。