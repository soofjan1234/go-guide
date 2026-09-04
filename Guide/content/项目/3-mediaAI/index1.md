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

## 租约

服务申请时提交：
| 字段 | 为什么调用方要提交 | scheduler 应如何使用 |
|---|---|---|
| `request_id` | 标识这一次具体推理 | 防重复入队、轮询领取结果、取消请求 |
| `PID` | 标识实际占用租约的进程 | 只允许 owner `Release/Heartbeat`，并检查进程是否已退出 |
| `client` | 声明服务身份，如 `rknn-ai` | 用于审计、策略匹配、限制优先级 |
| `deadline` | 调用方最清楚自己的 RPC 何时失效 | scheduler 用它排序；调用方超时后取消排队 |
| `lease_duration` | 声明这次 NPU 调用最长可占用多久 | 用于超时回收，避免进程卡死一直占资源 |

获得许可后会收到 lease_id。服务只能在持有这个 lease 期间执行一次 NPU 推理；正常结束必须带着 lease_id + PID 释放。

## 优先级

选择规则依次是：
1. 先选最高优先级；
2. 若有不同 PID 的 P0 同时等待，刚刚获批的 P0 PID 不能连续再次获批；
3. 在剩余候选中，deadline 更早者优先；
4. deadline 相同，再按先入队者优先。

NPU 租约调度器的作用不是自己执行推理，而是充当“唯一发号员”：在多个本地 AI 服务竞争同一颗 NPU 时，决定**下一次 `rknn_run` 由谁执行**。

```text
ASR / 实时检测 / 相册人脸
  ↓ Acquire
npu-scheduler
  ↓ GRANTED + lease_id
服务执行一次 rknn_run
  ↓ Release
scheduler 再选择下一位
```

它一次只维护一张 active lease，所以核心目标是避免多个服务同时冲进 NPU。

## 为什么 P0 还要公平轮换

若没有公平规则，实时服务 A 如果持续提交 P0 请求、且 deadline 总更早，可能长期压住实时服务 B。

例如：

```text
A(P0) 获得租约
A(P0) 又排队
B(P0) 也在排队
```

此时调度器会暂时排除 A 的下一条 P0 请求，优先让 B 获得下一张租约。

注意它按 **PID** 轮换，不是按业务名称轮换；它只保障 P0 之间不连续垄断，**不能保证 P3 相册任务不被持续 P0 流量饿死**。这是设计取舍：实时业务优先于后台相册扫描。

## deadline 的作用

deadline 有两层意义：

- 在同优先级候选中，更早到期的请求优先；
- 客户端等到自己的 deadline 仍未拿到 lease，就发送 `Cancel`，并返回 `NPU_LEASE_TIMEOUT`，绝不绕过 scheduler 直接执行 `rknn_run`。

相册调用 `AnalyzePhoto` 的总 deadline 目前覆盖：路径检查、等待租约、人脸检测、特征提取、聚类和持久化。前面花掉的时间，会减少后续可等待租约的时间。

## 心跳和超时回收

租约不是永久占有。它有 `expires_at_ms`：

```text
授予时：
expires_at = 当前时间 + lease_duration

持有者定期 Heartbeat：
expires_at = 本次心跳时间 + lease_duration
```

如果 owner 卡死、忘记释放、或者不再发心跳：

- `Tick()` 发现租约到期，清空 active lease；
- 处理新协议请求时，还会检查 owner PID 是否已退出；已退出也会回收；
- 回收后可以发放下一张租约。

这避免“进程死了，却一直占住 NPU”。

