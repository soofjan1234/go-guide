---
title: mediaAI1
weight: 21
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

## 标签算法

1. 启动时加载模型
2. 图片路径过来时做过滤：是否有效、是否超过 50MB 或图片超过 8000x8000
3. 调用缩略图接口得到224*224
4. JNI调用算法推理
5. 算法返回每个标签的置信度，系统按每类阈值筛选出可信的标签 id。
6. 得到id映射成标签

# NPU调度

NPU 租约调度器：在多个本地 AI 服务竞争同一颗 NPU 时，决定下一次 rknn_run 由谁执行

## 优先级

选择规则依次是：

1. 先选最高优先级；
2. 若有不同 PID 的 P0 同时等待，刚刚获批的 P0 PID 不能连续再次获批；
3. 在剩余候选中，deadline 更早者优先；
4. deadline 相同，再按先入队者优先。

- 正常模式：严格按现有优先级
- 饥饿保护模式：某个仍在 scheduler 队列中的相册请求等待超过阈值后，标记“相册饥饿”。
  - 当前这一次 P0 推理结束、释放租约后，调度器只放行 一个 等待最久的 P3 租约；P3 用完立刻回到正常模式

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

MediaAI 这里的“心跳”本质是租约续约：防止正在正常执行的推理被误判超时、导致调度器把 NPU 资格发给另一个任务。

超时回收有两种：
- 租约到期：下一次 scheduler 收到任意协议请求时会执行 Tick()；发现已过期，就清掉 active_lease，再从等待队列挑下一项。
- 进程死亡：scheduler 发现 active lease 所属 PID 已退出，就取消这张租约并继续调度。

### 心跳延迟，误回收怎么办

1. 使用unix domain socket，降低了常规延迟
2. 租约时长会大于续约间隔，比如 30 秒租约、10 秒续约，并使用单调时钟判断是否真正过期。  
3. 每个租约都带 lease ID 和递增的 fencing token。租约过期并重新分配后，旧持有者后续的续约、释放或执行请求都会因为 lease ID 或代际不匹配被拒绝，不能影响新持有者。