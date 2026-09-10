---
title: 相册2
weight: 21
date: 2026-06-12
draft: false
---

# AI 异步任务协调器

相册发起分析请求

```
文件同步 / 开启 AI
        │
        │ 创建持久化任务，只记录 SHA1
        ▼
media_ai_tasks 任务表
        │
        │ 唤醒
        ▼
AI 异步任务协调器
        │
        │ 领取任务、选路径、检查文件
        ▼
rknnAISvc.AnalyzePhoto
```

相册进程启动时，会把处于 processing 的遗留任务恢复成 pending。后续旧 worker 即使迟到，也会因为 claim_token 已失效而无法覆盖状态。

## 单个协调器

1. 不断串行处理任务；
2. 有新任务时通过 channel 快速唤醒；
3. 即使唤醒信号丢失，也会每秒轮询一次任务表；
4. 任务存在 SQLite 中，进程重启后不会全部消失。

## 领任务

只领取以下两类到期任务：
1. pending
2. failed_retryable 且已到 next_attempt_at

领取顺序为：
1. next_attempt_at 最早的优先
2. 相同时，任务 ID 更小的优先

领取成功后，数据库会原子更新：
```
state                 = processing
attempts              = attempts + 1
processing_started_at = 当前时间
claim_token           = 新 UUID
```

claim_token 可以理解为这次领取任务的“工作凭证”。后面只有持有当前凭证的 worker，才有权提交结果，防止旧 worker 覆盖新结果。

领任务后，查看是否已经有持久化人脸结果？
- 有就直接把任务标记为 success，不再调用
- 否则检查并发送请求：
  request_id:      "本次调用的唯一编号"
  deadline:        "一分钟后必须结束"
  sha1:            "这张照片内容的身份"
  absolute_path:   "/实际照片路径/a.jpg"

# gRPC 状态码

- 参数错误、权限错误、资源明确不存在时，任务进入 failed_terminal，不再自动重试。
- 暂时找不到可用图片路径、文件状态查询失败、服务不可用或调用超时时，任务进入 failed_retryable，按退避时间重试

## 搜索

1. 鉴权和解析请求体：时间范围、分页、关键词、搜索类型
2. 按各类搜索加条件：比如收藏、人脸、地点
3. 先构造一个gorm查询条件，然后统一进入BaseQuery做真正查询
4. 最后检查原文件是否真的存在；如果文件已经没了，会异步提交清理任务