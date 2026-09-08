---
title: 相册2
weight: 21
date: 2026-06-12
draft: false
---

# AI 异步任务协调器

## 步骤

1. 添加任务时，使用 SHA1 去重：同一内容只推理一次

2. 领取任务时拿到处理权凭证 claim token

worker 不能先查出 `pending` 再自行处理，因为两个 worker 可能同时查到同一条任务。

因此领取时会做一次原子条件更新：

```text
UPDATE media_ai_tasks
SET state = 'processing',
    claim_token = '本次随机令牌',
    attempts = attempts + 1
WHERE id = ?
  AND state IN ('pending', 'failed_retryable')
  AND next_attempt_at <= 当前时间;
```

谁成功把 pending 原子改成 processing，谁才真正拥有处理权。

3. 条件更新：旧 worker 不能覆盖新 worker

完成任务时，不能只根据任务 ID 更新，而是必须同时满足：

```sql
WHERE id = ?
  AND state = 'processing'
  AND claim_token = ?
```

也就是说，只有“任务仍在处理中，并且 token 仍是我当初领取的那个”的 worker 才能提交结果。

解决“旧 worker 晚回来覆盖新状态”。

4. 为什么重启后任务能恢复

任务状态不放在内存队列，而是持久化在 SQLite：

- `processing_started_at`：本次处理从什么时候开始；
- `state`：当前状态；
- `claim_token`：当前处理权属于谁；
- `attempts`、`next_attempt_at`：重试调度信息。

服务启动时，会把超过处理时限、仍停留在 `processing` 的任务恢复为可领取状态。新 worker 领取后会获得新 token；旧进程即便随后恢复，也失去提交权。

旧 worker 的结果写入靠 claim token 做条件更新来隔离；NPU 租约过期只能回收调度权，不能假设已在执行的 rknn_run 被中断。只有确认旧进程退出、推理返回，或 watchdog 完成恢复后，才能把物理 NPU 安全分配给新 worker。

# gRPC 状态码

- 参数、权限、文件有问题会中止
- 服务不可用、连接超时默认可重试

## 搜索

1. 鉴权和解析请求体：时间范围、分页、关键词、搜索类型
2. 按各类搜索加条件：比如收藏、人脸、地点
3. 先构造一个gorm查询条件，然后统一进入BaseQuery做真正查询
4. 最后检查原文件是否真的存在；如果文件已经没了，会异步提交清理任务