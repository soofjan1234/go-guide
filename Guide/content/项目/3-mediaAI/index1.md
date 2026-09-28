---
title: mediaAI1
weight: 31
date: 2026-06-12
draft: false
---

# 算法
## RKNN 平台是什么？和你的nas有什么关系

推出基于瑞芯微芯片（如RK3568、RK3588）的 ARM 架构 NAS，可以支持 RKNN 平台，通过 JNI 接口调用 native 层能力，实现模型推理。

相比于 Intel 的 x86 芯片，价格更便宜、功耗极低，因为有 NPU 的存在，它的 AI 算力很强。是1.0TOPS。

## 人脸检测和识别的流程

1. 人脸检测：使用 yunet rknn 模型，返回人脸的位置信息
    1. retinaface速度快，但漏检多
    2. scrfd误检偏多
2. 识别：使用了 mobileFaceNet 模型 ，并提取人脸特征向量
    1. sface rknn 精度一般
    2. arcface、iResNet 速度不如 mobileFaceNet
3. 和所有已有 cluster 中心比较，合并到最像的人 / 创建新 cluster
4. 合入后，做累计平均，再做一次 L2 归一化
    1. 一个 cluster 的中心会随着同一人不同角度、光线、年龄阶段的照片逐渐稳定，而不是被某一张极端照片带偏

## 为什么不使用增量聚类？怎样避免把两个人合并？0% 和 89% 分别怎么算？


## 标签算法

1. 启动时加载模型
2. 图片路径过来时做过滤：是否有效、是否超过 50MB 或图片超过 8000x8000
3. 调用缩略图接口得到224*224
4. JNI调用算法推理
5. 算法返回每个标签的置信度，系统按每类阈值筛选出可信的标签 id。
6. 得到id映射成标签

# NPU调度

## 架构

- ai-manager：负责服务的启停，模型的管理
- npu-scheduler：NPU 租约、优先级与资源准入
- 推理服务：持有模型，完成输入校验、推理、后处理

相册发起分析请求，rknn-ai-svc 执行分析返回结果，npu-scheduler 分配 NPU 使用权

## 优先级

选择规则依次是：

1. 先选最高优先级；
2. 若有不同 PID 的 P0 同时等待，刚刚获批的 P0 PID 不能连续再次获批；
3. 在剩余候选中，deadline 更早者优先；
4. deadline 相同，再按先入队者优先。

它一次只维护一张 active lease，所以核心目标是避免多个服务同时冲进 NPU。

Scheduler 进程内存
├─ has_active_lease_   // 当前是否有人持有
├─ active_lease_       // 当前那张租约的 lease_id、PID、request_id、到期时间
├─ pending_            // 等待队列
└─ cancelled_          // 已取消请求的标记

## deadline 的作用

deadline 有两层意义：

- 在同优先级候选中，更早到期的请求优先；
- 客户端等到自己的 deadline 仍未拿到 lease，就发送 `Cancel`，并返回 `NPU_LEASE_TIMEOUT`，绝不绕过 scheduler 直接执行 `rknn_run`。

相册调用 `AnalyzePhoto` 的总 deadline 目前覆盖：路径检查、等待租约、人脸检测、特征提取、聚类和持久化。前面花掉的时间，会减少后续可等待租约的时间。

## 心跳和超时回收

MediaAI 这里的“心跳”本质是租约续约，防止正在正常执行的推理被误判超时、导致调度器把 NPU 资格发给另一个任务：
- 首次租约最长为 30 秒，但不能超过照片 RPC 的原始 deadline。
- 续租间隔是“当前租约窗口的一半”，最多 10 秒。典型的 30 秒租约会每 10 秒续一次。
- 因此续租只能维持一次长推理，不可以把 NPU 永远续下去；超过原始请求 deadline 后，续租会被拒绝

超时回收有两种：
- 租约到期：下一次 scheduler 收到任意协议请求时会执行 Tick()；发现已过期，就清掉 active_lease，再从等待队列挑下一项。
- 进程死亡：scheduler 发现 active lease 所属 PID 已退出，就取消这张租约并继续调度。

### 心跳延迟，误回收怎么办

1. 使用unix domain socket，降低了常规延迟
2. 租约时长会大于续约间隔，比如 30 秒租约、10 秒续约，并使用单调时钟判断是否真正过期。  
3. 每个租约都带 lease ID 和递增的 fencing token。租约过期并重新分配后，旧持有者后续的续约、释放或执行请求都会因为 lease ID 或代际不匹配被拒绝，不能影响新持有者。
可以。这段写的是**旧的短连接、每 5 ms 轮询流程**。当前工作区已改为保持 UDS 连接、由调度器主动推送授权；但整项改造还未完成服务联调和板端验收。建议把这段替换为：

## 交互

`rknn-ai-svc` 执行 YuNet 前，向 `npu-scheduler` 发送一次 `ACQUIRE`：

| 参数 | 示例 | 含义 |
| --- | --- | --- |
| `pid` | 服务当前进程号 | 租约持有者；调度器还会核对连接的真实进程身份 |
| `request_id` | `abc-123:yunet` | 标识这一次模型调用 |
| `client` / `workload` | `rknn-ai` / `yunet` | 调度器据此校验工作负载并确定优先级 |
| `deadline` | 单调时钟截止时间 | 限制**等待和接受授权**的时间，不截断已开始的 `rknn_run` |

```text
A 持有租约，正在执行 rknn_run
B 发送一次 ACQUIRE → 调度器将 B 入队并回复 QUEUED
B 保持连接等待，不重复发送 ACQUIRE
A 发送 RELEASE → 调度器先持久化空占用记录
调度器选中 B → 先持久化 B 的占用记录，再主动推送 GRANTED
B 在等待期限内收到授权 → 执行 rknn_run，完成后 RELEASE
```

等待超时时，调度器可主动发送 `TIMEOUT`，客户端也会按自身截止时间发送 `CANCEL`；两者都不能让该请求进入推理。如果授权与超时恰好同时发生，客户端须归还迟到的租约。连接断开或授权是否送达无法确认时，调度器先进入恢复对账状态，确认安全前不发放下一张租约。
