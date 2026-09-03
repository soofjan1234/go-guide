---
title: 相册2
weight: 21
date: 2026-06-12
draft: false
---

# AI 异步任务协调器

即使相册进程重启、同一照片重复出现、旧 worker 晚回来，也不能把新结果覆盖掉。

任务流程可以概括为：

```text
图片入库
  ↓
按 SHA1 确保只有一条任务
  ↓
worker 原子领取任务，获得 claim token
  ↓
调用 MediaAI，写人脸结果
  ↓
带着 token 条件更新任务状态
```

## 步骤

1. SHA1 去重：同一内容只推理一次

2. claim token：领取任务时拿到“处理权凭证”

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

例如：

```text
worker A 领取任务，token=A
  ↓
A 卡住，进程重启或任务超时恢复
  ↓
worker B 重新领取同一任务，token=B
  ↓
B 成功写入结果并完成任务
  ↓
A 终于返回，尝试用 token=A 提交
  ↓
条件更新影响 0 行，返回 ErrMediaAIClaimLost
```

A 必须停止，不能把任务改回失败、重试或成功。  
这就是解决“旧 worker 晚回来覆盖新状态”的核心。

4. 为什么重启后任务能恢复

任务状态不放在内存队列，而是持久化在 SQLite：

- `processing_started_at`：本次处理从什么时候开始；
- `state`：当前状态；
- `claim_token`：当前处理权属于谁；
- `attempts`、`next_attempt_at`：重试调度信息。

服务启动时，会把超过处理时限、仍停留在 `processing` 的任务恢复为可领取状态。新 worker 领取后会获得新 token；旧进程即便随后恢复，也失去提交权。

因此它解决的是：**进程没了，任务不会跟着没；旧执行者回来，也不会污染新执行者的结果。**

5. 失败不是一种状态，而是两类

| 情况 | 状态 | 后续行为 |
|---|---|---|
| MediaAI 不可用、超时、临时 gRPC 错误、临时查路径或 `stat` 失败 | `failed_retryable` | 写入下次尝试时间，按 1 / 5 / 30 分钟退避后重试 |
| 文件已不存在、变成目录、参数或权限明确错误 | `failed_terminal` | 不自动重试，避免无限消耗资源 |
| AI 正常返回但无人脸 | `success_empty` | 是成功，不应反复推理 |
| AI 返回人脸并成功落库 | `success` | 任务完成 |

退避的意义是：MediaAI 短暂重启或磁盘临时异常时，不会立刻对同一任务无限重试，把服务压垮。

# gRPC

1. 为什么用 Unix Domain Socket，不用 TCP

Unix Domain Socket 是同一台 Linux 设备上进程间通信的文件型通道，不开放 TCP 端口。

它适合这个场景，因为：

- 相册和 MediaAI 都部署在同一台 NAS/设备；
- 不暴露局域网接口，攻击面更小；
- 权限由 socket 文件和所在目录权限控制；
- 仍可继续使用 gRPC 的超时、状态码、生成客户端等能力。

2. 状态码

中止：
- 请求参数不合法 
- 无权访问图片或服务拒绝访问
- 身份/认证契约不成立
- 服务明确表示目标文件/资源不存在

这些错误通常不是“等一会儿就会好”，自动重试只会反复浪费资源。

默认可重试：

- MediaAI 未启动、socket 暂不可连、服务重启中
- 推理或连接超时
- 服务暂时异常、未能可靠分类

可重试任务不会马上死循环，而是设置 `next_attempt_at`，按退避策略稍后重新领取。

## 搜索

1. 鉴权和解析请求体：时间范围、分页、关键词、搜索类型
2. 按各类搜索加条件：比如收藏、人脸、地点
3. 先构造一个gorm查询条件，然后统一进入BaseQuery做真正查询
4. 最后检查原文件是否真的存在；如果文件已经没了，会异步提交清理任务