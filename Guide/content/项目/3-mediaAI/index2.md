---
title: mediaAI2
weight: 22
date: 2026-06-12
draft: false
---

## 架构

- ai-manager：负责服务的启停，模型的管理
- npu-scheduler：NPU 租约、优先级与资源准入
- 推理服务：持有模型，完成输入校验、推理、后处理

相册发起分析请求，rknn-ai-svc 执行分析返回结果，npu-scheduler 分配 NPU 使用权

# 三端交互

```
rknn-ai-svc 收到 AnalyzePhoto
        │
        ├─ 查询结果缓存
        │     └─ 命中：直接返回，不申请 NPU
        │
        └─ 缓存未命中
              ↓
          申请 YuNet 租约
              ↓
          执行人脸检测
              ↓
          释放 YuNet 租约
              │
              ├─ 没有人脸：结束，不运行 MobileFaceNet
              │
              └─ 有人脸
                    ↓
                CPU 完成人脸对齐
                    ↓
                申请 MobileFaceNet 租约
                    ↓
                提取人脸特征
                    ↓
                释放 MobileFaceNet 租约
```

rknn-ai-svc 申请 YuNet 时，会向 npu-scheduler 发送:

| 参数 | 实际值 | 含义 |
|---|---|---|
| `pid` | rknn-ai-svc 当前进程号 | 谁在申请和持有租约 |
| `request_id` | `abc-123:yunet` | 这一次具体的模型调用 |
| `client` | `rknn-ai` | 申请者属于哪个服务 |
| `workload` | `yunet` | 准备运行哪个工作负载 |
| `deadline` | 从相册请求截止时间换算出的单调时钟时间 | 最晚可以等到什么时候 |

npu-scheduler 发放租约时，核心返回内容是：

lease_id      → 本次使用权的编号
pid           → 租约属于哪个进程
request_id    → 对应哪次模型调用
granted_at    → 什么时候获批
expires_at    → 这段租约什么时候到期

然后 rknn-ai-svc  才执行真实的 rknn_run：
```
申请租约
   ↓
等待获批
   ↓
启动租约续期
   ↓
执行对应模型的 rknn_run
   ↓
停止续期线程
   ↓
使用 lease_id + pid 释放租约
```

无论 rknn_run 成功、失败或抛异常，都会尝试释放租约。执行时间较长时，rknn-ai-svc 会在租约窗口大约过半时续租，最长每 10 秒尝试一次。

如果有人正在跑，时间线是：
```
A 正在持有租约并执行 rknn_run
B 发起 ACQUIRE
  → 调度器把 B 记入 pending 队列
  → 回复 QUEUED，关闭本轮连接
B 每 5 ms 用相同 request_id 轮询
A RELEASE
  → 调度器下次处理请求时从 pending 中选出 B 并发放租约
B 下次轮询得到 GRANTED
```

如果一直轮询到截止时间仍未获批：
```
rknn-ai-svc 发送 CANCEL(request_id, pid)
调度器移除 pending 队列记录，并留下取消标记
rknn-ai-svc 得到 NPU_LEASE_TIMEOUT
```