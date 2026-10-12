---
title: 相册1
weight: 20
date: 2026-06-12
draft: false
---

# 模糊

一个图片越清晰，边缘就锋利，那么拉普拉斯方差通常更大，所以可以用一个阈值快速判断清晰度。

除此之外还可以使用 Sobel 等梯度方法，还可以训练 CNN 模型直接输出图像清晰度评分。拉普拉斯方差最简单高效

## 拉普拉斯方差

1. 拉普拉斯算子：负责找“边缘”
    - 图像处理中的二阶微分算子（求二阶导数）。
    - 物理意义：它对图像中像素灰度发生**剧烈变化的地方（即边缘、纹理、轮廓）**极度敏感。
        - 清晰图像：边缘锐利，像素明暗跳变大，经过拉普拉斯卷积后，边缘处会产生极大的正值和极大的负值。
        - 模糊图像：边缘被抹平（平滑过渡），像素变化平缓，经过拉普拉斯卷积后，所有响应值都接近 0。
2. 方差（Variance）：负责统计“响应的剧烈程度”
    - 方差衡量的是一组数据的离散程度（波动大小）。

常用的 3×3 拉普拉斯卷积核：
```
0  1  0
1 -4  1
0  1  0
```

## 阈值测试

### 测试集

1. CUHK Blur Dataset 香港中文大学的数据集不太适合，因为是局部模糊的
2. 最后使用了CERTH Image Blur Dataset 希腊研究与技术中心

### 怎么实验

1. 确定测试集：使用 CERTH 整图模糊数据集，共 2480 张照片，其中模糊照片 1850 张、清晰照片 630 张
2. 确定比较方法：比较了从 5 到 1000 的 15 个阈值，统计正确检出、漏检和误判。
3. 统计指标：
    - 正确检出率（True Positive Rate，TPR）= 检测为模糊的模糊照片 / 模糊照片总数
    - 漏检率（False Negative Rate，FNR）= 检测为清晰的模糊照片 / 模糊照片总数
    - 误判率（False Positive Rate，FPR）= 检测为模糊的清晰照片 / 清晰照片总数
4. 优化：在整图分数之外，将图片划分为 8×8 个区域，提取分块分数和边缘块比例。    
    - 尝试把判断规则从：score < 500 到 score < 500 且 edge_block_ratio < 0.05
    - 清晰照片误判从 10% 降到 5%，模糊照片检出率从 80% 降到 75%
5. 如果想进一步优化：
    - 先分析误判、漏检样本。按场景分类
    - 看看有没有别的更好的方法辅助
    - 轻量模型

### 原本清晰的大图缩放会影响吗

原图：黑 → 深灰 → 灰 → 浅灰 → 白
缩小：黑 ───────────────→ 白

## 并行处理

```
// CPU 核心数：模糊检测属于 CPU 密集计算，避免启动过多 Worker 争抢 CPU。
// 8：人为设置的并发上限
workers = min(runtime.NumCPU(), 8, photoCount)

jobs := make(chan Photo, workers*2)
results := make(chan Result, workers*2)

var wg sync.WaitGroup

// 1. Worker 只负责计算，结果发送给 Writer。
for i := 0; i < workers; i++ {
    wg.Add(1)
    go func() {
        defer wg.Done()
        for photo := range jobs {
            results <- detectBlur(photo)
        }
    }()
}

// 2. 投递完成后关闭任务通道。
go func() {
    for _, photo := range photos {
        jobs <- photo
    }
    close(jobs)
}()

// 3. 所有 Worker 退出后，才能关闭结果通道。
go func() {
    wg.Wait()
    close(results)
}()

// 4. 当前协程充当唯一 Writer，边接收边批量保存。
batch := make([]Result, 0, 100)
for result := range results {
    batch = append(batch, result)
    if len(batch) == 100 {
        saveBatch(batch) // 简化示意，省略错误处理
        batch = batch[:0]
    }
}

// 5. 通道关闭且结果读完后，保存最后不足 100 条的数据。
if len(batch) > 0 {
    saveBatch(batch)
}
```

## 单 Writer 批量写库

1. 为什么是单 writter
    - SQLite 的 WAL 模式允许读写并发，但同一数据库在同一时刻仍只有一个 Writer 能写；多个 Writer 会争用写入机会，不能同时提交
    - 实验也证明多writer写入反而变慢
2. 批量写多少，为什么是100
    - 因为主要链路的阻碍点不在这
    - 我测了 25、50、100、200、500 条，两者约 **4.429 s 和 4.428 s**，没有可辨认的稳定收益。所以目前保留 100
3. 并发写可能出现什么问题
    - 锁竞争和busy问题
    - busy_timeout=5000ms 能缓解普通写锁竞争
4. MySQL呢
    - 也会发生并发写入的锁竞争，但通常不会像 SQLite 那样，整个数据库同一时间只有一个写事务
    - 不同记录可以通过行锁隔离；同一记录可能会等待锁

# 时间轴分页查询

## 出现的问题

当用户存了4-5万张照片后，开始稳定出现慢查询，通过 Explain query plan 分析发现，查询只命中了 deleted_at 索引，排序依赖 CASE 动态计算 filming_time 或 modified_at。

## 解决方案

新增了 sort_time 字段，在媒体写入或更新时提前计算排序时间；并建立 (user_id, sort_time DESC, id DESC) 索引。

另一方面，分类查询先获取某个标签下所有 SHA，再通过 WHERE sha IN (...) 查询媒体数据，随着数据量增长，不仅需要在后端拼接超长 SQL，而且由于 IN 参数数量动态变化，数据库无法复用执行计划。因此改为 JOIN 查询，并补充关联索引。

